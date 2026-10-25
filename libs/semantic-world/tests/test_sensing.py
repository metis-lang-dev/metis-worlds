"""road-world step 4: the sensing model — range, occlusion by another body and by a polygon, the seeded miss rate,
the visible cells for the belief's negative evidence."""
from semantic_world.lane import Lane, LaneMap
from semantic_world.sensing import Body, Sensor, cell_points


def test_range_and_occlusion_by_a_car():
    ego = Body(0, 0)
    bodies = {"ego": ego, "lead": Body(15, 0), "hidden": Body(30, 0), "beside": Body(20, 3.5), "far": Body(100, 0)}
    seen = Sensor(range=60).sense(ego, bodies, ego_id="ego")
    assert "lead" in seen and "beside" in seen
    assert "hidden" not in seen                          # behind the lead on the same line
    assert "far" not in seen                             # out of range


def test_a_polygon_occludes():
    ego = Body(0, 0)
    wall = [(10, -5), (12, -5), (12, 5), (10, 5)]
    assert Sensor(range=60).sense(ego, {"ego": ego, "car": Body(20, 0)}, occluders=[wall], ego_id="ego") == []


def test_the_miss_rate_is_seeded():
    ego = Body(0, 0)
    bodies = {"ego": ego, **{"c%d" % i: Body(10, 3.5 * (i - 5)) for i in range(11)}}
    a = Sensor(range=60, miss=0.5, seed=7).sense(ego, bodies, ego_id="ego")
    b = Sensor(range=60, miss=0.5, seed=7).sense(ego, bodies, ego_id="ego")
    assert a == b and 0 < len(a) < 11


def test_visible_cells_stop_behind_a_body():
    lm = LaneMap([Lane("e_0", 60.0, shape=[(0, 0), (60, 0)])])
    pts = cell_points(lm, 5.0)
    ego = Body(-5, 0)
    vis = set(Sensor(range=80).visible(ego, pts, {"ego": ego, "truck": Body(20, 0, length=8)}, ego_id="ego"))
    assert "e_0|0" in vis and "e_0|2" in vis and "e_0|8" not in vis
