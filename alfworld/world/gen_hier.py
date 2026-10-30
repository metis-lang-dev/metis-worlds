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
from metis.catalog import protocol_stub  # noqa: E402  (metispy's: a member's cancels, step 3c)

# ALFWorld's receptacle kinds (ALFRED's rtype constants, as the text names them): in view mode the places are known at
# once, so only these can be said absent before a search (alf-tasks step 2; the vocabulary: task_domain.llp's kind)
RECEPTACLE_KINDS = ("armchair", "bathtubbasin", "bed", "cabinet", "cart", "coffeemachine", "coffeetable", "countertop", "desk", "diningtable", "drawer", "dresser", "fridge", "garbagecan", "handtowelholder", "laundryhamper", "microwave", "ottoman", "paintinghanger", "safe", "shelf", "sidetable", "sinkbasin", "sofa", "stoveburner", "tvstand", "toaster", "toilet", "toiletpaperhanger", "towelholder")

SPECS = {
    "nav":    dict(types=("location", "receptacle"), dyn=("at", "recat"), goal="goto", out=("reached",)),
    "access": dict(types=("location", "receptacle"),
                   dyn=("at", "recat", "openable", "notopenable", "opened", "closed", "checked"), goal="open",
                   out=("accessible", "elsewhere")),
    "grasp":  dict(types=("location", "receptacle", "object"),
                   dyn=("at", "recat", "openable", "notopenable", "objat", "inrecep", "opened", "closed", "holds", "holding",
                        "handsfree"), goal="take", out=("taken", "refused_take", "elsewhere")),
    "place":  dict(types=("location", "receptacle", "object"),
                   dyn=("at", "recat", "openable", "notopenable", "objat", "inrecep", "opened", "closed", "holds", "holding",
                        "handsfree"), goal="put", out=("placed", "refused_put", "elsewhere")),
    "task":   dict(types=("object", "receptacle", "thing"), dyn=("inrecep", "holds", "absent", "lost", "believed", "fetch_risk", "seen", "unseen", "handsfree", "presence"),
                   goal="fetch", takes=("reached", "accessible", "taken", "placed", "refused_take", "refused_put", "refused"),
                   out=("goto", "open", "take", "put", "done", "stuck", "wrong_dest", "wrong_object", "nothing", "cannot", "misfit", "gave_up")),
}
# which specialist handles a sub-goal: the driver's manual switch table (step 3 makes it the director's handles/2)
HANDLES = {"goto": "nav", "open": "access", "take": "grasp", "put": "place"}


# the specialists' interface (specialist-tree s-404d001f step 2; metis-lang spec/15): what each reads (in: a peer's
# out or the person's; world-private: the world through its own binding), what it puts out (out), the token it acts with (motion,
# the body: every specialist but the planner moves or handles), and the statuses its outs mean
STATUS = {"nav": {"success": ["reached"], "failure": []},
          "access": {"success": ["accessible"], "failure": []},
          "grasp": {"success": ["taken"], "failure": ["refused_take"]},
          "place": {"success": ["placed"], "failure": ["refused_put"]},
          "task": {"success": ["done", "gave_up"], "failure": ["stuck", "wrong_dest", "wrong_object", "nothing", "cannot", "misfit"]}}


# the inversion (specialist-tree step 3b): the tree variant of a member's base reports itself through the protocol
REPORTS = {"nav": ("tick__active", "tick__done"), "access": ("tick__active", "tick__done"),
           "grasp": ("tick__active", "tick__done", "tick__stuck"), "place": ("tick__active", "tick__done", "tick__stuck"),
           "task": ("tick__active", "tick__done", "tick__stuck")}
GOAL_ARITY = {"goto": 1, "open": 1, "take": 1, "put": 2}


