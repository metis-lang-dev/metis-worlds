"""semantic-world step 3a, the user's amendment: the reachable-set motion model (RSS's worst case over the adapter's
graph) and the association gate (two beasts alike: a sighting is the instance whose predicted mass is near it,
else a new one)."""
from semantic_world import bayes, dungeon
from semantic_world.grid import GridMap, name


def line(n):
    """A path graph 0 - 1 - … - n-1."""
    return lambda p: [q for q in (p - 1, p + 1) if 0 <= q < n]


def test_the_kinematic_interval():
    assert bayes.interval(1.0, vmin=0, vmax=1) == (0.0, 1.0)                    # a beast: anything up to a cell
    lo, hi = bayes.interval(2.0, vmin=10, vmax=10, accel=2, brake=5)            # a car at 10 m/s, 2 s
    assert lo == 10.0 and hi == 24.0                                            # braked from 10 at 5: stops in 2 s, 10 m; sped up at 2: 24 m
    assert bayes.interval(2.0, vmin=10, vmax=10, accel=2, vcap=11)[1] == 21.75   # capped at 11 m/s after 0.5 s
    assert bayes.travel(10, 5, brake=5) == 10.0                                  # stopped after 2 s, still at 10 m


def test_the_reachable_set_spreads_the_mass_over_the_interval():
    m = bayes.reachable(line(9), vmin=0, vmax=2)
    bel = m({4: 1.0}, 1.0)
    assert sorted(bel) == [2, 3, 4, 5, 6] and abs(sum(bel.values()) - 1) < 1e-9   # within two steps, evenly
    assert abs(bel[2] - 0.2) < 1e-9
    ring = bayes.reachable(line(9), vmin=2, vmax=2)({4: 1.0}, 1.0)
    assert sorted(ring) == [2, 6]                                                 # it cannot stop: exactly two away
    assert bayes.reachable(line(9), vmax=2)({4: 1.0}, 0.0) == {4: 1.0}           # dt 0: where it was
    assert bayes.mass_within({0: 0.5, 5: 0.5}, line(9), 1, 1.0) == 0.5            # P(at cell 1 within a step)


def test_two_newts_alike_keep_their_instances_and_a_third_is_new(tmp_path):
    lv = dungeon.corner()
    a, b = dungeon.Monster("newt", (1, 1)), dungeon.Monster("newt", (1, 5))
    sim = dungeon.Sim(lv, [a, b], seed=1)
    m = GridMap.build(str(tmp_path / "m.json"), (lv.w, lv.h), cells=lv.cells())
    who = {}
    for t in range(6):
        if t == 3:                                                                # a third newt, far from both predictions
            c = dungeon.Monster("newt", (6, 1))
            sim.monsters.append(c)
        m.cycle(sim.perceive(), models=m.models())
        seen = m.load()["_beasts_seen"]
        for mo in sim.monsters:
            inst = next(n for n, cell in seen.items() if cell == name(*mo.pos))
            assert who.setdefault(id(mo), inst) == inst, (t, mo.pos, inst)       # never swapped
        sim.act("wait")
    assert sorted(who.values()) == ["newt", "newt_2", "newt_3"]
    assert who[id(c)] == "newt_3"
    d = m.load()
    assert {n: d["things"][n].get("of", n) for n in who.values()} == {"newt": "newt", "newt_2": "newt", "newt_3": "newt"}


def test_the_gate_takes_the_likelier_instance_greedily():
    d = {"things": {"newt": {}, "newt_2": {"of": "newt"}},
         "belief": {"newt": {2: 0.7, 3: 0.3}, "newt_2": {3: 0.6, 4: 0.4}}}
    out = bayes.associate(d, [("newt", 3), ("newt", 2)], line(9), lambda t: 0.0)  # radius 0: the mass on the cell itself
    assert out == [("newt_2", 3), ("newt", 2)]
    out = bayes.associate(d, [("newt", 8)], line(9), lambda t: 1.0)               # nobody's mass near 8: a new newt
    assert out == [("newt_3", 8)]


def test_the_grid_offers_the_reachable_set_as_a_beasts_model(tmp_path):
    lv = dungeon.corner()
    m = GridMap.build(str(tmp_path / "m.json"), (lv.w, lv.h), cells=lv.cells())
    d = m.load()
    d["agent"]["at"] = "c3_3"
    d["things"]["newt"] = {"in": None, "kind": "beast"}
    d["belief"]["newt"] = {"c10_3": 1.0}
    m.save()
    bel = m.models(reach=True)["newt"]({"c10_3": 1.0}, 1.0)
    assert sorted(bel) == ["c10_3", "c11_3", "c9_3"]             # a corridor: itself and the two cells beside it
    chase = m.models()["newt"]({"c10_3": 1.0}, 1.0)
    assert max(chase, key=chase.get) == "c9_3"                    # the chase leans toward the ego; the set does not
    assert m.hazard("newt", horizon=7.0) == 1.0 and m.hazard("newt", horizon=2.0) == 0.0
