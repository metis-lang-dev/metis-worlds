"""situation — the RSS layer, world-independent (semantic-world step 3a; refs/rss-model.md §B, §D, §F).

The ego and every relevant mover form a PAIR, with one constellation (the pair's type), a position along the
ego's way and across it, and distances. The adapter builds the pairs from its geometry (a road's lanes, a
dungeon's lanes and areas); this layer does the rest, with numbers that never reach the rules:

- `safe_long`, `safe_lat`: the host-evaluated comparisons d > d_safe (RSS Lemma 2 same direction, Lemma 3
  opposite direction, Lemma 4 lateral), from each side's `Dynamics`;
- `able_to_stop`, `no_time_overlap`: the crossing tests (Def 17), for a conflict zone ahead;
- the memory "which axis was safe before" per pair (Def 10/18: rewritten while the pair is safe, frozen while it
  is dangerous; forgotten when the pair is gone), the one thing the past contributes;
- the response per pair (the lib's realization of Def 10/18, §B) and the FOLD over all pairs: the responses by
  their enum order (the most severe wins), the restrictions by interval intersection (the min of the maxima, the
  max of the minima): the star shape (Remark 1/8), so k independent roles suffice;
- `facts(roles)`: the booleans and enums as atoms over the bound roles, for the program; `readings`: P(hazard)
  per role, from the motion model's belief (bayes.mass_within), for a weight port.

On a dungeon the same layer runs with REACH instead of braking distance: a beast's speed in cells a turn, no
acceleration and no braking bound (it stops at will), the ego's response time one turn; a one-wide lane has no
lateral room (`lat` overlap: never laterally safe), an area has."""
from dataclasses import dataclass, field

TYPES = ("same_dir", "opp_dir", "xing_ego_prio", "xing_obj_prio", "xing_same_prio", "unstructured", "not_relevant")
LON = ("in_front", "overlap_front", "overlap", "overlap_back", "at_back")     # the OBJECT relative to the ego
LAT = ("at_left", "overlap_left", "overlap", "overlap_right", "at_right")
RESP_LON = ("none", "brake_min_correct", "brake_min")                        # the enum order: the most severe last
RESP_LAT = ("none", "brake_min")


@dataclass
class Dynamics:
    """One side's RssDynamics, in the world's units (a road: m, m/s, m/s²; a dungeon: cells, cells a turn).
    brake_* None: it stops at will (a beast, the dungeon's ego)."""
    vmin: float = 0.0
    vmax: float = 1.0
    accel: float = 0.0                 # alpha_lon.accel_max during the response time
    brake_min: float = None            # the least braking it is sure to apply (the follower's, Lemma 2)
    brake_max: float = None            # the most braking it might apply (the leader's)
    brake_min_correct: float = None    # in its correct lane, against an oncoming one (Lemma 3)
    rho: float = 1.0                   # the response time
    min_dist: float = 0.0              # the floor added to every safe distance
    lat_v: float = 0.0                 # lateral speed toward the other, accel, brake (Lemma 4)
    lat_accel: float = 0.0
    lat_brake: float = None
    mu: float = 0.0                    # the lateral fluctuation margin
    vcap: float = None                 # max_speed_on_acceleration: the speed accelerating stops at (a lane's limit)


def stated(v, accel, rho, brake, vcap=None):
    """The distance covered in the response time at ACCEL, then braking at BRAKE to a stop (RSS's stated braking
    distance); BRAKE None: it stops at will after the response time. VCAP (ad-rss max_speed_on_acceleration): the
    acceleration stops at VCAP, and a mover already at or above it does not accelerate."""
    if vcap is not None and accel > 0 and v + accel * rho > vcap:
        if v >= vcap:                                           # no acceleration at all: the response time at v
            v1, d = v, v * rho
        else:                                                   # up to vcap, then on at vcap
            tc = (vcap - v) / accel
            v1, d = vcap, v * tc + 0.5 * accel * tc * tc + vcap * (rho - tc)
    else:
        v1, d = v + accel * rho, v * rho + 0.5 * accel * rho * rho
    return d + (v1 * v1 / (2 * brake) if brake else 0.0)


