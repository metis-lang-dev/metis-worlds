"""cr-harvest 3 (s-f4e297da): the converter's net name (A), the start and goal through the lanelet maps (B), the lenient
read of a file whose objects reuse an id (C). No SUMO, no checkout: fakes and a temp dir; C only where commonroad is."""
import importlib.util
import os
import sys
import time
from pathlib import Path

import pytest

ROAD = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROAD / "world"))
import cr_world as W  # noqa: E402

SPEC = importlib.util.spec_from_file_location("cr_convert", ROAD / "tools" / "cr_convert.py")
C = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(C)


def test_a_the_net_named_after_the_benchmark_id_is_moved_to_the_scenario_id(tmp_path):
    (tmp_path / "ZAM_Tjunction-1_374_I-1.net.xml").write_text("<net/>")
    assert C.produced_net(tmp_path, "ZAM_Tjunction-1_374_I-1-1") == "ZAM_Tjunction-1_374_I-1-1.net.xml"
    assert (tmp_path / "ZAM_Tjunction-1_374_I-1-1.net.xml").is_file()
    assert C.produced_net(tmp_path, "ZAM_Tjunction-1_374_I-1-1") == "ZAM_Tjunction-1_374_I-1-1.net.xml"
    (tmp_path / "none").mkdir()
    assert C.produced_net(tmp_path / "none", "X") is None


class Lane:
    def __init__(self, lid, length=50.0):
        self.lid, self.length = lid, length

    def getLength(self):
        return self.length

    def getClosestLanePosAndDist(self, xy):
        return 12.0, 0.1


class Net:
    def __init__(self, lanes):
        self.lanes = {l: Lane(l) for l in lanes}

    def hasEdge(self, e):
        return any(l.rpartition("_")[0] == e for l in self.lanes)

    def getLane(self, lid):
        return self.lanes[lid]


def square(x0, y0, x1, y1):
    return {"left": [[x0, y1], [x1, y1]], "right": [[x0, y0], [x1, y0]]}


DOC = {"lanelets": [dict(square(-10, -2, 0, 2), id=1, predecessors=[], successors=[2]),      # leads in
                    dict(square(0, -2, 10, 2), id=2, predecessors=[1], successors=[3]),        # in the junction
                    dict(square(10, -2, 20, 2), id=3, predecessors=[2], successors=[])],       # leads out
       "lanelet_lane": {"1": "e1_0", "2": "e2_0", "3": "e3_0"}}


def test_b_a_start_in_a_junction_begins_at_the_end_of_the_lane_leading_in():
    net = Net(["e1_0", "e3_0"])                                   # netconvert folded e2 into the junction
    lane, pos = W.start_lane(net, DOC, 5.0, 0.0, 0.0)
    assert lane.lid == "e1_0" and pos == 49.0
    lane, pos = W.start_lane(Net(["e1_0", "e2_0", "e3_0"]), DOC, 5.0, 0.0, 0.0)
    assert lane.lid == "e2_0" and pos == 12.0
    assert W.nearest_in_net(DOC, net, 2, first="successors")[0].lid == "e3_0"
    assert W.start_lane(Net([]), DOC, 5.0, 0.0, 0.0) is None


def test_b_a_time_only_goal_has_no_position():
    assert not W.has_position({"polygons": [], "lanelets": [], "time": [10, 20]})
    assert W.has_position({"polygons": [], "lanelets": [3]})


def test_c_a_file_reusing_an_id_is_read_with_the_check_off():
    pytest.importorskip("commonroad")
    from commonroad.scenario.scenario import Scenario
    calls = []

    class Reader:
        def __init__(self, path):
            pass

        def open(self):
            s = Scenario(0.1)
            s._mark_object_id_as_used(0)
            calls.append(1)
            s._mark_object_id_as_used(0)                          # 'ID 0 is already used' unless lenient
            return s, None

    import commonroad.common.file_reader as fr
    keep = fr.CommonRoadFileReader
    fr.CommonRoadFileReader = Reader
    try:
        sc, pps, lenient = C.read_lenient("x.cr.xml")
    finally:
        fr.CommonRoadFileReader = keep
    assert lenient and len(calls) == 2
    with pytest.raises(ValueError):                              # the check is back after the read
        sc._mark_object_id_as_used(0)