def tree_base(spec, text):
    """SPEC's base TEXT as the tree variant: a specialist takes its goal with a begin rule that reads it (re-putting it
    out would be a new arrival) and reports tick__active once (idle → busy); every rule consuming the goal also takes
    busy and gives back idle, reporting tick__done with a success out, tick__stuck with a failure out (a refusal the
    director detours, elsewhere, reports nothing); the task reports active as it takes a fetch, done and stuck with
    its ends. A stop (step 3c, v8 §13.2): the director's tick__cancel(D) — the member drops its goal (the cancel rules
    generated by metis.catalog.protocol_stub from its own rules and goal kinds). gating: program (design §14.6): every
    rule that sends the world a command (alf_host.COMMANDS) reads the member's grant, $tick__grant(D, motion), so a
    model cannot move without the body — no held command, no model ahead of the world (host gating stays the safety
    net). The bases stay today's for plain installs."""
    import re
    from alf_host import COMMANDS
    st = STATUS[spec]
    lines, out = text.split("\n"), []
    if spec != "task":
        g = SPECS[spec]["goal"]
        args = ", ".join("X%d" % i for i in range(GOAL_ARITY[g]))
    for l in lines:
        m = re.match(r"^(  (\w+) \[dyn\] : )(.*) -o (.*)\.(\s*%.*)?$", l)
        if m:
            pre, name, body, head = m.group(1), m.group(2), m.group(3), m.group(4)
            heads = {a.split("(")[0].strip() for a in head.split("*")}
            rep_ = ""
            if heads & set(st["success"]):
                rep_ = " * tick__done(%s)" % spec
            elif heads & set(st["failure"]):
                rep_ = " * tick__stuck(%s)" % spec
            if spec == "task":
                if re.search(r"(^|\* )fetch\(", body) and not rep_:   # an errand ended in the rule that takes it reports
                    rep_ = " * tick__active(task)"                     # its end only: active + stuck in one row would pop
                                                                        # the path and push it again (step 3c)
                l = "%s%s -o %s%s." % (pre, body, head, rep_)
            else:
                grant = " * $tick__grant(%s, motion)" % spec if COMMANDS.get(name) else ""
                if re.search(r"(^|\* )%s\(" % g, body):
                    l = "%s%s * busy%s -o %s * idle%s." % (pre, body, grant, head, rep_)
                elif grant:
                    l = "%s%s%s -o %s%s." % (pre, body, grant, head, rep_)
        out.append(l)
        if spec != "task" and l.startswith("namespace "):
            out += ["pred idle : %s.                     %% the tree: no goal taken" % spec,
                    "pred busy : %s.                     %% … a goal taken (reported active once)" % spec]
        if spec != "task" and l.strip() == "stage act {":
            out += ["  %% I take my goal.", "  begin [dyn] : $%s(%s) * idle -o busy * tick__active(%s)." % (g, args, spec)]
    t = "\n".join(out)
    # a stop (step 3c): the cancel rules, generated from the member's own rules and its goal kinds, beside begin
    cancels = protocol_stub.cancel_rules(t, spec, [SPECS[spec]["goal"]], ends=st["success"] + st["failure"] if spec == "task" else (),
                                         decls=open(os.path.join(os.path.dirname(HERE), "domains", "hier", "iface", "alfworld.llp")).read())
    at = "  begin [dyn]" if spec != "task" else "stage act {"
    lines = t.split("\n")
    i = next(k for k, l in enumerate(lines) if l.startswith(at))
    return "\n".join(lines[:i + 1] + cancels + lines[i + 1:])


# each member's own cases (metis.catalog.stub: the member alone, its interface closed with facts), in roles;
# the tree variant fires its begin rule first and reports itself
def _cases(spec, tree):
    T = lambda *a: list(a) if tree else []
    B = ["begin"] if tree and spec != "task" else []
    one = lambda name, world, deliver, fired, out, status: {name: {"case": "%s: %s" % (spec, name.replace("_", " ")), "boundaries": [
        dict({"world": world} if world else {}, deliver=deliver, **({"grant": ["motion"]} if spec != "task" else {}),
             expect={"out": out, "status": status, "fired": B + fired})]}}
    stop = _stop_cases(spec) if tree else {}
    if spec == "nav":
        return dict(stop, **one("goes_there", ["at(lhere)", "recat(dest, ldest)"], ["goto(dest)"], ["go"],
                        ["reached(dest)"] + T("tick__active(nav)", "tick__done(nav)"), "success"),
                    **one("is_there", ["at(ldest)", "recat(dest, ldest)"], ["goto(dest)"], ["here"],
                          ["reached(dest)"] + T("tick__active(nav)", "tick__done(nav)"), "success"))
    if spec == "access":
        return dict(one("opens_it", ["at(ldest)", "recat(dest, ldest)", "openable(dest)", "closed(dest)"], ["open(dest)"], ["open_closed"],
                        ["accessible(dest)"] + T("tick__active(access)", "tick__done(access)"), "success"),
                    **one("is_elsewhere", ["at(lhere)", "recat(dest, ldest)"], ["open(dest)"], ["not_here"],
                          ["elsewhere(dest)"] + T("tick__active(access)"), "running"))
    if spec == "grasp":
        return dict(one("takes_it", ["at(l1)", "recat(p1, l1)", "notopenable(p1)", "inrecep(target, p1)", "objat(target, l1)", "handsfree"],
                        ["take(target)"], ["take_plain"], ["taken(target)"] + T("tick__active(grasp)", "tick__done(grasp)"), "success"),
                    **one("hands_full", ["at(l1)", "objat(target, l1)", "holding"], ["take(target)"], ["hands_full"],
                          ["refused_take(target)"] + T("tick__active(grasp)", "tick__stuck(grasp)"), "failure"))
    if spec == "place":
        return dict(one("puts_it", ["at(ldest)", "recat(dest, ldest)", "notopenable(dest)", "holds(target)", "holding"],
                        ["put(target, dest)"], ["put_plain"], ["placed(target, dest)"] + T("tick__active(place)", "tick__done(place)"), "success"),
                    **one("hands_empty", ["handsfree"], ["put(target, dest)"], ["empty_handed"],
                          ["refused_put(dest)"] + T("tick__active(place)", "tick__stuck(place)"), "failure"))
    if spec == "task":
        # the task's weight port `look` (the map's belief, the host's) bound to a constant per case (the stub's
        # `ports`, metispy 7579dac): the case author's belief, what the host would bind
        cs = dict(stop, **one("already_there", ["inrecep(target, dest)"], ["fetch(target, dest)"], ["already"],
                              ["done"] + T("tick__done(task)"), "success"),
                  # the level port's atom present (spec16 step 4): the host's fetch_risk, read by no rule — the fetch
                  # goes as it does without it (the target seen, the hand empty: the host's reading, alf-tasks)
                  **one("level_present", ["inrecep(target, p1)", "fetch_risk(mid)", "seen(target)", "handsfree"], ["fetch(target, dest)"],
                        ["fetch", "go_for"], ["goto(p1)"] + T("tick__active(task)"), "running"),
                  # a fetch while the hand holds another thing (alf-tasks step 3): it goes down where the robot stands first
                  **one("hands_full_first", ["inrecep(target, p1)", "seen(target)", "holds(other)"], ["fetch(target, dest)"],
                        ["free_hands"], ["put(other, p0)"], "running"),
                  **one("wrong_destination", ["inrecep(target, p2)"], ["fetch(target, p1)"], ["not_dest"],
                        ["wrong_dest(p1)"] + T("tick__stuck(task)"), "failure"))
        return {k: dict(c, ports={"look": 1.0}) for k, c in cs.items()}
    return {}


