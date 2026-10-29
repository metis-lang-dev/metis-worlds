"""RSS's unstructured constellation (wc-world s-db2f8e59 step 2c; DESIGN v5 §12 position 2): free-space pairs as
ad-rss-lib's, trajectory sets as discs, the drive-away response's headings quantised into SECTORS."""
import math

from semantic_world.lane import dynamics_for
from semantic_world.situation import Pair, Situation, away_sectors, brake_set


def pair(gap, bearing, ev=0.0, ov=0.0, pid="w:unstructured", role="vru1"):
    return Pair(pid, "unstructured", d_lon=gap, ego=dynamics_for("pedestrian", v=ev, ego=True),
                obj=dynamics_for("pedestrian", v=ov), role=role, bearing=bearing)


def test_two_standing_too_close_drive_away_from_each_other():
    sit = Situation()
    st, = sit.check([pair(0.2, 0.0)])                       # the walker east, both standing, closer than the floors
    assert st.dangerous and st.resp_unst == "drive_away" and st.resp_lon == "none"
    f = Situation.fold([st], dynamics_for("pedestrian", ego=True))
    assert f["resp_unst"] == "drive_away" and f["drive_away_sector"] == 4    # due west: farthest from east
    facts = Situation.facts([st], f)
    assert facts["resp_unst(drive_away)"] == facts["drive_away_sector(s4)"] == facts["type(vru1,unstructured)"] == 1


def test_who_may_drive_on_is_the_memory_of_the_last_safe_cycle():
    sit = Situation()
    far, = sit.check([pair(10.0, 0.0, ev=0.5, ov=1.2)])      # safe: the brake sets far apart, the continue set too
    assert not far.dangerous and far.resp_unst == "none"
    near, = sit.check([pair(0.5, 0.0, ev=0.5, ov=1.2)])      # now dangerous: the ego's continue set was clear before
    assert near.dangerous and near.resp_unst == "continue" and near.resp_lon == "none"
    other = Situation()
    sudden, = other.check([pair(0.5, 0.0, ev=0.5, ov=1.2, pid="x:unstructured")])     # never safe: brake
    assert sudden.resp_unst == "brake" and sudden.resp_lon == "brake_min"
    f = Situation.fold([sudden], dynamics_for("pedestrian", v=0.5, ego=True))
    assert f["resp_unst"] == "brake" and f["resp_lon"] == "brake_min" and f["drive_away_sector"] is None


def test_nowhere_to_drive_away_is_a_brake():
    sit = Situation()
    a, b = sit.check([pair(0.2, 0.0, pid="e:unstructured", role="vru1"),
                      pair(0.2, math.pi, pid="w:unstructured", role="vru2")])
    assert a.resp_unst == b.resp_unst == "drive_away"
    assert away_sectors([0.0, math.pi]) == []
    f = Situation.fold([a, b], dynamics_for("pedestrian", ego=True))
    assert f["resp_unst"] == "brake" and f["resp_lon"] == "brake_min" and f["drive_away_sector"] is None


def test_a_road_without_free_space_says_nothing_new():
    sit = Situation()
    st, = sit.check([Pair("c:same_dir", "same_dir", "in_front", "overlap", 50.0, 0.0,
                          dynamics_for("passenger", v=10.0, ego=True), dynamics_for("passenger", v=10.0), role="lead")])
    f = Situation.fold([st], dynamics_for("passenger", v=10.0, ego=True))
    facts = Situation.facts([st], f)
    assert "resp_unst" not in f and not any(a.startswith(("resp_unst", "drive_away")) for a in facts)


def test_the_brake_set_grows_with_speed():
    assert brake_set(dynamics_for("pedestrian", v=0.0)) < brake_set(dynamics_for("pedestrian", v=1.4)) \
        < brake_set(dynamics_for("bicycle", v=5.0))
