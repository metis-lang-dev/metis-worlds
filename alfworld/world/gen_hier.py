"""gen_hier.py — a game as generated instances over the HIERARCHY's lifted specialists
(alf-hierarchy step 1, docs/HIERARCHY.md): one package per activation,

    generate(game_dir, out_dir, spec, k, handles, reading, init, replay)

writes out_dir/<spec>-<k>/{<spec>.llp, game.json, domain.yaml, alf_host.py} — the specialist's
instance: the types it uses, the static facts it sees, the current world facts it observes
(`reading`, the driver's mirror of the game, filtered to the specialist's predicates), the
goal or the results and the task's tokens (`init`), over ../../hier/<spec>_domain.llp (the driver
copies the bases to out_dir/hier). game.json carries the commands to replay (the game is a
fresh child per run), the observed predicates and the result predicates for the host.
With intents=True (the domain agent's package, alf-hierarchy step 2) it adds intent.yaml, the
specialist's card (domains/hier/<spec>/intent.yaml) filled with the activation's things, and
names it in domain.yaml; the driver's packages stay four files.
"""
import json, os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import gen_instance  # noqa: E402

SPECS = {
    "nav":    dict(types=("location", "receptacle"), static=("recat",), dyn=("at",), goal="goto", out=("reached",)),
    "access": dict(types=("location", "receptacle"), static=("recat", "openable", "notopenable"),
                   dyn=("at", "opened", "closed", "checked"), goal="open", out=("accessible", "refused", "elsewhere")),
    "grasp":  dict(types=("location", "receptacle", "object"), static=("recat", "openable", "notopenable"),
                   dyn=("at", "objat", "inrecep", "opened", "closed", "holds", "holding", "handsfree"), goal="take",
                   out=("taken", "refused", "elsewhere")),
    "place":  dict(types=("location", "receptacle", "object"), static=("recat", "openable", "notopenable"),
                   dyn=("at", "objat", "inrecep", "opened", "closed", "holds", "holding", "handsfree"), goal="put",
                   out=("placed", "refused", "elsewhere")),
    "task":   dict(types=("object", "receptacle", "thing"), static=("target", "dest", "notdest", "nottarget"), dyn=("inrecep",),
                   goal="fetch", takes=("reached", "accessible", "taken", "placed", "refused"),
                   out=("goto", "open", "take", "put", "done", "stuck", "wrong_dest", "wrong_object")),
}
# which specialist handles a sub-goal: the driver's manual switch table (step 3 makes it the director's handles/2)
HANDLES = {"goto": "nav", "open": "access", "take": "grasp", "put": "place"}


def args_of(atom):
    i = atom.find("(")
    return [x.strip() for x in atom[i + 1:-1].split(",")] if i >= 0 else []


def static_facts(spec, info, objects=None):
    """The specialist's static facts from the game's (gen_instance's maps), plus the complements."""
    st = list(info["static"])
    want = SPECS[spec]["static"]
    facts = [a for a in st if a.split("(")[0] in want]
    if "notopenable" in want:
        kinds = info["handles"]["kind"]
        openable = {a[len("openable("):-1] for a in st if a.startswith("openable(")}
        facts += ["notopenable(%s)" % r for r, k in sorted(kinds.items()) if k == "receptacle" and r not in openable]
    if "target" in want:
        facts += [f.rstrip(".") for f in gen_instance.TASK_FACTS[info["task_type"]](info["params"], info)]
        dests = {f[len("dest("):-1] for f in facts if f.startswith("dest(")}
        kinds = info["handles"]["kind"]
        facts += ["notdest(%s)" % r for r, k in sorted(kinds.items()) if k == "receptacle" and r not in dests]
        targets = {f[len("target("):-1] for f in facts if f.startswith("target(")}
        facts += ["nottarget(%s)" % o for o in sorted(objects or ()) if o not in targets]
    return facts


