"""scenario_director — a scene card on SUMO (road-scenarios s-e23be780 step 2b): the card at one of its SITES in a CARLA
town (road/maps), its actors placed along the ego's route from the site, its triggers armed and its steps applied each
SUMO step through TraCI. sumo_world.SumoWorld calls the director before every simulationStep (the SUMO host's Loop
stays the one TraCI client).

    scenario name: card:NAME[:VARIANT]@TOWN#SITE      e.g. card:ParkedObstacle@Town03#42
    build(name, work, seed) → (net, routes, script, director)     sumo_world.SCENARIOS' contract, plus the director

Placement (scenario_cards.carla_to_sumo gives the site's pose in SUMO's frame):
- the site's lane: the nearest lane whose heading is within 30° of the pose's; its edge and the position on it;
- the ego: AT the site, departing at the card's speed (CARLA places a scenario's actors relative to its trigger point,
  where the ego is when the scenario starts; the exerciser places them relative to the ego's start: the same), its
  route onward straight through the next junctions for ONWARD_M;
- an actor `at {ahead | behind, lane}`: AHEAD m past (BEHIND m before: back along straight predecessors) the site
  along the ego's route, on the site's lane + LANE (SUMO's lane index grows to the left: +1 left, as the card's).
  The card's main distance is clipped to the free run (the site's
  edge past the site) minus FREE_MARGIN_M (nina's review: the S1 poses sit 10–22 m before a junction), every actor
  moved by the same amount;
- `at {road: side}`: the junction at the end of the site's edge, an incoming edge of another approach, the actor
  SIDE_M before the junction on it (the source's _source_dist 30), its route straight across; added when its trigger
  fires (a car the source spawns moving).
Triggers (as the exerciser's, road_world._arm): `gap` (the ego's driving distance to the actor's rear), `tta`/`dist`
`beside` the actor (the ego's driving distance to the actor's position) or `at: junction` (to the end of the site's
edge), `traveled` (the actor's odometer), `t`. Steps: v (setSpeed), brake (setDecel + setSpeed 0), lane (changeLane
over CHANGE_S), go, speed (a side actor added at that speed, else setSpeed), `after` a delay.
"""
import math
import os
import random
import sys
from functools import lru_cache

import scenario_cards as C

ONWARD_M = 200.0             # the ego's route past the site (the scenario ends at its junction, as CARLA's WaitEndIntersection: a longer way only adds later junctions)
FREE_MARGIN_M = 66.0         # nina: the card's distance clipped to the free run minus this
SIDE_M = 30.0                # the side actor's start before the junction (the source's _source_dist)
CHANGE_S = 3.0               # a scripted lane change (the source's CutIn change_time)
EGO = "ego"


def _sumolib():
    sys.path.append(os.path.join(os.environ.get("SUMO_HOME", "/usr/share/sumo"), "tools"))
    import sumolib
    return sumolib


@lru_cache(maxsize=None)
def net_of(town):
    return _sumolib().net.readNet(str(C.MAPS / ("%s.net.xml" % town)))


def parse(name):
    """card:NAME[:VARIANT]@TOWN#SITE → (card name with its variant, town, site index)."""
    body = name[5:] if name.startswith("card:") else name
    card, _, rest = body.partition("@")
    town, _, site = rest.partition("#")
    if not town or not site.isdigit():
        raise ValueError("%r: a SUMO card is card:NAME[:VARIANT]@TOWN#SITE" % name)
    return card, town, int(site)


def _heading_at(shape, pos):
    """SUMO's heading (degrees clockwise from north) of SHAPE at POS m along it."""
    run = 0.0
    for (x0, y0), (x1, y1) in zip(shape, shape[1:]):
        seg = math.hypot(x1 - x0, y1 - y0)
        if run + seg >= pos or (x1, y1) == shape[-1]:
            return math.degrees(math.atan2(x1 - x0, y1 - y0)) % 360.0
        run += seg
    return 0.0


def locate(town, x, y, angle):
    """The lane at (x, y) heading ANGLE (SUMO's degrees): (lane, position on it)."""
    sl = _sumolib()
    best = None
    for lane, d in net_of(town).getNeighboringLanes(x, y, 5.0):
        if not lane.allows("passenger"):
            continue
        shape = lane.getShape()
        pos = sl.geomhelper.polygonOffsetWithMinimumDistanceToPoint((x, y), shape, perpendicular=False)
        dh = abs((_heading_at(shape, pos) - angle + 180.0) % 360.0 - 180.0)
        if dh < 30.0 and (best is None or d < best[2]):
            best = (lane, pos, d)
    if best is None:
        raise ValueError("%s: no lane at (%.1f, %.1f) heading %.0f°" % (town, x, y, angle))
    return best[0], best[1]


