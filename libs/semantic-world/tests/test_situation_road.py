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
    assert s.dangerous and s.resp_lon == "brake_max"      # no brake stops it short of the conflict 6 m on: the yielder at its
                                                          # hardest still (cr-harvest L1, rule 5's symmetry)
    # never seen safe: the same answer as with the history above (the rule 5 ruling: the present decides, the memory
    # is the blame's record only)
    s = Situation().check([xpair("xing_ego_prio", 5.0, 15.0, 6.0, 16.0, obj_vmin=0)])[0]
    assert s.dangerous and s.xing_before is None and s.resp_lon == "none"


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


# -- a crossing with both standing: Town01 seed 1's stand, where no brake answers and the pair stays dangerous for ever -----

PASSENGER = dict(accel=3.5, brake_min=4.0, brake_max=8.0, rho=2.0, min_dist=1.0)   # the road's: a standing one's stated stop is 14.125 m


def standing(kind, d_enter=0.0, d_leave=10.34, o_enter=6.75, o_leave=25.75, ego_v=0.0, obj_v=0.0):
    return Pair("x:" + kind, kind, d_enter=d_enter, d_leave=d_leave, o_enter=o_enter, o_leave=o_leave, role="a1",
                ego=Dynamics(vmin=ego_v, vmax=ego_v, **PASSENGER), obj=Dynamics(vmin=obj_v, vmax=obj_v, **PASSENGER))


def test_both_standing_the_way_goes_and_the_other_stays():
    # the ego stands inside the zone holding the way, calm_5 stands short of it (the log's numbers at tick 300)
    ego = Dynamics(vmin=0.0, vmax=0.0, **PASSENGER)
    s = Situation().check([standing("xing_ego_prio")])[0]
    assert s.dangerous and s.resp_stand == "drive_away" and s.resp_lon == "none"
    f = Situation.fold([s], ego)
    assert f["resp_lon"] == "none" and f["resp_unst"] == "drive_away" and f["drive_away_sector"] == 0
    # the same pair from calm_5's seat: it stays, and nothing brakes
    s = Situation().check([standing("xing_obj_prio", d_enter=6.75, d_leave=25.75, o_enter=0.0, o_leave=10.34)])[0]
    assert s.dangerous and s.resp_stand == "stay" and s.resp_lon == "none"
    f = Situation.fold([s], ego)
    assert f["resp_lon"] == "none" and f["lon_range"][1] == 0.0 and "resp_unst" not in f


def test_a_person_with_the_way_is_never_driven_away_from():
    # the chair's people hold priority by its ports: a chair standing by a standing person stays, whatever its place
    s = Situation().check([standing("xing_obj_prio")])[0]
    assert s.resp_stand == "stay" and "resp_unst" not in Situation.fold([s], Dynamics(vmin=0.0, vmax=0.0, **PASSENGER))


def test_no_priority_the_one_inside_goes():
    assert Situation().check([standing("xing_same_prio")])[0].resp_stand == "drive_away"
    outside = standing("xing_same_prio", d_enter=6.75, d_leave=25.75, o_enter=0.0, o_leave=10.34)
    assert Situation().check([outside])[0].resp_stand == "stay"


def test_a_drive_away_holds_while_the_other_stands_and_ends_when_it_moves():
    sit = Situation()
    assert sit.check([standing("xing_ego_prio")])[0].resp_stand == "drive_away"
    assert sit.check([standing("xing_ego_prio", ego_v=2.0)])[0].resp_stand == "drive_away"      # moving now: not back to a brake
    assert sit.check([standing("xing_ego_prio", ego_v=2.0, obj_v=1.0)])[0].resp_stand == "none"  # it moves after all
    assert Situation().check([standing("xing_ego_prio", ego_v=2.0)])[0].resp_stand == "none"     # never stood: the usual response


def test_one_pair_that_stays_or_brakes_holds_a_drive_away():
    ego = Dynamics(vmin=0.0, vmax=0.0, **PASSENGER)
    go = Situation().check([standing("xing_ego_prio")])[0]
    stay = Situation().check([standing("xing_obj_prio")])[0]
    f = Situation.fold([go, stay], ego)
    assert "resp_unst" not in f and f["lon_range"][1] == 0.0



# -- the YIELDER's escalation (cr-harvest s-f4e297da, L1: rule 5's symmetry for xing_obj_prio) ----------------------------

def test_the_yielder_brakes_min_while_that_stops_it_short_then_max_and_holds_it():
    """brake_min while that stops the ego short of the conflict's entry, brake_max while only that does (ESCALATED holds it),
    brake_max still when neither does; never a brake_min that enters. At 10 m/s: brake_min stops in 12.5 + 1, brake_max in 6.25 + 1."""
    s = Situation().check([xpair("xing_obj_prio", 16.0, 26.0, 2.0, 12.0)])[0]
    assert s.dangerous and s.resp_lon == "brake_min"                                   # 13.5 < 16
    sit = Situation()
    s = sit.check([xpair("xing_obj_prio", 10.0, 20.0, 2.0, 12.0)])[0]
    assert s.dangerous and s.resp_lon == "brake_max"                                   # 7.25 < 10 <= 13.5
    s = sit.check([xpair("xing_obj_prio", 16.0, 26.0, 2.0, 12.0)])[0]
    assert s.resp_lon == "brake_max"                                                   # ESCALATED holds it while dangerous
    s = Situation().check([xpair("xing_obj_prio", 0.0, 10.0, 2.0, 12.0)])[0]
    assert s.resp_lon == "brake_max"                                                   # inside the conflict: hardest still


def test_the_harvests_yielder_geometry_asks_brake_max_where_brake_min_entered():
    """ARG_Carcarana-10_2_T-1 (the 13): the ego at 9.8 m/s with a priority crosser, the conflict 11.3 m on: brake_min (12.0 + 1)
    enters it, brake_max (6.0 + 1) stops short: the fold asks brake_max, where it asked brake_min and the ego was hit at 1.9 m/s."""
    s = Situation().check([xpair("xing_obj_prio", 11.3, 21.3, 3.0, 13.0, ego_v=9.8)])[0]
    assert s.dangerous and s.resp_lon == "brake_max"

# -- the ZIPPER (cr-harvest s-f4e297da, L2: Hennigsdorf-18_1) ------------------------------------------------------------

def lead_pair(d_lon, ego_v, lead_v):
    return Pair("z:same_dir", "same_dir", "in_front", "overlap", d_lon, 0.0, Dynamics(vmin=ego_v, vmax=ego_v, **CAR),
                Dynamics(vmin=lead_v, vmax=lead_v, **CAR), role="lead")


def test_a_lead_whose_rear_has_not_cleared_the_egos_front_asks_brake_max_whatever_dv_says():
    """Hennigsdorf-18_1: the lead merged from a parallel internal lane, its rear beside the ego's front (d_lon 0), faster (7.5
    against 6.0 m/s): brake_max, where the fold asked brake_min (stops_behind holds for a faster lead) and the two touched."""
    sit = Situation()
    s = sit.check([lead_pair(0.0, 6.0, 7.5)])[0]
    assert s.dangerous and s.resp_lon == "brake_max"
    s = sit.check([lead_pair(0.4, 6.0, 7.5)])[0]                       # the gap opening, still under the floor: held
    assert s.dangerous and s.resp_lon == "brake_max"


def test_a_faster_lead_with_a_gap_stays_at_brake_min():
    s = Situation().check([lead_pair(2.0, 6.0, 7.5)])[0]
    assert not s.dangerous or s.resp_lon in ("none", "brake_min")
