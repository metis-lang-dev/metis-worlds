"""nh_tty.py — the real game's tty as data: NetHack 3.6.6 built with the tile hints (nethack/build.sh) behind a pty, its
screen in a terminal emulator (pyte), each map cell with the tile the game itself named for it. Tilehack's idea
(https://www.jwhitham.org/tilehack/, TelnetTiles before it): the game says which tile, the client never guesses from a
character and its colour (55% of the monsters and 93% of the objects share theirs with another). Rewritten here for
3.6.6's own codes, the map schema of minihack/web/map.js and no terminal in the browser.

    ESC [ 1 ; 0 ; tile ; flags z   a glyph starts       ESC [ 1 ; 2 ; window z   output goes to that window
    ESC [ 1 ; 1 z                  the glyph ends       ESC [ 1 ; 3 z            the game waits for input

    tty = Tty(); tty.feed(bytes)                 the parser alone (no game; the tests)
    game = Game(); game.start(); game.keys(b"s") the game; game.fd for the caller's loop, game.read() → feed
    tty.snapshot() → {cells, agent, message, status, text, more, waiting}

Map cell (x, y) is the screen's column x, row y + 1 (row 0 the message line, 22 and 23 the status).
"""
import fcntl
import glob
import os
import pty
import re
import signal
import struct
import termios

import pyte

COLS, ROWS, MAP_ROWS = 80, 24, 21
MAP_COLS = 79
NHW_MAP = 3
MG_PET = 0x08
CODE = re.compile(rb"\x1b\[1;(\d+)(?:;(\d+))?(?:;(\d+))?z")
PARTIAL = re.compile(rb"\x1b(?:\[[0-9;]*)?$")               # a code cut by the read: held for the next one

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
GAME = os.path.join(REPO, ".nethack", "install", "games", "nethack")
SHARE = os.path.join(REPO, ".nethack", "src", "win", "share")
OPTIONS = ("name:agent,role:Valkyrie,race:human,gender:female,align:neutral,pettype:cat,!legacy,!splash_screen,"
           "!autopickup,color,time,showexp,msg_window:single,vt_tiledata,windowtype:tty")
# what is ground, not a thing: the map draws it, the page names none of it
GROUND = re.compile(r"\b(wall|corner|junction|stone|doorway|floor of a room|dark part of a room|corridor|"
                    r"cross wall|tee|tree \(dummy\))\b")


class Tty:
    """The screen and the tile of each map cell. A cell keeps its tile only while the screen still shows the character
    it was drawn with, so a menu over the map, a clear or a line of text takes it away by itself."""

    def __init__(self):
        self.screen = pyte.Screen(COLS, ROWS)
        self.stream = pyte.ByteStream(self.screen)
        self.tiles = {}                                     # (row, col) → (tile, flags, ch)
        self.window, self.glyph, self.held = 0, None, b""
        self.waiting = False
        self.hero = None                                    # (x, y, tile): the cell under the cursor when last waiting

    def feed(self, data):
        data, self.held = self.held + data, b""
        cut = PARTIAL.search(data)
        if cut:
            data, self.held = data[:cut.start()], data[cut.start():]
        at = 0
        for m in CODE.finditer(data):
            self.stream.feed(data[at:m.start()])
            at = m.end()
            self.code(*(int(g) if g else None for g in m.groups()))
        self.stream.feed(data[at:])
        if data:
            self.waiting = self.waiting and not data[at:].strip()

    def code(self, kind, a, b):
        cur = self.screen.cursor
        if kind == 0:
            self.glyph = (a, b or 0, cur.y, cur.x)
        elif kind == 1 and self.glyph:
            tile, flags, y, x = self.glyph
            self.glyph = None
            if self.window == NHW_MAP:
                self.tiles[(y, x)] = (tile, flags, self.screen.buffer[y][x].data)
        elif kind == 2:
            self.window = a
        elif kind == 3:
            self.waiting = True

    def cell(self, row, col):
        t = self.tiles.get((row, col))
        return t if t and self.screen.buffer[row][col].data == t[2] else None

    def snapshot(self):
        """The map's cells (None: nothing drawn; frozen is the caller's when text lies over the map), the hero, and what
        is text: the message line, the two status lines, a menu or a page over the map."""
        s = self.screen
        cells, text = [], []
        for y in range(MAP_ROWS):
            row, line = [], [" "] * COLS
            for x in range(COLS):
                t = self.cell(y + 1, x)
                if x < MAP_COLS:
                    row.append(t and {"tile": t[0], "flags": t[1], "ch": t[2]})
                if not t:
                    line[x] = s.buffer[y + 1][x].data
            cells.append(row)
            text.append("".join(line).rstrip())
        over = [l for l in text if l.strip()]
        message = s.display[0].rstrip()
        if over:                                            # a menu's first line lies on the message line: it is the menu's
            # from where the text starts, as the screen shows it: a letter that happens to be the map cell's own under it is the text's too
            left = min(len(l) - len(l.lstrip()) for l in over)
            text = [s.display[y + 1][left:].rstrip() if text[y].strip() else "" for y in range(MAP_ROWS)]
            text, message = [message] + text, ""
        cur = (s.cursor.x, s.cursor.y - 1)
        if not over and self.waiting and 0 <= cur[1] < MAP_ROWS and cur[0] < MAP_COLS:
            c = cells[cur[1]][cur[0]]
            if c and c["ch"] == "@" and c["tile"] < n_monsters():
                self.hero = (cur[0], cur[1], c["tile"])
        if not over and self.hero:                          # a prompt holds the cursor off the map: the hero is still the cell with its tile
            at = [(x, y) for y, row in enumerate(cells) for x, c in enumerate(row) if c and c["tile"] == self.hero[2] and not c["flags"] & MG_PET]
            if len(at) == 1:
                self.hero = (at[0][0], at[0][1], self.hero[2])
        return {"cells": cells, "hero": self.hero, "message": message.replace("--More--", "").strip(),
                "status": [s.display[22].rstrip(), s.display[23].rstrip()], "text": "\n".join(_trim(text)) if over else "",
                "more": "--More--" in "\n".join(s.display), "waiting": self.waiting, "prompt": s.cursor.y == 0}


