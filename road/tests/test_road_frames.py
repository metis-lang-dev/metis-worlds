"""The road page's frames and the responder host's page faces (road-agent s-357becc7 step 1): road_frames over a Loop's readings, the world lines,
the pace, the next run. No SUMO runs here."""
import json
import os
import sys
from types import SimpleNamespace

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "world"))
import road_frames  # noqa: E402
import road_host  # noqa: E402
import road_wishes as W  # noqa: E402

NET = """<net version="1.16"><location netOffset="0,0" convBoundary="0.00,0.00,1000.00,0.00" origBoundary="0,0,1000,0" projParameter="!"/>
<edge id="E" from="a" to="b"><lane id="E_0" index="0" speed="15.00" length="1000.00" shape="0.00,-4.80 1000.00,-4.80"/>
<lane id="E_1" index="1" speed="15.00" length="1000.00" shape="0.00,-1.60 1000.00,-1.60"/></edge>
<junction id="a" type="dead_end" x="0" y="0" shape="0,0 0,-6.4"/><junction id="b" type="dead_end" x="1000" y="0" shape="1000,0 1000,-6.4"/></net>"""
EGO = {"x": 20.0, "y": -4.8, "heading": 0.0, "lane": "E_0", "s": 20.0, "speed": 6.0, "vclass": "passenger", "type": "aggr", "length": 5.0, "width": 1.8, "signals": 0, "route": ["E"]}


def loop(path):
    return SimpleNamespace(world=SimpleNamespace(net=str(path), ego_collisions=0), prev_truth={"ego": EGO, "lead": dict(EGO, x=60.0, s=60.0, type="calm")}, ego_id="ego", level_dest=950.0,
                           scenario="straight", seed=3, tick=7, t=0.7, restricted=2, log=[{"cmd": ["accel", None], "a": 1.5, "seen": 1, "tracks": 1}],
                           proj={"binding": {"lead": "lead"}, "fold": {"resp_lon": "brake_min", "resp_lat": "none", "dangerous": True}}, arrived=lambda: False,
                           violations=[], unseen_duty=[1, 2], optimistic=[1], ms=[{"restrict": 0.001, "sumo": 0.002, "perceive": 0.01, "project": 0.001, "account": 0.001, "vehicles": 3}],
                           summary=lambda: {"ticks": 7, "arrived": True, "ms": {"sumo": 1.0}, "first": [], "violations": 0})


@pytest.fixture
def net(tmp_path):
    p = tmp_path / "n.net.xml"
    p.write_text(NET)
    return p


def test_the_net_is_as_the_client_reads_it_and_its_ground_has_area(net):
    doc = road_frames.net_json(net)["net"]
    assert [e["id"] for e in doc["edge"]] == ["E"] and [la["id"] for la in doc["edge"][0]["lane"]] == ["E_0", "E_1"]
    assert doc["location"]["projParameter"] == "!" and len(doc["junction"]) == 2
    x0, y0, x1, y1 = (float(v) for v in doc["location"]["convBoundary"].split(","))
    assert x1 > x0 and y1 > y0                     # SUMO's order


def test_the_net_frame_has_the_lanes_and_the_way(net):
    f = road_frames.net_frame(loop(net))
    assert f["ev"] == "world/net" and f["route"] == ["E"] and f["dest"] == 950.0 and f["scenario"] == "straight" and f["seed"] == 3
    assert f["lanes"][1] == {"id": "E_1", "index": 1, "speed": 15.0, "length": 1000.0}


def test_the_scene_has_the_truths_movers_and_the_beliefs_roles(net):
    f = road_frames.scene_frame(loop(net))
    assert f["ev"] == "world/scene" and f["ego"] == "ego" and [m["id"] for m in f["movers"]] == ["ego", "lead"]
    assert f["movers"][1]["class"] == "passenger" and f["movers"][1]["type"] == "calm" and f["movers"][1]["x"] == 60.0
    assert f["roles"] == {"lead": "lead"} and f["fold"] == {"resp_lon": "brake_min", "resp_lat": "none"} and f["cmd"] == ["accel", None] and f["a"] == 1.5
    assert f["violations"] == 0 and f["unseen_other_duty"] == 2 and f["optimistic"] == 1 and f["ms"] == 15.0


