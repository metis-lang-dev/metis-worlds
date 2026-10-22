"""baseline.py — the program's own rules on a sample of games, no loop (world-alfworld
step 1 / step 3's baseline):

    ALFWORLD_DATA=data METISC=… .venv/bin/python experiments/baseline.py --split train --task pick_and_place_simple --n 10 --seed 1

For each game: generate its package (world/gen_instance.py), run the program through
metispy's REPL with the host attached (`metis --plugin <pkg>/alf_host.py:make <pkg>/<iid>.llp`,
`run N`), read the host's log: the commands, which the game refused, whether it won. The
report (experiments/records/baseline-<split>-<task>-<seed>.json): per game the outcome,
the steps, the refusals; the totals. The metispy interpreter: $METIS_PY, else the packages'
shared .venv beside this repo.
"""
import argparse, json, os, subprocess, sys, tempfile, time
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "world"))
import families  # noqa: E402
import gen_instance  # noqa: E402


def metis_py():
    p = os.environ.get("METIS_PY")
    if p:
        return p
    d = ROOT
    for _ in range(3):  # a metispy venv beside the worlds repo (perotheia-packages/.venv), walking up
        d = os.path.dirname(d)
        c = os.path.join(d, ".venv", "bin", "metis")
        if os.path.exists(c):
            return c
    raise SystemExit("set METIS_PY to a metispy `metis` CLI")


def run_game(game_dir, steps, workdir):
    path, nd, ns = gen_instance.generate(game_dir, workdir)
    pkg = os.path.dirname(path)
    log = os.path.join(pkg, "host.log")
    env = dict(os.environ, METIS_ALF_LOG=log, METIS_ALF_PY=os.environ.get("METIS_ALF_PY", sys.executable))
    t0 = time.time()
    p = subprocess.run([metis_py(), "--plugin", os.path.join(pkg, "alf_host.py:make"), path], input="run %d\n" % steps,
                       capture_output=True, text=True, env=env, timeout=900)
    recs = [json.loads(l) for l in open(log)] if os.path.exists(log) else []
    cmds = [r for r in recs if "rule" in r]
    fired = [l for l in p.stdout.splitlines() if l.startswith("llp>")]
    return {"game": os.path.relpath(game_dir, families.data_root()), "task": families.task_of(game_dir),
            "dynamic": nd, "static": ns, "won": any(r.get("won") for r in cmds), "commands": len(cmds),
            "refused": [[r["rule"], r["command"]] for r in cmds if not r["admissible"]],
            "fired": (fired[0][5:][:300] if fired else ""), "seconds": round(time.time() - t0, 1),
            "error": (p.stderr.strip().splitlines()[-1] if p.returncode else None)}


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--split", default="train")
    ap.add_argument("--task", default="pick_and_place_simple")
    ap.add_argument("--n", type=int, default=10)
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--steps", type=int, default=30)
    a = ap.parse_args(argv)
    games = families.sample(a.split, a.task, a.n, a.seed)
    out = {"split": a.split, "task": a.task, "n": len(games), "seed": a.seed, "games": []}
    with tempfile.TemporaryDirectory(prefix="alf-baseline-") as wd:
        import shutil
        shutil.copy(os.path.join(ROOT, "domains", "alfred_domain.llp"), os.path.join(wd, "alfred_domain.llp"))
        for i, g in enumerate(games):
            r = run_game(g, a.steps, wd)
            out["games"].append(r)
            print("%2d %-60s %s  %d commands, %d refused, %.0fs%s" % (i + 1, r["game"][-60:], "WON " if r["won"] else "lost",
                  r["commands"], len(r["refused"]), r["seconds"], ("  ERROR " + r["error"]) if r["error"] else ""), flush=True)
    out["won"] = sum(1 for r in out["games"] if r["won"])
    out["refusals"] = sum(len(r["refused"]) for r in out["games"])
    os.makedirs(os.path.join(HERE, "records"), exist_ok=True)
    rp = os.path.join(HERE, "records", "baseline-%s-%s-%d.json" % (a.split, a.task, a.seed))
    json.dump(out, open(rp, "w"), indent=1)
    print("won %d/%d, %d refusals; %s" % (out["won"], out["n"], out["refusals"], rp))
    return 0


if __name__ == "__main__":
    sys.exit(main())
