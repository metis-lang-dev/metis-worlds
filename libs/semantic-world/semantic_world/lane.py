"""lane — the `lane` adapter's skeleton (semantic-world step 3a): a road as RSS's world model sees it, enough to
build the situation layer's pairs; no road runtime, no simulator, and the parked road catalog untouched.

- The lane graph: lanes with a length and a direction of travel, their successors, their left and right
  neighbours (with the neighbour's direction: same or opposite).
- A position is (lane, s): the lane and the distance along it (Frenet's s, metres); a mover has a position, a
  speed range and its `Dynamics`.
- The ego's route: a sequence of lanes; `ahead(route, s0, pos)` the distance along the route to a position on it.
- Conflict zones: where two routes' lanes cross (an intersection's overlap area), with the priority between them,
  each lane's s where the zone begins and ends.
- `pairs(ego, objects)`: one situation.Pair per relevant object — on the ego's lane ahead or behind (same_dir),
  on an opposite-direction neighbour lane (opp_dir; the ego in its correct lane), crossing the ego's route at a
  conflict zone (xing_ego_prio / xing_obj_prio / xing_same_prio, with the distances to enter and to leave), else
  not_relevant. The lateral gap is the lanes' centre offset less the cars' half-widths (overlap within one lane).

The roles a road program reads (design §2: ego, lead, leadleft, leadright, follower, a1..ak, nextzone) are bound by
the projection the road subject will write; here only `role_of` in pairs."""
from dataclasses import dataclass, field

from .situation import Dynamics, Pair


@dataclass
class Lane:
    id: str
    length: float
    width: float = 3.5
    succ: list = field(default_factory=list)
    left: str = None                    # the neighbour lane on the left, and whether it runs the other way
    left_opposite: bool = False
    right: str = None
    right_opposite: bool = False


@dataclass
class Mover:
    id: str
    lane: str
    s: float
    dyn: Dynamics = field(default_factory=Dynamics)
    route: list = None                  # the lanes it will take (its prediction; the ego's plan)
    length: float = 4.5
    width: float = 1.8


@dataclass
class Zone:
    """A conflict zone: LANES {lane: (s_enter, s_leave)}, PRIORITY the lane with right of way (None: the same)."""
    id: str
    lanes: dict
    priority: str = None


class LaneMap:
    def __init__(self, lanes, zones=()):
        self.lanes = {l.id: l for l in lanes}
        self.zones = list(zones)

    def ahead(self, route, s0, lane, s):
        """The distance along ROUTE from (route[0], s0) to (LANE, S); None if LANE is not on it."""
        d = -s0
        for lid in route:
            if lid == lane:
                return d + s
            d += self.lanes[lid].length
        return None

    def lateral(self, a, b):
        """(position, offset) of lane B relative to lane A: at_left / at_right of a neighbour with the distance
        between the lanes' centres, overlap on the same lane (0), None when not neighbours."""
        la = self.lanes[a]
        if a == b:
            return "overlap", 0.0
        off = 0.5 * (la.width + self.lanes[b].width)
        if la.left == b:
            return "at_left", off
        if la.right == b:
            return "at_right", off
        return None, None

    def zone_on(self, route, lane):
        """The first conflict zone the ROUTE and LANE share: (zone, the route lane in it)."""
        for z in self.zones:
            for rl in route:
                if rl in z.lanes and lane in z.lanes and rl != lane:
                    return z, rl
        return None, None

    def pairs(self, ego, objects, role_of=None):
        """→ [situation.Pair] of EGO (a Mover with its route) and every object."""
        role_of = role_of or (lambda o: None)
        route = ego.route or [ego.lane]
        out = []
        for o in objects:
            d = self.ahead(route, ego.s, o.lane, o.s)
            lat, gap = self.lateral(ego.lane, o.lane)
            if d is not None and lat == "overlap":                                        # on the ego's way
                if d >= 0:
                    lon, d_lon = "in_front", max(0.0, d - o.length)
                else:
                    lon, d_lon = "at_back", max(0.0, -d - ego.length)
                out.append(Pair("%s:same_dir" % o.id, "same_dir", lon, "overlap", d_lon, 0.0, ego.dyn, o.dyn, role=role_of(o)))
                continue
            la = self.lanes[ego.lane]
            if lat in ("at_left", "at_right"):
                opposite = la.left_opposite if lat == "at_left" else la.right_opposite
                kind = "opp_dir" if opposite else "same_dir"
                lb = self.lanes[o.lane]
                rel = ((lb.length - o.s) if opposite else o.s) - ego.s                         # opposite: its s runs the other way
                d_lon = max(0.0, abs(rel) - o.length)
                lon = "in_front" if rel >= 0 else "at_back"
                d_lat = max(0.0, gap - 0.5 * (ego.width + o.width))                             # between the cars' sides
                out.append(Pair("%s:%s" % (o.id, kind), kind, lon, lat, d_lon, d_lat, ego.dyn, o.dyn, role=role_of(o)))
                continue
            z, rl = self.zone_on(route, o.lane)
            if z is not None:
                kind = "xing_same_prio" if z.priority is None else ("xing_ego_prio" if z.priority == rl else "xing_obj_prio")
                e_in, e_out = z.lanes[rl]
                o_in, o_out = z.lanes[o.lane]
                base = self.ahead(route, ego.s, rl, 0.0)
                out.append(Pair("%s:%s:%s" % (o.id, kind, z.id), kind, "in_front", "overlap", 0.0, 0.0, ego.dyn, o.dyn,
                                d_enter=max(0.0, base + e_in), d_leave=max(0.0, base + e_out),
                                o_enter=max(0.0, o_in - o.s), o_leave=max(0.0, o_out - o.s), role=role_of(o)))
                continue
            out.append(Pair("%s:not_relevant" % o.id, "not_relevant", role=role_of(o), ego=ego.dyn, obj=o.dyn))
        return out
