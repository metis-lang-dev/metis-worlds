"""The road exerciser's pieces (road-world s-e812715d step 2): the commands and the restrictor (restrict.py, every road
host's), the facts over roles (road_facts.py), the world (road_world.py). No Live here: the tree demo is
road/experiments/road_tree.py. Run in a python with libs/semantic-world installed (metis-agent's venv, or a world's)."""
import sys
from pathlib import Path

import pytest

WORLD = Path(__file__).resolve().parents[1] / "world"
sys.path.insert(0, str(WORLD))
import restrict  # noqa: E402
import road_facts  # noqa: E402
import road_world  # noqa: E402
from semantic_world.lane import Mover, dynamics_for  # noqa: E402
from semantic_world.situation import Pair, Situation  # noqa: E402


def test_a_rule_names_its_command():
    assert restrict.command("brake_lon[R=brake_min]") == ("brake", "brake_min")
    assert restrict.command("change[C=none,D=left,F=followleft,L=leadleft]") == ("change", "left")
    assert restrict.command("stop_lat_left") == ("stop_lat", None)
    assert restrict.command("yield_zone[C=near,P=obj]") == ("yield", None)
    assert restrict.command("accel") == ("accel", None) and restrict.command("keep_limit") == ("keep", None)
    assert restrict.command("drive") is None and restrict.command("decide") is None


def test_the_restrictor_never_gives_more_than_the_response():
    d = dynamics_for("passenger", v=10.0, ego=True)
    none = {"resp_lon": "none", "resp_lat_left": "none", "resp_lat_right": "none"}
    assert restrict.restrict(("accel", None), none, d, 10.0)[0] == d.accel
    braking = dict(none, resp_lon="brake_min")
    a, _ = restrict.restrict(("accel", None), braking, d, 10.0)
    assert a == -d.brake_min and restrict.capped(("accel", None), braking, d, 10.0)
    assert restrict.restrict(("keep", None), none, d, 0.0)[0] == 0.0          # stopped: no braking backwards
    assert restrict.restrict(("change", "left"), none, d, 10.0)[1] == "left"
    assert restrict.restrict(("change", "left"), dict(none, resp_lat_left="brake_min"), d, 10.0)[1] is None
    assert restrict.restrict(("keep", None), dict(none, resp_lat_left="brake_min"), d, 10.0, changing="left")[1] == "abort"
    a, _ = restrict.restrict(("yield", None), none, d, 10.0, yield_gap=26.0)   # stops min_dist before the line
    assert -d.brake_max <= a < 0 and abs(10.0 ** 2 / (2 * (26.0 - d.min_dist)) + a) < 1e-9


def test_a_vacant_role_reads_safe_and_the_zone_ahead_is_said():
    w = road_world.RoadWorld("cruise", 1)
    facts, roles, fold, _ = w.observe()
    for r in road_facts.OBJ_ROLES:
        if r not in roles:
            assert {"type(%s,not_relevant)" % r, "safe_long(%s)" % r, "safe_lat(%s)" % r} <= set(facts)
    assert {"adjacent(left)", "adjacent(right)", "now", "resp_lon(none)"} <= set(facts)
    assert any(a.startswith("zone_at(nextzone,") for a in facts) and "zprio(nextzone,obj)" in facts   # the crosswalk
    assert not any(a.startswith("resp_lat(") and a.count(",") == 2 for a in facts)   # the pair's: resp_side
    assert "lead" in roles


def test_the_facts_are_one_projection_for_every_host():
    # truth-free: a host that knows only the movers (no world object) gets the same atoms
    w = road_world.RoadWorld("demo", 2)
    for _ in range(150):
        w.step()
    facts = w.observe()[0]
    live = w.live()
    again = road_facts.facts(w.map, w.ego.m, w.ego.v, [a.m for a in live], Situation(), changing=w.ego.change_side,
                             dest=w.dest, turn=w.zone_turn, speeds={a.m.id: a.v for a in live})[0]
    memory_free = {a for a in facts if not a.startswith(("safe_before(", "xing_before("))}
    assert memory_free == {a for a in again if not a.startswith(("safe_before(", "xing_before("))}


def test_s_is_the_front():
    w = road_world.RoadWorld("cruise", 1)
    m = Mover("x", "e_1", w.ego.m.s + 4.0)                      # its rear 0.5 m behind the ego's front: overlap
    w.agents.append(road_world.Agent(m, 0.0, moving=False))
    w._account({}, [], 0.0, 1.0, {"accel": False, "change": False}, {})
    assert w.collisions and w.collisions[-1]["with"] == "x"


@pytest.mark.parametrize("scenario", sorted(road_world.SCENARIOS))
def test_every_scenario_is_safe_under_the_restrictor_alone(scenario):
    # the world's own floor: the ego keeping its speed, capped by the proper response (L4), meets no one
    w = road_world.RoadWorld(scenario, 1)
    for _ in range(1200):
        if w.arrived():
            break
        w.step()
    s = w.summary()
    assert s["collisions"] == 0 and s["violations"] == 0, s