def card(spec, kinds, info):
    """The activation's intent.yaml (alf-hierarchy step 2): the specialist's card template
    (domains/hier/<spec>/intent.yaml) with its slots' enums and values the activation's things —
    every receptacle, the objects that can be picked up (the task: its targets) — and only the
    examples whose values the game has. None when the specialist has no card."""
    import yaml
    t = os.path.join(os.path.dirname(HERE), "domains", "hier", spec, "intent.yaml")
    if not os.path.exists(t):
        return None
    text = open(t).read()
    c = yaml.safe_load(text)
    pick = {a[len("pickupable("):-1] for a in info["static"] if a.startswith("pickupable(")}
    import re
    num = lambda h: (re.sub(r"\d+$", "", h), int(re.search(r"\d*$", h).group() or 0))   # cabinet2 before cabinet10
    have = {"receptacle": sorted(kinds.get("receptacle", []), key=num),
            "object": sorted((o for o in kinds.get("object", []) if spec == "task" or o in pick), key=num)}
    for slot in c.get("slots") or {}:      # an enum value upper-cased, as the mapper looks it up; the atom's constant
        c["slots"][slot] = {"enum": [v.upper() for v in have[slot]]}
        c["values"][slot] = {v.upper(): v for v in have[slot]}

    # the room's things in the prompt too: the grammar holds the model to them, and a model that
    # has not read a name (bread, a spatula) answers UNKNOWN rather than an enum value it never saw
    said = {"receptacle": "The receptacles here", "object": "The objects this task moves" if spec == "task"
            else "The objects here that can be picked up"}
    c["guidance"] = c["guidance"].rstrip("\n") + "\n" + "".join(
        "%s: %s.\n" % (said[slot], ", ".join(v.upper() for v in have[slot])) for slot in c.get("slots") or {})

    def known(j):
        return all(j[k].lower() in have[k] for k in j if k in have)

    c["examples"] = [e for e in c["examples"] if known(e[1])]
    if c.get("spoken"):
        c["spoken"]["examples"] = [e for e in c["spoken"]["examples"] if known(e[1])]
    head = "".join(l for l in text.splitlines(True) if l.startswith("#"))

    class Dumper(yaml.SafeDumper):
        pass
    Dumper.add_representer(str, lambda d, v: d.represent_scalar("tag:yaml.org,2002:str", v, style="|" if "\n" in v else None))
    return ("# GENERATED by world/gen_hier.py from domains/hier/%s/intent.yaml for this activation's things.\n" % spec
            + head + yaml.dump(c, Dumper=Dumper, sort_keys=False, allow_unicode=True, width=100, default_flow_style=None))


# ── the director (alf-hierarchy step 3): the instance's facts from the specialists' declared ports ──
DIRECTOR_OUT = ("wake", "sleep", "forward", "ask", "ended")
ENDS = ("done", "stuck", "wrong_dest", "wrong_object")


def director_facts():
    """handles/2 and the rest, derived from SPECS — what the SDK's generator will read from the
    packages' declared ports (director decision 1): a specialist handles its goal kind; the planner
    its goal and the results; a result is what a specialist puts out that the planner takes; the
    ends end; elsewhere detours to the navigator's goal and escalates as refused."""
    kinds = sorted({sp["goal"] for sp in SPECS.values()} | {k for sp in SPECS.values() for k in sp["out"]})
    facts = ["specialist(%s)" % d for d in SPECS if d != "task"] + ["planner(task)"]
    for d, sp in SPECS.items():
        facts.append("handles(%s, %s)" % (d, sp["goal"]))
        for k in sp.get("takes", ()):
            facts.append("handles(%s, %s)" % (d, k))
    handled = {k for d, sp in SPECS.items() for k in (sp["goal"],) + tuple(sp.get("takes", ()))}
    facts += ["result(%s)" % k for k in SPECS["task"]["takes"] if k != "refused"]
    facts += ["end(%s)" % k for k in ENDS]
    facts += ["detour(elsewhere, goto)", "escalate(elsewhere, refused)"]
    facts += ["rename(elsewhere, goto, goto)", "rename(elsewhere, refused, refused)"]   # the orchestrator's frames (metis-agent director.py)
    facts += ["nohandler(%s)" % k for k in kinds if k not in handled and k not in ENDS and k != "elsewhere"]
    return kinds, facts


def generate_director(out_dir, k, init, domain_rel="../../director_domain.llp"):
    """One beat of the director as a package: its facts, its state (`init`: the carried tokens plus
    the arrival), over the lifted base; the host is none (the driver reads the effects from the run)."""
    kinds, facts = director_facts()
    name = "director_%d" % k
    lines = ["% " + name + " — the director's beat " + str(k) + " over the ALFWorld hierarchy (generated by world/gen_hier.py).",
             "catalog " + name + " 1.",
             'provenance text "generated: the director over nav/access/grasp/place/task, beat %d" "2026-10-22".' % k,
             'include "%s".' % domain_rel,
             "type domain {%s}." % " ".join(SPECS), "type kind {%s}." % " ".join(kinds), ""]
    lines += [f + "." for f in facts] + [""]
    lines += ["#init %s 1" % a for a in init] + ["#steps 6", "#seeds 1"]
    pkg = os.path.join(out_dir, name)
    os.makedirs(pkg, exist_ok=True)
    path = os.path.join(pkg, "director.llp")
    open(path, "w").write("\n".join(lines) + "\n")
    return path