def _stop_cases(spec):
    """A stop (step 3c, v8 §13.2): the director's tick__cancel(D) taken in — the member drops its goal (its generated
    cancel rules) and takes its next one as from idle; a cancel with nothing left to drop (the race: its done and the
    stop in one director beat) is absorbed and the next goal stands."""
    if spec == "nav":
        return {"cancelled_mid_goal": {"case": "nav: a stop while it is on its goal", "boundaries": [
                    {"deliver": ["goto(dest)"], "grant": ["motion"], "expect": {"out": ["tick__active(nav)"], "status": "running", "fired": ["begin"]}},
                    {"deliver": ["tick__cancel(nav)"], "expect": {"out": [], "status": "running", "fired": ["cancel_goto"]}},
                    {"deliver": ["goto(dest)"], "expect": {"out": ["tick__active(nav)"], "status": "running", "fired": ["begin"]}}]},
                "cancel_after_done": {"case": "nav: a cancel with nothing left to drop", "boundaries": [
                    {"deliver": ["tick__cancel(nav)"], "expect": {"out": [], "status": "running", "fired": ["cancel_none"]}},
                    {"world": ["at(ldest)", "recat(dest, ldest)"], "deliver": ["goto(dest)"], "grant": ["motion"],
                     "expect": {"out": ["reached(dest)", "tick__active(nav)", "tick__done(nav)"], "status": "success", "fired": ["begin", "here"]}}]}}
    if spec == "task":
        go = {"world": ["inrecep(target, p1)"], "deliver": ["fetch(target, dest)"],
              "expect": {"out": ["goto(p1)", "tick__active(task)"], "status": "running", "fired": ["fetch", "go_for"]}}
        return {"stop_mid_fetch": {"case": "task: a stop mid-fetch", "boundaries": [
            go, {"deliver": ["tick__cancel(task)"], "expect": {"out": [], "status": "running", "fired": ["cancel_to_want"]}}, go]}}
    return {}


def director_cases():
    """The tree director's own cases (step 3c): a stop cancels the members on the path — the task, and nav once it
    reported itself active — and no idle one; a stuck task is off the path, so a stop after it cancels nobody."""
    # (the stub hands a boundary's outs over and retracts them; the Live's director keeps tick__goal, a level of its
    # own (I4): the second boundary puts it back as the Live's session holds it)
    return {"stop_cancels_the_path": {"case": "director: a stop cancels the path, not the idle", "boundaries": [
        {"deliver": ["tick__active(nav)"], "expect": {"out": ["tick__goal(nav)"], "fired": ["path_push"]}},
        {"lines": ["+tick__goal(nav) 1"], "deliver": ["tick__stop"], "expect": {"out": ["tick__cancel(nav)", "tick__cancel(task)"]}}]},
            "stop_after_stuck": {"case": "director: a stop after the task is stuck cancels nobody", "boundaries": [
                {"deliver": ["tick__stuck(task)"], "expect": {"out": [], "fired": ["path_stuck"]}},
                {"deliver": ["tick__stop"], "expect": {"out": []}}]}}


