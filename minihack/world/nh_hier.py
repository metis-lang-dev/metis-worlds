"""nh_hier.py — the real game installed for metis-agent: mh_hier's hierarchy (director, task, nav, act over roles) with
the real game as its world (nh_host.py), and the service's config for this world's own page (minihack/web).

    python world/nh_hier.py ROOT [--port P]     ROOT/.run/config.yaml, ROOT/world-map.json
"""
import argparse
import json
import os
import shutil
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import mh_hier  # noqa: E402

SIZE = [79, 21]
WEB = os.path.join(os.path.dirname(HERE), "web")
ASKS = [{"say": "go to the stairs", "what": "the agent walks there: it explores until it has seen them, opens doors and fights what blocks the way"},
        {"say": "go north", "what": "one step: north, south, east, west, northeast, northwest, southeast, southwest"},
        {"say": "search here", "what": "search this cell and around it for a turn"},
        {"say": "pick that up", "what": "take what lies on this cell"},
        {"say": "go down the stairs", "what": "descend, standing on the stairs down"}]
CARD = {"title": "NetHack 3.6.6", "about": ["The real game on a tty: the page draws the tile the game names for each cell.",
                                            "Tell the agent what to do in your words, or play it yourself on the keyboard: both act in one game."],
        "asks": ASKS, "cannot": ["fight, eat, use things or plan beyond the stairs on its own yet: the rest of the domain is the agentic loop's to make"],
        "source": "metis-worlds minihack/world/nh_hier.py"}
# the task's single commands: each rule's name is the command (MhHost.action_of), its goal the card's atom
TASK_EXTRA = {"goals": ("walk", "search_here", "pick_up", "go_down"),
              "decls": ["type dir {n e s w ne se sw nw}.", "pred walk(dir) : task.", "pred search_here : task.", "pred pick_up : task.", "pred go_down : task."],
              "rules": ["  %% I step {D}.", "  move [dyn] : walk(D) -o done * tick__active(task) * tick__done(task).",
                        "  %% I search here.", "  search [dyn] : search_here -o done * tick__active(task) * tick__done(task).",
                        "  %% I pick up what lies here.", "  pickup [dyn] : pick_up -o done * tick__active(task) * tick__done(task).",
                        "  %% I go down.", "  down [dyn] : go_down -o done * tick__active(task) * tick__done(task)."]}
