"""The real game's tty as data (world/nh_tty.py): the codes, a cell losing its tile to text, and the game itself."""
import json
import os
import pickle
import re
import select
import shutil
import subprocess
import sys
import time

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "world"))
from nh_tty import GAME, SHARE, Game, Tty, describe   # noqa: E402

BUILT = pytest.mark.skipif(not os.access(GAME, os.X_OK), reason="no game: minihack/nethack/build.sh")
SEL_MAP = b"\x1b[1;2;3z"


def glyph(row, col, tile, ch, flags=0):
    return b"\x1b[%d;%dH\x1b[1;0;%d;%dz%s\x1b[1;1z" % (row + 1, col + 1, tile, flags, ch)


def test_a_cell_takes_the_tile_the_game_names():
    t = Tty()
    t.feed(SEL_MAP + glyph(5, 10, 123, b"r", 8))
    assert t.cell(5, 10) == (123, 8, "r")
    assert t.snapshot()["cells"][4][10] == {"tile": 123, "flags": 8, "ch": "r"}


def test_a_code_cut_by_the_read_is_held():
    t, data = Tty(), SEL_MAP + glyph(2, 3, 77, b"d")
    for i in range(len(data)):
        t.feed(data[i:i + 1])
    assert t.cell(2, 3) == (77, 0, "d")


def test_only_the_map_window_draws_tiles():
    t = Tty()
    t.feed(b"\x1b[1;2;4z" + glyph(5, 10, 123, b"r"))
    assert t.cell(5, 10) is None


def test_text_over_a_cell_takes_its_tile_and_is_the_text():
    t = Tty()
    t.feed(SEL_MAP + glyph(3, 2, 9, b"#"))
    t.feed(b"\x1b[1;2;4z\x1b[4;1HMenu (end)")
    s = t.snapshot()
    assert t.cell(3, 2) is None and "Menu (end)" in s["text"]


def test_text_keeps_a_letter_equal_to_the_cell_under_it():
    t = Tty()
    t.feed(SEL_MAP + glyph(3, 12, 900, b"-"))
    t.feed(b"\x1b[4;11Hc - a shield")                 # the menu's dash lands on the wall's own dash
    s = t.snapshot()
    assert "c - a shield" in s["text"]


def test_waiting_and_the_hero_under_the_cursor():
    t = Tty()
    t.feed(SEL_MAP + glyph(4, 7, 330, b"@") + b"\x1b[5;8H\x1b[1;3z")
    s = t.snapshot()
    assert s["waiting"] and s["hero"] == (7, 3, 330)


def test_a_prompt_does_not_leave_the_hero_behind():
    """The hero moves and a prompt takes the cursor to the message line before the game waits on the map."""
    t = Tty()
    t.feed(SEL_MAP + glyph(4, 7, 330, b"@") + b"\x1b[5;8H\x1b[1;3z")
    assert t.snapshot()["hero"] == (7, 3, 330)
    t.feed(SEL_MAP + glyph(4, 7, 900, b".") + glyph(4, 8, 330, b"@") + b"\x1b[1;2;1z\x1b[1;1HWhat do you want to eat?\x1b[1;3z")
    assert t.snapshot()["hero"] == (8, 3, 330)


def test_a_pet_of_the_heros_kind_is_not_the_hero():
    t = Tty()
    t.feed(SEL_MAP + glyph(4, 7, 330, b"@") + b"\x1b[5;8H\x1b[1;3z")
    assert t.snapshot()["hero"] == (7, 3, 330)
    t.feed(SEL_MAP + glyph(6, 2, 330, b"@", 8) + b"\x1b[1;2;1z\x1b[1;1HWhat?")
    assert t.snapshot()["hero"] == (7, 3, 330)


@BUILT
def test_the_sheet_is_the_games_tileset():
    """The tile numbers the game emits index minihack/web/tiles/nethack/glyphs.png: every tile of its win/share art against the
    sheet's source, pixel by pixel. Glyph numbers do differ (this build has the mail daemon, NLE's has not): hence
    the map's raw_tiles."""
    import minihack
    import numpy as np
    pal, game = {}, []
    for f in ("monsters", "objects", "other"):
        cur = None
        for l in open(os.path.join(SHARE, f + ".txt"), encoding="latin-1"):
            m = re.match(r"^(\S) = \((\d+), *(\d+), *(\d+)\)", l)
            if m:
                pal[m[1]] = tuple(int(m[i]) for i in (2, 3, 4))
            elif l.startswith("# tile"):
                cur = []
            elif l.startswith("}"):
                game.append(np.array(cur, dtype=np.uint8))
            elif cur is not None and l.strip() and not l.startswith("{"):
                cur.append([pal[c] for c in l.strip()])
    sheet = pickle.load(open(os.path.join(os.path.dirname(minihack.__file__), "tiles", "tiles.pkl"), "rb"))
    assert len(game) == len(sheet) == json.load(open(os.path.join(HERE, "..", "web", "tiles", "nethack", "glyphs.json")))["count"]
    assert all((game[i] == np.array(sheet[i])).all() for i in range(len(game)))


