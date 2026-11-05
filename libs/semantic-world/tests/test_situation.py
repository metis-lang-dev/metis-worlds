"""The situation layer (semantic-world step 3a): RSS's safe distances, the memory of the axis safe before, the
responses and the fold, the facts over roles; and design §4's cases 4 and 5 on the exerciser through a rule
program (metispy's REPL, when it is importable)."""
import importlib.util
import sys
from pathlib import Path

import pytest

from semantic_world import situation as S
from semantic_world.situation import Dynamics, Pair, Situation

CAR = dict(rho=0.5, accel=2.0, brake_min=4.0, brake_max=8.0, brake_min_correct=3.0, min_dist=1.0)


def test_lemma_2_same_direction():
    f, l = Dynamics(vmin=10, vmax=10, **CAR), Dynamics(vmin=10, vmax=10, **CAR)
    # follower: 10·0.5 + 0.5·2·0.25 + 11²/8 = 5 + 0.25 + 15.125; leader stops in 10²/16 = 6.25; + 1
    assert abs(S.safe_same_dir(f, l) - (20.375 - 6.25 + 1.0)) < 1e-9
    assert S.safe_same_dir(Dynamics(vmax=1, rho=1, min_dist=1), Dynamics(vmax=0, rho=1)) == 2.0   # a dungeon: a step + a cell


def test_lemma_3_opposite_direction_uses_the_correct_lanes_gentler_brake():
    a, b = Dynamics(vmax=10, **CAR), Dynamics(vmax=10, **CAR)
    d = S.safe_opp_dir(a, b)
    assert abs(d - (S.stated(10, 2, 0.5, 3.0) + S.stated(10, 2, 0.5, 4.0) + 1.0)) < 1e-9
    assert S.safe_opp_dir(Dynamics(vmax=1, rho=1, min_dist=1), Dynamics(vmax=1, rho=1, min_dist=1)) == 3.0   # both reaches + a cell


def test_the_crossing_cascade():
    ego, obj = Dynamics(vmax=10, **CAR), Dynamics(vmax=10, **CAR)
    far = Pair("x", "xing_obj_prio", d_enter=40.0, d_leave=50.0, o_enter=5.0, o_leave=15.0, ego=ego, obj=obj)
    assert S.check_long(far)[0]                                      # the ego, without priority, can stop before it
    near = Pair("x", "xing_obj_prio", d_enter=10.0, d_leave=20.0, o_enter=5.0, o_leave=15.0, ego=ego, obj=obj)
    assert not S.check_long(near)[0]
    assert S.able_to_stop(ego, 40.0) and not S.able_to_stop(ego, 10.0)


def lane_pair(gap, kind="opp_dir"):
    ego = Dynamics(vmax=1, rho=1, min_dist=1)
    obj = Dynamics(vmax=1 if kind == "opp_dir" else 0, rho=1, min_dist=1)
    return Pair("newt:" + kind, kind, "in_front", "overlap", float(gap), 0.0, ego, obj, lateral_room=False, role="b1")


def test_the_memory_of_the_axis_safe_before_is_frozen_while_dangerous():
    sit = Situation()
    s = sit.check([lane_pair(6)])[0]
    assert s.safe_long and not s.safe_lat and not s.dangerous and s.before == (True, False)
    s = sit.check([lane_pair(3)])[0]                                  # a one-wide lane: no lateral room, gap 3 ≤ 3
    assert s.dangerous and s.before == (True, False) and s.resp_lon == "brake_min_correct" and s.resp_lat == "none"
    s = sit.check([lane_pair(2)])[0]
    assert s.before == (True, False)                                  # frozen at the last safe cycle
    sit.check([])                                                     # the pair gone: forgotten
    s = sit.check([lane_pair(2)])[0]
    assert s.dangerous and s.before is None and s.resp_lon == "brake_min_correct"   # appeared dangerous: brake


def test_lateral_room_and_the_responses_by_the_axis_safe_before():
    ego, obj = Dynamics(vmax=1, rho=1, min_dist=1), Dynamics(vmax=1, rho=1, min_dist=1, lat_v=1)
    beside = lambda g: Pair("n:opp_dir", "opp_dir", "in_front", "at_left", float(g), float(g), ego, obj, lateral_room=True, role="b1")
    sit = Situation()
    s = sit.check([beside(2)])[0]                                     # too close along, but laterally clear: safe
    assert not s.safe_long and s.safe_lat and not s.dangerous and s.before == (False, True)
    s = sit.check([beside(1)])[0]
    assert s.dangerous and s.resp_lat == "brake_min" and s.resp_lon == "none"   # laterally safe before: brake across


