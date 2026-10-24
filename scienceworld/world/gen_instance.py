"""gen_instance.py — a ScienceWorld task variation as a PACKAGE (world-scienceworld step 1):
`python world/gen_instance.py test-conductivity 0 [--out DIR]` writes
`domains/<task>_<n>/{<name>.llp, domain.yaml, intent.yaml, task.json, sw_host.py}`: the world's
names as types (the simulator's referents: a VOCABULARY, nothing of its hidden properties), the
perceived start and the task as `#init`, the card, the host shim. Declarations only, no rules: the
domain is what the loop extracts (step 3); step 2's hand hierarchy includes its rules beside it."""
import argparse, json, os, re, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from sw_gym import World  # noqa: E402
from perceive import MESSAGES  # noqa: E402
from families import package_name  # noqa: E402

CARD = open(os.path.join(HERE, "card.yaml")).read()
TEMPS = ["n%d" % t for t in range(0, 301, 1)] + ["m%d" % t for t in range(1, 51)]


# the perception's TYPES (world-scienceworld step 3, the loop's instance): one 500-name type made every
# binary predicate ground to hundreds of thousands of events (the policy driver's first rule over
# in(thing, thing) took 14 GB); the vocabulary is typed by what a name can be — a room, a place
# (a room or a container: what `in` puts things in), a terminal (what `connect` joins), a thing
PERCEPTION = ["% the perception (the text; never the simulator's hidden properties)",
              "pred here(room) : sw.", "pred door(room, doorstate) : sw.", "pred in(thing, place) : sw.", "pred state(thing, onoff) : sw.",
              "pred closed(place) : sw.", "pred open(place) : sw.", "pred reads(thing, temp) : sw.", "pred holds(thing) : sw.",
              "pred matter(thing, phase) : sw.", "pred measured(thing, temp) : sw.",
              "pred focused(thing) : sw.", "pred connected(term, term) : sw.", "pred task(kind, thing, place, place) : sw.", "pred where(thing, room) : sw.",
              "pred threshold(temp) : sw.", "pred said(said_kind) : sw."]
PRED_TYPES = {"here": ("room",), "door": ("room", "doorstate"), "in": ("thing", "place"), "state": ("thing", "onoff"), "closed": ("place",),
              "open": ("place",), "reads": ("thing", "temp"), "holds": ("thing",), "matter": ("thing", "phase"), "measured": ("thing", "temp"),
              "focused": ("thing",), "connected": ("term", "term"), "task": ("kind", "thing", "place", "place"), "where": ("thing", "room"),
              "threshold": ("temp",), "said": ("said_kind",)}
ROOMS = ["art_studio", "bathroom", "bedroom", "foundry", "greenhouse", "hallway", "kitchen", "living_room", "outside", "workshop", "sewer"]
PLACE = re.compile(r"(box|cup|jar|bowl|pot|bottle|glass|table|counter|shelf|cupboard|drawer|fridge|freezer|oven|stove|sink|bathtub|toilet|bed$|desk|chair|closet|fountain|pit|inventory|workbench|dresser|microwave|blast_furnace|nest|hive|flower_pot|container|bucket|pan$|tin|basket|rack|tray|tub|ground|wardrobe|cabinet|urn|vase|couch|jug|beaker|flask)")
TERM = re.compile(r"(terminal|^anode|^cathode)")


def typed_names(names, task_atoms=()):
    """The vocabulary by what a name can be: rooms, places (rooms and containers), terms, things."""
    names = sorted(n for n in names if n and re.match(r"^[a-z][a-z0-9_]*$", n))
    terms = sorted(n for n in names if TERM.search(n))
    things = sorted(n for n in names if n not in terms)
    boxes = set()
    for a in task_atoms:
        if a.startswith("task("):
            boxes |= set(a[5:-1].split(",")[2:4])
    places = sorted(set(ROOMS) | {n for n in things if PLACE.search(n)} | boxes)
    return {"room": ROOMS, "place": places, "term": terms, "thing": sorted(set(things) | boxes)}
COMMAND_PREDS = ["% the commands, one per intent",
                 "pred cmd_go(thing) : sw.", "pred cmd_open(thing) : sw.", "pred cmd_close(thing) : sw.", "pred cmd_take(thing) : sw.", "pred cmd_drop(thing) : sw.",
                 "pred cmd_focus(thing) : sw.", "pred cmd_connect(thing, thing) : sw.", "pred cmd_move(thing, thing) : sw.", "pred cmd_activate(thing) : sw.",
                 "pred cmd_deactivate(thing) : sw.", "pred cmd_use(thing, thing) : sw.", "pred cmd_examine(thing) : sw.",
                 "pred cmd_wait : sw.", "pred cmd_look : sw.", "pred cmd_unknown : sw."]
OUTCOMES = ["% the outcomes", "type act {go open close take drop focus connect move activate deactivate use examine wait look unknown}.",
            "pred done(act) : sw.", "pred refused(act) : sw.", "pred progress(act) : sw."]
FIXED_TYPES = ["type doorstate {open closed}.", "type onoff {on off}.", "type phase {solid liquid gas}.",
               "type said_kind {%s}." % " ".join(sorted({k for _, k in MESSAGES} | {"other"})),
               "type kind {conductivity melting boiling}.", "type temp {%s}." % " ".join(TEMPS)]
DYNAMIC_PREDS = ("here", "door", "in", "state", "closed", "open", "reads", "holds", "matter", "measured", "focused", "connected", "task", "where", "threshold", "said")


