"""The predicted occupancy and the rasteriser (wc-motion s-efcc13bf step 2): the mixed map's predict step over a horizon, soft
and hard, and its zones on a grid aligned to its cells. The recordings' tests are metis-wheelchair's tests/test_occupancy.py."""
import copy
import math
from pathlib import Path

import pytest

from semantic_world import mixed, occupancy
from semantic_world.lane import Lane, LaneMap, dynamics_for
from semantic_world.situation import Pair, check_unstructured, safe_lat_dist, stated


def plaza(tmp_path, n=30, dt=0.5, name="m.json"):
    cells = {mixed.cell_id(i, j): (i + 0.5, j + 0.5, "P") for i in range(n) for j in range(n)}
    return mixed.MixedMap.build(str(tmp_path / name), LaneMap([]), cells, {"P": {"kind": "plaza"}}, dt=dt)


def walker(x, y, speed=1.3, heading=0.0, cls="pedestrian"):
    return {"class": cls, "x": x, "y": y, "speed": speed, "heading": heading}


def walk_east(m, x0=5.0, y=15.5, ticks=6, speed=1.3):
    """A walker seen TICKS ticks walking east at SPEED. → its track's name, its pose."""
    for k in range(ticks):
        x = x0 + k * speed * m.load()["dt"]
        m.cycle([walker(x, y, speed)], ego={"x": 0.5, "y": 0.5, "speed": 0.0})
    return next(iter(m._people(m.load()))), (x, y)


def mean(soft):
    z = sum(soft.values())
    return (sum((mixed.cell_ij(c)[0] + 0.5) * p for c, p in soft.items()) / z,
            sum((mixed.cell_ij(c)[1] + 0.5) * p for c, p in soft.items()) / z)


def test_the_render_reads_the_map_and_writes_nothing(tmp_path):
    m = plaza(tmp_path)
    walk_east(m)
    before, on_disk = copy.deepcopy(m.load()), Path(m.path).read_bytes()
    occupancy.render(m).soft(6)
    assert m.load() == before and Path(m.path).read_bytes() == on_disk


def test_the_times_are_the_horizon_at_the_maps_dt_or_the_step_asked(tmp_path):
    m = plaza(tmp_path)
    walk_east(m)
    assert occupancy.render(m, horizon=3.0).times == [0.0, 0.5, 1.0, 1.5, 2.0, 2.5, 3.0]
    assert occupancy.render(m, horizon=2.0, step=1.0).times == [0.0, 1.0, 2.0]


def test_a_walker_keeps_going_its_mass_ahead_of_it_and_further_with_time(tmp_path):
    m = plaza(tmp_path)
    t, (x, y) = walk_east(m)
    assert m.load()["intent"][t]["keep"] > 0.5
    tr = occupancy.render(m).tracks[t]
    assert tr.form == "unstructured" and tr.seen and tr.mass == 1.0
    xs = [mean(tr.soft(k))[0] for k in range(7)]
    assert xs[0] == pytest.approx(math.floor(x) + 0.5) and all(a < b for a, b in zip(xs[1:], xs[2:]))
    assert xs[6] - x > 1.5                             # the stop and cross branches are in the mean too
    assert abs(mean(tr.soft(6))[1] - y) < 2.0
    for k in range(7):
        assert sum(tr.soft(k).values()) == pytest.approx(1.0)


def test_an_intent_persists_over_the_horizon(tmp_path):
    m = plaza(tmp_path)
    t, (x, y) = walk_east(m)
    d = m.load()
    d["intent"][t] = {"keep": 0.5, "stop": 0.5, "cross": 0.0}
    here = d["_people_seen"] and next(iter(d["belief"][t]))
    tr = occupancy.render(m).tracks[t]
    assert tr.soft(6)[here] == pytest.approx(0.5, abs=0.02)      # the stop branch has not moved
    far = {c: p for c, p in tr.soft(6).items() if mixed.cell_ij(c)[0] + 0.5 - x > 2.0}
    assert sum(far.values()) > 0.35                              # and the keep branch is far ahead, not half way
    redrawn = {here: 1.0}                                        # the mixture redrawn a tick, as meets rolls it
    model = m.people_mixture(d["intent"][t], m.people_models(d, t))
    for _ in range(6):
        redrawn = model(redrawn)
    assert redrawn[here] < 0.2


