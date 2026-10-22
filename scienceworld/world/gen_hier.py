"""gen_hier.py — the hand hierarchy's instances (world-scienceworld step 2): one specialist, one
activation, one package over the lifted base (domains/hier/<spec>_domain.llp): the types it sees,
its static facts (the house's routes, the circuit's parts, where the task's text puts the thing),
the world as it is now (the perceived atoms of its predicates), the goal or the results, the tokens.

Instance knowledge, declared: the HOUSE graph (walked once with the gym, a constant here — what
the loop's exploration must discover), the circuit's parts named from the perceived names
(a wire's two terminals, a battery's poles, a bulb's poles, the thing's own terminals: the
referents the game accepts), the task's text."""
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import perceive  # noqa: E402

# the house, walked through its doors (tests/test_world.py checks it against a walk)
HOUSE = {
    "art_studio": ["hallway"], "bathroom": ["kitchen"], "bedroom": ["hallway"], "foundry": ["outside"],
    "greenhouse": ["hallway", "outside"], "hallway": ["art_studio", "bedroom", "greenhouse", "kitchen", "living_room", "workshop"],
    "kitchen": ["bathroom", "hallway", "outside"], "living_room": ["hallway"], "outside": ["foundry", "greenhouse", "kitchen"],
    "workshop": ["hallway"],
}
ROOMS = sorted(HOUSE)

# one specialist = the types it declares, the world predicates it sees, its goal kind, its results
SPECS = {
    "nav": {"types": ("room", "doorstate"), "dyn": ("here", "door"), "goal": "goto", "out": ("reached",), "takes": ()},
    "grasp": {"types": ("thing", "room"), "dyn": ("here", "in", "holds", "focused"), "goal": "get", "out": ("got", "elsewhere"), "takes": ()},
    "circuit": {"types": ("thing", "part", "term", "onoff", "said_kind"), "dyn": ("holds", "state"), "goal": "test", "out": ("conducts", "insulates"), "takes": ()},
    "verdict": {"types": ("thing",), "dyn": (), "goal": "put", "out": ("placed",), "takes": ()},
    "task": {"types": ("kind", "thing", "room"), "dyn": ("task", "where"), "goal": "task", "out": ("goto", "get", "test", "put", "done", "stuck"),
             "takes": ("reached", "got", "conducts", "insulates", "placed", "elsewhere", "refused")},
}
HANDLES = {"goto": "nav", "get": "grasp", "test": "circuit", "put": "verdict"}      # the manual switch (step 2)
ENDS = ("done", "stuck")


def routes():
    """next(L, G, R): from L, to reach G, step into R — BFS over the house."""
    out = []
    for g in ROOMS:
        # BFS from g outward gives, for every L, the neighbour on L's shortest path to g
        prev = {g: None}
        todo = [g]
        while todo:
            x = todo.pop(0)
            for y in HOUSE[x]:
                if y not in prev:
                    prev[y] = x
                    todo.append(y)
        for l, nxt in prev.items():
            if nxt is not None:
                out.append("next(%s, %s, %s)" % (l, g, nxt))
    return out


def args_of(atom):
    return [x.strip() for x in atom[atom.index("(") + 1:-1].split(",")] if "(" in atom else []


def parts_of(names):
    """The circuit's parts among the perceived names: wires, bulbs, the battery; their terminals as the game names them."""
    wires = sorted(n for n in names if n.endswith("_wire"))
    bulbs = sorted(n for n in names if n.endswith("light_bulb"))
    battery = [n for n in names if n == "battery"]
    facts, terms = [], []
    for b in battery:
        facts += ["battery(%s)" % b, "anode(%s, %s_anode)" % (b, b), "cathode(%s, %s_cathode)" % (b, b)]
        terms += ["%s_anode" % b, "%s_cathode" % b]
    for w in wires:
        facts += ["wire(%s)" % w, "term1(%s, %s_terminal_1)" % (w, w), "term2(%s, %s_terminal_2)" % (w, w)]
        terms += ["%s_terminal_1" % w, "%s_terminal_2" % w]
    for l in bulbs:
        facts += ["bulb(%s)" % l, "anode(%s, anode_in_%s)" % (l, l), "cathode(%s, cathode_in_%s)" % (l, l)]
        terms += ["anode_in_%s" % l, "cathode_in_%s" % l]
    return {"parts": battery + wires + bulbs, "terms": terms, "facts": facts}


