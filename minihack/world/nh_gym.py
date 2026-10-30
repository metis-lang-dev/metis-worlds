"""nh_gym.py — the real game as the hierarchy's world: mh_gym.py's protocol over NetHack's tty (nh_tty.py), a child
under the world's venv, one JSON request per line. The rules and the map are the hierarchy's (mh_hier, semantic_world's
grid in view mode: nothing known until seen); only the world under them changed.

  {"op": "open", "map_doc": PATH, "card": {...}}  → {"size", "cells", "actions"} + the perception
  {"op": "reset", "seed": S}                      → the perception (the game goes on: a real game is never reset)
  {"op": "step", "action": NAME}                  → the perception + {"reward", "done", "won"}; prompts answered
  {"op": "keys", "keys": STR}                     → the perception: the person's keys, as typed, nothing answered
  {"op": "frames"}                                → {"frames": [...]}: the page's world/* frames since the last call
The perception: {"atoms", "events", "message", "done", "won", "dlvl", "game"}. Map cell (x, y) is c<x>_<y>; dlvl and game
change when the level or the game does (the host then starts its map again).
"""
import json
import os
import re
import select
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from nh_tty import COLS, MAP_COLS, MAP_ROWS, MG_PET, Game, Tty, describe   # noqa: E402
from perceive import MESSAGES                                              # noqa: E402

KEYS = {"N": "k", "S": "j", "E": "l", "W": "h", "NE": "u", "NW": "y", "SE": "n", "SW": "b", "PICKUP": ",", "EAT": "e", "DOWN": ">",
        "WAIT": "s", "SEARCH": "s", "OPEN": "o", "KICK": "\x04", "APPLY": "a", "MORE": "\r", "ESC": "\x1b"}
WANTS_DIR = {"OPEN", "KICK"}
IMPASSABLE = re.compile(r"\b(bars|tree|pool|lava|water|air|cloud|closed drawbridge)\b")
FRESH_SCREEN_EVERY = 10             # frames calls between two world/screen frames, unchanged (a page opened since)


def name_of(text):
    return re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_") or "thing"


def events_of(message):
    low = message.lower()
    kinds = [k for pat, k in MESSAGES if re.search(pat, low)]
    return ["said(%s)" % k for k in (kinds or (["other"] if message else []))]


def status_atoms(status):
    out, line = [], " ".join(status)
    m = re.search(r"HP:(\d+)\((\d+)\)", line)
    if m:
        out += ["hp(%s)" % m[1], "hpmax(%s)" % m[2]]
    m = re.search(r"\bT:(\d+)", line)
    if m:
        out.append("turn(%s)" % m[1])
    m = re.search(r"\b(Satiated|Hungry|Weak|Fainting|Fainted)\b", line)
    out.append("hunger(%s)" % (m[1].lower() if m else "normal"))
    return out


def cell_atoms(C, tile, flags):
    """What one drawn cell says, in the perceiver's vocabulary (perceive.py)."""
    name, kind = describe(tile)
    if kind == "monster":
        return ["floor(%s)" % C] if flags & MG_PET else ["monster(%s,%s)" % (name_of(name), C), "floor(%s)" % C]   # a pet swaps places
    if kind == "object":
        return ["obj(%s,%s)" % (name_of(name), C), "floor(%s)" % C]
    if "closed door" in name:
        return ["door(%s,closed)" % C]
    if "open door" in name:
        return ["door(%s,open)" % C]
    if "staircase down" in name or "ladder down" in name:
        return ["stairs_down(%s)" % C, "floor(%s)" % C]
    if "staircase up" in name or "ladder up" in name:
        return ["stairs_up(%s)" % C, "floor(%s)" % C]
    if "corridor" in name:
        return ["corridor(%s)" % C]
    if IMPASSABLE.search(name) or "wall" in name:
        return ["wall(%s)" % C]
    if name == "stone":
        return []
    if kind == "place" and re.search(r"trap|pit|hole|web|portal|field|squeaky|mine|teleporter", name):
        return ["trap(%s,%s)" % (name_of(name), C), "floor(%s)" % C]
    return ["floor(%s)" % C]


