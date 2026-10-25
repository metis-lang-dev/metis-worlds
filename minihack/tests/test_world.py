"""The world under test (world-minihack step 1): the perception, the host, the level
families, the generated package. Runs under the world's venv; the program check needs METISC."""
import os, subprocess, sys
import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "world"))
from mh_gym import World  # noqa: E402
from mh_host import MhHost, bindings, ACTIONS  # noqa: E402
import levels  # noqa: E402
import gen_level  # noqa: E402

VARIANT = ("medium", "apple", "newt", "closed", "none")


def test_level_families_and_splits():
    d, h = levels.split("room", "discovery"), levels.split("room", "held_out")
    assert len(d) + len(h) == len(levels.all_variants()) == 144
    assert all(levels.is_held_out(v) for v in h) and not any(levels.is_held_out(v) for v in d)
    assert ("small", "apple", "newt", "none", "pit") in h and ("small", "key", "none", "closed", "none") in h


def test_perception_of_a_level():
    lv = levels.level(VARIANT, seed=1)
    w = World()
    info = w.open(des=lv["des"], actions=ACTIONS, max_steps=20, seed=1)
    atoms = set(info["init"]["atoms"])
    assert info["size"] == [8, 5] and len(info["cells"]) == 40     # 7 floor columns + the wall with the door (M2)
    assert any(a.startswith("agent_at(") for a in atoms) and any(a.startswith("obj(apple,") for a in atoms)
    assert any(a.startswith("monster(newt,") for a in atoms) and any(a.startswith("door(") for a in atoms)
    assert not any(a.startswith("stairs_down(") for a in atoms) and "hunger(normal)" in atoms   # behind the door (M2)
    s = w.step("WAIT")
    assert "atoms" in s and not s["done"]


def test_bindings():
    assert bindings("cmd_move_rule[D=n]") == ("cmd_move_rule", {"D": "n"})


@pytest.fixture
def package(tmp_path):
    pkg, n = gen_level.generate(VARIANT, 1, str(tmp_path))
    assert n > 20 and os.path.exists(os.path.join(pkg, "level.json")) and os.path.exists(os.path.join(pkg, "intent.yaml"))
    return pkg


def test_host_moves_picks_up_and_restores(package):
    h = MhHost(package)
    try:
        r = h.reading()
        at = next(a for a in r if a.startswith("agent_at("))[9:-1]
        apple = next(a for a in r if a.startswith("obj(apple,"))[10:-1]
        ax, ay = map(int, at[1:].split("_")); px, py = map(int, apple[1:].split("_"))
        for _ in range(20):
            if (ax, ay) == (px, py):
                break
            dx, dy = (px > ax) - (px < ax), (py > ay) - (py < ay)
            d = {(0, -1): "n", (0, 1): "s", (1, 0): "e", (-1, 0): "w", (1, -1): "ne", (-1, -1): "nw", (1, 1): "se", (-1, 1): "sw"}[(dx, dy)]
            assert h.tick({a: 1 for a in h.reading()}) is not None
            h.on_event("cmd_move[D=%s]" % d, ())
            at = next(a for a in h.reading() if a.startswith("agent_at("))[9:-1]
            ax, ay = map(int, at[1:].split("_"))
        assert (ax, ay) == (px, py), "the walk did not reach the apple"
        h.on_event("cmd_pickup", ())
        assert "holds(apple)" in h.reading() and not any(a.startswith("obj(apple,") for a in h.reading())
        assert any(k.startswith("said(") for k in h.pending_events)      # the message became an event
        snap = h.snapshot()
        h.restore(snap)
        assert "holds(apple)" in h.reading() and len(h.actions) == len(snap["actions"])
    finally:
        h.gym.close()


@pytest.mark.skipif(not os.environ.get("METISC"), reason="METISC is not set")
def test_package_compiles(package):
    llp = next(f for f in os.listdir(package) if f.endswith(".llp"))
    out = subprocess.run([os.environ["METISC"], "--diagnostics-json", os.path.join(package, llp)], capture_output=True, text=True, timeout=120)
    assert out.returncode == 0 and "error" not in out.stdout.lower(), out.stdout[-400:] + out.stderr[-200:]


def _xy(atom):
    import re
    m = re.search(r"\bc(\d+)_(\d+)\b", atom)
    return (int(m.group(1)), int(m.group(2)))


