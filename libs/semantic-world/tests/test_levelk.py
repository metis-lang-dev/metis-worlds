"""levelk: the host's tables and belief on the two-car unprotected left turn against oncoming (LEVELK.md §2, §4, §5).

The small world: the ego turns left across the oncoming lane (8 m to the zone at 5 m/s, 8 m inside it), the oncoming car goes
straight (20 m at 10 m/s, 6 m inside). Both are driven by the host's own game each tick: an other at level K plays
levelk.predicted(K); an ego at level J plays its best reply to an other at J-1 (J = 0: its myopic move); the adaptive ego plays
its best reply to the believed level."""
import pytest

from semantic_world import levelk as L
from semantic_world.situation import Dynamics, Pair

EGO = dict(d_in=8.0, d_out=16.0, v=5.0, accel=2.0, brake=8.0, cap=10.0)
ONC = dict(d_in=20.0, d_out=26.0, v=10.0, accel=2.0, brake=8.0, cap=14.0)


def side(b, s=0.0):
    return L.Side(b["d_in"] - s, b["d_out"] - s, b["v"], b["accel"], b["brake"], b["cap"])


def ego_move(t, k):
    if k == "l0":
        return t["ego_myopic"]
    return t["ego_reply"][L.predicted(t, L.LEVELS[L.LEVELS.index(k) - 1])]


def left_turn(k_ego, k_onc, ticks=60):
    """Runs the left turn; returns (contact, the ego cleared, the oncoming cleared, the final belief)."""
    e, o = dict(EGO, s=0.0), dict(ONC, s=0.0)
    belief, last_v, contact = dict(L.PRIOR), None, False
    for _ in range(ticks):
        E, O = side(e, e["s"]), side(o, o["s"])
        t = L.tables(E, O)
        if last_v is not None:
            belief = L.update(belief, t, L.observed_move(o["v"] - last_v, L.DT, o["v"], o["cap"]))
        last_v = o["v"]
        me = t["ego_reply"][L.predicted(t, L.believed(belief))] if k_ego == "adaptive" else ego_move(t, k_ego)
        mo = L.predicted(t, k_onc)
        for body, S, m in ((e, E, me), (o, O, mo)):
            body["v"] = min(body["cap"], max(0.0, body["v"] + L.accel_of(S, m) * L.DT))
            body["s"] += body["v"] * L.DT
        inside = lambda b: b["d_in"] <= b["s"] < b["d_out"]
        contact = contact or (inside(e) and inside(o))
    return contact, e["s"] >= e["d_out"], o["s"] >= o["d_out"], belief


# ── the tables ──
def test_the_levels_part_on_the_left_turn():
    t = L.tables(side(EGO), side(ONC))
    assert (t["myopic"], t["ego_myopic"]) == ("go", "go")          # level 0: each treats the other as standing, and goes
    assert t["reply"] == {"go": "yield", "hold": "yield", "yield": "go"}
    assert t["ego_reply"] == {"go": "yield", "hold": "yield", "yield": "go"}
    assert [L.predicted(t, k) for k in L.LEVELS] == ["go", "yield", "go"]


def test_no_conflict_far_out_every_level_goes():
    t = L.tables(side(EGO), side(dict(ONC, d_in=60.0, d_out=66.0)))
    assert [L.predicted(t, k) for k in L.LEVELS] == ["go", "go", "go"]


def test_a_body_past_the_zone_occupies_nothing():
    assert L.occupancy(L.Side(-7.0, -1.0, 10.0), "go")[0] == (None, None)
    assert L.occupancy(L.Side(-1.0, 4.0, 0.0), "hold")[0] == (0.0, float("inf"))     # standing inside: it stays


def test_yield_stops_short_of_the_entry():
    (t_in, _), s = L.occupancy(side(EGO), "yield")
    assert t_in is None and s < EGO["d_in"]


# ── every level pairing ──
# (ego, oncoming): level-k's own failures are two l0s (both go), an l2 ego against an l0 (it expects the l1 that yields) and
# two l1s (both yield: the deadlock); every other pairing clears without contact. The shield (rule 5) is not in this world.
PAIRINGS = {
    ("l0", "l0"): "contact", ("l0", "l1"): "clear", ("l0", "l2"): "clear",
    ("l1", "l0"): "clear", ("l1", "l1"): "deadlock", ("l1", "l2"): "clear",
    ("l2", "l0"): "contact", ("l2", "l1"): "clear", ("l2", "l2"): "clear",
}


@pytest.mark.parametrize("k_ego,k_onc", sorted(PAIRINGS))
def test_every_level_pairing(k_ego, k_onc):
    contact, e_clear, o_clear, _ = left_turn(k_ego, k_onc)
    got = "contact" if contact else "clear" if (e_clear and o_clear) else "deadlock"
    assert got == PAIRINGS[(k_ego, k_onc)]