class Gym:
    def __init__(self, options=None):
        self.options = options
        self.game, self.tty, self.over, self.games, self.want_dir = None, None, False, 0, False
        self.map_doc, self.card = None, {}
        self.last, self.calls, self.said, self.sent_text = None, 0, "", None

    # ── the process ──
    def start(self):
        self.game, self.tty, self.over, self.last, self.said = Game(self.options) if self.options else Game(), Tty(), False, None, ""
        self.games += 1
        self.game.start()
        self.settle(1.0)
        for _ in range(12):                 # the welcome and "Restoring save file...--More--": the map is behind them
            s = self.tty.snapshot()
            if s["hero"] and not s["more"]:
                break
            self.press("\r" if s["more"] else "")
            self.settle(0.5)

    def press(self, keys):
        if keys:
            self.tty.waiting = False
            self.game.keys(keys.encode("latin-1", "ignore"))

    def drain(self):
        got = False
        while self.game and not self.over and select.select([self.game.fd], [], [], 0)[0]:
            d = self.game.read()
            if d is None:
                break
            if d == b"":
                self.over = True
                self.game.stop()
                break
            self.tty.feed(d)
            got = True
        return got

    def settle(self, timeout=2.0):
        """Until the game waits for a key and has been quiet a moment (or the time is up)."""
        end, quiet = time.time() + timeout, time.time()
        while time.time() < end and not self.over:
            if select.select([self.game.fd], [], [], 0.02)[0]:
                self.drain()
                quiet = time.time()
            elif self.tty.waiting and time.time() - quiet > 0.03:
                return

    # ── the perception ──
    def perceive(self, events=(), message=None):
        s = self.tty.snapshot()
        if self.over:
            return {"atoms": [], "events": list(events) + ["said(died)"], "message": "The game has ended.", "done": True, "won": False,
                    "reward": 0.0, "dlvl": 0, "game": self.games}
        cells = self.last["cells"] if s["text"] and self.last else s["cells"]
        hero = (self.last["hero"] if s["text"] and self.last else s["hero"])
        atoms = set(status_atoms(s["status"]))
        for y, row in enumerate(cells):
            for x, c in enumerate(row):
                if not c:
                    continue
                C = "c%d_%d" % (x, y)
                if hero and (x, y) == tuple(hero[:2]):
                    atoms.update(("agent_at(%s)" % C, "floor(%s)" % C))
                else:
                    atoms.update(cell_atoms(C, c["tile"], c["flags"]))
        m = re.search(r"Dlvl:(\d+)", " ".join(s["status"]))
        msg = s["message"] if message is None else message
        return {"atoms": sorted(atoms), "events": list(events) or events_of(msg), "message": msg, "done": False, "won": False, "reward": 0.0,
                "dlvl": int(m[1]) if m else None, "game": self.games}

    # ── the protocol ──
    def open(self, map_doc=None, card=None, **_):
        self.map_doc, self.card = map_doc, card or {}
        self.start()
        self.write_map()
        return dict(self.perceive(), size=[MAP_COLS, MAP_ROWS], cells=[], actions=sorted(KEYS))

    def reset(self, **_):
        self.settle(0.2)
        return self.perceive()

    def clear_prompt(self):
        s = self.tty.snapshot()
        if s["more"]:
            self.press("\r")
        elif s["text"] or s["prompt"]:
            self.press("\x1b")
        else:
            return False
        self.settle(0.5)
        return True

    def step(self, action, **_):
        """One action of the hierarchy's: whatever the game then asks is answered as mh_gym answers it (a y/n "n", nothing
        else left waiting), so the rules see a game that is waiting for its next command."""
        if self.over:
            return self.perceive()
        self.settle(0.05)
        if not (self.want_dir and action in ("N", "S", "E", "W", "NE", "NW", "SE", "SW")):
            for _ in range(5):              # the person may have left a prompt open
                if not self.clear_prompt():
                    break
        self.want_dir = action in WANTS_DIR
        keys = action[4:5] if action.startswith("KEY:") else KEYS.get(action)
        if keys is None:
            raise ValueError("no key for action %r" % action)
        self.press(keys)
        self.settle(1.0)
        if action == "PICKUP" and self.tty.snapshot()["text"]:   # several things here: the menu, all of them
            self.press(",\r")
            self.settle(0.5)
        said, events = [], []
        for _ in range(12):
            if self.over:
                break
            s = self.tty.snapshot()
            if s["message"] and s["message"] not in said:
                said.append(s["message"])
                events += [e for e in events_of(s["message"]) if e not in events]
            if self.want_dir and s["prompt"]:
                break
            if s["more"]:
                self.press("\r")
            elif s["text"]:
                self.press("\x1b")
            elif s["prompt"] and re.search(r"\[yn[aq]*\]", s["message"]):
                self.press("n")
            elif s["prompt"]:
                self.press("\x1b")
            else:
                break
            self.settle(0.5)
        return self.perceive(events, " ".join(said))

    def keys(self, keys="", **_):
        if self.over:
            self.start()
            self.write_map()
            return self.perceive()
        self.want_dir = False
        self.press(keys)
        self.settle(0.5)
        return self.perceive()

    # ── the page ──
    def things(self, cells, hero):
        out = {}
        for y, row in enumerate(cells):
            for x, c in enumerate(row):
                if not c or (hero and (x, y) == tuple(hero[:2])):
                    continue
                name, kind = describe(c["tile"])
                if kind:
                    pet = kind == "monster" and c["flags"] & MG_PET
                    out["%s@%d_%d" % (kind, x, y)] = {"id": "%s@%d_%d" % (kind, x, y), "name": name + (" (your pet)" if pet else ""), "pos": [x, y],
                                                      "tile": c["tile"], "ch": c["ch"], "kind": kind}
        return out

    def agent(self, hero):
        return {"pos": [hero[0], hero[1]], "yaw": None, "tile": hero[2], "ch": "@", "name": "you"} if hero else \
            {"pos": [0, 0], "yaw": None, "tile": None, "ch": "@", "name": "you"}

    def write_map(self):
        s = self.tty.snapshot()
        if s["text"] and self.last:
            s = dict(s, cells=self.last["cells"], hero=self.last["hero"])
        doc = {"world": "nethack", "level": "the real game", "raw_tiles": True, "keys": True, "cols": MAP_COLS, "rows": MAP_ROWS,
               "cells": [[c and {"t": c["tile"], "ch": c["ch"]} for c in row] for row in s["cells"]],
               "entities": list(self.things(s["cells"], s["hero"]).values()), "agent": self.agent(s["hero"]),
               "task": {"text": "", "goal": "", "room": False, "source": "the person's words"}, "card": self.card, "tileset": {"index": []},
               "screen": {"status": s["status"], "text": s["text"]}}
        if self.map_doc:
            t = self.map_doc + ".tmp"
            with open(t, "w") as f:
                json.dump(doc, f)
            os.replace(t, self.map_doc)

    def frames(self, **_):
        self.drain()
        out, self.calls = [], self.calls + 1
        if self.over:
            return {"frames": [{"ev": "world/message", "text": "The game has ended: press a key to start another."}] if self.last else []}
        s = self.tty.snapshot()
        was = self.last
        if not s["text"]:
            things = self.things(s["cells"], s["hero"])
            cells, old_cells = [], was["cells"] if was else None
            for y, row in enumerate(s["cells"]):
                for x, c in enumerate(row):
                    o = old_cells[y][x] if old_cells else None
                    if (c and c["tile"]) != (o and o["tile"]):
                        cells.append({"pos": [x, y], "tile": c["tile"] if c else None})
            old = was["things"] if was else {}
            ents = [t for i, t in things.items() if old.get(i) != t] + [{"id": i, "gone": True} for i in old if i not in things]
            d = {"ev": "world/delta"}
            if cells:
                d["cells"] = cells
            if ents:
                d["entities"] = ents
            if s["hero"] and (not was or was.get("hero") != s["hero"]):
                d["agent"] = self.agent(s["hero"])
            if len(d) > 1:
                out.append(d)
                self.last = {"cells": s["cells"], "things": things, "hero": s["hero"]}
                self.write_map()
            elif not was:
                self.last = {"cells": s["cells"], "things": things, "hero": s["hero"]}
        screen = {"ev": "world/screen", "status": s["status"], "text": s["text"], "more": s["more"], "prompt": s["message"] if s["prompt"] else ""}
        if screen != self.sent_text or self.calls % FRESH_SCREEN_EVERY == 0:
            out.append(screen)
            self.sent_text = screen
        msg = s["message"]
        if msg and msg != self.said:
            out.append({"ev": "world/message", "text": msg})
        self.said = msg
        return {"frames": out}


def main():
    gym, ops = Gym(), None
    ops = {"open": gym.open, "reset": gym.reset, "step": gym.step, "keys": gym.keys, "frames": gym.frames}
    for line in sys.stdin:
        req = json.loads(line)
        op = req.pop("op")
        if op == "close":
            if gym.game and not gym.over:
                gym.game.stop()
            print(json.dumps({"ok": True}), flush=True)
            return
        try:
            print(json.dumps(dict(ops[op](**req), ok=True)), flush=True)
        except Exception as e:
            print(json.dumps({"ok": False, "error": "%s: %s" % (type(e).__name__, e)}), flush=True)


if __name__ == "__main__":
    main()