def stated_of(dyn, brake):
    """A side's stated braking distance from its top speed, with its own vcap."""
    return stated(dyn.vmax, dyn.accel, dyn.rho, brake, dyn.vcap)


def stop(v, brake):
    """A leader's stopping distance braking at BRAKE (None: at once)."""
    return v * v / (2 * brake) if brake else 0.0


def safe_same_dir(follower, leader):
    """Lemma 2 with speed ranges and a floor: the follower's stated braking from its top speed less the leader's
    stop from its least, never below zero, plus the follower's floor."""
    return max(stated_of(follower, follower.brake_min) - stop(leader.vmin, leader.brake_max), 0.0) \
        + follower.min_dist


def safe_opp_dir(correct, opposite):
    """Lemma 3: both stated braking distances, the one in its correct lane at its own (gentler) bound, plus the
    larger floor."""
    return stated_of(correct, correct.brake_min_correct or correct.brake_min) \
        + stated_of(opposite, opposite.brake_min) + max(correct.min_dist, opposite.min_dist)


def safe_lat_dist(left, right):
    """Lemma 4 over the two lateral speeds toward each other (lat_v ≥ 0 means toward the other side)."""
    return max(stated(left.lat_v, left.lat_accel, left.rho, left.lat_brake) + stated(right.lat_v, right.lat_accel, right.rho, right.lat_brake), 0.0) \
        + 0.5 * (left.mu + right.mu)


def time_to(d, v, accel, vcap=None):
    """The earliest time a mover at V accelerating at ACCEL (capped at VCAP) covers D: None if it never does."""
    if d <= 0:
        return 0.0
    if accel <= 0:
        return d / v if v > 0 else None
    import math
    if vcap is not None and v >= vcap:                          # at or above its cap: no acceleration
        return d / v if v > 0 else None
    t = (-v + math.sqrt(v * v + 2 * accel * d)) / accel
    if vcap is not None and v + accel * t > vcap:
        tc = (vcap - v) / accel
        dc = v * tc + 0.5 * accel * tc * tc
        return tc + (d - dc) / vcap if vcap > 0 else None
    return t


def time_to_brake(d, v, brake):
    """The latest time a mover at V braking at BRAKE covers D (ad-rss's latest leave: the least speed, braking as
    hard as it might): None if it stops first (it may never leave); BRAKE None: it stops at will, so None unless
    D ≤ 0."""
    if d <= 0:
        return 0.0
    if not brake:
        return None
    import math
    disc = v * v - 2 * brake * d
    if v <= 0 or disc < 0:
        return None
    return (v - math.sqrt(disc)) / brake


@dataclass
class Pair:
    """The ego and one object, as the adapter sees them this cycle. id: stable across cycles for the same object and
    constellation (the memory's key); role: the object's role in the binding (b1, obj_3, …), or None unbound."""
    id: str
    type: str
    lon: str = "in_front"
    lat: str = "overlap"
    d_lon: float = 0.0                 # the gap along the ego's way (0 when overlapping)
    d_lat: float = 0.0                 # the gap across (0 when overlapping; a one-wide lane: always 0)
    ego: Dynamics = field(default_factory=Dynamics)
    obj: Dynamics = field(default_factory=Dynamics)
    ego_correct: bool = True           # opposite direction: the ego is in its correct lane
    lateral_room: bool = True          # False: a one-wide lane (no lateral evasion exists)
    d_enter: float = None              # a crossing: each side's distance to enter and to leave the conflict zone
    d_leave: float = None
    o_enter: float = None
    o_leave: float = None
    role: str = None


XING = ("able_to_stop", "safe_long", "no_overlap")    # Def 17's three cases, the one that held (Def 18's memory)


