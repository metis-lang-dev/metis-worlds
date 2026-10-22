"""alf_host.py — one ALFWorld game as a catalog host (world-alfworld step 1): the shape of
metis-catalog's tools/rddl_host.py. The program acts: a fired action rule is a command the
host sends to the game (through alf_gym.py, a child under the world's venv); the game's
facts after the step are the world's answer, read back by observe(); the watch scores the
rules' effects against them. A command the game refuses ("Nothing happens.") changes no
fact while the rule produced its effect: a surprise, the learning signal.

    make(case, package_dir)  -> AlfHost   (a package's alf_host.py shim passes its directory)

The package holds game.json (the game's path and the handle map, written by
world/gen_instance.py). The gym's interpreter: $METIS_ALF_PY, else the world repo's
.venv/bin/python (found by walking up from this file).
"""
import json
import os
import sys

from metis.host import GymChild, find_interpreter

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from ground import STATIC  # noqa: E402

# the rule -> the command it is (the bindings are the rule's variables)
COMMANDS = {
    "choose": None,
    "go_obj": ("go", "L2", "O"),       # go to a receptacle at L2 (the one holding O, else any there)
    "go_target": ("go", "L2", "R"),    # go to R (at L2)
    "open_obj": ("open", "R"),
    "open_target": ("open", "R"),
    "take_open": ("take", "O", "R"),
    "take_plain": ("take", "O", "R"),
    "put_open": ("put", "O", "R"),
    "put_plain": ("put", "O", "R"),
    "go": ("go", "L2", "R"),           # nav_domain (alf-hierarchy): go to R at L2
    "open_closed": ("open", "R"),      # access_domain
}


def interpreter():
    """$METIS_ALF_PY, else the world repo's own venv (setup.sh), else a shared venv beside the world repos
    (.worlds/alf; never a sibling .venv), else this interpreter (metis.host.find_interpreter)."""
    repo = os.path.dirname(HERE)
    cands, d = [os.path.join(repo, ".venv", "bin", "python")], repo
    for _ in range(3):
        d = os.path.dirname(d)
        cands.append(os.path.join(d, ".worlds", "alf", "bin", "python"))
    return find_interpreter("METIS_ALF_PY", None, cands)


def _args(atom):
    i = atom.find("(")
    return [x.strip() for x in atom[i + 1:-1].split(",")] if i >= 0 else []


def bindings(name):
    """`go_obj[O=tissuebox3,L=loc22,L2=loc2]` -> ("go_obj", {"O": "tissuebox3", ...})."""
    base, _, rest = name.partition("[")
    b = {}
    if rest:
        for kv in rest.rstrip("]").split(","):
            k, _, v = kv.partition("=")
            b[k.strip()] = v.strip()
    return base.split("-")[0], b


class GymClient(GymChild):
    """world/alf_gym.py as a child: one JSON request per line, one answer (metis.host.GymChild)."""

    def __init__(self, game, max_steps=60, handles=None):
        super().__init__(os.path.join(HERE, "alf_gym.py"), interpreter(), "game", env=dict(os.environ),
                         game=game, max_steps=max_steps, handles=handles)


