"""semantic_map.py — a game's semantic map (alf-demo, DEMO.md §3): places with a pose, things at
places, the agent, the task. TEXT mode here (no THOR, no frames: CI and the page's fixtures);
the THOR half (the oracle's exploration tables and frames) is step 1's.

    ALFWORLD_DATA=… .worlds/alf/bin/python world/semantic_map.py GAME_DIR OUT.json [INDEX_URL]

INDEX_URL: the world's tile index as the map's reader finds it from the map file (relative to
it), written as the map's `tileset.index`; the page merges it over its base (DEMO.md §8).

Text mode reads the game's PDDL facts through the host (the generated package's game.json and
alf_host.py, as the driver does) and traj_data.json:
- places = the receptacles (`recat(R, L)`), each at the position its THOR object id carries:
  ALFWorld names a thing by its id (`countertop_bar__minus_01_dot_87_bar__plus_00_dot_96_…` =
  `CounterTop|-01.87|+00.96|+01.80`), so x and z are read from the name, in metres;
  `openable` / `closed` from the facts;
- things = the objects in a receptacle (`inrecep(O, R)`), `pickupable` from the facts; their
  own coordinates too (traj_data's `object_poses` name objects by THOR's instance names,
  `Pan_94f6c891`, so they do not join the PDDL ids; the id's coordinates are the same pose);
- agent = traj_data's `init_action` (TeleportFull x, z, rotation), at nowhere yet, empty-handed;
- edges = every pair (ALFWorld's `go to` reaches any place);
- cell = 0.25: the grid a reader puts the places on, in metres (a kitchen's drawers sit 0.3 m
  apart: at 0.5 they share cells; the architect's ruling);
- task = the annotators' words (`turk_annotations`, the first `task_desc`) and the goal the
  generator resolves (`target(O)` / `dest(R)`): fetch(O, R).
Ids are the program's handles (`countertop3`), names the game's spoken form ("countertop 3").
"""
import json
import os
import re
import shutil
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

_WORD = {"_bar_": "|", "_minus_": "-", "_plus_": "+", "_dot_": "."}
CELL = 0.25                                        # metres per grid cell, for the map's readers (web/map.js)


def thor_id(name):
    """A PDDL name → (type, x, y, z): `countertop_bar__minus_01_dot_87_bar__plus_00_dot_96_bar__plus_01_dot_80`
    → ("countertop", -1.87, 0.96, 1.8); None for a name without coordinates."""
    s = name
    for k, v in _WORD.items():
        s = s.replace(k, v)
    parts = s.split("|")
    if len(parts) < 4:
        return None
    try:
        x, y, z = (float(p.replace("_", "")) for p in parts[1:4])
    except ValueError:
        return None
    return parts[0].strip("_"), x, y, z


def spoken(handle):
    """countertop3 → "countertop 3"."""
    m = re.match(r"^(.*?)(\d+)$", handle)
    return "%s %s" % (m.group(1), m.group(2)) if m else handle


def _args(atom):
    return atom[atom.index("(") + 1:-1].split(",")


def text_map(game_dir, index=None):
    import gen_instance
    from alf_host import AlfHost
    tmp = tempfile.mkdtemp(prefix="alf-map-")
    try:
        path, _, _ = gen_instance.generate(game_dir, tmp)
        meta = json.load(open(os.path.join(os.path.dirname(path), "game.json")))
        facts = open(path).read()
        h = AlfHost(os.path.dirname(path))
        try:
            static, dyn, params, to_name = set(h.static), set(h.dyn), h.params, h.to_name
        finally:
            h.gym.close()
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    traj = json.load(open(os.path.join(game_dir, "traj_data.json")))
    kind = meta["handles"]["kind"]

    def pos(handle):
        t = thor_id(to_name.get(handle, ""))
        return [round(t[1], 2), round(t[3], 2)] if t else None

    places = []
    for a in sorted(a for a in static if a.startswith("recat(")):
        r, _ = _args(a)
        places.append({"id": r, "name": spoken(r), "type": re.sub(r"\d+$", "", r), "pos": pos(r),
                       "openable": "openable(%s)" % r in static,
                       "closed": "openable(%s)" % r in static and "opened(%s)" % r not in dyn, "frame": None})
    things = []
    for a in sorted(a for a in dyn if a.startswith("inrecep(")):
        o, r = _args(a)
        if kind.get(o) != "object":
            continue
        things.append({"id": o, "name": spoken(o), "type": re.sub(r"\d+$", "", o), "at": r, "pos": pos(o),
                       "pickupable": "pickupable(%s)" % o in static})
    ia = traj["scene"].get("init_action") or {}
    ann = traj.get("turk_annotations", {}).get("anns", [])
    words = [a["task_desc"].strip() for a in ann if a.get("task_desc")]
    targets = re.findall(r"^target\((\w+)\)\.", facts, re.M)
    dests = re.findall(r"^dest\((\w+)\)\.", facts, re.M)
    ids = [p["id"] for p in places]
    task = {"text": words[0] if words else "", "goal": "fetch(%s, %s)" % (targets[0], dests[0]) if targets and dests else "",
            "targets": targets, "dests": dests, "params": params,
            "source": "ALFWorld traj_data.json: turk_annotations (the annotators' words)"}
    return {"world": "alfworld", "scene": traj["scene"]["floor_plan"], "units": "m", "mode": "text", "cell": CELL,
            "game": os.path.relpath(game_dir, os.path.dirname(os.path.dirname(os.path.dirname(game_dir)))),
            "places": places, "things": things,
            "agent": {"pos": [round(ia.get("x", 0.0), 2), round(ia.get("z", 0.0), 2)], "yaw": ia.get("rotation", 0),
                      "at": None, "holding": None},
            "edges": [[a, b] for i, a in enumerate(ids) for b in ids[i + 1:]],
            "task": task, "card": world_card(traj["scene"]["floor_plan"], places, things, task),
            "overview": None, "tileset": {"index": [index] if index else []}}


