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
import time

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
    """world/alf_gym.py as a child: one JSON request per line, one answer (metis.host.GymChild).
    `history` is the commands stepped since the last reset and `last` the last answer, so a host
    opened on a world another host already brought to the log's state takes it without a replay.
    A `shared` client (one per game and commands log, _SHARED) lives for the process: close() is a
    no-op on it — the agent's hierarchy opens a host per activation (alf-demo step 3b: a spawn, a
    reset and a replay cost 3.6 s, twice per director step, 90 s of a 93 s task)."""

    def __init__(self, game, max_steps=60, handles=None, room=False):
        self.history, self.last, self.shared = [], None, False
        super().__init__(os.path.join(HERE, "alf_gym.py"), interpreter(), "game", env=dict(os.environ),
                         game=game, max_steps=max_steps, handles=handles, room=bool(room))

    def call(self, op, **kw):
        out = super().call(op, **kw)
        if op == "reset":
            self.history, self.last = [], out
        elif op == "step":
            self.history.append(kw.get("command"))
            self.last = out
        return out

    def close(self):
        if self.shared:
            return
        super().close()


_SHARED = {}          # (game, commands_log) -> the GymClient every host on that log shares


def shared_client(game, commands_log, max_steps, handles, room=False):
    key = (game, commands_log)                    # a log is one install's: a room's or a game's, never both
    c = _SHARED.get(key)
    if c is None or c.proc.poll() is not None:
        c = _SHARED[key] = GymClient(game, max_steps=max_steps, handles=handles, room=room)
        c.shared = True
    return c