def write_cases(pkg, spec, tree=False):
    """SPEC's cases into PKG/cases/ (one YAML file a case)."""
    import yaml
    d = os.path.join(pkg, "cases")
    os.makedirs(d, exist_ok=True)
    cs = _cases(spec, tree)
    if tree and spec != "task":                                   # gating: program — a boundary granting motion delivers
        for c in cs.values():                                     # the director's grant too, the in-copy its rules read
            for b in c["boundaries"]:
                if "motion" in b.get("grant", ()):
                    b["deliver"] = b.get("deliver", []) + ["tick__grant(%s, motion)" % spec]
    for name, c in cs.items():
        with open(os.path.join(d, name + ".yaml"), "w") as f:
            yaml.safe_dump(c, f, sort_keys=False, default_flow_style=None, width=200)


# the task's level port, live (spec16 s-b12d90f2 step 4; metis-lang spec/16 §4): the host runs the one-tick instrument
# once a tick over the task's world model (domains/hier/task/eval/world_rules.llp, copied into the installed package)
# from the task's session as it stands, the map's belief bound to look and where, and asserts fetch_risk(L) — the
# fetch's failure risk within 17 events. The task reads it (world-private); no rule of today's task does anything
# with it (go_for unchanged: the decision on a level is belief-levels' ruling).
TASK_INSTRUMENT = {
    "beliefs": {"truly": {"port": "where", "lone": "R"}},     # lone: the target may be bound to no place role
    "evaluate": {"fetch": {"reach": "done", "within": 17, "model": "eval/world.llp"}},
    "levels": {"fetch_risk": {"from": {"evaluate": "fetch"}, "at": [0.5, 0.9], "names": ["high", "mid", "low"]}},
}


def instrument_fields():
    """The task's manifest lines for its level port (spec/16 §2, §4, §5): one flow line a field (metisc's interface
    reader takes `key: value` at column 0 and refuses block YAML)."""
    import yaml
    return "".join("%s: %s\n" % (k, yaml.safe_dump(v, sort_keys=False, default_flow_style=True, width=1000).strip())
                   for k, v in TASK_INSTRUMENT.items())


def write_world_model(pkg):
    """The task's world model into its installed package (eval/): the task as installed and the world rules."""
    import shutil
    d = os.path.join(pkg, "eval")
    os.makedirs(d, exist_ok=True)
    shutil.copy(os.path.join(os.path.dirname(HERE), "domains", "hier", "task", "eval", "world_rules.llp"), d)
    open(os.path.join(d, "world.llp"), "w").write(
        "% world — the installed task under the one-tick instrument, its level port's world model (generated by\n"
        "% world/gen_hier.py; the task's own world model: domains/hier/task/eval/world.llp).\n"
        'catalog task_world 1.\ninclude "../task.llp".\ninclude "world_rules.llp".\n')


def manifest_fields(spec, tree=False):
    """SPEC's manifest lines (metis-lang spec/15 §2.1): shared {pred: in|out|resource|world-private} and status
    {success, failure}. The world readings are world-private: each session reads them through its own binding
    (a specialist the one it was woken with, the planner the map's live one)."""
    sp = SPECS[spec]
    shared = {p: "world-private" for p in sp["dyn"]}
    shared[sp["goal"]] = "in"
    shared.update({p: "in" for p in sp.get("takes", ())})
    shared.update({p: "out" for p in sp["out"]})
    if tree:
        shared.update({p: "out" for p in REPORTS[spec]})
        shared["tick__cancel"] = "in"                             # the director's on a stop (step 3c): the task's too
        if spec != "task":
            shared["tick__grant"] = "in"                          # gating: program (§14.6): the grant an in-copy its rules read
    if spec != "task":
        shared["motion"] = "resource"
    return "shared: {%s}\nstatus: {success: [%s], failure: [%s]}\n%s" % (
        ", ".join("%s: %s" % kv for kv in shared.items()), ", ".join(STATUS[spec]["success"]), ", ".join(STATUS[spec]["failure"]),
        "gating: program\n" if tree and spec != "task" else "")


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
            + ["notdest(%s)" % r for r in semantic_map.place_roles(k) if r != "dest"]
            # the casts into `thing` (step 3b: grasp's refused_take is an object, place's refused_put a receptacle,
            # the task's stuck a thing; one signature each, no subtyping)
            + ["thing_of(%s, %s)" % (o, o) for o in semantic_map.OBJECT_ROLES]
            + ["place_of(%s, %s)" % (r, r) for r in semantic_map.place_roles(k)])


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
    # what this task cannot do (alf-tasks step 2): the kinds of ALFWorld's vocabulary this room lacks (view mode: its
    # places only — a thing not seen yet is searched for), and the chores of the other task families
    vocab = vocabulary()
    if spec == "task" and "alfkind" in vocab:
        # a kind it lacks is FETCH's own value (the model spells the word it heard, never another thing in its place);
        # the host says it is not here (AlfHost.intent_atom → nothere). View mode: a thing not seen yet is searched for
        present = set(d.get("kinds") or []) | {re.sub(r"\d+$", "", h) for h in list(d["places"]) + list(d["things"])}
        absent = [k for k in vocab["alfkind"] if k not in present]
        have["receptacle"] += [k for k in absent if k in RECEPTACLE_KINDS]
        if not d.get("view"):
            have["object"] += [k for k in absent if k not in RECEPTACLE_KINDS]
        elif d["task"].get("room"):                                  # a room in view mode: any kind that can be carried, not seen yet
            seen = {re.sub(r"_t$", "", d["types"].get(o, "")) for o, th in d["things"].items() if not th.get("wanted")}
            carried = {re.sub(r"_t$", "", t) for t in compat_all()}
            have["object"] += [k for k in vocab["alfkind"] if k in carried and k not in seen and k not in have["object"]]
        have["chore"] = vocab["chore"]
    if d.get("view") and spec == "task":   # view mode: the task's kind stays a value ("a tomato": any tomato), seen or not
        kinds = {semantic_map.want_handle(t) for t in d["task"]["targets"]}
        have["object"] = sorted(set(have["object"]) | kinds, key=num)
    for slot in c.get("slots") or {}:      # an enum value upper-cased, as the mapper looks it up; the atom's constant
        c["slots"][slot] = {"enum": [v.upper() for v in have[slot]]}
        c["values"][slot] = {v.upper(): v for v in have[slot]}

    # the room's things in the prompt too: the grammar holds the model to them, and a model that
    # has not read a name (bread, a spatula) answers UNKNOWN rather than an enum value it never saw
    said = {"receptacle": "The receptacles here", "object": "The objects this task moves" if spec == "task"
            else "The objects here that can be picked up",
            "chore": "The chores this task cannot do (NOTASK)"}
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