def generate_director_package(root, game_dir, flat_pkg, commands_log, domain_rel="../../director_domain.llp"):
    """The director as an INSTALLED package (alf-hierarchy step 3, the agent): domains/hier/director/
    — the instance's facts and start over the lifted base, a manifest, a host shim, and game.json
    naming the game, the flat package (the host's mirror) and the shared commands log."""
    kinds, facts = director_facts()
    pkg = os.path.join(root, "domains", "hier", "director")
    os.makedirs(pkg, exist_ok=True)
    lines = ["% director — the director over the ALFWorld hierarchy, installed for the agent (generated by world/gen_hier.py).",
             "catalog director 1.",
             'provenance text "generated: the director over nav/access/grasp/place/task for %s" "2026-10-22".' % os.path.basename(os.path.dirname(game_dir)),
             'include "%s".' % domain_rel,
             "type domain {%s}." % " ".join(SPECS), "type kind {%s}." % " ".join(kinds), ""]
    lines += [f + "." for f in facts] + [""]
    lines += ["#init %s 1" % a for a in director_start()] + ["#steps 6", "#seeds 1"]
    open(os.path.join(pkg, "director.llp"), "w").write("\n".join(lines) + "\n")
    json.dump({"game": os.path.join(game_dir, "game.tw-pddl"), "game_dir": game_dir, "flat": flat_pkg, "root": root,
               "commands_log": commands_log, "out": list(DIRECTOR_OUT), "kinds": kinds},
              open(os.path.join(pkg, "game.json"), "w"), indent=1)
    open(os.path.join(pkg, "domain.yaml"), "w").write(
        "# director — activation from context as a domain (generated by world/gen_hier.py); its host re-instances the specialists.\n"
        "program: director.llp\nhost: director_host.py:make\nclock: {beats: 1}\nrecords: records/\n"
        "display: the director\nline: \"the director: who is woken for what arrives\"\nvoice: line\n")
    shim = open(os.path.join(HERE, "package_host.py")).read().replace("__WORLD__", HERE).replace('"alf_host"', '"director_host"').replace("AlfHost", "DirectorHost")
    open(os.path.join(pkg, "director_host.py"), "w").write(shim)
    return pkg


def install(game_dir, root, person=True):
    """A game installed for the agent under ROOT: domains/hier/_flat (the mirror's package), the
    director, the task's person-mode instance (continues; `person`: no seeded fetch — the FETCH the
    person types is its goal; False seeds the driver's fetch), and an empty instance of every
    specialist (no goal: the director's forward re-instances it through the director host's
    instance()). Every host appends its commands to domains/hier/.commands.jsonl, the shared world
    state the re-instancing reads. → {name: package dir}."""
    hier = os.path.join(root, "domains", "hier")
    os.makedirs(hier, exist_ok=True)
    import shutil
    bases = os.path.join(os.path.dirname(HERE), "domains")        # the lifted bases the instances include, copied when the root is not this repo
    for src, dst in [(os.path.join(bases, "director_domain.llp"), os.path.join(root, "domains", "director_domain.llp"))] + \
                    [(os.path.join(bases, "hier", sp + "_domain.llp"), os.path.join(hier, sp + "_domain.llp")) for sp in SPECS]:
        if os.path.abspath(src) != os.path.abspath(dst) and not os.path.exists(dst):
            shutil.copy(src, dst)
    flat, _, _ = gen_instance.generate(game_dir, os.path.join(hier, "_flat"))
    flat_pkg = os.path.dirname(flat)
    log = os.path.join(hier, ".commands.jsonl")
    open(log, "w").close()
    from alf_host import AlfHost
    mirror = AlfHost(flat_pkg)
    try:
        info = dict(json.load(open(os.path.join(flat_pkg, "game.json"))), static=sorted(mirror.static), task_type=mirror.task, params=mirror.params)
        reading = mirror.reading()
    finally:
        mirror.gym.close()
    out = {"_flat": flat_pkg, "director": generate_director_package(root, game_dir, flat_pkg, log)}
    for spec in SPECS:
        # the task's goal: a person's FETCH arrives by intent (person=True: no seed), else the driver's seed
        inits = seed(info) if spec == "task" and not person else []
        path = generate(game_dir, hier, spec, 0, info, reading, inits, [], intents=(spec == "task"), continues=True, fixed=True, commands_log=log)
        out[spec] = os.path.dirname(path)
    return out


def director_start():
    """The director's state before the first arrival: the planner up, the specialists down."""
    return ["active(task)", "attention(task)", "fresh"] + ["inactive(%s)" % d for d in SPECS if d != "task"]


def seed(info):
    """The driver's way into the task: fetch(the first target, the first destination) — the same
    atom the FETCH intent types."""
    facts = static_facts("task", info)
    o = sorted(a[len("target("):-1] for a in facts if a.startswith("target("))[0]
    r = sorted(a[len("dest("):-1] for a in facts if a.startswith("dest("))[0]
    return ["fetch(%s,%s)" % (o, r)]