@dataclass
class State:
    """One pair's verdict this cycle."""
    id: str
    type: str
    role: str
    safe_long: bool
    safe_lat: bool
    dangerous: bool
    before: tuple                      # (long safe, lat safe) at the last safe cycle; None: never seen safe
    resp_lon: str
    resp_lat: str
    d_lon: float
    d_safe: float
    safe_lat_left: bool = True         # the lateral split (ad-rss lateral_state_left/right): the side the object is on
    safe_lat_right: bool = True
    resp_lat_left: str = "none"        # the pair's lateral response, per side (brake only toward the other)
    resp_lat_right: str = "none"
    xing: str = None                   # a crossing: the Def 17 case that holds now (None: none holds, or not a crossing)
    xing_before: tuple = None          # a crossing: (case, ego in front) at the last safe cycle (Def 18); None: never safe


def check_long(p):
    """→ (safe, d_safe) along the ego's way."""
    if p.type == "not_relevant":
        return True, 0.0
    if p.type == "same_dir":
        if p.lon in ("in_front", "overlap_front"):              # the object ahead: the ego follows
            ds = safe_same_dir(p.ego, p.obj)
        else:                                                   # the object behind: it follows the ego
            ds = safe_same_dir(p.obj, p.ego)
        return p.d_lon > ds, ds
    if p.type == "opp_dir":
        ds = safe_opp_dir(p.ego, p.obj) if p.ego_correct else safe_opp_dir(p.obj, p.ego)
        return p.d_lon > ds, ds
    if p.type.startswith("xing"):
        return check_xing(p)
    return p.d_lon > p.ego.min_dist, p.ego.min_dist             # unstructured: the bare floor


def check_lat(p):
    """→ safe across the way: never in a one-wide lane or at a crossing (the lib's: lateral conflict assumed)."""
    left, right = check_lat_sides(p)
    return left and right


def check_lat_sides(p):
    """→ (safe on the ego's left, safe on its right): ad-rss's lateral_state_left / _right. The object at (or
    overlapping) the ego's left is judged on the left side only, with it as the left one of Lemma 4; at the right,
    on the right side; overlapping, or at a crossing, or in a one-wide lane, neither side is safe."""
    if p.type == "not_relevant":
        return True, True
    if not p.lateral_room or p.type.startswith("xing") or p.lat == "overlap":
        return False, False
    if p.lat in ("at_left", "overlap_left"):
        return p.d_lat > safe_lat_dist(p.obj, p.ego), True
    return True, p.d_lat > safe_lat_dist(p.ego, p.obj)


def check_xing(p):
    """Def 17's cascade at a conflict zone (ad-rss checkIntersectionSafe). → (safe, d_safe)."""
    safe, ds, _case, _front = xing_case(p)
    return safe, ds


def ego_in_front(p):
    """Def 16 on different routes: True when the ego is in front (it leaves the zone before the object reaches it),
    False when the object is, None when neither is wholly in front."""
    if None in (p.d_enter, p.d_leave, p.o_enter, p.o_leave):
        return None
    if p.d_leave < p.o_enter:
        return True
    if p.o_leave < p.d_enter:
        return False
    return None


def xing_case(p):
    """Def 17's cascade → (safe, d_safe, the case that holds or None, ego in front or None):
    (1) the one without priority is able to stop before entering the zone (its stated braking plus its floor);
    (2) one is wholly in front (Def 16: it leaves the zone before the other reaches it), and the rear one keeps
        Lemma 2's distance to it through the zone: the distance from the rear one's entry to the front one's leave;
    (3) no time overlap: the earliest arrival of one after the latest leave of the other."""
    ego_stop = stated_of(p.ego, p.ego.brake_min) + p.ego.min_dist
    obj_stop = stated_of(p.obj, p.obj.brake_min) + p.obj.min_dist
    front = ego_in_front(p)
    if p.type in ("xing_obj_prio", "xing_same_prio") and p.d_enter is not None and ego_stop < p.d_enter:
        return True, ego_stop, "able_to_stop", front
    if p.type in ("xing_ego_prio", "xing_same_prio") and p.o_enter is not None and obj_stop < p.o_enter:
        return True, obj_stop, "able_to_stop", front
    if front is True:                                       # the ego in front: the object follows it through
        ds = safe_same_dir(p.obj, p.ego)
        if p.o_enter - p.d_leave > ds:
            return True, ds, "safe_long", front
    elif front is False:                                    # the object in front: the ego follows it
        ds = safe_same_dir(p.ego, p.obj)
        if p.d_enter - p.o_leave > ds:
            return True, ds, "safe_long", front
    if no_time_overlap(p):
        return True, 0.0, "no_overlap", front
    return False, ego_stop, None, front


