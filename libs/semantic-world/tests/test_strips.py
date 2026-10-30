"""A sidewalk as lanes (wc-member s-4fe6cfd6; the wheelchair DESIGN amendment 4): a strip's two halves under keep right,
the chair and a cyclist on them as movers paired by LaneMap.pairs, a walker unstructured, finite readings."""
import math

from semantic_world import mixed
from semantic_world.lane import LaneMap, Mover, dynamics_for, halves
from semantic_world.situation import Situation


def street(tmp_path, width=3.0, n=2, bike=False):
    """A strip S, y 0..WIDTH, x 0..60, the axis running east, one cell per metre; a bike lane B to its north if BIKE."""
    cells = {mixed.cell_id(i, j): (i + 0.5, j + 0.5, "S") for i in range(60) for j in range(int(math.ceil(width)))}
    zones = {"S": {"kind": "sidewalk",
                   "strip": {"axis": [[0.0, width / 2], [60.0, width / 2]], "width": width, "halves": n}}}
    if bike:
        for i in range(60):
            cells[mixed.cell_id(i, int(width))] = (i + 0.5, width + 0.5, "B")
        zones["B"] = {"kind": "bike", "strip": {"axis": [[0.0, width + 0.5], [60.0, width + 0.5]], "width": 1.0, "halves": 1}}
    return mixed.MixedMap.build(str(tmp_path / "s.json"), LaneMap([]), cells, zones, [("S", "B", "curb")] if bike else [],
                                dt=0.5, journal="")


LIMIT, COMFORT, MU = 0.5, 1.0, 0.05                  # the scenes' numbers: the host's, here as a host would give them


def tick(m, chair_x, chair_y, who, heading=0.0, v=1.2):
    place = mixed.cell_id(int(chair_x), int(chair_y))
    m.cycle(who, ego={"place": place, "x": chair_x, "y": chair_y, "heading": heading, "speed": v, "path": [place]})
    m.project(k=0, j=2)
    return m.pairs(chair_mu=MU)


def bike(x, y, heading=math.pi, v=4.5):
    return {"class": "bicycle", "x": x, "y": y, "speed": v, "heading": heading}


def test_two_halves_keep_right_and_their_s_runs_their_way():
    a, b = halves("S", [(0.0, 1.5), (60.0, 1.5)], 3.0)
    assert (a.id, a.shape[0], a.width, a.left, a.left_opposite) == ("S_along", (0.0, 0.75), 1.5, "S_against", True)
    assert (b.id, b.shape[0], b.left, b.left_opposite) == ("S_against", (60.0, 2.25), "S_along", True)


def test_a_body_is_placed_by_where_it_is_and_which_way_it_goes(tmp_path):
    m = street(tmp_path)
    at = m.strip_at("S", 10.0, 0.5, 0.0)                     # near half, heading east: the cells' row, off the centre
    assert (at["lane"], at["s"], at["dir"], at["against"], at["lat"]) == ("S_along", 10.0, "along", False, "centre")
    assert abs(at["offset"] + 0.25) < 1e-9
    at = m.strip_at("S", 10.0, 2.25, math.pi)                # far half, heading west: its s runs back
    assert (at["lane"], at["s"], at["dir"], at["against"], at["lat"]) == ("S_against", 50.0, "against", False, "centre")
    assert m.strip_at("S", 10.0, 1.5, math.pi)["lane"] == "S_against"     # on the line: the half its direction keeps
    assert m.strip_at("S", 10.0, 0.75, math.pi)["against"]                 # in the near half, going west: the wrong way


def test_a_cyclist_in_the_other_half_asks_nothing_while_it_passes(tmp_path):
    m = street(tmp_path)
    sit, seen = Situation(), []
    for k in range(30):                                      # S3's: the chair east in the near half, it west in the far
        x, cx = 50.0 - 2.25 * k, 5.0 + 0.6 * k
        st, = sit.check(tick(m, cx, 0.5, [bike(max(x, 1.0), 2.25)]))
        seen.append(st)
    assert {s.type for s in seen} == {"opp_dir"} and all(s.safe_lat and not s.dangerous for s in seen)
    assert {s.resp_lon for s in seen} == {"none"} and {s.resp_lat for s in seen} == {"none"}
    assert not all(s.safe_long for s in seen)                # along the way it is inside lemma 3: lemma 4 is why


def test_035_m_off_is_a_brake_rss_honest_answer(tmp_path):
    m = street(tmp_path)
    sit, seen = Situation(), []
    for k in range(20):                                      # the chair on the dividing line, 0.35 m between the bodies
        st, = sit.check(tick(m, 5.0 + 0.6 * k, 1.5, [bike(50.0 - 2.25 * k, 2.5)]))
        seen.append(st)
    assert seen[0].type == "opp_dir" and seen[0].resp_lon == "none" and any(s.dangerous for s in seen)
    assert "brake_min_correct" in {s.resp_lon for s in seen}


