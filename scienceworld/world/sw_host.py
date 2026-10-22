"""sw_host.py — one ScienceWorld task variation as a catalog host (world-scienceworld step 1), the
shape of the other worlds' hosts: a fired command rule's event → the game's verb (through sw_gym.py,
a child under the world's venv), the perception after the step as the world's answer, the result
line as one beat of `said(KIND)` events.

    make(case, package_dir) -> SwHost   (a package's sw_host.py shim passes its directory)

The package holds task.json: the task name, the variation, the simplification. A command the game
does not take answers with its own line ("No known action matches", "can't …"): `said(unknown)` /
`said(cant)`, nothing moved — the world's refusal, as modeled (the game's `valid` list is advisory:
it spells referents one way, the game accepts several). The interpreter: $METIS_SW_PY, else the world's
.venv, else .worlds/sw walking up."""
import json
import os
import sys

from metis.host import GymChild, find_interpreter

HERE = os.path.dirname(os.path.abspath(__file__))

# a command atom -> the game's verb template, with its argument kinds (names with _ → spaces)
COMMANDS = {
    "cmd_go": ("go to {R}", ("R",)),            # cmd_go(R): a room behind a door of here
    "cmd_open": ("open {D}", ("D",)),           # cmd_open(D): a door ("door_to_workshop") or a container
    "cmd_close": ("close {D}", ("D",)),
    "cmd_take": ("pick up {O}", ("O",)),
    "cmd_drop": ("drop {O}", ("O",)),
    "cmd_focus": ("focus on {O}", ("O",)),
    "cmd_connect": ("connect {A} to {B}", ("A", "B")),
    "cmd_move": ("move {O} to {C}", ("O", "C")),
    "cmd_activate": ("activate {O}", ("O",)),
    "cmd_deactivate": ("deactivate {O}", ("O",)),
    "cmd_wait": ("wait1", ()),
    "cmd_look": ("look around", ()),
}
# the perceived predicates the sync may retract (the agent's own tokens never)
PERCEIVED = {"here", "door", "in", "state", "closed", "open", "reads", "holds", "focused", "connected"}


def interpreter():
    """The gym's interpreter: $METIS_SW_PY, else the world's own .venv (setup.sh), else .worlds/sw
    beside the checkouts, else this interpreter (metis.host.find_interpreter)."""
    repo = os.path.dirname(HERE)
    cands = [os.path.join(repo, ".venv", "bin", "python")]
    d = repo
    for _ in range(4):
        d = os.path.dirname(d)
        cands.append(os.path.join(d, ".worlds", "sw", "bin", "python"))
    return find_interpreter("METIS_SW_PY", None, cands)


def bindings(name):
    base, _, rest = name.partition("[")
    b = {}
    if rest:
        for kv in rest.rstrip("]").split(","):
            k, _, v = kv.partition("=")
            b[k.strip()] = v.strip()
    return base.split("-")[0], b


def words(n, labels=None):
    return (labels or {}).get(n) or n.replace("_", " ")


class GymClient(GymChild):
    """world/sw_gym.py as a child: one JSON request per line, one answer (metis.host.GymChild)."""

    def __init__(self, task, max_steps):
        super().__init__(os.path.join(HERE, "sw_gym.py"), interpreter(), "world", env=dict(os.environ),
                         task=task["task"], variation=task.get("variation", 0),
                         simplification=task.get("simplification", "easy"), max_steps=max_steps)


