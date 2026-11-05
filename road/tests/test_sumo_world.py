"""The TraCI world and its perception (road-world s-e812715d step 4) without a simulator: a fake TraCI connection
for sumo_world, netconvert's straight for the perception (netconvert builds a net; no SUMO process runs)."""
import json
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
        if name.startswith(("set", "change", "moveTo")):
            return lambda *a, **kw: self.calls.append((name,) + a + ((kw,) if kw else ()))
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
    speeds = [c for c in tr.conn.calls if c[0] == "setSpeed" and c[1] == "ego"]
    assert speeds and math.isclose(speeds[-1][2], max(0.0, t["ego"]["speed"] - 0.3))      # the speed -3 m/s² gives in one step
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
    assert {"now", "type(lead,same_dir)", "dangerous(lead)", "resp_lon(brake_min)", "role_empty(vru1)"} <= set(facts)   # no walker: role_empty, no filler (spec 20 §2)
    assert roles["lead"] != "stop" and fold["resp_lon"] == "brake_min"             # a track's name, never the world's id
    loop.command(("accel", None), life=10)
    assert loop.step() is True
    assert loop.log[-1]["a"] == -4.0                                             # accel capped at −brake_min
    assert [c for c in tr.conn.calls if c[0] == "setSpeed"]                      # and given as the speed it makes
    assert loop.restricted == 1 and loop.latency == [1] and loop.violations == [] and loop.life == 9
    assert loop.log[-1]["resp"] == "brake_min" and loop.log[-1]["cmd"] == ["accel", None]
    seen, real = loop.log[-1]["danger"][0], loop.log[-1]["truth"][0]              # the pair the brake answers: as believed, as it is
    assert seen["role"] == "lead" and seen["resp"] == "brake_min" and seen["id"].split(":")[0] == roles["lead"]
    assert real["id"].startswith("stop:") and (real["lane"], real["s"], real["v"]) == ("E_0", 125.0, 0.0) and len(real["rho"]) == 2
    assert loop.level_dest == 950.0 and not loop.arrived()
    loop.proj["ego"].s = 951.0
    assert loop.arrived()                                                        # s at dest, still in the net
    sm = loop.summary()
    assert sm["collisions"] == 0 and sm["ticks"] == 1 and set(sm["ms"]) >= {"perceive", "project"}
    loop.close()


def test_what_a_car_shows_its_indicator_and_its_lane_change(straight):
    """road-2 item 2: a seen track's indicator (latched over the blink: SIGNAL_TICKS) and its lane change seen
    complete (the lane changed, the lane offset within SETTLED_LAT: settled to that side for SETTLED_TICKS); observed
    facts, never an intent belief."""
    import sumo_perceive as SP
    lm = straight
    p = Perception(lm, Sensor(range=60.0), dt=0.1)
    def step(lane, s, signals=0, lat=0.0):
        a = dict(pose(lm, lane, s, speed=8.0), signals=signals, lat=lat)
        movers, _ = p.step({"ego": pose(lm, "E_0", 100.0), "a": a})
        return movers[0]
    m = step("E_0", 130.0)
    assert m.signal is None and m.settled is None
    m = step("E_0", 131.0, signals=SP.__dict__.get("BLINKER_LEFT", 2))
    assert m.signal == "left"
    m = step("E_0", 132.0, signals=0)                    # the blink's dark half: still signalled
    assert m.signal == "left"
    for k in range(SP.SIGNAL_TICKS):
        m = step("E_0", 133.0 + k)
    assert m.signal is None                              # dark for a second: no longer
    m = step("E_1", 145.0, lat=-1.2)                     # the lane switched, the car still off the centre
    assert m.settled is None
    m = step("E_1", 146.0, lat=0.1)                      # centred: the change is complete, to the left
    assert m.settled == "left" and m.lane == "E_1"
    for k in range(SP.SETTLED_TICKS):
        m = step("E_1", 147.0 + k)
    assert m.settled is None


def test_travel_is_no_lane_change(straight, monkeypatch):
    """Seed 2's lie: a track seen on another edge, or back from an earlier sighting, is not a car that changed lanes."""
    lm = straight
    p = Perception(lm, Sensor(range=60.0), dt=0.1)
    def step(lane, s):
        movers, _ = p.step({"ego": pose(lm, "E_0", 100.0), "a": dict(pose(lm, lane, s, speed=8.0), signals=0, lat=0.0)})
        return movers[0]
    step("E_0", 130.0)
    monkeypatch.setattr(lm.lanes["E_1"], "edge", "another")
    for k in range(3):
        assert step("E_1", 131.0 + k).settled is None
    monkeypatch.undo()
    assert step("E_1", 134.0).settled is None                       # no change yet: it is on that lane already
    assert step("E_0", 135.0).settled is None                       # the change, seen once
    assert step("E_0", 136.0).settled == "right"                    # and a second time: complete