@BUILT
def test_the_game_draws_tiles_the_hero_and_status(tmp_path):
    g = Game(options="name:metistest,role:Valkyrie,race:human,gender:female,align:neutral,pettype:none,!legacy,!splash_screen,!autopickup,color,vt_tiledata,windowtype:tty")
    g.start()
    t, end = Tty(), time.time() + 8
    try:
        while time.time() < end and not (t.snapshot()["hero"]):
            if select.select([g.fd], [], [], 0.2)[0]:
                d = g.read()
                if d:
                    t.feed(d)
            s = t.snapshot()
            if s["more"]:
                g.keys(b"\r")
        s = t.snapshot()
        assert s["hero"], s
        assert describe(s["hero"][2])[1] == "monster"
        assert any("Dlvl" in l for l in s["status"])
        drawn = [c for row in s["cells"] for c in row if c]
        assert len(drawn) > 5
    finally:
        g.keys(b"#quit\r")
        time.sleep(0.2)
        g.keys(b"y")
        time.sleep(0.2)
        g.keys(b"\x1b\x1b\r\r")
        g.stop()


def test_the_page_stands_alone():
    """NetHack's page takes nothing from another world's: every file it loads is under minihack/web."""
    web = os.path.join(HERE, "..", "web")
    for f in ("world.html", "world.js", "map.js"):
        src = open(os.path.join(web, f)).read()
        assert "../" not in re.sub(r"//.*", "", src), f
    for r in re.findall(r'(?:src|href)="([^"#]+)"', open(os.path.join(web, "world.html")).read()):
        if not r.startswith("http"):
            assert os.path.exists(os.path.join(web, r)), r


def test_the_game_as_the_hierarchys_atoms():
    from nh_gym import cell_atoms, events_of, status_atoms
    from nh_tty import tile_names
    n = tile_names()
    mon, obj = len(n["monsters"]), len(n["objects"])
    other = lambda name: mon + obj + n["other"].index(name)
    assert cell_atoms("c1_2", other("vertical closed door"), 0) == ["door(c1_2,closed)"]
    assert cell_atoms("c1_2", other("horizontal open door"), 0) == ["door(c1_2,open)"]
    assert "stairs_down(c1_2)" in cell_atoms("c1_2", other("staircase down"), 0)
    assert cell_atoms("c1_2", other("lit corridor"), 0) == ["corridor(c1_2)"]
    assert cell_atoms("c1_2", other("tlwall"), 0) == ["wall(c1_2)"] and cell_atoms("c1_2", other("iron bars"), 0) == ["wall(c1_2)"]
    assert cell_atoms("c1_2", other("no door"), 0) == ["floor(c1_2)"] and cell_atoms("c1_2", other("floor of a room"), 0) == ["floor(c1_2)"]
    assert cell_atoms("c1_2", 0, 0)[0].startswith("monster(giant_ant,")
    assert cell_atoms("c1_2", 0, 8) == ["floor(c1_2)"]                 # a pet swaps places: never a monster to fight
    assert cell_atoms("c1_2", mon + n["objects"].index("boulder"), 0) == ["wall(c1_2)"]
    assert "said(door_locked)" in events_of("This door is locked.") and events_of("") == []
    assert "said(asked)" in events_of("Really attack the gnome? [yn] (n)")
    assert "hp(16)" in status_atoms(["", "Dlvl:1 $:0 HP:16(16) Pw:2(2) AC:6 Xp:1/0 T:5"])