def generate(game_dir, out_dir, spec, k, info, reading, init, replay, domain_rel=None, intents=False, continues=False, fixed=False, commands_log=None):
    sp = SPECS[spec]
    iid = gen_instance.instance_id(game_dir)
    kinds = {}
    for handle, kind in info["handles"]["kind"].items():
        kinds.setdefault(kind, []).append(handle)
    # the activation sees only the things its goal names: grasp and place the one object, the task
    # its targets (the receptacles stay whole: where a target is, is the world's to say)
    goal_objs = sorted({a[a.index("(") + 1:-1].split(",")[0] for a in init if a.split("(")[0] in ("take", "put")})
    if spec in ("grasp", "place") and goal_objs:
        kinds["object"] = goal_objs
    if spec == "task":
        # the driver's task sees its targets and the object its goal names; a person's task (intents=True)
        # sees every pickupable, since a typed fetch may name any of them (then nottarget/1 refuses it)
        targets = sorted(a[len("target("):-1] for a in static_facts("task", info) if a.startswith("target("))
        pick = sorted(a[len("pickupable("):-1] for a in info["static"] if a.startswith("pickupable("))
        named = sorted({a[a.index("(") + 1:-1].split(",")[0] for a in init if a.startswith("fetch(")})
        kinds["object"] = pick if intents else sorted(set(targets) | set(named))
    kinds["thing"] = sorted(kinds.get("object", [])) + sorted(kinds.get("receptacle", []))
    things = sorted({h for kind in sp["types"] for h in kinds.get(kind, [])})
    name = "%s_%d" % (spec, k)
    lines = ["% " + name + " — " + iid + ", activation " + str(k) + " of the " + spec + " specialist (generated by world/gen_hier.py):",
             "% the game's types and the facts this specialist sees, over the lifted " + spec + "_domain.llp.",
             "catalog " + name + " 1.",
             'provenance text "generated from ALFWorld game %s, activation %d" "2026-10-22".' % (os.path.basename(os.path.dirname(game_dir)), k),
             'include "%s".' % (domain_rel or "../../hier/%s_domain.llp" % spec)]
    for kind in sp["types"]:
        lines.append("type %s {%s}." % (kind, " ".join(sorted(kinds.get(kind, []))) or "none"))
    lines.append("")
    lines.append("% the static facts this specialist sees")
    lines += [a + "." for a in static_facts(spec, info, kinds.get("object") if spec == "task" else None)]
    lines.append("")
    lines.append("% the start: the world as it is now (this specialist's predicates), the goal or the results, the tokens")
    for a in sorted(reading):
        if a.split("(")[0] in sp["dyn"] and all(x in things for x in args_of(a)):
            lines.append("#init %s 1" % a)
    for a in init:
        lines.append("#init %s 1" % a)
    lines.append("#steps 8")
    lines.append("#seeds 1")
    pkg = os.path.join(out_dir, spec if fixed else "%s-%d" % (spec, k))   # fixed: the agent's installed directory, rewritten per activation
    os.makedirs(pkg, exist_ok=True)
    path = os.path.join(pkg, spec + ".llp")
    open(path, "w").write("\n".join(lines) + "\n")
    json.dump({"game": os.path.join(game_dir, "game.tw-pddl"), "task_type": info["task_type"], "params": info["params"],
               "handles": info["handles"], "replay": list(replay), "observe": list(sp["dyn"]), "out": list(sp["out"]), "continues": bool(continues),
               "things": things, "commands_log": commands_log},
              open(os.path.join(pkg, "game.json"), "w"), indent=1)
    open(os.path.join(pkg, "domain.yaml"), "w").write(
        "# %s — one activation of the %s specialist on an ALFWorld game (generated by world/gen_hier.py).\n"
        "program: %s.llp\nhost: alf_host.py:make\nclock: {beats: 1}\nrecords: records/\n"
        "display: ALFWorld %s (%s)\nline: \"%s\"\nvoice: own\n" % (name, spec, spec, spec, iid, spec))
    c = card(spec, kinds, info) if intents else None   # the agent's package (step 2); the driver's stays four files
    if c is not None:
        open(os.path.join(pkg, "intent.yaml"), "w").write(c)
        open(os.path.join(pkg, "domain.yaml"), "a").write("intent: {spec: intent.yaml}\n")
    shim = open(os.path.join(HERE, "package_host.py")).read().replace("__WORLD__", HERE)
    open(os.path.join(pkg, "alf_host.py"), "w").write(shim)
    return path


def vector(spec):
    """The specialist's static complexity: rules and predicates of its lifted base."""
    import re
    base = os.path.join(os.path.dirname(HERE), "domains", "hier", spec + "_domain.llp")
    text = open(base).read()
    return {"rules": len(re.findall(r"^\s+\w+ \[dyn\] :", text, re.M)),
            "preds": len(re.findall(r"^(?:pred|bwd) ", text, re.M)),
            "types": list(SPECS[spec]["types"])}