def test_no_responder_brake_without_a_dangerous_pair(straight, tmp_path):
    """road-2 (the ruling): on the straight, a responder brake (brake_min) is applied only with a dangerous pair in the
    fold it was decided on — the summary's undue_brakes counts the others (0 by construction); and the run card
    prints the RSS parameters every pair used."""
    import sumo_host
    lm = straight
    frames = [{"vehicles": {"stop": lane_car(lm, "E_0", 125.0, 0.0)}}]
    s_e = 100.0
    for k in range(4):
        frames.append({"vehicles": {"ego": lane_car(lm, "E_0", s_e, 10.0), "stop": lane_car(lm, "E_0", 125.0, 0.0)}})
        s_e += 1.0
    loop = sumo_host.Loop({"scenario": "straight", "seed": 1, "vehicles": 2}, str(tmp_path / "w"), traci=FakeTraci(frames))
    assert loop.proj["fold"]["dangerous"]                                          # the stopped car: dangerous
    loop.command(("brake", "brake_min"), life=5)
    loop.step()
    assert loop.undue == []                                                        # braked with a dangerous pair
    loop.proj["fold"] = {"resp_lon": "none", "dangerous": []}                      # a fold with nothing dangerous
    loop.command(("brake", "brake_min"), life=5)
    loop.step()
    sm = loop.summary()
    assert sm["undue_brakes"] == 1                                                 # ... a brake there is counted
    card = sm["rss"]
    assert card["ego_rho"] > 0 and {"rho", "brake_min", "brake_max", "min_dist"} <= set(card["classes"]["passenger"])
    loop.close()


def test_the_run_doctor_refuses_a_world_that_is_not_the_one_meant(tmp_path):
    """T9 (checks-open s-17e557f0; Check the world first): the script acts on a vehicle the routes lack, or the routes lack the ego."""
    routes = tmp_path / "r.rou.xml"
    routes.write_text('<routes><vehicle id="ego" route="r" depart="0"/><vehicle id="lead" route="r" depart="0"/></routes>')
    assert sumo_world.doctor(str(routes), [(1.0, "lead", "lcmode", 0)]) == []
    assert sumo_world.doctor(str(routes), [(1.0, "car9", "lcmode", 0)]) == ["the script names car9, which the routes lack"]
    routes.write_text('<routes><vehicle id="lead" route="r" depart="0"/></routes>')
    assert sumo_world.doctor(str(routes), []) == ["the routes lack the ego (ego)"]


@needs_netconvert
def test_every_scenario_at_head_is_the_world_it_says(tmp_path):
    for name in ("straight", "cut_out", "cut_in"):
        (tmp_path / name).mkdir()
        made = sumo_world.SCENARIOS[name](str(tmp_path / name), 1)
        assert sumo_world.doctor(made[1], made[2] if len(made) > 2 else []) == [], name



def test_a_collision_is_bodies_touching():
    """CARLA's CollisionTest counts physical contact; SUMO by default counts a gap under the follower's minGap (2.5 m when the
    vType names none) as a collision (--collision.mingap-factor 1): ParkingCutIn #19/#95/#96 read 2.4 m gaps as contacts. The
    world's command line sets the factor 0 (the architect's ruling, road-scenarios s-e23be780)."""
    cmd = sumo_world.SumoWorld.cmd(SimpleNamespace(sumo="sumo", net="n", routes="r", dt=0.1, seed=1))
    i = cmd.index("--collision.mingap-factor")
    assert cmd[i + 1] == "0" and "--collision.check-junctions" in cmd


