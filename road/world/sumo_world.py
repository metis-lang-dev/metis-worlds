"""sumo_world.py — the road's TRUTH (road-world s-e812715d step 4, the framework brief's L0): one SUMO process driven
over TraCI, headless, at the responder's step (0.1 s), the ego under the stack's control with SUMO's own safety off.

- The net and the routes: a scenario writes them into a work directory (`straight`: the old harness's 1 km two-lane
  road with its planted calm / aggr vTypes, the ego behind the traffic and faster than the calm cap, so it must
  brake or change lanes; more scenarios join as the cases need them). Every vehicle in depart order (SUMO drops an
  out-of-order one silently).
- The ego: speed mode 0 and lane-change mode 0 (no SUMO safety, no strategic changes: the RSS stack is what is under
  test, and a TraCI change is done as asked); its acceleration set each step (setAcceleration for one step), a lane
  change through changeLane with SUMO's continuous change of `LC_DURATION` s.
- The truth per step: every vehicle and person as a pose (the centre: SUMO's position is the front bumper), its
  lane and s, speed, vClass, length and width; the collisions the step had (SUMO's own check, junctions included,
  `warn`: nobody is removed) and whether the ego was in one.

    w = SumoWorld(scenario, work, seed); w.start(); w.step(); w.truth() · w.ego() · w.control(accel, lane) · w.close()

The TraCI module is injected (`traci=`) so the tests run without a simulator; the default imports the system's."""
import math
import os
import random
import subprocess
import sys

DT = 0.1
EGO = "ego"
LC_DURATION = 1.0              # a lane change takes 1 s (the restrictor's contract, step 2)
EDGE_M, LANES = 1000.0, 2
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


def straight(work, seed, n=40):
    """The straight: a 1 km road of LANES lanes at 15 m/s, N vehicles of the planted styles (a seeded draw) a 0.9 s
    apart on random lanes and speeds, the ego (aggr, 6 m/s, lane 0) at 8 s behind them. → (net, routes)."""
    net = os.path.join(work, "straight.net.xml")
    if not os.path.exists(net):
        nod, edg = os.path.join(work, "straight.nod.xml"), os.path.join(work, "straight.edg.xml")
        with open(nod, "w") as f:
            f.write('<nodes><node id="a" x="0" y="0"/><node id="b" x="%g" y="0"/></nodes>' % EDGE_M)
        with open(edg, "w") as f:
            f.write('<edges><edge id="E" from="a" to="b" numLanes="%d" speed="15"/></edges>' % LANES)
        subprocess.run(["netconvert", "-n", nod, "-e", edg, "-o", net], check=True, capture_output=True)
    rng = random.Random(seed)
    rows = [(8.0, '<vehicle id="%s" type="aggr" route="r" depart="8.0" departLane="0" departPos="0" departSpeed="6"/>' % EGO)]
    for i in range(n):
        vt = "calm" if rng.random() < 0.5 else "aggr"
        rows.append((i * 0.9, '<vehicle id="%s_%d" type="%s" route="r" depart="%.1f" departLane="random" departSpeed="random"/>'
                     % (vt, i, vt, i * 0.9)))
    lines = ["<routes>"]
    lines += ['<vType id="%s" accel="%s" decel="%s" sigma="%s" maxSpeed="%s" tau="%s" color="%s"/>'
              % (k, p["accel"], p["decel"], p["sigma"], p["maxSpeed"], p["tau"], p["color"]) for k, p in VTYPES.items()]
    lines.append('<route id="r" edges="E"/>')
    lines += [x for _, x in sorted(rows, key=lambda r: r[0])]
    lines.append("</routes>")
    routes = os.path.join(work, "straight_%d.rou.xml" % seed)
    with open(routes, "w") as f:
        f.write("\n".join(lines))
    return net, routes


SCENARIOS = {"straight": straight}
DESTS = {"straight": 950.0}       # the ego's destination (s on its lane), short of the net's end: arrived
                                  # while it is still in the net (TraCI drops a vehicle that leaves)


class SumoWorld:
    def __init__(self, scenario, work, seed=1, dt=DT, traci=None, label=None, sumo="sumo", **kw):
        os.makedirs(work, exist_ok=True)
        self.net, self.routes = SCENARIOS[scenario](work, seed, **kw)
        self.seed, self.dt, self.sumo = int(seed), float(dt), sumo
        self.traci = traci or load_traci()
        self.label = label or "road-%s-%d" % (scenario, seed)
        self.t, self.steps, self.collisions, self.ego_collisions = 0.0, 0, [], 0
        self.ego_seen = self.ego_done = False
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
        return {"x": x, "y": y, "heading": h, "length": length, "width": width, "speed": dom.getSpeed(vid),
                "lane": dom.getLaneID(vid), "s": dom.getLanePosition(vid)}

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
            v.setAcceleration(EGO, float(accel), self.dt)
        if lane is not None and lane != v.getLaneIndex(EGO):
            v.changeLane(EGO, int(lane), LC_DURATION)
