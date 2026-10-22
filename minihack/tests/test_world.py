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