def no_time_overlap(p):
    """The ego's earliest arrival after the object's latest leave, or the other way round, or one never arrives.
    The earliest arrival accelerates from the top speed up to the side's vcap; the latest leave brakes from the least
    speed at brake_max (ad-rss checkLateralIntersect): one that may stop inside the zone never surely leaves."""
    if None in (p.d_enter, p.d_leave, p.o_enter, p.o_leave):
        return False
    e_in = time_to(p.d_enter, p.ego.vmax, p.ego.accel, p.ego.vcap)
    o_in = time_to(p.o_enter, p.obj.vmax, p.obj.accel, p.obj.vcap)
    if e_in is None or o_in is None:
        return True
    e_out = time_to_brake(p.d_leave, p.ego.vmin, p.ego.brake_max)
    o_out = time_to_brake(p.o_leave, p.obj.vmin, p.obj.brake_max)
    return (o_out is not None and e_in > o_out) or (e_out is not None and o_in > e_out)


def able_to_stop(dyn, d_enter):
    """X able to stop before a zone D_ENTER away (its stated braking plus its floor)."""
    return stated_of(dyn, dyn.brake_min) + dyn.min_dist < d_enter


def past_last_stop(dyn, d_enter):
    """X past its last point to stop before a zone D_ENTER away: even braking its hardest (brake_max) from the speed
    it has, with no response time, it would not stop short of the line + its floor. The evidence that it does not
    yield (RSS rule 5's trigger; the stated distance, worst-case accelerating through its response time, is past the
    line for every car that comes on, a yielding one too)."""
    return stop(dyn.vmin if dyn.vmin is not None else dyn.vmax, dyn.brake_max) + dyn.min_dist >= d_enter


def ego_stops_short(dyn, d_enter):
    """The ego can still stop short of a zone D_ENTER away braking at its proper response (brake_min) from the speed
    it has: the floor kept. Inside the zone (D_ENTER 0), or past that point, braking would hold it in the conflict:
    the proper response is to clear it (road-2 item 1, the step 6 ruling)."""
    if d_enter is None or d_enter <= 0:
        return False
    return stop(dyn.vmax, dyn.brake_min) + dyn.min_dist < d_enter


