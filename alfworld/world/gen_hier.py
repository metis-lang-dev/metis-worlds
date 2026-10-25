"""gen_hier.py — a game over the HIERARCHY's specialists (alf-hierarchy, docs/HIERARCHY.md), roles not
rooms (semantic-map s-d4270bed): every specialist is compiled ONCE over the role vocabulary, and the
room lives in the host's semantic map.

    capacity(k)          domains/hier/capacity.llp: object {target other}, receptacle {dest p0 p1..pk},
                         location {lhere ldest l1..lk} (k = 8 committed)
    committed(spec)      domains/hier/<spec>/<spec>.llp: the base + the capacity (+ the task's role statics)
    install(game, root)  the agent's catalog under ROOT: the flat mirror, the director, the semantic map
                         (domains/hier/.map.json), the committed instances, one commands log
    generate(…)          one package of a specialist over the map: the agent's (fixed, the committed
                         instance) or the driver's activation k (its start in roles, experiments/hier.py)
    card(spec, smap)     a specialist's intent.yaml from the map's things (the room's terms)

No constant of any room is in a specialist's source: game.json names the game and the map, and the host
reads the world through the map's binding (alf_host.AlfHost, semantic_map.SemanticMap).
"""
import json, os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import gen_instance  # noqa: E402
import semantic_map  # noqa: E402

SPECS = {
    "nav":    dict(types=("location", "receptacle"), dyn=("at", "recat"), goal="goto", out=("reached",)),
    "access": dict(types=("location", "receptacle"),
                   dyn=("at", "recat", "openable", "notopenable", "opened", "closed", "checked"), goal="open",
                   out=("accessible", "refused", "elsewhere")),
    "grasp":  dict(types=("location", "receptacle", "object"),
                   dyn=("at", "recat", "openable", "notopenable", "objat", "inrecep", "opened", "closed", "holds", "holding",
                        "handsfree"), goal="take", out=("taken", "refused", "elsewhere")),
    "place":  dict(types=("location", "receptacle", "object"),
                   dyn=("at", "recat", "openable", "notopenable", "objat", "inrecep", "opened", "closed", "holds", "holding",
                        "handsfree"), goal="put", out=("placed", "refused", "elsewhere")),
    "task":   dict(types=("object", "receptacle", "thing"), dyn=("inrecep", "holds", "absent", "lost", "believed"),
                   goal="fetch", takes=("reached", "accessible", "taken", "placed", "refused"),
                   out=("goto", "open", "take", "put", "done", "stuck", "wrong_dest", "wrong_object")),
}
# which specialist handles a sub-goal: the driver's manual switch table (step 3 makes it the director's handles/2)
HANDLES = {"goto": "nav", "open": "access", "take": "grasp", "put": "place"}


# the specialists' interface (specialist-tree s-404d001f step 2; metis-lang spec/15): what each reads (in: a peer's
# out or the person's; world-private: the world through its own binding), what it puts out (out), the token it acts with (motion,
# the body: every specialist but the planner moves or handles), and the statuses its outs mean
STATUS = {"nav": {"success": ["reached"], "failure": []},
          "access": {"success": ["accessible"], "failure": ["refused"]},
          "grasp": {"success": ["taken"], "failure": ["refused"]},
          "place": {"success": ["placed"], "failure": ["refused"]},
          "task": {"success": ["done"], "failure": ["stuck", "wrong_dest", "wrong_object"]}}


def manifest_fields(spec):
    """SPEC's manifest lines (metis-lang spec/15 §2.1): shared {pred: in|out|resource|world-private} and status
    {success, failure}. The world readings are world-private: each session reads them through its own binding
    (a specialist the one it was woken with, the planner the map's live one)."""
    sp = SPECS[spec]
    shared = {p: "world-private" for p in sp["dyn"]}
    shared[sp["goal"]] = "in"
    shared.update({p: "in" for p in sp.get("takes", ())})
    shared.update({p: "out" for p in sp["out"]})
    if spec != "task":
        shared["motion"] = "resource"
    return "shared: {%s}\nstatus: {success: [%s], failure: [%s]}\n" % (
        ", ".join("%s: %s" % kv for kv in shared.items()), ", ".join(STATUS[spec]["success"]), ", ".join(STATUS[spec]["failure"]))


def args_of(atom):
    i = atom.find("(")
    return [x.strip() for x in atom[i + 1:-1].split(",")] if i >= 0 else []