def test_the_summary_is_said_once_at_the_end(net):
    lp = loop(net)
    lp.arrived = lambda: True
    h = host(world=lp)
    h.beat = 10
    first = [f for f in h.frames() if f["ev"] == "world/summary"]
    assert first == [{"ev": "world/summary", "ticks": 7, "arrived": True, "violations": 0}]
    assert not [f for f in h.frames() if f["ev"] == "world/summary"]


def host(spec="responder", page=True, world=None):
    h = road_host.RoadHost.__new__(road_host.RoadHost)
    h.spec, h.steps, h.run = spec, spec == "responder", {"page": page, "scenario": "straight", "seed": 1, "world": "sumo", "key": "t"}
    h.road, h.shared, h.beat = world, {"world": world}, 1
    h.latched, h.latched_at, h.now_due = None, None, False
    return h


def test_no_page_no_lines_and_no_frames():
    h = host(page=False)
    assert h.frames() == []
    with pytest.raises(ValueError):
        h.world(["pause"])


def test_on_the_page_the_watch_sees_no_surprise():
    h = host()
    assert h.observe({"dangerous(lead)": 1}) == {"dangerous(lead)": 1}


def test_only_the_responders_host_says_the_frames(net):
    assert host("planner", world=loop(net)).frames() == []
    h = host(world=loop(net))
    h.world(["watching", "hello"])
    assert [f["ev"] for f in h.frames()] == ["world/net", "world/scene", "world/mark"]
    assert [f["ev"] for f in h.frames()] == ["world/scene"]        # the road once


def test_the_scene_comes_every_second_with_no_page_watching(net):
    h = host(world=loop(net))
    h.beat = 3
    assert h.frames() == []
    h.beat = 10
    assert [f["ev"] for f in h.frames()] == ["world/scene"]
    h.beat = 3
    h.world(["watching"])
    assert [f["ev"] for f in h.frames()] == ["world/scene"]


def test_the_page_says_pause_play_speed_and_the_next_run():
    h = host()
    h.world(["pause"])
    assert h.shared["paused"]
    h.world(["play", "speed:2"])
    assert not h.shared["paused"] and h.shared["speed"] == 2.0
    with pytest.raises(ValueError):
        h.world(["key:y"])


def test_paused_or_there_the_clock_is_held(net, monkeypatch):
    slept, stepped = [], []
    world = dict(arrived=lambda: False, step=lambda: stepped.append(1), tick=0, observe=lambda: ({}, {}, {}, []), log=[{}], proj={"ego": None})
    h = host(world=SimpleNamespace(**world))
    h.observed, h.period, h.beat = set(), 1, 5
    monkeypatch.setattr(road_host.time, "sleep", slept.append)
    h.world(["pause"])
    h.tick({})
    assert slept == [road_host.DT] and not stepped


def test_every_step_is_logged_with_or_without_a_page(tmp_path, monkeypatch):
    monkeypatch.setattr(road_host.time, "sleep", lambda s: None)
    for page in (True, False):
        path = tmp_path / ("log%s.jsonl" % page)
        world = SimpleNamespace(arrived=lambda: False, step=lambda: None, tick=0, observe=lambda: ({}, {}, {}, []), log=[{"tick": 1}])
        h = host(page=page, world=world)
        h.observed, h.period, h.beat = set(), 1, 5
        h.shared["log"] = str(path)
        h.tick({})
        assert path.read_text().strip() == '{"tick": 1}'


def test_a_new_run_opens_one_world_and_the_planner_gets_a_trip(monkeypatch):
    closed, made = [], []
    old = SimpleNamespace(close=lambda: closed.append(1), scenario="straight", seed=1, arrived=lambda: True, tick=0, observe=lambda: ({}, {}, {}, []), log=[{}], proj={"ego": None})

    def new_world(run):
        made.append(run)
        return SimpleNamespace(close=lambda: None, scenario=run["scenario"], seed=run["seed"], arrived=lambda: False, tick=0, observe=lambda: ({}, {}, {}, []), log=[{}], proj={"ego": None})
    monkeypatch.setattr(road_host, "new_world", new_world)
    a, b = host(world=old), host("planner", world=old)
    b.shared = a.shared
    a.observed = b.observed = set()
    a.period, b.period = 1, 10
    a.world(["pause", "run:cut_out:5"])
    assert closed == [1] and len(made) == 1 and made[0]["scenario"] == "cut_out" and made[0]["seed"] == 5 and not a.shared["paused"]
    assert b.road is old
    assert "+trip 1" in (b.tick({}) or [])
    assert b.road is a.shared["world"]
    assert "+trip 1" not in (b.tick({}) or [])                # once