def test_the_same_half_head_on_is_the_opposite_direction_rule(tmp_path):
    m = street(tmp_path)
    st, = Situation().check(tick(m, 10.0, 0.5, [bike(14.0, 0.5)]))
    assert st.type == "opp_dir" and st.dangerous and st.resp_lon == "brake_min_correct"
    passed, = tick(m, 10.0, 0.5, [bike(4.0, 0.5)])
    assert passed.type == "not_relevant"


def test_a_narrow_path_is_one_lane_for_both_ways(tmp_path):
    m = street(tmp_path, width=1.6, n=1)
    st, = Situation().check(tick(m, 10.0, 0.5, [bike(14.0, 0.5)]))
    assert st.type == "opp_dir" and st.dangerous
    ahead, = tick(m, 10.0, 0.5, [bike(14.0, 0.5, heading=0.0, v=1.0)])
    assert ahead.type == "same_dir"


def test_a_bike_lane_beside_the_chairs_half_is_an_adjacent_lane(tmp_path):
    m = street(tmp_path, width=3.0, bike=True)
    p, = tick(m, 10.0, 2.25, [bike(30.0, 3.5, heading=0.0)], heading=math.pi, v=0.5)   # the chair in the far half
    assert p.type == "opp_dir" and p.lat == "at_right" and abs(p.d_lat - 0.6) < 1e-9     # 1.25 between the lines


def test_a_walker_keeps_no_lane_and_a_cyclist_off_the_strips_neither(tmp_path):
    m = street(tmp_path)
    w, = tick(m, 10.0, 0.5, [{"class": "pedestrian", "x": 20.0, "y": 2.5, "speed": 1.0, "heading": math.pi}])
    assert w.type == "unstructured"
    d = m.load()
    del d["zones"]["S"]["strip"]
    m.save()
    c, = tick(m, 10.0, 0.5, [bike(20.0, 2.25)])
    assert c.type == "unstructured"


def test_the_lane_readings_are_finite_atoms(tmp_path):
    m = street(tmp_path)
    tick(m, 10.0, 0.5, [bike(30.0, 2.25)])
    f = m.lane_facts(LIMIT, COMFORT)
    assert {"chair_half(S,along)", "chair_dir(S,along)", "chair_lat(S,centre)", "cyclist_half(vru1,other)",
            "cyclist_dir(vru1,against)", "cyclist_gap(vru1,clear)"} == set(f)
    d = m.load()
    del d["zones"]["S"]["strip"]
    m.save()
    assert m.lane_facts(LIMIT, COMFORT) == {}


def test_the_lateral_level_is_the_bodies_gap_against_the_hosts_numbers(tmp_path):
    def gap(chair_y, y=2.25):
        m = street(tmp_path)
        p, = tick(m, 10.0, chair_y, [bike(30.0, y)])
        return round(p.d_lat, 6), [a for a in m.lane_facts(LIMIT, COMFORT) if a.startswith("cyclist_gap")]
    assert gap(0.5) == (1.1, ["cyclist_gap(vru1,clear)"])         # the cells' row, over 1 m
    assert gap(0.75) == (0.85, ["cyclist_gap(vru1,near)"])        # the half's centre line: comfortable it is not, slow
    assert gap(1.4, 2.5) == (0.45, ["cyclist_gap(vru1,tight)"])   # under the limit


def test_lemma_4_needs_the_limit_with_the_chairs_lateral_neglected():
    from semantic_world.situation import safe_lat_dist
    chair, cyclist = dynamics_for("wheelchair", ego=True), dynamics_for("bicycle")
    chair.mu = MU
    assert (chair.lat_accel, chair.lat_brake) == (0.0, 0.0)
    assert abs(safe_lat_dist(chair, cyclist) - LIMIT) < 1e-9       # the cyclist's 0.375 + (0.05 + 0.2) / 2


def test_past_the_limit_is_safe_across_and_under_it_the_response_comes(tmp_path):
    def st(y):
        return Situation().check(tick(street(tmp_path), 10.0, y, [bike(14.0, y + 1.3)]))[0]
    assert not st(0.75).dangerous                                  # 1.3 between the lines: 0.65 between the bodies
    near, = Situation().check(tick(street(tmp_path), 10.0, 1.4, [bike(14.0, 2.5)]))
    assert near.dangerous and near.resp_lon == "brake_min_correct" and not near.safe_lat


def test_a_roads_mover_is_as_it_was():
    lanes = [halves("R", [(0.0, 0.0), (100.0, 0.0)], 7.0)[i] for i in (0, 1)]
    ego = Mover("e", "R_along", 10.0, dynamics_for("passenger", v=10.0, ego=True))
    obj = Mover("o", "R_against", 40.0, dynamics_for("passenger", v=10.0))
    p, = LaneMap(lanes).pairs(ego, [obj])
    assert (p.type, p.lat, p.d_lat) == ("opp_dir", "at_left", 3.5 - 1.8) and p.d_lon == 50.0 - 4.5


def test_the_wheelchair_class_is_its_own():
    w, p = dynamics_for("wheelchair", v=1.0), dynamics_for("pedestrian", v=1.0)
    assert w.lat_accel < p.lat_accel and w.vcap == 1.2