def task_goal(info):
    """The task resolved to the game's things (gen_instance.TASK_FACTS): (targets, dests)."""
    facts = [f.rstrip(".") for f in gen_instance.TASK_FACTS[info["task_type"]](info["params"], info)]
    return (sorted(f[len("target("):-1] for f in facts if f.startswith("target(")),
            sorted(f[len("dest("):-1] for f in facts if f.startswith("dest(")))


# ── the roles (semantic-map s-d4270bed step 2): one vocabulary per robot, the room in the host's map ──
K = semantic_map.K


def capacity(k=K):
    """The role vocabulary's source: the types every specialist's base leaves abstract (spec 12),
    completed with roles, k the places a projection binds besides dest and p0. domains/hier/capacity.llp
    is capacity(8), committed; k is this argument, never a rule's."""
    obj, rec, loc = semantic_map.OBJECT_ROLES, semantic_map.place_roles(k), semantic_map.location_roles(k)
    return "\n".join([
        "%% capacity — the ALFWorld hierarchy's role vocabulary, k = %d (semantic-map s-d4270bed; generated by" % k,
        "%% world/gen_hier.py capacity(%d)): one per robot, never per room. The host binds the roles to its" % k,
        "% semantic map per goal (world/semantic_map.py project): target, the object the goal wants; other, one",
        "% it does not; dest, where it goes; p0, the receptacle where the robot stands; p1..pk, the places most",
        "% likely to hold the target; lhere, ldest, l1..lk, their locations.",
        "catalog capacity 1.",
        'provenance text "the role vocabulary of the ALFWorld specialists, k = %d" "2026-10-24".' % k,
        "type object {%s}." % " ".join(obj),
        "type receptacle {%s}." % " ".join(rec),
        "type location {%s}." % " ".join(loc),
        "type thing {%s}." % " ".join(obj + rec), ""])


def role_statics(spec, k=K):
    """The task's static facts over roles: true in every room (target is what it wants, dest where)."""
    if spec != "task":
        return []
    return (["target(target)", "dest(dest)", "nottarget(other)"]
            + ["notdest(%s)" % r for r in semantic_map.place_roles(k) if r != "dest"])


def instance_text(spec, base_rel, capacity_rel, init=(), name=None, k=K, header=None):
    """A specialist's instance: its base and the role vocabulary, the task's role statics, the start
    (`init`: role atoms) — no constant of any room. committed(spec) is the one domains/hier/<spec>/ holds."""
    lines = ["% " + (name or spec) + " — " + (header or "the %s specialist over the role vocabulary (semantic-map s-d4270bed): "
             "compiled once, the room in the host's semantic map (generated by world/gen_hier.py)." % spec),
             "catalog %s 1." % (name or spec),
             'provenance text "the %s specialist over roles: the host projects the map onto them" "2026-10-24".' % spec,
             'include "%s".' % base_rel, 'include "%s".' % capacity_rel, ""]
    st = role_statics(spec, k)
    if st:
        lines += ["% the task over roles: what it wants is the target, where, the dest"] + [a + "." for a in st] + [""]
    lines += ["#init %s 1" % a for a in init]
    lines += ["#steps 8", "#seeds 1", ""]
    return "\n".join(lines)


def committed(spec):
    return instance_text(spec, "../%s_domain.llp" % spec, "../capacity.llp")


def card(spec, smap):
    """The activation's intent.yaml (alf-hierarchy step 2), from the semantic map (step 2 of
    semantic-map): the specialist's card template (domains/hier/<spec>/intent.yaml) with its slots'
    enums and values the map's things — every place, every thing that can be picked up — and only the
    examples whose values the map has. The card stays in the room's terms (the person names things);
    the host projects what it is told onto the roles (AlfHost.intent_atom). None when the specialist
    has no card."""
    import yaml
    t = os.path.join(os.path.dirname(HERE), "domains", "hier", spec, "intent.yaml")
    if not os.path.exists(t):
        return None
    text = open(t).read()
    c = yaml.safe_load(text)
    d = smap.load()
    import re
    num = lambda h: (re.sub(r"\d+$", "", h), int(re.search(r"\d*$", h).group() or 0))   # cabinet2 before cabinet10
    have = {"receptacle": sorted(d["places"], key=num),
            "object": sorted((o for o, th in d["things"].items() if th["pickupable"]), key=num)}
    if d.get("view") and spec == "task":   # view mode: the task's kind stays a value ("a tomato": any tomato), seen or not
        kinds = {semantic_map.want_handle(t) for t in d["task"]["targets"]}
        have["object"] = sorted(set(have["object"]) | kinds, key=num)
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
    return ("# GENERATED by world/gen_hier.py from domains/hier/%s/intent.yaml for the semantic map's things.\n" % spec
            + head + yaml.dump(c, Dumper=Dumper, sort_keys=False, allow_unicode=True, width=100, default_flow_style=None))