def _path(reading, src, dst):
    """A BFS over the perceived walkable cells (floor, doors, stairs), 8-connected; the moves."""
    walk = {_xy(a) for a in reading if a.split("(")[0] in ("floor", "door", "stairs_down", "agent_at", "obj", "monster", "trap")}
    walk.add(dst)
    steps = {(0, -1): "n", (0, 1): "s", (1, 0): "e", (-1, 0): "w", (1, -1): "ne", (-1, -1): "nw", (1, 1): "se", (-1, 1): "sw"}
    prev, todo = {src: None}, [src]
    while todo:
        cur = todo.pop(0)
        if cur == dst:
            break
        for (dx, dy), d in steps.items():
            nxt = (cur[0] + dx, cur[1] + dy)
            if nxt in walk and nxt not in prev:
                prev[nxt] = (cur, d)
                todo.append(nxt)
    assert dst in prev, "no path %s -> %s" % (src, dst)
    moves, cur = [], dst
    while prev[cur]:
        cur, d = prev[cur]
        moves.append(d)
    return moves[::-1]


def _walk(h, dst):
    at = _xy(next(a for a in h.reading() if a.startswith("agent_at(")))
    for d in _path(h.reading(), at, dst):
        h.on_event("cmd_move[D=%s]" % d, ())
        if h.done:                       # the skill level ends on the stairs
            return dst
    return _xy(next(a for a in h.reading() if a.startswith("agent_at(")))


def test_every_variant_opens_as_its_level():
    """M1: every des compiles and the level has the stairs (a bad des makes NLE fall back to a
    3x3 room without them); with a door the stairs are behind the wall (M2)."""
    from mh_gym import World
    from levels import all_variants, des_of, level
    bad = []
    for v in all_variants():
        w = World()
        try:
            info = w.open(des=des_of(v), actions=level(v)["actions"], max_steps=10, seed=1)
            atoms = set(info["init"]["atoms"])
            stairs = any(a.startswith("stairs_down(") for a in atoms)
            if v[3] != "none":   # the stairs are behind the wall: a door is seen, the stairs are not, and the des
                import re        # places them past the wall column (N3)
                des = des_of(v)
                row0 = des.split("MAP\n")[1].split("\n")[0]
                wall = row0.index("+") if "+" in row0 else row0.index("|")
                sx = int(re.search(r"STAIR:\((\d+), ?(\d+)\),down", des).group(1))
                ok = any(a.startswith("door(") for a in atoms) and not stairs and sx > wall
            else:
                ok = stairs and info["size"][0] >= 4
            if v[1] == "key":
                ok = ok and any(a.startswith("obj(skeleton_key,") for a in atoms)
            if not ok:
                bad.append(v)
        finally:
            w.env.close()
    assert not bad, bad


def test_the_key_unlocks_the_door(tmp_path):
    """M3: a key variant: pick the skeleton key up, UNLOCK the locked door (APPLY, the letter,
    the direction, y), OPEN it, walk through to the stairs, DOWN: won."""
    v = ("small", "key", "none", "closed", "none")
    pkg, _ = gen_level.generate(v, 1, str(tmp_path))
    h = MhHost(pkg)
    try:
        r = h.reading()
        key = _xy(next(a for a in r if a.startswith("obj(skeleton_key,")))
        assert _walk(h, key) == key
        h.on_event("cmd_pickup", ())
        assert "holds(key)" in h.reading()          # on the floor it is the skeleton_key glyph; carried, "a key"
        door = _xy(next(a for a in h.reading() if a.startswith("door(")))
        front = (door[0] - 1, door[1])
        assert _walk(h, front) == front
        h.on_event("cmd_apply[D=e]", ())
        assert any("unlock" in e for e in h.pending_events), h.pending_events
        h.on_event("cmd_open[D=e]", ())
        assert any(a == "door(c%d_%d,open)" % door for a in h.reading()), [a for a in h.reading() if a.startswith("door(")]
        stairs = _xy(next(a for a in h.reading() if a.startswith("stairs_down(")))   # seen once the door is open
        assert _walk(h, stairs) == stairs
        assert h.done and h.won              # the level ends on the stairs: won
    finally:
        h.gym.close()


def test_map_export_is_the_fixture():
    """alf-demo step 3a: a level's first screen as web/map.js's grid — its glyphs and characters,
    floor under what can move, the things named — is web/fixtures/'s, as written by map_export."""
    import json
    import map_export
    pkg = os.path.join(ROOT, "domains", "room_medium_apple_newt_closed_none")
    m = map_export.export(pkg)
    assert (m["cols"], m["rows"]) == (8, 5) and m["agent"]["ch"] == "@"
    assert {e["name"] for e in m["entities"]} == {"door (closed)", "newt", "apple"}
    floor = {(c["t"], c["ch"]) for row in m["cells"] for c in row if c and c["ch"] == "."}
    assert len(floor) == 1
    for e in m["entities"] + [m["agent"]]:
        if e is m["agent"] or e["kind"] in ("monster", "object"):
            c = m["cells"][e["pos"][1]][e["pos"][0]]
            assert (c["t"], c["ch"]) in floor, e
    assert json.load(open(os.path.join(ROOT, "..", "web", "fixtures", "minihack_room_medium.json"))) == m, \
        "web/fixtures/ is stale: rerun world/map_export.py"


