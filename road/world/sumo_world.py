"""sumo_world.py — the road's TRUTH (road-world s-e812715d step 4, the framework brief's L0): one SUMO process driven
over TraCI, headless, at the responder's step (0.1 s), the ego under the stack's control with SUMO's own safety off.

- The net and the routes: a scenario writes them into a work directory (`straight`: the old harness's 1 km two-lane
  road with its planted calm / aggr vTypes, the ego behind the traffic and faster than the calm cap, so it must
  brake or change lanes; each CARLA town in road/maps by its name, every car on its own way; more scenarios join as the cases need them). Every vehicle in depart order (SUMO drops an
  out-of-order one silently).
- The ego: speed mode 0 and lane-change mode 0 (no SUMO safety, no strategic changes: the RSS stack is what is under
  test, and a TraCI change is done as asked); its acceleration set each step (as the speed it gives, setSpeed), a lane
  change through changeLane with SUMO's continuous change of `LC_DURATION` s.
- The truth per step: every vehicle and person as a pose (the centre: SUMO's position is the front bumper), its
  lane and s, speed, vClass, length and width; the collisions the step had (SUMO's own check, junctions included,
  `warn`: nobody is removed) and whether the ego was in one.

    w = SumoWorld(scenario, work, seed); w.start(); w.step(); w.truth() · w.ego() · w.control(accel, lane) · w.close()

The TraCI module is injected (`traci=`) so the tests run without a simulator; the default imports the system's."""
import functools
import heapq
import math
import os
import random
import subprocess
import sys
import xml.etree.ElementTree as ET

DT = 0.1
EGO = "ego"
LC_DURATION = 1.0              # a lane change takes 1 s (the restrictor's contract, step 2)
EDGE_M, LANES = 1000.0, 2
MAPS = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "maps")   # road/maps: the towns' nets
ROUTE_M = 1500.0               # a town's way, m
CRAWL_MS = 3.0                 # a lane limited below this is a shoulder in CARLA's nets, not a lane to drive, m/s
LATE_M = 5.0                   # how near a lane's end its way is settled, beyond two seconds of the ego's speed, m
TURNS = {"r": "right", "R": "right", "l": "left", "L": "left", "s": "straight"}     # a connection's dir
VTYPES = {                     # the old harness's planted styles (metispy sumo_harness): the ground truth of a style
    "calm": dict(accel=1.0, decel=2.0, sigma=0.2, maxSpeed=8.0, tau=1.4, color="0,0,1"),
    "aggr": dict(accel=3.0, decel=4.5, sigma=0.8, maxSpeed=15.0, tau=0.9, color="1,0,0"),
}


def load_traci():
    try:
        import traci
    except ImportError:
        sys.path.append(os.path.join(os.environ.get("SUMO_HOME", "/usr/share/sumo"), "tools"))
        import traci
    return traci


def _net(work):
    net = os.path.join(work, "straight.net.xml")
    if not os.path.exists(net):
        nod, edg = os.path.join(work, "straight.nod.xml"), os.path.join(work, "straight.edg.xml")
        with open(nod, "w") as f:
            f.write('<nodes><node id="a" x="0" y="0"/><node id="b" x="%g" y="0"/></nodes>' % EDGE_M)
        with open(edg, "w") as f:
            f.write('<edges><edge id="E" from="a" to="b" numLanes="%d" speed="15"/></edges>' % LANES)
        subprocess.run(["netconvert", "-n", nod, "-e", edg, "-o", net], check=True, capture_output=True)
    return net


def _routes(work, name, rows):
    lines = ["<routes>"]
    lines += ['<vType id="%s" accel="%s" decel="%s" sigma="%s" maxSpeed="%s" tau="%s" color="%s"/>'
              % (k, p["accel"], p["decel"], p["sigma"], p["maxSpeed"], p["tau"], p["color"]) for k, p in VTYPES.items()]
    lines.append('<route id="r" edges="E"/>')
    lines += [x for _, x in sorted(rows, key=lambda r: r[0])]
    lines.append("</routes>")
    routes = os.path.join(work, name)
    with open(routes, "w") as f:
        f.write("\n".join(lines))
    return routes