def write_card(pkg, spec, smap):
    """SPEC's card in its package PKG from the map as it is now: intent.yaml, and the generated grammar
    and prompts under intent/ when the package has them (the agent's: metis.intents over the catalog
    root, PKG's grandparent's parent) — at install, and again when the map grows in view mode (a thing
    seen for the first time: the card names it; the agent re-reads it, no reload). → the card's text,
    None when SPEC has no card."""
    c = card(spec, smap)
    if c is None:
        return None
    open(os.path.join(pkg, "intent.yaml"), "w").write(c)
    d = os.path.join(pkg, "intent")
    if os.path.isdir(d):
        from pathlib import Path
        from metis import intents
        intents.ROOT = Path(pkg).resolve().parents[2]
        sp, name = intents.load_from(pkg), os.path.basename(os.path.normpath(pkg))
        for fn, text in [("%s.gbnf" % name, intents.grammar(sp)), ("%s-prompt.txt" % name, intents.prompt(sp)),
                         ("%s-spoken.txt" % name, intents.spoken(sp))]:
            open(os.path.join(d, fn), "w").write(text)
    return c


def build_map(path, info, mirror, k=K, view=False):
    """The hierarchy's semantic map at PATH from the mirror's game as it is now (its static facts and its
    reading) and the task (task_goal); view: the robot sees only what stands before it (step 3)."""
    targets, dests = task_goal(info)
    return semantic_map.SemanticMap.build(path, mirror.static, mirror.dyn, targets, dests, k, view=view)


# ── the director (alf-hierarchy step 3): the instance's facts from the specialists' declared ports ──
DIRECTOR_OUT = ("wake", "sleep", "forward", "ask", "ended", "tick__grant", "tick__revoke")   # the last two: the tree director's (the tick)
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
    facts += ["end(%s)" % k for k in ENDS if k != "done"] + ["finished(done)"]   # done ends without an ask (opus, the demo)
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


def generate_director_package(root, game_dir, flat_pkg, commands_log, domain_rel="../../director_domain.llp", tree=False):
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
    if tree:                                                # the composition's resource, the hysteresis (brief §9 rule 4)
        lines += ["type resource {%s}." % " ".join(RESOURCES)] + [f + "." for f in hysteresis()] + [""]
    lines += ["#init %s 1" % a for a in director_start(tree)] + ["#steps 6", "#seeds 1"]
    open(os.path.join(pkg, "director.llp"), "w").write("\n".join(lines) + "\n")
    json.dump({"game": os.path.join(game_dir, "game.tw-pddl"), "game_dir": game_dir, "flat": flat_pkg, "root": root,
               "commands_log": commands_log, "out": list(DIRECTOR_OUT), "kinds": kinds},
              open(os.path.join(pkg, "game.json"), "w"), indent=1)
    open(os.path.join(pkg, "domain.yaml"), "w").write(
        "# director — activation from context as a domain (generated by world/gen_hier.py); its host re-instances the specialists.\n"
        "program: director.llp\nhost: director_host.py:make\nclock: {beats: 1}\nrecords: records/\n"
        "display: the director\nline: \"the director: who is woken for what arrives\"\nvoice: line\n"
        + (DIRECTOR_FIELDS if tree else ""))
    shim = open(os.path.join(HERE, "package_host.py")).read().replace("__WORLD__", HERE).replace('"alf_host"', '"director_host"').replace("AlfHost", "DirectorHost")
    open(os.path.join(pkg, "director_host.py"), "w").write(shim)
    return pkg


