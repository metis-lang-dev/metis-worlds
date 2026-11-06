"""levelk — the one-step game at an unsettled zone, the host's half of the road family's levelk.llp (levelk-intersection
s-5be9291b step 2; the design: metis-worlds road/docs/LEVELK.md §2 and §4; the idea: Li, Kolmanovsky, Girard, Yildiz 2018 and
the TUM-2024 planner's interactive module; level-k is bounded recursion, not a Nash equilibrium). Rule 2: the geometry and the
reward are here, the levels and the decision are the law's.

Per crosser (a crossing Pair: the ego and the other each with their distance to enter and to leave the conflict zone and their
dynamics):
- MOVES along the lane only: go (accelerate toward the zone at the dynamics' accel, to the cap), hold (keep the present speed),
  yield (brake to stop short of the zone's entry, at most brake_max).
- the ROLLOUT: both bodies under a pair of moves over HORIZON (3 s at DT 0.1), each one's zone occupancy [t_in, t_out].
- the REWARD of one side: - W_COLLISION · (the occupancies overlap) - W_SAFE · (T_SAFE short of the time gap between them)
  + W_PROGRESS · (its distance covered over what its cap allows) + W_LANE · 0 (moves keep the lane: the term is there for the
  form and stays 0). The weights are host constants (spec 19's rates: fit by notching from the catalog later, never in a rule).
- the TABLES (the law's vocabulary): myopic(O, M) its best move ignoring the ego's reaction (the ego a standing obstacle where
  it is, Li et al.'s level 0: short of the zone it never enters, inside it it stays); ego_myopic(E) the ego's against a standing
  O; both pairwise, per crosser (ego_myopic(O, E), ego_reply(O, M, E): the architect's ruling); reply(O, E, M) O's best move if the ego plays E; ego_reply(M, E) the ego's best move if O plays M.
- the BELIEF over O's level {l0, l1, l2} (spec 16's categorical port), prior PRIOR; each tick O's observed move (from its
  acceleration, OBS_A) updates it with a SOFTMAX likelihood over O's rewards under what that level assumes the ego plays
  (l0: a standing ego, l1: ego_myopic, l2: ego_reply(myopic(O))), temperature TEMP, a floor FLOOR so a driver who changes is followed
  within a few ticks; believed = argmax; level_belief quantised low / mid / high (BLEVEL).
- the ZONE's reading: by_rule where a priority (a sign, a light, right-before-left: the pair's type says who has it) settles it
  and O's moves follow it; by_game where the rule is silent (xing_same_prio) or O's last moves contradict it (the holder holds
  or yields, the yielder keeps coming) — and never where the belief is spread (no level above mid): there the rule's law holds."""
import math

MOVES = ("go", "hold", "yield")
STAND = "stand"                              # not a move: the key of the other body standing still in the reward tables
LEVELS = ("l0", "l1", "l2")
HORIZON, DT = 3.0, 0.1
W_COLLISION, W_SAFE, W_PROGRESS, W_LANE = 100.0, 10.0, 1.0, 0.0
T_SAFE = 1.0                                 # s: the time gap between the two occupancies the safe term asks for
PRIOR = {"l0": 0.2, "l1": 0.6, "l2": 0.2}    # the source's prior
TEMP = 0.5                                   # the softmax likelihood's temperature (reward units)
FLOOR = 0.02                                 # every level keeps this much: a driver who changes is followed
OBS_A = 0.5                                  # m/s²: an acceleration above +OBS_A is go, below -OBS_A yield, else hold
BLEVEL = ((1.0 / 3.0, "low"), (2.0 / 3.0, "mid"), (1.01, "high"))
CONTRADICT_TICKS = 5                         # O's moves against the rule's prediction this many ticks in a row: by_game


# ── one side ──
class Side:
    """One body against the zone: D_IN, D_OUT (m from its front to the zone's entry, and to its rear having left it), its speed V,
    ACCEL, BRAKE (its hardest), CAP (its speed cap)."""
    __slots__ = ("d_in", "d_out", "v", "accel", "brake", "cap")

    def __init__(self, d_in, d_out, v, accel=2.0, brake=8.0, cap=None):
        self.d_in, self.d_out, self.v = float(d_in), float(d_out), max(0.0, float(v))
        self.accel, self.brake = float(accel or 2.0), float(brake or 8.0)
        self.cap = float(cap) if cap else max(self.v, 1.0) * 1.5


def side_of(pair, ego=True):
    """The ego's (or the other's) Side from a crossing Pair (situation.Pair: d_enter / d_leave, o_enter / o_leave, the dynamics)."""
    if ego:
        dyn, d_in, d_out = pair.ego, pair.d_enter, pair.d_leave
    else:
        dyn, d_in, d_out = pair.obj, pair.o_enter, pair.o_leave
    v = dyn.vmax or 0.0
    return Side(d_in or 0.0, d_out if d_out is not None else (d_in or 0.0) + 5.0, v, dyn.accel, dyn.brake_max, dyn.vcap)