_VOCAB = {}


def vocabulary():
    """The task's own vocabulary (task_domain.llp's enumerated types: alfkind, chore, risk, …): {type: [constants]}."""
    if not _VOCAB:
        import re
        text = open(os.path.join(os.path.dirname(HERE), "domains", "hier", "task_domain.llp")).read()
        _VOCAB.update({n: body.split() for n, body in re.findall(r"^type\s+(\w+)\s*\{([^}]*)\}", text, re.M)})
    return _VOCAB


def build_map(path, info, mirror, k=K, view=False, room=False):
    """The hierarchy's semantic map at PATH from the mirror's game as it is now (its static facts and its
    reading) and the task (task_goal); view: the robot sees only what stands before it (step 3). room (alf-tasks
    step 1): no task — the episode's goal is not the agent's; the person's goal binds the roles (project)."""
    targets, dests = ([], []) if room else task_goal(info)
    m = semantic_map.SemanticMap.build(path, mirror.static, mirror.dyn, targets, dests, k, view=view, room=room)
    if view and room:                  # a kind the room's facts never place (none of it here): ALFRED's own compatibility
        d = m.load()                   # (world/cancontain.json, every game's union), so a search for it looks where it could be
        for ot, rts in compat_all().items():
            d["compat"].setdefault(ot, rts)
        d["presence_prior"] = presence_prior(info.get("game") or "")
        d["place_rate"] = place_rate()                # where each kind usually starts (nina's F2; map-queries step 1)
        m.save()
    return m


def presence_prior(game):
    """P(a kind is in this room) by ALFRED's frequency in rooms of its type (world/presence.json: the fraction of the
    type's scenes whose objects include it), add-half smoothed: never 0, never 1. {kind type: p}."""
    import re
    m = re.search(r"-(\d+)(?:/|$)", str(game).rstrip("/").replace("/game.tw-pddl", ""))
    n = int(m.group(1)) if m else 0
    room = next((r for a, b, r in ((1, 30, "kitchen"), (201, 230, "living room"), (301, 330, "bedroom"), (401, 430, "bathroom"))
                 if a <= n <= b), None)
    t = json.load(open(os.path.join(HERE, "presence.json")))
    if room is None:
        return {}
    k = t["scenes"][room]
    return {kind: round((p * k + 0.5) / (k + 1), 4) for kind, p in t["presence"][room].items()} | \
        {kind: round(0.5 / (k + 1), 4) for kind in compat_all() if kind not in t["presence"][room]}


def place_rate():
    """Where a kind usually IS, per place (map-queries step 1, the architect's ruling): for each object type, the games
    whose initial state starts it in or on a receptacle type, per receptacle of that type across the scenes
    (world/starts.json, world/gen_tables.py). The room map's prior is this rate times compatibility, normalized over
    the room's places. {object type: {receptacle type: rate}}."""
    t = json.load(open(os.path.join(HERE, "starts.json")))
    n = t["receptacles"]
    return {o: {r: round(c / n[r], 4) for r, c in rs.items() if n.get(r)} for o, rs in t["starts"].items()}


def compat_all():
    """ALFRED's receptacle compatibility, no room's: {object type: [receptacle types]} (world/cancontain.json)."""
    return json.load(open(os.path.join(HERE, "cancontain.json")))["cancontain"]


