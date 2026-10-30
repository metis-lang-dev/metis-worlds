"""nh_demo.py — the real game on its own page (minihack/web): NetHack's tty (world/nh_tty.py) as the page's frames, the
wire of metis-agent's service, so the agent can take this place; independent of ALFWorld. No agent yet: the NetHack domain is the agentic loop's to make, so
the chat passes the person's words to the game as commands (WORDS) and the keyboard plays it directly.

    minihack/demo.sh [ADDR]                  http://127.0.0.1:8399/world.html

The frames: world/map, world/delta (the changed cells, the things), world/status (state, the message), world/screen (the
status lines, a menu or a page over the map), narration + journal (the game's messages, the person's words).
Hanging up saves the game, the next start restores it.
"""
import argparse
import asyncio
import json
import logging
import os
import sys
import time

from aiohttp import WSMsgType, web

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "world"))
from nh_tty import COLS, MAP_COLS, MAP_ROWS, MG_PET, Game, Tty, describe   # noqa: E402

WEB = os.path.join(os.path.dirname(HERE), "web")
# the chat's words → the game's keys; one token goes as typed (`20s`, `y`), a `#command` with its Return; a sentence the
# table does not know goes nowhere (each of its letters would be a command in the game)
WORDS = {"north": "k", "south": "j", "east": "l", "west": "h", "northeast": "u", "northwest": "y", "southeast": "n",
         "southwest": "b", "up": "<", "down": ">", "search": "s", "wait": "s", "look": ":", "look here": ":",
         "inventory": "i", "pick up": ",", "pickup": ",", "eat": "e", "open": "o", "close": "c", "kick": "\x04",
         "zap": "z", "quaff": "q", "read": "r", "wear": "W", "wield": "w", "drop": "d", "apply": "a", "pray": "#pray\r",
         "yes": "y", "no": "n", "more": "\r", "next": "\r", "enter": "\r", "escape": "\x1b", "esc": "\x1b", "cancel": "\x1b"}
ASKS = [{"say": "north", "what": "move: north, south, east, west, northeast, … (or hjklyubn and the arrows)"},
        {"say": "search", "what": "search here for a turn"},
        {"say": "look here", "what": "what lies on this cell"},
        {"say": "inventory", "what": "what you carry (a page over the map: \"esc\" closes it)"},
        {"say": "pick up", "what": "take what lies here"},
        {"say": "down", "what": "take the stairs down"},
        {"say": "more", "what": "the next line, at --More--"}]
CARD = {"title": "NetHack 3.6.6", "about": ["The real game, from its source, on a tty: the page draws the tile the game names for each cell.",
                                            "There is no agent here yet: the NetHack domain is the agentic loop's to make. Your words and your keys are the game's commands."],
        "asks": ASKS, "cannot": ["choose for you: nothing here plans or acts on its own"],
        "source": "metis-worlds minihack/experiments/nh_demo.py"}


def key_of(text):
    t = text.strip()
    w = WORDS.get(t.lower())
    if w is not None:
        return w
    if t.startswith("#"):
        return t + "\r"
    return None if " " in t else t


