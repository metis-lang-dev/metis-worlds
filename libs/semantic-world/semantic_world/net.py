"""net — a SUMO `.net.xml` as the lane adapter's map (road-world s-e812715d step 3b, 3c): the lanes, the connections
and the internal lanes, the junctions with their link rows (foes, response), the traffic-light programs, and the
CONFLICT ZONES the junctions' internal lanes make where they overlap.

- `load_net(path, walking=False)` → Net: `lanes` {id: lane.Lane} (normal and internal, with length, speed, width, shape, the edge
  and index, the junction of an internal lane, the vClasses allowed), `connections` [Connection], `junctions`
  {id: Junction}, `tls` {id: Tls}.
- A junction's LINK index: its incoming lanes in `incLanes` order, each lane's connections in file order (SUMO's
  own order: the `request` rows are indexed by it, and a `foes` / `response` bit j, counted from the right, is link
  j). A traffic light's connection carries its own `linkIndex` into the phase states.
- A link's internal CHAIN: its `via` lane, then the vias of the connections out of that internal lane (a left turn
  waits at an internal junction: `:C_6_0` then `:C_14_0`), up to the outgoing lane.
- `Net.zones()`: for every pair of foe links, the stretch where their chains' lane bodies overlap (the centre lines
  closer than the half widths, sampled every `step` m), as one lane.Zone with each side's (s_enter, s_leave) on the
  chain lane the overlap begins on (s along the chain from that lane's start; it may run on into the next part).
  The static priority is the response row's: the link that need not yield to the other; none when both or neither
  yield (lane.Zone.priority None: xing_same_prio).
- `Net.lanemap()` → lane.LaneMap over the lanes, the zones and the net (successors through the internal lanes,
  same-direction neighbours by lane index, the leftmost lane's opposite neighbour on the reverse edge)."""
import math
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field

from .lane import Lane, LaneMap, Zone

DEFAULT_WIDTH = 3.2          # SUMO's default lane width
DEFAULT_SPEED = 13.89        # SUMO's default edge speed (50 km/h)


@dataclass
class Connection:
    from_lane: str
    to_lane: str
    via: str = None              # the first internal lane (None: no internal lane)
    dir: str = ""                # s straight, l left, r right, t turn, L/R partially
    state: str = ""              # M major, m minor, = equal, s stop, w all-way stop, o / O off; a light's: its index
    junction: str = None
    link: int = None             # the junction's link index
    tl: str = None               # the traffic light controlling it, and its index into the phase states
    tl_link: int = None
    chain: list = field(default_factory=list)    # the internal lanes from `via` to the outgoing lane


@dataclass
class Junction:
    id: str
    type: str
    inc_lanes: list
    int_lanes: list
    requests: dict = field(default_factory=dict)  # link index -> (response, foes, cont)
    links: list = field(default_factory=list)     # Connection, by link index
    shape: list = None

    def bit(self, row, j):
        """Bit J (counted from the right) of a request row's string."""
        return len(row) > j and row[len(row) - 1 - j] == "1"

    def foes(self, i, j):
        r = self.requests.get(i)
        return bool(r) and self.bit(r[1], j)

    def yields(self, i, j):
        """Link I must yield to link J (the response row)."""
        r = self.requests.get(i)
        return bool(r) and self.bit(r[0], j)


@dataclass
class Tls:
    id: str
    type: str
    program: str
    offset: float
    phases: list                 # [(duration, state)]

    def state_at(self, t):
        """The phase state string at time T (seconds, the program cycling from its offset)."""
        cycle = sum(d for d, _ in self.phases)
        if cycle <= 0:
            return self.phases[0][1]
        t = (t + self.offset) % cycle
        for d, s in self.phases:
            if t < d:
                return s
            t -= d
        return self.phases[-1][1]


def _shape(text):
    return [tuple(float(c) for c in p.split(",")[:2]) for p in (text or "").split()]