class AlfHost:
    """The host faces the domain agent's AgentHost and metispy's REPL read:
    bind(reg) · tick(counts) -> do-lines | None · on_event(name, args) · observe(counts) -> {atom: n}
    · snapshot() / restore(snap) · ports() · world(lines) (unsupported here: the game is the world)."""

    PAIRS = ()

    def __init__(self, package_dir, case=None, max_steps=60):
        self.package_dir, self.case = package_dir, case
        meta = json.load(open(os.path.join(package_dir, "game.json")))
        self.game = meta["game"]
        self.to_name = meta["handles"]["to_name"]
        self.gym = GymClient(self.game, max_steps=max_steps, handles=meta["handles"])
        info = self.gym.info
        self.task, self.params = info["task_type"], info["params"]
        self.static = set(info["static"])
        self.recat = {}                              # location -> [receptacles]
        for a in self.static:
            if a.startswith("recat("):
                r, l = a[6:-1].split(",")
                self.recat.setdefault(l, []).append(r)
        self.openable = {a[9:-1] for a in self.static if a.startswith("openable(")}
        # a hierarchy package (world/gen_hier.py): the commands to replay before the program starts,
        # the predicates the package declares (the reading is filtered to them), and its result
        # predicates (an atom of one in the counts ends the episode: the result is out)
        self.replay = list(meta.get("replay") or [])
        self.observed = set(meta["observe"]) if meta.get("observe") else None
        self.out = set(meta.get("out") or [])
        self.continues = bool(meta.get("continues"))          # the agent's hierarchy: a result is reported, the run goes on (the director sleeps the specialist)
        self.reported = set()
        self.things = set(meta["things"]) if meta.get("things") else None   # … and the things it declares
        self.beat, self.due, self.script, self.last = 0, (), {}, None   # the AgentHost reads these
        self._reset()

    # ── the episode ──
    def _reset(self):
        out = self.gym.call("reset")
        self._take(out)
        self.commands = []                           # (beat, rule, command, admissible, changed): the snapshot
        self.t, self.done, self.won = 0, False, False
        self.stepped = False
        for c in self.replay:                        # the prefix another package's run sent
            self._take(self.gym.call("step", command=c))
            self.t += 1

    def _take(self, out):
        self.dyn = set(out["dynamic"])
        self.admissible = list(out["admissible"])
        self.obs = out["obs"]
        self.won = bool(out.get("won"))
        self.done = bool(out.get("done")) or self.won
        self.changed = bool(out.get("changed", True))

    def reading(self):
        r = {a: 1 for a in self.dyn}
        held = any(a.startswith("holds(") for a in self.dyn)
        r["holding" if held else "handsfree"] = 1
        opened = {a[7:-1] for a in self.dyn if a.startswith("opened(")}
        for rec in self.openable:
            if rec not in opened:
                r["closed(%s)" % rec] = 1
        if self.observed is not None:
            r = {a: n for a, n in r.items() if a.split("(")[0] in self.observed}
        if self.things is not None:
            r = {a: n for a, n in r.items() if all(x in self.things for x in _args(a))}
        return r

    # ── the commands ──
    def name(self, handle):
        return self.to_name[handle]

    def command_of(self, name, args):
        base, b = bindings(name)
        spec = COMMANDS.get(base)
        if spec is None:
            return None
        kind = spec[0]
        if kind == "go":
            l2 = b[spec[1]]
            recs = self.recat.get(l2, [])
            if not recs:
                return None
            prefer = b.get(spec[2])
            r = next((x for x in recs if prefer and "inrecep(%s,%s)" % (prefer, x) in self.dyn), None) or (
                prefer if prefer in recs else recs[0])
            return "go to " + self.name(r)
        if kind == "open":
            return "open " + self.name(b[spec[1]])
        if kind == "take":
            return "take %s from %s" % (self.name(b[spec[1]]), self.name(b[spec[2]]))
        if kind == "put":
            # the text game's own verb ("put O in/on R" is ALFWorld's agent-side alias; the game lists `move O to R`)
            return "move %s to %s" % (self.name(b[spec[1]]), self.name(b[spec[2]]))
        return None

    # ── the host faces ──
    def bind(self, reg):
        pass

    def on_event(self, name, args):
        cmd = self.command_of(name, args)
        if cmd is None or self.done:
            return
        admissible, before = cmd in self.admissible, list(self.admissible)
        out = self.gym.call("step", command=cmd)
        self._take(out)
        self.t += 1
        self.stepped = True
        self.commands.append((self.beat, name, cmd, admissible, self.changed))
        rec = {"beat": self.beat, "t": self.t, "rule": name, "command": cmd, "admissible": admissible,
               "changed": self.changed, "won": self.won, "obs": self.obs[:120].replace("\n", " ")}
        if not admissible:
            rec["admissible_were"] = before      # what the game would have taken instead
        self._log(rec)

    def _log(self, rec):
        """$METIS_ALF_LOG: one JSON line per command (the experiments' record of what the game said)."""
        p = os.environ.get("METIS_ALF_LOG")
        if p:
            with open(p, "a") as f:
                f.write(json.dumps(rec) + "\n")

    def observe(self, counts):
        if self.done and not self.won:
            return {}
        return self.reading()

    def tick(self, counts):
        if self.done and not self.out:
            return None
        self.beat += 1
        self.stepped = False
        reading = self.reading()
        own = sorted(a for a, n in counts.items() if n > 0 and a not in reading and a.split("(")[0] not in DYNAMIC_PREDS)
        out = [a for a in own if a.split("(")[0] in self.out and a not in self.reported]
        tokens = [a for a in own if a not in out]
        dos = self.sync(counts)
        self._log({"beat": self.beat, "tick": True, "counts": len(counts), "sync": dos[:12], "n_sync": len(dos),
                   "tokens": tokens, "out": out})
        if self.done:                                # the game ended: the run is over
            return None
        if out and not self.continues:               # a result is out: the run is over (the driver's manual switch)
            self.done = True
            return None
        if out:                                      # continues: the result is reported once, the world keeps stepping
            self.reported |= set(out)
        return dos

    def sync(self, counts):
        """The do-lines that bring the program's dynamic facts to the game's (the policy's
        own tokens untouched)."""
        dos = []
        reading = self.reading()
        for a, n in sorted(reading.items()):
            have = counts.get(a, 0)
            if n > have:
                dos.append("+%s %d" % (a, n - have))
        for a, have in sorted(counts.items()):
            base = a.split("(")[0]
            if have > 0 and a not in reading and base in DYNAMIC_PREDS:
                dos.append("-%s %d" % (a, have))
        return dos

    def world(self, lines):
        raise ValueError("world lines: the game is the world; set a scenario by choosing another game")

    def ports(self):
        return {"game": {"path": self.game, "task": self.task, "params": self.params, "step": self.t,
                         "done": self.done, "won": self.won},
                "observed": sorted({a.split("(")[0] for a in self.dyn} | {"closed", "handsfree", "holding"}),
                "commands": [[b, n, c, adm, ch] for b, n, c, adm, ch in self.commands]}

    def snapshot(self):
        return {"t": self.t, "beat": self.beat, "commands": [[b, n, c, adm, ch] for b, n, c, adm, ch in self.commands]}

    def restore(self, snap):
        self._reset()
        for b, n, c, adm, ch in snap["commands"]:
            out = self.gym.call("step", command=c)
            self._take(out)
            self.t += 1
            self.commands.append((b, n, c, adm, self.changed))
        self.beat = snap["beat"]


# the program's dynamic predicates (the ones sync may retract): ground.py's, plus the complements
from ground import DYNAMIC as _DYN  # noqa: E402
DYNAMIC_PREDS = set(_DYN) | {"closed", "handsfree", "holding"}


def make(case=None, package_dir=None):
    return AlfHost(package_dir or os.getcwd(), case)