class AlfHost:
    """The host faces the domain agent's AgentHost and metispy's REPL read:
    bind(reg) · tick(counts) -> do-lines | None · on_event(name, args) · observe(counts) -> {atom: n}
    · snapshot() / restore(snap) · ports() · world(lines) (unsupported here: the game is the world)."""

    PAIRS = ()

    def __init__(self, package_dir, case=None, max_steps=60, commands_log=None):
        self.package_dir, self.case = package_dir, case
        meta = json.load(open(os.path.join(package_dir, "game.json")))
        self.game = meta["game"]
        self.to_name = meta["handles"]["to_name"]
        self.commands_log = commands_log or meta.get("commands_log")   # the agent's hierarchy: the shared world state (every host's commands, replayed at reset)
        # a room (alf-tasks s-e9cc8fae step 1): the game carries the room's state only — its episode's goal never
        # ends the session (alf_gym's room: the env keeps stepping), `won` is the hierarchy's own; episode_won reports it
        self.room = bool(meta.get("room"))
        self.episode_won = False
        if self.commands_log:                                           # … and every host on that log shares one world process
            self.gym = shared_client(self.game, self.commands_log, max_steps, meta["handles"], room=self.room)
        else:
            self.gym = GymClient(self.game, max_steps=max_steps, handles=meta["handles"], room=self.room)
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
        self.pending_frames = []                               # the world page's frames (alf-demo): frames() hands them over
        self.verbs = bool(meta.get("verbs"))                   # the loop's instances: a rule named verb_why is a command (opt-in: a hand domain's bookkeeping rule may start with a verb — go_for, open_dest)
        # a hierarchy package over the role vocabulary (semantic-map s-d4270bed): the program speaks roles,
        # this host the room — it reads the world through the map's binding and says its commands, its
        # lines and its goals through it back in the room's things
        from semantic_map import SemanticMap
        self.smap = SemanticMap(meta["map"]) if meta.get("map") else None
        # view mode (step 3): the map re-projects while the robot looks; a specialist reads the binding it
        # was woken with until its next activation (a role in its goal keeps its place: no surprise
        # mid-goal), the planner the map's own (the next place to look is its)
        self.spec, self.frozen = meta.get("spec"), None
        self.beat, self.due, self.script, self.last = 0, (), {}, None   # the AgentHost reads these
        self._level_hook()
        self._reset()
        self._freeze()
        self.card_changed()                          # the card as loaded: the map's things now

    # ── the episode ──
    def _reset(self):
        want = self._replay()                        # the prefix another package's run sent
        self.commands = []                           # (beat, rule, command, admissible, changed): the snapshot
        self.stepped = False
        if self.gym.shared and self.gym.last is not None and self.gym.history == want:
            self._take(self.gym.last)                # the shared world already stands at the log's end: no replay
            self.t = len(want)
            return
        out = self.gym.call("reset")
        self._take(out)
        self.t, self.done, self.won = 0, False, False
        for c in want:
            self._take(self.gym.call("step", command=c))
            self.t += 1

    def intent_atom(self, atom):
        """The mapper's atom (the room's things: the card names them) in the program's roles: a fetch
        re-projects the map for its goal (metis-agent's AgentHost.submit asks); the atom itself without a map."""
        name = atom.split("(")[0]
        if self.spec == "task":                          # a task begins: its card opens (alf-tasks step 3)
            self._task_begin(atom)
        if name == "notask":                             # ALFWorld's vocabulary, not the room's things: no projection
            return atom
        if name == "fetch" and self.smap is not None:     # what the room cannot do, said before anything moves (alf-tasks step 2)
            said = self.cannot_fetch(*[a.strip() for a in atom[6:-1].split(",")])
            if said == "unfit":                           # the goal's own roles (the projection binds them), its line in the room's names
                return "unfit(%s)" % self.smap.intent_atom(atom)[6:-1]
            if said:
                return said
        return self.smap.intent_atom(atom) if self.smap is not None else atom

    def cannot_fetch(self, obj, rec):
        """A fetch the room cannot do, as the task's vocabulary atom, or None: a kind it does not have (the card offers
        ALFWorld's kinds it lacks: a word with no number, not the map's) → nothere(K); a thing the world never puts
        there (ALFWorld's cancontain over the two types) → "unfit" (intent_atom says it over the fetch's roles). View
        mode: a kind not seen yet is searched for."""
        import re
        d = self.smap.load()
        for a, known in ((obj, d["things"]), (rec, d["places"])):
            if a and not re.search(r"\d$", a) and a not in self.smap.roles() and a not in known \
                    and not (d.get("view") and known is d["things"]):
                return "nothere(%s)" % a
        types = {h: t for x in self.static if x.startswith(("otype(", "rtype(")) for h, t in [x[6:-1].split(",")]}
        ot, rt = types.get(obj), types.get(rec)
        if ot and rt and any(x.startswith("cancontain(") for x in self.static) and "cancontain(%s,%s)" % (rt, ot) not in self.static:
            return "unfit"
        return None

    def refresh(self):
        """This host's view of the world taken from the shared process as it stands now (another host on
        the log stepped it): no reset, no replay. A planner kept live between its activations (the
        director host's deliver, the agent's take) reads the world its specialists changed; a host of
        its own process has nothing to refresh."""
        if getattr(self.gym, "shared", False) and self.gym.last is not None:
            self._take(self.gym.last)
            self.t = len(self.gym.history)
        self._freeze()
        self.reported = set()                    # a delivered activation reports its result again (reached(p1) in a second task)

    def card_changed(self):
        """The planner's card in view mode (semantic-map step 3): True once after the map's things grew —
        a thing seen for the first time — with the card rewritten from the map (intent.yaml and its
        generated grammar and prompts); the agent re-reads it (DomainAgent.refresh_card), no reload.
        False for any other host, and in text mode (the map knows every thing from the start)."""
        if self.smap is None or self.spec != "task" or not self.smap.load().get("view"):
            return False
        d = self.smap.load()
        key = sorted(o for o, t in d["things"].items() if t.get("pickupable"))
        if key == getattr(self, "_card_key", None):
            return False
        first = not hasattr(self, "_card_key")
        self._card_key = key
        if first:                                    # at load: the card the agent read
            return False
        import gen_hier
        gen_hier.write_card(self.package_dir, self.spec, self.smap)
        return True

    def _freeze(self):
        if self.smap is not None and self.smap.load().get("view") and self.spec not in (None, "task"):
            self.frozen = self.smap.binding()

    def new_episode(self):
        """The same game from its start (alf-demo step 3b, F7: a won game accepts commands that change
        nothing): the shared commands log truncated, the reported results and the pending frames
        dropped, the episode reset. Another game = gen_hier.install() on its directory."""
        if self.commands_log:
            open(self.commands_log, "w").close()
        self.reported, self.pending_frames = set(), []
        self._reset()
        self._freeze()

    def _replay(self):
        if self.commands_log and os.path.exists(self.commands_log):
            return [json.loads(l)["command"] for l in open(self.commands_log) if l.strip()]
        return self.replay

    def _take(self, out):
        self.dyn = set(out["dynamic"])
        if self.smap is not None:
            self.smap.observe(self.dyn)              # the map follows what the robot sees (another host's step too)
        self.admissible = list(out["admissible"])
        self.obs = out["obs"]
        self.won = bool(out.get("won"))
        if self.room:                                # the episode's goal is reported, never the session's end
            self.episode_won, self.won = self.won, False
        self.done = bool(out.get("done")) or self.won
        if self.won and self.continues:              # the agent's hierarchy: the game won is not the run's end — the planner
            self.done = False                        # beats on to put out its own (done), the director ends the run
        self.changed = bool(out.get("changed", True))

    # ── the level port, live (spec16 s-b12d90f2 step 4; metis-lang spec/16 §4) ──
    def _level_hook(self):
        """The task's manifest names levels (gen_hier.TASK_INSTRUMENT): the one-tick instrument over its world model,
        compiled once (metispy's metis.kernel.evaluate.LevelHook); none otherwise, or on a metispy without it."""
        self.levels, self.level_atoms, self.level_preds = None, {}, set()
        man_p = os.path.join(self.package_dir, "domain.yaml")
        if self.spec != "task" or self.smap is None or not os.path.exists(man_p):
            return
        import yaml
        man = yaml.safe_load(open(man_p)) or {}
        if not man.get("levels"):
            return
        try:
            from metis.kernel.evaluate import LevelHook
        except ImportError:
            return
        self.levels = LevelHook(man, self.package_dir)
        self.level_preds = set(man["levels"])

    def instrument_ports(self):
        """The ports the instrument reads, from the map: look (the task's choice weight) and where (the truth's
        distribution) bound to the same numbers, for every object role and place role. A distribution the instrument
        checks exactly: the map's belief normalized over the bound places, floored to nine decimals so its sum is
        at most 1 (a lone belief: the rest is the world where the target is bound to no place), uniform over the
        bound places for a thing the map has no belief of."""
        from fractions import Fraction
        d = self.smap.load()
        b, places = d["binding"], self.smap.place_roles(d["k"])
        bound = [r for r in places if b.get(r)]
        tbl = {}
        for o in self.smap.OBJECT_ROLES:
            known = bool(d["belief"].get(b.get(o)))
            for r in places:
                p = (self.smap.belief(o, r) if known else 1.0 / len(bound)) if r in bound else 0.0
                tbl[(o, r)] = repr(float(Fraction(int(p * 10 ** 9), 10 ** 9)))
        return {"look": tbl, "where": tbl}

    def update_levels(self, counts):
        """Once a tick: the level atoms from the session as it stands (the instrument's init) and the map's belief;
        the report (the values, the level, the time per tick) logged. A refusal or an error asserts no level."""
        if self.levels is None:
            return
        try:
            self.level_atoms, rep = self.levels.levels(counts, self.instrument_ports())
        except Exception as e:                      # the level is advice: it never stops the task
            self.level_atoms, rep = {}, {"error": "%s: %s" % (type(e).__name__, e)}
        self._log({"beat": self.beat, "instrument": rep})

    def reading(self):
        r = {a: 1 for a in self.dyn}
        held = any(a.startswith("holds(") for a in self.dyn)
        r["holding" if held else "handsfree"] = 1
        opened = {a[7:-1] for a in self.dyn if a.startswith("opened(")}
        for rec in self.openable:
            if rec not in opened:
                r["closed(%s)" % rec] = 1
        if self.smap is not None:
            r = self.smap.role_reading(r, self.frozen)   # the world over the bound roles: the binding changed, so does the reading
        r.update(self.level_atoms)                       # the level port's atom (the task's: spec16 step 4)
        if self.observed is not None:
            r = {a: n for a, n in r.items() if a.split("(")[0] in self.observed}
        return r

    # ── the commands ──
    def name(self, handle):
        return self.to_name[handle]

    # a rule named `verb` or `verb_why` that is not a COMMANDS key (the loop's own rules, loop-policy
    # step 2 F2): the first token is the verb, its variables by this convention
    VERBS = {"go": ("go", "L2", "R"), "open": ("open", "R"), "take": ("take", "O", "R"), "put": ("put", "O", "R")}

    def command_of(self, name, args):
        base, b = bindings(name)
        if self.smap is not None:                    # the rule's roles → the map's things
            b = {k: self.smap.handle(v, self.frozen) or v for k, v in b.items()}
        spec = COMMANDS.get(base)
        if spec is None:
            spec = self.VERBS.get(base.split("_")[0]) if self.verbs else None
            if spec is None:
                return None
            if spec[0] == "go" and "L2" not in b and b.get("R"):       # go by the receptacle alone: its location from recat
                b = dict(b, L2=next((l for l, rs in self.recat.items() if b["R"] in rs), ""))
        kind = spec[0]
        if kind == "go":
            l2 = b.get(spec[1], "")
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
        if self.smap is not None:                # the task's belief port: where the map believes the target is
            reg.weight("look", lambda args, counts: self.smap.weight("look", args))   # the query API: a room's search, next()'s place

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
        if admissible and self.changed:
            self.pending_frames.append(dict(self.delta(cmd), ev="world/delta"))
        if self.commands_log:
            with open(self.commands_log, "a") as f:
                f.write(json.dumps({"command": cmd, "rule": name, "admissible": admissible, "changed": self.changed}) + "\n")

    def _log(self, rec):
        """$METIS_ALF_LOG: one JSON line per command (the experiments' record of what the game said)."""
        p = os.environ.get("METIS_ALF_LOG")
        if p:
            with open(p, "a") as f:
                f.write(json.dumps(rec) + "\n")

    def observe(self, counts):
        """The reading the watch scores the program against: the world's, without the level hook's atoms (fetch_risk
        and its kin). A level is the host's own world line, asserted by its tick; it is never part of a surprise
        difference (belief-levels follow-up: after a stop the live level came back in the reading, and the watch
        opened a surprise {fetch_risk(low): 1} on a change the model did not cause)."""
        if self.done and not self.won:
            return {}
        return {a: n for a, n in self.reading().items() if a.split("(")[0] not in self.level_preds}

    def tick(self, counts):
        if self.done and not self.out:
            return None
        self.beat += 1
        self.stepped = False
        self.update_levels(counts)
        reading = self.reading()
        own = sorted(a for a, n in counts.items() if n > 0 and a not in reading and a.split("(")[0] not in self.dynamic_preds())
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
        if self.spec == "task" and getattr(self, "_task", None) is not None:
            self._task_step()
        if out:                                      # continues: the result is reported once, the world keeps stepping
            self.reported |= set(out)
            if self.spec == "task":
                self._task_end(out)
        return dos

    # ── a card per task (alf-tasks s-e9cc8fae step 3): what it was asked, what it did, what it believed, our own check ──
    ENDS = ("done", "stuck", "wrong_dest", "wrong_object", "nothing", "cannot", "misfit", "gave_up")

    def _root(self):
        return os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(self.smap.path)))) if self.smap is not None else None

    def _task_begin(self, atom):
        """The person's goal arrives (intent_atom): a card opens at the world's and the map's records as they stand."""
        if getattr(self, "_task", None) is None and self._root():   # a card left open on disk (a stop reloads the task: another host)
            f = os.path.join(self._root(), "records", "tasks", ".open.json")
            if os.path.exists(f):
                self._task = json.load(open(f))
        if getattr(self, "_task", None) is not None:   # the one before never ended (a stop, a new task over it): its card says so
            self._task_end(["stopped"])
        mj = getattr(self.smap, "journal", None) if self.smap is not None else None   # the map's journal file (its store's)
        n = lambda f: sum(1 for _ in open(f)) if f and os.path.exists(f) else 0
        self._task = {"goal": atom, "beat": self.beat, "commands_at": n(self.commands_log), "map_at": n(mj), "map_journal": mj,
                      "t0": time.time()}
        if self._root():                                # open on disk too, until its end writes the card
            d = os.path.join(self._root(), "records", "tasks")
            os.makedirs(d, exist_ok=True)
            json.dump(self._task, open(os.path.join(d, ".open.json"), "w"))

    def _task_end(self, out):
        """A task's end atom is out: its card under ROOT/records/tasks/ — the goal (the room's names), the ticks, the
        commands it sent, the map's records meanwhile (the belief: projections, wanted kinds, looks), the outcome and
        OUR OWN success check: for done, the goal holds in the world as observed (inrecep of the goal's thing in its
        place), never the episode's `won`."""
        task = getattr(self, "_task", None)
        end = next((a for a in out if a.split("(")[0] in self.ENDS + ("stopped",)), None)
        root = self._root()
        if task is None or end is None or root is None:
            return
        self._task = None
        if os.path.exists(os.path.join(root, "records", "tasks", ".open.json")):
            os.remove(os.path.join(root, "records", "tasks", ".open.json"))
        lines = lambda f, k: [json.loads(l) for l in list(open(f))[k:] if l.strip()] if f and os.path.exists(f) else []
        refused = end.split("(")[0] in ("nothing", "cannot", "misfit", "stopped")   # refused before anything moved, or cut short
        b = {} if refused else self.smap.binding()
        obj, rec = b.get("target"), b.get("dest")
        holds = bool(obj and rec and "inrecep(%s,%s)" % (obj, rec) in self.dyn)
        cmds = lines(self.commands_log, task["commands_at"])
        card = {"goal": task["goal"], "goal_roles": {"target": obj, "dest": rec}, "outcome": self.in_room(end),
                "ticks": self.beat - task["beat"] if self.beat >= task["beat"] else None, "seconds": round(time.time() - task["t0"], 1),
                "commands": [{"command": self.speak(" ".join(self._spoken_command(c["command"]))), "rule": c.get("rule"),
                              "admissible": c.get("admissible"), "changed": c.get("changed")} for c in cmds],
                "belief": [r for r in lines(task["map_journal"], task["map_at"]) if r.get("kind") != "observe"],
                "search": task.get("steps") or [],            # each search step: next()'s place, presence, the belief's top five
                **({"prior": "the place belief's prior: ALFRED's starts of the kind per receptacle of each type "
                             "(world/starts.json) over the room's places that can hold it, normalized over them; "
                             "next() = its argmax, ties by place id; presence: the existence belief (world/presence.json)"}
                   if task.get("steps") else {}),
                "check": {"applies": False, "why": "stopped before its end" if end == "stopped" else "refused before anything moved"} if refused else
                         {"goal_holds": holds, "agrees": holds == (end.split("(")[0] == "done"),
                          "how": "inrecep(%s,%s) in the world's facts as observed" % (obj, rec)}}
        d = os.path.join(root, "records", "tasks")
        os.makedirs(d, exist_ok=True)
        k = len([f for f in os.listdir(d) if f.endswith(".json")]) + 1
        json.dump(card, open(os.path.join(d, "task-%02d.json" % k), "w"), indent=1)
        self.last_card = card

    def _task_step(self):
        """A search step on the open card (map-queries step 1, the architect's ruling: the card says why a place was
        chosen): while the goal's thing is a kind not seen yet, the place next() gives (the likeliest bound place, ties
        by id), the presence level, and the belief's five likeliest places, once each time it changes."""
        d = self.smap.load()
        obj = d["binding"].get("target")
        if not (d.get("view") and obj and (d["things"].get(obj) or {}).get("wanted")):
            return
        bound = {d["binding"][r] for r in self.smap.place_roles(d["k"]) if d["binding"].get(r)}
        bel = d["belief"].get(obj) or {}
        step = {"next": self.smap.next(obj, excluded=[r for r in bel if r not in bound]),
                "presence": self.smap.level("presence", (obj,)),
                "belief": [[r, round(p, 4)] for r, p in sorted(bel.items(), key=lambda x: (-x[1], x[0]))[:5]]}
        steps = self._task.setdefault("steps", [])
        if not steps or {k: v for k, v in steps[-1].items() if k != "beat"} != step:
            steps.append(dict(step, beat=self.beat))
            if self._root():
                json.dump(self._task, open(os.path.join(self._root(), "records", "tasks", ".open.json"), "w"))

    def _spoken_command(self, cmd):
        """A game command in the room's handles (the game's long names → fridge1)."""
        inv = {v: k for k, v in self.to_name.items()}
        return [inv.get(w, w) for w in cmd.split()]

    def dynamic_preds(self):
        """The predicates the world owns in this program (sync may retract them): a role host's place facts too."""
        return (DYNAMIC_PREDS | PLACE_PREDS | self.level_preds) if self.smap is not None else DYNAMIC_PREDS

    def sync(self, counts):
        """The do-lines that bring the program's dynamic facts to the game's (the policy's
        own tokens untouched)."""
        from semantic_world import ports
        return ports.sync_diff(self.reading(), counts, self.dynamic_preds())

    def world(self, lines):
        raise ValueError("world lines: the game is the world; set a scenario by choosing another game")

    # ── the world page (alf-demo step 2, DEMO.md §5): what a taken command changed, as the map's delta ──
    def delta(self, command):
        """The command's change in the map's terms (web/README.md's schema): the agent's place or
        hand, a receptacle opened, what a receptacle holds now — read from the facts after it."""
        from semantic_map import spoken
        h = {v: k for k, v in self.to_name.items()}
        holding = sorted(_args(a)[0] for a in self.dyn if a.startswith("holds("))
        items = lambda r: sorted(spoken(_args(a)[0]) for a in self.dyn if a.startswith("inrecep(") and _args(a)[1] == r)
        if command.startswith("go to "):
            return {"agent": {"at": h.get(command[6:], command[6:])}}
        if command.startswith("open "):
            return {"entities": [{"id": h.get(command[5:], command[5:]), "closed": False}]}
        if command.startswith("close "):                   # nina's review N5: the map closes it again
            return {"entities": [{"id": h.get(command[6:], command[6:]), "closed": True}]}
        if command.startswith("take ") and " from " in command:
            r = h.get(command[5:].split(" from ")[1], "")
            return {"agent": {"holding": spoken(holding[0]) if holding else None}, "entities": [{"id": r, "items": items(r)}]}
        if command.startswith("move ") and " to " in command:
            r = h.get(command[5:].split(" to ")[1], "")
            return {"agent": {"holding": spoken(holding[0]) if holding else None}, "entities": [{"id": r, "items": items(r)}]}
        return {"note": command}

    def speak(self, text):
        """A line with the program's handles said as the game's things are named (fridge1 → "fridge 1"):
        metis-agent's service says the director's lines with it (nina's alf-demo review N3)."""
        import re
        from semantic_map import spoken
        if re.match(r"^gave_up: ", text):            # the director's end line for a search's answer (map-queries step 1)
            return "I stopped looking."
        if getattr(self, "smap", None) is not None:   # a role said as the thing it is bound to: name(role, thing)
            names = dict(self.smap.names(self.frozen))
            if names:
                text = re.sub(r"\b(%s)\b" % "|".join(sorted(names, key=len, reverse=True)), lambda m: names[m.group(0)], text)
        return re.sub(r"\b[a-z]+\d+\b", lambda m: spoken(m.group(0)) if m.group(0) in self.to_name else m.group(0), text)

    GOALS = {"goto": "going to {0}", "open": "opening {0}", "take": "taking {0}", "put": "moving {0} to {1}"}

    def goal_text(self, goal):
        """A hierarchy domain's goal as the person reads it (goto(countertop3) → "going to countertop 3"):
        metis-agent's service says the working status with it (nina's alf-demo 3b wire note); None for a
        goal it has no words for."""
        from semantic_map import spoken
        name, _, rest = goal.partition("(")
        words = self.GOALS.get(name)
        args = [a.strip() for a in rest.rstrip(")").split(",")] if rest else []
        if getattr(self, "smap", None) is not None:
            args = [self.smap.handle(a, self.frozen) or a for a in args]
        if words is None or words.count("{") != len(args):
            return None
        return words.format(*(spoken(a) if a in self.to_name else a for a in args))

    def in_room(self, atom):
        """An atom of the program's roles with its roles as the things they are bound to (goto(p1) →
        goto(countertop3)): the hierarchy's chain as the page shows it; the atom itself without a map."""
        if getattr(self, "smap", None) is None:
            return atom
        from semantic_world import ports
        return ports.in_room(atom, lambda r: self.smap.handle(r, self.frozen))

    def frames(self):
        """The world page's frames since the last call (metis-agent's service sends them on the wire)."""
        self._seen_frames()
        out, self.pending_frames = self.pending_frames, []
        return out

    def _seen_frames(self):
        """View mode (semantic-map step 3, the architect): the page draws what the robot knows — a place
        is dimmed until the robot has seen into it. The planner's host (one per hierarchy) sends each place
        as it is first seen into, with what the map saw there (world/delta entities: unseen false, items),
        and marks it seen in the page's map file (a page loaded later draws the same)."""
        if self.smap is None or self.spec != "task":
            return
        d = self.smap.load()
        if not d.get("view"):
            return
        sent = getattr(self, "_seen_sent", None)
        if sent is None:
            sent = self._seen_sent = set()
        new = [r for r in d.get("seen", []) if r not in sent]
        if not new:
            return
        from semantic_map import spoken
        ents = [{"id": r, "unseen": False, "items": sorted(spoken(o) for o, b in d["belief"].items() if b.get(r) == 1.0)} for r in new]
        self.pending_frames.append({"ev": "world/delta", "entities": ents})
        sent.update(new)
        wm = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(self.package_dir)))), "world-map.json")
        if os.path.exists(wm):
            m = json.load(open(wm))
            for p in m.get("places", []):
                if p["id"] in sent:
                    p["unseen"] = False
            tmp = wm + ".tmp"
            json.dump(m, open(tmp, "w"), indent=1)
            os.replace(tmp, wm)

    def ports(self):
        return {"game": {"path": self.game, "task": self.task, "params": self.params, "step": self.t,
                         "done": self.done, "won": self.won, **({"room": True, "episode_won": self.episode_won} if self.room else {})},
                "observed": sorted({a.split("(")[0] for a in self.dyn} | {"closed", "handsfree", "holding"}),
                **({"names": self.smap.names(self.frozen)} if self.smap is not None else {}),     # name(role, thing) as data
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
PLACE_PREDS = {"recat", "openable", "notopenable", "absent", "lost", "believed", "seen", "unseen", "presence"}     # a role host's too: the projection asserts the place facts (a flat
                                                       # program's are static, or its own: a learned split's to keep),
                                                       # and the map's view mode what was looked for in vain (step 3)


def make(case=None, package_dir=None):
    return AlfHost(package_dir or os.getcwd(), case)