def straight(work, seed, n=40):
    """The straight: a 1 km road of LANES lanes at 15 m/s, N vehicles of the planted styles (a seeded draw) a 0.9 s
    apart on random lanes and speeds, the ego (aggr, 6 m/s, lane 0) at 8 s behind them. → (net, routes)."""
    net = _net(work)
    rng = random.Random(seed)
    rows = [(8.0, '<vehicle id="%s" type="aggr" route="r" depart="8.0" departLane="0" departPos="0" departSpeed="6"/>' % EGO)]
    for i in range(n):
        vt = "calm" if rng.random() < 0.5 else "aggr"
        rows.append((i * 0.9, '<vehicle id="%s_%d" type="%s" route="r" depart="%.1f" departLane="random" departSpeed="random"/>'
                     % (vt, i, vt, i * 0.9)))
    return net, _routes(work, "straight_%d.rou.xml" % seed, rows)


# the indicator's TraCI bits (SUMO's VEH_SIGNAL_BLINKER_RIGHT / _LEFT)
BLINKER_RIGHT, BLINKER_LEFT = 1, 2


def cut_out(work, seed, n=0):
    """road-2 item 2: a slow lead (calm, 8 m/s) 60 m ahead of the ego on lane 0 signals left at t 4 (+ a seeded
    jitter) and changes to lane 1 at t 5.5; the ego (aggr, 10 m/s) closes on it. A script: [(t, vehicle, what,
    arg)]: signal BITS, change LANE (LC_DURATION), its own lane changes off. → (net, routes, script)."""
    rng = random.Random(seed)
    j = rng.uniform(0.0, 0.5)
    rows = [(0.0, '<vehicle id="lead" type="calm" route="r" depart="0.0" departLane="0" departPos="60" departSpeed="8"/>'),
            (0.0, '<vehicle id="%s" type="aggr" route="r" depart="0.0" departLane="0" departPos="0" departSpeed="10"/>' % EGO)]
    script = [(0.1, "lead", "lcmode", 0), (4.0 + j, "lead", "signal", BLINKER_LEFT),
              (5.5 + j, "lead", "change", 1), (5.5 + j + LC_DURATION + 0.5, "lead", "signal", 0)]
    return _net(work), _routes(work, "cut_out_%d.rou.xml" % seed, rows), script


def cut_in(work, seed, n=0):
    """road-2 item 2: a car (aggr, 12 m/s) on lane 1, 25 m ahead of the ego (aggr, 12 m/s, lane 0), signals right at
    t 2 (+ a seeded jitter) and cuts into lane 0 at t 3.5. → (net, routes, script)."""
    rng = random.Random(seed)
    j = rng.uniform(0.0, 0.5)
    rows = [(0.0, '<vehicle id="cutter" type="aggr" route="r" depart="0.0" departLane="1" departPos="25" departSpeed="12"/>'),
            (0.0, '<vehicle id="%s" type="aggr" route="r" depart="0.0" departLane="0" departPos="0" departSpeed="12"/>' % EGO)]
    script = [(0.1, "cutter", "lcmode", 0), (0.1, "cutter", "speed", 12.0), (2.0 + j, "cutter", "signal", BLINKER_RIGHT),
              (3.5 + j, "cutter", "change", 0), (3.5 + j + LC_DURATION + 0.5, "cutter", "signal", 0)]
    return _net(work), _routes(work, "cut_in_%d.rou.xml" % seed, rows), script


def _town(net):
    """A CARLA town's net as routes: the edges a car can drive, each with the edges it connects to and its length."""
    root = ET.parse(net).getroot()
    edges = {}
    for e in root.findall("edge"):
        lanes = e.findall("lane")
        if e.get("function", "normal") == "normal" and lanes and any(la.get("allow") in (None, "passenger") or "passenger" in la.get("allow", "").split() for la in lanes):
            edges[e.get("id")] = {"length": float(lanes[0].get("length")), "next": set(), "turns": {}, "ways": {}, "speeds": [float(la.get("speed")) for la in lanes]}
    for c in root.findall("connection"):
        if c.get("from") in edges and c.get("to") in edges:
            edges[c.get("from")]["next"].add(c.get("to"))
            edges[c.get("from")]["ways"].setdefault(int(c.get("fromLane")), set()).add(c.get("to"))
            edges[c.get("from")]["turns"].setdefault(TURNS.get(c.get("dir")), []).append((c.get("to"), int(c.get("fromLane"))))
    return edges


