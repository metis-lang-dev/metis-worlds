"""The level-k intersection world (road/intersection; levelk-intersection s-5be9291b step 3, LEVELK.md §5): its geometry and
rule without signs, its level-k drivers, its measures, the cards' glue. No family here: the ego keeps its command (the
restrictor still caps it); the cards with the family are scenario_run.py check's (CI's catalog job)."""
import sys
from pathlib import Path

import pytest

ROAD = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROAD / "intersection"))
sys.path.insert(0, str(ROAD / "tools"))
import intersection as I  # noqa: E402


def zones(names):
    lm, _ = I.layout(names)
    return {tuple(sorted(z.lanes)): z.priority for z in lm.zones}


def test_the_left_turn_yields_to_the_oncoming_straight():
    assert zones(["S_W", "N_S"]) == {("N_S", "S_W"): "N_S"}


def test_right_before_left_goes_round_the_four_way():
    z = zones(["S_N", "E_W", "N_S", "W_E"])
    assert z == {("E_W", "S_N"): "E_W", ("E_W", "N_S"): "N_S", ("N_S", "W_E"): "W_E", ("S_N", "W_E"): "S_N"}
    assert ("N_S", "S_N") not in z and ("E_W", "W_E") not in z            # opposite straights never meet


def test_the_paths_turn_and_measure():
    _, p = I.layout(["S_W", "S_N", "S_E"])
    assert (p["S_W"].turn, p["S_N"].turn, p["S_E"].turn) == ("left", "straight", "right")
    assert p["S_N"].length == pytest.approx(2 * I.ARM + 2 * I.HALF, abs=0.3)
    x, y = p["S_N"].xy(I.ARM + I.HALF)
    assert x == pytest.approx(0.5 * I.LANE_W) and y == pytest.approx(0.0, abs=0.3)


def test_the_cards_load_with_their_levels():
    for name in ("ix-left-turn", "ix-four-way", "ix-crossing-gap"):
        c = I.load(name)
        assert c["map"]["world"] == "intersection" and I.levels_of(c) == ["l0", "l1", "l2"]
        assert c["source"]["suite"] == "ours" and "junction-priority" in c["tags"]
        assert c["verdict"]["sumo"]["status"] == "skip" and c["verdict"]["exerciser"]["status"] in ("pass", "fail")
        assert c["set"] == ("regression" if c["verdict"]["exerciser"]["status"] == "pass" else "working")


def play(name, ticks=200):
    w = I.IntersectionWorld(name)
    moves = []
    for _ in range(ticks):
        w.observe()
        w.step()
        moves.append({a.m.id: getattr(a, "move", None) for a in w.agents})
    return w, moves


@pytest.mark.parametrize("level,yields", [("l0", False), ("l1", True), ("l2", False)])
def test_the_oncoming_driver_plays_its_level(level, yields):
    """The oncoming car at the left turn, already at its cap (go and hold roll out alike there, the tie to hold): level 0
    never yields (the ego as standing), level 1 yields (it expects the ego's myopic go), level 2 never yields (it expects
    the ego to yield to a level-1 car)."""
    _, moves = play("ix-left-turn:" + level, 40)
    played = {m["onc"] for m in moves if m["onc"]}
    assert ("yield" in played) == yields and played <= {"go", "hold", "yield"}


def test_the_ego_s_game_runs_and_the_belief_finds_the_level_1_driver():
    w, _ = play("ix-left-turn:l1", 300)
    s = w.summary()
    assert s["drivers"]["onc"]["game_ticks"] > 0 and s["drivers"]["onc"]["believed"] == "l1"
    assert s["drivers"]["onc"]["converged"] is not None


def test_a_level_1_driver_against_a_waiting_ego_is_a_deadlock():
    """Without the family the ego only keeps (the restrictor stops it short); the level-1 oncoming car yields to it: both
    stand short of the zone, the zone empty: the deadlock measure counts it."""
    w, _ = play("ix-left-turn:l1", 300)
    s = w.summary()
    assert s["deadlock"] and s["deadlock_s"] >= I.DEADLOCK_S and not s["arrived"] and s["delay"] is None