@BUILT
def test_the_hierarchy_acts_in_the_real_game(tmp_path):
    """The gym under the rules: a search is a turn, a move's perception names the hero, the agent's frames carry the map."""
    from nh_gym import Gym
    g = Gym(options="name:metistest,role:Valkyrie,race:human,gender:female,align:neutral,pettype:none,!legacy,!splash_screen,!autopickup,color,time,vt_tiledata,windowtype:tty")
    try:
        info = g.open(map_doc=str(tmp_path / "map.json"), card={"title": "t"})
        assert info["size"] == [79, 21] and any(a.startswith("agent_at(") for a in info["atoms"])
        turn = lambda p: next(int(a[5:-1]) for a in p["atoms"] if a.startswith("turn("))
        t0, after = turn(info), g.step("SEARCH")
        assert turn(after) == t0 + 1 and not after["done"]
        assert json.load(open(tmp_path / "map.json"))["raw_tiles"] is True
        frames = g.frames()["frames"]
        assert any(f["ev"] == "world/screen" for f in frames)
        g.step("OPEN")                                    # a direction prompt is left for the rule's next action
        assert g.tty.snapshot()["prompt"]
        g.step("N")
        assert not g.tty.snapshot()["prompt"]
    finally:
        g.keys("#quit\r")
        g.keys("y")
        g.keys("\x1b\x1b\r\r")
        if not g.over:
            g.game.stop()


def test_a_command_that_did_not_do_what_it_said_is_a_surprise():
    sys.path.insert(0, os.path.join(HERE, "..", "world"))
    from nh_host import surprise
    was = {"at": (5, 5), "turn": 10, "dlvl": 1}
    assert surprise("move", ["E"], was, {"at": (6, 5), "turn": 11, "dlvl": 1}, []) is None
    assert surprise("move", ["E"], was, {"at": (5, 5), "turn": 10, "dlvl": 1}, ["said(blocked)"])
    assert surprise("move", ["E"], was, {"at": (30, 2), "turn": 11, "dlvl": 2}, [])    # a trap door under the step
    assert surprise("move_fight", ["E"], was, {"at": (5, 5), "turn": 11, "dlvl": 1}, ["said(hit)"]) is None
    assert surprise("move_fight", ["E"], was, {"at": (5, 5), "turn": 11, "dlvl": 1}, [])
    assert surprise("open_door", ["OPEN", "N"], was, was, ["said(door_locked)"]) is None
    assert surprise("pickup", ["PICKUP"], was, was, ["said(other)"])
    assert surprise("pickup", ["PICKUP"], was, was, ["said(nothing_here)"]) is None
    assert surprise("down", ["DOWN"], was, {"at": (5, 5), "turn": 11, "dlvl": 2}, []) is None
    assert surprise("down", ["DOWN"], was, was, ["said(cant)"])
    assert surprise("search", ["SEARCH"], was, {"at": (5, 5), "turn": 11, "dlvl": 1}, []) is None
    assert surprise("search", ["SEARCH"], was, was, [])


def test_an_errand_held_too_long_is_refused(monkeypatch):
    sys.path.insert(0, os.path.join(HERE, "..", "world"))
    import nh_host
    from mh_host import MhHost
    monkeypatch.setattr(MhHost, "pending", lambda self: False)
    h = nh_host.NhHost.__new__(nh_host.NhHost)
    h.spec, h.key = "task", "k"
    nh_host.SHARED["k"] = {"last": {"atoms": ["agent_at(c1_1)", "turn(5)"], "dlvl": 1}}
    clock = [100.0]
    monkeypatch.setattr(nh_host.time, "monotonic", lambda: clock[0])
    try:
        assert h.pending() is False
        clock[0] += nh_host.STALL_SECONDS - 1
        assert h.pending() is False
        nh_host.SHARED["k"]["last"]["atoms"] = ["agent_at(c1_1)", "turn(6)"]    # a turn passed: the clock starts again
        assert h.pending() is False
        clock[0] += nh_host.STALL_SECONDS - 1
        assert h.pending() is False
        clock[0] += 2
        assert h.pending() is True
        nh_host.SHARED["k"]["last"]["atoms"] = ["agent_at(c1_1)", "turn(7)"]    # a tick with no wake check before it reads the clock itself
        dos = []
        h.stalled({"want(goal)": 1}, dos)
        assert dos == []
        clock[0] += nh_host.STALL_SECONDS + 1
        assert h.pending() is True
        dos = []
        h.stalled({"want(goal)": 1}, dos)
        assert dos == ["+refused(goal) 1"] and h.stall_said and h.pending() is False
        clock[0] += nh_host.STALL_SECONDS + 1
        dos = []
        h.stalled({"idle": 1}, dos)                   # no errand: nothing to stop
        assert dos == []
    finally:
        del nh_host.SHARED["k"]