def _straight_next(edge, lane_index):
    """The edge a car on LANE_INDEX of EDGE goes on to: straight from that lane first, else any way on."""
    outs = []
    for to, conns in edge.getOutgoing().items():
        for c in conns:
            mine = c.getFromLane().getIndex() == lane_index
            outs.append((0 if mine else 1, 0 if c.getDirection() == "s" else 1, to.getID(), to))
    return sorted(outs, key=lambda o: o[:3])[0][3] if outs else None


def _straight_prev(edge):
    ins = []
    for frm, conns in edge.getIncoming().items():
        for c in conns:
            ins.append((0 if c.getDirection() == "s" else 1, frm.getID(), frm))
    return sorted(ins)[0][2] if ins else None


def place(card, town, site):
    """The card at SITE of TOWN: {site: (edge, lane, pos), ego: {route, lane, pos, v}, actors: [...], junction_s}."""
    poses = C.sites(card, town)
    p = next((q for q in poses if q["i"] == site), None)
    if p is None:
        raise ValueError("%s: site %d of %s is not one of its sites (%s)" % (card["scenario"], site, town, [q["i"] for q in poses]))
    lane, pos = locate(town, p["sumo"]["x"], p["sumo"]["y"], p["sumo"]["angle"])
    edge, li = lane.getEdge(), lane.getIndex()
    back, depart = [], pos                          # the ego at the site
    route, run, e = [edge], edge.getLength() - pos, edge
    onward = float((card.get("sumo") or {}).get("onward", ONWARD_M))   # a card whose actor needs a longer way (the emergency vehicle)
    while run < onward:
        e = _straight_next(e, li)
        if e is None or e in route:
            break
        route.append(e)
        run += e.getLength()
    free = edge.getLength() - pos
    # the card's main distance clipped to the free run (nina's review), every actor moved by the same amount
    aheads = [a["at"].get("ahead", 0.0) for a in card.get("actors") or [] if "ahead" in a.get("at", {})]
    clip = "distance" in (card.get("params") or {})          # an obstacle's distance; traffic ahead may pass a junction
    shift = min(0.0, (free - FREE_MARGIN_M) - min(aheads)) if aheads and clip else 0.0
    actors = []
    expanded = []
    for a in card.get("actors") or []:                       # a flow: `count` cars `gap` m apart
        for k in range(int(a.get("count", 1))):
            b = dict(a, id=a["id"] if "count" not in a else "%s_%d" % (a["id"], k), at=dict(a["at"]))
            b["at"]["ahead"] = float(a["at"].get("ahead", 0.0)) + k * float(a.get("gap", 0.0))
            expanded.append(b)
    for a in expanded:
        at = a["at"]
        item = dict(a)
        if at.get("road") == "side":                         # timed: at its speed it reaches the junction as the ego
            tta = float((a.get("trigger") or {}).get("tta", 0.0))      # does from the trigger's TTA (the source's sync)
            sp = max([float(st.get("speed", 0.0)) for st in a.get("script") or []] + [0.0])
            item["place"] = _side(edge, route, sp * tta if sp and tta else SIDE_M)
        elif at.get("opposite"):
            try:
                item["place"] = _opposite(edge, pos + float(at.get("ahead", 0.0)) + shift, a, town, site)
            except ValueError:
                if "_" in a["id"] and a["id"].rsplit("_", 1)[1].isdigit():
                    continue                                 # a flow's car past the road's end: the flow is the cars that fit
                raise
        else:
            s = pos + float(at.get("ahead", 0.0)) + shift - float(at.get("behind", 0.0))
            way, ri = list(route), 0
            while s < 0:                                     # behind the site: back along straight predecessors
                prev = _straight_prev(way[0])
                if prev is None:
                    raise ValueError("%s at %s#%d: no road %.0f m behind the site" % (a["id"], town, site, -s))
                way.insert(0, prev)
                s += prev.getLength()
            route_a = way
            while s > route_a[ri].getLength() and ri + 1 < len(route_a):
                s -= route_a[ri].getLength()
                ri += 1
            eid = route_a[ri]
            idx = li + int(at.get("lane", 0))
            if not 0 <= idx < eid.getLaneNumber():
                if a.get("script") and any("lane" in st for st in a["script"]):
                    raise ValueError("%s at %s#%d: lane %d off %s (%d lanes)" % (a["id"], town, site, idx, eid.getID(), eid.getLaneNumber()))
                idx = max(0, min(eid.getLaneNumber() - 1, idx))   # traffic on a lane the road lacks: queued on this one,
                s += 15.0                                         # further ahead (Town01/02: one lane each way)
                while s > route_a[ri].getLength() and ri + 1 < len(route_a):
                    s -= route_a[ri].getLength()
                    ri += 1
                eid = route_a[ri]
            if not 0 <= idx < eid.getLaneNumber():
                raise ValueError("%s at %s#%d: lane %d off %s" % (a["id"], town, site, idx, eid.getID()))
            item["place"] = {"route": [x.getID() for x in route_a[ri:]], "lane": idx, "pos": round(max(0.1, s), 2)}
        actors.append(item)
    back = float((card.get("sumo") or {}).get("back", 0.0))  # a junction card whose site is too near its junction for the
    ego_li, s = li, depart - back                            # trigger's TTA: the ego starts BACK m before it (the actors stay)
    while s < 0:
        prev = _straight_prev(route[0])
        if prev is None or prev in route or prev.getLaneNumber() <= ego_li:
            s = 0.1
            break
        route.insert(0, prev)
        s += prev.getLength()
    depart = max(0.1, s) if back else depart
    return {"site": (edge.getID(), li, round(pos, 2)), "free": round(free, 1), "shift": round(shift, 1),
            "junction": {"edge": edge.getID(), "pos": edge.getLength()},
            "ego": {"route": [x.getID() for x in route], "lane": li, "pos": round(depart, 2), "v": float(card["ego"]["v"])},
            "actors": actors}