def planner_cmd(w):
    """The planner's longitudinal command as its rules read the facts (a plan is held 1 s)."""
    f = w.observe()[0]
    if "cross_overlap(nextzone)" in f:
        return ("brake", "brake_min_correct")
    return ("accel", None) if "accel_ok" in f and "cross_settled(nextzone)" in f and "below_limit" in f else ("keep", None)


def planned(scenario, seed, phase=2):
    """The world under the planner's commands, planned PHASE ticks into each second (the tree's phase is 2); no responder:
    the world's restrictor only."""
    w = road_world.RoadWorld(scenario, seed)
    for i in range(1200):
        if w.arrived():
            break
        if i % 10 == phase:
            w.command(planner_cmd(w), life=10)
        w.step()
    return w


@pytest.mark.parametrize("scenario", sorted(road_world.SCENARIOS))
@pytest.mark.parametrize("seed", [1, 2, 3])
def test_every_scenario_is_safe_under_the_planners_commands(scenario, seed):
    s = planned(scenario, seed).summary()
    assert s["collisions"] == 0 and s["violations"] == 0, s


@pytest.mark.parametrize("phase", range(10))
@pytest.mark.parametrize("seed", range(1, 9))
def test_a_rule_breaker_leaves_a_response_times_margin_at_any_plan_phase(seed, phase):
    # the margin (road-sync s-4169b42d step 2): the ego enters the zone a response time or more after the car has left
    w = road_world.RoadWorld("junction_rb", seed)
    car_out = ego_in = None
    for i in range(400):
        if w.arrived():
            break
        if i % 10 == phase:
            w.command(planner_cmd(w), life=10)
        w.step()
        car = next((a.m for a in w.live() if a.m.id == "xcar"), None)
        if car is not None and w.zones_of(car):
            car_out = w.t
        if ego_in is None and w.zones_of(w.ego.m):
            ego_in = w.t
    s = w.summary()
    assert s["collisions"] == 0 and s["violations"] == 0, s
    assert ego_in is not None and ego_in - car_out >= w.ego.m.dyn.rho, (ego_in, car_out)


def test_an_accel_held_at_a_rule_breaker_is_why_the_rule_is_there():
    # the world alone, accel held whatever the crossing car does: the restrictor has no reason to stop it (the ego has the
    # priority, and is past stopping short by the time the car takes it), and they meet
    w = road_world.RoadWorld("junction_rb", 1)
    for _ in range(140):
        if w.arrived():
            break
        w.command(("accel", None), life=1)
        w.step()
    assert w.summary()["collisions"] > 0


def test_a_crossing_car_settles_when_it_stands_or_has_left():
    w = road_world.RoadWorld("junction_rb", 1)
    assert "cross_settled(nextzone)" in w.observe()[0]            # it stands, at t 0
    while w.t < 1.5:
        w.step()
    assert "cross_unsettled(nextzone)" in w.observe()[0]          # it goes: whether it yields is not yet seen
    while w.t < 12.0 and not w.arrived():
        w.step()
    assert "cross_settled(nextzone)" in w.observe()[0]            # it has passed


def test_room_to_speed_up_counts_on_the_lead_braking_and_room_to_keep_does_not():
    ego = Mover("e", "L", 100.0, dynamics_for("passenger", v=12.0, ego=True))
    p = Pair("lead:same_dir", "same_dir", "in_front", "overlap", 40.0, 0.0, ego.dyn, dynamics_for("passenger", v=13.0),
             role="lead")
    assert road_facts.gap_room([p], ego, 12.0, 13.9, 0.0)
    assert not road_facts.gap_room([p], ego, 12.0, 13.9, ego.dyn.accel)


def test_a_car_yields_only_from_another_lane_to_an_ego_with_the_priority():
    w = road_world.RoadWorld("cruise", 1)
    cw = next(z for z in w.map.zones if z.priority == "w_0" and "e_1" in z.lanes)
    j = next(z for z in w.map.zones if z.priority == "e_1")
    ahead = road_world.Agent(Mover("a", "e_1", cw.lanes["e_1"][0] - 10.0), 10.0)   # the ego's lane, at the crosswalk
    w.ego.m.s = cw.lanes["e_1"][0] - 40.0
    assert w._must_yield(ahead) is None                       # neither has the crosswalk: no yielding to the ego
    side = road_world.Agent(Mover("x", "c_0", j.lanes["c_0"][0] - 10.0), 10.0)
    w.ego.m.s = j.lanes["e_1"][0] - 40.0
    assert w._must_yield(side) == j.lanes["c_0"][0]           # the side road to the main road's ego
    same = road_world.Agent(Mover("b", "e_1", j.lanes["e_1"][0] - 10.0), 10.0)
    assert w._must_yield(same) is None                        # the ego's lane, the priority's: it drives on


