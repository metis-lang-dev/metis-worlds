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
`roles` (road-world step 2, opus's spec), so that every host projects alike; `pairs` takes the caller's `role_of`.

Road-world step 3 (s-e812715d) adds, keeping every name above: a lane's speed limit, shape, edge and index, the
junction of an internal lane and the vClasses allowed (filled by net.load_net from a SUMO net); a zone's junction and
links, so a traffic light's phase decides its priority (`priority`); the nearest zone along a route
(`nearest_zone`); a route through the internal lanes (`route_through`); objects' predicted routes in `pairs` (its
route if given, else every way out of its lane), a lead on a later lane of the ego's route followed (same_dir), and
the nearest shared zone, the object's ways merged worst-case (the least enter, the most leave); and the per-vClass
Dynamics table with the lane's vcap (`dynamics_for`)."""
import math
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
    speed: float = None                 # the speed limit (m/s)
    shape: list = None                  # the centre line [(x, y)]
    internal: bool = False              # a junction's internal lane
    junction: str = None                # the junction an internal lane belongs to
    edge: str = None
    index: int = 0                      # the lane index on its edge (0: the rightmost)
    allow: tuple = None                 # the vClasses allowed (None: all), and disallowed
    disallow: tuple = None


@dataclass
class Mover:
    id: str
    lane: str
    s: float
    dyn: Dynamics = field(default_factory=Dynamics)
    route: list = None                  # the lanes it will take (its prediction; the ego's plan)
    length: float = 4.5
    width: float = 1.8
    vclass: str = "passenger"


@dataclass
class Zone:
    """A conflict zone: LANES {lane: (s_enter, s_leave)}, PRIORITY the lane with right of way (None: the same).
    From a net: the JUNCTION, and each lane's link index there (LINK_OF), so a light's phase can decide."""
    id: str
    lanes: dict
    priority: str = None
    junction: str = None
    link_of: dict = None


# A traffic light's link state, by how much right of way it gives (SUMO: G priority green, g green that yields,
# y/Y amber, r/u red, o/O off, s stop). The higher one at a zone has priority; equal: the junction's own rows.
LIGHT_RANK = {"G": 4, "g": 3, "y": 2, "Y": 2, "u": 1, "r": 1, "s": 1, "o": 0, "O": 0}

# The per-vClass RSS dynamics (road-world step 3d). Parameters, not facts: RSS leaves them to regulation (Remark 2);
# these follow the ad-rss / CARLA practice (an ego's response time 1 s, another vehicle's 2 s, a pedestrian's 0.5 s;
# braking bounds brake_min_correct < brake_min < brake_max) with SUMO's class top speeds as the cap where no lane
# limit applies. A host may replace any entry.
VCLASS = {
    "passenger":  dict(accel=3.5, brake_min=4.0, brake_max=8.0, brake_min_correct=3.0, rho=2.0, min_dist=1.0,
                       lat_accel=0.2, lat_brake=0.8, mu=0.1, top=55.56),
    "truck":      dict(accel=2.0, brake_min=3.0, brake_max=6.0, brake_min_correct=2.5, rho=2.0, min_dist=1.0,
                       lat_accel=0.2, lat_brake=0.8, mu=0.1, top=36.11),
    "bicycle":    dict(accel=2.0, brake_min=2.5, brake_max=5.0, brake_min_correct=2.0, rho=1.0, min_dist=0.5,
                       lat_accel=0.5, lat_brake=1.0, mu=0.2, top=5.56),
    "pedestrian": dict(accel=2.0, brake_min=2.0, brake_max=4.0, brake_min_correct=2.0, rho=0.5, min_dist=0.5,
                       lat_accel=2.0, lat_brake=2.0, mu=0.2, top=1.39),
}
VCLASS_ALIAS = {"private": "passenger", "taxi": "passenger", "evehicle": "passenger", "emergency": "passenger",
                "delivery": "truck", "bus": "truck", "coach": "truck", "trailer": "truck", "moped": "bicycle"}
EGO_RHO = 1.0