class Situation:
    """The per-pair memory across cycles and the fold. One per ego; `check(pairs)` every cycle, in order."""

    def __init__(self, memory=None, xmemory=None):
        self.memory = dict(memory or {})          # pair id -> (long safe, lat safe) at its last safe cycle
        self.xmemory = dict(xmemory or {})        # a crossing's id -> (Def 17 case, ego in front) at its last safe cycle
        self.escalated = set()                    # crossings whose priority holder's response escalated (RSS rule 5)

    def check(self, pairs):
        """→ [State] for PAIRS (the memory updated: rewritten while safe, frozen while dangerous, dropped for pairs
        no longer present)."""
        out, seen = [], set()
        for p in pairs:
            seen.add(p.id)
            xing = front = None
            if p.type.startswith("xing"):
                lon, ds, xing, front = xing_case(p)
            else:
                lon, ds = check_long(p)
            left, right = check_lat_sides(p)
            lat = left and right
            dangerous = not lon and not lat
            before = self.memory.get(p.id)
            xbefore = self.xmemory.get(p.id)
            if not dangerous:
                self.memory[p.id] = (lon, lat)
                if xing:
                    self.xmemory[p.id] = (xing, front)
            r_lon, r_lat = respond(p, dangerous, before, xbefore, escalated=p.id in self.escalated)
            if dangerous and p.type == "xing_ego_prio" and r_lon == "brake_min":
                self.escalated.add(p.id)          # held at least that while the pair stays dangerous
            else:
                self.escalated.discard(p.id)      # safe again, or released (the other stopped; the ego past stopping short)
            out.append(State(p.id, p.type, p.role, lon, lat, dangerous, before if dangerous else (lon, lat),
                             r_lon, r_lat, round(p.d_lon, 6), round(ds, 6), left, right,
                             r_lat if not left else "none", r_lat if not right else "none",
                             xing, xbefore if dangerous else ((xing, front) if xing else xbefore)))
        for k in [k for k in self.memory if k not in seen]:
            self.memory.pop(k)
        for k in [k for k in self.xmemory if k not in seen]:
            self.xmemory.pop(k)
        self.escalated &= seen
        return out

    @staticmethod
    def fold(states, ego):
        """The proper response over all pairs (§D): responses by enum max; the ego's longitudinal acceleration range
        [brake_max, accel] narrowed by each response (BrakeMin: at most −brake_min; BrakeMinCorrect: at most
        −brake_min_correct), lateral likewise. → {"resp_lon", "resp_lat", "lon_range", "lat_max", "dangerous":
        [roles or ids]}."""
        r_lon, r_lat = "none", "none"
        r_left, r_right = "none", "none"
        lo = -(ego.brake_max if ego.brake_max else float("inf"))
        hi = ego.accel
        lat_hi = ego.lat_accel
        left_hi = right_hi = ego.lat_accel
        bad = []
        for s in states:
            if not s.dangerous:
                continue
            bad.append(s.role or s.id)
            r_lon = max(r_lon, s.resp_lon, key=RESP_LON.index)
            r_lat = max(r_lat, s.resp_lat, key=RESP_LAT.index)
            if s.resp_lon == "brake_min":
                hi = min(hi, -(ego.brake_min or 0.0))
            elif s.resp_lon == "brake_min_correct":
                hi = min(hi, -(ego.brake_min_correct or ego.brake_min or 0.0))
            if s.resp_lat == "brake_min":
                lat_hi = min(lat_hi, -(ego.lat_brake or 0.0))
            r_left = max(r_left, s.resp_lat_left, key=RESP_LAT.index)
            r_right = max(r_right, s.resp_lat_right, key=RESP_LAT.index)
            if s.resp_lat_left == "brake_min":
                left_hi = min(left_hi, -(ego.lat_brake or 0.0))
            if s.resp_lat_right == "brake_min":
                right_hi = min(right_hi, -(ego.lat_brake or 0.0))
        return {"resp_lon": r_lon, "resp_lat": r_lat, "lon_range": [lo, hi], "lat_max": lat_hi, "dangerous": bad,
                "resp_lat_left": r_left, "resp_lat_right": r_right,
                "lat_left_max": left_hi, "lat_right_max": right_hi}

    @staticmethod
    def facts(states, folded=None, detail=False):
        """The program's atoms over the bound roles (a pair whose object has no role is not said): the type, the
        booleans, the memory, the pair's response, and the folded response once (resp_lon(R), resp_lat(R)).
        DETAIL (a program that declares them; the road's): also the lateral split, safe_lat_left(o) /
        safe_lat_right(o); the pair's lateral response, resp_side(o, left|right, brake_min) (not resp_lat: a pred
        has one arity, and resp_lat(R) is the fold's); at a crossing the Def 17 case that holds, xing_case(o,
        able_to_stop|safe_long|no_overlap), and when dangerous the case held before (Def 18), xing_before(o, …|none);
        and the fold's resp_lat_left(R), resp_lat_right(R)."""
        out = {}
        for s in states:
            if not s.role:
                continue
            o = s.role
            out["type(%s,%s)" % (o, s.type)] = 1
            if s.safe_long:
                out["safe_long(%s)" % o] = 1
            if s.safe_lat:
                out["safe_lat(%s)" % o] = 1
            if s.dangerous:
                out["dangerous(%s)" % o] = 1
                before = s.before
                out["safe_before(%s,%s)" % (o, "none" if before is None else "long" if before[0] and not before[1]
                                             else "lat" if before[1] and not before[0] else "both")] = 1
            if s.resp_lon != "none":
                out["resp(%s,%s)" % (o, s.resp_lon)] = 1
            if detail:
                if s.safe_lat_left:
                    out["safe_lat_left(%s)" % o] = 1
                if s.safe_lat_right:
                    out["safe_lat_right(%s)" % o] = 1
                if s.resp_lat_left != "none":
                    out["resp_side(%s,left,%s)" % (o, s.resp_lat_left)] = 1
                if s.resp_lat_right != "none":
                    out["resp_side(%s,right,%s)" % (o, s.resp_lat_right)] = 1
                if s.type.startswith("xing"):
                    if s.xing:
                        out["xing_case(%s,%s)" % (o, s.xing)] = 1
                    if s.dangerous:
                        out["xing_before(%s,%s)" % (o, s.xing_before[0] if s.xing_before else "none")] = 1
        if folded is not None:
            out["resp_lon(%s)" % folded["resp_lon"]] = 1
            out["resp_lat(%s)" % folded["resp_lat"]] = 1
            if detail:
                out["resp_lat_left(%s)" % folded.get("resp_lat_left", "none")] = 1
                out["resp_lat_right(%s)" % folded.get("resp_lat_right", "none")] = 1
        return out


