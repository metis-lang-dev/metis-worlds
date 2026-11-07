"""intersection — the small level-k world under the exerciser (levelk-intersection s-5be9291b step 3; LEVELK.md §5).

One unsignalised junction, no signs: four arms (S, E, N, W) of one lane each way, right-hand traffic, a box of 2·HALF
metres. A car's way through it is one PATH (`S_N`: in from the south, out to the north; `S_W`: in from the south, a left
turn out to the west), one exerciser Lane of the approach, the box and the exit, with its centre line. Where two paths'
centre lines come within ZONE_GAP of each other they share a conflict ZONE (each path's s-interval there); its priority
is the road's rule without signs: the car going straight over the one turning left against it (StVO §9(3)), else the car
from the right (right-before-left, StVO §8(1)).

The ego is the family's, as on the exerciser (RoadWorld's step, restrictor and accounting). The other cars are LEVEL-K
DRIVERS of the host's own game (semantic_world.levelk): each tick a driver at level K takes the mover whose zone with it is
the most urgent (the ego or another driver, not yet past it, within APPROACH of it) and plays levelk.predicted(K) against
it: go (to its cap), hold (its speed) or yield (stop short of the line). Past its zones it goes. The world runs the ego's
game (levelk.Game, RoadWorld(levelk=True)'s), so the family reads crosser / the tables / the belief at every zone.

The measures beside RoadWorld's (summary): `deadlock_s` (the longest stretch every car still short of its zones and within
APPROACH of them, at least two, stood with the zones empty) and `deadlock` (≥ DEADLOCK_S); `clear_t` (the ego's rear past
its last zone) and `delay` (clear_t − the free run's, the ego alone accelerating to the limit); per driver `level`,
`believed` (the ego's last believed level of it) and `converged` (ticks of its game until the ego's believed level is its
true one and stays: None when it never is), `identified` ("level" when converged; "behaviour" when the believed level
predicted the true level's move on every tick: behavioural equivalence; else None) and `same_move` (that share of ticks); `others_contacts` (two drivers in one zone at once: the world's, not the
family's); `collisions_partner` (contacts with a holder that moved after the ego committed past it under the waiver: the
holder's restart, attributed to it, never the ego's fail) and `collisions_own`. A card (road/catalog/ours/*.yaml, `map: {world: intersection}`) places the paths, the cars and the levels."""
import math
import sys
from pathlib import Path

ROAD = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROAD / "world"))
from road_world import DT, SENSOR_RANGE, Agent, Ego, RoadWorld  # noqa: E402
from semantic_world import levelk  # noqa: E402
from semantic_world.lane import Lane, LaneMap, Mover, Zone  # noqa: E402
from semantic_world.situation import Situation  # noqa: E402

CATALOG = ROAD / "catalog"
LANE_W = 3.5
HALF = 3.5                      # m: the box's half side (one lane each way)
ARM = 60.0                      # m: an approach's and an exit's length
SPEED = 11.1                    # m/s: every path's limit (40 km/h)
ZONE_GAP = 2.6                  # m: two centre lines this close are one conflict zone (two 1.8 m bodies and a margin)
STEP = 0.25                     # m: the centre lines' sampling
APPROACH = 40.0                 # m: a driver plays the game with a mover this close to their zone (road_facts' APPROACH)
STAND_V = 0.1                   # m/s: standing
DEADLOCK_S = 6.0
FOLLOW_T, FOLLOW_M = 1.5, 2.0   # s, m: a driver's time gap to the car ahead on its path, and the floor                # s: everyone short of the zones standing this long, the zones empty: a deadlock

# the inbound lane's entry at the box edge and its heading; the outbound lane's exit and heading (right-hand traffic)
ENTRY = {"S": ((0.5 * LANE_W, -HALF), (0.0, 1.0)), "N": ((-0.5 * LANE_W, HALF), (0.0, -1.0)),
         "E": ((HALF, 0.5 * LANE_W), (-1.0, 0.0)), "W": ((-HALF, -0.5 * LANE_W), (1.0, 0.0))}
EXIT = {"N": ((0.5 * LANE_W, HALF), (0.0, 1.0)), "S": ((-0.5 * LANE_W, -HALF), (0.0, -1.0)),
        "W": ((-HALF, 0.5 * LANE_W), (-1.0, 0.0)), "E": ((HALF, -0.5 * LANE_W), (1.0, 0.0))}


