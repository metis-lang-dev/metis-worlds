"""The lane adapter's skeleton: a two-lane road with an oncoming lane and a crossing, its pairs, and the situation
layer's verdicts on them (no road runtime)."""
from semantic_world.lane import Lane, LaneMap, Mover, Zone
from semantic_world.situation import Dynamics, Situation

CAR = dict(rho=0.5, accel=2.0, brake_min=4.0, brake_max=8.0, brake_min_correct=3.0, min_dist=1.0)


def road():
    return LaneMap([Lane("e1", 100, succ=["e2"], left="w1", left_opposite=True), Lane("e2", 100),
                    Lane("w1", 100, right="e1", right_opposite=True), Lane("n1", 60)],
                   zones=[Zone("x", {"e2": (40.0, 47.0), "n1": (30.0, 37.0)}, priority="e2")])


def car(id, lane, s, v, route=None):
    return Mover(id, lane, s, Dynamics(vmin=v, vmax=v, **CAR), route=route)


def test_the_pairs_of_a_road():
    m = road()
    ego = car("ego", "e1", 10.0, 10.0, route=["e1", "e2"])
    lead, oncoming, cross, far = car("lead", "e1", 60.0, 10.0), car("on", "w1", 80.0, 10.0), car("x", "n1", 10.0, 10.0), car("p", "w1", 5.0, 0.0)
    ps = {p.id.split(":")[0]: p for p in m.pairs(ego, [lead, oncoming, cross, far], role_of=lambda o: o.id)}
    assert ps["lead"].type == "same_dir" and ps["lead"].lon == "in_front" and ps["lead"].d_lon == 45.5   # 50 m less its length
    assert ps["on"].type == "opp_dir" and ps["on"].lat == "at_left" and ps["on"].lon == "in_front"
    assert ps["on"].d_lon == 5.5                          # at s 80 of the westbound lane: 20 m in the ego's frame, 10 ahead
    assert ps["x"].type == "xing_ego_prio" and ps["x"].d_enter == 130.0 and ps["x"].o_enter == 20.0
    states = {s.id.split(":")[0]: s for s in Situation().check(list(ps.values()))}
    assert states["lead"].safe_long                       # 45.5 m against Lemma 2's 15.1 m
    assert states["x"].safe_long                          # no time overlap: it leaves the zone long before the ego arrives
    assert states["on"].safe_lat and not states["on"].dangerous   # the oncoming car is in its own lane: laterally safe