def test_the_reach_cuts_what_the_class_cannot_get_to(tmp_path):
    m = plaza(tmp_path)
    t, (x, y) = walk_east(m)
    d = m.load()
    tr = occupancy.render(m).tracks[t]
    dyn = dynamics_for("pedestrian", v=d["speed"][t])
    bel, model = dict(d["belief"][t]), m.people_models(d, t)["keep"]
    over = 0
    for k in range(1, 7):
        limit = stated(dyn.vmax, dyn.accel, k * 0.5, None, dyn.vcap)
        bel = model(bel)
        far = lambda c: occupancy._sq_gap(((mixed.cell_ij(c)[0] + 0.5), (mixed.cell_ij(c)[1] + 0.5), 0.5), (x, y, 0.0)) > limit  # noqa: E731
        over += any(far(c) for c in bel)                         # the walk alone goes further
        assert not any(far(c) for c in tr.soft(k))
    assert over


@pytest.mark.parametrize("speed", [0.0, 1.3])
@pytest.mark.parametrize("ev", [None, 0.0, 1.2])
def test_at_now_the_disc_is_the_unstructured_pairs_safety(tmp_path, speed, ev):
    m = plaza(tmp_path)
    m.cycle([walker(15.2, 14.7, speed)], ego={"x": 0.5, "y": 0.5, "speed": 0.0})
    t = next(iter(m._people(m.load())))
    occ = occupancy.render(m)
    tr = occ.tracks[t]
    ego = None if ev is None else dynamics_for(mixed.CHAIR, v=ev, ego=True)
    pair_ego = ego or dynamics_for(mixed.CHAIR, v=0.0)
    if ego is None:                                              # the object's side alone: no brake set of the chair's
        pair_ego.vmax = pair_ego.accel = pair_ego.min_dist = 0.0
    obj = dynamics_for("pedestrian", v=speed)
    both = 0
    for i in range(0, 30):
        for j in range(0, 30):
            x, y = i + 0.5, j + 0.5
            gap = max(0.0, math.hypot(x - 15.2, y - 14.7) - m.RADIUS["chair"] - m.RADIUS["pedestrian"])
            safe = check_unstructured(Pair("p", "unstructured", d_lon=gap, ego=pair_ego, obj=obj))[0]
            assert occ.clear(0, x, y, ego) == safe, (x, y)
            assert (mixed.cell_id(i, j) in occ.hard(0, ego)) == (not safe)
            both += not safe
    assert both and tr.radius(ego) > 0


def test_the_hard_set_follows_the_prediction_and_not_a_reach_disc(tmp_path):
    m = plaza(tmp_path)
    t, (x, y) = walk_east(m)
    occ = occupancy.render(m)
    tr = occ.tracks[t]
    behind = (x - tr.radius() - 1.0, y)
    assert not occ.clear(6, x + 3.0, y) and occ.clear(0, x + tr.radius() + 0.1, y)   # what is free now is closed ahead later
    assert occ.clear(0, *behind)
    # the set at 3 s is its credible cells' discs, far short of the reach's on top of them
    far = stated(1.3, 2.0, 3.0, None, 1.39) + tr.radius()
    assert occ.clear(6, x, y + far - 0.1)


def test_a_standing_track_stands(tmp_path):
    m = plaza(tmp_path)
    for _ in range(4):
        m.cycle([walker(15.2, 14.7, 0.0)], ego={"x": 0.5, "y": 0.5, "speed": 0.0})
    t = next(iter(m._people(m.load())))
    tr = occupancy.render(m).tracks[t]
    for k in range(7):
        assert tr.soft(k) == {"c15_14": pytest.approx(1.0)}
    assert tr.hard(6) == tr.hard(1)