def _opposite(edge, s, a, town, site):
    """The oncoming lane of EDGE (its reverse edge's lane 0) at the point S m along EDGE: the actor faces the ego."""
    rev = next((e for e in edge.getToNode().getOutgoing() if e.getToNode() == edge.getFromNode()), None)
    if rev is None:
        raise ValueError("%s at %s#%d: %s has no oncoming lane" % (a["id"], town, site, edge.getID()))
    p = rev.getLength() - s
    if p < 0.1:
        raise ValueError("%s at %s#%d: %.0f m along %s is past its oncoming lane" % (a["id"], town, site, s, edge.getID()))
    nxt = _straight_next(rev, 0)
    return {"route": [rev.getID()] + ([nxt.getID()] if nxt is not None else []), "lane": 0, "pos": round(p, 2)}


def _side(edge, route, before=None):
    """The side actor's way: an incoming edge of the junction at EDGE's end that is not the ego's (nor its reverse),
    BEFORE m (default SIDE_M) before the junction, back over its straight predecessors when it is shorter, and on
    straight across."""
    before = SIDE_M if before is None else before
    node = edge.getToNode()
    mine = {x.getID() for x in route}
    for frm in sorted(node.getIncoming(), key=lambda x: x.getID()):
        if frm.getID() in mine or frm.getFromNode() == edge.getToNode() or frm.getToNode() != node:
            continue
        if frm.getFromNode() == edge.getFromNode():
            continue                               # the ego's reverse
        if not any(ln.allows("passenger") for ln in frm.getLanes()):
            continue
        nxt = _straight_next(frm, 0)
        if nxt is None:
            continue
        way, p = [frm], frm.getLength() - before
        while p < 0:
            prev = _straight_prev(way[0])
            if prev is None or prev in way or prev.getID() in mine:
                p = 0.1
                break
            way.insert(0, prev)
            p += prev.getLength()
        return {"route": [x.getID() for x in way] + [nxt.getID()], "lane": 0, "pos": round(max(0.1, p), 2), "spawn": True}
    raise ValueError("no side road at the junction after %s" % edge.getID())


