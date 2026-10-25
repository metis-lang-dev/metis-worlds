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

from metis.host import GymChild, find_interpreter

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
    "cmd_apply": ("dir",),           # cmd_apply(D): the key on the door in direction D (the gym's UNLOCK macro)
}
DIRS = {"n": "N", "e": "E", "s": "S", "w": "W", "ne": "NE", "se": "SE", "sw": "SW", "nw": "NW"}
ACTIONS = ["N", "E", "S", "W", "NE", "SE", "SW", "NW", "PICKUP", "EAT", "DOWN", "WAIT", "OPEN", "KICK", "APPLY", "SEARCH", "MORE", "ESC"]
# the perceived predicates the sync may retract (the agent's own tokens never)
PERCEIVED = {"agent_at", "floor", "wall", "door", "corridor", "stairs_down", "stairs_up", "obj", "monster", "trap",
             "unknown", "hp", "hpmax", "hunger", "turn", "holds"}


def interpreter():
    """$METIS_MH_PY, else the world repo's own venv (setup.sh), else a shared venv beside the world repos
    (.worlds/mh; never a sibling .venv), else this interpreter (metis.host.find_interpreter)."""
    repo = os.path.dirname(HERE)
    cands, d = [os.path.join(repo, ".venv", "bin", "python")], repo
    for _ in range(3):
        d = os.path.dirname(d)
        cands.append(os.path.join(d, ".worlds", "mh", "bin", "python"))
    return find_interpreter("METIS_MH_PY", None, cands)


def bindings(name):
    base, _, rest = name.partition("[")
    b = {}
    if rest:
        for kv in rest.rstrip("]").split(","):
            k, _, v = kv.partition("=")
            b[k.strip()] = v.strip()
    return base.split("-")[0], b


class GymClient(GymChild):
    """world/mh_gym.py as a child: one JSON request per line, one answer (metis.host.GymChild; the
    level's `env` rides in open_args, beside the child's own environment)."""

    def __init__(self, level, max_steps, seed):
        super().__init__(os.path.join(HERE, "mh_gym.py"), interpreter(), "level",
                         open_args={"des": level.get("des"), "env": level.get("env"),
                                    "actions": level.get("actions") or ACTIONS, "max_steps": max_steps, "seed": seed})


ALIVE = (0.2, -1.0)    # a beast out of sight fades (exists −0.2 a turn; dropped below −1: semantic_world.bayes)
# the response time, in turns: the tree's, measured (the beast case) — act's want is relayed at one boundary, the
# director's preempt grant latched at the next, so the body answers two turns after the trigger
RHO = 2.0
SITUATION = {"oncoming", "closing", "resp_lon"}       # the situation layer's facts (the beast case): the host's, retracted when gone
# nav-belief s-794cf4c1 step 1: a map that tracks intents (GridMap.build(intents=…)) — the bound beasts' intent level
# (semantic_world.intent HOSTILE_SURE / HOSTILE_MAYBE), closing level (P(closing within RHO) at CLOSING_LEVELS, as
# belief-levels-mh) and position support, for a domain that declares them; every step's record and per-step table
# (PREDICT_H ticks) in the step log
INTENT_FACTS = {"hostile_sure", "hostile_maybe", "closing_sure", "closing_maybe", "support"}
CLOSING_LEVELS = (0.7, 0.3)
PREDICT_H = 4
ROLE_READ = {"agent_at", "floor", "door", "stairs_down", "obj", "monster", "holds", "said", "next", "toward", "step"}
SHARED = {}            # a hierarchy's one NLE process (level.json `shared`: the map's path): {key: {"gym", "last", "won_at"}}


