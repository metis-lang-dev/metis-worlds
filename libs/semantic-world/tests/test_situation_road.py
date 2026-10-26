"""The situation layer's road fixes (road-world s-e812715d step 3a), each against RSS's formulas (refs/rss-model.md;
Shalev-Shwartz, Shammah, Shashua, arXiv:1708.06374; ad-rss-lib): vcap in the stated braking distance, the latest
leave braking at brake_max, Def 17 case 2 and Def 18's memory at a crossing, the lateral left/right split and the
per-pair lateral response in facts()."""
import math

from semantic_world import situation as S
from semantic_world.situation import Dynamics, Pair, Situation

CAR = dict(rho=0.5, accel=2.0, brake_min=4.0, brake_max=8.0, brake_min_correct=3.0, min_dist=1.0)


# -- vcap: ad-rss max_speed_on_acceleration ----------------------------------------------------------------------

def test_vcap_stops_the_acceleration_in_the_response_time():
    # uncapped: 10·0.5 + ½·2·0.25 + 11²/8 = 5.25 + 15.125
    assert math.isclose(S.stated(10, 2, 0.5, 4), 20.375)
    # capped at 10.5: up to 10.5 in 0.25 s (2.5 + 0.0625), then 0.25 s at 10.5 (2.625); then 10.5²/8 = 13.78125
    assert math.isclose(S.stated(10, 2, 0.5, 4, vcap=10.5), 2.5 + 0.0625 + 2.625 + 13.78125)
    # already above the cap: no acceleration at all: 12·0.5 + 12²/8
    assert math.isclose(S.stated(12, 2, 0.5, 4, vcap=10), 6 + 18)
    # a cap the response time never reaches changes nothing
    assert math.isclose(S.stated(10, 2, 0.5, 4, vcap=20), 20.375)


def test_vcap_reaches_lemma_2_through_the_dynamics():
    f = Dynamics(vmin=10, vmax=10, vcap=10.5, **CAR)
    l = Dynamics(vmin=10, vmax=10, **CAR)
    assert math.isclose(S.safe_same_dir(f, l), (2.5 + 0.0625 + 2.625 + 13.78125) - 6.25 + 1.0)
    assert S.safe_same_dir(f, l) < S.safe_same_dir(Dynamics(vmin=10, vmax=10, **CAR), l)


def test_time_to_with_a_cap():
    assert math.isclose(S.time_to(30, 10, 2, vcap=12), 1.0 + (30 - 11) / 12)   # 1 s to 12 (11 m), then at 12
    assert math.isclose(S.time_to(30, 15, 2, vcap=12), 2.0)                    # above the cap: no acceleration


# -- the latest leave: braking at brake_max from the least speed ------------------------------------------------

def test_the_latest_leave_brakes_at_brake_max():
    assert S.time_to_brake(10, 10, 8) is None                                  # stops in 6.25 m: may never leave
    assert math.isclose(S.time_to_brake(5, 10, 8), (10 - math.sqrt(100 - 80)) / 8)
    assert S.time_to_brake(5, 10, None) is None                                # stops at will
    assert S.time_to_brake(0, 0, 8) == 0.0


def test_no_time_overlap_with_braking_and_vcap():
    ego, obj = Dynamics(vmin=10, vmax=10, **CAR), Dynamics(vmin=10, vmax=10, **CAR)
    # the object leaves 5 m on: at the latest in 0.691 s; the ego arrives in 30 m: at the earliest 2.62 s
    p = Pair("x", "xing_same_prio", d_enter=30.0, d_leave=40.0, o_enter=0.0, o_leave=5.0, ego=ego, obj=obj)
    assert S.no_time_overlap(p)
    # 10 m to leave: it may stop inside (6.25 m), so it never surely leaves: overlap
    p = Pair("x", "xing_same_prio", d_enter=30.0, d_leave=40.0, o_enter=0.0, o_leave=10.0, ego=ego, obj=obj)
    assert not S.no_time_overlap(p)
    # the constant-speed reading (the old code) would have said 1 s and called it safe; RSS's says it is not
    capped = Pair("x", "xing_same_prio", d_enter=30.0, d_leave=40.0, o_enter=0.0, o_leave=5.0,
                  ego=Dynamics(vmin=10, vmax=10, vcap=10, **CAR), obj=obj)
    assert S.no_time_overlap(capped)                                           # 3 s at the cap, still after 0.69 s


# -- Def 17 case 2 and Def 18's memory at a crossing -------------------------------------------------------------

def xpair(kind, d_enter, d_leave, o_enter, o_leave, ego_v=10, obj_vmin=10):
    return Pair("x:" + kind, kind, d_enter=d_enter, d_leave=d_leave, o_enter=o_enter, o_leave=o_leave,
                ego=Dynamics(vmin=10, vmax=ego_v, **CAR), obj=Dynamics(vmin=obj_vmin, vmax=10, **CAR), role="c1")


def test_def_17_case_2_the_one_in_front_leads():
    # neither can stop before the zone (stated 20.375 + 1), the object leaves it 2 m on, the ego enters in 20:
    # the object is wholly in front (Def 16), 18 m apart through the zone against Lemma 2's 15.125 m
    p = xpair("xing_same_prio", 20.0, 30.0, 0.0, 2.0)
    assert S.ego_in_front(p) is False
    safe, ds, case, front = S.xing_case(p)
    assert safe and case == "safe_long" and front is False and math.isclose(ds, 15.125)
    # the ego in front: the object follows it through
    q = xpair("xing_same_prio", 0.0, 2.0, 20.0, 30.0)
    assert S.xing_case(q)[2:] == ("safe_long", True)
    # neither wholly in front: case 2 does not apply
    assert S.ego_in_front(xpair("xing_same_prio", 5.0, 15.0, 5.0, 15.0)) is None