def build(name, work, seed=1, n=0, **_):
    """sumo_world.SCENARIOS' contract for a card: (net, routes, script, director)."""
    cname, town, site = parse(name)
    card = C.load(cname)
    pl = place(card, town, site)
    rows = ['<routes>', '<vType id="ego_t" accel="3.0" decel="6.0" sigma="0" maxSpeed="20" length="4.5" width="1.8"/>',
            '<vType id="actor_t" accel="3.0" decel="8.0" sigma="0" maxSpeed="25" length="4.5" width="1.8"/>',
            '<vType id="emergency_t" vClass="emergency" accel="3.5" decel="8.0" sigma="0" maxSpeed="30" speedFactor="1.5" length="5.0" width="2.0"/>']
    e = pl["ego"]
    rows.append('<vehicle id="%s" type="ego_t" depart="0" departLane="%d" departPos="%.2f" departSpeed="%.2f"><route edges="%s"/></vehicle>'
                % (EGO, e["lane"], e["pos"], e["v"], " ".join(e["route"])))
    for a in pl["actors"]:
        pa = a["place"]
        if pa.get("spawn"):
            continue
        vt = "emergency_t" if a.get("kind") == "emergency" else "actor_t"
        length = float(a.get("length", C.KIND[a.get("kind", "car")][1]))
        # no bluelight device: SUMO's would move the ego aside itself (it changes others' lanes whatever their lane-change
        # mode), doing the yielding the card asks of the family; the emergency vehicle is its vClass and its speed
        dev = ""
        rows.append('<vehicle id="%s" type="%s" depart="0" departLane="%d" departPos="%.2f" departSpeed="%.2f" length="%.1f"><route edges="%s"/>%s</vehicle>'
                    % (a["id"], vt, pa["lane"], pa["pos"], float(a.get("v", 0.0)), length, " ".join(pa["route"]), dev))
    rows.append("</routes>")
    routes = os.path.join(work, "%s.rou.xml" % name.replace(":", "_").replace("@", "_").replace("#", "_"))
    with open(routes, "w") as f:
        f.write("\n".join(rows) + "\n")
    return str(C.MAPS / ("%s.net.xml" % town)), routes, [], Director(card, pl)