def _route_from(edges, start, want):
    """The shortest way from START to the edge nearest WANT metres out (Dijkstra). → the edges in order."""
    dist, prev, heap = {start: 0.0}, {}, [(0.0, start)]
    while heap:
        d, e = heapq.heappop(heap)
        for n in sorted(edges[e]["next"]):
            nd = d + edges[n]["length"]
            if nd < dist.get(n, math.inf):
                dist[n], prev[n] = nd, e
                heapq.heappush(heap, (nd, n))
    end = min(sorted(dist), key=lambda e: abs(dist[e] - want))
    way = [end]
    while way[-1] != start:
        way.append(prev[way[-1]])
    return way[::-1]


def town(work, seed, n=30, name="Town01"):
    """A CARLA town (road/maps): the ego on a seeded way about ROUTE_M long, N cars of the planted styles on their own seeded ways ahead of it. No destination: the ego arrives at
    its route's end. → (net, routes)."""
    net = os.path.join(MAPS, name + ".net.xml")
    edges = _town(net)
    rng = random.Random(seed)
    names = sorted(edges)
    longest = lambda s: _route_from(edges, s, ROUTE_M)
    def way():
        for _ in range(50):
            w = longest(rng.choice(names))
            if sum(edges[e]["length"] for e in w) > ROUTE_M / 3:
                return w
        raise RuntimeError("%s: no way of %g m" % (name, ROUTE_M / 3))
    rows = [(8.0, '<vehicle id="%s" type="aggr" depart="8.0" departSpeed="6"><route edges="%s"/></vehicle>' % (EGO, " ".join(way())))]
    for i in range(n):
        vt = "calm" if rng.random() < 0.5 else "aggr"
        rows.append((i * 0.5, '<vehicle id="%s_%d" type="%s" depart="%.1f" departLane="best" departSpeed="random"><route edges="%s"/></vehicle>'
                     % (vt, i, vt, i * 0.5, " ".join(way()))))
    lines = ["<routes>"]
    lines += ['<vType id="%s" accel="%s" decel="%s" sigma="%s" maxSpeed="%s" tau="%s" color="%s"/>' % (k, p["accel"], p["decel"], p["sigma"], p["maxSpeed"], p["tau"], p["color"]) for k, p in VTYPES.items()]
    lines += [x for _, x in sorted(rows, key=lambda r: r[0])]
    lines.append("</routes>")
    routes = os.path.join(work, "%s_%d.rou.xml" % (name, seed))
    with open(routes, "w") as f:
        f.write("\n".join(lines))
    return net, routes


SCENARIOS = {"straight": straight, "cut_out": cut_out, "cut_in": cut_in}
for _name in sorted(f[:-len(".net.xml")] for f in (os.listdir(MAPS) if os.path.isdir(MAPS) else ()) if f.endswith(".net.xml")):
    SCENARIOS[_name] = functools.partial(town, name=_name)
DESTS = {"straight": 950.0, "cut_out": 400.0, "cut_in": 400.0}       # the ego's destination (s on its lane), short of the net's end: arrived
                                  # while it is still in the net (TraCI drops a vehicle that leaves)


def _read(dom, getter, vid, default):
    """A TraCI reading a fake (the tests') or an older TraCI may lack: its default then."""
    try:
        return type(default)(getattr(dom, getter)(vid))
    except (AttributeError, KeyError, TypeError):
        return default