def test_tiles_export(tmp_path):
    """alf-demo step 3a: MiniHack's tiles.pkl as a sprite sheet + the glyph → tile index, and the
    committed sheet is what the exporter writes."""
    import json
    sys.path.insert(0, os.path.join(ROOT, "..", "tools"))
    import tiles_export
    n, g = tiles_export.glyph_sheet(str(tmp_path))
    meta = json.load(open(tmp_path / "glyphs.json"))
    assert (n, g) == (1082, 5976) and meta["size"] == 16 and meta["cols"] == 40
    assert max(meta["glyph2tile"]) < n
    head = (tmp_path / "glyphs.png").read_bytes()[:24]
    assert head[:8] == b"\x89PNG\r\n\x1a\n" and int.from_bytes(head[16:20], "big") == 640 and int.from_bytes(head[20:24], "big") == 448
    ref = os.path.join(ROOT, "..", "web", "tiles", "nethack")
    assert (tmp_path / "glyphs.png").read_bytes() == open(os.path.join(ref, "glyphs.png"), "rb").read()
    assert meta == json.load(open(os.path.join(ref, "glyphs.json")))


def test_the_actor_faces_act_and_describe(tmp_path):
    """world-minihack step 2a: the host's faces for metis-agent's actor (act without a rule). act(atom)
    runs a command atom no rule took as the world's action and says whether the world took it (a wall,
    nothing to pick up: not taken; a wait: taken); describe() says the perception in words, from the
    atoms only; the manifest carries actor: {max_steps, task}."""
    import yaml
    pkg, _ = gen_level.generate(("small", "apple", "none", "none", "none"), 1, str(tmp_path), max_steps=12)
    m = yaml.safe_load(open(os.path.join(pkg, "domain.yaml")))
    assert m["actor"] == {"max_steps": 12, "task": gen_level.TASK} and m["line"].startswith("a lit room: {")
    assert "down" not in gen_level.TASK and "stairs" not in gen_level.TASK   # opus's R1: the world wins on arrival
    h = MhHost(pkg)
    try:
        text = h.describe()
        assert text.startswith("You see: ") and "Around you: north: " in text and "an apple (item) is" in text
        at = next(a for a in h.reading() if a.startswith("agent_at("))
        x, y = map(int, at[10:-1].split("_"))
        wall = next(d for (dx, dy), d in [((-1, 0), "w"), ((0, -1), "n"), ((1, 0), "e"), ((0, 1), "s")]
                    if not any(a in h.reading() for a in ("floor(c%d_%d)" % (x + dx, y + dy), "stairs_down(c%d_%d)" % (x + dx, y + dy))))
        r = h.act("cmd_move(%s)" % wall)
        assert r["acted"] is False and r["action"] == [wall.upper()]
        assert h.act("cmd_pickup")["acted"] is False                        # nothing here (the apple is elsewhere)
        assert h.act("cmd_wait")["acted"] is True                           # a wait changes nothing, by design
        # opus's R2: a cell that is both floor and stairs reads as the stairs, whatever the set's order
        keep = h.atoms
        h.atoms = {"agent_at(c1_1)", "floor(c1_1)", "floor(c2_1)", "stairs_down(c2_1)", "wall(c1_0)", "door(c0_1,closed)"}
        text = h.describe()
        assert "east: the goal" in text and "north: a wall" in text and "west: a closed door" in text, text
        h.atoms = keep
        assert h.act("cmd_unknown") == {"acted": False, "action": None, "message": "no action for cmd_unknown", "events": [],
                                        "reward": 0.0, "done": False, "won": False}
    finally:
        h.gym.close()


