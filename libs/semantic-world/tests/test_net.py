"""A SUMO net as the lane adapter's map (road-world s-e812715d step 3b-3d): the loader on two netconvert-made nets
(tests/nets/make_nets.sh: a four-way junction, a two-lane major road W-E at 13.89 m/s and a one-lane minor road S-N
at 8.33 m/s; once under right of way, once under a traffic light), the conflict zones from the internal lanes'
overlaps with their priority, the nearest zone on a route, the pairs a crossing makes, and the per-vClass dynamics."""
import math
import shutil
import subprocess
from pathlib import Path

import pytest

from semantic_world.lane import VCLASS, Mover, dynamics_for
from semantic_world.net import load_net
from semantic_world.situation import Situation

DATA = Path(__file__).resolve().parent / "nets"


@pytest.fixture(scope="module")
def cross():
    return load_net(DATA / "cross.net.xml")


@pytest.fixture(scope="module")
def tls():
    return load_net(DATA / "cross_tls.net.xml")


def test_the_lanes(cross):
    assert len(cross.lanes) == 28 and sum(l.internal for l in cross.lanes.values()) == 16
    w0, w1 = cross.lanes["WC_0"], cross.lanes["WC_1"]
    assert (w0.length, w0.speed, w0.width, w0.edge, w0.index) == (92.8, 13.89, 3.2, "WC", 0)
    assert cross.lanes["SC_0"].speed == 8.33
    assert len(w0.shape) == 2 and w0.shape[0][0] < w0.shape[1][0]                # westward to eastward
    assert (w0.left, w0.left_opposite, w0.right) == ("WC_1", False, None)       # same direction, by index
    assert (w1.left, w1.left_opposite, w1.right) == ("CW_1", True, "WC_0")      # the reverse edge's leftmost
    assert w0.succ == [":C_10_0", ":C_11_0"] and w1.succ == [":C_11_1", ":C_13_0"]
    i = cross.lanes[":C_11_0"]
    assert i.internal and i.junction == "C" and i.succ == ["CE_0"]


def test_the_junction_its_links_and_rows(cross):
    j = cross.junctions["C"]
    assert j.type == "priority" and j.inc_lanes == ["NC_0", "EC_0", "EC_1", "SC_0", "WC_0", "WC_1"]
    assert [(c.from_lane, c.dir) for c in j.links] == [
        ("NC_0", "r"), ("NC_0", "s"), ("NC_0", "l"), ("EC_0", "r"), ("EC_0", "s"), ("EC_1", "s"), ("EC_1", "l"),
        ("SC_0", "r"), ("SC_0", "s"), ("SC_0", "l"), ("WC_0", "r"), ("WC_0", "s"), ("WC_1", "s"), ("WC_1", "l")]
    assert j.links[11].state == "M" and j.links[8].state == "m"                   # major straight, minor straight
    assert j.links[6].chain == [":C_6_0", ":C_14_0"]                              # a left turn waits inside
    assert j.foes(8, 11) and j.yields(8, 11) and not j.yields(11, 8)              # the minor yields to the major
    assert not j.foes(11, 12)                                                     # two straight lanes side by side


def test_the_zones_and_their_priority(cross):
    zs = {z.id: z for z in cross.lanemap().zones}
    assert len(zs) == 34
    x = zs["C:8:11"]                                                              # minor straight across major straight
    (a0, a1), (b0, b1) = x.lanes[":C_8_0"], x.lanes[":C_11_0"]
    assert x.priority == ":C_11_0" and x.junction == "C" and x.link_of == {":C_8_0": 8, ":C_11_0": 11}
    # a right-angle crossing of two 3.2 m lanes: each side's stretch about the other's width plus its own
    assert 5.5 < a1 - a0 < 6.5 and 5.5 < b1 - b0 < 6.5
    assert zs["C:1:9"].priority == ":C_1_0"                                       # the left turn yields to oncoming
    assert zs["C:6:8"].priority == ":C_6_0"                                       # the major's left turn over the minor
    assert zs["C:0:4"].priority == ":C_4_0"                                       # a merge: the minor right turn yields
    m = zs["C:6:9"]
    assert ":C_14_0" in m.lanes                                                   # on the left turn's second part


def test_routes_ways_and_the_nearest_zone(cross):
    m = cross.lanemap()
    route = m.route_through(["WC_0", "CE_0"])
    assert route == ["WC_0", ":C_11_0", "CE_0"]
    assert m.route_through(["EC_1", "CS_0"]) == ["EC_1", ":C_6_0", ":C_14_0", "CS_0"]
    assert sorted(w[-1] for w in m.ways("SC_0")) == ["CE_0", "CN_0", "CW_1"]
    z, rl, d_in, d_out = m.nearest_zone(route, 70.0)
    assert rl == ":C_11_0" and math.isclose(d_in, 92.8 - 70.0 + z.lanes[rl][0])
    assert all(m.ahead(route, 70.0, rl2, zz.lanes[rl2][0]) >= d_in
               for zz in m.zones for rl2 in route if rl2 in zz.lanes)
    assert m.nearest_zone(route, 70.0, lane="NC_0") is None                       # no zone on the lane itself:
    assert m.nearest_zone(route, 70.0, ways=m.ways("NC_0")) is not None           # its ways cross the route


