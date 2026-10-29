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


# ── people (step 2b): intents on the cells, the birth prior, meets ──
def people_scene(tmp_path):
    m = scene(tmp_path)
    d = m.load()
    d["dt"] = 1.0                                      # a second a tick: a walker at 1.2 m/s moves about a cell
    m.save()
    return m


def chair_on_s(m, at="c12_-3", path=("c11_-3", "c10_-3")):
    m.cycle([], visible=(), ego={"place": at, "speed": 0.5, "path": list(path)})


def test_a_walker_toward_the_chair_meets_it_one_walking_away_does_not(tmp_path):
    m = people_scene(tmp_path)
    chair_on_s(m)
    m.cycle([{"class": "pedestrian", "x": 6.5, "y": -2.5, "speed": 1.2, "heading": 0.0},
             {"class": "pedestrian", "x": 4.5, "y": -2.5, "speed": 1.2, "heading": 3.14159}],
            ego={"place": "c12_-3", "speed": 0.5, "path": ["c11_-3", "c10_-3"]})
    d = m.load()
    toward, away = sorted(t for t in d["things"] if d["things"][t]["layer"] == "people")
    assert d["belief"][toward] == {"c6_-3": 1.0} and d["belief"][away] == {"c4_-3": 1.0}
    assert m.meets(toward) > 0.5 > 0.1 > m.meets(away)


def test_a_steady_walker_is_believed_to_keep_its_way(tmp_path):
    m = people_scene(tmp_path)
    chair_on_s(m)
    for x in (3.5, 4.5, 5.5, 6.5):
        m.cycle([{"class": "pedestrian", "x": x, "y": -2.5, "speed": 1.0}], ego={"place": "c12_-3", "path": []})
    p = m.load()["intent"]["pedestrian"]
    assert p["keep"] > 0.6 and p["keep"] > p["stop"] and p["keep"] > p["cross"]          # from its prior 0.5


def test_a_birth_prior_rises_through_the_middle_and_is_removed_by_an_empty_view(tmp_path):
    m = people_scene(tmp_path)
    chair_on_s(m, at="c5_-3", path=["c4_-3", "c3_-3"])
    m.birth("hidden", ["c0_-3", "c1_-3"], mass=0.3)
    p = m.meets("hidden")
    assert 0.0 < p <= 0.3                              # unconfirmed: never more than its existence
    # seen into where it could have walked by now (the boundary and a step beyond), and nobody there
    m.cycle([], visible=["c0_-3", "c1_-3", "c2_-3", "c3_-3", "c4_-3"], ego={"place": "c5_-3", "path": ["c4_-3", "c3_-3"]})
    d = m.load()
    assert not d["belief"].get("hidden") and "hidden" in d["gone"] and m.meets("hidden") == 0.0


def test_a_sighting_near_a_birth_prior_is_that_walker(tmp_path):
    m = people_scene(tmp_path)
    chair_on_s(m, at="c5_-3", path=["c4_-3", "c3_-3"])
    m.birth("hidden", ["c0_-3", "c1_-3"], mass=0.3)
    m.cycle([{"class": "pedestrian", "x": 1.5, "y": -2.5, "speed": 1.2, "heading": 0.0}],
            ego={"place": "c5_-3", "path": ["c4_-3", "c3_-3"]})
    d = m.load()
    assert sorted(t for t in d["things"] if d["things"][t]["layer"] == "people") == ["hidden"]
    assert "birth" not in d["things"]["hidden"] and d["belief"]["hidden"] == {"c1_-3": 1.0}
    assert m.meets("hidden") > 0.5                     # confirmed and heading at the chair: its whole belief counts


def test_vehicles_and_people_share_the_one_map(tmp_path):
    m = people_scene(tmp_path)
    m.cycle([{"class": "passenger", "lane": "R", "s": 3.0, "speed": 5.0},
             {"class": "bicycle", "x": 15.5, "y": 2.5, "speed": 4.0, "heading": 3.14159}],
            ego={"place": "c10_2", "path": ["X|1", "X|0"]})
    d = m.load()
    assert d["belief"]["passenger"] == {"R|0": 1.0} and d["things"]["passenger"].get("layer") is None
    assert d["belief"]["bicycle"] == {"c15_2": 1.0} and d["things"]["bicycle"]["layer"] == "people"
    m.cycle([], ego={"place": "c10_2", "path": ["X|1", "X|0"]})
    d = m.load()
    assert all("|" in c and c.startswith("R|") for c in d["belief"]["passenger"])     # the car stays on its lane
    assert all(not c.startswith("R|") for c in d["belief"]["bicycle"])               # the cyclist never enters it
    assert m.weight("meets", ("bicycle",)) == m.meets("bicycle")


def test_the_one_binding_and_the_peoples_readings(tmp_path):
    m = people_scene(tmp_path)
    d = m.load()
    d["zones"]["S"]["width"] = 1.0
    d["zones"]["N"]["width"] = 3.0
    m.save()
    dets = [{"class": "pedestrian", "x": x, "y": -2.5, "speed": 1.0, "heading": 0.0} for x in (6.5, 7.5, 8.5)]
    dets += [{"class": "bicycle", "x": 15.5, "y": 2.5, "speed": 4.0, "heading": 3.14159},
             {"class": "passenger", "lane": "R", "s": 12.0, "speed": 8.0}]
    m.cycle(dets, ego={"place": "c10_-3", "lane": "X", "s": 1.0, "speed": 0.5, "route": ["X"], "path": ["X|0"]})
    b = m.project(k=2, j=2)
    assert set(b) == {"vru1", "vru2"} | {r for r in b if r.startswith(("a", "lead", "follow"))}
    assert m.load()["things"][b["vru1"]]["layer"] == "people" and b["vru1"] != b["vru2"]
    assert all(b[r] == "passenger" for r in b if not r.startswith("vru"))           # the lane roles: the car
    f = m.people_facts(group=3)
    assert "group_at(S)" in f and "walker_at(vru1,S)" in f
    z = m.zone_facts()
    assert z["path_width(S,narrow)"] == z["path_width(N,wide)"] == 1
    assert m.roles() == set(b)


def test_the_people_seen_are_the_chairs_unstructured_pairs(tmp_path):
    from semantic_world.situation import Situation
    m = people_scene(tmp_path)
    m.cycle([{"class": "pedestrian", "x": 11.5, "y": -2.5, "speed": 0.0},
             {"class": "bicycle", "x": 18.5, "y": 2.5, "speed": 5.0, "heading": 3.14159}],
            ego={"place": "c10_-3", "speed": 0.0, "path": []})
    b = m.project(k=0, j=2)
    ps = {p.role: p for p in m.pairs()}
    assert set(ps) == {"vru1", "vru2"} and all(p.type == "unstructured" for p in ps.values())
    walker = ps[[r for r, t in b.items() if t == "pedestrian"][0]]
    assert walker.d_lon < 0.5 and abs(walker.bearing) < 1e-6                  # just east of the chair
    states = Situation().check(list(ps.values()))
    f = Situation.fold(states, walker.ego)
    assert f["resp_unst"] in ("drive_away", "brake")                          # standing too close: never drive on
