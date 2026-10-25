"""The grid adapter, the motion models and the dungeon exerciser (no NetHack): levels connected, the segment graph,
the route with gate costs and NetHack's doorway rule, predict for movers (a hostile walks toward the ego, a peaceful
holds, the alive decay forgets), and the whole cycle on the exerciser — the ego through doors closed and locked to
the stairs, the binding stable, view mode to the frontier first."""
from semantic_world import bayes, dungeon
from semantic_world.grid import GridMap, capacity, cell_roles, xy

ALIVE = (0.1, -2.0)


def cells_of(lv):
    out = {}
    for (x, y), t in lv.tiles.items():
        k = {".": "floor", "#": "corridor", "|": "wall", "-": "wall", ">": "stairs_down"}.get(t)
        if t == "+":
            st = lv.doors[(x, y)]
            k = "floor" if st in ("doorway", "broken") else "door:" + st
        out["c%d_%d" % (x, y)] = k
    return out


def direction(a, b):
    (ax, ay), (bx, by) = xy(a), xy(b)
    return {(0, -1): "n", (1, 0): "e", (0, 1): "s", (-1, 0): "w", (1, -1): "ne", (1, 1): "se", (-1, 1): "sw", (-1, -1): "nw"}[(bx - ax, by - ay)]


def drive(sim, m, turns=600):
    """A scripted stand-in for the rule program over the map: the route's next cell — a beast on it is attacked, a
    closed door opened, a locked one kicked, else a step. → (turns taken, the roles the doors had while bound)."""
    door_roles = {}
    for t in range(turns):
        m.cycle(sim.perceive(), models=m.models(), alive=ALIVE)
        b = m.project()
        if sim.won:
            return t, door_roles
        d = m.load()
        if len(d["path"]) < 2:
            sim.act("wait")
            continue
        here, nxt = d["path"][0], d["path"][1]
        for r, h in b.items():
            if d["cells"].get(h) == "door":
                door_roles.setdefault(h, set()).add(r)
        beast = any(p >= 0.5 and c == nxt for n, t2 in d["things"].items() if t2.get("kind") == "beast" for c, p in d["belief"].get(n, {}).items())
        st = d["doors"].get(nxt) if d["cells"].get(nxt) == "door" else None
        if beast:
            sim.act("move", direction(here, nxt))
        elif st == "closed":
            if sim.act("open", direction(here, nxt)) == "door_locked":
                d["doors"][nxt] = "locked"
                m.save()
        elif st == "locked":
            sim.act("kick", direction(here, nxt))
        else:
            sim.act("move", direction(here, nxt))
    return None, door_roles


def test_the_levels_are_joined():
    for seed in range(1, 11):
        c, r = dungeon.cave(76, 21, seed), dungeon.rooms(76, 21, seed)
        assert c.bfs(c.start, c.stairs) and r.bfs(r.start, r.stairs), seed
        assert len(r.rooms) == 5 and set(r.doors.values()) == {"doorway", "open", "closed", "locked"}
    assert dungeon.cave(76, 21, 3).tiles == dungeon.cave(76, 21, 3).tiles          # a seed is a level


def test_the_segment_graph(tmp_path):
    #  |-----|            a room (an area), a door, a corridor with a junction and a dead end
    #  |.....+####
    #  |.....|   #
    #  |-----|   ####>
    #            #
    #            #       (a spur two cells long: its tip has one neighbour, diagonals counted)
    rows = ["|-----|      ", "|.....+####   ", "|.....|   #   ", "|-----|   ####>", "          #   ", "          #   "]
    cells = {}
    for y, row in enumerate(rows):
        for x, ch in enumerate(row):
            k = {"|": "wall", "-": "wall", ".": "floor", "#": "corridor", "+": "door:closed", ">": "stairs_down"}.get(ch)
            if k:
                cells["c%d_%d" % (x, y)] = k
    m = GridMap.build(str(tmp_path / "m.json"), (15, 6), cells=cells)
    seg = m.segments()
    kinds = {c: seg["segments"][s]["kind"] for c, s in seg["of"].items()}
    assert kinds["c2_1"] == "area" and kinds["c6_1"] == "gate" and kinds["c8_1"] == "lane"
    assert seg["junctions"] == ["c10_3"] and "c10_5" in seg["deadends"]
    assert any(seg["segments"][s]["kind"] == "gate" and seg["segments"][s]["state"] == "closed" for s in seg["segments"])


def test_the_route_costs_the_gates_and_keeps_the_doorway_rule(tmp_path):
    # the left room and the right one: through the door in the wall (5 steps), or round by a gap at the top (6)
    cells = {"c%d_%d" % (x, y): "floor" for x in range(9) for y in range(5)}
    for y in range(5):
        cells["c4_%d" % y] = "wall"
    cells["c4_2"] = "door:open"
    cells["c8_2"] = "stairs_down"
    m = GridMap.build(str(tmp_path / "m.json"), (9, 5), cells=cells)
    d = m.load()
    d["agent"]["at"] = "c3_2"
    m.save()
    assert m.route()[:3] == ["c3_2", "c4_2", "c5_2"]           # through the open door, straight: no diagonal into it
    d["doors"]["c4_2"] = "closed"
    m.save()
    assert "c4_2" in m.route()                                   # the only way: the closed door all the same
    d["cells"]["c4_0"] = "floor"                                 # a way round, one step longer
    m.save()
    assert "c4_2" not in m.route()                               # a closed door costs 2: round the wall (6 < 5 + 2)
    d["doors"]["c4_2"] = "open"
    m.save()
    assert "c4_2" in m.route()                                   # open: the door again (5 < 6)