def _trim(lines):
    while lines and not lines[0].strip():
        lines = lines[1:]
    while lines and not lines[-1].strip():
        lines = lines[:-1]
    left = min(len(l) - len(l.lstrip()) for l in lines if l.strip()) if lines else 0
    return [l[left:] for l in lines]


_NAMES = None
def tile_names():
    """The tiles' names from the game's own art (win/share: monsters, objects, other, the order of the sheet)."""
    global _NAMES
    if _NAMES is None:
        _NAMES = {"monsters": [], "objects": [], "other": []}
        for k in _NAMES:
            for l in open(os.path.join(SHARE, k + ".txt"), encoding="latin-1"):
                m = re.match(r"# tile \d+ \((.*)\)", l)
                if m:
                    _NAMES[k].append(m.group(1))
    return _NAMES


def n_monsters():
    return len(tile_names()["monsters"])


def describe(tile):
    """(name, kind) of a tile; kind None: the ground."""
    n = tile_names()
    mon, obj = len(n["monsters"]), len(n["objects"])
    if tile < mon:
        return n["monsters"][tile], "monster"
    if tile < mon + obj:
        return n["objects"][tile - mon], "object"
    name = n["other"][tile - mon - obj] if tile - mon - obj < len(n["other"]) else "effect"
    return name, None if GROUND.search(name) else "place"


class Game:
    """The process behind the pty. The caller's loop reads game.fd, game.read() returns its bytes (b"" when it ended)."""

    def __init__(self, options=OPTIONS, path=GAME):
        self.options, self.path, self.pid, self.fd = options, path, None, None

    def start(self):
        if not os.access(self.path, os.X_OK):
            raise FileNotFoundError(f"{self.path}: run minihack/nethack/build.sh")
        env = dict(os.environ, TERM="xterm", LINES=str(ROWS), COLUMNS=str(COLS), NETHACKOPTIONS=self.options)
        env.pop("LD_LIBRARY_PATH", None)
        self.pid, self.fd = pty.fork()
        if self.pid == 0:
            os.execvpe(self.path, ["nethack"], env)
        fcntl.ioctl(self.fd, termios.TIOCSWINSZ, struct.pack("HHHH", ROWS, COLS, 0, 0))
        os.set_blocking(self.fd, False)

    def read(self):
        try:
            return os.read(self.fd, 65536)
        except BlockingIOError:
            return None
        except OSError:
            return b""

    def keys(self, data):
        os.write(self.fd, data)

    def forget(self):
        """The game ended for good: stopped, and its save gone, so the next start is a new hero in a new dungeon."""
        self.stop()
        name = re.search(r"name:([^,]+)", self.options)
        for f in glob.glob(os.path.join(os.path.dirname(self.path), "lib", "nethackdir", "save", "%d%s*" % (os.getuid(), name[1] if name else ""))):
            os.remove(f)

    def stop(self):
        """SIGHUP: the game saves itself, the next start restores it."""
        if self.pid:
            try:
                os.kill(self.pid, signal.SIGHUP)
            except ProcessLookupError:
                pass
            for _ in range(50):
                try:
                    if os.waitpid(self.pid, os.WNOHANG)[0]:
                        break
                except ChildProcessError:
                    break
                import time
                time.sleep(0.05)
            self.pid = None
        if self.fd is not None:
            try:
                os.close(self.fd)
            except OSError:
                pass
            self.fd = None