# ── the geometry ──
def _line(p, h, length):
    n = int(round(length / STEP))
    return [(p[0] + h[0] * STEP * i, p[1] + h[1] * STEP * i) for i in range(n + 1)]


def _bezier(p0, h0, p3, h3):
    d = math.hypot(p3[0] - p0[0], p3[1] - p0[1])
    k = 0.55 * d if abs(h0[0] * h3[1] - h0[1] * h3[0]) > 1e-9 else d / 3.0
    p1 = (p0[0] + h0[0] * k, p0[1] + h0[1] * k)
    p2 = (p3[0] - h3[0] * k, p3[1] - h3[1] * k)
    n = max(4, int(d / STEP * 1.6))
    out = []
    for i in range(n + 1):
        t = i / n
        u = 1 - t
        out.append((u ** 3 * p0[0] + 3 * u * u * t * p1[0] + 3 * u * t * t * p2[0] + t ** 3 * p3[0],
                    u ** 3 * p0[1] + 3 * u * u * t * p1[1] + 3 * u * t * t * p2[1] + t ** 3 * p3[1]))
    return out


class Path_:
    """A path NAME (FROM_TO): its centre line POINTS, their arc lengths S, the entry heading and its turn
    (straight | left | right)."""

    def __init__(self, name):
        frm, to = name.split("_")
        (pe, he), (px, hx) = ENTRY[frm], EXIT[to]
        start = (pe[0] - he[0] * ARM, pe[1] - he[1] * ARM)
        pts = _line(start, he, ARM)[:-1] + _bezier(pe, he, px, hx)[:-1] + _line(px, hx, ARM)
        self.name, self.points, self.heading = name, pts, he
        cross = he[0] * hx[1] - he[1] * hx[0]
        self.turn = "straight" if abs(cross) < 1e-9 else ("left" if cross > 0 else "right")
        self.s = [0.0]
        for a, b in zip(pts, pts[1:]):
            self.s.append(self.s[-1] + math.hypot(b[0] - a[0], b[1] - a[1]))
        self.length = self.s[-1]

    def xy(self, s):
        s = max(0.0, min(self.length, s))
        lo, hi = 0, len(self.s) - 1
        while hi - lo > 1:
            mid = (lo + hi) // 2
            if self.s[mid] <= s:
                lo = mid
            else:
                hi = mid
        a, b = self.points[lo], self.points[hi]
        f = 0.0 if self.s[hi] == self.s[lo] else (s - self.s[lo]) / (self.s[hi] - self.s[lo])
        return a[0] + f * (b[0] - a[0]), a[1] + f * (b[1] - a[1])