def test_what_the_hero_carries_as_atoms():
    from nh_gym import holds_atoms, items_of
    page = " Weapons\n a - a +1 long sword (weapon in hand)\n b - 2 daggers (alternate weapon; not wielded)\n Comestibles\n d - a food ration\n (end)"
    items = items_of(page)
    assert [i[0] for i in items] == ["a", "b", "d"]
    assert holds_atoms(items) == ["holds(1_long_sword)", "holds(daggers)", "holds(food_ration)"]


@BUILT
def test_the_hero_carries_picks_up_from_a_menu_and_starts_again(tmp_path):
    """The inventory read, several things on one cell picked up through the game's menu, a new game with a new dungeon."""
    from nh_gym import Gym
    g = Gym(options="name:metisitems,role:Valkyrie,race:human,gender:female,align:neutral,pettype:none,!legacy,!splash_screen,!autopickup,color,time,vt_tiledata,windowtype:tty")
    try:
        first = g.open(map_doc=str(tmp_path / "map.json"), card={})
        g.frames()
        g.frames()
        held = [w for _, w in g.items]
        assert any("long sword" in w for w in held) and any("holds(" in a for a in g.perceive()["atoms"])
        assert not g.tty.snapshot()["text"]               # the page is closed again, and the map is back
        letters = [l for l, w in g.items if "long sword" not in w and "worn" not in w][:2]
        for l in letters:
            g.keys("d" + l)
        g.frames()
        assert len(g.items) == len(held) - 2
        got = g.step("PICKUP")
        assert "said(picked)" in got["events"]
        g.frames()
        assert len(g.items) == len(held)
        game = first["game"]
        g.keys("#quit\r")
        g.keys("y")
        ended = g.step("N")                               # the rules' next command answers the game's last questions: its end, no error
        assert ended["done"] and g.over and "said(died)" in ended["events"]
        again = g.new_game()
        assert again["game"] == game + 1 and any(a.startswith("agent_at(") for a in again["atoms"])
        assert next(a for a in again["atoms"] if a.startswith("turn(")) == "turn(1)"
    finally:
        if g.game and not g.over:
            g.game.forget()


def test_the_view_zooms_drags_and_follows():
    node = shutil.which("node")
    if not node:
        pytest.skip("no node")
    r = subprocess.run([node, os.path.join(HERE, "viewport_test.mjs")], capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr


def test_the_real_game_installs_for_the_agent(tmp_path):
    """The packages the service loads: every domain compiles, the task's card maps its verbs to goals its rules take."""
    import yaml
    from metis.lang.compiler import load_llp
    import nh_hier
    cfg = yaml.safe_load(open(nh_hier.install(str(tmp_path / "root"))))
    assert cfg["domains"]["tick"] is True and cfg["v3"]["world_map"].endswith("world-map.json")
    hier = tmp_path / "root" / "domains" / "hier"
    for sp in ("director", "task", "nav", "act"):
        assert load_llp(hier / sp / ("%s.llp" % sp)).catalog.ground({}) is not None
    card = yaml.safe_load(open(hier / "task" / "intent.yaml"))
    goals = {m["act"] for m in card["map"]}
    assert goals == {"reach", "walk", "search_here", "pick_up", "go_down"}
    text = (hier / "task_domain.llp").read_text()
    assert all(("%s" % g) in text for g in goals)
    assert "NhHost" in (hier / "nav" / "mh_host.py").read_text()


def test_stairs_seen_with_no_way_to_them_do_not_stop_the_search(tmp_path):
    from semantic_world.grid import GridMap
    sys.path.insert(0, os.path.join(HERE, "..", "world"))
    from nh_host import NhMap
    p = str(tmp_path / "map.json")
    GridMap.build(p, [20, 5], view=True)
    m = NhMap(p)
    m.observe({"agent_at(c1_1)": 1, "floor(c1_1)": 1, "floor(c2_1)": 1, "corridor(c3_1)": 1, "stairs_down(c10_1)": 1, "floor(c10_1)": 1})
    assert GridMap(p).route() == []                   # the library's answer: it knows the stairs and no way to them
    r = m.route()
    assert r and r[0] == "c1_1" and "c10_1" not in r  # ours: on to what is not yet known
    m2 = NhMap(p)
    m2.observe({"agent_at(c9_1)": 1, "floor(c9_1)": 1, "floor(c10_1)": 1, "stairs_down(c10_1)": 1})
    assert m2.route()[-1] == "c10_1"                  # and straight to them once there is a way
