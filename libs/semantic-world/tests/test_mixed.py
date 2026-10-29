"""The mixed adapter's geometry (wc-world s-db2f8e59 step 2a): one map over lane segments and cells, zones and their
links (open | ramp | curb), the adjacency computed once; built from data and from a SUMO net read with walking=True."""
import collections
import os

import pytest

from semantic_world import mixed, net
from semantic_world.lane import Lane, LaneMap

NETS = os.path.join(os.path.dirname(__file__), "nets")


def scene(tmp_path):
    """A road lane R (y = 0, x 0..20, 3.5 m wide) with a crosswalk lane X across it at x = 10 (y -4..4), a sidewalk S
    south of the road (y -3..-2) and a sidewalk N north of it (y 2..3), one cell row each; ramps S–X and N–X, curbs
    S–R and N–R."""
    lanes = [Lane("R", 20.0, 3.5, shape=[(0.0, 0.0), (20.0, 0.0)]),
             Lane("X", 8.0, 2.0, shape=[(10.0, -4.0), (10.0, 4.0)], allow=("pedestrian",), function="crossing")]
    cells = {}
    for i in range(20):
        cells[mixed.cell_id(i, -3)] = ((i + 0.5), -2.5, "S")
        cells[mixed.cell_id(i, 2)] = ((i + 0.5), 2.5, "N")
    zones = {"S": {"kind": "sidewalk"}, "N": {"kind": "sidewalk"}, "X": {"kind": "crossing", "lanes": ["X"]}}
    links = [("S", "X", "ramp"), ("N", "X", "ramp"), ("S", "R", "curb"), ("N", "R", "curb")]
    return mixed.MixedMap.build(str(tmp_path / "m.json"), LaneMap(lanes), cells, zones, links)


def reach(m, start):
    seen, q = {start}, collections.deque([start])
    while q:
        for n in m.neighbours(q.popleft()):
            if n not in seen:
                seen.add(n)
                q.append(n)
    return seen


def test_zones_links_and_the_one_graph(tmp_path):
    m = scene(tmp_path)
    assert m.zone_of("c3_-3") == "S" and m.zone_kind("S") == "sidewalk"
    assert m.zone_of("R|2") == "R" and m.zone_kind("R") == "lane"          # a lane in no zone: its own, kind lane
    assert m.zone_of("X|1") == "X" and m.zone_kind("X") == "crossing"
    assert m.link("S", "X") == "ramp" and m.link("R", "S") == "curb" and m.link("S", "N") is None
    # a sidewalk cell beside the road: its row neighbours, never the road (a curb connects nothing)
    assert m.neighbours("c3_-3") == ["c2_-3", "c4_-3"]
    # the cells at the crosswalk touch its bins (a ramp), and a bin touches them back
    near = m.neighbours("c10_-3")
    assert "X|0" in near and not any(p.startswith("R|") for p in near)
    assert "c10_-3" in m.neighbours("X|0")
    # S reaches N only through the crosswalk; no road bin is ever reached from a sidewalk
    got = reach(m, "c0_-3")
    assert "c19_2" in got and "X|1" in got and not any(p.startswith("R|") for p in got)


def test_the_zones_readings_both_ways(tmp_path):
    f = scene(tmp_path).zone_facts()
    assert f["zone_kind(S,sidewalk)"] == f["zone_kind(X,crossing)"] == f["zone_kind(R,lane)"] == 1
    assert {"ramp(S,X)", "ramp(X,S)", "curb(R,S)", "curb(S,R)"} <= set(f)
    assert not any(a.startswith("open(") for a in f)                    # an open link is no reading


def test_a_scene_states_its_topology(tmp_path):
    lm = LaneMap([Lane("R", 10.0, 3.5, shape=[(0.0, 0.0), (10.0, 0.0)])])
    with pytest.raises(ValueError, match="kind 'road'"):
        mixed.MixedMap.build(str(tmp_path / "a.json"), lm, {}, {"Z": {"kind": "road"}})
    with pytest.raises(ValueError, match="no zone Q"):
        mixed.MixedMap.build(str(tmp_path / "b.json"), lm, {}, {"Z": {"kind": "path"}}, [("Z", "Q", "open")])
    with pytest.raises(ValueError, match="kind 'wall'"):
        mixed.MixedMap.build(str(tmp_path / "c.json"), lm, {}, {"Z": {"kind": "path"}}, [("Z", "R", "wall")])
    with pytest.raises(ValueError, match="cell c0_0: no zone Q"):
        mixed.MixedMap.build(str(tmp_path / "d.json"), lm, {"c0_0": (0.5, 0.5, "Q")}, {"Z": {"kind": "path"}})


def test_a_net_read_with_walking_keeps_its_crosswalks_and_areas():
    plain = net.load_net(os.path.join(NETS, "walk.net.xml"))
    walk = net.load_net(os.path.join(NETS, "walk.net.xml"), walking=True)
    extra = sorted(set(walk.lanes) - set(plain.lanes))
    assert extra and all(walk.lanes[l].function in ("crossing", "walkingarea") for l in extra)
    assert sum(walk.lanes[l].function == "crossing" for l in extra) == 4
    assert all(l.function == "normal" for l in plain.lanes.values())   # the default reads a net as before


def test_a_net_as_the_one_map(tmp_path):
    n = net.load_net(os.path.join(NETS, "walk.net.xml"), walking=True)
    m = mixed.MixedMap.from_net(str(tmp_path / "w.json"), n)
    d = m.load()
    kinds = collections.Counter(v["kind"] for v in d["zones"].values())
    assert kinds["crossing"] == 4 and kinds["sidewalk"] == 16 and len(d["cells"]) > 1000
    assert {k for _, _, k in d["links"]} == {"open", "ramp", "curb"}
    assert all(k == "ramp" for a, b, k in d["links"] if "crossing" in (m.zone_kind(a), m.zone_kind(b)))
    # the west sidewalk's end reaches the east one's through the crosswalks; no vehicle lane is ever entered
    west = min(d["cells"], key=lambda c: d["cells"][c][0])
    east = max(d["cells"], key=lambda c: d["cells"][c][0])
    got = reach(m, west)
    assert east in got
    assert not any("|" in p and m.zone_kind(m.zone_of(p)) == "lane" for p in got)
