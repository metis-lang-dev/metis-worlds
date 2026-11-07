"""cr_native + iface (planner-loop s-0dcc5ed1 step 2, deliverables 3 + 4): the command → setpoints mapping (table-driven),
the lane map extended from cr.json's lanelet adjacency (ZAM_Over-1_1's oncoming lane), the map matching; no planner,
no simulator."""
import importlib.util
import math
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

ROAD = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROAD / "world"))
sys.path.insert(0, str(ROAD / "planner"))
import iface  # noqa: E402

LIMIT, TARGET = 23.0, 15.0


@pytest.mark.parametrize("cmd, kw, want", [
    (("keep", None), {}, dict(desired_v=LIMIT, stop_xy=None, lane="own")),
    (("accel", None), {}, dict(desired_v=LIMIT, stop_xy=None, lane="own")),
    (("accel", None), {"target": TARGET}, dict(desired_v=TARGET)),
    (None, {}, dict(desired_v=LIMIT)),
    ("keep", {}, dict(desired_v=LIMIT)),
    (("brake", "brake_min"), {"brake_bound": 4.0}, dict(desired_v=6.0, lane="own")),
    (("brake", "brake_max"), {"brake_bound": 8.0}, dict(desired_v=2.0)),
    (("brake", "brake_max"), {"brake_bound": 20.0}, dict(desired_v=0.0)),
    (("yield", None), {"stop_xy": (3.0, 4.0)}, dict(desired_v=None, stop_xy=(3.0, 4.0))),
    (("yield", None), {}, dict(desired_v=0.0, stop_xy=None)),
    (("inch", None), {"stop_xy": (1.0, 2.0)}, dict(stop_xy=(1.0, 2.0))),
    (("change", "left"), {"sibling": "sib"}, dict(desired_v=LIMIT, lane="sib")),
    (("change", "left"), {}, dict(lane="own")),
    (("change_back", None), {"sibling": "sib"}, dict(desired_v=LIMIT, lane="own")),
    (("stop_lat", None), {}, dict(desired_v=LIMIT, lane="own")),
])
def test_setpoints_of_the_command(cmd, kw, want):
    sp = iface.setpoints_of(cmd, ego_v=10.0, limit=LIMIT, own="own", **kw)
    for k, v in want.items():
        assert getattr(sp, k) == v, (cmd, k, getattr(sp, k))


def test_the_desired_speed_is_never_the_initial_speed():
    """The day-1 review's ruling (b): keep / accel ask the target (the lane's limit), not the speed the ego has."""
    for v in (0.0, 5.0, 40.0):
        assert iface.setpoints_of(("keep", None), ego_v=v, limit=LIMIT).desired_v == LIMIT


def test_command_of_the_held_tuple():
    assert iface.Command.of(("brake", "brake_min")) == iface.Command("brake", ("brake_min",))
    assert iface.Command.of(None) == iface.Command("keep")
    assert iface.Command.of("yield").kind == "yield"


# ---------------------------------------------------------------- the lane map and the matching
def lane(lid, shape, edge, index=0, speed=23.0, succ=()):
    pts = list(shape)
    length = sum(math.hypot(b[0] - a[0], b[1] - a[1]) for a, b in zip(pts, pts[1:]))
    return SimpleNamespace(id=lid, shape=pts, edge=edge, index=index, speed=speed, width=3.25, length=length,
                           succ=list(succ), internal=False, left=None, right=None, left_opposite=False,
                           right_opposite=False)


def two_way():
    """ZAM_Over-1_1's shape: lanelet 1000 eastward, 1001 its oncoming left neighbour, each its own edge and nodes."""
    lanes = {"1000_0": lane("1000_0", [(0.0, -1.6), (100.0, -1.6)], "1000"),
             "1001_0": lane("1001_0", [(100.0, 1.6), (0.0, 1.6)], "1001")}
    doc = {"lanelet_lane": {"1000": "1000_0", "1001": "1001_0"},
           "lanelets": [{"id": 1000, "adj_left": 1001, "adj_left_same": False, "adj_right": None},
                        {"id": 1001, "adj_left": 1000, "adj_left_same": False, "adj_right": None}]}
    return SimpleNamespace(lanes=lanes), doc


@pytest.fixture
def cr_native():
    pytest.importorskip("semantic_world", reason="the Live's venv (semantic_world)")
    import cr_native as m
    return m


