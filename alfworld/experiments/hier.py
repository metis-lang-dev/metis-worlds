"""hier.py — the hierarchy with a MANUAL switch (alf-hierarchy step 1, docs/HIERARCHY.md):

    ALFWORLD_DATA=data METISC=… .venv/bin/python experiments/hier.py --split train --task pick_and_place_simple --n 10 --seed 1

One game = a sequence of kernel runs, one per activation: the task domain runs until it emits a
sub-goal (the host ends the run: the atom is a result of the task's); the driver's TABLE
(gen_hier.HANDLES, the manual switch) names the specialist; the specialist's instance is
generated over the game's current facts (the driver's mirror of the game) with the sub-goal
as its start and runs until its result atom appears; the result and the task's own tokens
go into the task's next start. Until `done` or `stuck`.

The record (experiments/records/hier-<split>-<task>-<seed>.json): per game the activations
(specialist, goal, result, commands), the win; the totals; the vector per specialist beside
the flat domain's.
"""
import argparse, json, os, shutil, subprocess, sys, tempfile, time
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "world"))
sys.path.insert(0, HERE)
import families  # noqa: E402
import gen_instance  # noqa: E402
import gen_hier  # noqa: E402
from alf_host import AlfHost  # noqa: E402
from baseline import metis_py  # noqa: E402


def run_package(path, steps=12):
    """One kernel run over a generated package; the host's log read back: the commands sent
    (rule records) and the last tick's out atoms and tokens."""
    pkg = os.path.dirname(path)
    log = os.path.join(pkg, "host.log")
    env = dict(os.environ, METIS_ALF_LOG=log, METIS_ALF_PY=os.environ.get("METIS_ALF_PY", sys.executable))
    p = subprocess.run([metis_py(), "--plugin", os.path.join(pkg, "alf_host.py:make"), path], input="run %d\n" % steps,
                       capture_output=True, text=True, env=env, timeout=600)
    recs = [json.loads(l) for l in open(log)] if os.path.exists(log) else []
    cmds = [r for r in recs if "rule" in r]
    ticks = [r for r in recs if r.get("tick")]
    last = ticks[-1] if ticks else {}
    err = None
    if p.returncode != 0 or "Traceback" in p.stderr:
        err = (p.stderr.strip().splitlines() or ["rc %d" % p.returncode])[-1]
    return {"commands": cmds, "out": last.get("out", []), "tokens": last.get("tokens", []), "error": err, "stderr": p.stderr[-400:]}


def run_game(game_dir, workdir, max_activations=16):
    """The flat package first (its game.json gives the handles and the mirror host its game)."""
    flat, _, _ = gen_instance.generate(game_dir, workdir)
    flat_pkg = os.path.dirname(flat)
    info = json.load(open(os.path.join(flat_pkg, "game.json")))
    out_dir = os.path.join(workdir, gen_instance.instance_id(game_dir))
    mirror = AlfHost(flat_pkg)                       # the driver's own copy of the game
    info = dict(info, static=sorted(mirror.static), task_type=mirror.task, params=mirror.params)
    t0 = time.time()
    commands, tokens, results, acts, error, outcome = [], gen_hier.seed(info), [], [], None, "running"
    try:
        for k in range(max_activations):
            # the task domain: until it asks for something, or is done, or stuck
            path = gen_hier.generate(game_dir, out_dir, "task", k, info, mirror.reading(), tokens + results, commands)
            r = run_package(path)
            if r["error"]:
                error, outcome = "task: " + r["error"], "error"
                break
            out = r["out"]
            if not out:
                outcome = "silent"                   # the task emitted nothing: a gap in its rules
                break
            goal = out[0]
            base = goal.split("(")[0]
            if base in ("done", "stuck", "wrong_dest", "wrong_object"):
                outcome = base if base == "done" else "stuck: " + goal
                break
            spec = gen_hier.HANDLES[base]            # the manual switch
            tokens = r["tokens"]
            # the specialist: over the game as it is now, with the goal; until its result
            path = gen_hier.generate(game_dir, out_dir, spec, k, info, mirror.reading(), [goal], commands)
            s = run_package(path)
            if s["error"]:
                error, outcome = spec + ": " + s["error"], "error"
                break
            for c in s["commands"]:                  # mirror what the specialist did
                mirror.on_event(c["rule"], ())
                commands.append(c["command"])
            results = s["out"]
            acts.append({"k": k, "spec": spec, "goal": goal, "result": results, "commands": [c["command"] for c in s["commands"]],
                         "refused": [c["command"] for c in s["commands"] if not c["admissible"]]})
            if not results:
                outcome = spec + " silent on " + goal
                break
        else:
            outcome = "activations exhausted"
    finally:
        won = mirror.won
        mirror.gym.close()
    return {"game": game_dir, "won": won, "outcome": outcome, "activations": acts, "n_activations": len(acts),
            "commands": len(commands), "refused": sum(len(a["refused"]) for a in acts), "seconds": round(time.time() - t0, 1),
            "error": error}