def accel_of(side, move):
    if move == "go":
        return side.accel
    if move == "hold":
        return 0.0
    room = side.d_in - 0.5                                  # yield: stop short of the entry, at most at its hardest
    if side.v <= 0.0:
        return 0.0
    if room <= 0.0:
        return -side.brake
    return -min(side.brake, side.v * side.v / (2.0 * room))


def occupancy(side, move, horizon=HORIZON, dt=DT):
    """[t_in, t_out] the body occupies the zone under MOVE within the horizon (t_out = inf while still in at its end; None: never
    enters), and the distance it covered."""
    a, s, v, t = accel_of(side, move), 0.0, side.v, 0.0
    if side.d_out <= 0.0:                                   # already past the zone: it occupies nothing
        return (None, None), _covered(side, a, horizon, dt)
    t_in = 0.0 if side.d_in <= 0.0 else None
    t_out = None
    while t < horizon - 1e-9:
        v = min(side.cap, max(0.0, v + a * dt))
        s += v * dt
        t += dt
        if t_in is None and s >= side.d_in:
            t_in = t
        if t_in is not None and t_out is None and s >= side.d_out:
            t_out = t
    if t_in is not None and t_out is None:
        t_out = math.inf
    return (t_in, t_out), s


def _covered(side, a, horizon, dt):
    s, v, t = 0.0, side.v, 0.0
    while t < horizon - 1e-9:
        v = min(side.cap, max(0.0, v + a * dt))
        s += v * dt
        t += dt
    return s


def reward(me, other, m_me, m_other):
    """ME's reward when ME plays M_ME and OTHER plays M_OTHER."""
    (a_in, a_out), s = occupancy(me, m_me)
    (b_in, b_out), _ = occupancy(other, m_other)
    collision, gap = 0.0, math.inf
    if a_in is not None and b_in is not None:
        if a_in < b_out and b_in < a_out:
            collision, gap = 1.0, 0.0
        else:
            gap = (b_in - a_out) if a_out <= b_in else (a_in - b_out)
    safe = max(0.0, T_SAFE - gap) if gap != math.inf else 0.0
    progress = s / max(1e-6, me.cap * HORIZON)
    return -W_COLLISION * collision - W_SAFE * safe + W_PROGRESS * progress + W_LANE * 0.0


def standing(side):
    """SIDE stopped where it is (the level-0 view of the other body)."""
    return Side(side.d_in, side.d_out, 0.0, side.accel, side.brake, side.cap)


def best(scores):
    """The best move of {move: score}; ties to the more careful move (yield, then hold, then go)."""
    order = {"yield": 0, "hold": 1, "go": 2}
    return max(scores, key=lambda m: (round(scores[m], 9), -order[m]))


# ── the tables ──
def tables(ego, other):
    """The one-step game's tables of a crosser: {myopic, ego_myopic, reply {E: M}, ego_reply {M: E}, and the rewards}."""
    r_o = {(e, m): reward(other, ego, m, e) for e in MOVES for m in MOVES}     # the other's reward: it plays m, the ego e
    r_e = {(m, e): reward(ego, other, e, m) for e in MOVES for m in MOVES}     # the ego's: the other m, the ego e
    still_e, still_o = standing(ego), standing(other)
    for m in MOVES:                                                            # STAND: the other body standing (level 0's view)
        r_o[(STAND, m)] = reward(other, still_e, m, "hold")
        r_e[(STAND, m)] = reward(ego, still_o, m, "hold")
    myopic = best({m: r_o[(STAND, m)] for m in MOVES})
    ego_myopic = best({e: r_e[(STAND, e)] for e in MOVES})
    reply = {e: best({m: r_o[(e, m)] for m in MOVES}) for e in MOVES}
    ego_reply = {m: best({e: r_e[(m, e)] for e in MOVES}) for m in MOVES}
    return {"myopic": myopic, "ego_myopic": ego_myopic, "reply": reply, "ego_reply": ego_reply, "r_other": r_o, "r_ego": r_e}


def assumed_ego(t, level):
    """The ego move a level-k other expects: l0 a standing ego (STAND), l1 the ego's myopic move, l2 the ego's reply to its
    myopic move."""
    return {"l0": STAND, "l1": t["ego_myopic"], "l2": t["ego_reply"][t["myopic"]]}[level]


def predicted(t, level):
    """The other's move at LEVEL (the law's chains): l0 myopic; l1 reply(ego_myopic); l2 reply(ego_reply(myopic))."""
    return t["myopic"] if level == "l0" else t["reply"][assumed_ego(t, level)]