def test_a_trip_still_held_is_not_doubled(monkeypatch):
    old = SimpleNamespace(close=lambda: None, arrived=lambda: False, tick=0, observe=lambda: ({}, {}, {}, []), log=[{}], proj={"ego": None})
    h = host("planner", world=old)
    h.observed, h.period = set(), 10
    h.shared["world"] = SimpleNamespace(arrived=lambda: False, tick=0, observe=lambda: ({}, {}, {}, []), log=[{}], proj={"ego": None})
    assert "+trip 1" not in (h.tick({"trip": 1}) or [])


def test_the_pace_holds_a_step_to_its_time(monkeypatch):
    h, clock, slept = host(), [100.0], []
    monkeypatch.setattr(road_host.time, "monotonic", lambda: clock[0])
    monkeypatch.setattr(road_host.time, "sleep", slept.append)
    h.shared["speed"] = 2.0
    h.pace()
    h.pace()
    assert slept == [pytest.approx(0.05)]
    clock[0] += 5.0                                # a slow step is not made up after
    h.pace()
    assert len(slept) == 1


FACTS = {"below_target": 1, "lead_ok": 1, "keep_ok": 1, "adjacent(left)": 1, "settled(left)": 1, "settled(right)": 1, "safe_long(leadleft)": 1, "safe_lat(leadleft)": 1,
         "safe_long(followleft)": 1, "safe_lat(followleft)": 1, "dangerous(lead)": 1}


def test_a_wish_only_gates_what_the_planner_already_reads():
    w = W.new()
    assert W.planner_facts(w, FACTS, 10.0) == FACTS
    W.take(w, "pace[P=easy]")
    assert W.pace_limit(w) == W.EASY_MS and W.pace_limit(W.new()) is None and W.planner_facts(w, FACTS, 10.0) == FACTS
    W.take(w, "resume")
    W.take(w, "lane[D=left]")
    f = W.planner_facts(w, FACTS, 10.0)
    assert f["change_reason(left)"] == 1 and "settled(left)" in f and "settled(right)" not in f and "change_reason(right)" not in f
    assert "lead_slow" not in f and f["below_target"] == 1 and f["lead_ok"] == 1    # a wish says nothing of the lead: it drives on while it waits
    assert f["dangerous(lead)"] == 1 and f["safe_long(leadleft)"] == 1  # the safety facts stand as the world has them
    W.take(w, "follow")
    f = W.planner_facts(w, FACTS, 10.0)
    assert "settled(left)" not in f and "settled(right)" not in f and "lead_slow" not in f


def test_a_lane_wish_is_met_or_dropped_with_its_reason():
    w = W.new()
    W.take(w, "lane[D=left]")
    W.planner_tick(w, dict(FACTS, **{"changing(left)": 1}))
    assert w["want"] is None and w["said"] == ["Changing lane now."]
    w = W.new()
    W.take(w, "lane[D=left]")
    unsafe = {k: v for k, v in FACTS.items() if k != "safe_long(followleft)"}
    for _ in range(W.WISH_TICKS):
        W.planner_tick(w, unsafe)
    assert w["want"] is None and w["said"] == ["Not now: a car is too close on the left. I have dropped it."]
    w = W.new()
    W.take(w, "lane[D=right]")
    assert W.why_not(FACTS, "right") == "there is no lane on the right"
    assert W.why_not(dict(FACTS, **{"zone_at(nextzone,near)": 1}), "left") == "too close to the junction"


def test_only_the_planner_reads_the_wish():
    world = SimpleNamespace(observe=lambda: (dict(FACTS), {}, {}, []), proj={"ego": None}, tick=0)
    for spec, seen in (("responder", True), ("planner", False)):
        h = host(spec, world=world)
        h.observed, h.period = set(), 1
        h.shared["wish"] = W.new()
        W.take(h.shared["wish"], "lane[D=left]")
        assert ("settled(right)" in h.fresh()) is seen