def test_the_carry_moves_the_body_through_the_opposite_lane_and_back():
    """The pass through the opposite lane (668e45, road-gap-sumo): the body moved over in LC_DURATION, carried along its route
    lane at the commanded speed, SUMO's position its front on the route lane's side and its rear (facing the opposite lane's
    way) past half the way; the truth on the opposite lane in that lane's s; the odometer the route lane's metres; back home
    the body is set on its lane and the route SUMO replaced restored at the next step."""
    w = sumo_world.SumoWorld.__new__(sumo_world.SumoWorld)
    w.dt, w.carry, w._restore, w.odo_fix, w.ego_seen, w.ego_done = 0.1, None, None, 0.0, True, False
    calls = []
    ego = dict(car(50.0, 0.0, speed=10.0, lane="E_0", s=50.0, route=("E", "F")), roadID="E", distance=50.0)
    w.conn = SimpleNamespace(vehicle=Dom({"ego": ego}, calls), lane=SimpleNamespace(
        getShape=lambda l: [(0.0, 0.0), (200.0, 0.0)], getLength=lambda l: 200.0, getWidth=lambda l: 3.2))
    w.carry_start("W_0")
    assert w.carry_side() == "home" and w.ego_distance() == 50.0
    for _ in range(10):                                            # one LC_DURATION: over, at 10 m/s
        w.control(accel=0.0)
    k = w.carry
    assert w.carry_side() == "opp" and math.isclose(k["lat"], 3.2) and math.isclose(k["s"], 60.0)
    mv = [c for c in calls if c[0] == "moveToXY"]
    assert len(mv) == 10
    first, last = mv[0], mv[-1]
    assert math.isclose(first[4], 51.0) and math.isclose(first[5], 0.32) and math.isclose(first[-1]["angle"], 90.0)
    assert math.isclose(last[4], 55.0) and math.isclose(last[5], 3.2)      # the rear (60 - 5), a lane width over,
    assert math.isclose(last[-1]["angle"], 270.0) and last[-1]["keepRoute"] == 2   # facing the opposite lane's way
    p = w.carried_pose(dict(ego))
    assert p["lane"] == "W_0" and math.isclose(p["s"], 140.0) and math.isclose(p["x"], 57.5) and math.isclose(p["speed"], 10.0)
    assert p["route"] == ["E", "F"] and p["carry"] == {"home": "E_0", "s": k["s"]}
    assert math.isclose(w.ego_distance(), 60.0)
    w.carry_back()
    for _ in range(10):
        w.control(accel=0.0)
    assert w.carry is None and w._restore[0] == ["E", "F"] and math.isclose(w._restore[2], 70.0)
    back = [c for c in calls if c[0] == "moveToXY"][-1]
    assert math.isclose(back[4], 70.0) and math.isclose(back[5], 0.0) and math.isclose(back[-1]["angle"], 90.0)


def test_along_and_beside():
    shape = [(0.0, 0.0), (10.0, 0.0), (10.0, 10.0)]
    assert sumo_world.along(shape, 15.0) == (10.0, 5.0, math.pi / 2)
    x, y, h = sumo_world.beside(shape, 5.0, 2.0)
    assert (x, y) == (5.0, 2.0) and sumo_world.sumo_angle(h) == 90.0
    assert sumo_world.along(shape, 99.0)[:2] == (10.0, 10.0)


def test_the_truth_row_holds_the_bodies_in_range_and_the_role_each_is_bound_to():
    """The truth column (spec 20 §10.2, cr-harvest s-f4e297da): the ego's lane, kind and contacts; the bodies within the sensor
    range with their world class, `as` obj, the role of the track the projection bound on their lane (null when unbound)."""
    import sumo_host
    from semantic_world.lane import Lane, LaneMap, Mover
    loop = sumo_host.Loop.__new__(sumo_host.Loop)
    loop.lanemap = LaneMap([Lane("E_0", 300.0, kind="driving"), Lane("W_0", 300.0)])
    loop.perc = SimpleNamespace(sensor=SimpleNamespace(range=100.0))
    loop.world = SimpleNamespace(carry=None)
    loop.log = [{"contact": [{"id": "lead", "type": "same_dir"}]}]

    def body(x, lane, s, v, vclass="passenger"):
        return {"x": x, "y": 0.0, "lane": lane, "s": s, "speed": v, "vclass": vclass, "length": 4.5}
    loop.prev_truth = {"ego": body(50.0, "E_0", 50.0, 10.0), "lead": body(70.0, "E_0", 70.0, 5.0),
                       "bike": body(90.0, "W_0", 210.0, 4.0, "bicycle"), "far": body(400.0, "E_0", 290.0, 9.0)}
    loop.proj = {"ego": Mover("ego", "E_0", 50.0), "binding": {"lead": "passenger_1"}}
    loop.last_movers = [Mover("passenger_1", "E_0", 68.0)]                       # the track, 2 m off its body
    r = loop.truth_row()
    assert r["ego"] == {"lane": "E_0", "s": 50.0, "v": 10.0, "kind": "driving", "contact": ["lead"]}
    things = {t["id"]: t for t in r["things"]}
    assert set(things) == {"lead", "bike"}                                       # "far" is out of range
    assert things["lead"]["role"] == "lead" and things["lead"]["as"] == "obj" and things["lead"]["class"] == "passenger"
    assert things["bike"]["role"] is None and things["bike"]["class"] == "bicycle"


def test_the_truth_column_is_written_beside_the_trace_with_its_header(tmp_path):
    import road_host
    h = road_host.RoadHost.__new__(road_host.RoadHost)
    h.run, h.shared = {"trace": str(tmp_path / "tr")}, {"k": 7}
    h.road = SimpleNamespace(truth_row=lambda: {"ego": {"lane": "E_0"}, "things": []})
    h.truth_out()
    h.shared["k"] = 8
    h.truth_out()
    lines = [json.loads(x) for x in (tmp_path / "tr" / "truth.jsonl").read_text().splitlines()]
    assert lines[0]["truth"] == 1 and "cannot" in lines[0] and [x["k"] for x in lines[1:]] == [7, 8]
    h.road = SimpleNamespace()                                                    # the exerciser: no truth kept
    h.truth_out()
    assert len((tmp_path / "tr" / "truth.jsonl").read_text().splitlines()) == 3