def test_the_fold_is_the_star_shape():
    ego = Dynamics(vmax=10, **CAR)
    st = [S.State("a", "same_dir", "o1", False, False, True, (True, False), "brake_min", "none", 1, 2),
          S.State("b", "opp_dir", "o2", False, False, True, (True, False), "brake_min_correct", "brake_min", 1, 2),
          S.State("c", "same_dir", "o3", True, False, False, (True, False), "none", "none", 9, 2)]
    f = Situation.fold(st, ego)
    assert f["resp_lon"] == "brake_min" and f["resp_lat"] == "brake_min"     # the most severe wins
    assert f["lon_range"] == [-8.0, -4.0]                             # min of the maxima: brake at least brake_min
    assert f["dangerous"] == ["o1", "o2"]
    facts = Situation.facts(st, f)
    assert facts == {"type(o1,same_dir)": 1, "dangerous(o1)": 1, "safe_before(o1,long)": 1, "resp(o1,brake_min)": 1,
                     "type(o2,opp_dir)": 1, "dangerous(o2)": 1, "safe_before(o2,long)": 1, "resp(o2,brake_min_correct)": 1,
                     "type(o3,same_dir)": 1, "safe_long(o3)": 1, "resp_lon(brake_min)": 1, "resp_lat(brake_min)": 1}


HAVE_METIS = importlib.util.find_spec("metis") is not None


@pytest.mark.skipif(not HAVE_METIS, reason="the cases' rule program runs in metispy's REPL")
def test_cases_4_and_5_on_the_exerciser(tmp_path):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "examples"))
    import situation_cases as C
    r4 = C.run(tmp_path, 4)
    assert r4["won"]
    said = r4["said"]
    stop = next(x for x in r4["rows"] if x["fold"] == "brake_min_correct")
    p = stop["pairs"][0]
    assert p["d_lon"] == p["d_safe"] == 3.0 and tuple(p["before"]) == (True, False)   # stopped at the gap of both reaches
    assert "The newt is coming down the lane at me: I stop and fall back to the open." in said
    assert "The newt is beside me in the open: I fight it." in said and "The way is clear: I go on." in said
    fight = next(x for x in r4["rows"] if "fight_it" in " ".join(x["fired"]))
    assert fight["ego"] in {"c%d_%d" % (x, y) for x in range(1, 6) for y in range(1, 6)}   # in room A, the passing place
    r5 = C.run(tmp_path, 5)
    assert r5["won"]
    waits = [x for x in r5["rows"] if any(f.startswith("give_way") for f in x["fired"])]
    assert len(waits) == 3 and waits[0]["pairs"][0]["d_lon"] == 2.0          # yielded at the safe gap, three turns
    back = next(x for x in r5["rows"] if any(f.startswith("back_off") for f in x["fired"]))
    on = next(x for x in r5["rows"] if any(f.startswith("go_on") for f in x["fired"]))
    assert on["ego"] == "c10_3" and on["t"] > back["t"]                        # backed off to the junction, then round
    assert any(x["ego"] == "c15_8" for x in r5["rows"])                        # the way round (y = 8)



def test_a_priority_holder_responds_once_the_other_cannot_stop():
    """road-2 item 1 (RSS rule 5: right of way is given, not taken; the junction_rb timeline): at a crossing the ego
    has priority over, the onset decision (Def 18: the other was able to stop) keeps the blame the other's and the
    response none while the other can still stop at its PROPER response (brake_min) from its speed; once it is past that
    last point the ego brakes (brake_min) and holds it while dangerous — brake_max while only that stops it short (the rule 5
    ruling, road-scenarios s-e23be780), none once neither does or inside (it clears the zone: never a hold in the
    conflict), and released once the other stops."""
    from semantic_world.situation import Dynamics, Pair, Situation
    ego = Dynamics(vmin=16.67, vmax=16.67, accel=2.0, brake_min=4.0, brake_max=8.0, rho=0.5, min_dist=1.0)
    def pair(o_v, o_enter, d_enter):        # the ego stops short in 16.67²/8 + 1 = 35.7 m
        obj = Dynamics(vmin=o_v, vmax=o_v, accel=2.0, brake_min=4.0, brake_max=8.0, rho=0.5, min_dist=1.0)
        return Pair("x:xing_ego_prio:j", "xing_ego_prio", ego=ego, obj=obj,
                    d_enter=d_enter, d_leave=d_enter + 8.0, o_enter=o_enter, o_leave=o_enter + 8.0)
    sit = Situation()
    [s] = sit.check([pair(2.0, 20.0, 90.0)])                   # it can stop: safe (Def 17 case 1)
    assert not s.dangerous and s.xing == "able_to_stop" and s.resp_lon == "none"
    [s] = sit.check([pair(6.0, 6.0, 60.0)])                    # dangerous, but at brake_min from 6 m/s it stops in
    assert s.dangerous and s.xing_before[0] == "able_to_stop" and s.resp_lon == "none"   # 5.5 m < 6: the other's turn
    [s] = sit.check([pair(10.0, 5.0, 50.0)])                   # 10 m/s, 5 m off: past its last stop (13.5 m)
    assert s.dangerous and s.resp_lon == "brake_min" and s.xing_before[0] == "able_to_stop"   # blame unchanged
    [s] = sit.check([pair(3.0, 4.0, 45.0)])                    # it brakes late, still coming: held
    assert s.dangerous and s.resp_lon == "brake_min"
    [s] = sit.check([pair(0.0, 0.5, 42.0)])                    # it has stopped at its line: released, it yields
    assert s.dangerous and s.resp_lon == "none" and not sit.escalated
    # no hold inside the zone, nor once the ego can no longer stop short of it: it clears the zone
    sit = Situation()
    sit.check([pair(2.0, 20.0, 90.0)])
    [s] = sit.check([pair(10.0, 5.0, 50.0)])
    assert s.resp_lon == "brake_min"
    [s] = sit.check([pair(10.0, 3.0, 20.0)])                   # 20 m < 35.7, but > 18.4 at brake_max: only that stops it
    assert s.dangerous and s.resp_lon == "brake_max" and sit.escalated     # short (the ruling: escalated, held)
    [s] = sit.check([pair(10.0, 2.0, 15.0)])                   # 15 m < 18.4: neither stops it short: it clears the zone
    assert s.dangerous and s.resp_lon == "none" and not sit.escalated
    [s] = sit.check([pair(10.0, 1.0, 0.0)])                    # inside the zone
    assert s.resp_lon == "none"