def respond(p, dangerous, before, xbefore=None, escalated=False):
    """The pair's responses (§B, the lib's realization of Def 10/18). → (resp_lon, resp_lat).
    At a crossing, Def 18 by the case that held at the last safe cycle (XBEFORE = (case, ego in front)): the
    non-priority one was able to stop and the ego has priority → none (the other brakes), until it is past its last
    point to stop (past_last_stop: braking its hardest from its speed it would not stop short of the line; RSS rule
    5, right of way is given, not taken; road step 5b): then brake_min, held while the pair is dangerous
    (ESCALATED; the blame stays Def 18's onset decision, the memory's) — only while the ego can still stop short of
    the zone (ego_stops_short: inside it, clear it, never hold), and released once the other has stopped (road-2
    item 1); one was in front at a safe
    distance and it was the ego → none (the front one drives on); otherwise (no time overlap held, the ego was the
    rear one or the non-priority one, or never safe) → brake_min. Lateral: none (a conflict is assumed)."""
    if not dangerous or p.type == "not_relevant":
        return "none", "none"
    if p.type.startswith("xing"):
        case, front = xbefore or (None, None)
        if case == "able_to_stop" and p.type == "xing_ego_prio":
            stopped = (p.obj.vmax or 0.0) <= 0.0               # the other has stopped: it yields after all
            if not stopped and ego_stops_short(p.ego, p.d_enter) and (
                    escalated or (p.o_enter is not None and past_last_stop(p.obj, p.o_enter))):
                return "brake_min", "none"                     # it does not yield: the ego avoids it if it can
            return "none", "none"                              # inside, or past stopping short: clear it, never hold
        if case == "safe_long" and front is True:
            return "none", "none"
        return "brake_min", "none"
    lon = "brake_min_correct" if p.type == "opp_dir" and p.ego_correct else "brake_min"
    if p.type == "same_dir" and p.lon in ("at_back", "overlap_back"):
        lon = "none"                                            # the follower is the object: its response, not ours
    lat = "brake_min" if p.lateral_room else "none"
    if before is None:                                          # appeared dangerous: brake everything; same dir and
        if p.type == "same_dir" and p.lat == "overlap":         # overlapping laterally: as if long-safe before, so
            return lon, "none"                                  # along the way only (§B's table; its aside reads the other way)
        return lon, lat
    long_before, lat_before = before
    if long_before and lat_before:
        return lon, lat
    if lat_before:                                              # laterally safe before: brake laterally
        return "none", lat
    return lon, "none"                                          # longitudinally safe before: brake along the way