def test_the_policy_drivers_base_instance_and_splits(tmp_path):
    """gen_level for metis-loop's policy driver: the lifted base (every level's predicates, no rule, no
    level type), an instance over it (the level's types, the grid as next/3 facts, the perceived start;
    the starting kit typed), and levels.sample's three splits (seeded; the gate discovery's variants at
    other layouts; room_quiet without a monster)."""
    base = gen_level.base_source("mh")
    assert "bwd next(cell, dir, cell)." in base and "pred agent_at(cell) : mh." in base and "type cell" not in base
    (tmp_path / "base").mkdir()
    (tmp_path / "base" / "mh.llp").write_text(base)
    pkg, n = gen_level.generate(VARIANT, 1, str(tmp_path), domain_rel="../base/mh.llp", name="lvl_s1")
    text = open(os.path.join(pkg, "lvl_s1.llp")).read()
    assert 'include "../base/mh.llp".' in text and "next(c0_0, e, c1_0)." in text and "next(c0_0, w," not in text
    held = [l[len("#init holds("):-3] for l in text.splitlines() if l.startswith("#init holds(")]
    things = next(l for l in text.splitlines() if l.startswith("type thing {"))[len("type thing {"):-2].split()
    assert held and all(h in things for h in held)                          # the kit is in the type (flint_stone, rock)
    assert any(l.startswith("#init hp(n") for l in text.splitlines()) and "stage act" not in text
    assert sorted(gen_level.geometry(["c0_0", "c1_0", "c1_1"])) == [
        "next(c0_0, e, c1_0).", "next(c0_0, se, c1_1).", "next(c1_0, s, c1_1).", "next(c1_0, w, c0_0).", "next(c1_1, n, c1_0).", "next(c1_1, nw, c0_0)."]
    if os.environ.get("METISC"):
        out = subprocess.run([os.environ["METISC"], "--diagnostics-json", os.path.join(pkg, "lvl_s1.llp")], capture_output=True, text=True, timeout=120)
        assert out.returncode == 0, out.stdout[-400:] + out.stderr[-200:]
    d, g, h = (levels.sample(s, "room", 200, 1) for s in ("discovery", "gate", "held_out"))
    assert {v for v, _ in d} == {v for v, _ in g} == set(levels.split("room", "discovery")) and {v for v, _ in h} == set(levels.split("room", "held_out"))
    assert {s for _, s in d} == {1} and {s for _, s in g} == {levels.GATE_SEED + 1} and levels.sample("gate", "room", 3, 1) != [(v, 1001) for v, _ in d[:3]]
    q = levels.sample("discovery", "room_quiet", 200, 1)
    assert q and all(v[2] == "none" for v, _ in q) and levels.sample("discovery", "room", 5, 1) == d[:5]
    with pytest.raises(ValueError, match="family"):
        levels.sample("discovery", "maze", 1, 1)


@pytest.mark.skipif(not os.environ.get("METISC"), reason="METISC is not set")
def test_the_loops_base_compiles_alone(tmp_path):
    """spec 12 (abstract-types step 3): base_source declares the level's types (cell thing beast)
    as abstract, so the loop's empty base compiles alone with metisc."""
    (tmp_path / "mh.llp").write_text(gen_level.base_source())
    out = subprocess.run([os.environ["METISC"], str(tmp_path / "mh.llp")], capture_output=True, text=True, timeout=120)
    assert out.returncode == 0 and "; abstract cell thing beast " in out.stdout, out.stderr[-600:]


def test_an_exerciser_level_opens_in_its_own_coordinates():
    """semantic-world step 2: the exerciser's levels (semantic_world.dungeon, the article's algorithms) as NLE levels
    through Level.des(): a dark cave and lit rooms, 76 x 21, the robot on the start cell, every cell on the first
    screen the des's own (the perceiver's top-left from the robot's pinned start: a dark level shows eight cells)."""
    from semantic_world import dungeon
    for lv in (dungeon.cave(76, 21, 1), dungeon.rooms(76, 21, 4)):
        w = World()
        try:
            info = w.open(des=lv.des(), actions=ACTIONS, max_steps=10, seed=1)
            atoms = info["init"]["atoms"]
            assert info["size"] == [76, 21] and "agent_at(c%d_%d)" % lv.start in atoms
            for a in atoms:
                p = a.split("(")[0]
                if p in ("floor", "corridor", "wall"):
                    x, y = map(int, a[a.index("(") + 2:-1].split("_"))
                    assert lv.tiles.get((x, y)) in ({"wall": "-|"}.get(p, ".#>+")), a
        finally:
            w.env.close()


def test_the_hierarchy_is_one_program_for_every_level(tmp_path):
    """semantic-world step 2: MiniHack's hierarchy (world/mh_hier.py: director, task, nav, act over roles) installs the
    same sources for a room and for a 76 x 21 cave — the level is the host's map (semantic_world.grid), never the
    program's; each domain compiles (METISC)."""
    import mh_hier
    from semantic_world import dungeon
    roots = {"room": VARIANT, "cave": dungeon.cave(76, 21, 1).des()}
    for n, lv in roots.items():
        mh_hier.install(lv, str(tmp_path / n), name=n)
    hier = lambda n, f: (tmp_path / n / "domains" / "hier" / f).read_bytes()
    for f in ("nav_domain.llp", "act_domain.llp", "task_domain.llp", "capacity.llp", "nav/nav.llp", "director/director.llp"):
        assert hier("room", f) == hier("cave", f), f
    if os.environ.get("METISC"):
        for d in mh_hier.NAMES:
            p = tmp_path / "cave" / "domains" / "hier" / d / ("%s.llp" % d)
            out = subprocess.run([os.environ["METISC"], "--diagnostics-json", str(p)], capture_output=True, text=True, timeout=120)
            assert out.returncode == 0 and '"error"' not in out.stdout, (d, out.stdout[-2000:], out.stderr[-2000:])