@pytest.mark.parametrize("k_onc", L.LEVELS)
def test_the_believing_ego_clears_against_every_level(k_onc):
    contact, e_clear, o_clear, _ = left_turn("adaptive", k_onc)
    assert not contact and e_clear and o_clear


# ── the belief ──
def test_a_level_1_other_is_found():
    *_, b = left_turn("adaptive", "l1")
    assert L.believed(b) == "l1" and L.quantise(b["l1"]) == "high"
    assert not L.spread(b)


@pytest.mark.parametrize("k_onc", ["l0", "l2"])
def test_l0_and_l2_both_go_here_the_belief_stays_spread(k_onc):
    *_, b = left_turn("adaptive", k_onc)
    assert L.quantise(b["l1"]) == "low"
    assert abs(b["l0"] - b["l2"]) < 0.05 and L.spread(b)           # no level above mid: the rule's law holds
    assert L.zone_game("xing_same_prio", 0, b) == "by_rule"


def test_the_floor_follows_a_driver_who_changes():
    t = L.tables(side(EGO), side(ONC))
    b = dict(L.PRIOR)
    for _ in range(10):
        b = L.update(b, t, "yield")
    assert L.believed(b) == "l1" and min(b.values()) >= L.FLOOR / (1 + 3 * L.FLOOR)
    for n in range(1, 6):
        b = L.update(b, t, "go")
        if L.believed(b) != "l1":
            break
    assert L.believed(b) != "l1" and n <= 3


def test_observed_move_from_the_acceleration():
    assert L.observed_move(0.2) == "go" and L.observed_move(-0.2) == "yield" and L.observed_move(0.01) == "hold"
    assert L.observed_move(0.0, L.DT, 14.0, 14.0) == "go"            # at its cap going looks like holding


# ── the zone's reading ──
def test_zone_game():
    sure = {"l0": 0.05, "l1": 0.9, "l2": 0.05}
    spread = dict(L.PRIOR, l1=0.5, l0=0.25, l2=0.25)
    assert L.zone_game("xing_same_prio", 0, sure) == "by_game"                       # the rule is silent
    assert L.zone_game("xing_obj_prio", 0, sure) == "by_rule"                        # the rule settles it
    assert L.zone_game("xing_obj_prio", L.CONTRADICT_TICKS, sure) == "by_game"       # the holder hesitates
    assert L.zone_game("xing_obj_prio", L.CONTRADICT_TICKS, spread) == "by_rule"     # spread: the rule's law


def pair_at(o_s, o_v, kind="xing_obj_prio"):
    return Pair(id="p1", type=kind, role="a1",
                ego=Dynamics(vmax=5.0, accel=2.0, brake_max=8.0, vcap=10.0),
                obj=Dynamics(vmax=o_v, accel=2.0, brake_max=8.0, vcap=14.0),
                d_enter=8.0, d_leave=16.0, o_enter=20.0 - o_s, o_leave=26.0 - o_s)


def test_game_the_oncoming_hesitates_turns_by_game():
    """The left turn: the oncoming has the way (xing_obj_prio, the rule says it goes); it brakes tick after tick: the
    contradiction count reaches CONTRADICT_TICKS, the belief finds l1, the zone turns by_game."""
    g, s, v, out = L.Game(), 0.0, 10.0, None
    for i in range(8):
        out = g.step("p1", pair_at(s, v))
        v = max(0.0, v - 2.0 * L.DT * 5)                            # 10 m/s² of braking a tick: plainly yielding
        s += v * L.DT
    assert g.contra["p1"] >= L.CONTRADICT_TICKS
    assert out["believed"] == "l1" and out["zone"] == "by_game"


def test_game_the_holder_who_goes_stays_by_rule():
    g, s, v, out = L.Game(), 0.0, 10.0, None
    for i in range(8):
        out = g.step("p1", pair_at(s, v))
        v = min(14.0, v + 2.0 * L.DT)
        s += v * L.DT
    assert g.contra["p1"] == 0 and out["zone"] == "by_rule"
    g.forget(set())
    assert not g.belief and not g.last_v and not g.contra


def test_facts_use_the_drafts_preds():
    g = L.Game()
    out = g.step("p1", pair_at(0.0, 10.0))
    f = L.facts("a1", out)
    assert "myopic(a1,go)" in f and "ego_myopic(a1,go)" in f
    assert {"reply(a1,go,yield)", "reply(a1,hold,yield)", "reply(a1,yield,go)"} <= set(f)
    assert {"ego_reply(a1,go,yield)", "ego_reply(a1,hold,yield)", "ego_reply(a1,yield,go)"} <= set(f)
    assert not [k for k in f if k.startswith("ego_myopic(") and k.count(",") != 1]
    assert {"level_belief(a1,l0,low)", "level_belief(a1,l1,mid)", "level_belief(a1,l2,low)", "believed(a1,l1)"} <= set(f)
    assert len([k for k in f if k.startswith("level_belief(")]) == 3