def test_a_lead_slower_than_the_limit_but_faster_than_the_ego_is_no_slow_lead():
    # nina's SUMO run: the ego at 3.6 behind a lead at 6.7 (the limit 16.67) read lead_slow, so it never accelerated
    w = road_world.RoadWorld("cruise", 1)
    lead = Mover("l", "e_1", w.ego.m.s + 30.0)
    def facts(v_ego, v_lead):
        return road_facts.facts(w.map, w.ego.m, v_ego, [lead], Situation(), speeds={"l": v_lead})[0]
    assert "lead_ok" in facts(3.6, 6.7) and "lead_slow" not in facts(3.6, 6.7)    # gaining on it: speed up
    assert "lead_slow" in facts(6.7, 6.7)                                         # at its speed: follow or change
    assert "lead_slow" in facts(5.0, 6.7)                                         # within the margin


def test_the_merge_waits_when_the_other_lane_arrives_first():
    # road step 5 (yield_merge): the alternation alone gave the ego the turn while the ramp's car reached the line first
    w = road_world.RoadWorld("merge", 1)
    m = next(z for z in w.map.zones if z.priority is None and "r_0" in z.lanes)
    a_ego, a_ramp = m.lanes["e_0"][0], m.lanes["r_0"][0]
    w.ego.m.s = a_ego - 30.0
    def facts(ramp_gap):
        ramp = Mover("r", "r_0", a_ramp - ramp_gap)
        return road_facts.facts(w.map, w.ego.m, 11.0, [ramp], Situation(), speeds={"r": 11.0}, turn={m.id: None})[0]
    assert "wait_turn(nextzone)" in facts(10.0) and "turn(nextzone)" not in facts(10.0)    # it is there first
    assert "turn(nextzone)" in facts(45.0)                                                 # the ego is first


def test_the_side_just_left_is_not_settled():
    w = road_world.RoadWorld("cruise", 1)
    f = lambda lf, ch=None: road_facts.facts(w.map, w.ego.m, 11.0, [], Situation(), left_from=lf, changing=ch)[0]
    assert "settled(left)" in f(None) and "settled(right)" in f(None)
    assert "settled(left)" not in f(("left", 3.0)) and "settled(right)" in f(("left", 3.0))
    assert "settled(left)" in f(("left", road_facts.SETTLE_S + 1))
    assert not any(k.startswith("settled(") for k in f(None, "left"))                     # while a change runs


def test_what_the_other_cars_show_are_facts_and_a_settled_pair_is_released():
    """road-2 item 2: signalled(R, S) and settled_to(R, D) from what a bound car shows (a mover's signal / settled);
    a dangerous pair whose other settled into a lane not the ego's is left out of the fold, and one that settled
    into the ego's lane is decided afresh (its memory from the lane it came from dropped)."""
    w = road_world.RoadWorld("cruise", 1)
    ego = w.ego.m
    lead = Mover("l", "e_1", ego.s + 12.0, dynamics_for("passenger", v=4.0))
    side = Mover("s", "e_2", ego.s + 15.0, dynamics_for("passenger", v=11.0))
    side.signal, side.settled, lead.signal, lead.settled = "right", None, None, None
    f, binding, fold, _ = road_facts.facts(w.map, ego, 11.0, [lead, side], Situation(), speeds={"l": 4.0, "s": 11.0})
    role = {m: r for r, m in binding.items()}
    assert f["signalled(%s,right)" % role["s"]] == 1 and fold["resp_lon"] != "none"      # the slow lead: brake
    # the lead settles away (to e_0): its dangerous pair is released from the fold
    lead.lane, lead.settled = "e_0", "right"
    f, binding, fold, _ = road_facts.facts(w.map, ego, 11.0, [lead], Situation(), speeds={"l": 4.0})
    role = {m: r for r, m in binding.items()}
    assert f["settled_to(%s,right)" % role["l"]] == 1 and fold["resp_lon"] == "none"
    # a car settled INTO the ego's lane: "laterally safe before" (from its lane) no longer holds, Def 10 afresh
    sit = Situation()
    cut = Mover("c", "e_2", ego.s + 8.0, dynamics_for("passenger", v=6.0))
    cut.signal = cut.settled = None
    road_facts.facts(w.map, ego, 11.0, [cut], sit, speeds={"c": 6.0})                  # beside: laterally safe
    cut.lane = "e_1"
    _, _, fold, _ = road_facts.facts(w.map, ego, 11.0, [cut], sit, speeds={"c": 6.0})
    assert fold["resp_lon"] == "none"                                                   # the memory: lateral only
    cut.settled = "right"
    _, _, fold, _ = road_facts.facts(w.map, ego, 11.0, [cut], sit, speeds={"c": 6.0})
    assert fold["resp_lon"] != "none"                                                   # settled in: along the way