def test_def_18_the_case_before_decides_the_response():
    sit = Situation()
    s = sit.check([xpair("xing_same_prio", 20.0, 30.0, 0.0, 2.0)])[0]                  # case 2, the object in front
    assert not s.dangerous and s.xing == "safe_long" and s.xing_before == ("safe_long", False)
    # closer, and the object slowing (vmin 0: Lemma 2 now 21.375 m against 13): it may stop in the zone: no case
    s = sit.check([xpair("xing_same_prio", 14.0, 24.0, 0.0, 1.0, obj_vmin=0)])[0]
    assert s.dangerous and s.xing is None and s.xing_before == ("safe_long", False)
    assert (s.resp_lon, s.resp_lat) == ("brake_min", "none")                   # the rear one brakes
    f = Situation.facts([s], Situation.fold([s], Dynamics(vmax=10, **CAR)), detail=True)
    assert f["xing_before(c1,safe_long)"] == 1 and "xing_case(c1,safe_long)" not in f
    # the ego in front before: it drives on
    sit = Situation()
    sit.check([xpair("xing_same_prio", 0.0, 2.0, 20.0, 30.0)])
    s = sit.check([Pair("x:xing_same_prio", "xing_same_prio", d_enter=0.0, d_leave=24.0, o_enter=14.0, o_leave=24.0,
                        ego=Dynamics(vmin=0, vmax=10, **CAR), obj=Dynamics(vmin=10, vmax=10, **CAR), role="c1")])[0]
    assert s.dangerous and s.xing_before == ("safe_long", True) and s.resp_lon == "none"


def test_def_18_able_to_stop_with_priority():
    sit = Situation()
    # the ego has priority; the object, 30 m off, can stop (21.375 < 30): case 1
    s = sit.check([xpair("xing_ego_prio", 10.0, 20.0, 30.0, 40.0)])[0]
    assert not s.dangerous and s.xing == "able_to_stop"
    s = sit.check([xpair("xing_ego_prio", 5.0, 15.0, 6.0, 16.0, obj_vmin=0)])[0]
    assert s.dangerous and s.xing_before[0] == "able_to_stop" and s.resp_lon == "none"   # the other must brake
    # the same history without priority: the ego brakes
    sit = Situation()
    sit.check([xpair("xing_obj_prio", 30.0, 40.0, 10.0, 20.0)])
    s = sit.check([xpair("xing_obj_prio", 6.0, 16.0, 5.0, 15.0, obj_vmin=0)])[0]
    assert s.dangerous and s.resp_lon == "brake_min"
    # never seen safe: brake
    s = Situation().check([xpair("xing_ego_prio", 5.0, 15.0, 6.0, 16.0, obj_vmin=0)])[0]
    assert s.dangerous and s.xing_before is None and s.resp_lon == "brake_min"


# -- the lateral left/right split, and the per-pair lateral response ---------------------------------------------

def side_pair(lat, d_lat, d_lon=1.0):
    ego = Dynamics(vmax=10, lat_v=0.5, lat_accel=0.2, lat_brake=0.8, mu=0.1, **CAR)
    obj = Dynamics(vmax=10, lat_v=0.5, lat_accel=0.2, lat_brake=0.8, mu=0.1, **CAR)
    return Pair("c:same_dir", "same_dir", "overlap", lat, d_lon, d_lat, ego, obj, role="c1")


def test_lemma_4_on_the_side_the_object_is_on():
    # each side: 0.5·0.5 + ½·0.2·0.25 + (0.5 + 0.1)²/(2·0.8) = 0.25 + 0.025 + 0.225 = 0.5; two sides + ½(0.1 + 0.1)
    assert math.isclose(S.safe_lat_dist(side_pair("at_left", 0).obj, side_pair("at_left", 0).ego), 1.1)
    assert S.check_lat_sides(side_pair("at_left", 0.9)) == (False, True)       # too close on the left only
    assert S.check_lat_sides(side_pair("at_right", 0.9)) == (True, False)
    assert S.check_lat_sides(side_pair("at_left", 1.2)) == (True, True)
    assert S.check_lat_sides(side_pair("overlap", 0.0)) == (False, False)


def test_the_lateral_response_brakes_toward_the_object_only():
    sit = Situation()
    s = sit.check([side_pair("at_left", 1.2, d_lon=0.0)])[0]                   # beside, laterally clear
    assert not s.dangerous and s.before == (False, True)
    s = sit.check([side_pair("at_left", 0.9, d_lon=0.0)])[0]                   # closing in from the left
    assert s.dangerous and (s.resp_lon, s.resp_lat) == ("none", "brake_min")   # laterally safe before: lateral
    assert (s.resp_lat_left, s.resp_lat_right) == ("brake_min", "none")
    fold = Situation.fold([s], Dynamics(vmax=10, lat_accel=0.2, lat_brake=0.8, **CAR))
    assert fold["resp_lat_left"] == "brake_min" and fold["resp_lat_right"] == "none"
    assert fold["lat_left_max"] == -0.8 and fold["lat_right_max"] == 0.2
    f = Situation.facts([s], fold, detail=True)
    assert f["resp_side(c1,left,brake_min)"] == 1 and "resp_side(c1,right,brake_min)" not in f
    assert f["safe_lat_right(c1)"] == 1 and "safe_lat_left(c1)" not in f
    assert f["resp_lat_left(brake_min)"] == 1 and f["resp_lat_right(none)"] == 1
    plain = Situation.facts([s], fold)                                          # without detail: as before
    assert not any(k.startswith(("safe_lat_left", "safe_lat_right", "resp_side", "resp_lat_left", "xing"))
                   for k in plain)
