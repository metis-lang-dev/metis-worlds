"""nav-belief s-794cf4c1 step 1: the categorical intent belief on synthetic trajectories — a chaser reaches
hostile_sure within k observations, a wanderer never does, k unseen steps spread the support along the corridor
graph, a beast lost and seen again is re-associated to its track; the line of sight and the per-step table."""
import random

from semantic_world import intent
from semantic_world.grid import GridMap, name

K_SURE = 4                                   # a chaser's sightings to hostile_sure, from the uniform prior


def corridor(n=15):
    cells = [name(x, 0) for x in range(n)]
    nb = lambda c: [name(x, 0) for x in (int(c[1:].split("_")[0]) - 1, int(c[1:].split("_")[0]) + 1) if 0 <= x < n]
    return cells, nb, (lambda c: int(c[1:].split("_")[0]))


def run(path, p=None):
    cells, nb, dist = corridor()
    ms = intent.models(nb, dist)
    p = p or intent.prior(None)
    trace = []
    for a, b in zip(path, path[1:]):
        p = intent.update(p, name(a, 0), name(b, 0), 1, ms)
        trace.append(intent.level(p))
    return p, trace


def test_a_chaser_reaches_hostile_sure_within_k():
    p, trace = run([12, 11, 10, 9, 8, 7, 6, 5])
    assert "hostile_sure" in trace[:K_SURE], trace
    assert p["hostile"] >= intent.HOSTILE_SURE


def test_a_wanderer_stays_below_sure():
    """A random walk (holding a third of the time) is not a chase: of 200 walks of twelve steps, fewer than 5% ever
    reach hostile_sure (a walk that happens to come four or five steps running does: no model rules it out), and
    most end below maybe."""
    rnd = random.Random(1)
    ever, low = 0, 0
    for _ in range(200):
        x, path = 10, [10]
        for _ in range(12):
            x = min(14, max(1, x + (0 if rnd.random() < 0.3 else rnd.choice((-1, 1)))))
            path.append(x)
        p, trace = run(path)
        ever += "hostile_sure" in trace
        low += p["hostile"] < intent.HOSTILE_MAYBE
    assert ever < 10 and low > 100, (ever, low)


def test_a_fleer_is_fleeing():
    p, _ = run([5, 6, 7, 8, 9, 10])
    assert max(p, key=p.get) == "fleeing"


def test_the_prior_by_species_and_uniform_otherwise():
    table = {"jackal": {"hostile": 0.8, "wandering": 0.2}}
    assert intent.prior("jackal", table) == {"hostile": 0.8, "wandering": 0.2, "fleeing": 0.0}
    assert intent.prior("unknown", table) == {i: 1 / 3 for i in intent.INTENTS}


def level(tmp_path, rows, **kw):
    """A GridMap over ROWS ('.' floor, ' ' rock), cells known (all mode), intents on with LOS."""
    cells = {name(x, y): "floor" for y, r in enumerate(rows) for x, ch in enumerate(r) if ch == "."}
    m = GridMap.build(str(tmp_path / "map.json"), (max(map(len, rows)), len(rows)), cells=cells, intents={"los": True, **kw})
    return m


def test_k_unseen_steps_spread_the_support(tmp_path):
    """A beast seen once, then out of sight: each predicted turn spreads its position belief along the corridor
    graph (the support grows, never shrinks while unseen)."""
    m = level(tmp_path, ["...       ", "  .       ", "  ........", "      .   ", "      .   "])
    m.cycle({"agent_at(c0_0)", "monster(gnome,c7_2)"}, 1, m.models())     # seen (the sighting atom places it)
    assert "c7_2" not in m.los(m.load(), "c0_0")                          # … in a corridor out of the ego's line
    sizes = []
    for _ in range(5):
        m.cycle({"agent_at(c0_0)"}, 1, m.models())
        bel = m.load()["belief"].get("gnome") or {}
        sizes.append(len([c for c, p in bel.items() if p >= GridMap.SUPPORT]))
    assert sizes == sorted(sizes) and sizes[-1] > sizes[0], sizes


