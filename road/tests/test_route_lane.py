"""route_lane(D) (commonroad-world s-9b7591fb step 2, record ec8088; the architect's vocabulary): road_facts states it when the ego's
lane has no way on along its route and a same-direction lane toward D has, within ROUTE_REACH of the lane's end, never inside a
junction. On a hand-built three-lane approach in Peachtree's shape: the straight way on (edge x) leaves from the two right lanes,
the left lane turns left only (edge l)."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "world"))
import road_facts  # noqa: E402
from semantic_world.lane import Lane, LaneMap, Mover, dynamics_for  # noqa: E402
from semantic_world.situation import Situation  # noqa: E402

V = 13.89


def approach(length=120.0):
    return LaneMap([
        Lane("a_0", length, left="a_1", speed=V, edge="a", index=0, succ=[":j_0_0"]),
        Lane("a_1", length, left="a_2", right="a_0", speed=V, edge="a", index=1, succ=[":j_1_0"]),
        Lane("a_2", length, right="a_1", speed=V, edge="a", index=2, succ=[":j_2_0"]),
        Lane(":j_0_0", 10.0, succ=["x_0"], internal=True, junction="j", speed=V),
        Lane(":j_1_0", 10.0, succ=["x_1"], internal=True, junction="j", speed=V),
        Lane(":j_2_0", 12.0, succ=["l_0"], internal=True, junction="j", speed=V),
        Lane("x_0", 200.0, left="x_1", speed=V, edge="x", index=0),
        Lane("x_1", 200.0, right="x_0", speed=V, edge="x", index=1),
        Lane("l_0", 200.0, speed=V, edge="l", index=0)])


def ego(lane, s, edges=("a", "x")):
    m = Mover("ego", lane, s, dynamics_for("passenger", v=10.0, ego=True), route=[lane])
    m.route_edges = list(edges)
    return m


def facts(lm, e):
    return road_facts.facts(lm, e, 10.0, [], Situation())[0]


def test_the_left_lane_with_no_way_on_says_the_right_lane_carries_the_route():
    lm = approach()
    assert road_facts.route_side(lm, ego("a_2", 40.0)) == "right"
    assert "route_lane(right)" in facts(lm, ego("a_2", 40.0))


def test_a_lane_that_carries_the_route_on_says_nothing():
    lm = approach()
    for lane in ("a_0", "a_1"):
        assert road_facts.route_side(lm, ego(lane, 40.0)) is None
    assert road_facts.route_side(lm, ego("a_2", 40.0, edges=("a", "l"))) is None, "the left turn is the route: the left lane carries it"


def test_not_too_early_not_inside_the_junction_not_on_the_last_edge_not_without_edges():
    lm = approach(length=400.0)
    assert road_facts.route_side(lm, ego("a_2", 100.0)) is None, "300 m before the end: beyond ROUTE_REACH"
    assert road_facts.route_side(lm, ego("a_2", 260.0)) == "right"
    lm = approach()
    assert road_facts.route_side(lm, ego(":j_2_0", 2.0)) is None
    assert road_facts.route_side(lm, ego("a_2", 40.0, edges=("a",))) is None
    e = ego("a_2", 40.0)
    del e.route_edges
    assert road_facts.route_side(lm, e) is None, "the exerciser's ego has no route edges: no fact"


def test_two_lanes_away_still_names_the_first_side():
    lm = LaneMap([
        Lane("a_0", 120.0, left="a_1", speed=V, edge="a", index=0, succ=["x_0"]),
        Lane("a_1", 120.0, left="a_2", right="a_0", speed=V, edge="a", index=1, succ=["l_0"]),
        Lane("a_2", 120.0, right="a_1", speed=V, edge="a", index=2, succ=["l_0"]),
        Lane("x_0", 200.0, speed=V, edge="x", index=0), Lane("l_0", 200.0, speed=V, edge="l", index=0)])
    assert road_facts.route_side(lm, ego("a_2", 40.0)) == "right"


def test_a_goal_on_another_lane_of_its_edge_points_route_lane_toward_it():
    """A CommonRoad goal region on one lane of a multi-lane road (cr_world's goal_lanes; USA_US101-11_1_T-1: the ego on 14_2,
    the goal on 14_1): route_lane toward it on the goal's edge; nothing on another edge, on the goal lane, or with no goal."""
    lm = approach()
    e = ego("a_2", 40.0, edges=("a", "l"))                      # the route carries on from a_2 (the left turn): no cut-off lane
    e.goal_lanes = ["a_0"]
    assert road_facts.goal_side(lm, e) == "right" and "route_lane(right)" in facts(lm, e)
    e.goal_lanes = ["a_2"]
    assert road_facts.goal_side(lm, e) is None
    e.goal_lanes = ["x_1"]
    assert road_facts.goal_side(lm, e) is None, "the goal is on another edge: the route takes the ego there first"
    e.goal_lanes = None
    assert road_facts.goal_side(lm, e) is None and "route_lane(right)" not in facts(lm, e)
    e = ego(":j_2_0", 2.0)
    e.goal_lanes = ["a_0"]
    assert road_facts.goal_side(lm, e) is None
