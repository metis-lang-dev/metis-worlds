"""The gap records' projection (road-scenarios s-e23be780 step 3, steps/road-gap-vocabulary-architect.md): road_facts states
oncoming(D), oncoming_clear/busy(D), lead_standing, own_kind(oncoming) in the ego's heading frame, emergency(obj), side_busy(D)
and side_clear's emergency sentence. On a hand-built two-way road in the two cards' geometry: ParkedObstacleTwoWays (Town01,
one lane each way, 50 km/h, a car standing in the ego's lane, an oncoming flow) and YieldToEmergencyVehicle (Town03, two lanes
the ego's way, an emergency vehicle closing from behind)."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "world"))
import road_facts  # noqa: E402
from semantic_world.lane import Lane, LaneMap, Mover, dynamics_for  # noqa: E402
from semantic_world.situation import Situation  # noqa: E402

V = 13.89                                   # the towns' 50 km/h


def two_way(length=300.0):
    """One lane each way: f_0 the ego's, b_0 the opposite direction's, each the other's opposite left neighbour."""
    return LaneMap([Lane("f_0", length, left="b_0", left_opposite=True, speed=V, edge="f"),
                    Lane("b_0", length, left="f_0", left_opposite=True, speed=V, edge="b")])


def car(mid, lane, s, v, vclass="passenger"):
    return Mover(mid, lane, s, dynamics_for(vclass, v=v), vclass=vclass)


def ego_at(lane, s, v, route=("f_0",)):
    return Mover("ego", lane, s, dynamics_for("passenger", v=v, ego=True), route=list(route))


def facts(lm, ego, v, movers):
    speeds = {m.id: m.dyn.vmax for m in movers}
    return road_facts.facts(lm, ego, v, movers, Situation(), speeds=speeds)[0]


# ── 668e45: a car standing in the only lane; the ego stands behind it, as the card plays (ParkedObstacleTwoWays) ──
PARKED_S, EGO_S = 100.0, 91.0                                   # the ego's front 4.5 m behind the parked car's rear


def test_the_opposite_lane_is_oncoming_and_clear_with_no_one_on_it():
    lm, ego = two_way(), ego_at("f_0", EGO_S, 0.0)
    out = facts(lm, ego, 0.0, [car("parked", "f_0", PARKED_S, 0.0)])
    assert {"oncoming(left)", "lane_kind(left,none)", "lane_kind(right,none)", "lead_slow", "lead_standing",
            "oncoming_clear(left)", "own_kind(driving)"} <= set(out)
    assert "adjacent(left)" not in out and "oncoming_busy(left)" not in out


def test_an_oncoming_car_inside_the_pass_makes_it_busy_one_beyond_sight_does_not():
    lm, ego = two_way(), ego_at("f_0", EGO_S, 0.0)
    parked = car("parked", "f_0", PARKED_S, 0.0)
    near = car("onc", "b_0", 300.0 - (EGO_S + 60.0), 11.1)      # 60 m ahead of the ego, coming at 40 km/h: inside the pass
    assert "oncoming_busy(left)" in facts(lm, ego, 0.0, [parked, near])
    lm, ego = two_way(1000.0), ego_at("f_0", EGO_S, 0.0)
    far = car("onc", "b_0", 1000.0 - (EGO_S + 300.0), 11.1)     # 300 m ahead: beyond the ego's 100 m of sight, not counted
    assert "oncoming_clear(left)" in facts(lm, ego, 0.0, [car("parked", "f_0", PARKED_S, 0.0), far])


def test_the_view_test_makes_a_pass_the_ego_cannot_see_through_busy():
    """The file's view test: the oncoming lane's limit x (T + rho) within sight; from standing behind the car the pass takes
    about 4.9 s (L = 4.5 + 4.5 + 4.5 + 2 s at 50 km/h), so 75 m of view: 100 m of sensor is enough, 50 m is not."""
    lm, ego = two_way(), ego_at("f_0", EGO_S, 0.0)
    lead = car("p", "f_0", PARKED_S, 0.0)
    assert road_facts.oncoming_clear(lm, ego, 0.0, V, lead, "b_0", [], sight_m=100.0) is True
    assert road_facts.oncoming_clear(lm, ego, 0.0, V, lead, "b_0", [], sight_m=50.0) is False