class Net:
    def __init__(self, lanes, connections, junctions, tls, edges):
        self.lanes, self.connections, self.junctions, self.tls, self.edges = lanes, connections, junctions, tls, edges

    def lanemap(self, step=0.25, margin=0.2):
        return LaneMap(list(self.lanes.values()), self.zones(step, margin), net=self)

    # -- the conflict zones ------------------------------------------------------------------------------------

    def zones(self, step=0.25, margin=0.2):
        """MARGIN: the lane bodies must overlap by more than this (m), so lanes that only touch (an incoming lane
        beside the outgoing one it runs against) make no zone."""
        out = []
        for jid, j in sorted(self.junctions.items()):
            n = len(j.links)
            for a in range(n):
                for b in range(a + 1, n):
                    if not (j.foes(a, b) or j.foes(b, a)):
                        continue
                    ca, cb = j.links[a], j.links[b]
                    if not ca.chain or not cb.chain:
                        continue
                    ia = self._overlap(ca.chain, cb.chain, step, margin)
                    ib = self._overlap(cb.chain, ca.chain, step, margin)
                    if ia is None or ib is None:
                        continue
                    la, sa = ia
                    lb, sb = ib
                    if la == lb:
                        continue
                    ya, yb = j.yields(a, b), j.yields(b, a)
                    prio = None if ya == yb else (lb if ya else la)
                    out.append(Zone("%s:%d:%d" % (jid, a, b), {la: sa, lb: sb}, prio,
                                    junction=jid, link_of={la: a, lb: b}))
        return out

    def _overlap(self, chain, other, step, margin=0.0):
        """→ (the chain lane the overlap with OTHER begins on, (s_enter, s_leave) from that lane's start), or None."""
        pts = []                                  # (lane, s along the chain from that lane's start, x, y, half width)
        for lid in chain:
            ln = self.lanes[lid]
            pts.append((lid, ln))
        other_lines = [(self.lanes[l].shape, 0.5 * self.lanes[l].width) for l in other]
        first = last = None
        start_lane, offset = None, 0.0
        base = 0.0
        for lid, ln in pts:
            shape, hw = ln.shape, 0.5 * ln.width
            total = sum(math.dist(shape[k], shape[k + 1]) for k in range(len(shape) - 1))
            s = 0.0
            while s <= total + 1e-9:
                x, y = _point_at(shape, s)
                if any(_dist_to_line(x, y, line) < hw + ohw - margin for line, ohw in other_lines):
                    if first is None:
                        first, start_lane, offset = s, lid, base
                    last = base + s
                s += step
            base += total
        if first is None:
            return None
        return start_lane, (round(first, 3), round(last - offset, 3))


def _point_at(shape, s):
    for k in range(len(shape) - 1):
        seg = math.dist(shape[k], shape[k + 1])
        if s <= seg or k == len(shape) - 2:
            f = 0.0 if seg == 0 else min(1.0, s / seg)
            return (shape[k][0] + f * (shape[k + 1][0] - shape[k][0]), shape[k][1] + f * (shape[k + 1][1] - shape[k][1]))
        s -= seg
    return shape[-1]


def _dist_to_line(x, y, line):
    best = float("inf")
    for k in range(len(line) - 1):
        (ax, ay), (bx, by) = line[k], line[k + 1]
        dx, dy = bx - ax, by - ay
        L = dx * dx + dy * dy
        t = 0.0 if L == 0 else max(0.0, min(1.0, ((x - ax) * dx + (y - ay) * dy) / L))
        best = min(best, math.hypot(x - (ax + t * dx), y - (ay + t * dy)))
    return best