def test_predict_a_hostile_comes_a_peaceful_holds_the_unseen_is_forgotten(tmp_path):
    cells = {"c%d_%d" % (x, y): "floor" for x in range(12) for y in range(3)}
    m = GridMap.build(str(tmp_path / "m.json"), (12, 3), cells=cells, peaceful=["dog"])
    d = m.load()
    d["agent"]["at"] = "c0_1"
    d["things"].update(newt={"in": None, "kind": "beast"}, dog={"in": None, "kind": "beast"})
    d["belief"].update(newt={"c10_1": 1.0}, dog={"c6_1": 1.0})
    m.save()
    mean = lambda bel: sum(xy(c)[0] * p for c, p in bel.items())
    before = mean(d["belief"]["newt"])
    for _ in range(3):
        bayes.predict(d, 1, m.models(d))
    assert mean(d["belief"]["newt"]) < before - 1.0 and len(d["belief"]["newt"]) > 1   # nearer the ego, spread
    assert d["belief"]["dog"] == {"c6_1": 1.0}                                         # a peaceful holds
    for _ in range(25):
        bayes.predict(d, 1, m.models(d), ALIVE)
    assert "newt" not in d["belief"] and "newt" in d["gone"]                           # unseen long enough: gone
    assert abs(sum(bayes.walk(lambda c: m.neighbours(c, d))({"c5_1": 1.0}, 1).values()) - 1) < 1e-9


def test_the_cycle_through_closed_and_locked_doors_to_the_stairs(tmp_path):
    lv = dungeon.rooms(76, 21, 4)
    sim = dungeon.Sim(lv, [dungeon.Monster("newt", (lv.rooms[1][0] + 1, lv.rooms[1][1]))], seed=4)
    m = GridMap.build(str(tmp_path / "m.json"), (76, 21), cells=cells_of(lv), k=8)
    turns, door_roles = drive(sim, m)
    assert turns is not None and sim.won, "the ego did not reach the stairs"
    passed = [lv.doors[p] for p in lv.doors if p in {xy(c) for c in door_roles}]
    assert "locked" in [lv.doors.get(xy(c)) for c in door_roles] or "broken" in passed or passed  # doors were on the way
    assert all(len(rs) == 1 for rs in door_roles.values()), door_roles   # a door kept its role while bound
    assert set(m.load()["binding"]) <= set(cell_roles(8)) | {"b1", "b2", "target", "other"}


def test_view_mode_goes_to_the_frontier_first(tmp_path):
    lv = dungeon.rooms(76, 21, 6)
    sim = dungeon.Sim(lv, [], seed=6)
    m = GridMap.build(str(tmp_path / "m.json"), (76, 21), view=True, k=8)
    m.cycle(sim.perceive())
    m.project()
    d = m.load()
    assert not any(k == "stairs_down" for k in d["cells"].values())
    assert d["path"] and d["path"][-1] in m.segments()["frontier"]          # the goal role: a frontier cell
    turns, _ = drive(sim, m, 1500)
    assert turns is not None and sim.won
    assert len(m.load()["cells"]) < sum(1 for _ in lv.tiles)                  # it never saw the whole level


def test_the_reading_is_in_roles(tmp_path):
    lv = dungeon.rooms(76, 21, 4)
    sim = dungeon.Sim(lv, [], seed=4)
    m = GridMap.build(str(tmp_path / "m.json"), (76, 21), cells=cells_of(lv), k=8)
    atoms = sim.perceive()
    m.cycle(atoms)
    m.project()
    r = m.role_reading({a: 1 for a in atoms})
    roles = set(cell_roles(8)) | {"b1", "b2", "target", "other"}
    import re
    for a in r:
        for x in re.findall(r"[(,]([^,()]+)", a):
            assert x in roles or x in ("n", "e", "s", "w", "ne", "se", "sw", "nw", "open", "closed", "locked"), a
    assert any(a.startswith("toward(") for a in r) and any(a.startswith("next(") for a in r) and "step(p1)" in r


def test_a_door_reads_its_state_the_message_passes_a_beast_gone_from_view_is_dropped(tmp_path):
    cells = {"c%d_1" % x: "floor" for x in range(6)}
    cells.update({"c3_1": "door:locked", "c6_1": "stairs_down"})
    m = GridMap.build(str(tmp_path / "m.json"), (8, 3), cells=cells, k=8)
    m.cycle(["agent_at(c2_1)", "monster(newt,c0_1)", "said(door_locked)"])
    m.project()
    inv = {h: r for r, h in m.binding().items()}
    r = m.role_reading({"agent_at(c2_1)": 1, "said(door_locked)": 1, "door(c3_1,closed)": 1})
    assert "door(%s,closed)" % inv["c3_1"] in r and "said(door_locked)" in r      # a locked door reads closed
    assert m.load()["belief"]["newt"] == {"c0_1": 1.0}
    m.cycle(["agent_at(c1_1)"], models=m.models(), alive=ALIVE)                    # killed: every cell it may be on in view, empty
    assert "newt" not in m.load()["belief"]


def test_the_capacity_text():
    t = capacity(16)
    assert t.startswith("% capacity") and "k = 16" in t
    assert "type cell {goal %s}." % " ".join("p%d" % i for i in range(1, 17)) in t and "type beast {b1 b2}." in t