def perceived_types():
    """The types the perception's signatures name, in order of first naming (the instance's
    type lines and FIXED_TYPES complete them)."""
    out = []
    for line in PERCEPTION:
        m = re.match(r"pred \w+\(([^)]*)\)", line)
        for t in (m.group(1).split(",") if m else ()):
            if t.strip() not in out:
                out.append(t.strip())
    return out


def base_source(name="sw"):
    """The loop's EMPTY base (loop-policy): the perception's predicates over ScienceWorld's text, the
    namespace, an empty stage — no rule. The instance (generate with domain_rel) includes it and
    declares the types (the variation's vocabulary) and the start."""
    lines = ["% " + name + " — the loop's base over ScienceWorld's text (world-scienceworld step 3): the perception's",
             "% predicates, no rule. The loop writes the rules: from the transitions (explore), the surprises",
             "% (exploit), the hierarchy (refactor), each through the experimental gate.",
             "catalog " + name + " 1.",
             'provenance text "the loop\'s base: the empty domain over ScienceWorld\'s perceived facts" "2026-10-23".',
             "layers (dyn).", "stages (act).",
             # the types the instance declares (spec 12: the base compiles alone)
             "types (%s)." % " ".join(perceived_types()),
             "namespace sw produce (dyn)."] + PERCEPTION + ["stage act {", "}", ""]
    return "\n".join(lines)


def generate(task, variation, out_dir, simplification="easy", domain_rel=None):
    """A variation as a package. With DOMAIN_REL the instance INCLUDES that base (the loop's: its
    predicates and rules) and declares only the types and the start; else it is self-contained."""
    w = World()
    try:
        info = w.open(task, variation, simplification)
        atoms = list(info["init"]["atoms"]) + list(info["task_atoms"])
        names = set(info["names"]) | set(info["init"]["names"])
    finally:
        w.close()
    types = typed_names(names, info["task_atoms"])
    things = types["thing"]
    name = package_name(task, variation)
    kinds = sorted({k for _, k in MESSAGES} | {"other"})
    lines = ["% " + name + " — a ScienceWorld task variation as a package (generated by world/gen_instance.py):",
             "% the world's names as types (its referents: a vocabulary), the perceived start and the task as #init;",
             "% declarations only — the rules are the hierarchy's (step 2) or what the loop extracts (step 3).",
             "catalog " + name + " 1.",
             'provenance text "generated ScienceWorld %s variation %d (%s)" "2026-10-22".' % (task, variation, simplification)]
    type_lines = ["type %s {%s}." % (k, " ".join(types[k]) or "none") for k in ("room", "place", "term", "thing")]
    if domain_rel:
        lines += ['include "%s".' % domain_rel] + type_lines + FIXED_TYPES + [""]
    else:
        lines += ["layers (dyn).", "stages (act)."] + type_lines + FIXED_TYPES + ["namespace sw produce (dyn)."] + PERCEPTION + COMMAND_PREDS + OUTCOMES + [
            "stage act {", "  %% I can't do that here.", "  unknown [dyn] : cmd_unknown -o refused(unknown).", "}", ""]
    kept = 0
    fixed = {"doorstate": {"open", "closed"}, "onoff": {"on", "off"}, "phase": {"solid", "liquid", "gas"}, "kind": {"conductivity", "melting", "boiling"},
             "temp": set(TEMPS), "said_kind": set()}
    members = {k: set(v) for k, v in types.items()}
    members.update(fixed)
    for a in atoms:
        args = [x.strip() for x in a[a.index("(") + 1:-1].split(",")] if "(" in a else []
        pred = a.split("(")[0]
        kinds = PRED_TYPES.get(pred)
        if kinds and len(kinds) == len(args) and all(x in members[k] for x, k in zip(args, kinds)):
            lines.append("#init %s 1" % a); kept += 1
    lines += ["#steps 20", "#seeds 1"]
    pkg = os.path.join(out_dir, name)
    os.makedirs(pkg, exist_ok=True)
    open(os.path.join(pkg, name + ".llp"), "w").write("\n".join(lines) + "\n")
    json.dump({"task": task, "variation": variation, "simplification": simplification, "desc": info["desc"],
               "task_atoms": info["task_atoms"], "names": things, "types": {k: len(v) for k, v in types.items()}}, open(os.path.join(pkg, "task.json"), "w"), indent=1)
    open(os.path.join(pkg, "intent.yaml"), "w").write(CARD)
    open(os.path.join(pkg, "domain.yaml"), "w").write(
        "# %s — a ScienceWorld task variation as a package (generated by world/gen_instance.py).\n"
        "program: %s.llp\nhost: sw_host.py:make\nintent: {spec: intent.yaml}\nclock: {beats: 1}\nrecords: records/\n"
        "display: ScienceWorld %s %d\nline: %s\nvoice: own\n" % (name, name, task, variation, json.dumps(info["desc"].replace("\n", " ")[:160])))
    shim = open(os.path.join(HERE, "package_host.py")).read().replace("__WORLD__", HERE)
    open(os.path.join(pkg, "sw_host.py"), "w").write(shim)
    return pkg, kept


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("task"); ap.add_argument("variation", type=int)
    ap.add_argument("--out", default=os.path.join(HERE, "..", "domains"))
    ap.add_argument("--simplification", default="easy")
    a = ap.parse_args(argv)
    pkg, n = generate(a.task, a.variation, a.out, a.simplification)
    print("%s: %d perceived atoms" % (pkg, n))
    return 0


if __name__ == "__main__":
    sys.exit(main())