# The roles `LaneMap.roles` binds, in the order a mover takes the first that fits (then a1..ak, vru1..vruj).
NEAR_ROLES = ("lead", "follower", "leadleft", "followleft", "leadright", "followright")
VRU = ("pedestrian", "bicycle")


def dynamics_for(vclass, v=None, vmin=None, vmax=None, lane=None, ego=False, vcap_factor=1.0):
    """A mover's Dynamics: its class's bounds (VCLASS; an unknown class: passenger), the speed range [vmin, vmax]
    (or v for both), the ego's response time EGO_RHO, and the vcap: the LANE's speed limit × VCAP_FACTOR (ad-rss's
    speed-limit modes 1, 1.05, 1.1), never above the class's top speed."""
    p = dict(VCLASS.get(VCLASS_ALIAS.get(vclass, vclass), VCLASS["passenger"]))
    top = p.pop("top")
    if ego:
        p["rho"] = EGO_RHO
    lo = vmin if vmin is not None else (v if v is not None else 0.0)
    hi = vmax if vmax is not None else (v if v is not None else 0.0)
    cap = top if lane is None or lane.speed is None else min(top, lane.speed * vcap_factor)
    return Dynamics(vmin=lo, vmax=hi, vcap=cap, **p)


class LaneMap:
    def __init__(self, lanes, zones=(), net=None):
        self.lanes = {l.id: l for l in lanes}
        self.zones = list(zones)
        self.net = net

    def vcap(self, lane, vclass="passenger", factor=1.0):
        """The lane's speed limit × FACTOR for VCLASS (its top speed where the lane sets none)."""
        top = VCLASS.get(VCLASS_ALIAS.get(vclass, vclass), VCLASS["passenger"])["top"]
        sp = self.lanes[lane].speed
        return top if sp is None else min(top, sp * factor)

    def route_through(self, lanes):
        """A route of LANES with the internal lanes between them filled in (each next lane reached through the
        successors: an internal chain from a junction's connection)."""
        out = [lanes[0]]
        for nxt in lanes[1:]:
            path = self._path(out[-1], nxt)
            if path is None:
                raise ValueError("no connection from %s to %s" % (out[-1], nxt))
            out += path
        return out

    def _path(self, a, b, depth=4):
        if b in self.lanes[a].succ:
            return [b]
        if depth == 0:
            return None
        for s in self.lanes[a].succ:
            if self.lanes[s].internal:
                p = self._path(s, b, depth - 1)
                if p is not None:
                    return [s] + p
        return None

    def ways(self, lane, depth=3):
        """Every way out of LANE through its next junction: [lane, internal…, the outgoing lane] (just [lane] when it
        has no successor)."""
        out = []

        def walk(path, d):
            succ = self.lanes[path[-1]].succ
            if not succ or d == 0:
                out.append(path)
                return
            for s in succ:
                if self.lanes[s].internal:
                    walk(path + [s], d - 1)
                else:
                    out.append(path + [s])
        walk([lane], depth)
        return out

    def priority(self, zone, lights=None):
        """The lane with right of way at ZONE: under a traffic light whose phase states LIGHTS {tl id: state} give
        one side more right of way (LIGHT_RANK), that side; else the zone's own (the junction's response rows)."""
        if not lights or not zone.link_of or self.net is None:
            return zone.priority
        ranks = {}
        for lane, link in zone.link_of.items():
            j = self.net.junctions.get(zone.junction)
            cn = j.links[link] if j and link < len(j.links) else None
            if cn is None or cn.tl is None or cn.tl not in lights:
                return zone.priority
            st = lights[cn.tl]
            ranks[lane] = LIGHT_RANK.get(st[cn.tl_link], 0) if cn.tl_link is not None and cn.tl_link < len(st) else 0
        (la, ra), (lb, rb) = sorted(ranks.items())
        if ra == rb:
            return zone.priority
        return la if ra > rb else lb

    def crossing(self, route, s0, ways, o_s, lights=None, ego_len=0.0, o_len=0.0):
        """The object's crossing of ROUTE (from s0): every zone a route lane shares with a lane of one of the object's
        WAYS (from o_s on their first lane), not yet left by either, grouped by junction (a zone without one: by
        itself); the nearest group along the route, MERGED worst-case as ad-rss merges one object's constellations at
        one intersection: the ego's least enter and most leave, the object's likewise, and the least priority for the
        ego (the object's anywhere → xing_obj_prio; else the same anywhere → xing_same_prio). A position is a mover's
        front: each side leaves a zone when its rear does, its EGO_LEN / O_LEN past s_leave. → (key, type, d_enter,
        d_leave, o_enter, o_leave), or None."""
        groups = {}
        for z in self.zones:
            for rl in route:
                if rl not in z.lanes:
                    continue
                e_in, e_out = z.lanes[rl]
                d_in, d_out = self.ahead(route, s0, rl, e_in), self.ahead(route, s0, rl, e_out)
                if d_out is None or d_out + ego_len < 0:
                    continue
                d_out += ego_len
                for w in ways:
                    for ol in w:
                        if ol == rl or ol not in z.lanes:
                            continue
                        a, b = z.lanes[ol]
                        oa, ob = self.ahead(w, o_s, ol, a), self.ahead(w, o_s, ol, b)
                        if ob is None or ob + o_len < 0:
                            continue
                        ob += o_len
                        prio = self.priority(z, lights)
                        kind = "xing_same_prio" if prio is None else ("xing_ego_prio" if prio == rl else "xing_obj_prio")
                        g = groups.setdefault(z.junction or z.id, [None, None, None, None, set()])
                        g[0] = d_in if g[0] is None else min(g[0], d_in)
                        g[1] = d_out if g[1] is None else max(g[1], d_out)
                        g[2] = oa if g[2] is None else min(g[2], oa)
                        g[3] = ob if g[3] is None else max(g[3], ob)
                        g[4].add(kind)
        if not groups:
            return None
        key, (d_in, d_out, o_in, o_out, kinds) = min(groups.items(), key=lambda kv: (kv[1][0], kv[0]))
        kind = "xing_obj_prio" if "xing_obj_prio" in kinds else "xing_same_prio" if "xing_same_prio" in kinds \
            else "xing_ego_prio"
        return key, kind, d_in, d_out, o_in, o_out

    def nearest_zone(self, route, s0, lane=None, ways=None, length=0.0):
        """The zone along ROUTE (from s0 on route[0]) nearest ahead and not yet left (by the rear of a mover of LENGTH
        whose front is at s0): → (zone, the route lane in it, d_enter, d_leave), or None. LANE / WAYS: only zones an
        object on LANE (or on one of WAYS) shares."""
        other = set(l for w in (ways or ([[lane]] if lane else [])) for l in w)
        best = None
        for z in self.zones:
            for rl in route:
                if rl not in z.lanes or (other and not (set(z.lanes) - {rl}) & other):
                    continue
                e_in, e_out = z.lanes[rl]
                d_in, d_out = self.ahead(route, s0, rl, e_in), self.ahead(route, s0, rl, e_out)
                if d_out is None or d_out + length < 0:
                    continue
                if best is None or d_in < best[2]:
                    best = (z, rl, d_in, d_out)
        return best

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

    def pairs(self, ego, objects, role_of=None, lights=None):
        """→ [situation.Pair] of EGO (a Mover with its route) and every object. LIGHTS {tl id: phase state}: the
        traffic lights' current states, for a zone's priority."""
        role_of = role_of or (lambda o: None)
        route = ego.route or [ego.lane]
        out = []
        for o in objects:
            d = self.ahead(route, ego.s, o.lane, o.s)
            lat, gap = self.lateral(ego.lane, o.lane)
            if d is not None and lat is None and d >= 0:                                   # on a later lane of the way
                lat = "overlap"
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
            ways = [o.route] if o.route else self.ways(o.lane)
            hit = self.crossing(route, ego.s, ways, o.s, lights, ego.length, o.length)
            if hit is not None:
                key, kind, d_in, d_out, o_in, o_out = hit
                out.append(Pair("%s:%s:%s" % (o.id, kind, key), kind, "in_front", "overlap", 0.0, 0.0, ego.dyn, o.dyn,
                                d_enter=max(0.0, d_in), d_leave=max(0.0, d_out),
                                o_enter=max(0.0, o_in), o_leave=max(0.0, o_out), role=role_of(o)))
                continue
            out.append(Pair("%s:not_relevant" % o.id, "not_relevant", role=role_of(o), ego=ego.dyn, obj=o.dyn))
        return out

    def roles(self, ego, movers, k=3, j=1, lights=None):
        """The road roles of MOVERS around EGO → {role: mover id}, a role nobody fills left out. In NEAR_ROLES order,
        then a1..aK, then vru1..vruJ, a mover taking the first role that fits and no mover two; ties by mover id.
        - lead: the nearest ahead (`ahead` ≥ 0) on the ego's way, its lane or a later lane of its route; follower:
          the nearest behind on the ego's lane.
        - leadleft / followleft: the nearest ahead / behind (by s relative to the ego's) on the ego lane's left
          neighbour, a same-direction one only; leadright / followright likewise on the right.
        - a1..aK: the remaining vehicles whose pair (`pairs`, under LIGHTS) is not not_relevant, nearest first by d_lon,
          at a crossing by d_enter (the ego's: equal for one junction's objects, so then by their own o_enter);
          vru1..vruJ: the remaining movers of a VRU vClass, by the same rule."""
        route = ego.route or [ego.lane]
        la = self.lanes[ego.lane]
        sides = (("left", None if la.left_opposite else la.left), ("right", None if la.right_opposite else la.right))
        cand = {r: [] for r in NEAR_ROLES}
        movers = [o for o in movers if o.id != ego.id]
        for o in movers:
            d = self.ahead(route, ego.s, o.lane, o.s)
            if d is not None and d >= 0:
                cand["lead"].append((d, o.id))
            if o.lane == ego.lane and o.s < ego.s:
                cand["follower"].append((ego.s - o.s, o.id))
            for side, nb in sides:
                if nb is not None and o.lane == nb:
                    rel = o.s - ego.s
                    cand[("lead" if rel >= 0 else "follow") + side].append((abs(rel), o.id))
        out, taken = {}, set()

        def take(role, ranked):
            for _, oid in sorted(ranked):
                if oid not in taken:
                    out[role] = oid
                    taken.add(oid)
                    return
        for r in NEAR_ROLES:
            take(r, cand[r])
        rest = [o for o in movers if o.id not in taken]
        near = {False: [], True: []}
        for o, p in zip(rest, self.pairs(ego, rest, lights=lights)):
            if p.type != "not_relevant":
                x = p.type.startswith("xing")
                near[o.vclass in VRU].append((p.d_enter if x else p.d_lon, p.o_enter if x else 0.0, o.id))
        for prefix, n, ranked in (("a", k, near[False]), ("vru", j, near[True])):
            for i, (_, _, oid) in enumerate(sorted(ranked)[:n]):
                out["%s%d" % (prefix, i + 1)] = oid
        return out

    def zone_roles(self, ego, movers, roles):
        """{"nextzone": the id of the zone nearest ahead on EGO's route and not yet left (`nearest_zone`) or None,
        "holder": the role (in ROLES {role: mover id}, in its order) of a mover inside it, any part of the mover
        between s_enter and s_leave on a zone lane, or None}."""
        hit = self.nearest_zone(ego.route or [ego.lane], ego.s, length=ego.length)
        if hit is None:
            return {"nextzone": None, "holder": None}
        z = hit[0]
        by_id = {o.id: o for o in movers}
        for role, oid in roles.items():
            o = by_id.get(oid)
            if o is not None and o.lane in z.lanes:
                a, b = z.lanes[o.lane]
                if o.s >= a and o.s - o.length <= b:
                    return {"nextzone": z.id, "holder": role}
        return {"nextzone": z.id, "holder": None}