def test_a_probability_is_never_over_one_though_the_map_rounds_its_intents(tmp_path):
    m = plaza(tmp_path)
    for _ in range(4):
        m.cycle([walker(15.2, 14.7, 0.0)], ego={"x": 0.5, "y": 0.5, "speed": 0.0})
    d = m.load()
    t = next(iter(m._people(d)))
    d["intent"][t] = {"keep": 0.593924, "stop": 0.049725, "cross": 0.356352}     # 1.000001, as S4's group has them
    tr = occupancy.render(m).tracks[t]
    assert all(p <= 1.0 for k in range(7) for p in tr.soft(k).values())


def test_a_track_lost_from_view_is_anchored_on_its_belief(tmp_path):
    m = plaza(tmp_path)
    t, _ = walk_east(m)
    for _ in range(3):
        m.cycle([], ego={"x": 0.5, "y": 0.5, "speed": 0.0})
    tr = occupancy.render(m).tracks[t]
    assert not tr.seen and tr.form == "unstructured" and tr.hard(0) and sum(tr.soft(0).values()) == pytest.approx(1.0)


def test_an_unconfirmed_birth_is_soft_by_its_mass_and_never_hard(tmp_path):
    m = plaza(tmp_path)
    m.birth("b1", ["c10_10", "c10_11"], "pedestrian", 0.2)
    occ = occupancy.render(m)
    tr = occ.tracks["b1"]
    assert tr.form == "birth" and not tr.seen and tr.mass == 0.2
    for k in range(7):
        assert sum(tr.soft(k).values()) == pytest.approx(0.2)
        assert occ.hard(k) == set() and occ.clear(k, 10.5, 10.5)
        assert max(occ.soft(k).values()) <= 0.2


def test_two_tracks_on_a_cell_are_independent(tmp_path):
    m = plaza(tmp_path)
    for name, mass in (("a", 0.5), ("b", 0.5)):
        m.birth(name, ["c10_10"], "pedestrian", mass)
    assert occupancy.render(m).soft(0)["c10_10"] == pytest.approx(0.75)


def strips(tmp_path, dt=0.5):
    """A sidewalk S (x 0..40, y 0..3) with its strip, two halves, and a plaza north of it."""
    cells = {mixed.cell_id(i, j): (i + 0.5, j + 0.5, "S") for i in range(40) for j in range(3)}
    cells.update({mixed.cell_id(i, j): (i + 0.5, j + 0.5, "Q") for i in range(40) for j in range(3, 13)})
    zones = {"S": {"kind": "sidewalk", "strip": {"axis": [[0, 1.5], [40, 1.5]], "width": 3.0, "halves": 2}},
             "Q": {"kind": "plaza"}}
    return mixed.MixedMap.build(str(tmp_path / "s.json"), LaneMap([]), cells, zones, [("S", "Q", "open")], dt=dt)


def test_a_cyclist_on_the_strip_is_a_capsule_and_the_pass_in_the_other_half_stays_clear(tmp_path):
    m = strips(tmp_path)
    chair = {"x": 20.0, "y": 0.75, "heading": 0.0, "speed": 1.2}
    for k in range(3):
        m.cycle([walker(30.0 - k * 2.25, 2.25, 4.5, math.pi, "bicycle")], ego=chair)
    t = next(iter(m._people(m.load())))
    ego = dynamics_for(mixed.CHAIR, v=1.2, ego=True)
    ego.mu = 0.05
    occ = occupancy.render(m)
    tr = occ.tracks[t]
    assert tr.form == "strip"
    assert tr.radius(ego) == pytest.approx(mixed.CHAIR_BODY[1] / 2 + mixed.BODY["bicycle"][1] / 2 + 0.5)
    assert safe_lat_dist(ego, dynamics_for("bicycle")) == pytest.approx(0.5)
    for k in range(7):
        assert occ.clear(k, 20.0, 0.75, ego)                     # the chair's half, 1.5 m across: the pass is free
    pose = m.load()["pos"][t]
    assert not occ.clear(0, pose["x"], pose["y"], ego)
    assert not occ.clear(4, pose["x"] - 4.5 * 2.0, pose["y"], ego) and occ.clear(0, pose["x"] - 4.5 * 2.0, pose["y"], ego)