TASK_CARD = """# task's intents (world/nh_hier.py): what the person asks in a real game of NetHack. REACH is the errand the rules plan
# (task, nav, act under the director); the others are one command each, a rule of the task's named after it.
persona: |
  You are the player's helper in a game of NetHack. Map what they say to exactly one intent JSON per utterance. Respond with
  only the JSON.

verbs:
  - {verb: REACH, meaning: "walk to the stairs down: the goal, the way down, the exit, finishing the level"}
  - {verb: MOVE, meaning: "one step in a direction", slots: [direction]}
  - {verb: SEARCH, meaning: "search here for hidden things, for one turn"}
  - {verb: PICKUP, meaning: "pick up what lies on this cell"}
  - {verb: DESCEND, meaning: "take the stairs down from this very cell"}
  - {verb: CHITCHAT, meaning: "small talk, not an errand: an acknowledgement, thanks, a greeting, a comment"}
  - {verb: UNKNOWN, meaning: "anything else: an action you cannot do here, or a question about what you can do"}

slots:
  direction: {enum: [NORTH, SOUTH, EAST, WEST, NORTHEAST, NORTHWEST, SOUTHEAST, SOUTHWEST]}

guidance: |
  Walking, going, heading or stepping one way is MOVE with its direction: up is NORTH, down the screen is SOUTH, left is WEST,
  right is EAST. Going to the stairs from anywhere, or finishing the level, is REACH; "go down", "descend" or "take the stairs"
  said of the stairs under you is DESCEND. Taking, grabbing or getting what is here is PICKUP. Looking for something hidden is
  SEARCH. Fighting, eating, opening, reading and everything else is UNKNOWN. Words that ask for no errand at all are CHITCHAT.

examples:
  - ["go to the stairs", {"intent":"REACH"}]
  - ["find the way down", {"intent":"REACH"}]
  - ["complete the level", {"intent":"REACH"}]
  - ["north", {"intent":"MOVE","direction":"NORTH"}]
  - ["go north", {"intent":"MOVE","direction":"NORTH"}]
  - ["step left", {"intent":"MOVE","direction":"WEST"}]
  - ["move southeast", {"intent":"MOVE","direction":"SOUTHEAST"}]
  - ["search", {"intent":"SEARCH"}]
  - ["search here", {"intent":"SEARCH"}]
  - ["look for hidden doors", {"intent":"SEARCH"}]
  - ["pick that up", {"intent":"PICKUP"}]
  - ["take it", {"intent":"PICKUP"}]
  - ["grab the item here", {"intent":"PICKUP"}]
  - ["go down the stairs", {"intent":"DESCEND"}]
  - ["descend", {"intent":"DESCEND"}]
  - ["hello there", {"intent":"CHITCHAT"}]
  - ["thanks", {"intent":"CHITCHAT"}]
  - ["cast a fireball", {"intent":"UNKNOWN"}]
  - ["what can you do", {"intent":"UNKNOWN"}]

spoken:
  heading: Spoken response (after the JSON)
  text: |
    After the JSON comes "Spoken response:" and one short sentence the helper says, in the first person.
    Never JSON, never an intent name.
  examples:
    - ["go to the stairs", {"intent":"REACH"}, "I'll walk to the stairs."]
    - ["go north", {"intent":"MOVE","direction":"NORTH"}, "Going north."]
    - ["hello there", {"intent":"CHITCHAT"}, "Hello."]

map:
  - {verb: REACH, atom: "reach(goal)", act: reach}
  - {verb: MOVE, atom: "walk({direction:direction})", act: walk}
  - {verb: SEARCH, atom: "search_here", act: search_here}
  - {verb: PICKUP, atom: "pick_up", act: pick_up}
  - {verb: DESCEND, atom: "go_down", act: go_down}
values:
  direction: {NORTH: n, SOUTH: s, EAST: e, WEST: w, NORTHEAST: ne, NORTHWEST: nw, SOUTHEAST: se, SOUTHWEST: sw}

asks: []
outcomes: {goto: progress, done: done, stuck: refused}
alternatives:
  max: 0
  rules: {}
"""


def install(root, port=8399):
    if os.path.exists(root):
        shutil.rmtree(root)
    os.makedirs(root)
    root = os.path.abspath(root)
    doc = os.path.join(root, "world-map.json")
    out = mh_hier.install("", root, view=True, name="nethack", max_steps=10 ** 9, info={"size": SIZE, "cells": []}, card=TASK_CARD, task_extra=TASK_EXTRA, tree=True)
    for sp in mh_hier.SPECS:
        pkg = out[sp]
        p = os.path.join(pkg, "level.json")
        level = json.load(open(p))
        level.update(map_doc=doc, card=CARD, surprises=os.path.join(os.path.dirname(root), "nh-records", "surprises.jsonl"))   # beside ROOT: this install starts ROOT afresh
        json.dump(level, open(p, "w"), indent=1)
        shim = os.path.join(pkg, "mh_host.py")
        text = open(shim).read().replace('MhHost = world_host(HERE, "mh_host"', 'MhHost = world_host(HERE, "nh_host"').replace('.MhHost\n', '.NhHost\n')
        open(shim, "w").write(text)
    json.dump({"world": "nethack", "raw_tiles": True, "keys": True, "cols": SIZE[0], "rows": SIZE[1], "cells": [[None] * SIZE[0] for _ in range(SIZE[1])],
               "entities": [], "agent": {"pos": [0, 0], "yaw": None, "tile": None, "ch": "@"}, "task": {}, "card": CARD, "tileset": {"index": []}}, open(doc, "w"))
    import yaml
    cfg_path = os.path.join(root, ".run", "config.yaml")
    c = yaml.safe_load(open(cfg_path))
    c["v3"]["world_map"] = doc
    c["domains"]["consult"] = False            # no seat: the watch opens no record here (nh_host.py), surprises are written down and play goes on
    c["ws"] = {"addr": "127.0.0.1:%d" % port, "ui": WEB}
    yaml.safe_dump(c, open(cfg_path, "w"), sort_keys=False)
    return cfg_path


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("root")
    ap.add_argument("--port", type=int, default=8399)
    a = ap.parse_args()
    print(install(a.root, a.port))