def conflict(p, q):
    """The s-intervals of P and Q where their centre lines come within ZONE_GAP: ((p_in, p_out), (q_in, q_out)), or None.
    Two paths from one arm (one approach lane) are not a crossing; the box's part only."""
    if p.name.split("_")[0] == q.name.split("_")[0]:
        return None
    sp, sq = [], []
    g2 = ZONE_GAP * ZONE_GAP
    for i, a in enumerate(p.points):
        if not (ARM - 1e-6 <= p.s[i] <= p.length - ARM + 1e-6):
            continue
        for j, b in enumerate(q.points):
            if not (ARM - 1e-6 <= q.s[j] <= q.length - ARM + 1e-6):
                continue
            if (a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2 <= g2:
                sp.append(p.s[i])
                sq.append(q.s[j])
    if not sp:
        return None
    return (min(sp), max(sp)), (min(sq), max(sq))


def priority(p, q):
    """The path with right of way between P and Q (no signs): straight over a left turn against it; else the one from
    the right (Q comes from P's right when its heading is P's turned a quarter counter-clockwise)."""
    hp, hq = p.heading, q.heading
    if abs(hp[0] + hq[0]) < 1e-9 and abs(hp[1] + hq[1]) < 1e-9:              # opposite approaches
        if p.turn == "left" and q.turn != "left":
            return q.name
        if q.turn == "left" and p.turn != "left":
            return p.name
        return None
    if abs(hq[0] + hp[1]) < 1e-9 and abs(hq[1] - hp[0]) < 1e-9:              # hq = rot90ccw(hp): Q from P's right
        return q.name
    return p.name


def layout(names):
    """The LaneMap of the paths NAMES: their lanes (with centre lines) and the zones between every two that conflict."""
    paths = {n: Path_(n) for n in names}
    lanes = [Lane(n, p.length, LANE_W, speed=SPEED, shape=p.points[::8] + [p.points[-1]], edge=n) for n, p in paths.items()]
    zones, ns = [], sorted(paths)
    for i, a in enumerate(ns):
        for b in ns[i + 1:]:
            c = conflict(paths[a], paths[b])
            if c:
                zones.append(Zone("z_%s_%s" % (a, b), {a: c[0], b: c[1]}, priority=priority(paths[a], paths[b])))
    return LaneMap(lanes, zones), paths


# ── the card ──
def card_path(name):
    hits = [p for p in CATALOG.glob("*/%s.yaml" % name)]
    if not hits:
        raise KeyError("no intersection card %r under %s" % (name, CATALOG))
    return hits[0]


def load(name):
    """'NAME[:LEVEL]' → the card (road/catalog/<source>/NAME.yaml with map.world intersection), LEVEL the others' level."""
    import yaml
    base, _, level = name.partition(":")
    card = yaml.safe_load(card_path(base).read_text())
    if (card.get("map") or {}).get("world") != "intersection":
        raise KeyError("%s is not an intersection card" % base)
    if level:
        card["variant"] = level
    return card


def levels_of(card):
    """The card's variants: params.level.variants (the others' level), else its value."""
    lv = (card.get("params") or {}).get("level") or {}
    return list(lv.get("variants") or [lv.get("value", "l1")])


# ── the world ──
class IntersectionWorld(RoadWorld):
    def __init__(self, card, seed=1, sensor_range=SENSOR_RANGE, level=None):
        if isinstance(card, str):
            card = load(card)
        level = level or card.get("variant") or (card.get("params") or {}).get("level", {}).get("value", "l1")
        import random
        self.card, self.level = card, level
        self.name = "ix:%s:%s" % (card["scenario"], level)
        self.seed, self.rng = seed, random.Random(seed)
        self.sensor_range = float(sensor_range)
        self.t, self.tick = 0.0, 0
        e = card["ego"]
        names = [e["path"]] + [a["path"] for a in card.get("actors") or []]
        self.map, self.paths = layout(names)
        jit = lambda x: float(x) + self.rng.uniform(-0.5, 0.5) * float((card.get("jitter") or {}).get("s", 0.0))
        self.ego = Ego(Mover("ego", e["path"], float(e["s"]), length=4.5, width=1.8), float(e["v"]))
        self.agents, self.level_of = [], {}
        for a in card.get("actors") or []:
            ag = Agent(Mover(a["id"], a["path"], jit(a["s"]), length=4.5, width=1.8), float(a["v"]), s0=float(a["s"]))
            ag.target = None
            self.agents.append(ag)
            self.level_of[a["id"]] = a.get("level") or level      # a driver's own level, else the variant's
        self.dest = self.map.lanes[e["path"]].length - 2.0
        self.s0 = self.ego.m.s
        self.sit = Situation()
        self.game = levelk.Game(dt=DT)
        self.collisions, self.violations, self.restricted, self.log = [], [], 0, []
        self.zone_turn = {z.id: None for z in self.map.zones}
        self.last_in = {}
        self.stand, self.deadlock_s, self.clear_t, self.others_contacts = 0.0, 0.0, None, 0
        self.believed_log = {}                           # driver id -> [the ego's believed level each tick it is in the game]
        self.same_log = {}                               # driver id -> [the believed level predicts the true level's move, per tick]
        self.committed_at, self.restarted = {}, set()   # the waiver (situation, WAIVER RULING 2): when the ego committed past a
                                                         # standing holder, and the holders that moved after it (their restart)
        self.ego_zones = [z for z in self.map.zones if self.ego.m.lane in z.lanes]
        self.ego_last = max((z.lanes[self.ego.m.lane][1] for z in self.ego_zones), default=0.0)
        self._dyn()

    # the sensor's world: positions on the paths' centre lines
    def xy_of(self, m):
        return self.paths[m.lane].xy(m.s)

    def seen(self):
        ex, ey = self.xy_of(self.ego.m)
        return [ag for ag in self.live() if math.hypot(self.xy_of(ag.m)[0] - ex, self.xy_of(ag.m)[1] - ey) <= self.sensor_range]

    def _arm(self, ag):
        return None

    # ── the level-k driver ──
    def _side(self, m, v, z):
        a, b = z.lanes[m.lane]
        d = m.dyn
        return levelk.Side(a - m.s, b - m.s + m.length, v, d.accel, d.brake_max, self.map.vcap(m.lane))

    def _speed(self, m):
        if m.id == "ego":
            return self.ego.v
        return next(ag.v for ag in self.agents if ag.m.id == m.id)

    def partner(self, ag):
        """The mover (the ego or another driver) of AG's most urgent zone: both short of its end, it within APPROACH of the
        zone's entry or in it; the most urgent = its earliest entry at its present speed. → (mover, zone) or None."""
        best = None
        me = ag.m
        for z in self.map.zones:
            if me.lane not in z.lanes:
                continue
            a, b = z.lanes[me.lane]
            if me.s - me.length > b or a - me.s > APPROACH:
                continue
            for m in [self.ego.m] + [o.m for o in self.live() if o is not ag]:
                if m.lane not in z.lanes or m.lane == me.lane:
                    continue
                oa, ob = z.lanes[m.lane]
                if m.s - m.length > ob or oa - m.s > APPROACH:
                    continue
                tta = max(0.0, oa - m.s) / max(self._speed(m), 0.5)
                if best is None or tta < best[0]:
                    best = (tta, m, z)
        return None if best is None else (best[1], best[2])

    def _script(self, ag):
        me = ag.m
        cap = self.map.vcap(me.lane)
        hit = self.partner(ag)
        if hit is None:
            a = me.dyn.accel if ag.v < cap else 0.0
        else:
            m, z = hit
            mine, theirs = self._side(me, ag.v, z), self._side(m, self._speed(m), z)
            t = levelk.tables(theirs, mine)                  # from the driver's seat: the partner is the game's "ego"
            ag.move = levelk.predicted(t, self.level_of[me.id])
            a = levelk.accel_of(mine, ag.move)
        a = min(a, self._follow(ag))
        v = max(0.0, min(cap, ag.v + a * DT))
        me.s += 0.5 * (ag.v + v) * DT
        ag.v, ag.a = v, (v - ag.v) / DT
        if me.s - me.length > self.map.lanes[me.lane].length:
            ag.done = True

    def _follow(self, ag):
        """The car ahead on AG's path (the ego or a driver): no closer than a FOLLOW_T time gap + FOLLOW_M; the braking that
        keeps it (at most its hardest), else no bound."""
        me, lead = ag.m, None
        for m in [self.ego.m] + [o.m for o in self.live() if o is not ag]:
            if m.lane == me.lane and m.s > me.s and (lead is None or m.s < lead.s):
                lead = m
        if lead is None:
            return math.inf
        gap = lead.s - lead.length - me.s
        want = ag.v * FOLLOW_T + FOLLOW_M
        if gap >= want:
            return math.inf
        dv = ag.v - self._speed(lead)
        return -min(me.dyn.brake_max or 8.0, max(0.5, dv * dv / (2.0 * max(0.5, gap - FOLLOW_M)) + (want - gap)))

    # ── the measures ──
    def step(self):
        n = len(self.collisions)
        super().step()
        for pid in self.sit.committed:                   # the ego committed past a standing holder (it gave the way)
            self.committed_at.setdefault(pid.split(":")[0], self.t)
        for ag in self.agents:
            if ag.m.id in self.committed_at and ag.v > STAND_V:
                self.restarted.add(ag.m.id)              # it moved after the ego committed: the holder's restart after waiver
        for c in self.collisions[n:]:
            if c["with"] in self.restarted:
                c["by"] = "partner: the holder's restart after its waiver"
        e = self.ego.m
        if self.clear_t is None and self.ego_zones and e.s - e.length > self.ego_last:
            self.clear_t = round(self.t, 2)
        inside = {z.id: [m for m in self._all() if self._in(z, m)] for z in self.map.zones}
        for z in self.map.zones:
            if len([m for m in inside[z.id] if m.id != "ego"]) >= 2:
                self.others_contacts += 1
        short = [m for m in self._all() if self._short(m)]
        still = all(self._speed(m) <= STAND_V for m in short)
        empty = not any(inside.values())
        self.stand = self.stand + DT if (len(short) >= 2 and still and empty) else 0.0
        self.deadlock_s = max(self.deadlock_s, round(self.stand, 2))
        for key, b in self.game.belief.items():
            oid = key.split(":")[0]
            if oid in self.level_of:
                k = levelk.believed(b)
                t = self.game.tables.get(key)
                same = t is not None and levelk.predicted(t, k) == levelk.predicted(t, self.level_of[oid])
                self.believed_log.setdefault(oid, []).append(k)
                self.same_log.setdefault(oid, []).append(same)

    def _in(self, z, m):
        if m.lane not in z.lanes:
            return False
        a, b = z.lanes[m.lane]
        return m.s >= a and m.s - m.length <= b

    def _short(self, m):
        """M is still short of a zone of its path, within APPROACH of it."""
        for z in self.map.zones:
            if m.lane in z.lanes:
                a, _ = z.lanes[m.lane]
                if 0.0 < a - m.s <= APPROACH:
                    return True
        return False

    def free_clear_t(self):
        """The ego alone: from its start, accelerating at its class's rate to the limit, its rear past its last zone."""
        if not self.ego_zones:
            return None
        s, v, t = self.s0, float(self.card["ego"]["v"]), 0.0
        cap, acc = self.map.vcap(self.ego.m.lane), self.ego.m.dyn.accel
        while s - self.ego.m.length <= self.ego_last and t < 120.0:
            v2 = min(cap, v + acc * DT)
            s += 0.5 * (v + v2) * DT
            v, t = v2, t + DT
        return round(t, 2)

    def converged(self, oid):
        """Ticks of OID's game until the ego's believed level is its true one and stays so; None when it never is."""
        log = self.believed_log.get(oid) or []
        true = self.level_of[oid]
        for k in range(len(log)):
            if all(x == true for x in log[k:]):
                return k
        return None

    def identified(self, oid):
        """How the ego identified OID (the architect's step 4 ruling, (3)): "level" when its believed level is the true one
        and stays (converged), "behaviour" when the believed level predicted the true level's move on every tick of the game
        (an l2 that moves as l1 in every state of the card: the likelihoods tie, the decision is the same), else None."""
        if self.converged(oid) is not None:
            return "level"
        same = self.same_log.get(oid) or []
        return "behaviour" if same and all(same) else None

    def summary(self):
        s = super().summary()
        free = self.free_clear_t()
        s.update({"scenario": self.name, "level": self.level, "deadlock_s": self.deadlock_s,
                  "deadlock": self.deadlock_s >= DEADLOCK_S, "clear_t": self.clear_t,
                  "delay": None if self.clear_t is None or free is None else round(self.clear_t - free, 2),
                  "others_contacts": self.others_contacts,
                  "collisions_partner": sum(1 for c in self.collisions if c.get("by")),
                  "collisions_own": sum(1 for c in self.collisions if not c.get("by")),
                  "drivers": {oid: {"level": lv, "believed": (self.believed_log.get(oid) or [None])[-1],
                                    "game_ticks": len(self.believed_log.get(oid) or []), "converged": self.converged(oid),
                                    "identified": self.identified(oid),
                                    "same_move": (round(sum(self.same_log[oid]) / len(self.same_log[oid]), 3)
                                                  if self.same_log.get(oid) else None)}
                              for oid, lv in self.level_of.items()}})
        return s


def check(card, summary):
    """The card's expect against one run's summary: [failure, …]."""
    exp = card.get("expect") or {}
    out = []
    own = summary.get("collisions_own", summary.get("collisions", 0))    # a contact the partner's restart after its waiver made
    if "collisions" in exp and own > exp["collisions"]:                  # is the partner's: kept in the row, not the ego's fail
        out.append("collisions %s > %s" % (own, exp["collisions"]))
    if "violations" in exp and summary.get("violations", 0) > exp["violations"]:
        out.append("violations %s > %s" % (summary.get("violations"), exp["violations"]))
    if exp.get("arrived") and not summary.get("arrived"):
        out.append("not arrived")
    if exp.get("deadlock") is False and summary.get("deadlock"):
        out.append("deadlock %.1f s" % summary.get("deadlock_s", 0.0))
    if "delay_s" in exp and summary.get("delay") is not None and summary["delay"] > exp["delay_s"]:
        out.append("delay %.1f s > %s" % (summary["delay"], exp["delay_s"]))
    return out