def test_a_cyclist_off_the_strips_is_a_disc(tmp_path):
    m = strips(tmp_path)
    chair = {"x": 20.0, "y": 8.0, "heading": 0.0, "speed": 0.0}             # the chair on the plaza: no strip
    for k in range(3):
        m.cycle([walker(30.0 - k * 2.25, 2.25, 4.5, math.pi, "bicycle")], ego=chair)
    t = next(iter(m._people(m.load())))
    tr = occupancy.render(m).tracks[t]
    assert tr.form == "unstructured" and tr.radius() > 11.0


def road_scene(tmp_path):
    """A lane R (y 4.75, x 0..100, 3.5 m wide) and a sidewalk S south of it (y 0..3), a curb between; cells only on S, x 20..60."""
    lm = LaneMap([Lane("R", 100.0, 3.5, shape=[(0.0, 4.75), (100.0, 4.75)], speed=13.9)])
    cells = {mixed.cell_id(i, j): (i + 0.5, j + 0.5, "S") for i in range(20, 60) for j in range(3)}
    return mixed.MixedMap.build(str(tmp_path / "r.json"), lm, cells, {"S": {"kind": "sidewalk"}}, [("S", "R", "curb")], dt=0.5)


def test_a_vehicle_is_its_body_on_its_lane(tmp_path):
    m = road_scene(tmp_path)
    for k in range(3):
        m.cycle([{"class": "passenger", "lane": "R", "s": 10.0 + k * 5.5, "speed": 11.0}], ego={"x": 30.5, "y": 1.5, "speed": 0.0})
    t = next(iter(t for t in m.load()["things"] if m.load()["things"][t].get("layer") != "people"))
    occ = occupancy.render(m)
    tr = occ.tracks[t]
    assert tr.form == "vehicle" and tr.seen
    assert tr.radius() == m.RADIUS["chair"]
    # the body's cells off the map's cells too (no cell on the lane), at the lane's width, its length behind the front
    assert all(3 <= mixed.cell_ij(c)[1] <= 6 for c in tr.soft(0))
    assert {mixed.cell_ij(c)[0] for c in tr.soft(0)} >= {16, 20, 24}
    at = lambda k: mean(tr.soft(k))[0]                  # noqa: E731
    assert all(at(k) < at(k + 1) for k in range(6))
    assert at(6) - at(0) == pytest.approx(33.0, abs=8.0)  # 11 m/s for 3 s
    for k in range(7):                                    # the sidewalk beside it stays clear of a body on the lane
        assert occ.clear(k, 30.5, 2.5) and occ.clear(k, 30.5, 0.5)
    assert not occ.clear(0, 20.5, 4.75)


def crossing(tmp_path, with_cells):
    """Sidewalks S (y 0..3) and N (y 10..13), a crosswalk lane X between them at x 10 (y 3..10); its zone X has cells or not."""
    lm = LaneMap([Lane("X", 7.0, 4.0, shape=[(10.0, 3.0), (10.0, 10.0)], allow=("pedestrian",), function="crossing")])
    cells = {}
    for i in range(20):
        for j in list(range(3)) + list(range(10, 13)):
            cells[mixed.cell_id(i, j)] = (i + 0.5, j + 0.5, "S" if j < 3 else "N")
    if with_cells:
        for i in range(8, 12):
            for j in range(3, 10):
                cells[mixed.cell_id(i, j)] = (i + 0.5, j + 0.5, "X")
    zones = {"S": {"kind": "sidewalk"}, "N": {"kind": "sidewalk"}, "X": {"kind": "crossing", "lanes": ["X"]}}
    return mixed.MixedMap.build(str(tmp_path / ("x%d.json" % with_cells)), lm, cells, zones, [("S", "X", "ramp"), ("N", "X", "ramp")])


