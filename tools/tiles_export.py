"""tiles_export.py — the base tileset of web/map.js (alf-demo step 3a, DEMO.md §8), written once:

    .worlds/mh/bin/python tools/tiles_export.py [EDITOR_DIR]

1. MiniHack's tiles.pkl (the NetHack 3.6 tileset: 1082 tiles × 16×16 RGB) → a sprite sheet
   web/tiles/nethack/glyphs.png (40 tiles a row) and web/tiles/nethack/glyphs.json
   {size, cols, count, glyph2tile}: an NLE glyph id (the `glyphs` observation) → its tile, so
   the page draws a level from `glyphs` with no other mapping.
2. EDITOR_DIR, a checkout of minihack-editor/minihack-editor.github.io: its 664 named icons
   (public/tilesets/nethack/{dungeon,items,monsters}) copied to web/tiles/editor/, and
   web/tiles/index.json {name: {image, glyph, color, source}} from its indexes
   (src/tilesets/nethack/*.json). A name is lower case with `_` for anything else
   ("Staircase (down)" → staircase_down, "skeleton key" → skeleton_key, as MiniHack's atoms
   spell them); the first entry of a name wins.

Both are NetHack's art (the NetHack General Public License; NetHackWiki's images, some CC
BY-SA 3.0): they live under web/tiles/ with its own NOTICE, never in the Apache sources.
The PNG is written with zlib (no PIL in the world's venv).
"""
import json
import os
import pickle
import re
import shutil
import struct
import sys
import zlib

HERE = os.path.dirname(os.path.abspath(__file__))
ASSETS = os.path.join(os.path.dirname(HERE), "web", "tiles")
COLS = 40


def png(path, rgb):
    """rgb: rows of bytes (R, G, B per pixel), all one width."""
    h, w = len(rgb), len(rgb[0]) // 3

    def chunk(kind, data):
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)
    raw = b"".join(b"\x00" + bytes(r) for r in rgb)
    with open(path, "wb") as f:
        f.write(b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0))
                + chunk(b"IDAT", zlib.compress(raw, 9)) + chunk(b"IEND", b""))


def glyph_sheet(out):
    import minihack
    from minihack.tiles import glyph2tile
    tiles = pickle.load(open(os.path.join(os.path.dirname(minihack.__file__), "tiles", "tiles.pkl"), "rb"))
    n, size = len(tiles), tiles[0].shape[0]
    rows = -(-n // COLS)
    sheet = [bytearray(COLS * size * 3) for _ in range(rows * size)]
    for t in range(n):
        x0, y0 = (t % COLS) * size, (t // COLS) * size
        for y in range(size):
            sheet[y0 + y][x0 * 3:(x0 + size) * 3] = tiles[t][y].tobytes()
    os.makedirs(out, exist_ok=True)
    png(os.path.join(out, "glyphs.png"), sheet)
    json.dump({"size": size, "cols": COLS, "count": n, "glyph2tile": list(map(int, glyph2tile))},
              open(os.path.join(out, "glyphs.json"), "w"), separators=(",", ":"))
    return n, len(glyph2tile)


def key(name):
    return re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")


def editor_index(editor, out):
    src = os.path.join(editor, "public", "tilesets", "nethack")
    dst = os.path.join(out, "editor")
    shutil.rmtree(dst, ignore_errors=True)
    for kind in ("dungeon", "items", "monsters"):
        shutil.copytree(os.path.join(src, kind), os.path.join(dst, kind))
    index = {}
    for kind in ("dungeon", "items", "monsters"):
        for cls in json.load(open(os.path.join(editor, "src", "tilesets", "nethack", kind + ".json"))):
            for o in cls.get("objects", []):
                k = key(o.get("name") or "")
                if not k or k in index or not o.get("image"):
                    continue
                g = o.get("glyph") or {}
                index[k] = {"image": "editor/" + o["image"], "glyph": g.get("character") or "",
                            "color": (g.get("color") or "").replace("nhsym ", ""), "source": o.get("wiki_link") or ""}
    json.dump(index, open(os.path.join(out, "index.json"), "w"), indent=0, sort_keys=True)
    return len(index), sum(len(fs) for _, _, fs in os.walk(dst))


if __name__ == "__main__":
    n, g = glyph_sheet(os.path.join(ASSETS, "nethack"))
    print("glyphs.png: %d tiles; glyphs.json: %d glyphs" % (n, g))
    if len(sys.argv) > 1:
        k, files = editor_index(sys.argv[1], ASSETS)
        print("index.json: %d names; editor/: %d images" % (k, files))