def install(game_dir, root, person=True, k=K, view=False, tree=False):
    """A game installed for the agent under ROOT: domains/hier/_flat (the mirror's package), the
    director, the semantic map (domains/hier/.map.json: the room as data, bound to the roles for the
    game's own task until a goal re-projects it), the task (continues; `person`: no seeded fetch — the
    FETCH the person types is its goal; False seeds the driver's fetch), and every specialist — each the
    committed instance over the role vocabulary (k: the capacity's places; 8 is the committed
    capacity.llp), no room in its source: the director's forward delivers it its goal on the live
    session. view: the map sees only what the robot sees (semantic-map step 3; default every fact).
    Every host appends its commands to domains/hier/.commands.jsonl, the shared world state.
    tree (specialist-tree s-404d001f step 2, the tick): the director over director_tree_domain.llp (the path, the
    motion's grants) and every specialist's extensions/tick.llp declaring the `motion` token it is granted.
    → {name: package dir}."""
    hier = os.path.join(root, "domains", "hier")
    os.makedirs(hier, exist_ok=True)
    import shutil
    bases = os.path.join(os.path.dirname(HERE), "domains")        # the lifted bases the instances include, copied when the root is not this repo
    for src, dst in [(os.path.join(bases, b), os.path.join(root, "domains", b))
                     for b in ("director_domain.llp", "director_tree_domain.llp", "protocol_domain.llp")] + \
                    [(os.path.join(bases, "hier", sp + "_domain.llp"), os.path.join(hier, sp + "_domain.llp")) for sp in SPECS]:
        if os.path.abspath(src) != os.path.abspath(dst) and not os.path.exists(dst):
            shutil.copy(src, dst)
    cap = os.path.join(hier, "capacity.llp")
    if not os.path.exists(cap) or open(cap).read() != capacity(k):
        open(cap, "w").write(capacity(k))
    flat, _, _ = gen_instance.generate(game_dir, os.path.join(hier, "_flat"))
    flat_pkg = os.path.dirname(flat)
    log = os.path.join(hier, ".commands.jsonl")
    open(log, "w").close()
    from alf_host import AlfHost
    mirror = AlfHost(flat_pkg)
    try:
        info = dict(json.load(open(os.path.join(flat_pkg, "game.json"))), static=sorted(mirror.static), task_type=mirror.task, params=mirror.params)
        smap = build_map(os.path.join(hier, ".map.json"), info, mirror, k, view=view)
        reading = mirror.reading()
    finally:
        mirror.gym.close()
    smap.project(*args_of(seed(info)[0]))                          # the game's own task until a goal says otherwise
    out = {"_flat": flat_pkg, "director": generate_director_package(
        root, game_dir, flat_pkg, log, domain_rel="../../director_tree_domain.llp" if tree else "../../director_domain.llp", tree=tree)}
    for spec in SPECS:
        # the task's goal: a person's FETCH arrives by intent (person=True: no seed), else the driver's seed
        inits = [smap.intent_atom(seed(info)[0])] if spec == "task" and not person else []
        path = generate(game_dir, hier, spec, 0, info, smap, reading, inits, [], intents=(spec == "task"), continues=True, fixed=True,
                        commands_log=log, places=k)
        out[spec] = os.path.dirname(path)
        if tree:                                                   # the protocol: the specialist reads its grant from it
            prog = os.path.join(out[spec], spec + ".llp")
            t = open(prog).read()
            inc = 'include "../capacity.llp".\n'
            t = t.replace(inc, inc + 'include "../../protocol_domain.llp".\ninclude "../tick_types.llp".\n', 1)
            open(prog, "w").write(t)
    if tree:
        open(os.path.join(hier, "composition.yaml"), "w").write(composition())
        open(os.path.join(hier, "tick_types.llp"), "w").write(
            "%% tick_types — the composition's specialists and resources (specialist-tree step 2): the protocol's\n"
            "%% abstract domain and resource made concrete (generated by world/gen_hier.py).\n"
            "catalog tick_types 1.\ntype domain {%s}.\ntype resource {%s}.\n" % (" ".join(SPECS), " ".join(RESOURCES)))
    return out


def director_start(tree=False):
    """The director's state before the first arrival: the planner up, the specialists down (tree: the motion free,
    the planner on the path, the specialists off it)."""
    out = ["active(task)", "attention(task)", "fresh"] + ["inactive(%s)" % d for d in SPECS if d != "task"]
    if tree:
        sp = [d for d in SPECS if d != "task"]
        out += ["free(%s)" % r for r in RESOURCES] + ["path(task)"] + ["offpath(%s)" % d for d in sp]
        out += ["nowant(%s)" % d for d in sp] + ["nolate(%s)" % d for d in sp] + ["age_of(%s,a0)" % d for d in SPECS]
    return out


RESOURCES = ("motion",)            # the body: one specialist moves or handles at a time
# the tree director's side of the protocol and its resource (spec/15 §2.3: I5's count invariant over free/holder)
DIRECTOR_FIELDS = ("shared: {tick__status: in, tick__active: in, tick__done: in, tick__stuck: in, tick__grant: out, "
                   "tick__goal: out, tick__revoke: out}\nresources: {motion: {count: 1, free: free, held_by: [holder]}}\n")


