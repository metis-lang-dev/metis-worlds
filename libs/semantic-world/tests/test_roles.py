"""The road roles (road-world s-e812715d step 2, opus's spec): `LaneMap.roles` binds lead, follower, the
neighbours' leads and followers, a1..ak and vru1..vruj around the ego, and `zone_roles` the next zone and the role
holding it, on the four-way net of test_net (tests/nets/cross.net.xml)."""
from pathlib import Path

import pytest

from semantic_world.lane import Mover, dynamics_for
from semantic_world.net import load_net

DATA = Path(__file__).resolve().parent / "nets"


@pytest.fixture(scope="module")
def m():
    return load_net(DATA / "cross.net.xml").lanemap()


def mover(m, id, lane, s, v=10.0, vclass="passenger", route=None, ego=False):
    return Mover(id, lane, s, dynamics_for(vclass, v=v, lane=m.lanes[lane], ego=ego), route=route, vclass=vclass)


def ego_on(m, lanes, s):
    route = m.route_through(lanes)
    return mover(m, "ego", route[0], s, route=route, ego=True)


def test_the_roles_around_an_ego(m):
    ego = ego_on(m, ["WC_0", "CE_0"], 50.0)
    ms = [mover(m, "lead", "WC_0", 70.0), mover(m, "far", "CE_0", 10.0),          # ahead on the way: its lane, later
          mover(m, "fol", "WC_0", 30.0), mover(m, "fol2", "WC_0", 10.0),          # behind on its lane
          mover(m, "ll", "WC_1", 60.0), mover(m, "fl", "WC_1", 45.0),             # the left neighbour, same direction
          mover(m, "x", "SC_0", 75.0, v=8), mover(m, "on", "CW_1", 50.0),         # a crossing; going away: not relevant
          mover(m, "pedb", "SC_0", 80.0, v=1, vclass="pedestrian"), mover(m, "peda", "SC_0", 10.0, v=1, vclass="pedestrian"),
          ego]                                                                    # the ego itself takes none
    r = m.roles(ego, ms)
    ps = {p.id.split(":")[0]: p for p in m.pairs(ego, ms[:-1])}
    assert ps["on"].type == "not_relevant" and ps["x"].type.startswith("xing")
    assert ps["fol2"].d_lon < ps["x"].d_enter < ps["far"].d_lon                     # the a* order
    assert ps["pedb"].d_enter == ps["peda"].d_enter and ps["pedb"].o_enter < ps["peda"].o_enter   # one junction: by o_enter
    assert r == {"lead": "lead", "follower": "fol", "leadleft": "ll", "followleft": "fl",
                 "a1": "fol2", "a2": "x", "a3": "far", "vru1": "pedb"}
    assert m.roles(ego, ms, k=1, j=2) == {"lead": "lead", "follower": "fol", "leadleft": "ll", "followleft": "fl",
                                          "a1": "fol2", "vru1": "pedb", "vru2": "peda"}


def test_the_right_neighbour_an_opposite_left_ties_and_a_vru_ahead(m):
    ego = ego_on(m, ["WC_1", "CE_1"], 50.0)                                       # its left: CW_1, the other way
    ms = [mover(m, "on", "CW_1", 40.0), mover(m, "rl", "WC_0", 50.0), mover(m, "rf", "WC_0", 49.0)]
    r = m.roles(ego, ms)
    assert "leadleft" not in r and "followleft" not in r
    assert (r["leadright"], r["followright"]) == ("rl", "rf")                      # s equal to the ego's: ahead
    tie = [mover(m, "m2", "WC_1", 60.0), mover(m, "m1", "WC_1", 60.0)]
    assert m.roles(ego, tie) == {"lead": "m1", "a1": "m2"}                         # ties by mover id
    bike = [mover(m, "car", "WC_1", 80.0), mover(m, "bike", "WC_1", 60.0, v=4, vclass="bicycle")]
    assert m.roles(ego, bike) == {"lead": "bike", "a1": "car"}                     # the first role that fits


def test_the_next_zone_and_its_holder(m):
    ego = ego_on(m, ["WC_0", "CE_0"], 50.0)
    z, rl, _, _ = m.nearest_zone(ego.route, ego.s)
    (ol,) = set(z.lanes) - {rl}
    a, b = z.lanes[ol]
    inside, before = mover(m, "in", ol, 0.5 * (a + b)), mover(m, "before", ol, a - 0.1)
    r = m.roles(ego, [inside, before])
    assert {r[k] for k in ("a1", "a2")} == {"in", "before"}
    holder = next(k for k, v in r.items() if v == "in")
    assert m.zone_roles(ego, [inside, before], r) == {"nextzone": z.id, "holder": holder}
    assert m.zone_roles(ego, [before], m.roles(ego, [before])) == {"nextzone": z.id, "holder": None}
    edge = mover(m, "edge", ol, b + inside.length - 0.1)                          # its rear still inside
    assert m.zone_roles(ego, [edge], m.roles(ego, [edge]))["holder"] is not None
    assert m.zone_roles(ego, [inside], {}) == {"nextzone": z.id, "holder": None}  # inside, but no role
    past = ego_on(m, ["CE_0"], 10.0)
    assert m.zone_roles(past, [inside], r) == {"nextzone": None, "holder": None}