# ── the director (alf-hierarchy step 3): the instance's facts from the specialists' declared ports ──
DIRECTOR_OUT = ("wake", "sleep", "forward", "ask", "ended", "tick__grant", "tick__revoke")   # the last two: the tree director's (the tick)
ENDS = ("done", "stuck", "wrong_dest", "wrong_object", "nothing", "cannot", "misfit", "gave_up")   # nothing … misfit: what the task cannot do (alf-tasks
# step 2); gave_up: a search's answer, "probably no T here" (map-queries step 1): it ends without an ask, as done does


FINISHED = ("done", "gave_up")      # the ends that are answers: no ask (done: opus, the demo; gave_up: map-queries step 1)


def director_facts():
    """handles/2 and the rest, derived from SPECS — what the SDK's generator will read from the
    packages' declared ports (director decision 1): a specialist handles its goal kind; the planner
    its goal and the results; a result is what a specialist puts out that the planner takes; the
    ends end; elsewhere detours to the navigator's goal and escalates as refused."""
    kinds = sorted({sp["goal"] for sp in SPECS.values()} | {k for sp in SPECS.values() for k in sp["out"]}
                   | {k for sp in SPECS.values() for k in sp.get("takes", ())})
    facts = ["specialist(%s)" % d for d in SPECS if d != "task"] + ["planner(task)"]
    for d, sp in SPECS.items():
        facts.append("handles(%s, %s)" % (d, sp["goal"]))
        for k in sp.get("takes", ()):
            facts.append("handles(%s, %s)" % (d, k))
    handled = {k for d, sp in SPECS.items() for k in (sp["goal"],) + tuple(sp.get("takes", ()))}
    facts += ["result(%s)" % k for k in SPECS["task"]["takes"] if not k.startswith("refused")]
    facts += ["end(%s)" % k for k in ENDS if k not in FINISHED] + ["finished(%s)" % k for k in FINISHED]   # these end without an ask
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


def generate_director_package(root, game_dir, flat_pkg, commands_log, domain_rel="../../director_domain.llp", tree=False, room=False, map_path=None, view=False):
    """The director as an INSTALLED package (alf-hierarchy step 3, the agent): domains/hier/director/
    — the instance's facts and start over the lifted base, a manifest, a host shim, and game.json
    naming the game, the flat package (the host's mirror) and the shared commands log."""
    kinds, facts = director_facts()
    pkg = os.path.join(root, "domains", "hier", "director")
    os.makedirs(pkg, exist_ok=True)
    lines = ["% director — the director over the ALFWorld hierarchy, installed for the agent (generated by world/gen_hier.py).",
             "catalog director 1.",
             'provenance text "generated: the director over nav/access/grasp/place/task for %s" "2026-10-22".' % os.path.basename(os.path.dirname(game_dir)),
             'include "%s".' % domain_rel] + (
            # the tree (specialist-tree step 3b): metispy's generic base and its bridge to the routing director
            ['include "iface/director_tree_domain.llp".', 'include "iface/director_tree_wake.llp".']
            if tree else []) + [
             "type domain {%s}." % " ".join(SPECS), "type kind {%s}." % " ".join(kinds), ""]
    lines += [f + "." for f in facts] + [""]
    if tree:                                                # the composition's resource, the hysteresis (brief §9 rule 4)
        lines += ["type resource {%s}." % " ".join(RESOURCES)] + [f + "." for f in hysteresis()] + [""]
    lines += ["#init %s 1" % a for a in director_start(tree)] + ["#steps 6", "#seeds 1"]
    open(os.path.join(pkg, "director.llp"), "w").write("\n".join(lines) + "\n")
    json.dump({**({"room": True} if room else {}), **({"tree": True} if tree else {}), **({"view": True} if view else {}),
               "map": os.path.abspath(map_path or os.path.join(root, "domains", "hier", ".map.json")),
               "game": os.path.join(game_dir, "game.tw-pddl"), "game_dir": game_dir, "flat": flat_pkg, "root": root,
               "commands_log": commands_log, "out": list(DIRECTOR_OUT), "kinds": kinds},
              open(os.path.join(pkg, "game.json"), "w"), indent=1)
    open(os.path.join(pkg, "domain.yaml"), "w").write(
        "# director — activation from context as a domain (generated by world/gen_hier.py); its host re-instances the specialists.\n"
        "program: director.llp\nhost: director_host.py:make\nclock: {beats: 1}\nrecords: records/\n"
        "display: the director\nline: \"the director: who is woken for what arrives\"\nvoice: line\n"
        + (DIRECTOR_FIELDS if tree else ""))
    shim = open(os.path.join(HERE, "package_host.py")).read().replace("__WORLD__", HERE).replace('"alf_host"', '"director_host"').replace("AlfHost", "DirectorHost")
    open(os.path.join(pkg, "director_host.py"), "w").write(shim)
    if tree:                                                       # its own cases (step 3c: the stop)
        import yaml
        os.makedirs(os.path.join(pkg, "cases"), exist_ok=True)
        for name, c in director_cases().items():
            with open(os.path.join(pkg, "cases", name + ".yaml"), "w") as f:
                yaml.safe_dump(c, f, sort_keys=False, default_flow_style=None, width=200)
    return pkg


