"""nh_host.py — the real game under the hierarchy's rules: MhHost with nh_gym.py as its world, and the faces the page and
the person use. The level is unknown until seen (view mode), a new dungeon level or game starts the map again, and the
game is never replayed: it is one game, the person's and the agent's, until the person asks for a new one (new_episode).

Surprises (level.json `surprises`, one JSON line each; surprise() below says what counts): a real game brings what no rule
predicts every turn, and most of it is the world's input, not a surprise. What is one is a command of the rules' own that
did not do what it says, or a message the perception has no word for. Each is written down for the loop and shown in the
journal, and the game goes on: the watch's stop (an open record, observe-only until a consult closes it) would halt the agent at
every monster in a doorway, so observe() keeps it closed.
"""
import json
import os
import re
import time

from metis.host import GymChild
from semantic_world.grid import GridMap

from mh_host import HERE, SHARED, MhHost, interpreter

EVENTS = ["blocked", "see_here", "door_here", "door_closed", "door_opened", "door_locked", "door_stuck", "whamm", "killed", "hit", "hurt", "fell_pit",
          "trap_door", "ate", "picked", "nothing_here", "cant", "hunger", "died", "welcome", "stopped", "nevermind", "prompt", "asked", "other"]
STALL_SECONDS = 20         # an errand with no turn taken and the hero in place this long has stalled: the task stops and asks
MOVES = {"N": (0, -1), "S": (0, 1), "E": (1, 0), "W": (-1, 0), "NE": (1, -1), "NW": (-1, -1), "SE": (1, 1), "SW": (-1, 1)}


def sensed(atoms, out=None):
    """What a command is checked on: the hero's cell, the turn, the dungeon level."""
    at = next((a[9:-1] for a in atoms if a.startswith("agent_at(")), None)
    cell = tuple(int(n) for n in re.match(r"c(\d+)_(\d+)", at).groups()) if at else None
    turn = next((int(a[5:-1]) for a in atoms if a.startswith("turn(")), None)
    return {"at": cell, "turn": turn, "dlvl": (out or {}).get("dlvl")}


def surprise(rule, acts, was, now, events):
    """What the rule's command said it would do and did not: (what it expected, what came), or None when it did it."""
    said = lambda *kinds: any("said(%s)" % k in events for k in kinds)
    act = acts[0]
    if act in MOVES:
        if rule.startswith(("move_fight", "move_strike")):        # a blow: the hero stays, the game says how it went
            return None if said("hit", "killed") else ("a blow at the beast %s" % act, "no blow struck")
        if was["at"] is None:
            return None
        want = (was["at"][0] + MOVES[act][0], was["at"][1] + MOVES[act][1])
        return None if now["at"] == want and now["dlvl"] == was["dlvl"] else ("the hero at %d,%d" % want, "the hero at %s on level %s" % (now["at"], now["dlvl"]))
    if act == "OPEN":
        return None if said("door_opened", "door_locked", "door_stuck") else ("the door answers", "no word of the door")
    if act == "PICKUP":
        return None if said("picked", "nothing_here") else ("something taken, or nothing here", "neither")
    if act == "DOWN":
        return None if was["dlvl"] is not None and now["dlvl"] == was["dlvl"] + 1 else ("the next level down", "level %s" % now["dlvl"])
    return None if now["turn"] != was["turn"] else ("a turn taken", "no turn")


class NhMap(GridMap):
    """Stairs seen from afar (down a lit room, through a doorway) with no known way to them are no reason to stop looking:
    the library's route has no way and no frontier then, so it is asked again as if they were unseen."""
    exploring = False

    def load(self):
        d = super().load()
        return dict(d, task=dict(d["task"], goal="unseen")) if self.exploring else d

    def route(self):
        r = super().route()
        if r or self.exploring:
            return r
        self.exploring = True
        try:
            return super().route()
        finally:
            self.exploring = False


class NhGym(GymChild):
    def __init__(self, level):
        super().__init__(os.path.join(HERE, "nh_gym.py"), interpreter(), "game", open_args={"map_doc": level.get("map_doc"), "card": level.get("card")})


