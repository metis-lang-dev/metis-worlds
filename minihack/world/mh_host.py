"""mh_host.py — one MiniHack level as a catalog host (world-minihack step 1), the shape of
metis-catalog's tools/rddl_host.py and alfworld/world/alf_host.py. The small LLM
agent acts: the person's or the agent's words become the card's intents, the harness maps
them to `cmd_*` atoms, the host turns a fired command rule's event into an NLE action
(through mh_gym.py, a child under the world's venv), and the level's perception after the
step is the world's answer, read back by observe().

    make(case, package_dir) -> MhHost   (a package's mh_host.py shim passes its directory)

The package holds level.json: the level's des text (or an env id), the action names, the
seed. The gym's interpreter: $METIS_MH_PY, else the world repo's .venv/bin/python.
"""
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))

# a command atom -> the NLE action, with its argument kinds
COMMANDS = {
    "cmd_move": ("dir",),            # cmd_move(D): D in n e s w ne se sw nw
    "cmd_pickup": (),
    "cmd_eat": (),                   # the item is asked in a prompt; the world eats the first edible
    "cmd_down": (),
    "cmd_wait": (),
    "cmd_open": ("dir",),
    "cmd_kick": ("dir",),
    "cmd_search": (),
    "cmd_apply": (),
}
DIRS = {"n": "N", "e": "E", "s": "S", "w": "W", "ne": "NE", "se": "SE", "sw": "SW", "nw": "NW"}
ACTIONS = ["N", "E", "S", "W", "NE", "SE", "SW", "NW", "PICKUP", "EAT", "DOWN", "WAIT", "OPEN", "KICK", "APPLY", "SEARCH", "MORE", "ESC"]
# the perceived predicates the sync may retract (the agent's own tokens never)
PERCEIVED = {"agent_at", "floor", "wall", "door", "corridor", "stairs_down", "stairs_up", "obj", "monster", "trap",
             "unknown", "hp", "hpmax", "hunger", "turn", "holds"}


def interpreter():
    p = os.environ.get("METIS_MH_PY")
    if p:
        return p
    repo = os.path.dirname(HERE)
    own = os.path.join(repo, ".venv", "bin", "python")  # the world repo's own venv (setup.sh)
    if os.path.exists(own):
        return own
    d = repo
    for _ in range(3):  # a shared venv beside the world repos (.worlds/mh); never a sibling .venv
        d = os.path.dirname(d)
        c = os.path.join(d, ".worlds", "mh", "bin", "python")
        if os.path.exists(c):
            return c
    return sys.executable


def bindings(name):
    base, _, rest = name.partition("[")
    b = {}
    if rest:
        for kv in rest.rstrip("]").split(","):
            k, _, v = kv.partition("=")
            b[k.strip()] = v.strip()
    return base.split("-")[0], b


class GymClient:
    def __init__(self, level, max_steps, seed):
        import tempfile
        self.err = tempfile.TemporaryFile("w+")
        self.proc = subprocess.Popen([interpreter(), os.path.join(HERE, "mh_gym.py")], stdin=subprocess.PIPE,
                                     stdout=subprocess.PIPE, stderr=self.err, text=True)
        self.info = self.call("open", des=level.get("des"), env=level.get("env"), actions=level.get("actions") or ACTIONS,
                              max_steps=max_steps, seed=seed)

    def call(self, op, **kw):
        self.proc.stdin.write(json.dumps(dict(kw, op=op)) + "\n")
        self.proc.stdin.flush()
        line = self.proc.stdout.readline()
        if not line:
            self.err.seek(0)
            tail = self.err.read().strip().splitlines()[-3:]
            raise RuntimeError("the level process ended (%s): %s" % (self.proc.poll(), " | ".join(tail)))
        out = json.loads(line)
        if not out.pop("ok"):
            raise RuntimeError("level %s: %s" % (op, out["error"]))
        return out

    def close(self):
        try:
            if self.proc.poll() is None:
                self.proc.stdin.write('{"op": "close"}\n')
                self.proc.stdin.flush()
                self.proc.wait(timeout=10)
        except (OSError, ValueError, subprocess.TimeoutExpired):
            self.proc.kill()

    def __del__(self):
        if getattr(self, "proc", None) is not None:
            self.close()


