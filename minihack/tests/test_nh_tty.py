"""The real game's tty as data (world/nh_tty.py): the codes, a cell losing its tile to text, and the game itself."""
import json
import os
import pickle
import re
import select
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


def test_waiting_and_the_hero_under_the_cursor():
    t = Tty()
    t.feed(SEL_MAP + glyph(4, 7, 330, b"@") + b"\x1b[5;8H\x1b[1;3z")
    s = t.snapshot()
    assert s["waiting"] and s["hero"] == (7, 3, 330)


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


def test_the_chat_never_types_a_sentence_into_the_game():
    sys.path.insert(0, os.path.join(HERE, "..", "experiments"))
    from nh_demo import key_of
    assert key_of("look here") == ":" and key_of("North") == "k"
    assert key_of("20s") == "20s" and key_of("#pray") == "#pray\r"
    assert key_of("nlook here f") is None