class SwHost:
    """bind(reg) · tick(counts) -> do-lines | None · on_event(name, args) · observe(counts) -> {atom: n}
    · snapshot() / restore(snap) · ports(). The result's events ride one beat."""

    PAIRS = ()

    def __init__(self, package_dir, case=None, max_steps=100):
        self.package_dir, self.case = package_dir, case
        self.task = json.load(open(os.path.join(package_dir, "task.json")))
        self.max_steps = max_steps
        self.gym = GymClient(self.task, max_steps)
        self.task_atoms = list(self.gym.info.get("task_atoms") or [])
        self.beat, self.due, self.script, self.last = 0, (), {}, None
        self._reset()

    def _reset(self):
        out = self.gym.call("reset")
        self.focused, self.connected, self.labels = None, set(), {}
        self._take(out)
        self.actions, self.t = [], 0
        self.pending_events = list(out.get("events", []))
        self.handed = []

    def _take(self, out, command=None):
        self.atoms = set(out["atoms"])
        self.message = out.get("message", "")
        self.events = list(out.get("events", []))
        self.valid = list(out.get("valid", []))
        self.labels.update(out.get("labels") or {})              # the world's spelling of what was seen ("unknown substance B")
        self.done, self.won = bool(out.get("done")), bool(out.get("won"))
        self.reward, self.score = float(out.get("reward", 0.0)), float(out.get("score", 0.0))
        # what the look does not show: the focus, the connections (from the results; a move disconnects)
        if command:
            if command.startswith("focus on ") and "said(focused)" in self.events:
                self.focused = command[9:].replace(" ", "_")
            if command.startswith("connect ") and "said(connected)" in self.events:
                a, _, b = command[8:].partition(" to ")
                self.connected.add((a.replace(" ", "_"), b.replace(" ", "_")))
            if "(disconnecting" in self.message or command.startswith("disconnect "):
                moved = self.message.split("(disconnecting ")[1].split(")")[0].replace(" ", "_") if "(disconnecting " in self.message else command[11:].replace(" ", "_")
                self.connected = {(a, b) for a, b in self.connected if not (a.startswith(moved) or b.startswith(moved))}

    def reading(self):
        r = {a: 1 for a in self.atoms}
        for a in self.task_atoms:
            r[a] = 1
        if self.focused:
            r["focused(%s)" % self.focused] = 1
        for a, b in self.connected:
            r["connected(%s,%s)" % (a, b)] = 1
        return r

    def command_of(self, name, args):
        base, b = bindings(name)
        key = base if base.startswith("cmd_") else "cmd_" + base.split("_")[0]
        spec = COMMANDS.get(key)
        if spec is None:
            return None
        tpl, keys = spec
        try:
            return tpl.format(**{k: words(b[k], self.labels) for k in keys})
        except KeyError:
            return None

    def bind(self, reg):
        pass

    def on_event(self, name, args):
        cmd = self.command_of(name, args)
        if not cmd or self.done:
            return
        out = self.gym.call("step", command=cmd)
        self._take(out, cmd)
        self.t += 1
        self.actions.append(cmd)
        self._log({"beat": self.beat, "t": self.t, "rule": name, "command": cmd, "message": self.message,
                   "events": self.events, "reward": self.reward, "score": self.score, "done": self.done, "won": self.won})
        self.pending_events += self.events

    def _log(self, rec):
        p = os.environ.get("METIS_SW_LOG")
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
        for e in self.handed:
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
        raise ValueError("world lines: the task is the world; choose another variation")

    def ports(self):
        return {"task": dict(self.task, step=self.t, score=self.score, done=self.done, won=self.won),
                "observed": sorted(PERCEIVED | {"task"}), "labels": dict(self.labels), "events": sorted({k for _, k in __import__("perceive").MESSAGES} | {"other"}),
                "commands": sorted(COMMANDS)}

    def snapshot(self):
        return {"t": self.t, "beat": self.beat, "actions": list(self.actions), "pending": list(self.pending_events), "handed": list(self.handed)}

    def restore(self, snap):
        self._reset()
        for c in snap["actions"]:
            out = self.gym.call("step", command=c)
            self._take(out, c)
            self.t += 1
            self.actions.append(c)
        self.beat, self.pending_events, self.handed = snap["beat"], list(snap["pending"]), list(snap["handed"])


def make(case=None, package_dir=None):
    return SwHost(package_dir or os.getcwd(), case)
