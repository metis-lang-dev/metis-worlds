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
    response none while the other can still stop braking its hardest from its speed; once it is past that last point
    the ego brakes (brake_min) and holds it while dangerous — only while it can itself still stop short of the zone
    (inside, or past that, it clears the zone: never a hold in the conflict), and released once the other stops."""
    from semantic_world.situation import Dynamics, Pair, Situation
    ego = Dynamics(vmin=16.67, vmax=16.67, accel=2.0, brake_min=4.0, brake_max=8.0, rho=0.5, min_dist=1.0)
    def pair(o_v, o_enter, d_enter):        # the ego stops short in 16.67²/8 + 1 = 35.7 m
        obj = Dynamics(vmin=o_v, vmax=o_v, accel=2.0, brake_min=4.0, brake_max=8.0, rho=0.5, min_dist=1.0)
        return Pair("x:xing_ego_prio:j", "xing_ego_prio", ego=ego, obj=obj,
                    d_enter=d_enter, d_leave=d_enter + 8.0, o_enter=o_enter, o_leave=o_enter + 8.0)
    sit = Situation()
    [s] = sit.check([pair(2.0, 20.0, 90.0)])                   # it can stop: safe (Def 17 case 1)
    assert not s.dangerous and s.xing == "able_to_stop" and s.resp_lon == "none"
    [s] = sit.check([pair(6.0, 6.0, 60.0)])                    # dangerous, but braking hard from 6 m/s it stops in
    assert s.dangerous and s.xing_before[0] == "able_to_stop" and s.resp_lon == "none"   # 3.25 m < 6: the other's turn
    [s] = sit.check([pair(10.0, 5.0, 50.0)])                   # 10 m/s, 5 m off: past its last stop (7.25 m)
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
    [s] = sit.check([pair(10.0, 3.0, 20.0)])                   # 20 m < 35.7: past stopping short
    assert s.dangerous and s.resp_lon == "none" and not sit.escalated
    [s] = sit.check([pair(10.0, 1.0, 0.0)])                    # inside the zone
    assert s.resp_lon == "none"