class SumoWorld:
    def __init__(self, scenario, work, seed=1, dt=DT, traci=None, label=None, sumo="sumo", **kw):
        os.makedirs(work, exist_ok=True)
        made = SCENARIOS[scenario](work, seed, **kw)
        self.net, self.routes = made[:2]
        self.script = sorted(made[2]) if len(made) > 2 else []     # [(t, vehicle, what, arg)]: the scenario's acts
        self.seed, self.dt, self.sumo = int(seed), float(dt), sumo
        self.traci = traci or load_traci()
        self.label = label or "road-%s-%d" % (scenario, seed)
        self.t, self.steps, self.collisions, self.ego_collisions = 0.0, 0, [], 0
        self.ego_seen = self.ego_done = False
        self.added, self.closed = 0, {}
        self.conn = None

    def cmd(self):
        return [self.sumo, "-n", self.net, "-r", self.routes, "--step-length", str(self.dt), "--seed", str(self.seed),
                "--no-warnings", "--no-step-log", "--collision.action", "warn", "--collision.check-junctions",
                "--lanechange.duration", str(LC_DURATION), "--default.speeddev", "0.2"]

    def start(self):
        self.traci.start(self.cmd(), label=self.label)
        self.conn = self.traci.getConnection(self.label)
        return self

    def close(self):
        if self.conn is not None:
            self.conn.close()
            self.conn = None

    def step(self):
        """One SUMO step: the collisions it had (the ego's counted), the ego's insertion (its modes set once) and its
        arrival (ego_done). → whether the ego is on the road."""
        c = self.conn
        while self.script and self.script[0][0] <= self.t + 1e-9:
            _, vid, what, arg = self.script.pop(0)
            if vid not in c.vehicle.getIDList():
                continue
            if what == "lcmode":
                c.vehicle.setLaneChangeMode(vid, int(arg))
            elif what == "speed":
                c.vehicle.setSpeed(vid, float(arg))
            elif what == "signal":
                c.vehicle.setSignals(vid, int(arg))
            elif what == "change":
                c.vehicle.changeLane(vid, int(arg), LC_DURATION)
        c.simulationStep()
        self.steps += 1
        self.t = round(self.steps * self.dt, 6)
        for k in c.simulation.getCollisions():
            rec = {"t": self.t, "collider": k.collider, "victim": k.victim, "type": getattr(k, "type", "")}
            self.collisions.append(rec)
            if EGO in (k.collider, k.victim):
                self.ego_collisions += 1
        on = EGO in c.vehicle.getIDList()
        if on and not self.ego_seen:
            self.ego_seen = True
            c.vehicle.setSpeedMode(EGO, 0)
            c.vehicle.setLaneChangeMode(EGO, 0)
        if self.ego_seen and not on:
            self.ego_done = True
        return on

    def _pose(self, dom, vid, vehicle=True):
        x, y = dom.getPosition(vid)
        ang = dom.getAngle(vid)                         # SUMO: degrees from north, clockwise
        h = math.radians(90.0 - ang)
        length, width = dom.getLength(vid), dom.getWidth(vid)
        if vehicle:                                     # the front bumper → the centre
            x, y = x - 0.5 * length * math.cos(h), y - 0.5 * length * math.sin(h)
        try:
            z = dom.getPosition3D(vid)[2]               # the towns have hills
        except (AttributeError, KeyError, TypeError):
            z = 0.0
        out = {"x": x, "y": y, "z": z, "heading": h, "length": length, "width": width, "speed": dom.getSpeed(vid),
               "lane": dom.getLaneID(vid), "s": dom.getLanePosition(vid)}
        if vehicle:                                     # what an indicator and the lane offset show (road-2 item 2)
            out["signals"], out["lat"] = _read(dom, "getSignals", vid, 0), _read(dom, "getLateralLanePosition", vid, 0.0)
        return out

    def truth(self):
        """{id: pose} of every vehicle and person on the net this step (the pose: x, y the centre, heading in radians
        from +x, length, width, speed, lane, s, vclass, and for a vehicle its lane index and type)."""
        c, out = self.conn, {}
        for vid in c.vehicle.getIDList():
            p = self._pose(c.vehicle, vid)
            p.update(vclass=c.vehicle.getVehicleClass(vid), index=c.vehicle.getLaneIndex(vid), type=c.vehicle.getTypeID(vid))
            if vid == EGO:
                p["route"] = list(c.vehicle.getRoute(vid))
            out[vid] = p
        for pid in c.person.getIDList():
            p = self._pose(c.person, pid, vehicle=False)
            p.update(vclass="pedestrian", index=0, type="pedestrian")
            out[pid] = p
        return out

    # ── the person's word on the ego's way ──
    def graph(self):
        if not hasattr(self, "_graph"):
            self._graph = _town(self.net)
        return self._graph

    def turn(self, way):
        """The ego's route, WAY at the next junction its route reaches that offers it, a shortest way on from there. → (the edge it turns from, the lanes that turn leaves from), or None."""
        c, edges = self.conn, self.graph()
        route = list(c.vehicle.getRoute(EGO))
        at = c.vehicle.getRouteIndex(EGO)
        first = at + 1 if c.vehicle.getLaneID(EGO).startswith(":") else at   # in a junction: that one is taken already
        for k in range(first, len(route)):
            options = edges.get(route[k], {}).get("turns", {}).get(way)
            if not options:
                continue
            to = sorted({o[0] for o in options})[0]
            c.vehicle.setRoute(EGO, route[at:k + 1] + _route_from(edges, to, ROUTE_M))
            lanes = sorted(o[1] for o in options if o[0] == to)
            speeds = edges[route[k]].get("speeds", ())
            return route[k], [i for i in lanes if i >= len(speeds) or speeds[i] >= CRAWL_MS] or lanes
        return None

    def keep_going(self):
        """On the route's last edge: a way on, so a drive by the person's word does not end by itself. Where there is none (the straight road), it arrives."""
        c, edges = self.conn, self.graph()
        if EGO not in c.vehicle.getIDList():
            return
        route = list(c.vehicle.getRoute(EGO))
        at = c.vehicle.getRouteIndex(EGO)
        if at < len(route) - 1 or not edges.get(route[-1], {}).get("next"):
            return
        c.vehicle.setRoute(EGO, route[at:] + _route_from(edges, route[-1], ROUTE_M)[1:])

    def follow_lane(self):
        """Too near an edge's end to change lane (lane_for_route had its time), on a lane that does not lead to the route's next edge: the route goes where the lane goes, where SUMO
        would hold the ego at the lane's end. → the edge the route changed on, or None."""
        c, edges = self.conn, self.graph()
        if EGO not in c.vehicle.getIDList() or c.vehicle.getLaneID(EGO).startswith(":"):
            return None
        route = list(c.vehicle.getRoute(EGO))
        at = c.vehicle.getRouteIndex(EGO)
        ways = edges.get(route[at], {}).get("ways", {}).get(c.vehicle.getLaneIndex(EGO))
        if at >= len(route) - 1 or not ways or route[at + 1] in ways or not self._late(edges[route[at]]):
            return None
        c.vehicle.setRoute(EGO, [route[at]] + _route_from(edges, sorted(ways)[0], ROUTE_M))
        return route[at]

    def _late(self, edge):
        """The ego is too near EDGE's end for a lane change."""
        c = self.conn
        return edge["length"] - c.vehicle.getLanePosition(EGO) <= 2.0 * c.vehicle.getSpeed(EGO) + LATE_M

    def lane_for_route(self):
        """The side towards a lane that continues the route, SUMO's reading of the connections down the route (getBestLanes' offset); None on a lane that does, in a junction, or too
        near the edge's end: no lane change at the stop line."""
        c, edges = self.conn, self.graph()
        lane = c.vehicle.getLaneID(EGO) if EGO in c.vehicle.getIDList() else ":"
        if lane.startswith(":"):
            return None
        off = next((b[3] for b in c.vehicle.getBestLanes(EGO) if b[0] == lane), 0)
        edge = edges.get(lane.rsplit("_", 1)[0])
        if not off or edge is None or self._late(edge):
            return None
        return "left" if off > 0 else "right"

    def lane_sides(self, edge, index):
        """The lanes beside lane INDEX of EDGE. → (the sides that are no lane to drive: a shoulder, or a lane that leads nowhere; the side towards a driving lane when this one is none)."""
        e = self.graph().get(edge) or {}
        speeds, ways = e.get("speeds", ()), e.get("ways", {})
        road = [i for i, v in enumerate(speeds) if v >= CRAWL_MS and (i in ways or not ways)]
        sides = {s for s, i in (("right", index - 1), ("left", index + 1)) if 0 <= i < len(speeds) and i not in road}
        if index in road or not road:
            return sides, None
        return sides, "left" if min(road, key=lambda i: abs(i - index)) > index else "right"

    # ── the person's hand on the traffic (the page's Traffic dock): what sumo-gui offers, and adding cars, which it does not (TraCI does) ──
    def add_cars(self, kind="aggr", n=1, ahead=False):
        """N cars of a planted style: on their own ways, or AHEAD of the ego on its route. → how many SUMO took."""
        c, took = self.conn, 0
        edges = self.graph()
        rng = random.Random(self.steps + self.added)
        for i in range(int(n)):
            self.added += 1
            vid, rid = "%s_h%d" % (kind, self.added), "hand%d" % self.added
            pos, lane = "random_free", "best"
            if ahead:
                way = list(c.vehicle.getRoute(EGO))[c.vehicle.getRouteIndex(EGO):]
                at = c.vehicle.getLanePosition(EGO) + 25.0 + 15.0 * i
                if c.vehicle.getLaneID(EGO).startswith(":"):      # in a junction: from the next edge's start
                    at = 5.0 + 15.0 * i
                pos = "%.1f" % min(at, edges[way[0]]["length"] - 1.0)
            else:
                way = _route_from(edges, rng.choice(sorted(edges)), ROUTE_M)
            c.route.add(rid, way)
            c.vehicle.add(vid, rid, typeID=kind, depart="now", departLane=lane, departPos=pos, departSpeed="max")
            took += 1
        return took

    def others(self):
        return [v for v in self.conn.vehicle.getIDList() if v != EGO]

    def clear_cars(self):
        gone = self.others()
        for v in gone:
            self.conn.vehicle.remove(v)
        return len(gone)

    def remove_car(self, vid):
        self.conn.vehicle.remove(vid)

    def stop_car(self, vid, stop=True):
        self.conn.vehicle.setSpeed(vid, 0.0 if stop else -1.0)    # -1: its own car-following again

    def scale(self, x):
        self.conn.simulation.setScale(float(x))

    def close_lane(self, lane):
        self.closed.setdefault(lane, self.conn.lane.getAllowed(lane))
        self.conn.lane.setDisallowed(lane, ["all"])

    def open_lanes(self):
        for lane, allowed in self.closed.items():
            self.conn.lane.setAllowed(lane, allowed)
        n, self.closed = len(self.closed), {}
        return n

    def lights_on(self, on):
        """Off: SUMO's own program `off`, the junction by right of way. On: the net's program."""
        for tl in self.conn.trafficlight.getIDList():
            self.conn.trafficlight.setProgram(tl, "0" if on else "off")

    def light_states(self):
        c = self.conn
        return {tl: {"phase": c.trafficlight.getPhase(tl), "programID": c.trafficlight.getProgram(tl)} for tl in c.trafficlight.getIDList()}

    def lights(self):
        c = self.conn
        return {tl: c.trafficlight.getRedYellowGreenState(tl) for tl in c.trafficlight.getIDList()}

    def control(self, accel=None, lane=None):
        """The restrictor's output for the next step: ACCEL (m/s², held one step) and LANE (the target lane index on
        the ego's edge: a change of LC_DURATION; None: no change)."""
        if not self.ego_seen or self.ego_done:
            return
        v = self.conn.vehicle
        if accel is not None:
            # the speed this step's acceleration gives. Not setAcceleration(a, dt): SUMO ramps it over the step after, and the car gets half of what was asked (asked -3 m/s² for 1 s: -1.5 m/s)
            v.setSpeed(EGO, max(0.0, v.getSpeed(EGO) + float(accel) * self.dt))
        if lane is not None and lane != v.getLaneIndex(EGO):
            v.changeLane(EGO, int(lane), LC_DURATION)