def _kinds(items, key="type"):
    out = {}
    for it in items:
        out.setdefault(it[key], []).append(it["id"])
    return [{"type": k, "n": len(v), "ids": v} for k, v in sorted(out.items())]


ON = ("countertop", "diningtable", "stoveburner", "shelf", "sidetable", "coffeetable", "sofa", "bed", "desk", "dresser", "toilet", "plate", "ottoman")


def prep(place_type):
    return "on" if place_type in ON else "in"


def world_card(scene, places, things, task):
    """The world card (alf-demo step 3b, the user's ask: a model-card-like page of what this world is
    and what can be asked of it, a dock beside TALK / HIERARCHY / JOURNAL): world-neutral keys —
    title, about (lines), room (place kinds with counts), things (thing kinds with counts), asks
    (say, what), cannot (lines), source — generated from the game's own facts, never typed."""
    pick = [t for t in things if t.get("pickupable")]
    rooms = _kinds(places)
    for r in rooms:
        r["openable"] = any(p["openable"] for p in places if p["type"] == r["type"])
    tk = _kinds(pick)
    target = next((t for t in things if t["id"] in task.get("targets", [])), None)
    dest = next((p for p in places if p["id"] in task.get("dests", [])), None)
    other = next((t for t in pick if t["type"] != (target or {}).get("type")), None)
    elsewhere = next((p for p in places if p["id"] != (dest or {}).get("id") and p["type"] in ("fridge", "countertop", "sinkbasin", "diningtable")), None) or (places[0] if places else None)
    asks = []
    if task.get("text"):
        asks.append({"say": task["text"].rstrip(".").lower() if task["text"] else "", "what": "this game's task: the one that wins the game"})
    if target and dest:
        asks.append({"say": "put the %s %s the %s" % (target["type"], prep(dest["type"]), dest["type"]), "what": "the same task in your words: things by kind, a number when the room has several (\"tomato 2\")"})
    if other and elsewhere:
        asks.append({"say": "put the %s %s the %s" % (other["type"], prep(elsewhere["type"]), elsewhere["type"]), "what": "any thing of the room to any place: the agent does it, or asks first when the task wants something else"})
    asks += [{"say": "stop", "what": "the agent stops what it is doing and waits"},
             {"say": "new game", "what": "the same room from its start, the task again"}]
    return {"title": "ALFWorld kitchen %s" % scene,
            "about": ["ALFWorld: a household scene from ALFRED, in text mode (TextWorld): one game is one room and one task.",
                      "The agent moves between places, opens what is closed, takes one thing at a time and puts it in or on a place.",
                      "%d places of %d kinds, %d things you can ask for (%d kinds)." % (len(places), len(rooms), len(pick), len(tk))],
            "room": rooms, "things": tk, "asks": asks,
            "cannot": ["a single step on its own (just go, just open, just pick up): the agent takes whole errands",
                       "a thing that is not in this room, or a place that is not",
                       "another task after the game is won: say \"new game\" first"],
            "source": "generated from the game's facts by world/semantic_map.py"}


if __name__ == "__main__":
    game, out = sys.argv[1:3]                  # read first: the game's loader rewrites sys.argv
    index = sys.argv[3] if len(sys.argv) > 3 else None
    m = text_map(game, index)
    with open(out, "w") as f:          # closed now: the game's child can end the process hard at exit
        json.dump(m, f, indent=1)
    print("%s: %d places, %d things; task %r → %s" % (m["scene"], len(m["places"]), len(m["things"]),
                                                     m["task"]["text"], m["task"]["goal"]))