class NhHost(MhHost):
    def new_map(self, path):
        return NhMap(path)

    def client(self):
        return NhGym(self.level)

    def _take(self, out, fresh=True):
        self.game_no = out.get("game")
        if out.get("done"):                             # the game ended: nothing is drawn any more, the map stays as it was last seen
            out = dict(out, atoms=sorted(getattr(self, "atoms", ())), dlvl=None)
        if fresh and getattr(self, "cmap", None) is not None and self.key in SHARED:
            sh, at = SHARED[self.key], (out.get("dlvl"), out.get("game"))
            if at[0] is not None:
                if sh.get("at") not in (None, at):       # another level or another game: its map is its own
                    self.start_map()
                sh["at"] = at
        super()._take(out, fresh)
        self.over, self.done = self.done, False     # the game's end is no end of the session: a new game goes on in it

    def start_map(self):
        from semantic_world.grid import GridMap
        k = self.cmap.load()["k"]
        GridMap.build(self.level["map"], self.level["size"], view=True, k=k)

    def on_event(self, name, args):
        acts = self.action_of(name, args)
        sh = SHARED.get(self.key) or {}
        was = sensed(self.atoms, sh.get("last"))
        super().on_event(name, args)
        if not acts or getattr(self, "over", False):
            return
        last = sh.get("last") or {}
        missed = surprise(name, acts, was, sensed(self.atoms, last), self.events)
        if missed:
            self.note("missed", name, acts, last, expected=missed[0], came=missed[1])
        if "said(other)" in self.events:
            self.note("unread", name, acts, last)

    def note(self, kind, rule, acts, out, **more):
        """One surprise: its line for the loop, its frame for the page (the task's host sends the frames)."""
        rec = {"kind": kind, "domain": self.spec, "rule": rule, "did": acts, "message": out.get("message", ""), "events": list(self.events), "game": out.get("game"),
               "dlvl": out.get("dlvl"), **sensed(self.atoms, out), **more, "ts": time.strftime("%Y-%m-%dT%H:%M:%S%z")}
        path = self.level.get("surprises")
        if path:
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "a") as f:
                f.write(json.dumps(rec) + "\n")
        SHARED[self.key].setdefault("surprises", []).append(rec)

    def new_episode(self):
        """The person's new game: the first of the hierarchy's hosts asks for it, the others find it done (its game's number moved)."""
        last = SHARED[self.key]["last"]
        if self.game_no == last.get("game"):
            self._take(self.gym.call("new_game"))
        else:
            self._take(last, fresh=False)
        self.fired, self.pending_events, self.said_lost, self.stall_sign = [], [], False, None

    def held(self):
        """Seconds since a turn was taken or the hero moved."""
        last = SHARED[self.key].get("last") or {}
        s, now = sensed(last.get("atoms", ()), last), time.monotonic()
        sign = (s["at"], s["turn"], s["dlvl"])
        if getattr(self, "stall_sign", None) != sign:
            self.stall_sign, self.stall_at = sign, now
        return now - self.stall_at

    def pending(self):
        """The tick's wake rule: the task sleeps through its errand, so the clock on it is read here too: held for STALL_SECONDS
        wakes it (stalled)."""
        out = super().pending()
        return out or (self.spec == "task" and self.held() > STALL_SECONDS)

    def stalled(self, counts, dos):
        """An errand held that long: no rule is moving it (a stall of the rules', or nowhere left to go). The task's own stop then:
        refused(its goal), its rule stuck_on, the director's question. With no errand the clock only starts again."""
        if self.held() <= STALL_SECONDS:
            return
        self.stall_at = time.monotonic()
        goal = next((a[5:-1] for a, n in counts.items() if n > 0 and a.startswith("want(")), None)
        if goal:
            dos.append("+refused(%s) 1" % goal)
            self.stall_said = True

    def tick(self, counts):
        """A release left in a sleeping specialist's session after the director already took the way back (it answered the
        result, not the release) would be read when the specialist next wakes, as a late release of its NEW grant: the
        director gives the way to a sleeping nav and neither moves. Without a grant there is nothing to release."""
        dos = super().tick(counts)
        if dos is not None and self.spec in ("nav", "act"):
            rel, grant = "tick__release(%s,motion)" % self.spec, "tick__grant(%s,motion)" % self.spec
            if counts.get(rel, 0) > 0 and counts.get(grant, 0) <= 0:
                dos.append("-%s %d" % (rel, counts[rel]))
        if dos is not None and self.spec == "task":
            self.stalled(counts, dos)
        return dos

    def world(self, lines):
        """The person's keys, on the wire as world lines `key:<keys>`: the game takes them as typed."""
        for line in lines:
            if not line.startswith("key:"):
                raise ValueError("the real game takes keys (key:<keys>), not %r" % line)
            out = self.gym.call("keys", keys=line[4:])
            self.done = False
            self._take(out)
            self.pending_events += self.events

    def frames(self):
        if self.spec != "task":
            return []
        out = self.gym.call("frames")["frames"]
        lost = self.cmap.load()["agent"]["at"] and not self.cmap.route()
        if lost and not getattr(self, "said_lost", False):      # no stairs seen and nowhere new to go: said once, not waited on in silence
            out.append({"ev": "world/message", "text": "I see no way on from here: a hidden door, perhaps. Say \"search here\", or show me on the keyboard."})
        self.said_lost = lost
        if getattr(self, "stall_said", False):
            self.stall_said = False
            out.append({"ev": "world/message", "text": "I have stopped: for %d seconds no turn has passed and nothing moved me." % STALL_SECONDS})
        for rec in SHARED[self.key].pop("surprises", []):
            out.append({"ev": "world/surprise", "text": "%s: %s" % (rec["rule"], ("expected %s, came %s" % (rec["expected"], rec["came"])) if rec["kind"] == "missed" else "no word for \"%s\"" % rec["message"])})
        over = bool((SHARED[self.key].get("last") or {}).get("done"))         # the task sleeps through an errand: the shared world's latest
        if over and not getattr(self, "said_over", False):
            out.append({"ev": "world/status", "state": "over", "text": "The game has ended.", "options": [{"label": "new game", "ev": "new_game"}]})
        elif getattr(self, "said_over", False) and not over:      # a key started another: the page takes its map again
            out.append({"ev": "world/status", "state": "waiting", "text": "A new game. Tell me a task."})
        self.said_over = over
        return out

    def observe(self, counts):
        """The watch's reading: what the session holds, so it never opens a record that would stop the game (surprise(),
        at the top); the world's reading still comes in, at the tick's sync."""
        return dict(counts)

    def reseed(self, seed):
        pass

    def restore(self, snap):
        self.beat, self.pending_events, self.handed = snap["beat"], list(snap["pending"]), list(snap["handed"])

    def ports(self):
        return {"level": {"size": self.gym.info["size"], "step": self.t, "done": self.done, "won": self.won}, "observed": [], "events": EVENTS,
                "actions": self.gym.info["actions"], "commands": []}


def make(case=None, package_dir=None):
    return NhHost(package_dir or os.getcwd(), case)
