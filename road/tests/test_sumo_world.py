"""The TraCI world and its perception (road-world s-e812715d step 4) without a simulator: a fake TraCI connection
for sumo_world, netconvert's straight for the perception (netconvert builds a net; no SUMO process runs)."""
import math
import os
import shutil
import sys
from types import SimpleNamespace

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "world"))
import sumo_world  # noqa: E402
from sumo_perceive import Perception, ego_route  # noqa: E402
from semantic_world import net as netmod, road  # noqa: E402
from semantic_world.sensing import Sensor  # noqa: E402

needs_netconvert = pytest.mark.skipif(shutil.which("netconvert") is None, reason="netconvert not installed")


class Dom:
    """A TraCI domain over a table {id: {field: value}} (the getters the world calls), recording the setters."""

    def __init__(self, rows, calls):
        self.rows, self.calls = rows, calls

    def getIDList(self):
        return list(self.rows)

    def __getattr__(self, name):
        if name.startswith("get"):
            key = name[3].lower() + name[4:]
            return lambda vid: self.rows[vid][key]
        if name.startswith(("set", "change")):
            return lambda *a: self.calls.append((name,) + a)
        raise AttributeError(name)


class FakeConn:
    def __init__(self, frames):
        self.frames, self.k, self.calls, self.closed = frames, -1, [], False
        self.vehicle = Dom({}, self.calls)
        self.person = Dom({}, self.calls)
        self.trafficlight = Dom({}, self.calls)
        self.simulation = SimpleNamespace(getCollisions=lambda: self.frames[self.k].get("collisions", []))

    def simulationStep(self):
        self.k += 1
        self.vehicle.rows = self.frames[self.k].get("vehicles", {})
        self.person.rows = self.frames[self.k].get("persons", {})

    def close(self):
        self.closed = True


class FakeTraci:
    def __init__(self, frames):
        self.conn, self.started = FakeConn(frames), None

    def start(self, cmd, label=None):
        self.started = (cmd, label)

    def getConnection(self, label):
        return self.conn


def car(x, y, angle=90.0, speed=10.0, lane="E_0", s=50.0, index=0, length=5.0, vclass="passenger", route=("E",)):
    return {"position": (x, y), "angle": angle, "length": length, "width": 1.8, "speed": speed, "laneID": lane,
            "lanePosition": s, "vehicleClass": vclass, "laneIndex": index, "typeID": "calm", "route": list(route)}


@needs_netconvert
def test_world_steps_poses_collisions_and_control(tmp_path):
    frames = [{"vehicles": {"calm_0": car(60, -1.6)}},
              {"vehicles": {"calm_0": car(61, -1.6), "ego": car(10, -1.6, speed=6.0, s=10.0)},
               "collisions": [SimpleNamespace(collider="ego", victim="calm_0", type="collision")]},
              {"vehicles": {"calm_0": car(62, -1.6)}}]
    tr = FakeTraci(frames)
    w = sumo_world.SumoWorld("straight", str(tmp_path), seed=2, traci=tr).start()
    cmd, label = tr.started
    assert cmd[0] == "sumo" and "--collision.action" in cmd and cmd[cmd.index("--step-length") + 1] == "0.1"
    assert cmd[cmd.index("--lanechange.duration") + 1] == "1.0" and label == "road-straight-2"
    routes = open(w.routes).read()
    departs = [float(x.split('depart="')[1].split('"')[0]) for x in routes.splitlines() if "<vehicle" in x]
    assert departs == sorted(departs) and 'id="ego"' in routes                   # SUMO's depart order
    assert w.step() is False and not w.ego_seen
    w.control(accel=-3.0, lane=1)                                                # no ego yet: nothing sent
    assert tr.conn.calls == []
    assert w.step() is True and w.ego_collisions == 1
    assert ("setSpeedMode", "ego", 0) in tr.conn.calls and ("setLaneChangeMode", "ego", 0) in tr.conn.calls
    t = w.truth()
    assert math.isclose(t["ego"]["x"], 7.5) and math.isclose(t["ego"]["heading"], 0.0, abs_tol=1e-9)   # front → centre
    assert t["ego"]["route"] == ["E"] and t["calm_0"]["vclass"] == "passenger"
    w.control(accel=-3.0, lane=1)
    assert ("setAcceleration", "ego", -3.0, 0.1) in tr.conn.calls
    assert ("changeLane", "ego", 1, sumo_world.LC_DURATION) in tr.conn.calls
    assert w.step() is False and w.ego_done
    w.close()
    assert tr.conn.closed


@pytest.fixture(scope="module")
def straight(tmp_path_factory):
    if shutil.which("netconvert") is None:
        pytest.skip("netconvert not installed")
    work = str(tmp_path_factory.mktemp("straight"))
    net, _ = sumo_world.straight(work, 1, n=2)
    return netmod.load_net(net).lanemap()


