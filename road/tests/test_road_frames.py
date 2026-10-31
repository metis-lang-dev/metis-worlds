"""The road page's frames and the responder host's page faces (road-agent s-357becc7 step 1): road_frames over a Loop's readings, the world lines,
the pace, the next run. No SUMO runs here."""
import os
import sys
from types import SimpleNamespace

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "world"))
import road_frames  # noqa: E402
import road_host  # noqa: E402

NET = """<net version="1.16"><location netOffset="0,0" convBoundary="0.00,0.00,1000.00,0.00" origBoundary="0,0,1000,0" projParameter="!"/>
<edge id="E" from="a" to="b"><lane id="E_0" index="0" speed="15.00" length="1000.00" shape="0.00,-4.80 1000.00,-4.80"/>
<lane id="E_1" index="1" speed="15.00" length="1000.00" shape="0.00,-1.60 1000.00,-1.60"/></edge>
<junction id="a" type="dead_end" x="0" y="0" shape="0,0 0,-6.4"/><junction id="b" type="dead_end" x="1000" y="0" shape="1000,0 1000,-6.4"/></net>"""
EGO = {"x": 20.0, "y": -4.8, "heading": 0.0, "lane": "E_0", "s": 20.0, "speed": 6.0, "vclass": "passenger", "type": "aggr", "length": 5.0, "width": 1.8, "signals": 0, "route": ["E"]}


def loop(path):
    return SimpleNamespace(world=SimpleNamespace(net=str(path), ego_collisions=0), prev_truth={"ego": EGO, "lead": dict(EGO, x=60.0, s=60.0, type="calm")}, ego_id="ego", level_dest=950.0,
                           scenario="straight", seed=3, tick=7, t=0.7, restricted=2, log=[{"cmd": ["accel", None], "a": 1.5, "seen": 1, "tracks": 1}],
                           proj={"binding": {"lead": "lead"}, "fold": {"resp_lon": "brake_min", "resp_lat": "none", "dangerous": True}}, arrived=lambda: False)


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
    assert f["lanes"][1] == {"id": "E_1", "index": 1, "speed": 15.0, "length": 1000.0, "shape": [[0.0, -1.6], [1000.0, -1.6]]}


def test_the_scene_has_the_truths_movers_and_the_beliefs_roles(net):
    f = road_frames.scene_frame(loop(net))
    assert f["ev"] == "world/scene" and f["ego"] == "ego" and [m["id"] for m in f["movers"]] == ["ego", "lead"]
    assert f["movers"][1]["class"] == "passenger" and f["movers"][1]["type"] == "calm" and f["movers"][1]["x"] == 60.0
    assert f["roles"] == {"lead": "lead"} and f["fold"] == {"resp_lon": "brake_min", "resp_lat": "none"} and f["cmd"] == ["accel", None] and f["a"] == 1.5


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
    h.world(["watching"])
    assert [f["ev"] for f in h.frames()] == ["world/net", "world/scene"]


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
    h.world(["play", "speed:2", "run:cut_in:4"])
    assert not h.shared["paused"] and h.shared["speed"] == 2.0
    assert h.shared["next"]["scenario"] == "cut_in" and h.shared["next"]["seed"] == 4
    with pytest.raises(ValueError):
        h.world(["key:y"])


def test_paused_or_there_the_clock_is_held(net, monkeypatch):
    slept, stepped = [], []
    world = dict(arrived=lambda: False, step=lambda: stepped.append(1), tick=0, observe=lambda: ({}, {}, {}, []), log=[{}])
    h = host(world=SimpleNamespace(**world))
    h.observed, h.period, h.beat = set(), 1, 5
    monkeypatch.setattr(road_host.time, "sleep", slept.append)
    h.world(["pause"])
    h.tick({})
    assert slept == [road_host.DT] and not stepped


def test_a_new_episode_opens_one_world_for_the_hierarchy(monkeypatch):
    closed, made = [], []
    old = SimpleNamespace(close=lambda: closed.append(1), scenario="straight", seed=1)

    def new_world(run):
        made.append(run)
        return SimpleNamespace(close=lambda: None, scenario=run["scenario"], seed=run["seed"])
    monkeypatch.setattr(road_host, "new_world", new_world)
    a, b = host(world=old), host("planner", world=old)
    b.shared = a.shared
    a.world(["run:cut_out:5", "pause"])
    a.new_episode()
    b.new_episode()
    assert closed == [1] and len(made) == 1 and a.road is b.road and made[0]["scenario"] == "cut_out" and made[0]["seed"] == 5
    assert a.beat == 0 and b.latched is None and not a.shared["paused"]


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
