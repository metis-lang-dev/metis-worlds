"""mh_director_host.py — the director's host over MiniHack's hierarchy (semantic-world step 2, world/mh_hier.py), the
same faces as alfworld's director_host: the director never acts in the world, so this host has no gym.
  world(lines)   the orchestrator's arrivals, `+seen(K) 1` / `+idle(D) 1`, handed in at the next tick
  tick(counts)   the queued arrivals, then the retraction of the director's own out atoms (reported once)
  deliver(D, goal, tokens) -> lines | None   a hierarchy domain's next activation on its live session: the world
                 in roles through the map's binding (D's declared predicates), its own tokens, the goal — less
                 what it holds (the agent takes them as one row: no reload); None outside the hierarchy
  instance(D, goal, tokens) -> bool   a reload's start (a new game): the map is the level's store, nothing to rewrite
The world it reads is the hierarchy's shared NLE process (mh_host.SHARED, keyed by the map's path)."""
import collections
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import mh_host  # noqa: E402
from semantic_world.grid import GridMap  # noqa: E402  (libs/semantic-world, installed editable)

OUT = ("wake", "sleep", "forward", "ask", "ended")
WORLD = {"agent_at", "step", "door", "monster", "next", "toward", "said", "floor", "stairs_down", "obj", "holds"}


class DirectorHost:
    PAIRS = ()

    def __init__(self, package_dir, case=None):
        self.package_dir, self.case = package_dir, case
        self.meta = json.load(open(os.path.join(package_dir, "game.json")))
        self.specs = self.meta["specs"]
        self.cmap = GridMap(self.meta["map"])
        self.queue, self.beat, self.k, self.reported = [], 0, 0, []
        self.due, self.script, self.last = (), {}, None

    def bind(self, reg):
        pass

    def world(self, lines):
        self.queue += [l.strip() for l in lines if l.strip()]

    def tick(self, counts):
        self.beat += 1
        dos, self.queue = list(self.queue), []
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

    def _reading(self, domain):
        last = (mh_host.SHARED.get(self.meta["map"]) or {}).get("last")
        if last is None:
            return {}
        self.cmap.project()                             # the binding as the robot stands now (the activation's input)
        keep = set(self.specs[domain]["dyn"])
        return {a: n for a, n in self.cmap.role_reading({a: 1 for a in last["atoms"]}).items() if a.split("(")[0] in keep}

    def deliver(self, domain, goal, tokens=()):
        sp = self.specs.get(domain)
        if sp is None:
            return None
        reading = self._reading(domain)
        held = {a: n for a, n in (tokens.items() if isinstance(tokens, dict) else ((t, 1) for t in tokens)) if a and n > 0}
        out = set(sp["out"])
        own = [a for a, n in held.items() if a not in reading and a.split("(")[0] not in WORLD and a.split("(")[0] not in out]
        want = collections.Counter(reading)
        want.update(sorted(own) + ([goal] if goal else []))
        lines = []
        for a in sorted(set(want) | set(held)):
            d = want.get(a, 0) - held.get(a, 0)
            if d:
                lines.append("%s%s %d" % ("+" if d > 0 else "-", a, abs(d)))
        return lines

    def instance(self, domain, goal, tokens=()):
        if domain not in self.specs:
            return False
        self.k += 1
        return True

    def ports(self):
        return {"director": {"beat": self.beat, "root": self.meta["root"]}, "in": ["seen(kind)", "idle(domain)"], "out": list(OUT),
                "kinds": self.meta.get("kinds", [])}

    def snapshot(self):
        return {"beat": self.beat, "k": self.k, "queue": list(self.queue)}

    def restore(self, snap):
        self.beat, self.k, self.queue = snap["beat"], snap["k"], list(snap["queue"])


def make(case=None, package_dir=None):
    return DirectorHost(package_dir or os.getcwd(), case)
