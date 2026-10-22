"""hier_vector.py — the complexity vector PER DOMAIN (alf-hierarchy step 1, docs/HIERARCHY.md):
the flat domain's instance against each specialist's activation instance on one game:

    ALFWORLD_DATA=data .venv/bin/python experiments/hier_vector.py [--split train --seed 1]

rules and predicates of the lifted base; the instance's declared types and their sizes, its
static facts, its #init facts; the GROUND BOUND = Σ over the declared predicates of the product
of their argument types' sizes (the atoms the kernel may have to consider). Written to
experiments/records/hier-vector-<split>-<seed>.json and printed as a table.
"""
import argparse, json, os, re, sys, tempfile
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "world"))
import families, gen_instance, gen_hier  # noqa: E402
from alf_host import AlfHost  # noqa: E402


def stats(instance, base):
    t = open(instance).read()
    kinds = {m.group(1): len(m.group(2).split()) for m in re.finditer(r"^type (\w+) \{([^}]*)\}", t, re.M)}
    facts = sum(1 for l in t.splitlines() if re.match(r"^[a-z]\w*\(.*\)\.$", l))
    init = sum(1 for l in t.splitlines() if l.startswith("#init"))
    b = open(base).read()
    rules = len(re.findall(r"^\s+\w+ \[dyn\] :", b, re.M))
    preds = len(re.findall(r"^(?:pred|bwd) ", b, re.M))
    ground = 0
    for m in re.finditer(r"^(?:pred|bwd) (\w+)(?:\(([^)]*)\))? ", b, re.M):
        n = 1
        for a in [x.strip() for x in (m.group(2) or "").split(",") if x.strip()]:
            n *= kinds.get(a, 0)
        ground += n
    return {"rules": rules, "preds": preds, "types": kinds, "static_facts": facts, "init": init, "ground_atoms": ground}


def measure(game, wd):
    path, _, _ = gen_instance.generate(game, wd)
    pkg = os.path.dirname(path)
    info = json.load(open(os.path.join(pkg, "game.json")))
    h = AlfHost(pkg)
    try:
        info = dict(info, static=sorted(h.static), task_type=h.task, params=h.params)
        reading = h.reading()
    finally:
        h.gym.close()
    rows = {"flat": stats(path, os.path.join(ROOT, "domains", "alfred_domain.llp"))}
    # the activation instances along the task's own plan on this game: the first target, its receptacle, the first destination
    targets = sorted(a[len("target("):-1] for a in gen_hier.static_facts("task", info) if a.startswith("target("))
    dests = sorted(a[len("dest("):-1] for a in gen_hier.static_facts("task", info) if a.startswith("dest("))
    o, d = targets[0], dests[0]
    rec = next(a for a in reading if a.startswith("inrecep(%s," % o))[8:-1].split(",")[1]
    goals = {"task": gen_hier.seed(info), "nav": ["goto(%s)" % rec], "access": ["open(%s)" % rec], "grasp": ["take(%s)" % o],
             "place": ["put(%s,%s)" % (o, d)]}
    for spec in gen_hier.SPECS:
        p = gen_hier.generate(game, os.path.join(wd, "pk"), spec, 0, info, reading, goals[spec], [])
        rows[spec] = stats(p, os.path.join(ROOT, "domains", "hier", spec + "_domain.llp"))
    return rows


def table(rows):
    out = ["| domain | rules | preds | types (sizes) | static facts | #init | ground atoms (bound) |", "|---|---|---|---|---|---|---|"]
    for k, r in rows.items():
        out.append("| %s | %d | %d | %s | %d | %d | %d |" % (k, r["rules"], r["preds"], ", ".join("%s %d" % kv for kv in r["types"].items()),
                                                           r["static_facts"], r["init"], r["ground_atoms"]))
    s = {k: r for k, r in rows.items() if k != "flat"}
    for name, f in (("specialists, sum", sum), ("specialists, max", max)):
        out.append("| %s | %d | %d | | %d | %d | %d |" % (name, f(r["rules"] for r in s.values()), f(r["preds"] for r in s.values()),
                                                       f(r["static_facts"] for r in s.values()), f(r["init"] for r in s.values()),
                                                       f(r["ground_atoms"] for r in s.values())))
    return "\n".join(out)


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--split", default="train")
    ap.add_argument("--task", default="pick_and_place_simple")
    ap.add_argument("--seed", type=int, default=1)
    a = ap.parse_args(argv)
    game = families.sample(a.split, a.task, 1, a.seed)[0]
    wd = tempfile.mkdtemp(prefix="alf-vec-")
    rows = measure(game, wd)
    print(table(rows))
    print(game)
    os.makedirs(os.path.join(HERE, "records"), exist_ok=True)
    json.dump({"game": game, "rows": rows}, open(os.path.join(HERE, "records", "hier-vector-%s-%d.json" % (a.split, a.seed)), "w"), indent=1)
    return 0


if __name__ == "__main__":
    sys.exit(main())