class Director:
    """The card's triggers and steps, applied before each SUMO step (SumoWorld.step)."""

    def __init__(self, card, placed):
        self.card, self.pl = card, placed
        self.armed, self.queue, self.started, self.spawned = [], [], set(), set()
        for a in placed["actors"]:
            for st in a.get("script") or []:
                when = st.get("when")
                steps = [(k, st[k]) for k in ("go", "speed", "v", "brake", "lane") if k in st]
                after = float(st.get("after", 0.0))
                if when is None:
                    self.queue.append((float(st.get("t", 0.0)) + after, a, steps))
                else:
                    self.armed.append((a, dict(a["trigger"] if when == "trigger" else when), steps, after))
        self.fired = []                                                    # [(t, actor id, what)] for the report
        self.spawn_v = {}                                                  # a trigger-spawned actor: its speed at insertion
        self.held = {}                                                     # an emergency vehicle: s it was held behind the ego

    def _dist(self, c, edge, pos):
        try:
            d = c.vehicle.getDrivingDistance(EGO, edge, pos)
        except Exception:                                                  # noqa: BLE001 — not on its route
            return None
        return None if d is None or d < -1e6 else d

    def _hit(self, c, t, a, when):
        if "t" in when and t >= when["t"] - 1e-9:
            return True
        pa = a["place"]
        if "gap" in when and a["id"] in c.vehicle.getIDList():
            d = self._dist(c, c.vehicle.getRoadID(a["id"]), max(0.0, c.vehicle.getLanePosition(a["id"]) - c.vehicle.getLength(a["id"])))
            if d is not None and 0.0 <= d <= when["gap"]:
                return True
        if when.get("beside") or "at" in when:
            if when.get("beside") and a["id"] in c.vehicle.getIDList():
                d = self._dist(c, c.vehicle.getRoadID(a["id"]), c.vehicle.getLanePosition(a["id"]))
            elif when.get("at") == "junction":
                j = self.pl["junction"]
                d = self._dist(c, j["edge"], j["pos"] - 0.1)
            else:
                d = None
            v = max(c.vehicle.getSpeed(EGO), 0.1)
            if d is not None and d >= 0.0 and (d <= when.get("dist", 0.0) or d / v <= when.get("tta", 0.0)):
                return True
        if "traveled" in when and a["id"] in c.vehicle.getIDList() and c.vehicle.getDistance(a["id"]) >= when["traveled"]:
            return True
        if "junction_ahead" in when and a["id"] in c.vehicle.getIDList():          # its lane's end is the next junction
            lane = c.vehicle.getLaneID(a["id"])
            if not lane.startswith(":") and c.lane.getLength(lane) - c.vehicle.getLanePosition(a["id"]) <= when["junction_ahead"]:
                return True
        return False

    def _apply(self, c, t, a, steps):
        """A trigger's steps on actor A; a step TraCI refuses is recorded (fired: "failed …"), never the run's end."""
        for what, arg in steps:
            try:
                self._step(c, t, a, steps, what, arg)
            except Exception as e:  # noqa: BLE001 — traci.TraCIException; the run goes on and the report says it
                self.fired.append((round(t, 2), a["id"], "failed %s: %s" % (what, str(e)[:120])))

    def _step(self, c, t, a, steps, what, arg):
        vid, pa = a["id"], a["place"]
        if True:
            if what in ("go", "speed") and pa.get("spawn") and vid not in self.spawned:
                self.spawned.add(vid)                                      # added once: inserted at the next step
                rid = "r_" + vid
                c.route.add(rid, pa["route"])
                sp = float(dict(steps).get("speed", a.get("v", 0.0)) or 0.0)
                # inserted standing (SUMO refuses a fast insertion before a minor road's junction: "unpriorised junction
                # too close"), then at SP from its first step (setPreviousSpeed): the source's car spawned moving
                c.vehicle.add(vid, rid, typeID="actor_t", departLane=str(pa["lane"]), departPos=str(pa["pos"]), departSpeed="0")
                self.spawn_v[vid] = sp
            elif pa.get("spawn") and what in ("go", "speed"):
                return                                                     # spawned already, at that speed
            elif vid not in c.vehicle.getIDList():
                return
            elif what == "v":
                c.vehicle.setSpeed(vid, float(arg))
            elif what == "speed":
                c.vehicle.setSpeed(vid, float(arg))
            elif what == "brake":
                c.vehicle.setDecel(vid, float(arg))
                c.vehicle.setSpeed(vid, 0.0)
            elif what == "lane":
                c.vehicle.changeLane(vid, pa["lane"] + int(arg), CHANGE_S)
            elif what == "go":
                c.vehicle.setSpeed(vid, -1)
            self.fired.append((round(t, 2), vid, what))

    def tick(self, c, t):
        """Before a SUMO step at time T: hold the actors at their speeds once inserted, fire what is due."""
        ids = set(c.vehicle.getIDList())
        for a in self.pl["actors"]:
            if a["id"] in ids and a["id"] not in self.started:
                self.started.add(a["id"])
                c.vehicle.setLaneChangeMode(a["id"], 0)                    # an actor goes where its script says only
                if a["id"] in self.spawn_v:                                # spawned by its trigger: at its step's speed
                    c.vehicle.setPreviousSpeed(a["id"], self.spawn_v[a["id"]])
                    c.vehicle.setSpeed(a["id"], self.spawn_v[a["id"]])
                elif a.get("script") or not a.get("moving", True) or float(a.get("v", 0.0)) == 0.0:
                    c.vehicle.setSpeed(a["id"], float(a.get("v", 0.0)))
                if a.get("breaks_rules"):
                    c.vehicle.setSpeedMode(a["id"], 0)
                elif a.get("kind") == "emergency":                         # lights on: through red lights and right of way,
                    c.vehicle.setSpeedMode(a["id"], 7)                     # still its safe gap to the car ahead (Town03 #49: its
                                                                           # walk back crosses a lit junction; it waited 50 s at red)
        if EGO not in ids:
            return
        ego_v = c.vehicle.getSpeed(EGO)
        for a in self.pl["actors"]:                    # v_rel: the source's "the ego's speed + N" (the ego takes the town's limit)
            if "v_rel" in a and a["id"] in ids:
                c.vehicle.setSpeed(a["id"], ego_v + float(a["v_rel"]))
        for a in self.pl["actors"]:                    # yield_emergency_vehicle (LB 2.0): held behind the ego within 30 m
            if a.get("kind") == "emergency" and a["id"] in ids:
                lead = c.vehicle.getLeader(a["id"], 30.0)
                if lead and lead[0] == EGO and c.vehicle.getSpeed(a["id"]) < c.vehicle.getAllowedSpeed(a["id"]) * 0.9 \
                        and not self._at_red(c):
                    self.held[a["id"]] = round(self.held.get(a["id"], 0.0) + 0.1, 1)
        keep = []
        for a, when, steps, after in self.armed:
            if self._hit(c, t, a, when):
                if after > 0:
                    self.queue.append((t + after, a, steps))
                else:
                    self._apply(c, t, a, steps)
            else:
                keep.append((a, when, steps, after))
        self.armed = keep
        due = [q for q in self.queue if q[0] <= t + 1e-9]
        self.queue = [q for q in self.queue if q[0] > t + 1e-9]
        for _, a, steps in due:
            self._apply(c, t, a, steps)


    @staticmethod
    def _at_red(c):
        """The ego stopped for a red or yellow light within 40 m: not a refusal to yield (its 600 m way passes lights)."""
        tls = c.vehicle.getNextTLS(EGO)
        return bool(tls) and tls[0][2] <= 40.0 and tls[0][3] in "rRyYu" and c.vehicle.getSpeed(EGO) < 1.0

    def report(self):
        """What the run's table reads: the steps fired, the emergency vehicles' held seconds, the placement."""
        return {"fired": self.fired, "emergency_held_s": self.held, "site": self.pl["site"], "free": self.pl["free"],
                "shift": self.pl["shift"]}