class MhHost:
    """bind(reg) · tick(counts) -> do-lines | None · on_event(name, args) · observe(counts) -> {atom: n}
    · snapshot() / restore(snap) · ports() · reseed(seed). The message's events ride one beat:
    `said(KIND)` atoms handed in with the next tick and taken off at the one after."""

    PAIRS = ()

    def __init__(self, package_dir, case=None, max_steps=100):
        self.package_dir, self.case = package_dir, case
        self.level = json.load(open(os.path.join(package_dir, "level.json")))
        self.seed = int(self.level.get("seed", 1))
        self.max_steps = max_steps
        self.gym = GymClient(self.level, max_steps, self.seed)
        self.cells = self.gym.info["cells"]
        self.beat, self.due, self.script, self.last = 0, (), {}, None
        self._reset(self.seed)

    def _reset(self, seed):
        self.seed = seed
        out = self.gym.call("reset", seed=seed)
        self._take(out)
        self.actions, self.t = [], 0
        self.pending_events = list(out.get("events", []))
        self.handed = []

    def _take(self, out):
        self.atoms = set(out["atoms"])
        msg = out.get("message", "")
        # NLE keeps the last message on the line: it is an event only when it is new
        self.events = list(out.get("events", [])) if msg != getattr(self, "message", None) else []
        self.message = msg
        self.done, self.won = bool(out.get("done")), bool(out.get("won"))
        self.reward = float(out.get("reward", 0.0))

    def reseed(self, seed):
        if seed != self.seed:
            self._reset(seed)

    def reading(self):
        return {a: 1 for a in self.atoms}

    def action_of(self, name, args):
        """The fired RULE's name says the command: a rule consuming cmd_X(...) is named X or X_<why>
        (alfred's take_open / take_plain); `cmd_X` itself is accepted too (the tests)."""
        base, b = bindings(name)
        key = base if base.startswith("cmd_") else "cmd_" + base.split("_")[0]
        spec = COMMANDS.get(key)
        if spec is None:
            return None
        base = key
        if spec == ("dir",):
            d = DIRS.get(b.get("D", "").lower())
            if d is None:
                return None
            if base == "cmd_move":
                return [d]
            return [base[4:].upper(), d]                 # OPEN then the direction
        return {"cmd_pickup": ["PICKUP"], "cmd_eat": ["EAT"], "cmd_down": ["DOWN"], "cmd_wait": ["WAIT"],
                "cmd_search": ["SEARCH"], "cmd_apply": ["APPLY"]}.get(base)

    def bind(self, reg):
        pass

    def on_event(self, name, args):
        acts = self.action_of(name, args)
        if not acts or self.done:
            return
        for a in acts:
            out = self.gym.call("step", action=a)
            self._take(out)
            self.t += 1
            self.actions.append(a)
            self._log({"beat": self.beat, "t": self.t, "rule": name, "action": a, "message": self.message,
                       "events": self.events, "reward": self.reward, "done": self.done, "won": self.won})
            if self.done:
                break
        self.pending_events += self.events

    def _log(self, rec):
        p = os.environ.get("METIS_MH_LOG")
        if p:
            with open(p, "a") as f:
                f.write(json.dumps(rec) + "\n")

    def observe(self, counts):
        if self.done and not self.won:
            return {}
        return self.reading()

    def tick(self, counts):
        if self.done:
            return None
        self.beat += 1
        dos = self.sync(counts)
        for e in self.handed:                              # last beat's events are over
            dos.append("-%s 1" % e)
        self.handed = []
        for e in self.pending_events:
            dos.append("+%s 1" % e)
            self.handed.append(e)
        self.pending_events = []
        return dos

    def sync(self, counts):
        dos = []
        reading = self.reading()
        for a, n in sorted(reading.items()):
            have = counts.get(a, 0)
            if n > have:
                dos.append("+%s %d" % (a, n - have))
        for a, have in sorted(counts.items()):
            if have > 0 and a not in reading and a.split("(")[0] in PERCEIVED:
                dos.append("-%s %d" % (a, have))
        return dos

    def world(self, lines):
        raise ValueError("world lines: the level is the world; set a scenario by choosing another level or seed")

    def ports(self):
        return {"level": {"size": self.gym.info["size"], "seed": self.seed, "step": self.t, "done": self.done, "won": self.won},
                "observed": sorted(PERCEIVED), "events": sorted({k for _, k in __import__("perceive").MESSAGES}),
                "actions": self.gym.info["actions"], "commands": sorted(COMMANDS)}

    def snapshot(self):
        return {"seed": self.seed, "t": self.t, "beat": self.beat, "actions": list(self.actions),
                "pending": list(self.pending_events), "handed": list(self.handed)}

    def restore(self, snap):
        self._reset(snap["seed"])
        for a in snap["actions"]:
            out = self.gym.call("step", action=a)
            self._take(out)
            self.t += 1
            self.actions.append(a)
        self.beat, self.pending_events, self.handed = snap["beat"], list(snap["pending"]), list(snap["handed"])


def make(case=None, package_dir=None):
    return MhHost(package_dir or os.getcwd(), case)