def test_a_level_0_driver_goes_first_and_the_ego_clears_after():
    w, _ = play("ix-left-turn:l0", 500)
    s = w.summary()
    assert s["collisions"] == 0 and not s["deadlock"] and s["clear_t"] is not None and s["delay"] > 0
    assert s["drivers"]["onc"]["converged"] is not None and s["drivers"]["onc"]["believed"] == "l0"


def test_converged_is_the_first_tick_from_which_the_belief_stays_true():
    w = I.IntersectionWorld("ix-left-turn:l1")
    w.believed_log = {"onc": ["l1", "l0", "l1", "l1"]}
    assert w.converged("onc") == 2
    w.believed_log = {"onc": ["l1", "l0"]}
    assert w.converged("onc") is None


def test_drivers_on_one_path_keep_their_gap():
    w, _ = play("ix-crossing-gap:l1", 300)
    r1, r2 = (next(a for a in w.agents if a.m.id == k) for k in ("right1", "right2"))
    assert r1.m.s - r1.m.length - r2.m.s >= I.FOLLOW_M - 0.5


def test_check_reads_the_expect():
    card = I.load("ix-left-turn")
    assert I.check(card, {"collisions": 0, "violations": 0, "arrived": True, "deadlock": False}) == []
    got = I.check(card, {"collisions": 2, "violations": 0, "arrived": False, "deadlock": True, "deadlock_s": 30.0})
    assert got == ["collisions 2 > 0", "not arrived", "deadlock 30.0 s"]


def test_the_runner_knows_a_world_card():
    import scenario_run as R
    c = R.load(ROAD / "catalog" / "ours" / "ix-four-way.yaml")
    assert R.on_world(c) and not R.on_net(c) and R.card_id(c) == "ours/ix-four-way"
    assert R.skipped(c, "sumo") and R.expected(c, "exerciser") in ("pass", "fail")


def test_road_host_builds_the_world_from_an_ix_run():
    sys.path.insert(0, str(ROAD / "world"))
    import road_host
    w = road_host.new_world({"scenario": "ix:ix-four-way:l2", "seed": 1})
    assert isinstance(w, I.IntersectionWorld) and w.level == "l2" and w.game is not None
    assert set(w.level_of) == {"east", "north", "west"} and w.name == "ix:ix-four-way:l2"


def test_a_holder_that_restarts_after_the_commitment_is_attributed_the_contact(monkeypatch):
    """WAIVER RULING 2's world rule: the ego (commanded to go) commits past the standing level-1 holder after rho of visible
    approach; the holder then starts (forced to level 0): the contacts are the holder's restart after its waiver, kept in the
    row as collisions_partner, not the ego's (collisions_own 0, check passes). The geometric window is switched off so that
    the commitment, not the window, releases the ego."""
    from semantic_world import situation as S
    monkeypatch.setattr(S, "waiver_window", lambda p, stood: False)
    w, forced = I.IntersectionWorld("ix-left-turn:l1"), None
    for _ in range(500):
        w.command(("accel", None), life=2)
        w.observe()
        w.step()
        if w.committed_at and forced is None:
            w.level_of["onc"], forced = "l0", w.t
        if w.arrived():
            break
    s = w.summary()
    assert forced is not None and s["arrived"]
    assert s["collisions_partner"] > 0 and s["collisions_own"] == 0
    assert I.check(I.load("ix-left-turn"), s) == []


def test_without_a_restart_the_committed_ego_clears_with_no_contact(monkeypatch):
    from semantic_world import situation as S
    monkeypatch.setattr(S, "waiver_window", lambda p, stood: False)
    w = I.IntersectionWorld("ix-left-turn:l1")
    for _ in range(500):
        w.command(("accel", None), life=2)
        w.observe()
        w.step()
        if w.arrived():
            break
    s = w.summary()
    assert w.committed_at and s["arrived"] and s["collisions"] == 0 and not s["deadlock"]
