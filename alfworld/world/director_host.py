"""director_host.py — the director's host in the agent (alf-hierarchy step 3): the director never
acts in the world, so this host has no gym. Its faces:
  world(lines)   the orchestrator's arrivals, `+seen(K) 1` / `+idle(D) 1`, handed in at the next tick
  tick(counts)   the queued arrivals, then the retraction of the director's own out atoms present
                 in counts (wake/sleep/forward/ask/ended): reported once, never piled up
  observe        nothing: the director reads no world
  instance(D, goal, tokens) -> bool   D's start for a reload (a new game, a reset): the map re-read from
                 the world as it is now (the shared commands log on the flat package's mirror) and
                 re-projected; the program, the committed instance over the roles, is never rewritten
  deliver(D, goal, tokens) -> lines | None   for every hierarchy domain: the do-lines that bring its
                 live session to its next activation — the world in roles through the map's binding, its
                 own tokens, the goal (the agent takes them as one row, no reload; semantic-map s-d4270bed)
The package's game.json names the game, the flat package, the root and the commands log."""
import collections
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import gen_hier  # noqa: E402
from alf_host import DYNAMIC_PREDS, PLACE_PREDS, AlfHost  # noqa: E402

OUT = tuple(gen_hier.DIRECTOR_OUT)


def own_tokens(domain, tokens, reading):
    """The atoms D carries into its next activation: those it holds (a count > 0) that are neither
    the world's (the reading, the dynamic predicates: the new instance reads them afresh) nor its
    results (put out, the director's now) — the driver's tick tokens (alf_host.tick)."""
    held = tokens.items() if isinstance(tokens, dict) else ((t, 1) for t in tokens)
    out = set(gen_hier.SPECS[domain]["out"])
    return sorted(a for a, n in held if a and n > 0 and a not in reading
                  and a.split("(")[0] not in DYNAMIC_PREDS | PLACE_PREDS and a.split("(")[0] not in out)


class DirectorHost:
    PAIRS = ()

    def __init__(self, package_dir, case=None):
        self.package_dir, self.case = package_dir, case
        self.meta = json.load(open(os.path.join(package_dir, "game.json")))
        self.queue, self.beat, self.k = [], 0, 0
        self.reported = []
        self.due, self.script, self.last = (), {}, None

    # ── the faces ──
    def bind(self, reg):
        pass

    def world(self, lines):
        self.queue += [l.strip() for l in lines if l.strip()]

    def tick(self, counts):
        self.beat += 1
        dos = list(self.queue)
        self.queue = []
        outs = sorted(a for a, n in counts.items() if n > 0 and a.split("(")[0] in OUT)
        for a in outs:
            dos.append("-%s %d" % (a, counts[a]))
        if outs:
            self.reported.append({"beat": self.beat, "out": outs})
        return dos

    def on_event(self, name, args):
        pass

    def observe(self, counts):
        return {}

    def sync(self, counts):
        return []

    def ports(self):
        return {"director": {"beat": self.beat, "root": self.meta["root"], "game": self.meta["game_dir"]},
                "in": ["seen(kind)", "idle(domain)"], "out": list(OUT), "kinds": self.meta.get("kinds", [])}

    def snapshot(self):
        return {"beat": self.beat, "k": self.k, "queue": list(self.queue)}

    def restore(self, snap):
        self.beat, self.k, self.queue = snap["beat"], snap["k"], list(snap["queue"])

    # ── re-instancing ──
    def _log_commands(self):
        p = self.meta["commands_log"]
        if not os.path.exists(p):
            return []
        return [json.loads(l)["command"] for l in open(p) if l.strip()]

    def _map(self):
        from semantic_map import SemanticMap
        from semantic_world.world import open_map
        return open_map(self.meta["map"], SemanticMap)

    # ── the rooms (rooms s-b51a2e80): one agent, the room is data ──
    def holding(self):
        """What the robot holds, by the map: a thing of this room's game does not exist in the next's. None: empty hands."""
        return self._map().load()["agent"].get("holding")

    def enter_room(self, room):
        """ROOM (a games.json id) installed over the tree, its own map and commands log, its world opened and its map the
        active one; the agent reloads the domains next. Refused (None) for a package that is not one of a World's rooms."""
        if not self.meta["map"].endswith(".world.json"):
            return None
        # in the world's own interpreter: reading a game needs what the agent's venv does not have (textworld)
        cmd = [os.environ.get("METIS_ALF_PY") or sys.executable, os.path.join(os.path.dirname(HERE), "experiments", "demo.py"),
               "room", room, self.meta["root"]] + ["--" + f for f in ("view", "tree", "room") if self.meta.get(f)]
        r = subprocess.run(cmd, capture_output=True, text=True, env=dict(os.environ))
        if r.returncode:
            raise RuntimeError(((r.stderr or r.stdout).strip().splitlines() or ["the room's install failed"])[-1])
        self.meta = json.load(open(os.path.join(self.package_dir, "game.json")))
        return room

    def instance(self, domain, goal, tokens=()):
        """DOMAIN's next start when the agent reloads it (a new game, a reset: the hierarchy at its start):
        the program is the committed instance over the roles and is never rewritten — the map is
        re-read from the world as it is now (the shared log on the flat package's mirror) and re-projected
        for the game's own task; True: the agent reloads D, whose host brings the world in on its first tick."""
        if domain not in gen_hier.SPECS:
            return False
        smap = self._map()
        mirror = AlfHost(self.meta["flat"], commands_log=self.meta["commands_log"])   # the shared world as it is now (one process per log: alf_host.shared_client)
        try:
            smap.observe(mirror.dyn)
            info = dict(json.load(open(os.path.join(self.meta["flat"], "game.json"))), static=sorted(mirror.static), task_type=mirror.task, params=mirror.params)
        finally:
            mirror.gym.close()
        if goal is None and not self.meta.get("room"):        # a room has no task of its own: the binding stays the person's
            smap.project(*gen_hier.args_of(gen_hier.seed(info)[0]))
        self.k += 1
        return True

    def deliver(self, domain, goal, tokens=()):
        """DOMAIN's next activation as do-lines on its live session, no reload (alf-demo 3b timing for the
        planner; semantic-map step 2 for every specialist: compiled once over the roles, each takes its
        goal this way): the counts it would start at — the world's facts it sees said in roles through the
        map's binding, its own tokens, the goal, one each — less the counts it holds. None for a domain that
        is not the hierarchy's."""
        sp = gen_hier.SPECS.get(domain)
        if sp is None:
            return None
        smap = self._map()
        mirror = AlfHost(self.meta["flat"], commands_log=self.meta["commands_log"])
        try:
            smap.observe(mirror.dyn)
            reading = smap.role_reading(mirror.reading())
        finally:
            mirror.gym.close()
        held = {a: n for a, n in (tokens.items() if isinstance(tokens, dict) else ((t, 1) for t in tokens)) if a and n > 0}
        want = collections.Counter(a for a in sorted(reading) if a.split("(")[0] in sp["dyn"])
        want.update(own_tokens(domain, held, reading) + ([goal] if goal else []))
        lines = []
        for a in sorted(set(want) | set(held)):
            d = want.get(a, 0) - held.get(a, 0)
            if d:
                lines.append("%s%s %d" % ("+" if d > 0 else "-", a, abs(d)))
        return lines


def make(case=None, package_dir=None):
    return DirectorHost(package_dir or os.getcwd(), case)