def task_of(task_atoms):
    t = next((a for a in task_atoms if a.startswith("task(conductivity")), None)
    w = next((a for a in task_atoms if a.startswith("where(")), None)
    if not t:
        return None
    kind, o, y, n = args_of(t)
    return {"thing": o, "yes": y, "no": n, "where": args_of(w)[1] if w else None}


def generate(out_dir, spec, k, task_atoms, reading, init, replay, names, domain_rel=None, commands_log=None, task_json=None):
    """One activation of SPEC as a package in OUT_DIR/<spec>-<k>: the lifted base included, the
    types, the static facts, the world's atoms of its predicates as #init, the goal/results/tokens."""
    sp = SPECS[spec]
    t = task_of(task_atoms)
    o = t["thing"] if t else "thing"
    circuit = parts_of(names) if spec == "circuit" else None
    types = {"room": ROOMS, "doorstate": ["open", "closed"], "onoff": ["on", "off"], "kind": ["conductivity"],
             "said_kind": sorted({k for _, k in perceive.MESSAGES} | {"other"}),
             "thing": sorted({o} | ({t["yes"], t["no"]} if t and spec in ("task", "verdict") else set())),
             "part": circuit["parts"] if circuit else [], "term": (circuit["terms"] + ["%s_terminal_1" % o, "%s_terminal_2" % o]) if circuit else []}
    members = {m for kind in sp["types"] for m in types[kind]}
    facts = []
    if spec == "nav":
        facts += routes() + ["same(%s, %s)" % (r, r) for r in ROOMS]
    if spec == "grasp" and t and t["where"]:
        facts += ["where(%s, %s)" % (o, t["where"])]
    if spec == "circuit":
        facts += circuit["facts"] + ["oterm1(%s, %s_terminal_1)" % (o, o), "oterm2(%s, %s_terminal_2)" % (o, o)]
    name = "%s_%d" % (spec, k)
    lines = ["% " + name + " — activation " + str(k) + " of the " + spec + " specialist (generated by world/gen_hier.py) over the lifted " + spec + "_domain.llp.",
             "catalog " + name + " 1.",
             'provenance text "generated: ScienceWorld %s specialist, activation %d" "2026-10-23".' % (spec, k),
             'include "%s".' % (domain_rel or "../../hier/%s_domain.llp" % spec)]
    for kind in sp["types"]:
        lines.append("type %s {%s}." % (kind, " ".join(types[kind]) or "none"))
    lines += [""] + [f + "." for f in facts] + [""]
    seen = set()
    for a in sorted(reading):
        if a.split("(")[0] in sp["dyn"] and all(x in members for x in args_of(a)) and a not in seen:
            lines.append("#init %s 1" % a); seen.add(a)
    for a in init:
        if a not in seen:
            lines.append("#init %s 1" % a); seen.add(a)
    lines += ["#steps 16", "#seeds 1"]
    pkg = os.path.join(out_dir, "%s-%d" % (spec, k))
    os.makedirs(pkg, exist_ok=True)
    path = os.path.join(pkg, spec + ".llp")
    open(path, "w").write("\n".join(lines) + "\n")
    meta = dict(task_json or {}, replay=list(replay), commands_log=commands_log, spec=spec, out=list(sp["out"]), observe=list(sp["dyn"]))
    json.dump(meta, open(os.path.join(pkg, "task.json"), "w"), indent=1)
    open(os.path.join(pkg, "domain.yaml"), "w").write(
        "# %s — one activation of the %s specialist on a ScienceWorld variation (generated by world/gen_hier.py).\n"
        "program: %s.llp\nhost: sw_host.py:make\nclock: {beats: 1}\nrecords: records/\ndisplay: ScienceWorld %s\nline: \"%s\"\nvoice: own\n" % (name, spec, spec, spec, spec))
    shim = open(os.path.join(HERE, "package_host.py")).read().replace("__WORLD__", HERE)
    open(os.path.join(pkg, "sw_host.py"), "w").write(shim)
    return path


def vector(spec):
    """The specialist's size: rules and predicates in its base."""
    txt = open(os.path.join(os.path.dirname(HERE), "domains", "hier", spec + "_domain.llp")).read()
    rules = len(re.findall(r"^\s+\w+ \[dyn\] :", txt, re.M))
    preds = len(re.findall(r"^(?:pred|bwd) ", txt, re.M))
    return {"rules": rules, "preds": preds}