# ── the belief ──
def observed_move(dv, dt=DT, v=None, cap=None):
    """The other's move this tick from its speed change DV; at its cap (V >= CAP) going and holding look the same: go."""
    a = dv / dt
    if a < -OBS_A:
        return "yield"
    if a > OBS_A or (cap is not None and v is not None and v >= cap - 1e-6 and v > 0.0):
        return "go"
    return "hold"


def likelihood(t, level, move):
    """P(the other plays MOVE | it reasons at LEVEL): a softmax of its rewards under the ego move that level assumes."""
    e = assumed_ego(t, level)
    q = {m: t["r_other"][(e, m)] / TEMP for m in MOVES}
    top = max(q.values())
    z = sum(math.exp(v - top) for v in q.values())
    return math.exp(q[move] - top) / z


def update(belief, t, move):
    """The posterior over the other's level after it played MOVE (FLOOR kept on every level)."""
    post = {k: belief.get(k, 0.0) * likelihood(t, k, move) for k in LEVELS}
    z = sum(post.values()) or 1.0
    post = {k: max(FLOOR, v / z) for k, v in post.items()}
    z = sum(post.values())
    return {k: v / z for k, v in post.items()}


def believed(belief):
    return max(LEVELS, key=lambda k: (belief.get(k, 0.0), -LEVELS.index(k)))


def quantise(p):
    return next(name for edge, name in BLEVEL if p < edge)


def spread(belief):
    """No level above mid: the belief cannot name the other's reasoning, so the rule's law holds (by_rule)."""
    return all(quantise(p) != "high" for p in belief.values())


# ── the zone's reading ──
def rule_move(pair_type, side="other"):
    """What the rule predicts the other plays: the holder (xing_obj_prio: the other has the way) goes; the yielder (xing_ego_prio)
    yields; xing_same_prio: the rule is silent (None)."""
    return {"xing_obj_prio": "go", "xing_ego_prio": "yield"}.get(pair_type)


def zone_game(pair_type, contradicted, belief):
    """by_rule | by_game for the zone: by_game where the rule is silent or the other's moves contradicted it for CONTRADICT_TICKS,
    and the belief is not spread; else by_rule."""
    silent = rule_move(pair_type) is None
    if (silent or contradicted >= CONTRADICT_TICKS) and not spread(belief):
        return "by_game"
    return "by_rule"


class Game:
    """The host's memory across ticks: per crosser its belief, its last speed and how many ticks its moves contradicted the rule.
    step(key, pair, dt) → the crosser's tables, belief, believed level and the zone's reading, after the tick's observation."""

    def __init__(self, prior=None, dt=DT):
        self.prior, self.dt = dict(prior or PRIOR), float(dt)
        self.belief, self.last_v, self.contra = {}, {}, {}

    def step(self, key, pair, dt=None):
        dt = self.dt if dt is None else dt
        ego, other = side_of(pair, True), side_of(pair, False)
        t = tables(ego, other)
        b = self.belief.get(key, dict(self.prior))
        v0 = self.last_v.get(key)
        move = None
        if v0 is not None:
            move = observed_move(other.v - v0, dt, other.v, pair.obj.vcap)
            b = update(b, t, move)
            want = rule_move(pair.type)
            self.contra[key] = self.contra.get(key, 0) + 1 if (want is not None and move != want) else 0
        self.belief[key], self.last_v[key] = b, other.v
        return {"tables": t, "belief": b, "believed": believed(b), "observed": move,
                "zone": zone_game(pair.type, self.contra.get(key, 0), b)}

    def forget(self, keep):
        for d in (self.belief, self.last_v, self.contra):
            for k in [k for k in d if k not in keep]:
                d.pop(k)


def facts(role, result):
    """The law's atoms for a crosser bound to ROLE (levelk.llp's preds), from Game.step's RESULT. The ego's tables are
    pairwise (the architect's ruling, step 2): ego_myopic(O, E) and ego_reply(O, M, E), the ego's best move against O alone.
    crosser(nextzone, O) and the zone's reading are the caller's (one per zone)."""
    t, b = result["tables"], result["belief"]
    out = {"myopic(%s,%s)" % (role, t["myopic"]): 1, "ego_myopic(%s,%s)" % (role, t["ego_myopic"]): 1}
    for e, m in t["reply"].items():
        out["reply(%s,%s,%s)" % (role, e, m)] = 1
    for m, e in t["ego_reply"].items():
        out["ego_reply(%s,%s,%s)" % (role, m, e)] = 1
    for k in LEVELS:
        out["level_belief(%s,%s,%s)" % (role, k, quantise(b[k]))] = 1
    out["believed(%s,%s)" % (role, result["believed"])] = 1
    return out