def install(game_dir, root, person=True, k=K, view=False, tree=False, room=False, name=None):
    """A game installed for the agent under ROOT: domains/hier/_flat (the mirror's package), the
    director, the semantic map (domains/hier/.map.json: the room as data, bound to the roles for the
    game's own task until a goal re-projects it), the task (continues; `person`: no seeded fetch — the
    FETCH the person types is its goal; False seeds the driver's fetch), and every specialist — each the
    committed instance over the role vocabulary (k: the capacity's places; 8 is the committed
    capacity.llp), no room in its source: the director's forward delivers it its goal on the live
    session. view: the map sees only what the robot sees (semantic-map step 3; default every fact).
    Every host appends its commands to domains/hier/.commands.jsonl, the shared world state.
    tree (specialist-tree s-404d001f steps 2-3b, the tick): the director over metispy's iface/ (METIS_HOME)
    director_tree_domain.llp + director_tree_wake.llp beside the routing base (the path, the
    motion's grants) and every specialist's extensions/tick.llp declaring the `motion` token it is granted.
    room (alf-tasks s-e9cc8fae step 1): the game is the room's state only — no task in the map (the person's goal
    binds the roles), every host plays it without an episode end (alf_gym's room), no driver's seed.
    name (rooms s-b51a2e80): one of the rooms of a World (domains/hier/.world.json), installed over the tree in place:
    the programs are the same, the room's data rewritten, its own map and commands log kept across a return (it stands
    as it was left), and it becomes the World's active map.
    → {name: package dir}."""
    if room and not person:
        raise ValueError("a room has no task of its own to seed: room=True needs person=True")
    hier = os.path.join(root, "domains", "hier")
    os.makedirs(hier, exist_ok=True)
    import shutil
    bases = os.path.join(os.path.dirname(HERE), "domains")        # the lifted bases the instances include, copied when the root is not this repo
    for src, dst in [(os.path.join(bases, b), os.path.join(root, "domains", b))
                     for b in ("director_domain.llp",)] + \
                    [(os.path.join(bases, "hier", sp + "_domain.llp"), os.path.join(hier, sp + "_domain.llp")) for sp in SPECS] + \
                    [(os.path.join(bases, "hier", "iface", f), os.path.join(hier, "iface", f)) for f in ("alfworld.llp", "alfworld.yaml")]:
        if os.path.abspath(src) != os.path.abspath(dst) and not os.path.exists(dst):
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            shutil.copy(src, dst)
    cap = os.path.join(hier, "capacity.llp")
    if not os.path.exists(cap) or open(cap).read() != capacity(k):
        open(cap, "w").write(capacity(k))
    log = os.path.join(hier, ".commands.%s.jsonl" % name if name else ".commands.jsonl")
    map_path = os.path.join(hier, ".map.%s.json" % name if name else ".map.json")
    known = os.path.join(hier, ".room.%s.json" % name) if name else None   # a room's facts do not change: read once
    fresh = not (name and os.path.exists(map_path) and os.path.exists(known))
    if fresh:
        flat, _, _ = gen_instance.generate(game_dir, os.path.join(hier, "_flat"))
        flat_pkg = os.path.dirname(flat)
        if room:                                                   # the mirror shares the hosts' world process (one per log): a room's too
            gj = os.path.join(flat_pkg, "game.json")
            json.dump(dict(json.load(open(gj)), room=True), open(gj, "w"), indent=1)
        open(log, "w").close()
        from alf_host import AlfHost
        mirror = AlfHost(flat_pkg)
        try:
            info = dict(json.load(open(os.path.join(flat_pkg, "game.json"))), static=sorted(mirror.static), task_type=mirror.task, params=mirror.params)
            smap = build_map(map_path, info, mirror, k, view=view, room=room)
            reading = mirror.reading()
        finally:
            mirror.gym.close()
        smap.project(*(() if room else args_of(seed(info)[0])))    # the game's own task until a goal says otherwise (a room: none)
        if known:
            json.dump({"flat": flat_pkg, "info": info}, open(known, "w"))
    else:                                                          # a room returned to stands as it was left
        d = json.load(open(known))
        flat_pkg, info, reading = d["flat"], d["info"], {}
        smap = semantic_map.SemanticMap(map_path)
    world = None
    if name:
        from semantic_world.world import World
        world = os.path.join(hier, ".world.json")
        w = World(path=world, make=semantic_map.SemanticMap)
        w.add_map(name, map_path)
        w.enter(name)
    out = {"_flat": flat_pkg, "director": generate_director_package(
        root, game_dir, flat_pkg, log, tree=tree, room=room, map_path=world or map_path, view=view)}
    for spec in SPECS:
        # the task's goal: a person's FETCH arrives by intent (person=True: no seed), else the driver's seed
        inits = [smap.intent_atom(seed(info)[0])] if spec == "task" and not person else []
        path = generate(game_dir, hier, spec, 0, info, smap, reading, inits, [], intents=(spec == "task"), continues=True, fixed=True,
                        commands_log=log, places=k, tree=tree, room=room, map_path=world)
        out[spec] = os.path.dirname(path)
        if tree:                                                   # the protocol: the specialist reads its grant from it
            prog = os.path.join(out[spec], spec + ".llp")
            t = open(prog).read()
            inc = 'include "../capacity.llp".\n'
            t = t.replace(inc, inc + 'include "iface/protocol_domain.llp".\ninclude "../tick_types.llp".\n', 1)
            if spec != "task":                                     # the inversion: a member starts with no goal taken
                t = t.rstrip("\n") + "\n#init idle 1\n"
            open(prog, "w").write(t)
            # … and its base the tree variant (the repo's bases stay today's: a tree root is never the repo)
            bp = os.path.join(hier, spec + "_domain.llp")
            if os.path.abspath(bp) == os.path.abspath(os.path.join(os.path.dirname(HERE), "domains", "hier", spec + "_domain.llp")):
                raise ValueError("a tree install never writes into the repo's own domains/")
            open(bp, "w").write(tree_base(spec, open(os.path.join(os.path.dirname(HERE), "domains", "hier", spec + "_domain.llp")).read()))
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
        out += ["free(%s)" % r for r in RESOURCES] + ["issue(%s,t0)" % r for r in RESOURCES] + ["serving(%s,t0)" % r for r in RESOURCES] + ["path(task)", "tick__goal(task)"] + ["offpath(%s)" % d for d in sp]
        out += ["nowant(%s)" % d for d in sp] + ["nolate(%s)" % d for d in sp] + ["nocommit(%s)" % d for d in sp] + ["age_of(%s,a0)" % d for d in SPECS]
    return out


