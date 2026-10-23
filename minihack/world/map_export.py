"""map_export.py — a level's first screen as web/map.js's grid (alf-demo step 3a, DEMO.md §8):
the `glyphs` observation is the map, the NetHack glyph sheet its tileset, so nothing is mapped.

    .worlds/mh/bin/python world/map_export.py PACKAGE_DIR OUT.json

{cols, rows, cells: [[{t: glyph, ch}|null]], entities: [{id, name, pos, tile, ch, kind}],
 agent: {pos, yaw: null, tile, ch}, task: {text, goal, source}, tileset: {index: []}}: the level's box as the
perceiver crops it (level coordinates: cell (x, y) is the perceiver's c<x>_<y>), every non-blank
cell its glyph id and character, the entities the perceiver names (monsters, objects, the
stairs, doors, traps) with their glyphs, the agent `@`. The task is the family's (the room:
reach the stairs down and descend).
"""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
TASK = {"text": "Find the stairs down and go down them.", "goal": "down",
        "source": "metis-worlds minihack: the room family (levels.py)"}
NAMES = {"stairs_down": "staircase down", "stairs_up": "staircase up"}


def world_card(ents):
    """The world card (the same keys as alfworld's semantic_map.world_card): what this level is and
    what can be asked of it."""
    kinds = {}
    for e in ents:
        kinds.setdefault(e.get("type") or e.get("kind") or "thing", []).append(e.get("id") or e.get("name") or "")
    things = [{"type": k, "n": len(v), "ids": v} for k, v in sorted(kinds.items())]
    return {"title": "MiniHack room", "about": ["MiniHack: a NetHack level on a grid; the agent walks, picks up, opens and unlocks, and goes down the stairs.",
                                                "%d things on the level (%d kinds)." % (sum(t["n"] for t in things), len(things))],
            "room": [], "things": things,
            "asks": [{"say": TASK.get("text", "go down the stairs").rstrip(".").lower(), "what": "the level's task: the one that wins"},
                     {"say": "stop", "what": "the agent stops and waits"}, {"say": "new game", "what": "the level from its start"}],
            "cannot": ["a single step on its own", "a thing that is not on this level"],
            "source": "generated from the level by world/map_export.py"}


def export(package_dir):
    from mh_gym import World
    lv = json.load(open(os.path.join(package_dir, "level.json")))
    w = World()
    try:
        info = w.open(des=lv["des"], actions=lv["actions"], max_steps=10, seed=int(lv.get("seed", 1)))
        obs, _ = w._reset(int(lv.get("seed", 1)))
        p = w.p
        g, c = obs["glyphs"], obs["chars"]
        at = lambda x, y: (int(g[p.y0 + y, p.x0 + x]), chr(c[p.y0 + y, p.x0 + x]))
        cells = [[None if at(x, y)[1] == " " else {"t": at(x, y)[0], "ch": at(x, y)[1]} for x in range(p.w)]
                 for y in range(p.h)]
        ents, agent = [], None
        for a in sorted(info["init"]["atoms"]):
            pred, args = a.split("(")[0], a[a.index("(") + 1:-1].split(",")
            cellname = next((x for x in args if x.startswith("c") and "_" in x), None)
            if cellname is None:
                continue
            x, y = map(int, cellname[1:].split("_"))
            glyph, ch = at(x, y)
            if pred == "agent_at":
                agent = {"pos": [x, y], "yaw": None, "tile": glyph, "ch": ch}
            elif pred in ("monster", "obj", "trap"):
                name = args[0] if pred != "trap" else args[0] + " trap"
                ents.append({"id": "%s@%s" % (args[0], cellname), "name": name.replace("_", " "), "pos": [x, y],
                             "tile": glyph, "ch": ch, "kind": {"obj": "object"}.get(pred, pred)})
            elif pred in ("stairs_down", "stairs_up", "door"):
                name = NAMES.get(pred, "door (%s)" % args[1] if pred == "door" else pred)
                ents.append({"id": "%s@%s" % (pred, cellname), "name": name, "pos": [x, y], "tile": glyph, "ch": ch,
                             "kind": "place"})
        # under a thing that can move (the agent, a monster, an object) the cell is floor: the glyph
        # of a seen floor cell, so nothing is drawn twice and a move leaves no trace behind
        floor = next(({"t": c["t"], "ch": "."} for row in cells for c in row if c and c["ch"] == "."), None)
        for e in ents + ([agent] if agent else []):
            if e is agent or e["kind"] in ("monster", "object"):
                cells[e["pos"][1]][e["pos"][0]] = floor
        return {"world": "minihack", "level": lv.get("name") or os.path.basename(package_dir), "cols": p.w, "rows": p.h,
                "cells": cells, "entities": ents, "agent": agent, "task": dict(TASK), "card": world_card(ents),
                "tileset": {"index": []}}             # the page's base tileset (the glyph sheet) is the level's
    finally:
        w.env.close()


if __name__ == "__main__":
    pkg, out = sys.argv[1:3]
    m = export(pkg)
    with open(out, "w") as f:
        json.dump(m, f, indent=1)
    print("%s: %dx%d, %d entities, agent at %s" % (m["level"], m["cols"], m["rows"], len(m["entities"]), m["agent"]["pos"]))