def test_the_roll_stays_on_the_cells_where_a_crossing_has_them(tmp_path):
    m = crossing(tmp_path, True)
    for k in range(5):
        m.cycle([walker(10.5, 9.5 - k * 0.65, 1.3, -math.pi / 2)], ego={"x": 0.5, "y": 0.5, "speed": 0.0})
    t = next(iter(m._people(m.load())))
    d = m.load()
    assert any(not mixed.is_cell(n) for n in m.neighbours("c10_6"))          # the one graph has the bins
    roll = occupancy._roll_person(m, d, t, 6, 0.5, occupancy._Places(m, d))
    assert all(mixed.is_cell(p) for bel in roll for p in bel)
    tr = occupancy.render(m).tracks[t]
    y0, y2 = d["pos"][t]["y"], mean(tr.soft(2))[1]
    assert y0 - y2 < 1.5                                                     # 1.3 m in the second, no 5 m bin in it


def test_a_crosswalk_with_no_cells_shares_a_persons_mass_under_the_bin(tmp_path):
    m = crossing(tmp_path, False)
    for k in range(4):
        m.cycle([walker(10.5, 10.9 - k * 0.1, 0.2, -math.pi / 2)], ego={"x": 0.5, "y": 0.5, "speed": 0.0})
    t = next(iter(m._people(m.load())))
    d = m.load()
    d["belief"][t] = {"X|0": 1.0}
    d["intent"][t] = {"keep": 0.0, "stop": 1.0, "cross": 0.0}
    d["_people_seen"] = []
    tr = occupancy.render(m).tracks[t]
    assert sum(tr.soft(0).values()) == pytest.approx(1.0)
    assert len(tr.soft(0)) == 20 and "c8_5" in tr.soft(0) and "c8_5" not in d["cells"]     # 4 m wide, a 5 m bin
    assert max(tr.soft(0).values()) == pytest.approx(1 / 20)


@pytest.mark.parametrize("factor", [1, 2, 5, 20])
def test_the_raster_is_aligned_to_the_cells_by_its_factor(tmp_path, factor):
    m = crossing(tmp_path, True)
    r = occupancy.rasterise(m, factor)
    d = m.load()
    assert r.res == pytest.approx(1.0 / factor) and r.origin[0] / d["cell"] == int(r.origin[0] / d["cell"])
    assert r.nx % factor == 0 and r.ny % factor == 0
    for iy in range(r.ny):
        for ix in range(r.nx):
            c = r.cell_at(ix, iy)
            z = r.zone[iy][ix]
            if c in d["cells"]:
                assert r.zones[z] == d["cells"][c][2]
            k = r.kind[iy][ix]
            assert (k == -1) == (z == -1) and (z == -1 or r.kinds[k] == d["zones"][r.zones[z]]["kind"])
            assert r.index(*r.xy(ix, iy)) == (ix, iy)
    assert r.zone_at(10.5, 1.5) == "S" and r.kind_at(10.5, 5.5) == "crossing" and r.zone_at(2.5, 5.5) is None


def test_a_lane_is_rastered_where_no_cell_has_spoken(tmp_path):
    m = road_scene(tmp_path)
    r = occupancy.rasterise(m, 2)
    assert r.origin[0] == 0.0 and r.zone_at(90.0, 4.75) == "R" and r.kind_at(90.0, 4.75) == "lane"
    assert r.zone_at(30.5, 1.5) == "S" and r.zone_at(10.5, 1.5) is None and r.zone_at(90.0, 7.0) is None


def test_the_mask_is_the_allowed_zones(tmp_path):
    m = crossing(tmp_path, True)
    r = occupancy.rasterise(m, 2)
    mask = r.mask({"S", "X"})
    for iy in range(r.ny):
        for ix in range(r.nx):
            z = r.zone[iy][ix]
            assert mask[iy][ix] == (1 if z >= 0 and r.zones[z] in {"S", "X"} else 0)
    assert sum(map(sum, r.mask(set()))) == 0


@pytest.mark.parametrize("factor", [0, -1, 2.5, "2"])
def test_a_factor_is_a_whole_number(tmp_path, factor):
    with pytest.raises(ValueError, match="factor"):
        occupancy.rasterise(crossing(tmp_path, True), factor)