def test_a_person_marks_events_numbered_over_the_demo(tmp_path):
    world = SimpleNamespace(log=[{"lane": "E_0", "s": 1.0, "v": 2.0}], t=0.7, tick=7, arrived=lambda: False)
    h = host("responder", world=world)
    logged = []
    h._log = logged.append
    h.world(["mark:1:start:40"])
    assert h.shared["marks"] == {"n": 1, "open": True}
    with pytest.raises(ValueError, match="the next is event 1 stop"):
        h.world(["mark:2:start"])                                                     # the page's count is not the host's: said, and nothing moves
    h.world(["mark:1:stop:50", "mark:2:start:"])
    assert h.shared["marks"] == {"n": 2, "open": True}
    assert [(r["mark"], r["edge"], r["at_tick"], r["lane"]) for r in logged] == [(1, "start", 7, "E_0"), (1, "stop", 7, "E_0"), (2, "start", 7, "E_0")]
    assert not any("tick" in r for r in logged), "rulecheck takes a row with a tick for a tick row"
    h.shared.pop("mark_due")
    h.world(["hello"])                                                                 # a page reloaded: it hears where the count stands
    h.shared.pop("net_due")
    f = [x for x in h.frames() if x["ev"] == "world/mark"][0]
    assert f["n"] == 2 and f["open"] is True and "started, tick 7" in f["said"]


def test_around_says_the_roles():
    assert W.around({}, {"lead": "x", "followleft": "y"}) == "I see a car ahead, a car behind on the left."
    assert "too close" in W.around({"dangerous(lead)": 1}, {"lead": "x"})
    assert W.around({}, {}) == "I see no one near."


def test_a_town_gives_every_car_a_connected_way(tmp_path):
    """Town01's routes, seeded: the same seed the same routes, each way connected edge to edge, no sidewalk-only edge. No SUMO runs."""
    import xml.etree.ElementTree as ET
    import sumo_world as SW
    net, routes = SW.town(str(tmp_path), 1, n=5)
    edges = SW._town(net)
    root = ET.parse(routes).getroot()
    cars = root.findall("vehicle")
    assert len(cars) == 6 and sum(c.get("id") == SW.EGO for c in cars) == 1
    departs = [float(c.get("depart")) for c in cars]
    assert departs == sorted(departs)                       # SUMO drops an out-of-order one
    for c in cars:
        way = c.find("route").get("edges").split()
        assert all(b in edges[a]["next"] for a, b in zip(way, way[1:]))
    again = SW.town(str(tmp_path / "again"), 1, n=5)[1] if (tmp_path / "again").mkdir() is None else None
    assert open(again).read() == open(routes).read()


class FakeSumo:
    """What the Traffic dock calls of TraCI, and what it was told."""
    def __init__(self):
        self.calls = []
        self.vehicle, self.route, self.lane, self.trafficlight, self.simulation = self, self, self, self, self
    def __getattr__(self, name):
        def call(*a, **k):
            self.calls.append((name,) + a)
            return {"getIDList": ["ego", "calm_1"], "getRoute": ["E"], "getRouteIndex": 0, "getLanePosition": 10.0, "getLaneID": "E_0", "getAllowed": ["passenger"]}.get(name)
        return call


def traffic_host(tmp_path):
    import sumo_world as SW
    w = SW.SumoWorld.__new__(SW.SumoWorld)
    w.conn, w.net, w.steps, w.added, w.closed = FakeSumo(), str(tmp_path / "n.net.xml"), 0, 0, {}
    (tmp_path / "n.net.xml").write_text(NET)
    return host(world=SimpleNamespace(world=w, ego_id="ego")), w


def test_the_traffic_dock_adds_removes_and_says(tmp_path):
    h, w = traffic_host(tmp_path)
    said = lambda: h.shared["wish"]["said"]
    h.world(["traffic:ahead:calm:2"])
    adds = [c for c in w.conn.calls if c[0] == "add" and c[1].startswith("calm_h")]
    assert len(adds) == 2 and adds[0][1].startswith("calm_h") and said()[-1] == "Added 2 calm cars ahead of the ego."
    h.world(["traffic:add:aggr:1"])
    assert said()[-1] == "Added 1 aggr car."
    h.world(["traffic:clear"])
    assert ("remove", "calm_1") in w.conn.calls and ("remove", "ego") not in w.conn.calls
    h.world(["car:remove:ego"])
    assert ("remove", "ego") not in w.conn.calls and "stays" in said()[-1]
    h.world(["car:stop:calm_1", "car:go:calm_1"])
    assert ("setSpeed", "calm_1", 0.0) in w.conn.calls and ("setSpeed", "calm_1", -1.0) in w.conn.calls
    h.world(["traffic:scale:2"])
    assert ("setScale", 2.0) in w.conn.calls


