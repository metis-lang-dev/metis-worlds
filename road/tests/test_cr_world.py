"""cr_world (commonroad-world s-9b7591fb step 1): the cr:<id> kind's director and its measures on a SYNTHETIC cr.json (no
CommonRoad data in any repo: road/docs/commonroad.md), and, where the checkout and the conversion venv are (road/setup-commonroad.sh),
the conversion cache and the placement on a scenario of the checkout."""
import json
import math
import os
import sys
from pathlib import Path

import pytest

ROAD = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROAD / "world"))
import cr_world as W  # noqa: E402

CR_ROOT = Path(os.environ.get("COMMONROAD_ROOT", "/bigdata/datasets/commonroad"))
CONV_PY = Path(os.environ.get("COMMONROAD_CONVERT_PY", str(ROAD / ".venv-cr" / "bin" / "python")))
checkout = pytest.mark.skipif(not (CR_ROOT / "scenarios").is_dir() or not CONV_PY.exists(),
                              reason="no CommonRoad checkout or conversion venv here (road/setup-commonroad.sh)")
T_JUNCTION = "ZAM_Tjunction-1_100_T-1"


def strip(x0, x1, y0=-2.0, y1=2.0):
    return {"left": [[x0, y1], [x1, y1]], "right": [[x0, y0], [x1, y0]]}


def doc():
    """A straight road of two lanelets along +x, the goal the second's last 20 m in steps 40-60 at 5-15 m/s, one recorded car
    ahead from step 0 to step 30 and one parked car beyond the road's end."""
    return {"version": W.CR_JSON_VERSION, "id": "SYN-1", "dt": 0.1, "net": "syn.net.xml", "net_offset": [0, 0], "edges": {"1": [1], "2": [2]},
            "lanelets": [dict(strip(0, 100), id=1), dict(strip(100, 200), id=2)], "signs": [], "lights": [], "intersections": [],
            "obstacles": [{"id": 7, "type": "car", "role": "dynamic", "length": 4.0, "width": 2.0,
                           "trajectory": [{"k": k, "x": 30.0 + k, "y": 0.0, "theta": 0.0, "v": 10.0} for k in range(0, 31)]},
                          {"id": 8, "type": "parkedVehicle", "role": "static", "length": 4.0, "width": 2.0,
                           "trajectory": [{"k": 0, "x": 260.0, "y": 0.0, "theta": 0.0, "v": 0.0}]}],
            "planning": [{"id": 1, "initial": {"k": 0, "x": 10.0, "y": 0.0, "theta": 0.0, "v": 10.0},
                          "goals": [{"polygons": [[[180, -2], [200, -2], [200, 2], [180, 2]]], "lanelets": [2], "time": [40, 60],
                                     "velocity": [5, 15], "orientation": None}]}]}


class Edge:
    def __init__(self, n):
        self.n = n

    def getLength(self):
        return self.n


class Net:
    def getEdge(self, eid):
        return Edge(100.0)


class Veh:
    """The TraCI vehicle domain, as far as the director reads and writes it: the ego at a pose the test sets."""

    def __init__(self):
        self.ids, self.pose, self.calls = {"ego"}, {}, []

    def getIDList(self):
        return list(self.ids)

    def getPosition(self, vid):
        x, y, h, _ = self.pose[vid]
        return x + 2.25 * math.cos(h), y + 2.25 * math.sin(h)            # the front bumper of a 4.5 m car

    def getAngle(self, vid):
        return 90.0 - math.degrees(self.pose[vid][2])

    def getLength(self, vid):
        return 4.5

    def getWidth(self, vid):
        return 1.8

    def getSpeed(self, vid):
        return self.pose[vid][3]

    def add(self, vid, rid, typeID, depart):
        self.ids.add(vid)
        self.calls.append(("add", vid, typeID))

    def remove(self, vid):
        self.ids.discard(vid)
        self.calls.append(("remove", vid))

    def moveToXY(self, vid, edge, lane, x, y, angle, keepRoute):
        self.calls.append(("move", vid, round(x, 2), round(y, 2)))

    def setLength(self, *a):
        pass

    setWidth = setSpeedMode = setSpeed = setLength


class Conn:
    def __init__(self):
        self.vehicle = Veh()
        self.route = type("R", (), {"add": lambda self, rid, edges: None})()
        self.simulation = type("S", (), {"convertRoad": lambda self, x, y: ("1", 0.0, 0)})()


def director():
    d = doc()
    pl = {"ego": {"lane": 0, "edge": "1", "pos": 10.0, "v": 10.0, "k0": 0, "route": ["1", "2"]}, "goal_edge": "2", "route_note": None}
    return W.Director(d, pl, Net()), Conn()


def drive(dr, c, poses):
    """POSES [(t, x, y, heading, v)]: the ego there before each tick."""
    for t, x, y, h, v in poses:
        c.vehicle.pose["ego"] = (x, y, h, v)
        dr.tick(c, t)
    return dr.report()