def pose(lm, lane, s, speed=10.0, vclass="passenger", length=5.0, route=("E",)):
    from semantic_world.sensing import point_at
    x, y = point_at(lm.lanes[lane].shape, s)
    return {"x": x, "y": y, "heading": 0.0, "length": length, "width": 1.8, "speed": speed, "lane": lane, "s": s,
            "vclass": vclass, "index": lm.lanes[lane].index, "route": list(route)}


def test_route_and_sighting_exact(straight):
    lm = straight
    assert ego_route(lm, "E_0", ["E"]) == ["E_0"]
    p = Perception(lm, Sensor(range=60.0), dt=0.1)
    truth = {"ego": pose(lm, "E_0", 100.0), "a": pose(lm, "E_0", 130.0, speed=8.0), "far": pose(lm, "E_1", 400.0)}
    movers, ego = p.step(truth)
    assert p.last["seen"] == ["a"] and len(movers) == 1                          # out of range: no track
    m = movers[0]
    assert (m.lane, m.s, m.length) == ("E_0", 130.0, 5.0) and m.dyn.vmax == 8.0  # the exact sighting, not the cell
    assert ego.route == ["E_0"] and ego.dyn.rho == 1.0


def test_occluded_track_worst_case_ahead(straight):
    lm = straight
    p = Perception(lm, Sensor(range=60.0), dt=0.1)
    # a car straight ahead, then a truck closer in front of the ego hides it: the hidden one is predicted and placed
    # at its support's near edge on the ego's way
    truth = {"ego": pose(lm, "E_0", 100.0, speed=0.0), "a": pose(lm, "E_0", 140.0, speed=0.0)}
    p.step(truth)
    truth["t"] = pose(lm, "E_0", 115.0, speed=0.0, length=12.0)
    movers, _ = p.step(truth)
    assert sorted(p.last["seen"]) == ["t"]                                       # a is behind the truck
    hidden = [m for m in movers if m.id != p.map.load()["_seen"][0]]
    assert len(hidden) == 1
    h = hidden[0]
    assert h.lane == "E_0" and 140.0 - road.BIN <= h.s <= 140.0                  # its front at the support's near edge
    sit_ids = {m.id for m in movers}
    assert len(sit_ids) == 2


def test_negative_evidence_clears_a_seen_empty_cell(straight):
    lm = straight
    p = Perception(lm, Sensor(range=60.0), dt=0.1)
    truth = {"ego": pose(lm, "E_0", 100.0, speed=0.0), "a": pose(lm, "E_0", 130.0, speed=0.0)}
    p.step(truth)
    del truth["a"]                                                               # gone from where the ego can see
    movers, _ = p.step(truth)
    assert movers == []


def lane_car(lm, lane, s, speed, length=5.0, route=("E",)):
    """A fake TraCI row for a car at (LANE, S) of the straight (SUMO's position: the front bumper)."""
    from semantic_world.sensing import point_at
    x, y = point_at(lm.lanes[lane].shape, s)
    return car(x, y, speed=speed, lane=lane, s=s, index=lm.lanes[lane].index, length=length, route=route)


def test_loop_projects_the_belief_and_restricts(straight, tmp_path):
    import sumo_host
    lm = straight
    # the ego at 10 m/s closes on a stopped car 20 m ahead on its lane: dangerous at once; the planner's accel is
    # cut to the proper response's braking, and the latency is the first tick. Frame 0 is before the ego's depart
    frames = [{"vehicles": {"stop": lane_car(lm, "E_0", 125.0, 0.0)}}]
    s_e = 100.0
    for k in range(4):
        frames.append({"vehicles": {"ego": lane_car(lm, "E_0", s_e, 10.0), "stop": lane_car(lm, "E_0", 125.0, 0.0)}})
        s_e += 1.0
    tr = FakeTraci(frames)
    loop = sumo_host.Loop({"scenario": "straight", "seed": 1, "vehicles": 2}, str(tmp_path / "w"), traci=tr)
    assert loop.warmup == 1 and loop.tick == 0                                    # the episode begins with the ego in
    facts, roles, fold, _ = loop.observe()
    assert {"now", "type(lead,same_dir)", "dangerous(lead)", "resp_lon(brake_min)", "type(vru1,not_relevant)"} <= set(facts)
    assert roles["lead"] != "stop" and fold["resp_lon"] == "brake_min"             # a track's name, never the world's id
    loop.command(("accel", None), life=10)
    assert loop.step() is True
    acc = [c for c in tr.conn.calls if c[0] == "setAcceleration"]
    assert acc and acc[0][2] == -4.0                                             # accel capped at −brake_min
    assert loop.restricted == 1 and loop.latency == [1] and loop.violations == [] and loop.life == 9
    assert loop.log[-1]["resp"] == "brake_min" and loop.log[-1]["cmd"] == ["accel", None]
    sm = loop.summary()
    assert sm["collisions"] == 0 and sm["ticks"] == 1 and set(sm["ms"]) >= {"perceive", "project"}
    loop.close()
