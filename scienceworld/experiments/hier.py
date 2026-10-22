"""hier.py — the hand hierarchy with a MANUAL switch (world-scienceworld step 2): one variation =
a sequence of kernel runs, one per activation. The task package runs until it puts out a sub-goal
(metis.repl's counts, as data); the driver's TABLE (gen_hier.HANDLES) names the specialist; its
instance is generated over the world as the driver's MIRROR sees it now, with the sub-goal as its
start, and runs until a result of its kind is out; the result goes into the task's next start.
Until done or stuck. The commands a run sent (the host's log) are replayed into the mirror, so the
next instance starts where the world is.

    METISC=… ../.worlds/sw/bin/python scienceworld/experiments/hier.py --family conductivity --split train --n 20

Record: experiments/records/hier-<family>-<split>-<n>.json (gitignored): per variation the
activations (specialist, goal, result, commands), the win; the totals; the vector per specialist.
"""
import argparse, json, os, shutil, sys, tempfile, time
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "world"))
sys.path.insert(0, HERE)
import families  # noqa: E402
import gen_hier  # noqa: E402
from sw_host import SwHost  # noqa: E402
from metis.repl import Repl  # noqa: E402


def run_package(path, steps=40):
    """One kernel run over a generated package, in process (metis.repl): the commands its host sent
    (the host's log) and the counts at the end — the out atoms of its kind, the rest as tokens."""
    pkg = os.path.dirname(path)
    log = os.path.join(pkg, "host.log")
    if os.path.exists(log):
        os.remove(log)
    old = os.environ.get("METIS_SW_LOG")
    os.environ["METIS_SW_LOG"] = log
    err, counts, fired = None, {}, []
    try:
        r = Repl.open(path, plugin=os.path.join(pkg, "sw_host.py:make"))
        res = r.run(steps)
        counts, fired = dict(res.get("counts") or {}), list(res.get("fired") or [])
        try:
            r.shell.close()
        except Exception:
            pass
    except Exception as e:  # noqa: BLE001
        err = "%s: %s" % (type(e).__name__, str(e).splitlines()[-1][:200] if str(e) else "")
    finally:
        if old is None:
            os.environ.pop("METIS_SW_LOG", None)
        else:
            os.environ["METIS_SW_LOG"] = old
    recs = [json.loads(l) for l in open(log)] if os.path.exists(log) else []
    cmds = [x for x in recs if "command" in x]
    meta = json.load(open(os.path.join(pkg, "task.json")))
    out = sorted(a for a, n in counts.items() if n > 0 and a.split("(")[0] in meta["out"])
    tokens = sorted(a for a, n in counts.items() if n > 0 and a.split("(")[0] not in meta["out"] and a.split("(")[0] not in meta["observe"]
                    and a.split("(")[0] not in ("task", "where", "here", "door", "in", "holds", "focused", "state", "connected", "reads", "closed", "open", "matter", "measured", "threshold", "said", "ready"))
    return {"commands": cmds, "out": out, "tokens": tokens, "fired": fired, "error": err}


def run_variation(task, variation, workdir, max_activations=12):
    """One variation through the hierarchy by the manual switch."""
    base = os.path.join(workdir, "base")
    os.makedirs(base, exist_ok=True)
    tj = {"task": task, "variation": variation, "simplification": "easy"}
    json.dump(tj, open(os.path.join(base, "task.json"), "w"))
    mirror = SwHost(base, max_steps=200)               # the driver's own copy of the world
    t0 = time.time()
    out_dir = os.path.join(workdir, "%s_%d" % (task.replace("-", "_"), variation))
    task_atoms, names = list(mirror.task_atoms), set(mirror.gym.info.get("names") or [])
    tokens, results, acts, error, outcome, commands = ["start"], [], [], None, "running", []
    try:
        for k in range(max_activations):
            names |= {a.split("(")[0] and x for a in mirror.reading() for x in gen_hier.args_of(a)}
            path = gen_hier.generate(out_dir, "task", k, task_atoms, mirror.reading(), tokens + results, commands, names, task_json=tj)
            r = run_package(path)
            if r["error"]:
                error, outcome = "task: " + r["error"], "error"; break
            if not r["out"]:
                outcome = "silent"; break
            goal = r["out"][0]
            base_kind = goal.split("(")[0]
            if base_kind in gen_hier.ENDS:
                outcome = base_kind if base_kind == "done" else "stuck: " + goal; break
            spec = gen_hier.HANDLES[base_kind]
            tokens = r["tokens"]
            path = gen_hier.generate(out_dir, spec, k, task_atoms, mirror.reading(), [goal], commands, names, task_json=tj)
            rs = run_package(path)
            if rs["error"]:
                error, outcome = spec + ": " + rs["error"], "error"; break
            for c in rs["commands"]:
                mirror.send(c["command"]); commands.append(c["command"])
            results = rs["out"]
            acts.append({"k": k, "spec": spec, "goal": goal, "result": rs["out"], "commands": [c["command"] for c in rs["commands"]],
                         "refused": [c["command"] for c in rs["commands"] if any(e in ("said(unknown)", "said(cant)") for e in c.get("events", []))]})
            if not rs["out"]:
                outcome = spec + " silent on " + goal; break
        else:
            outcome = "activations exhausted"
    finally:
        won, score = mirror.won, mirror.score
        mirror.gym.close()
    return {"task": task, "variation": variation, "won": won, "score": score, "outcome": outcome, "activations": acts,
            "n_activations": len(acts), "commands": len(commands), "refused": sum(len(a["refused"]) for a in acts),
            "seconds": round(time.time() - t0, 1), "error": error}


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--family", default="conductivity"); ap.add_argument("--split", default="train")
    ap.add_argument("--n", type=int, default=20); ap.add_argument("--keep")
    a = ap.parse_args(argv)
    vs = families.variations(a.family, a.split, max(1, a.n // len(families.FAMILIES[a.family])))[:a.n]
    wd = a.keep or tempfile.mkdtemp(prefix="sw-hier-")
    os.makedirs(os.path.join(wd, "hier"), exist_ok=True)
    for s in gen_hier.SPECS:
        shutil.copy(os.path.join(ROOT, "domains", "hier", s + "_domain.llp"), os.path.join(wd, "hier", s + "_domain.llp"))
    out = {"family": a.family, "split": a.split, "n": len(vs), "vector": {s: gen_hier.vector(s) for s in gen_hier.SPECS}, "games": []}
    for task, v in vs:
        r = run_variation(task, v, wd)
        out["games"].append(r)
        print("%-42s v=%-4d won=%-5s score=%5.1f acts=%d cmds=%d refused=%d %s %s" % (
            task, v, r["won"], r["score"], r["n_activations"], r["commands"], r["refused"], r["outcome"], ("ERR " + r["error"]) if r["error"] else ""))
    won = sum(g["won"] for g in out["games"])
    out["won"] = won
    os.makedirs(os.path.join(HERE, "records"), exist_ok=True)
    p = os.path.join(HERE, "records", "hier-%s-%s-%d.json" % (a.family, a.split, len(vs)))
    json.dump(out, open(p, "w"), indent=1)
    print("won %d/%d; vector %s; record %s" % (won, len(vs), json.dumps(out["vector"]), p))
    return 0


if __name__ == "__main__":
    sys.exit(main())