def load_net(path, walking=False):
    """WALKING (the mixed adapter, wc-world s-db2f8e59): keep the `crossing` and `walkingarea` edges as lanes of that
    `function` (a crosswalk's lane, allow pedestrian; a walking area's polygon in its shape), outside the vehicle graph
    (no neighbours, no successors, no zones). Off (the default): skipped, as every lane adapter reads a net."""
    root = ET.parse(path).getroot()
    lanes, edges = {}, {}
    for e in root.iter("edge"):
        eid, func = e.get("id"), e.get("function", "normal")
        if func in ("crossing", "walkingarea"):
            if walking:
                for ln in e.iter("lane"):
                    allow = ln.get("allow")
                    lanes[ln.get("id")] = Lane(
                        ln.get("id"), float(ln.get("length")), float(ln.get("width", DEFAULT_WIDTH)),
                        speed=float(ln.get("speed", DEFAULT_SPEED)), shape=_shape(ln.get("shape")), edge=eid,
                        junction=eid[1:].rsplit("_", 1)[0], index=int(ln.get("index", 0)),
                        allow=tuple(allow.split()) if allow else None, function=func)
            continue
        internal = func == "internal"
        edges[eid] = {"from": e.get("from"), "to": e.get("to"), "lanes": [], "internal": internal}
        for ln in e.iter("lane"):
            allow = ln.get("allow")
            lanes[ln.get("id")] = Lane(
                ln.get("id"), float(ln.get("length")), float(ln.get("width", DEFAULT_WIDTH)),
                speed=float(ln.get("speed", DEFAULT_SPEED)), shape=_shape(ln.get("shape")), internal=internal,
                junction=(eid[1:].rsplit("_", 1)[0] if internal else None), edge=eid, index=int(ln.get("index", 0)),
                allow=tuple(allow.split()) if allow else None,
                disallow=tuple(ln.get("disallow").split()) if ln.get("disallow") else None)
            edges[eid]["lanes"].append(ln.get("id"))
    # neighbours: same edge by index (0 rightmost), the leftmost lane's opposite on the reverse edge
    for eid, e in edges.items():
        if e["internal"]:
            continue
        ls = sorted(e["lanes"], key=lambda l: lanes[l].index)
        for k, l in enumerate(ls):
            if k + 1 < len(ls):
                lanes[l].left = ls[k + 1]
            if k > 0:
                lanes[l].right = ls[k - 1]
        rev = [r for r, f in edges.items() if not f["internal"] and f["from"] == e["to"] and f["to"] == e["from"]]
        if rev:
            other = sorted(edges[rev[0]]["lanes"], key=lambda l: lanes[l].index)
            lanes[ls[-1]].left, lanes[ls[-1]].left_opposite = other[-1], True
    # connections
    conns, by_internal = [], {}
    for c in root.iter("connection"):
        f, t = c.get("from"), c.get("to")
        if f not in edges or t not in edges:
            continue
        cn = Connection("%s_%s" % (f, c.get("fromLane")), "%s_%s" % (t, c.get("toLane")), c.get("via"),
                        c.get("dir", ""), c.get("state", ""), tl=c.get("tl"),
                        tl_link=int(c.get("linkIndex")) if c.get("linkIndex") is not None else None)
        conns.append(cn)
        if edges[f]["internal"]:
            by_internal.setdefault(cn.from_lane, []).append(cn)
    for cn in conns:
        if cn.via:
            chain, cur = [cn.via], cn.via
            while True:
                nxt = [x for x in by_internal.get(cur, []) if x.via]
                if not nxt:
                    break
                cur = nxt[0].via
                chain.append(cur)
            cn.chain = chain
    # successors: a lane's next lanes through its connections (an internal lane's: its own connection's next)
    for cn in conns:
        nxt = cn.via or cn.to_lane
        if cn.from_lane in lanes and nxt in lanes and nxt not in lanes[cn.from_lane].succ:
            lanes[cn.from_lane].succ.append(nxt)
    # junctions, their link order, their request rows
    junctions = {}
    for j in root.iter("junction"):
        if j.get("type") == "internal":
            continue
        jn = Junction(j.get("id"), j.get("type"), (j.get("incLanes") or "").split(), (j.get("intLanes") or "").split(),
                      shape=_shape(j.get("shape")))
        for r in j.iter("request"):
            jn.requests[int(r.get("index"))] = (r.get("response"), r.get("foes"), r.get("cont"))
        junctions[jn.id] = jn
    for jn in junctions.values():
        for inc in jn.inc_lanes:
            for cn in conns:
                if cn.from_lane == inc and not edges[cn.from_lane.rsplit("_", 1)[0]]["internal"] \
                        and edges[cn.from_lane.rsplit("_", 1)[0]]["to"] == jn.id:
                    cn.junction, cn.link = jn.id, len(jn.links)
                    jn.links.append(cn)
    tls = {}
    for t in root.iter("tlLogic"):
        tls[t.get("id")] = Tls(t.get("id"), t.get("type"), t.get("programID"), float(t.get("offset", 0)),
                               [(float(p.get("duration")), p.get("state")) for p in t.iter("phase")])
    return Net(lanes, conns, junctions, tls, edges)