def ego_on(m, route, s, v=10.0):
    return Mover("ego", route[0], s, dynamics_for("passenger", v=v, lane=m.lanes[route[0]], ego=True), route=route)


def test_a_crossing_pair_merges_the_objects_ways(cross):
    m = cross.lanemap()
    route = m.route_through(["WC_0", "CE_0"])
    ego = ego_on(m, route, 70.0)
    x = Mover("x", "SC_0", 75.0, dynamics_for("passenger", v=8, lane=m.lanes["SC_0"]))
    (p,) = m.pairs(ego, [x], role_of=lambda o: o.id)
    assert p.id == "x:xing_ego_prio:C" and p.type == "xing_ego_prio"             # one pair for the junction
    # merged worst-case over its three ways: the least enter and the most leave of each side
    ins = [m.ahead(w, 75.0, l, z.lanes[l][0]) for z in m.zones for w in m.ways("SC_0") for l in w
           if l in z.lanes and any(r in z.lanes for r in route if r != l)]
    assert math.isclose(p.o_enter, min(i for i in ins if i is not None))
    assert p.d_enter < p.d_leave and p.o_enter < p.o_leave
    s = Situation().check([p])[0]
    assert s.dangerous and s.resp_lon == "brake_min"                              # never seen safe: brake
    far = Mover("x", "SC_0", 5.0, dynamics_for("passenger", v=8, lane=m.lanes["SC_0"]))
    s = Situation().check(m.pairs(ego_on(m, route, 5.0), [far]))[0]
    assert not s.dangerous and s.xing == "able_to_stop"                            # 85 m off: it can stop


def test_a_lead_on_the_routes_next_lane_is_followed(cross):
    m = cross.lanemap()
    route = m.route_through(["WC_0", "CE_0"])
    lead = Mover("lead", "CE_0", 10.0, dynamics_for("passenger", v=10, lane=m.lanes["CE_0"]))
    (p,) = m.pairs(ego_on(m, route, 70.0), [lead])
    assert p.type == "same_dir" and p.lon == "in_front" and p.lat == "overlap"
    assert math.isclose(p.d_lon, (92.8 - 70.0) + m.lanes[":C_11_0"].length + 10.0 - lead.length)


def test_the_traffic_light_decides_the_priority(tls):
    t = tls.tls["C"]
    assert [d for d, _ in t.phases] == [42, 3, 42, 3]
    assert t.state_at(0) == "rrrGGGgrrrGGGg" and t.state_at(50) == "GGgrrrrGGgrrrr" and t.state_at(91) == t.state_at(1)
    c = tls.junctions["C"].links[11]
    assert (c.tl, c.tl_link) == ("C", 11)
    m = tls.lanemap()
    route = m.route_through(["WC_0", "CE_0"])
    x = Mover("x", "SC_0", 75.0, dynamics_for("passenger", v=8, lane=m.lanes["SC_0"]))
    ego = ego_on(m, route, 70.0)
    assert m.pairs(ego, [x], lights={"C": t.state_at(0)})[0].type == "xing_ego_prio"   # W-E green
    assert m.pairs(ego, [x], lights={"C": t.state_at(50)})[0].type == "xing_obj_prio"  # S-N green
    z = next(z for z in m.zones if set(z.lanes) == {":C_8_0", ":C_11_0"})
    assert m.priority(z, {"C": "rrrrrrrrrrrrrr"}) == z.priority                   # equal ranks: the junction's rows


def test_the_vclass_dynamics_and_the_lanes_vcap(cross):
    m = cross.lanemap()
    car = dynamics_for("passenger", v=12.0, lane=m.lanes["WC_0"])
    assert (car.vmin, car.vmax, car.vcap, car.rho) == (12.0, 12.0, 13.89, 2.0)
    assert dynamics_for("passenger", v=12.0, lane=m.lanes["WC_0"], ego=True).rho == 1.0
    assert math.isclose(dynamics_for("passenger", v=12.0, lane=m.lanes["WC_0"], vcap_factor=1.1).vcap, 13.89 * 1.1)
    assert dynamics_for("bus", v=5.0).brake_max == VCLASS["truck"]["brake_max"]      # an alias
    assert dynamics_for("pedestrian", v=1.0, lane=m.lanes["WC_0"]).vcap == 1.39      # the class's top speed
    assert dynamics_for("bicycle", vmin=3.0, vmax=5.0).vcap == 5.56
    for k, p in VCLASS.items():
        assert p["brake_min_correct"] <= p["brake_min"] <= p["brake_max"], k
    assert m.vcap("SC_0") == 8.33 and m.vcap("SC_0", "pedestrian") == 1.39


@pytest.mark.skipif(shutil.which("netconvert") is None, reason="SUMO's netconvert is not installed")
def test_the_nets_are_netconvert_s(tmp_path):
    for f in ("cross.nod.xml", "cross_tls.nod.xml", "cross.edg.xml", "make_nets.sh"):
        shutil.copy(DATA / f, tmp_path / f)
    subprocess.run(["sh", str(tmp_path / "make_nets.sh")], check=True, capture_output=True)
    a, b = load_net(tmp_path / "cross_tls.net.xml"), load_net(DATA / "cross_tls.net.xml")
    assert {k: (v.length, v.succ) for k, v in a.lanes.items()} == {k: (v.length, v.succ) for k, v in b.lanes.items()}
    assert [z.lanes for z in a.zones()] == [z.lanes for z in b.zones()]