def composition():
    """The composition file (spec/15 §2.3, domains/hier/composition.yaml): the capacity, the protocol, the
    specialists in the tick's order, the direct domain, the world's ports (out: what the host writes into the
    sessions — the world-private readings and the person's fetch; in: the goals whose specialists' commands it
    executes). Flow maps and lists, one key a line, no anchors."""
    order = ["task"] + [d for d in SPECS if d != "task"]
    out = sorted({p for sp in SPECS.values() for p in sp["dyn"]} | {"fetch"})
    cmds = [SPECS[d]["goal"] for d in order if d != "task"]
    return ("# composition — the ALFWorld hierarchy as one package (specialist-tree s-404d001f; generated by world/gen_hier.py)\n"
            "capacity: capacity.llp\nprotocol: ../protocol_domain.llp\nspecialists: [%s]\ndirect: director\n"
            "world: {out: [%s], in: [%s]}\n" % (", ".join(order), ", ".join(out), ", ".join(cmds)))
HOLD_GRANT, HOLD_STATUS = 1, 1     # brief §9 rule 4: a grant is not revoked within k ticks, a status holds m ticks


def hysteresis(k=HOLD_GRANT, m=HOLD_STATUS, ages=4):
    """The tree director's hysteresis facts over its ages a0..a3: mature_grant / young_grant (k), mature_status (m)."""
    a = ["a%d" % i for i in range(ages)]
    return (["mature_grant(%s)" % x for x in a[k:]] + ["young_grant(%s)" % x for x in a[:k]]
            + ["mature_status(%s)" % x for x in a[m:]])


def seed(info):
    """The driver's way into the task, in the room's terms: fetch(the first target, the first
    destination) — the atom the FETCH intent types; the host projects it onto the roles."""
    targets, dests = task_goal(info)
    return ["fetch(%s,%s)" % (targets[0], dests[0])]


def generate(game_dir, out_dir, spec, k, info, smap, reading, init, replay, domain_rel=None, intents=False, continues=False, fixed=False,
             commands_log=None, places=None):
    """One package of SPEC over the semantic map SMAP. `fixed` (the agent's install): the committed
    instance (committed(spec)), plus `init` (role atoms: the driver's seed) — the world comes in on the
    first tick's sync, the goals by delivery. Otherwise the driver's activation K: the instance over
    domain_rel (default ../../hier/<spec>_domain.llp) and the capacity beside it, starting at the world
    as it is now said in roles (`reading`: the game's facts, the mirror's; the projection's binding) and
    `init`. Either way no constant of the room is in the source: game.json names the game and the map."""
    sp = SPECS[spec]
    kp = places or smap.load()["k"]                                  # the capacity's places (install's k)
    iid = gen_instance.instance_id(game_dir)
    if fixed:
        text = instance_text(spec, "../%s_domain.llp" % spec, "../capacity.llp", init, k=kp)
    else:
        base = domain_rel or "../../hier/%s_domain.llp" % spec
        roles = smap.role_reading(reading)
        start = [a for a in sorted(roles) if a.split("(")[0] in sp["dyn"]] + list(init)
        text = instance_text(spec, base, os.path.join(os.path.dirname(base), "capacity.llp"), start, name="%s_%d" % (spec, k), k=kp,
                             header="activation %d of the %s specialist on %s, over the role vocabulary (generated by world/gen_hier.py)." % (k, spec, iid))
    pkg = os.path.join(out_dir, spec if fixed else "%s-%d" % (spec, k))   # fixed: the agent's installed directory
    os.makedirs(pkg, exist_ok=True)
    path = os.path.join(pkg, spec + ".llp")
    open(path, "w").write(text)
    json.dump({"game": os.path.join(game_dir, "game.tw-pddl"), "task_type": info["task_type"], "params": info["params"],
               "handles": info["handles"], "replay": list(replay), "spec": spec, "observe": list(sp["dyn"]), "out": list(sp["out"]), "continues": bool(continues),
               "map": os.path.abspath(smap.path), "commands_log": commands_log},
              open(os.path.join(pkg, "game.json"), "w"), indent=1)
    open(os.path.join(pkg, "domain.yaml"), "w").write(
        "# %s — the %s specialist on an ALFWorld game over the role vocabulary (generated by world/gen_hier.py).\n"
        "program: %s.llp\nhost: alf_host.py:make\nclock: {beats: 1}\nrecords: records/\n"
        "display: ALFWorld %s (%s)\nline: \"%s\"\nvoice: own\n" % (spec, spec, spec, spec, iid, spec))
    open(os.path.join(pkg, "domain.yaml"), "a").write(manifest_fields(spec))
    c = write_card(pkg, spec, smap) if intents else None   # the agent's package (step 2); the driver's stays four files
    if c is not None:
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
