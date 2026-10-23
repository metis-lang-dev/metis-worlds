"""director_host.py — the director's host in the agent (alf-hierarchy step 3): the director never
acts in the world, so this host has no gym. Its faces:
  world(lines)   the orchestrator's arrivals, `+seen(K) 1` / `+idle(D) 1`, handed in at the next tick
  tick(counts)   the queued arrivals, then the retraction of the director's own out atoms present
                 in counts (wake/sleep/forward/ask/ended): reported once, never piled up
  observe        nothing: the director reads no world
  instance(D, goal, tokens) -> bool   D's installed package rewritten for GOAL from the world as it is
                 now (the shared commands log replayed on the flat package's mirror; `tokens` = D's own
                 counts carried between activations); the agent then reloads D
  deliver(D, goal, tokens) -> lines | None   for the planner: the do-lines that bring its live
                 session to what that new instance would start at (the agent takes them as one row,
                 no reload); None for a specialist (its instance is narrowed to its goal's things)
The package's game.json names the game, the flat package, the root and the commands log."""
import collections
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import gen_hier  # noqa: E402
from alf_host import DYNAMIC_PREDS, AlfHost  # noqa: E402

OUT = tuple(gen_hier.DIRECTOR_OUT)


def own_tokens(domain, tokens, reading):
    """The atoms D carries into its next activation: those it holds (a count > 0) that are neither
    the world's (the reading, the dynamic predicates: the new instance reads them afresh) nor its
    results (put out, the director's now) — the driver's tick tokens (alf_host.tick)."""
    held = tokens.items() if isinstance(tokens, dict) else ((t, 1) for t in tokens)
    out = set(gen_hier.SPECS[domain]["out"])
    return sorted(a for a, n in held if a and n > 0 and a not in reading
                  and a.split("(")[0] not in DYNAMIC_PREDS and a.split("(")[0] not in out)


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
        mirror = AlfHost(flat, commands_log=self.meta["commands_log"])   # the shared world as it is now (one process per log: alf_host.shared_client)
        try:
            info = dict(json.load(open(os.path.join(flat, "game.json"))), static=sorted(mirror.static), task_type=mirror.task, params=mirror.params)
            reading = mirror.reading()
        finally:
            mirror.gym.close()
        self.k += 1
        inits = own_tokens(domain, tokens, reading) + ([goal] if goal else [])
        gen_hier.generate(self.meta["game_dir"], os.path.join(self.meta["root"], "domains", "hier"), domain, self.k, info, reading, inits,
                          self._log_commands(), intents=(domain == "task"), continues=True, fixed=True, commands_log=self.meta["commands_log"])
        return True

    def deliver(self, domain, goal, tokens=()):
        """The planner's next activation as do-lines on its live session (alf-demo 3b timing: the
        task's six reloads were 0.2 s each of a 4 s turn): the counts a new instance's #init would give
        it — the world's facts it sees, its own tokens, the goal, one each, as instance() writes them —
        less the counts it holds. Only a planner (its types are the game's, the same in every
        instance: a person's task sees every pickupable); None for any other domain, or when its
        installed instance cannot be read (the agent re-instances and reloads it then)."""
        sp = gen_hier.SPECS.get(domain)
        if sp is None or "takes" not in sp:
            return None
        try:
            text = open(os.path.join(self.meta["root"], "domains", "hier", domain, domain + ".llp")).read()
        except OSError:
            return None
        things = set()
        for kind in sp["types"]:
            m = re.search(r"^type %s \{([^}]*)\}\." % kind, text, re.M)
            if m is None:
                return None
            things |= set(m.group(1).split())
        mirror = AlfHost(self.meta["flat"], commands_log=self.meta["commands_log"])
        try:
            reading = mirror.reading()
        finally:
            mirror.gym.close()
        held = {a: n for a, n in (tokens.items() if isinstance(tokens, dict) else ((t, 1) for t in tokens)) if a and n > 0}
        want = collections.Counter(a for a in sorted(reading) if a.split("(")[0] in sp["dyn"]
                                   and all(x in things for x in gen_hier.args_of(a)))
        want.update(own_tokens(domain, held, reading) + ([goal] if goal else []))
        lines = []
        for a in sorted(set(want) | set(held)):
            d = want.get(a, 0) - held.get(a, 0)
            if d:
                lines.append("%s%s %d" % ("+" if d > 0 else "-", a, abs(d)))
        return lines


def make(case=None, package_dir=None):
    return DirectorHost(package_dir or os.getcwd(), case)