def test_the_goal_is_reached_in_its_window_and_not_before_or_after_it():
    dr, c = director()
    r = drive(dr, c, [(0.1 * k, 150.0 + 2.0 * k, 0.0, 0.0, 10.0) for k in range(0, 50)])     # through the region (x 180-200) at steps 15-25: before the window
    assert r["cr"]["goal_position_t"] == 1.5 and not r["cr"]["goal_reached"]
    dr, c = director()
    r = drive(dr, c, [(0.1 * k, 140.0 + 1.0 * k, 0.0, 0.0, 10.0) for k in range(0, 50)])     # x 180 at step 40: in the window
    assert r["cr"]["goal_reached"] and r["cr"]["goal_t"] == 4.0
    dr, c = director()
    r = drive(dr, c, [(0.1 * k, 140.0 + 1.0 * k, 0.0, 0.0, 20.0) for k in range(0, 50)])     # in time, too fast
    assert r["cr"]["goal_position_t"] == 4.0 and not r["cr"]["goal_reached"]
    assert r["cr"]["goal_window_s"] == [[4.0, 6.0]]


def test_a_recorded_obstacle_is_played_at_its_pose_and_removed_after_its_last_step():
    dr, c = director()
    drive(dr, c, [(0.1 * k, 0.0 + k, 0.0, 0.0, 10.0) for k in range(0, 35)])
    adds = [x for x in c.vehicle.calls if x[0] == "add"]
    assert ("add", "cr7", "cr_car") in adds and ("add", "cr8", "cr_static") in adds
    first = next(x for x in c.vehicle.calls if x[0] == "move" and x[1] == "cr7")
    assert first[2:] == (32.0, 0.0), "SUMO's position is the front bumper: the recorded centre + half the length"
    assert ("remove", "cr7") in c.vehicle.calls and "cr8" in c.vehicle.ids, "the dynamic one leaves after step 30, the static one stays"


def test_contact_is_the_boxes_touching_and_off_lanelet_is_the_centre_outside_every_lanelet():
    dr, c = director()
    r = drive(dr, c, [(0.0, 26.0, 0.0, 0.0, 10.0), (0.1, 27.0, 0.0, 0.0, 10.0)])            # the car's rear at 29 m, the ego's front at 29.25 m
    assert r["cr"]["contact"] and r["cr"]["contacts"][0][1] == 7
    dr, c = director()
    r = drive(dr, c, [(0.0, 50.0, 0.0, 0.0, 10.0), (0.1, 51.0, 3.0, 0.0, 10.0), (0.2, 52.0, 3.0, 0.0, 10.0)])
    assert r["cr"]["off_lanelet_ticks"] == 2 and r["cr"]["off_lanelet_m"] > 1.0 and not r["cr"]["contact"]


def test_a_cache_of_another_version_is_refused_in_words(tmp_path):
    d = doc()
    d["version"] = W.CR_JSON_VERSION + 1
    (tmp_path / "SYN-1").mkdir()
    (tmp_path / "SYN-1" / "cr.json").write_text(json.dumps(d))
    with pytest.raises(RuntimeError, match="cr_convert.py --force"):
        W.load("SYN-1", cache=tmp_path)


def test_a_scenario_not_in_the_cache_without_a_conversion_venv_is_refused_in_words(tmp_path, monkeypatch):
    monkeypatch.setenv("COMMONROAD_CONVERT_PY", str(tmp_path / "no-python"))
    with pytest.raises(RuntimeError, match="setup-commonroad.sh"):
        W.load("SYN-2", cache=tmp_path)


def test_the_interpolation_is_linear_and_the_heading_takes_the_short_way():
    traj = [{"k": 0, "x": 0.0, "y": 0.0, "theta": 3.1, "v": 0.0}, {"k": 10, "x": 10.0, "y": 0.0, "theta": -3.1, "v": 10.0}]
    s = W.at(traj, 5)
    assert (s["x"], s["v"]) == (5.0, 5.0) and abs(abs(s["theta"]) - math.pi) < 0.1
    assert W.at(traj, 11) is None and W.at(traj, -1) is None


@checkout
def test_the_conversion_is_cached_by_the_files_hash(tmp_path):
    import subprocess
    run = lambda *a: subprocess.run([str(CONV_PY), str(ROAD / "tools" / "cr_convert.py"), T_JUNCTION, "--cache", str(tmp_path), *a],
                                    capture_output=True, text=True, check=True)
    run()
    meta = tmp_path / T_JUNCTION / "cr.json"
    m0 = meta.stat().st_mtime_ns
    run()
    assert meta.stat().st_mtime_ns == m0, "the same file: the cache is kept"
    run("--force")
    assert meta.stat().st_mtime_ns != m0
    d = json.loads(meta.read_text())
    assert d["version"] == W.CR_JSON_VERSION and d["planning"][0]["goals"] and len(d["obstacles"]) == 5


@checkout
def test_the_ego_starts_at_the_planning_problems_state_and_is_routed_to_the_goals_edge(tmp_path):
    net, routes, script, dr = W.build("cr:" + T_JUNCTION, str(tmp_path))
    assert Path(net).is_file() and script == []
    assert dr.pl["goal_edge"] == "50203" and dr.pl["ego"]["route"][-1] == "50203" and dr.pl["route_note"] is None
    text = Path(routes).read_text()
    assert 'id="ego"' in text and "50203" in text