def test_matching_by_heading_and_the_preferred_lane(cr_native):
    lm, _ = two_way()
    ix = cr_native.LaneIndex(lm)
    lid, s, lat = ix.match(30.0, -1.0, heading=0.0)
    assert lid == "1000_0" and abs(s - 30.0) < 1e-6 and abs(lat - 0.6) < 1e-6
    lid, s, _ = ix.match(30.0, 1.0, heading=math.pi)               # driving west: the oncoming lane, s from its start
    assert lid == "1001_0" and abs(s - 70.0) < 1e-6
    assert ix.match(30.0, 1.0, heading=0.0)[0] == "1000_0"         # eastward: never the westward lane
    assert ix.match(30.0, 0.2, heading=None, prefer="1001_0")[0] == "1001_0"


def test_a_centreline_ahead_and_reversed(cr_native):
    lm, _ = two_way()
    ix = cr_native.LaneIndex(lm)
    line = ix.centreline("1000_0", 20.0, ahead=50.0)
    assert line[0] == (20.0, -1.6) and line[-1] == (70.0, -1.6)
    back = ix.centreline("1001_0", 70.0, reverse=True)              # the oncoming lane driven eastward from x = 30
    assert back[0] == (30.0, 1.6) and back[-1] == (100.0, 1.6)


# ---------------------------------------------------------------- the lanelet adapter (cr_lanes, no SUMO)
def lanelet(lid, x0, y0, x1, y1, w=3.0, **kw):
    dx, dy = x1 - x0, y1 - y0
    n = math.hypot(dx, dy)
    nx, ny = -dy / n * w / 2, dx / n * w / 2
    r = {"id": lid, "center": [[x0, y0], [x1, y1]], "left": [[x0 + nx, y0 + ny], [x1 + nx, y1 + ny]],
         "right": [[x0 - nx, y0 - ny], [x1 - nx, y1 - ny]], "successors": [], "predecessors": [], "adj_left": None,
         "adj_left_same": None, "adj_right": None, "adj_right_same": None, "signs": [], "speed": 13.9}
    r.update(kw)
    return r


@pytest.fixture
def cr_lanes():
    pytest.importorskip("semantic_world", reason="the Live's venv (semantic_world)")
    import cr_lanes as m
    return m


def test_same_direction_neighbours_are_one_edge_by_index(cr_lanes):
    rows = [lanelet(1, 0, 0, 100, 0, adj_left=2, adj_left_same=True),
            lanelet(2, 0, 3, 100, 3, adj_left=3, adj_left_same=True, adj_right=1, adj_right_same=True),
            lanelet(3, 0, 6, 100, 6, adj_right=2, adj_right_same=True)]
    lm = cr_lanes.lanemap_from({"lanelets": rows})
    assert {l.id: (l.edge, l.index) for l in lm.lanes.values()} == {"1": ("e1", 0), "2": ("e1", 1), "3": ("e1", 2)}
    assert lm.lanes["2"].left == "3" and lm.lanes["2"].right == "1" and not lm.lanes["2"].left_opposite
    assert lm.lanes["1"].speed == 13.9 and abs(lm.lanes["1"].length - 100.0) < 1e-9


def test_the_oncoming_lane_is_the_left_opposite(cr_lanes):
    rows = [lanelet(1, 0, 0, 100, 0, adj_left=2, adj_left_same=False),
            lanelet(2, 100, 3, 0, 3, adj_left=1, adj_left_same=False)]
    lm = cr_lanes.lanemap_from({"lanelets": rows})
    assert (lm.lanes["1"].left, lm.lanes["1"].left_opposite) == ("2", True)
    assert lm.lanes["1"].edge != lm.lanes["2"].edge and not lm.zones


def test_a_crossing_is_a_zone_and_the_yield_sign_gives_priority(cr_lanes):
    rows = [lanelet(1, 0, 0, 100, 0), lanelet(2, 50, -50, 50, 50, signs=[7])]
    doc = {"lanelets": rows, "signs": [{"id": 7, "elements": [{"id": "YIELD", "values": []}]}],
           "intersections": [{"id": 9, "incomings": [{"lanelets": [], "left": [], "straight": [1], "right": []}]}]}
    lm = cr_lanes.lanemap_from(doc)
    zs = list(lm.zones.values()) if isinstance(lm.zones, dict) else list(lm.zones)
    assert len(zs) == 1 and zs[0].priority == "1" and zs[0].junction == "9"
    s1 = zs[0].lanes["1"]
    assert 48.0 <= s1[0] <= 49.0 and 51.0 <= s1[1] <= 52.0
    assert lm.lanes["1"].internal and lm.lanes["1"].junction == "9" and not lm.lanes["2"].internal