def test_a_lane_closes_and_reopens_as_it_was(tmp_path):
    h, w = traffic_host(tmp_path)
    h.world(["lane:close:E_0", "lane:close:E_0", "lane:open"])
    assert ("setDisallowed", "E_0", ["all"]) in w.conn.calls and ("setAllowed", "E_0", ["passenger"]) in w.conn.calls and not w.closed


def test_lights_go_off_and_on_by_program(tmp_path):
    h, w = traffic_host(tmp_path)
    h.world(["lights:off", "lights:on"])
    assert ("setProgram", "ego", "off") in w.conn.calls and ("setProgram", "ego", "0") in w.conn.calls


def test_a_refused_line_is_said_and_the_run_goes_on(tmp_path):
    h, w = traffic_host(tmp_path)
    def refuse(*a):
        raise RuntimeError("no such vehicle")
    w.remove_car = refuse
    h.world(["car:remove:calm_9"])
    assert "no such vehicle" in h.shared["wish"]["said"][-1]


def test_every_town_is_a_scenario_with_its_lights_for_the_client():
    import sumo_world as SW
    assert {"straight", "Town01", "Town03"} <= set(SW.SCENARIOS)
    doc = road_frames.net_json(SW.os.path.join(SW.MAPS, "Town03.net.xml"))["net"]
    programs = {t["programID"] for t in doc["tlLogic"]}
    assert programs == {"0", "off"} and any("tl" in c for c in doc["connection"])


def test_a_towns_height_is_measured_from_its_lowest_point(net, tmp_path):
    high = tmp_path / "h.net.xml"
    high.write_text(NET.replace('shape="0.00,-4.80 1000.00,-4.80"', 'shape="0.00,-4.80,150.00 1000.00,-4.80,170.00"').replace('shape="0.00,-1.60 1000.00,-1.60"', 'shape="0.00,-1.60,150.00 1000.00,-1.60,170.00"'))
    assert road_frames.floor_of(str(net)) == 0.0 and road_frames.floor_of(str(high)) == 150.0
    assert road_frames.net_json(str(high))["net"]["edge"][0]["lane"][0]["shape"] == "0.00,-4.80,0.00 1000.00,-4.80,20.00"
    lp = loop(high)
    lp.prev_truth = {"ego": dict(EGO, z=160.0)}
    assert road_frames.scene_frame(lp)["movers"][0]["z"] == 10.0


def test_a_drawn_lane_keeps_its_bends_and_loses_the_rest():
    straight = " ".join("%d.00,0.00" % x for x in range(0, 101))
    assert road_frames.simpler(straight) == "0.00,0.00,0.00 100.00,0.00,0.00"
    bent = " ".join("%d.00,%.2f,%d.00" % (x, 5.0 if x == 50 else 0.0, 0) for x in range(0, 101))
    assert "50.00,5.00,0.00" in road_frames.simpler(bent)
    hill = " ".join("%d.00,0.00,%.2f" % (x, 3.0 if x == 50 else 0.0) for x in range(0, 101))
    assert "50.00,0.00,3.00" in road_frames.simpler(hill)


def test_the_lane_map_comes_back_from_its_cache(net, monkeypatch, tmp_path):
    import sumo_host
    monkeypatch.setattr(sumo_host, "CACHE", str(tmp_path / "cache"))
    first = sumo_host.lanemap_of(str(net))
    monkeypatch.setattr(sumo_host.netmod, "load_net", lambda p: 1 / 0)      # no rebuild
    second = sumo_host.lanemap_of(str(net))
    assert set(second.lanes) == set(first.lanes) and second is not first


def test_stop_is_the_planners_own_brake_and_go_takes_it_back():
    w = W.new()
    W.take(w, "stop")
    f = W.planner_facts(w, FACTS, 10.0)
    assert f["above_target"] == 1 and not {"below_target", "at_target", "lead_ok", "accel_ok"} & set(f) and f["dangerous(lead)"] == 1
    f = W.planner_facts(w, FACTS, 0.0)
    assert f["at_target"] == 1 and "above_target" not in f and f["keep_ok"] == 1       # it stands: the keep holds it
    W.take(w, "go")
    assert W.planner_facts(w, FACTS, 10.0) == FACTS