def test_rule_5_answers_from_the_present_whatever_the_memory():
    """The rule 5 ruling (road-scenarios s-e23be780, record 503be4): the priority holder's response depends on the PRESENT
    only; the blame facts (xing_before) stay recorded and never gate it, so a crosser first seen dangerous ('before none')
    and one seen safe first ('able_to_stop before') get the same answer on the same geometry. A standing crosser at its
    line has not run it: none."""
    from semantic_world.situation import Dynamics, Pair, Situation
    ego = Dynamics(vmin=13.9, vmax=13.9, accel=2.0, brake_min=4.0, brake_max=8.0, rho=0.5, min_dist=1.0)
    def pair(o_v, o_enter, d_enter):
        obj = Dynamics(vmin=o_v, vmax=o_v, accel=2.0, brake_min=4.0, brake_max=8.0, rho=0.5, min_dist=1.0)
        return Pair("x:xing_ego_prio:j", "xing_ego_prio", ego=ego, obj=obj,
                    d_enter=d_enter, d_leave=d_enter + 8.0, o_enter=o_enter, o_leave=o_enter + 8.0)
    seen_safe = Situation()
    seen_safe.check([pair(2.0, 40.0, 90.0)])
    for geometry, want in [((16.7, 40.0, 60.0), "none"),          # OVTP: 16.7 m/s 40 m off stops in 35.9 m: may still yield
                           ((16.7, 30.0, 40.0), "brake_min"),     # 30 m off: past its proper stop; the ego stops in 25.2 m
                           ((16.7, 30.0, 20.0), "brake_max")]:    # the ego 20 m off: only brake_max (13.1 m) stops it short
        first_seen = Situation()
        [a] = first_seen.check([pair(*geometry)])
        [b] = Situation(xmemory=dict(seen_safe.xmemory)).check([pair(*geometry)])
        assert a.dangerous and b.dangerous and a.resp_lon == b.resp_lon == want, (geometry, a.resp_lon, b.resp_lon)
    [s] = Situation().check([pair(0.0, 0.5, 30.0)])               # standing at its line: it yields
    assert s.resp_lon == "none"


def test_a_cut_in_that_became_the_lead_is_braked_for_whatever_the_blame():
    """The rule 5 ruling (3), records 40f229 / 87279b: a same-direction car that was laterally safe and then cut in
    (the lateral distance unsafe last: the blame its), now the ego's lead at an unsafe distance: the ego brakes along
    the way (brake_min), the lateral response as before."""
    from semantic_world.situation import Dynamics, Pair, Situation
    ego = Dynamics(vmin=11.1, vmax=11.1, accel=2.0, brake_min=4.0, brake_max=8.0, rho=0.5, min_dist=1.0)
    obj = Dynamics(vmin=5.6, vmax=5.6, accel=2.0, brake_min=4.0, brake_max=8.0, rho=0.5, min_dist=1.0)
    sit = Situation(memory={"c:same_dir": (False, True)})         # long unsafe, laterally safe: beside, then it cut in
    [s] = sit.check([Pair("c:same_dir", "same_dir", "in_front", "overlap", 8.0, 0.0, ego, obj)])
    assert s.dangerous and s.resp_lon == "brake_min"
    side = Situation(memory={"c:same_dir": (False, True)})        # still beside (not the lead): lateral only, as before
    [t] = side.check([Pair("c:same_dir", "same_dir", "in_front", "at_left", 8.0, 0.2, ego, obj)])
    assert t.resp_lon == "none"