def test_line_of_sight_is_straight_and_blocked_by_rock(tmp_path):
    m = level(tmp_path, ["..........", "   .      ", "   .      "])
    d = m.load()
    v = set(m.los(d, "c0_0"))
    assert "c9_0" in v                                   # down the corridor
    assert "c3_2" not in v                               # round the corner, behind rock


def test_re_acquisition_keeps_the_track(tmp_path):
    """A chaser seen, lost round a corner, seen again within its reach: the same track (not a second jackal), its
    intent carried on."""
    m = level(tmp_path, ["...........", "    .      ", "    .      ", "    .      "])
    for c in ("c9_0", "c8_0", "c7_0"):
        m.cycle({"agent_at(c0_0)", "monster(jackal,%s)" % c}, 1, m.models())
    p0 = m.load()["intent"]["jackal"]["p"]["hostile"]
    m.cycle({"agent_at(c0_0)"}, 1, m.models())          # out of sight a turn (no sighting)
    m.cycle({"agent_at(c0_0)", "monster(jackal,c5_0)"}, 1, m.models())
    d = m.load()
    assert sorted(t for t in d["things"] if d["things"][t].get("kind") == "beast") == ["jackal"]
    assert d["intent"]["jackal"]["seen"] == 4 and d["intent"]["jackal"]["p"]["hostile"] >= p0


def test_the_per_step_table(tmp_path):
    """The table's rows: per step the hazard closing(B, I) per intent (a chaser's hostile hazard high and held, its
    fleeing one low), the categorical intent beside them, the marginals for the levels; rows are ticks."""
    m = level(tmp_path, ["...........", "    .      ", "    .      "])
    for c in ("c7_0", "c6_0", "c5_0", "c4_0", "c3_0"):
        m.cycle({"agent_at(c0_0)", "monster(jackal,%s)" % c}, 1, m.models())
    t = m.predict_table(4)
    assert t["h"] == 4 and t["unit"] == "tick" and t["beasts"] == ["jackal"] and len(t["rows"]) == 4
    hz = [r["closing(jackal,hostile)"] for r in t["rows"]]
    assert all(x > 0.8 for x in hz[:2]), hz                  # a chaser's hazard: it steps nearer, step after step
    assert all(r["closing(jackal,fleeing)"] < 0.2 for r in t["rows"])
    assert t["intent"]["jackal"]["hostile"] >= intent.HOSTILE_SURE and set(t["intent"]["jackal"]) == set(intent.INTENTS)
    near = [r[0] for r in t["marginals"]["near"]]
    assert near == sorted(near) and near[-1] > near[0]


def test_the_contact_hazard_follows_the_ego_along_its_path(tmp_path):
    """nav-belief step 3: contact(B, I), the first passage of B to within CONTACT of the ego per intent. A chaser four
    cells away reaches a standing ego within a few steps under hostile, rarely under fleeing; an ego walking
    toward it meets it sooner."""
    m = level(tmp_path, ["...........", "    .      ", "    .      "])
    for c in ("c8_0", "c7_0", "c6_0", "c5_0"):
        m.cycle({"agent_at(c0_0)", "monster(jackal,%s)" % c}, 1, m.models())
    stand = m.predict_table(4)
    walk = m.predict_table(4, path=["c0_0", "c1_0", "c2_0", "c3_0", "c4_0"])
    survive = lambda t, i: __import__("math").prod(1 - r["contact(jackal,%s)" % i] for r in t["rows"])
    assert 1 - survive(stand, "hostile") > 0.5 > 1 - survive(stand, "fleeing")
    assert survive(walk, "hostile") < survive(stand, "hostile")       # walking into it: contact sooner
    assert all(0.0 <= r["contact(jackal,wandering)"] <= 1.0 for r in walk["rows"])
    assert [k for k in stand["rows"][0] if k.startswith("closing(")] == [k for k in walk["rows"][0] if k.startswith("closing(")]