def test_a_turn_from_another_lane_asks_for_that_lane():
    w = W.new()
    w["turn"] = ("E", [0])
    W.turn_lanes(w, ("E", 1))
    assert w["want"] == "right"
    w = W.new()
    w["turn"] = ("E", [2, 3])
    W.turn_lanes(w, ("E", 0))
    assert w["want"] == "left"
    w = W.new()
    w["turn"] = ("E", [1])
    W.turn_lanes(w, ("E", 1))
    W.turn_lanes(w, ("F", 0))
    assert w["want"] is None


def test_there_is_no_lane_on_a_shoulder_and_the_wish_is_refused_at_once():
    w = W.new()
    W.take(w, "lane[D=right]")
    facts = W.without_sides({"adjacent(right)": 1, "settled(right)": 1, "adjacent(left)": 1}, {"right"})
    assert facts == {"adjacent(left)": 1}
    W.planner_tick(w, facts)
    assert w["want"] is None and w["said"][-1] == "Not now: there is no lane on the right. I have dropped it."


LANES = {"a": {"length": 50.0, "next": {"b", "c"}, "turns": {}, "ways": {1: {"b"}, 2: {"c"}}, "speeds": [1.39, 13.89, 13.89, 1.39]},
         "b": {"length": 50.0, "next": set(), "turns": {}, "ways": {}, "speeds": [13.89]}, "c": {"length": 50.0, "next": set(), "turns": {}, "ways": {}, "speeds": [13.89]}}


def test_the_lanes_beside_read_shoulders_and_the_way_back():
    import sumo_world as SW
    w = SW.SumoWorld.__new__(SW.SumoWorld)
    w._graph = LANES
    assert w.lane_sides("a", 1) == ({"right"}, None)
    assert w.lane_sides("a", 2) == ({"left"}, None)
    assert w.lane_sides("a", 0) == (set(), "left")
    assert w.lane_sides("a", 3) == (set(), "right")
    assert w.lane_sides(":j_0", 0) == (set(), None)


def lane_host(tmp_path, s, v=14.0, index=1, route=("a", "c")):
    h, w = traffic_host(tmp_path)
    w._graph = LANES
    x = w.conn.vehicle
    x.getIDList, x.getLaneID, x.getLaneIndex, x.getLanePosition, x.getSpeed = lambda: ["ego"], lambda e: "a_%d" % index, lambda e: index, lambda e: s, lambda e: v
    x.getRoute, x.getRouteIndex = lambda e: list(route), lambda e: 0
    return h, w


def test_near_the_lanes_end_the_route_goes_where_the_lane_goes(tmp_path):
    import sumo_world as SW
    _, w = lane_host(tmp_path, 10.0)                # far yet: a lane change may still come
    assert w.follow_lane() is None and not [c for c in w.conn.calls if c[0] == "setRoute"]
    _, w = lane_host(tmp_path, 30.0)                # 20 m left at 14 m/s
    assert w.follow_lane() == "a" and ("setRoute", SW.EGO, ["a", "b"]) in w.conn.calls
    _, w = lane_host(tmp_path, 30.0, index=2)       # this lane leads where the route goes
    assert w.follow_lane() is None


def test_the_host_asks_quietly_for_the_lane_that_continues_the_route(tmp_path):
    _, world = lane_host(tmp_path, 5.0)
    world.conn.vehicle.getBestLanes = lambda e: [("a_1", 50.0, 0.0, 1, True, ()), ("a_2", 90.0, 0.0, 0, True, ())]
    assert world.lane_for_route() == "left"
    world.conn.vehicle.getLanePosition = lambda e: 30.0      # too near the end: no change at the stop line
    assert world.lane_for_route() is None
    w = W.new()
    W.route_lane(w, "a", "left")
    assert w["want"] == "left" and w["quiet"]
    W.planner_tick(w, {"changing(left)": 1})
    assert w["want"] is None and w["said"] == []
    W.route_lane(w, "a", None)
    W.planner_tick(w, {})
    assert w["said"] == []