RESOURCES = ("motion",)            # the body: one specialist moves or handles at a time
# the tree director's side of the protocol and its resource (spec/15 §2.3: I5's count invariant over free/holder)
DIRECTOR_FIELDS = ("shared: {tick__status: in, tick__active: in, tick__done: in, tick__stuck: in, tick__committed: in, tick__yield: in, tick__grant: out, "
                   "tick__goal: out, tick__revoke: out, tick__cancel: out, tick__stop: in}\nresources: {motion: {count: 1, free: free, held_by: [holder]}}\n")


def composition():
    """The composition file (spec/15 §2.3, domains/hier/composition.yaml): the capacity, the protocol, the
    specialists in the tick's order, the direct domain, the world's ports (out: what the host writes into the
    sessions — the world-private readings and the person's fetch; in: the goals whose specialists' commands it
    executes). Flow maps and lists, one key a line, no anchors."""
    order = ["task"] + [d for d in SPECS if d != "task"]
    out = sorted({p for sp in SPECS.values() for p in sp["dyn"]} | {"fetch"})
    cmds = [SPECS[d]["goal"] for d in order if d != "task"]
    return ("# composition — the ALFWorld hierarchy as one package (specialist-tree s-404d001f; generated by world/gen_hier.py)\n"
            "capacity: capacity.llp\nprotocol: iface/protocol_domain.llp\ninterfaces: [iface/alfworld.llp]\nspecialists: [%s]\ndirect: director\n"
            "world: {out: [%s], in: [%s]}\n" % (", ".join(order), ", ".join(out + ["tick__stop"]), ", ".join(cmds)))   # tick__stop: the agent's on a stop (3c)
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
             commands_log=None, places=None, tree=False, room=False, map_path=None):
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
               "map": os.path.abspath(map_path or smap.path), "commands_log": commands_log, **({"room": True} if room else {})},
              open(os.path.join(pkg, "game.json"), "w"), indent=1)
    open(os.path.join(pkg, "domain.yaml"), "w").write(
        "# %s — the %s specialist on an ALFWorld game over the role vocabulary (generated by world/gen_hier.py).\n"
        "program: %s.llp\nhost: alf_host.py:make\nclock: {beats: 1}\nrecords: records/\n"
        "display: ALFWorld %s (%s)\nline: \"%s\"\nvoice: own\n" % (spec, spec, spec, spec, iid, spec))
    open(os.path.join(pkg, "domain.yaml"), "a").write(manifest_fields(spec, tree))
    if fixed:
        write_cases(pkg, spec, tree)
    if fixed and spec == "task":                                       # the level port, live (spec16 step 4)
        open(os.path.join(pkg, "domain.yaml"), "a").write(instrument_fields())
        write_world_model(pkg)
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