class MhHost:
    """bind(reg) · tick(counts) -> do-lines | None · on_event(name, args) · observe(counts) -> {atom: n}
    · snapshot() / restore(snap) · ports() · reseed(seed). The message's events ride one beat:
    `said(KIND)` atoms handed in with the next tick and taken off at the one after."""

    PAIRS = ()

    def __init__(self, package_dir, case=None, max_steps=100):
        self.package_dir, self.case = package_dir, case
        self.level = json.load(open(os.path.join(package_dir, "level.json")))
        self.seed = int(self.level.get("seed", 1))
        self.max_steps = int(self.level.get("max_steps", max_steps))
        # a level over the role program (semantic-world step 2): the level is the host's map (semantic_world.grid,
        # libs/semantic-world), read through its binding; the program speaks roles and is never the level's
        from semantic_world.grid import GridMap
        self.cmap = GridMap(self.level["map"]) if self.level.get("map") else None
        self.fired = []                                 # (rule, the binding it fired under)
        # a hierarchy's domain (mh_hier): its spec, what it reads, the world one process shared by the hierarchy's hosts
        self.spec, self.observed = self.level.get("spec"), set(self.level["observe"]) if "observe" in self.level else None
        self.continues, self.key = bool(self.level.get("continues")), self.level.get("shared")
        self.beat, self.due, self.script, self.last = 0, (), {}, None
        if self.key and self.key in SHARED:             # another host of the hierarchy opened the world: no reset
            self.gym = SHARED[self.key]["gym"]
            self.cells = self.gym.info["cells"]
            self._take(SHARED[self.key]["last"], fresh=False)
            self.actions, self.t, self.pending_events, self.handed = [], 0, [], []
            return
        self.gym = GymClient(self.level, self.max_steps, self.seed)
        self.cells = self.gym.info["cells"]
        if self.key:
            SHARED[self.key] = {"gym": self.gym, "last": None}
        self._reset(self.seed)

    def _reset(self, seed):
        self.seed = seed
        out = self.gym.call("reset", seed=seed)
        self._take(out)
        if self.cmap is not None:                       # the episode's first binding (then the beat's: tick)
            self.cmap.project()
        self.actions, self.t = [], 0
        self.pending_events = list(out.get("events", []))
        self.handed = []

    def _take(self, out, fresh=True):
        self.atoms = set(out["atoms"])
        if fresh and getattr(self, "key", None):        # the shared world's latest, for every host of the hierarchy
            SHARED[self.key]["last"] = out
        if getattr(self, "cmap", None) is not None and fresh:   # the map follows what the robot sees, step by step:
            self.cmap.cycle(self.atoms, 1, self.cmap.models(), ALIVE)   # the beasts predicted a turn, then the sighting
            d = self.cmap.load()
            if d.get("intents") is not None:                # the intent belief's trace, a record per world step
                from semantic_world import intent
                self._log({"t": getattr(self, "t", 0), "intents": self.cmap.intent_record(RHO, d), "table": self.cmap.predict_table(PREDICT_H, d),
                           "levels": {"hostile": [intent.HOSTILE_SURE, intent.HOSTILE_MAYBE], "closing": list(CLOSING_LEVELS),
                                      "temper": intent.TEMPER, "rho": RHO}, "agent": d["agent"]["at"]})
        msg = out.get("message", "")
        # NLE keeps the last message on the line: it is an event only when it is new
        self.events = list(out.get("events", [])) if msg != getattr(self, "message", None) else []
        self.message = msg
        self.done, self.won = bool(out.get("done")), bool(out.get("won"))
        self.reward = float(out.get("reward", 0.0))
        if self.won and getattr(self, "continues", False):   # the hierarchy: the level won is not the run's end — nav reports
            self.done = False                                  # reached(goal), the task its done (alfworld's AlfHost the same)

    def pending(self):
        """Input waiting for this host's next tick (the tick's wake rule, specialist-tree step 2): the message's
        events of its last steps, handed in as one-beat atoms then; or a STALE projection — the route the map would
        bind now (the robot on its frontier goal, a beast moved) differs from the bound one: the binding moves at
        the tick's input, so until this domain beats, its reading through the old binding shows no change."""
        if self.pending_events:
            return True
        if self.cmap is None or self.cmap.load().get("flat"):
            return False
        return self.cmap.route() != self.cmap.load().get("path")

    def reseed(self, seed):
        if seed != self.seed:
            self._reset(seed)

    def situation(self):
        """The situation layer's facts in roles (specialist-tree s-404d001f step 3a, the beast case; semantic_world
        .situation over the map's pairs: reach for braking distance): oncoming(B) for a beast coming at the robot along
        the map and dangerous (opposite direction, the gap within both reaches), closing(B) while it is not beside the
        robot yet, resp_lon(R) the fold's response.
        The numbers stay here; the memory of the axis safe before is this host's, across its beats."""
        from semantic_world.situation import Dynamics, Situation
        if getattr(self, "_sit", None) is None:
            self._sit = Situation()
        states = self._sit.check(self.cmap.pairs(rho=RHO))
        fold = Situation.fold(states, Dynamics(vmax=1.0, rho=RHO, min_dist=1.0))
        out = {"resp_lon(%s)" % fold["resp_lon"]: 1}
        for st in states:
            if st.role and st.type == "opp_dir" and st.dangerous:
                out["oncoming(%s)" % st.role] = 1
                if st.d_lon > 1:                           # not beside yet: a cell or more between
                    out["closing(%s)" % st.role] = 1
        return out

    def gaps(self):
        """The beasts' gaps along the way before a step, for the log (the beast case's safety check): [[role, type,
        d_lon, dangerous]] from a fresh situation (no memory), None off a role level or with no log."""
        if self.cmap is None or not os.environ.get("METIS_MH_LOG"):
            return None
        from semantic_world.situation import Situation
        return [[st.role, st.type, st.d_lon, st.dangerous] for st in Situation().check(self.cmap.pairs(rho=RHO))]

    def reading(self):
        if self.cmap is not None:
            r = self.cmap.role_reading({a: 1 for a in self.atoms})
            if self.observed is not None and self.observed & SITUATION:
                r.update(self.situation())
            if self.observed is not None and self.observed & INTENT_FACTS:
                r.update(self.cmap.intent_facts(CLOSING_LEVELS, RHO))
            keep = self.observed if self.observed is not None else ROLE_READ   # what the domain declares
            return {a: n for a, n in r.items() if a.split("(")[0] in keep}
        return {a: 1 for a in self.atoms}

    def speak(self, text, binding=None):
        """A rule's line said in the world's words (the binding's — the one its rule fired under, when given:
        "the door at 3, 1", "east")."""
        return self.cmap.say(text, binding) if self.cmap is not None else text

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
            if base == "cmd_apply":
                return ["UNLOCK:" + d]                   # APPLY, the key's letter, the direction, y (mh_gym)
            return [base[4:].upper(), d]                 # OPEN then the direction
        return {"cmd_pickup": ["PICKUP"], "cmd_eat": ["EAT"], "cmd_down": ["DOWN"], "cmd_wait": ["WAIT"],
                "cmd_search": ["SEARCH"], "cmd_apply": ["APPLY"]}.get(base)

    def bind(self, reg):
        pass

    def on_event(self, name, args):
        acts = self.action_of(name, args)
        if self.cmap is not None:                       # the binding the rule fired under (its line is said in it)
            self.fired.append((name, self.cmap.binding()))
        if not acts or self.done or self.won:          # nothing steps a world that is over
            return
        gaps = self.gaps()
        for a in acts:
            out = self.gym.call("step", action=a)
            self._take(out)
            self.t += 1
            self.actions.append(a)
            self._log({"beat": self.beat, "t": self.t, "rule": name, "action": a, "message": self.message,
                       "events": self.events, "reward": self.reward, "done": self.done, "won": self.won,
                       **({"gaps": gaps} if gaps is not None else {})})
            if self.won and getattr(self, "won_at", None) is None:
                self.won_at = __import__("time").perf_counter()       # the winning step (a turn's end, before the episode's record)
                if self.key:
                    SHARED[self.key]["won_at"] = self.won_at
            if self.done:
                break
        beast = bindings(name)[1].get("B")
        if self.cmap is not None and beast and "said(killed)" in self.events:
            # the world says the rule's beast is dead: out of the map (core.gone), so no motion model carries it on and
            # the situation layer finds nothing coming (the beast case: act's release)
            thing = self.cmap.handle(beast, self.fired[-1][1])
            if thing:
                self.cmap.gone(thing, "killed")
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
        if self.key and SHARED.get(self.key, {}).get("last") is not None:
            self._take(SHARED[self.key]["last"], fresh=False)  # the world as another host of the hierarchy left it
        if self.done:
            return None
        self.beat += 1
        if self.cmap is not None:
            # the binding moves at the beat's input, never mid-pass (the architect's ruling, as step 3's refresh): the
            # pass's reading is said in the binding its rules fired under, so a step the rules predicted (agent_at the
            # cell they moved to) reads as predicted; the sync below then brings the new binding in as the beat's input
            self.cmap.project()
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
        owned = PERCEIVED | ({"next", "toward", "step"} | SITUATION | INTENT_FACTS if self.cmap is not None else set())   # a role level's geometry is the host's too
        for a, have in sorted(counts.items()):
            if have > 0 and a not in reading and a.split("(")[0] in owned:
                dos.append("-%s %d" % (a, have))
        return dos

    def world(self, lines):
        raise ValueError("world lines: the level is the world; set a scenario by choosing another level or seed")

    # ── metis-agent's actor (world-minihack step 2a: act without a rule) ──
    def act(self, atom):
        """A command atom no rule took (`cmd_move(n)`, `cmd_pickup`), the package's manifest saying
        actor: {...}: the world's action, as a rule named after the command would send it (action_of:
        `cmd_move[D=n]`). → {acted, action, message, events, reward, done, won}: acted false when the
        world did not take it (no such action, or nothing in the perception changed: a wall, nothing
        to pick up, no stairs to go down; a wait or a search changes nothing by design)."""
        pred, _, rest = atom.partition("(")
        args = [x.strip() for x in rest.rstrip(")").split(",") if x.strip()] if rest else []
        name = pred + ("[D=%s]" % args[0] if args else "")
        acts = self.action_of(name, ())
        if not acts:
            return {"acted": False, "action": None, "message": "no action for %s" % atom, "events": [], "reward": 0.0,
                    "done": self.done, "won": self.won}
        before = {a for a in self.atoms if a.split("(")[0] not in ("turn", "hunger", "hp")}
        self.on_event(name, ())
        after = {a for a in self.atoms if a.split("(")[0] not in ("turn", "hunger", "hp")}
        # refused: nothing in the perception changed, nothing won, and the action was not one that changes nothing by
        # design (WAIT, SEARCH). NLE keeps a repeated message on the line, so the message alone cannot say it twice
        acted = after != before or self.done or self.reward > 0 or acts[0] in ("WAIT", "SEARCH") \
            or bool(set(self.events) & {"said(hit)", "said(killed)", "said(hurt)"})   # a fight is taken (opus's N4)
        return {"acted": acted, "action": acts, "message": self.message, "events": list(self.events), "reward": self.reward,
                "done": self.done, "won": self.won}

    STEPS = {(0, -1): "north", (0, 1): "south", (1, 0): "east", (-1, 0): "west",
             (1, -1): "northeast", (-1, -1): "northwest", (1, 1): "southeast", (-1, 1): "southwest"}

    def describe(self):
        """The perception in words, for metis-agent's actor: from the atoms only (never NLE's screen
        or the des): where each perceived thing is from the agent, what is on the eight cells around
        it, what it holds, its state, and the last message's events."""
        xy = lambda c: tuple(int(v) for v in c[1:].split("_"))
        args = lambda a: a[a.index("(") + 1:-1].split(",")
        at = next((xy(args(a)[0]) for a in self.atoms if a.startswith("agent_at(")), None)
        if at is None:
            return "You do not see yourself on the map."

        def where(c):
            x, y = xy(c)
            dx, dy = x - at[0], y - at[1]
            if (dx, dy) == (0, 0):
                return "here, on your cell"
            parts = ([("%d %s" % (abs(dy), "north" if dy < 0 else "south"))] if dy else []) + \
                    ([("%d %s" % (abs(dx), "west" if dx < 0 else "east"))] if dx else [])
            return " and ".join(parts) + " of you"
        things = []
        for a in sorted(self.atoms):
            pred = a.split("(")[0]
            if pred in ("obj", "monster", "trap"):
                n, c = args(a)
                w = n.replace("_", " ")
                art = "a trap:" if pred == "trap" else ("an" if w[:1] in "aeiou" else "a")
                things.append("%s %s (%s) is %s" % (art, w, pred if pred != "obj" else "item", where(c)))
            elif pred in ("stairs_down", "stairs_up"):                      # the stairs down are the room's goal (gen_level.TASK)
                things.append("%s is %s" % ("the goal (a staircase)" if pred == "stairs_down" else "a staircase up (not the goal)",
                                            where(args(a)[0])))
            elif pred == "door":
                c, s = args(a)
                things.append("a %s door is %s" % (s, where(c)))
        around = []
        cells = {}                                 # the cell's most specific kind (a stairs cell is also floor: opus's R2)
        RANK = {"stairs_down": 0, "door": 1, "corridor": 2, "wall": 3, "floor": 4}
        WORD = {"stairs_down": "the goal", "corridor": "a corridor", "wall": "a wall", "floor": "floor"}
        for a in sorted(self.atoms):
            pred = a.split("(")[0]
            if pred in RANK:
                c = args(a)[0]
                word = "a %s door" % args(a)[1] if pred == "door" else WORD[pred]
                if c not in cells or RANK[pred] < cells[c][0]:
                    cells[c] = (RANK[pred], word)
        for (dx, dy), word in self.STEPS.items():
            c = "c%d_%d" % (at[0] + dx, at[1] + dy)
            kind = cells.get(c, (None, None))[1]
            if kind is None:
                kind = "nothing you can see"
            elif kind == "floor" and any(a.startswith(("monster(", "obj(")) and a.endswith("," + c + ")") for a in self.atoms):
                kind = next(a.split("(")[1].split(",")[0].replace("_", " ") for a in self.atoms
                            if a.startswith(("monster(", "obj(")) and a.endswith("," + c + ")"))
            around.append("%s: %s" % (word, kind))
        held = sorted(args(a)[0].replace("_", " ") for a in self.atoms if a.startswith("holds("))
        state = [a for a in self.atoms if a.split("(")[0] in ("hp", "hunger")]
        said = [e[5:-1] if e.startswith("said(") else e for e in self.events]
        return ("You see: " + ("; ".join(things) if things else "nothing but the room") + ".\n"
                "Around you: " + ", ".join(around) + ".\n"
                "You carry: " + (", ".join(held) if held else "nothing") + ". " + " ".join(sorted(state)) + "\n"
                "Last turn: " + (", ".join(said) if said else "nothing happened") + ".")

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