def test_the_person_chooses_the_lane_on_this_edge(tmp_path):
    w = W.new()
    W.take(w, "lane[D=right]")
    W.route_lane(w, "a", "left")
    assert w["want"] == "right" and not w["quiet"]
    w["want"] = None
    W.route_lane(w, "a", "left")            # the host does not undo it here
    assert w["want"] is None
    W.route_lane(w, "b", "left")
    assert w["want"] == "left"


def test_a_turn_missed_for_the_lane_is_said(tmp_path):
    h, _ = lane_host(tmp_path, 30.0)
    wish = h.shared.setdefault("wish", W.new())
    wish.update(turn=("a", [2]), want="left")
    h.follow_lane()
    assert wish["turn"] is None and wish["want"] is None and "could not get over" in wish["said"][-1]


def test_the_drive_dock_says_what_the_words_say(tmp_path):
    h, w = traffic_host(tmp_path)
    h.world(["drive:stop"])
    assert h.shared["wish"]["stop"] and h.shared["wish"]["said"][-1] == "Stopping."
    h.world(["drive:go", "drive:pace:easy", "drive:lane:left"])
    assert not h.shared["wish"]["stop"] and h.shared["wish"]["pace"] == "easy" and h.shared["wish"]["want"] == "left"


def test_a_turn_changes_the_egos_route_or_says_there_is_none(tmp_path):
    import sumo_world as SW
    edges = {"a": {"length": 50.0, "next": {"b", "c"}, "turns": {"right": [("b", 0)], "straight": [("c", 1), ("c", 2)]}}, "b": {"length": 50.0, "next": set(), "turns": {}},
             "c": {"length": 50.0, "next": set(), "turns": {}}}
    h, w = traffic_host(tmp_path)
    w._graph = edges
    w.conn.vehicle.getRoute = lambda e: ["a", "c"]
    w.conn.vehicle.getRouteIndex = lambda e: 0
    w.conn.vehicle.getLaneID = lambda e: "a_0"
    assert w.turn("right") == ("a", [0]) and ("setRoute", SW.EGO, ["a", "b"]) in w.conn.calls
    assert w.turn("straight") == ("a", [1, 2])
    assert w.turn("left") is None
    h.wish("turn[D=left]")
    assert h.shared["wish"]["said"][-1] == "There is no way left ahead."


def test_rulecheck_sorts_a_violation_by_why_it_is_one():
    sys.path.insert(0, os.path.join(os.path.dirname(HERE), "tools"))
    import rulecheck
    car = {"id": "c:xing_ego_prio:1", "role": "a1", "resp": "brake_min", "lane": "-18_0", "s": 40.98}
    row = lambda v=16.0, a=0.0, cmd=("keep", None), truth=(car,), danger=(): {"tick": 1, "v": v, "a": a, "cmd": list(cmd), "truth": list(truth), "danger": list(danger), "zone": "near"}
    assert [x[0]["tick"] for x in rulecheck.violations([row(), row()])] == [1]
    assert not rulecheck.violations([row(), row(a=-4.0)])                         # at the bound: none
    assert not rulecheck.violations([row(v=0.0), row(v=0.0)])                     # at rest: a standing car meets any brake
    assert rulecheck.sort_row(row(), row(), ["resp_lon(none)"])[0] == 2           # the belief has no such pair
    assert rulecheck.sort_row(row(), row(), ["resp_lon(brake_min)"])[0] == 3
    side = {"id": "c:xing_ego_prio:z", "resp": "brake_min", "lane": "x", "s": 1.0}
    hidden = dict(row(truth=(side,)), seen_ids=[])
    assert rulecheck.sort_row(hidden, row(), ["resp_lon(none)"])[0] == 6                                     # the other's duty, as account counts it
    assert rulecheck.sort_row(dict(hidden, seen_ids=["c"]), row(), ["resp_lon(none)"])[0] == 2               # seen: the ego's
    obj = dict(side, id="c:xing_obj_prio:z")
    assert rulecheck.sort_row(dict(row(truth=(obj,)), seen_ids=[]), row(), ["resp_lon(none)"])[0] == 2       # the way is not the ego's: the ego's
    assert rulecheck.sort_row(row(truth=(side,)), row(), ["resp_lon(none)"])[0] == 2                         # a log without the field: as it was
    seen = row(danger=(car,))
    assert rulecheck.sort_row(seen, row(), ["resp_lon(none)"])[0] == 5            # dangerous, no response, no release
    settled = ["resp_lon(none)", "settled_to(a1,right)"]
    assert rulecheck.sort_row(seen, row(), settled, [row()])[0] == 2              # the truth saw it hold its lane: the release is a lie
    assert rulecheck.sort_row(seen, row(), settled)[0] == 1                       # no row saw it: the release stands unjudged
    moved = dict(car, lane="-18_1")
    assert rulecheck.sort_row(seen, row(), settled, [row(truth=(moved,))])[0] == 1
    with open(os.path.join(HERE, "sort_seed2.jsonl")) as f:
        rows = [json.loads(line) for line in f]
    assert rows[-1]["violations"] == 37 and rows[-1]["by_class"]["projection"] == 37 and all(r["class"] == 2 for r in rows[:-1])


