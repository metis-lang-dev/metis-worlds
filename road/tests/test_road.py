"""The road exerciser's pieces (road-world s-e812715d step 2): the commands and the restrictor (restrict.py, every road
host's), the facts over roles (road_facts.py), the world (road_world.py). No Live here: the tree demo is
road/experiments/road_tree.py. Run with libs/semantic-world on the path."""
import sys
from pathlib import Path

import pytest

WORLD = Path(__file__).resolve().parents[1] / "world"
sys.path.insert(0, str(WORLD))
import restrict  # noqa: E402
import road_facts  # noqa: E402
import road_world  # noqa: E402
from semantic_world.lane import Mover, dynamics_for  # noqa: E402
from semantic_world.situation import Situation  # noqa: E402


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
