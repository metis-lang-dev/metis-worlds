"""director_host.py — the director's host in the agent (alf-hierarchy step 3): the director never
acts in the world, so this host has no gym. Its faces:
  world(lines)   the orchestrator's arrivals, `+seen(K) 1` / `+idle(D) 1`, handed in at the next tick
  tick(counts)   the queued arrivals, then the retraction of the director's own out atoms present
                 in counts (wake/sleep/forward/ask/ended): reported once, never piled up
  observe        nothing: the director reads no world
  instance(D, goal, tokens) -> bool   D's installed package rewritten for GOAL from the world as it is
                 now (the shared commands log replayed on the flat package's mirror; `tokens` = D's own
                 counts carried between activations); the agent then reloads D
The package's game.json names the game, the flat package, the root and the commands log."""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import gen_hier  # noqa: E402
from alf_host import AlfHost  # noqa: E402

OUT = tuple(gen_hier.DIRECTOR_OUT)


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

    def instance(self, domain, goal, tokens=()):
        """Write DOMAIN's installed package for GOAL (an atom) over the world as it is now; True when written."""
        if domain not in gen_hier.SPECS:
            return False
        flat = self.meta["flat"]
        mirror = AlfHost(flat)                       # replays the shared log: the world as it is now
        try:
            info = dict(json.load(open(os.path.join(flat, "game.json"))), static=sorted(mirror.static), task_type=mirror.task, params=mirror.params)
            reading = mirror.reading()
        finally:
            mirror.gym.close()
        self.k += 1
        inits = [t for t in tokens if t] + ([goal] if goal else [])
        gen_hier.generate(self.meta["game_dir"], os.path.join(self.meta["root"], "domains", "hier"), domain, self.k, info, reading, inits,
                          self._log_commands(), intents=(domain == "task"), continues=True, fixed=True, commands_log=self.meta["commands_log"])
        return True


def make(case=None, package_dir=None):
    return DirectorHost(package_dir or os.getcwd(), case)
