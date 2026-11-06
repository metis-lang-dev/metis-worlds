"""The exerciser's levelk projection (LEVELK.md §2; levelk-intersection s-5be9291b step 2): off by default, on with
RoadWorld(levelk=True). Run in a python with libs/semantic-world installed (or on PYTHONPATH)."""
import sys
from pathlib import Path

WORLD = Path(__file__).resolve().parents[1] / "world"
sys.path.insert(0, str(WORLD))
import road_world  # noqa: E402

GAME = ("crosser(", "myopic(", "ego_myopic(", "reply(", "ego_reply(", "level_belief(", "believed(", "by_game(")


def ticks(levelk, n=120):
    w = road_world.RoadWorld("junction", seed=1, levelk=levelk)
    out = []
    for _ in range(n):
        out.append(dict(w.observe()[0]))
        w.step()
    return out


def test_off_by_default_no_game_atoms_and_by_rule_at_every_zone():
    """The law gates yield_zone and keep_cross by by_rule(nextzone): with the game off it is stated on every tick a zone is
    ahead (the architect's host contract, levelk step 1), and nothing of the game is."""
    assert not road_world.RoadWorld("junction", seed=1).game
    fs = ticks(False)
    assert not [a for f in fs for a in f if a.startswith(GAME)]
    zoned = [f for f in fs if any(a.startswith("zone_at(nextzone,") and a != "zone_at(nextzone,none)" for a in f)]
    assert zoned and all("by_rule(nextzone)" in f for f in zoned)


def test_with_the_game_on_every_zone_tick_has_one_reading():
    fs = ticks(True)
    zoned = [f for f in fs if any(a.startswith("zone_at(nextzone,") and a != "zone_at(nextzone,none)" for a in f)]
    assert zoned and all(("by_rule(nextzone)" in f) != ("by_game(nextzone)" in f) for f in zoned)


def test_the_crosser_who_keeps_coming_turns_the_zone_by_game():
    """junction: the main road has the way, the side road's car crosses without yielding (a scripted driver: level 0 in
    effect). The tables are stated for its role while it is bound; the rule's prediction (it yields) is contradicted tick
    after tick, the belief finds l0, and the zone turns by_game; by_rule before and after."""
    fs = ticks(True)
    bound = [f for f in fs if "believed(a1,l0)" in f or "believed(a1,l1)" in f or "believed(a1,l2)" in f]
    assert bound and all("myopic(a1,go)" in f or "myopic(a1,hold)" in f or "myopic(a1,yield)" in f for f in bound)
    assert all(sum(a.startswith("level_belief(a1,") for a in f) == 3 for f in bound)
    assert all("crosser(nextzone,a1)" in f and any(a.startswith("ego_myopic(a1,") for a in f) for f in bound)
    assert [f for f in fs if "holder(nextzone,a1)" in f]                      # it enters: the holder, no longer the crosser
    assert not [f for f in fs if "holder(nextzone,a1)" in f and "crosser(nextzone,a1)" in f]
    game = [f for f in fs if "by_game(nextzone)" in f]
    assert game and all("believed(a1,l0)" in f and "level_belief(a1,l0,high)" in f for f in game)
    assert "by_rule(nextzone)" in fs[0] and "by_rule(nextzone)" in fs[-1]
    assert not [f for f in fs if "by_game(nextzone)" in f and "by_rule(nextzone)" in f]