def test_the_rule_check_counts_a_short_log():
    sys.path.insert(0, os.path.join(os.path.dirname(HERE), "tools"))
    import rulecheck
    with open(os.path.join(HERE, "rulecheck_log.jsonl")) as f:
        runs = rulecheck.runs_of([json.loads(line) for line in f])
    got = rulecheck.check(runs[0], rulecheck.read_net(os.path.join(os.path.dirname(HERE), "maps", "Town03.net.xml")))
    assert len(runs) == 1 and got["ticks"] == 120 and got["stood"] == 0 and got["change_in_junction"] == 0 and got["abrupt"] == []
    assert got["change_at_line"] == [] and got["signal_entries"] + got["minor_entries"] >= 1


def test_the_lifted_sort_reproduces_seed2_class_for_class():
    """metis.trace sort (checks-open s-17e557f0) on Town01 seed 2's log and trace as committed: sort_seed2.jsonl, row for row."""
    pytest.importorskip("metis.trace")
    from metis import trace
    if not hasattr(trace, "sort"):
        pytest.skip("metispy before metis.trace sort: this CI's sibling at its head, until it merges")
    sys.path.insert(0, os.path.join(os.path.dirname(HERE), "tools"))
    import rulecheck
    fx = os.path.join(HERE, "fixtures", "sort-town01-2")
    rows = rulecheck.sort_rows(os.path.join(fx, "log.jsonl"), os.path.join(fx, "trace"))
    with open(os.path.join(HERE, "sort_seed2.jsonl")) as f:
        want = [json.loads(line) for line in f]
    got = trace.sort_summary(rows)                 # the file predates class 6: its five counts, and none in the sixth
    assert rows == want[:-1] and got["violations"] == want[-1]["violations"]
    assert {k: got["by_class"][k] for k in want[-1]["by_class"]} == want[-1]["by_class"] and got["by_class"]["unseen, the other's duty"] == 0


def test_truth_flags_a_lane_change_no_one_made_and_a_contact_with_nobodys_pair(tmp_path):
    """T10 (checks-open s-17e557f0): seed 2's settled_to on a car the truth saw keep its lane, standing (calm_12) or driving on
    (aggr_4); a contact on a not_relevant pair (the crash of Town01 s1 at tick 911); a log before `contact` says it is unchecked."""
    pytest.importorskip("metis.trace")
    from metis import trace
    if not hasattr(trace, "member_atoms"):
        pytest.skip("metispy before metis.trace sort: this CI's sibling at its head, until it merges")
    sys.path.insert(0, os.path.join(os.path.dirname(HERE), "tools"))
    import rulecheck
    fx = os.path.join(HERE, "fixtures", "sort-town01-2")
    rows = rulecheck.truth_rows(os.path.join(fx, "log.jsonl"), os.path.join(fx, "trace"))
    assert [(r.get("body"), r.get("from"), r.get("to"), r["kind"]) for r in rows] == [
        ("calm_12", 586, 605, "idle"), ("aggr_4", 695, 714, "idle"), (None, None, None, "note")]
    log = tmp_path / "log.jsonl"
    log.write_text("".join(json.dumps({"tick": k, "resp": "none", "contact": c, "danger": [], "truth": []}) + "\n" for k, c in (
        (910, []), (911, [{"id": "calm_9", "type": "not_relevant"}]), (912, [{"id": "x", "type": "same_dir"}]))))
    assert rulecheck.truth_rows(str(log)) == [{"tick": 911, "body": "calm_9", "kind": "no pair", "type": "not_relevant"}]