class Demo:
    def __init__(self):
        self.clients, self.seq = set(), 0
        self.game, self.tty, self.last, self.said, self.over = None, None, None, "", False
        self.pending, self.log, self.state, self.booting = None, [], None, True

    # ── the game ──
    def start_game(self):
        self.game, self.tty, self.last, self.said, self.over, self.booting = Game(), Tty(), None, "", False, True
        self.game.start()
        asyncio.get_running_loop().add_reader(self.game.fd, self.on_read)

    def on_read(self):
        data = self.game.read()
        if data is None:
            return
        if data == b"":
            asyncio.get_running_loop().remove_reader(self.game.fd)
            self.game.stop()
            self.over = True
            self.broadcast({"ev": "world/status", "state": "over", "text": "The game has ended: say anything to start another."})
            return
        self.tty.feed(data)
        if self.pending:
            self.pending.cancel()
        self.pending = asyncio.get_running_loop().call_later(0.03, self.publish)

    def press(self, data):
        if self.over or not self.game:
            self.start_game()
            asyncio.get_running_loop().create_task(self.say_map())
            return
        s = self.tty.snapshot()
        if data == "\r" and not (s["more"] or s["text"] or s["prompt"]):
            return                                          # Return on the map is the game's "move south": never by accident
        self.game.keys(data.encode("latin-1", "ignore"))

    async def say_map(self):
        await asyncio.sleep(0.2)
        self.broadcast({"ev": "world/map", "url": f"world/map.json?t={time.time()}"})

    # ── the frames ──
    def things(self, snap):
        out, hero = {}, snap["hero"]
        for y, row in enumerate(snap["cells"]):
            for x, c in enumerate(row):
                if not c or (hero and (x, y) == hero[:2]):
                    continue
                name, kind = describe(c["tile"])
                if kind:
                    pet = kind == "monster" and c["flags"] & MG_PET
                    out[f"{kind}@{x}_{y}"] = {"id": f"{kind}@{x}_{y}", "name": name + (" (your pet)" if pet else ""), "pos": [x, y],
                                              "tile": c["tile"], "ch": c["ch"], "kind": kind}
        return out

    def agent(self, snap):
        h = snap["hero"]
        return {"pos": [h[0], h[1]], "yaw": None, "tile": h[2], "ch": "@", "name": "you"} if h else {"pos": [0, 0], "yaw": None, "tile": None, "ch": "@", "name": "you"}

    def map_json(self):
        snap = self.tty.snapshot()
        if snap["text"] and self.last:                      # a menu over the map: the map as it was
            snap = {**snap, "cells": self.last["cells"], "hero": self.last["hero"]}
        return {"world": "nethack", "level": "the real game", "raw_tiles": True, "keys": True, "cols": MAP_COLS, "rows": MAP_ROWS,
                "cells": [[c and {"t": c["tile"], "ch": c["ch"]} for c in row] for row in snap["cells"]],
                "entities": list(self.things(snap).values()), "agent": self.agent(snap),
                "task": {"text": "", "goal": "", "room": False, "source": "the person plays"}, "card": CARD, "tileset": {"index": []}}

    def publish(self):
        snap = self.tty.snapshot()
        if self.booting:                                    # the welcome and "Restoring save file...--More--": nobody's to answer, the map is behind them
            if snap["hero"]:
                self.booting = False
            elif snap["more"]:
                self.game.keys(b"\r")
        was = self.last
        frozen = bool(snap["text"])                         # a menu or a page over the map: the map stays as it was
        if not frozen:
            cells = []
            things = self.things(snap)
            old_cells = was["cells"] if was else None
            for y, row in enumerate(snap["cells"]):
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
            if snap["hero"] and (not was or was.get("hero") != snap["hero"]):
                d["agent"] = self.agent(snap)
            if len(d) > 1:
                self.broadcast(d)
            self.last = {"cells": snap["cells"], "things": things, "hero": snap["hero"]}
        self.broadcast({"ev": "world/screen", "status": snap["status"], "text": snap["text"], "more": snap["more"]})
        msg = snap["message"]
        if msg and msg != self.said:
            self.said = msg
            self.seq += 1
            self.broadcast({"ev": "narration", "id": f"g{self.seq}", "sentence": msg, "kind": "v3-card"})
            self.journal({"kind": "dlg-say", "what": "world", "text": msg})
        elif not msg:
            self.said = ""
        state = "asking" if snap["prompt"] and not snap["more"] else "waiting" if snap["waiting"] else "working"
        text = "--More--: Return for the next line" if snap["more"] else "Esc closes this page" if snap["text"] else msg if state == "asking" else "Your move."
        if (state, text) != self.state and state != "working":
            self.state = (state, text)
            self.broadcast({"ev": "world/status", "state": state, "text": text})

    def journal(self, rec):
        rec = {"seq": len(self.log) + 1, "t": time.time(), **rec}
        self.log.append(rec)
        self.broadcast({"ev": "journal", "rec": rec})

    def broadcast(self, f):
        s = json.dumps(f)
        for ws in list(self.clients):
            if not ws.closed:
                asyncio.ensure_future(ws.send_str(s))

    # ── the wire ──
    async def ws(self, req):
        ws = web.WebSocketResponse(heartbeat=30)
        await ws.prepare(req)
        self.clients.add(ws)
        try:
            async for m in ws:
                if m.type != WSMsgType.TEXT:
                    continue
                f = json.loads(m.data)
                if f.get("ev") == "hello":
                    await ws.send_str(json.dumps({"ev": "world/map", "url": f"world/map.json?t={time.time()}"}))
                    self.state = None
                    self.publish()
                elif f.get("ev") == "say_text":
                    text = f.get("text", "")
                    self.journal({"kind": "dlg-wake", "what": "person", "person": text})
                    keys = key_of(text)
                    if keys is None:
                        await ws.send_str(json.dumps({"ev": "intent", "id": f["id"], "intent": "", "voice": f"I don't know that command: {text}. The world card lists what you can say."}))
                        continue
                    self.press(keys)
                    await ws.send_str(json.dumps({"ev": "intent", "id": f["id"], "intent": {"intent": "KEYS", "keys": keys.replace("\r", "⏎").replace("\x1b", "esc")}, "voice": ""}))
                elif f.get("ev") == "keys":
                    self.press(f.get("keys", ""))
        finally:
            self.clients.discard(ws)
        return ws

    async def map_route(self, req):
        return web.json_response(self.map_json())

    async def games_route(self, req):
        return web.json_response({"games": []})             # one game: no picker on the page

    async def journal_route(self, req):
        return web.Response(text="".join(json.dumps(r) + "\n" for r in self.log), content_type="text/plain")

    async def on_start(self, app):
        self.start_game()

    async def on_shutdown(self, app):
        for ws in list(self.clients):                       # an open page would hold the shutdown (and the game's save) for a minute
            await ws.close()

    async def on_stop(self, app):
        if self.game and not self.over:
            self.game.stop()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--addr", default="127.0.0.1:8399")
    a = ap.parse_args()
    logging.basicConfig(level=logging.INFO, stream=sys.stdout, format="%(asctime)s %(message)s")
    host, port = a.addr.rsplit(":", 1)
    demo = Demo()
    app = web.Application()
    app.router.add_get("/ws", demo.ws)
    app.router.add_get("/world/map.json", demo.map_route)
    app.router.add_get("/world/journal.jsonl", demo.journal_route)
    app.router.add_get("/world/games.json", demo.games_route)
    app.router.add_get("/favicon.ico", lambda req: web.Response(status=204))
    app.router.add_static("/", WEB)
    app.on_startup.append(demo.on_start)
    app.on_shutdown.append(demo.on_shutdown)
    app.on_cleanup.append(demo.on_stop)
    print(f"the page: http://{host}:{port}/world.html", flush=True)
    web.run_app(app, host=host, port=int(port), print=None, shutdown_timeout=5)


if __name__ == "__main__":
    main()
