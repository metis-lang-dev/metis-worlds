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
    """world/alf_gym.py as a child: one JSON request per line, one answer (metis.host.GymChild).
    `history` is the commands stepped since the last reset and `last` the last answer, so a host
    opened on a world another host already brought to the log's state takes it without a replay.
    A `shared` client (one per game and commands log, _SHARED) lives for the process: close() is a
    no-op on it — the agent's hierarchy opens a host per activation (alf-demo step 3b: a spawn, a
    reset and a replay cost 3.6 s, twice per director step, 90 s of a 93 s task)."""

    def __init__(self, game, max_steps=60, handles=None):
        self.history, self.last, self.shared = [], None, False
        super().__init__(os.path.join(HERE, "alf_gym.py"), interpreter(), "game", env=dict(os.environ),
                         game=game, max_steps=max_steps, handles=handles)

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


def shared_client(game, commands_log, max_steps, handles):
    key = (game, commands_log)
    c = _SHARED.get(key)
    if c is None or c.proc.poll() is not None:
        c = _SHARED[key] = GymClient(game, max_steps=max_steps, handles=handles)
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
        if self.commands_log:                                           # … and every host on that log shares one world process
            self.gym = shared_client(self.game, self.commands_log, max_steps, meta["handles"])
        else:
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
        return self.smap.intent_atom(atom) if self.smap is not None else atom

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
        self.done = bool(out.get("done")) or self.won
        if self.won and self.continues:              # the agent's hierarchy: the game won is not the run's end — the planner
            self.done = False                        # beats on to put out its own (done), the director ends the run
        self.changed = bool(out.get("changed", True))

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
            reg.weight("look", lambda args, counts: self.smap.belief(*args))

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
        if self.done and not self.won:
            return {}
        return self.reading()

    def tick(self, counts):
        if self.done and not self.out:
            return None
        self.beat += 1
        self.stepped = False
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
        if out:                                      # continues: the result is reported once, the world keeps stepping
            self.reported |= set(out)
        return dos

    def dynamic_preds(self):
        """The predicates the world owns in this program (sync may retract them): a role host's place facts too."""
        return DYNAMIC_PREDS | PLACE_PREDS if self.smap is not None else DYNAMIC_PREDS

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
                         "done": self.done, "won": self.won},
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
PLACE_PREDS = {"recat", "openable", "notopenable", "absent", "lost", "believed"}     # a role host's too: the projection asserts the place facts (a flat
                                                       # program's are static, or its own: a learned split's to keep),
                                                       # and the map's view mode what was looked for in vain (step 3)


def make(case=None, package_dir=None):
    return AlfHost(package_dir or os.getcwd(), case)