def director_beat(out_dir, k, state, arrival):
    """One beat of the director (alf-hierarchy step 3): its carried state plus the arrival, one
    kernel run (no host), the effects read from the final counts: wake/sleep/forward/ask/ended;
    the state carried on is everything else."""
    path = gen_hier.generate_director(out_dir, k, state + [arrival])
    p = subprocess.run([metis_py(), path], input="run 6\nstate\n", capture_output=True, text=True, timeout=300)
    counts = {}
    for line in p.stdout.splitlines():
        for tok in line.split():
            if ":" in tok and "(" in tok or ":" in tok and tok.split(":")[0].isidentifier():
                a, _, n = tok.rpartition(":")
                if n.isdigit() and int(n) > 0:
                    counts[a] = int(n)
    if p.returncode != 0 or "Traceback" in p.stderr:
        raise RuntimeError("director: " + (p.stderr.strip().splitlines() or ["rc %d" % p.returncode])[-1])
    effects = sorted(a for a in counts if a.split("(")[0] in gen_hier.DIRECTOR_OUT)
    state = sorted(a for a in counts if a.split("(")[0] not in gen_hier.DIRECTOR_OUT and a.split("(")[0] not in ("seen", "idle"))
    return effects, state


def run_game_director(game_dir, workdir, max_beats=40, first=None):
    """The hierarchy with the DIRECTOR making the switch: every atom a domain puts out is an
    arrival of its kind for the director; the director's forward(D, K) sends D the atom of kind K
    whose frame the driver holds (the one just seen, or the one kept through a detour); wake and
    sleep are the driver's bookkeeping of which package runs. `first` overrides the seed (a
    person's goal, e.g. open(R) from elsewhere: the detour scenario)."""
    flat, _, _ = gen_instance.generate(game_dir, workdir)
    flat_pkg = os.path.dirname(flat)
    info = json.load(open(os.path.join(flat_pkg, "game.json")))
    out_dir = os.path.join(workdir, gen_instance.instance_id(game_dir))
    mirror = AlfHost(flat_pkg)
    info = dict(info, static=sorted(mirror.static), task_type=mirror.task, params=mirror.params)
    t0 = time.time()
    commands, acts, error, outcome = [], [], None, "running"
    tokens = {"task": []}                            # each domain's own tokens between its runs
    frames = {}                                      # kind -> the atom last seen of that kind; (D, kind) -> the one sent to D
    state = gen_hier.director_start()
    arrivals = list(first or gen_hier.seed(info))
    beats = []
    try:
        for k in range(max_beats):
            if not arrivals:
                outcome = "quiet"                    # nothing arrived: the director has nothing to do
                break
            atom = arrivals.pop(0)
            kind = atom.split("(")[0]
            frames[kind] = atom
            effects, state = director_beat(out_dir, k, state, "seen(%s)" % kind if kind != "idle" else atom)
            beats.append({"k": k, "arrival": atom, "effects": effects})
            for e in effects:
                base = e.split("(")[0]
                if base in ("ask", "ended"):
                    outcome = "done" if "done" in e else "stuck: " + frames.get(e[e.index("(") + 1:-1], e)
                if base == "forward":
                    d, kd = e[len("forward("):-1].split(",")
                    goal = frames.get(kd)
                    if kd in gen_hier.SPECS.get(d, {}).get("takes", ()) or d == "task" and kd == "fetch":
                        inits = tokens["task"] + [goal]
                    else:
                        # a goal for a specialist: after a detour the kept frame, else the one just seen renamed to its kind
                        goal = frames.get((d, kd)) if kind == "reached" and (d, kd) in frames and kd != "goto" else goal
                        if kd == "goto" and kind == "elsewhere":
                            goal = "goto(%s)" % atom[atom.index("(") + 1:-1]
                        if kd == "refused" and kind == "elsewhere":
                            goal = "refused(%s)" % atom[atom.index("(") + 1:-1]
                        frames[(d, kd)] = goal
                        inits = [goal]
                    path = gen_hier.generate(game_dir, out_dir, d, k, info, mirror.reading(), inits, commands)
                    r = run_package(path)
                    if r["error"]:
                        error, outcome = d + ": " + r["error"], "error"
                        break
                    for c in r["commands"]:
                        mirror.on_event(c["rule"], ())
                        commands.append(c["command"])
                    if d == "task":
                        tokens["task"] = r["tokens"]
                    acts.append({"k": k, "spec": d, "goal": goal, "result": r["out"], "commands": [c["command"] for c in r["commands"]],
                                 "refused": [c["command"] for c in r["commands"] if not c["admissible"]]})
                    arrivals += r["out"]
                    if d != "task":
                        arrivals.append("idle(%s)" % d)
                    if not r["out"] and d != "task":
                        outcome = d + " silent on " + str(goal)
            if outcome != "running" or error:
                break
        else:
            outcome = "beats exhausted"
    finally:
        won = mirror.won
        mirror.gym.close()
    return {"game": game_dir, "won": won, "outcome": outcome, "activations": acts, "n_activations": len([a for a in acts if a["spec"] != "task"]),
            "beats": beats, "commands": len(commands), "refused": sum(len(a["refused"]) for a in acts),
            "seconds": round(time.time() - t0, 1), "error": error}


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--split", default="train")
    ap.add_argument("--task", default="pick_and_place_simple")
    ap.add_argument("--n", type=int, default=10)
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--keep", help="keep the generated packages under this directory")
    ap.add_argument("--director", action="store_true", help="the director's rules make the switch (step 3), not the table")
    a = ap.parse_args(argv)
    games = families.sample(a.split, a.task, a.n, a.seed)
    out = {"split": a.split, "task": a.task, "n": len(games), "seed": a.seed, "games": [],
           "vector": {s: gen_hier.vector(s) for s in gen_hier.SPECS},
           "flat": {"rules": __import__("complexity").rules_in_base(),
                    "preds": sum(1 for l in open(os.path.join(ROOT, "domains", "alfred_domain.llp")) if l.startswith(("pred ", "bwd ")))}}
    wd = a.keep or tempfile.mkdtemp(prefix="alf-hier-")
    os.makedirs(wd, exist_ok=True)
    shutil.copy(os.path.join(ROOT, "domains", "alfred_domain.llp"), os.path.join(wd, "alfred_domain.llp"))
    os.makedirs(os.path.join(wd, "hier"), exist_ok=True)
    for s in gen_hier.SPECS:
        shutil.copy(os.path.join(ROOT, "domains", "hier", s + "_domain.llp"), os.path.join(wd, "hier", s + "_domain.llp"))
    shutil.copy(os.path.join(ROOT, "domains", "director_domain.llp"), os.path.join(wd, "director_domain.llp"))
    for i, g in enumerate(games):
        r = run_game_director(g, wd) if a.director else run_game(g, wd)
        out["games"].append(r)
        print("%2d %-56s %s  %d activations, %d commands, %d refused, %.0fs  %s" % (
            i + 1, g[-56:], "WON " if r["won"] else "lost", r["n_activations"], r["commands"], r["refused"], r["seconds"],
            r["outcome"] + ((" ERROR " + r["error"]) if r["error"] else "")), flush=True)
    out["won"] = sum(1 for r in out["games"] if r["won"])
    out["refusals"] = sum(r["refused"] for r in out["games"])
    os.makedirs(os.path.join(HERE, "records"), exist_ok=True)
    rp = os.path.join(HERE, "records", "hier%s-%s-%s-%d.json" % ("-director" if a.director else "", a.split, a.task, a.seed))
    json.dump(out, open(rp, "w"), indent=1)
    print("won %d/%d, %d refusals; %s" % (out["won"], out["n"], out["refusals"], rp))
    return 0


if __name__ == "__main__":
    sys.exit(main())
