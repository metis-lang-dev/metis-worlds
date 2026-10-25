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


def stated(v, accel, rho, brake):
    """The distance covered in the response time at ACCEL, then braking at BRAKE to a stop (RSS's stated braking
    distance); BRAKE None: it stops at will after the response time."""
    v1 = v + accel * rho
    d = v * rho + 0.5 * accel * rho * rho
    return d + (v1 * v1 / (2 * brake) if brake else 0.0)


def stop(v, brake):
    """A leader's stopping distance braking at BRAKE (None: at once)."""
    return v * v / (2 * brake) if brake else 0.0


def safe_same_dir(follower, leader):
    """Lemma 2 with speed ranges and a floor: the follower's stated braking from its top speed less the leader's
    stop from its least, never below zero, plus the follower's floor."""
    return max(stated(follower.vmax, follower.accel, follower.rho, follower.brake_min) - stop(leader.vmin, leader.brake_max), 0.0) \
        + follower.min_dist


def safe_opp_dir(correct, opposite):
    """Lemma 3: both stated braking distances, the one in its correct lane at its own (gentler) bound, plus the
    larger floor."""
    return stated(correct.vmax, correct.accel, correct.rho, correct.brake_min_correct or correct.brake_min) \
        + stated(opposite.vmax, opposite.accel, opposite.rho, opposite.brake_min) + max(correct.min_dist, opposite.min_dist)


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
    t = (-v + math.sqrt(v * v + 2 * accel * d)) / accel
    if vcap is not None and v + accel * t > vcap:
        tc = (vcap - v) / accel
        dc = v * tc + 0.5 * accel * tc * tc
        return tc + (d - dc) / vcap if vcap > 0 else None
    return t


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
    if p.type == "not_relevant":
        return True
    if not p.lateral_room or p.type.startswith("xing") or p.lat == "overlap":
        return False
    return p.d_lat > safe_lat_dist(p.obj if p.lat in ("at_left", "overlap_left") else p.ego,
                                   p.ego if p.lat in ("at_left", "overlap_left") else p.obj)


def check_xing(p):
    """Def 17's cascade at a conflict zone: the one without priority able to stop before it; else the same-direction
    distance; else no time overlap (one leaves before the other can arrive). → (safe, d_safe)."""
    ego_stop = stated(p.ego.vmax, p.ego.accel, p.ego.rho, p.ego.brake_min) + p.ego.min_dist
    obj_stop = stated(p.obj.vmax, p.obj.accel, p.obj.rho, p.obj.brake_min) + p.obj.min_dist
    if p.type in ("xing_obj_prio", "xing_same_prio") and p.d_enter is not None and ego_stop < p.d_enter:
        return True, ego_stop
    if p.type in ("xing_ego_prio", "xing_same_prio") and p.o_enter is not None and obj_stop < p.o_enter:
        return True, obj_stop
    if no_time_overlap(p):
        return True, 0.0
    return False, ego_stop


def no_time_overlap(p):
    """The ego's earliest arrival after the object's latest leave, or the other way round, or neither ever arrives."""
    if None in (p.d_enter, p.d_leave, p.o_enter, p.o_leave):
        return False
    e_in, o_in = time_to(p.d_enter, p.ego.vmax, p.ego.accel), time_to(p.o_enter, p.obj.vmax, p.obj.accel)
    e_out = time_to(p.d_leave, p.ego.vmin, 0.0) if p.ego.vmin > 0 else None
    o_out = time_to(p.o_leave, p.obj.vmin, 0.0) if p.obj.vmin > 0 else None
    if e_in is None or o_in is None:
        return True
    return (o_out is not None and e_in > o_out) or (e_out is not None and o_in > e_out)


def able_to_stop(dyn, d_enter):
    """X able to stop before a zone D_ENTER away (its stated braking plus its floor)."""
    return stated(dyn.vmax, dyn.accel, dyn.rho, dyn.brake_min) + dyn.min_dist < d_enter


class Situation:
    """The per-pair memory across cycles and the fold. One per ego; `check(pairs)` every cycle, in order."""

    def __init__(self, memory=None):
        self.memory = dict(memory or {})          # pair id -> (long safe, lat safe) at its last safe cycle

    def check(self, pairs):
        """→ [State] for PAIRS (the memory updated: rewritten while safe, frozen while dangerous, dropped for pairs
        no longer present)."""
        out, seen = [], set()
        for p in pairs:
            seen.add(p.id)
            lon, ds = check_long(p)
            lat = check_lat(p)
            dangerous = not lon and not lat
            before = self.memory.get(p.id)
            if not dangerous:
                self.memory[p.id] = (lon, lat)
            out.append(State(p.id, p.type, p.role, lon, lat, dangerous, before if dangerous else (lon, lat),
                             *respond(p, dangerous, before), round(p.d_lon, 6), round(ds, 6)))
        for k in [k for k in self.memory if k not in seen]:
            self.memory.pop(k)
        return out

    @staticmethod
    def fold(states, ego):
        """The proper response over all pairs (§D): responses by enum max; the ego's longitudinal acceleration range
        [brake_max, accel] narrowed by each response (BrakeMin: at most −brake_min; BrakeMinCorrect: at most
        −brake_min_correct), lateral likewise. → {"resp_lon", "resp_lat", "lon_range", "lat_max", "dangerous":
        [roles or ids]}."""
        r_lon, r_lat = "none", "none"
        lo = -(ego.brake_max if ego.brake_max else float("inf"))
        hi = ego.accel
        lat_hi = ego.lat_accel
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
        return {"resp_lon": r_lon, "resp_lat": r_lat, "lon_range": [lo, hi], "lat_max": lat_hi, "dangerous": bad}

    @staticmethod
    def facts(states, folded=None):
        """The program's atoms over the bound roles (a pair whose object has no role is not said): the type, the
        booleans, the memory, the pair's response, and the folded response once (resp_lon(R), resp_lat(R))."""
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
        if folded is not None:
            out["resp_lon(%s)" % folded["resp_lon"]] = 1
            out["resp_lat(%s)" % folded["resp_lat"]] = 1
        return out


def respond(p, dangerous, before):
    """The pair's responses (§B, the lib's realization of Def 10/18). → (resp_lon, resp_lat)."""
    if not dangerous or p.type == "not_relevant":
        return "none", "none"
    if p.type.startswith("xing"):
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