def test_a_slow_lead_a_queue_or_a_car_waiting_at_the_lane_end_is_not_standing():
    lm, ego = two_way(), ego_at("f_0", EGO_S - 40.0, 8.0)
    out = facts(lm, ego, 8.0, [car("slow", "f_0", PARKED_S, 3.0)])
    assert "lead_slow" in out and "lead_standing" not in out
    queue = [car("p1", "f_0", PARKED_S, 0.0), car("p2", "f_0", PARKED_S + 10.0, 0.0)]
    assert "lead_slow" in facts(lm, ego, 8.0, queue) and "lead_standing" not in facts(lm, ego, 8.0, queue)
    assert "lead_standing" not in facts(lm, ego_at("f_0", 270.0, 0.0), 0.0, [car("waits", "f_0", 285.0, 0.0)])


def test_on_the_oncoming_lane_the_route_lane_is_the_egos_right_and_clear_once_past():
    """The heading frame: on b_0 beside its route f_0, the ego's right is f_0; the parked car behind (standing) is safe."""
    lm = two_way()
    ego = ego_at("b_0", 300.0 - (PARKED_S + 20.0), 11.1)        # level with f_0's s 120: 20 m past the parked car
    out = facts(lm, ego, 11.1, [car("parked", "f_0", PARKED_S, 0.0)])
    assert {"own_kind(oncoming)", "adjacent(right)", "lane_kind(right,driving)", "side_clear(right)", "lane_kind(left,none)"} <= set(out)
    assert "own_kind(driving)" not in out and "oncoming(left)" not in out


def test_on_the_oncoming_lane_a_car_close_ahead_on_the_route_lane_makes_it_busy():
    lm = two_way()
    ego = ego_at("b_0", 300.0 - (PARKED_S + 20.0), 11.1)
    out = facts(lm, ego, 11.1, [car("parked", "f_0", PARKED_S, 0.0), car("ahead", "f_0", PARKED_S + 28.0, 2.0)])
    assert "side_busy(right)" in out and "side_clear(right)" not in out


# ── 13b2f9: an emergency vehicle from behind ──
def two_lane(length=300.0):
    """Two lanes the ego's way (e_0 right, e_1 left) and the opposite carriageway beyond e_1."""
    return LaneMap([Lane("e_0", length, left="e_1", speed=V, edge="e", index=0),
                    Lane("e_1", length, right="e_0", left="w_0", left_opposite=True, speed=V, edge="e", index=1),
                    Lane("w_0", length, left="e_1", left_opposite=True, speed=V, edge="w")])


def test_an_emergency_follower_is_a_class_of_its_role():
    lm, ego = two_lane(), ego_at("e_1", 100.0, 13.0, route=("e_1",))
    out = facts(lm, ego, 13.0, [car("amb", "e_1", 70.0, 20.0, vclass="emergency")])
    assert "emergency(follower)" in out and "side_clear(right)" in out and "adjacent(right)" in out


def test_a_side_with_an_emergency_vehicle_closing_behind_is_busy():
    lm, ego = two_lane(), ego_at("e_1", 100.0, 13.0, route=("e_1",))
    out = facts(lm, ego, 13.0, [car("amb", "e_0", 60.0, 20.0, vclass="emergency")])
    assert "emergency(followright)" in out and "side_busy(right)" in out and "side_clear(right)" not in out
    out = facts(lm, ego, 13.0, [car("amb", "e_0", 60.0, 5.0, vclass="emergency")])     # not closing: the side as the fold says
    assert "side_clear(right)" in out


def test_side_busy_is_side_clears_complement_on_an_adjacent_side():
    lm, ego = two_lane(), ego_at("e_1", 100.0, 13.0, route=("e_1",))
    out = facts(lm, ego, 13.0, [car("beside", "e_0", 101.0, 13.0)])                    # level with the ego on the right
    assert ("side_clear(right)" in out) != ("side_busy(right)" in out)
    assert "side_clear(left)" not in out and "side_busy(left)" not in out and "oncoming(left)" in out


def test_the_pass_time_accelerates_to_the_limit():
    assert abs(road_facts.pass_time(100.0, 13.89, 13.89, 2.0) - 100.0 / 13.89) < 1e-9
    t = road_facts.pass_time(100.0, 0.0, 13.89, 2.0)
    assert 10.0 < t < 11.0                                       # 6.9 s to the limit over 48 m, then 52 m at 13.89
