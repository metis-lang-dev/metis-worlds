"""agent_run.py — the small agent in the level, unattended (world-minihack step 2a): every variant of a
split once, Gemma E2B acting from the card through metis-agent's domain agent (act without a rule:
the package's manifest `actor: {max_steps, task}`), every step journaled; then the measures.

    cd metis-agent/py && .venv/bin/python …/minihack/experiments/agent_run.py run OUT_DIR [--split discovery] [--max-steps 40] [--n N]
    …/agent_run.py report OUT_DIR            (no model: the journals → OUT_DIR/report.json and the REPORT §2a tables)

Runs under metis-agent's venv (the domain agent, the mapper, the model); the level's gym is the world's
child under .worlds/mh (mh_host). Each episode: the variant's package generated into a scratch catalog
(world/gen_level.py), one domain agent (one model, loaded once for the run), beats until the world
ends (the stairs, death) or the cap. Its journal, metis-agent's actor's (one JSONL per episode: a
`step` row per step, an `episode` row last), is copied to OUT_DIR/<variant>.jsonl: plain JSON lines,
what step 2b's extraction reads. Spend: 0 (E2B local).
"""
import argparse
import json
import os
import shutil
import sys
import tempfile
import time
from collections import Counter, defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
WORLD = HERE.parent / "world"
sys.path.insert(0, str(WORLD))
FEATURES = ("size", "item", "monster", "door", "trap")


def run(out, split="discovery", max_steps=40, n=None, seed=1, model=None):
    import subprocess
    import levels                                         # the split only (pure Python); the generator runs as the world's child
    from mh_host import interpreter
    from metis_agent.domain_agent import Process
    from metis_agent.llm import LLM
    from metis_agent.intent_check import GGUF
    out.mkdir(parents=True, exist_ok=True)
    variants = levels.split("room", split)[:n] if n else levels.split("room", split)
    llm = LLM(model or os.environ.get("E2B_GGUF") or str(GGUF), n_ctx=8192, n_batch=512, n_threads=4, n_gpu_layers=99)
    cat = Path(tempfile.mkdtemp(prefix="mh-agent-"))
    os.environ["METIS_CATALOG"] = str(cat)
    t0 = time.time()
    try:
        for i, v in enumerate(variants, 1):
            name = "room_%s_%s_%s_%s_%s" % v
            if (out / (name + ".jsonl")).exists():
                continue                                  # a resumed run keeps what it has
            g = subprocess.run([interpreter(), str(WORLD / "gen_level.py"), *v, "--seed", str(seed), "--out", str(cat / "domains"),
                                "--max-steps", str(max_steps)], capture_output=True, text=True, timeout=300)
            if g.returncode != 0:
                raise RuntimeError("gen_level %s: %s" % (name, g.stderr.strip().splitlines()[-1:]))
            pkg = str(cat / "domains" / name)
            sys.modules.pop("metis_agent.domains." + name, None)
            session = "s%d" % seed
            proc = Process([name], llm=llm, seat="template", records="catalog", session=session)
            ag = proc.build(seed, None)
            e0 = time.time()
            try:
                for _ in range(3 * max_steps + 10):       # a beat types, the next acts: well inside the cap's beats
                    ag.handle({"clock": "beat"})
                    if ag.actor.ended:
                        break
            finally:
                inner = getattr(ag.host, "inner", ag.host)
                getattr(getattr(inner, "gym", None), "close", lambda: None)()
            src = Path(pkg) / "records" / ("agent-%s.jsonl" % session)
            rows = [json.loads(x) for x in src.read_text().splitlines()] if src.exists() else []
            for r in rows:
                if r.get("kind") == "episode":
                    r.update(variant=dict(zip(FEATURES, v)), seed=seed, seconds=round(time.time() - e0, 1))
            with open(out / (name + ".jsonl"), "w") as f:
                for r in rows:
                    f.write(json.dumps(r) + "\n")
            ep = rows[-1] if rows and rows[-1].get("kind") == "episode" else {}
            print("%2d/%d %-40s %-4s %2d steps, %2d refused  %5.0fs" % (i, len(variants), name, ep.get("end", "?"), ep.get("steps", 0),
                                                                     ep.get("refusals", 0), time.time() - e0), flush=True)
            shutil.rmtree(pkg, ignore_errors=True)
    finally:
        llm.close()
        shutil.rmtree(cat, ignore_errors=True)
    print("run: %d episodes in %.0fs" % (len(variants), time.time() - t0))


# ── the measures (REPORT §2a) ──
def episodes(out):
    eps = []
    for p in sorted(Path(out).glob("room_*.jsonl")):
        rows = [json.loads(x) for x in p.read_text().splitlines() if x.strip()]
        ep = next((r for r in rows if r.get("kind") == "episode"), None)
        if ep:
            eps.append({"name": p.stem, "ep": ep, "steps": [r for r in rows if r.get("kind") == "step"]})
    return eps


def surprises(e):
    """The kinds of surprise in one episode (step 2b's extraction must turn each into a rule): one record
    per kind, named, with the episode and the step where it shows."""
    v, steps, out = e["ep"]["variant"], e["steps"], []
    cmd = lambda s: s.get("command") if isinstance(s.get("command"), str) else None
    took = lambda s: (s.get("result") or {}).get("acted", False)
    # a refused command the model keeps repeating (three in a row, the same command, the world refusing)
    run_, prev = 0, None
    for s in steps:
        c = cmd(s)
        run_ = run_ + 1 if (c == prev and not took(s)) else (1 if not took(s) else 0)
        prev = c
        if run_ == 3:
            out.append({"kind": "repeats_a_refused_command", "step": s["step"], "command": c,
                        "events": (s.get("result") or {}).get("events")})
            break
    # a monster it walks into (the world says it hit one, or it was hurt, after a move)
    for s in steps:
        ev = set((s.get("result") or {}).get("events") or [])
        if cmd(s) and cmd(s).startswith("cmd_move") and ev & {"said(hit)", "said(hurt)", "said(killed)"}:
            out.append({"kind": "walks_into_a_monster", "step": s["step"], "command": cmd(s), "events": sorted(ev)})
            break
    # killed while a monster bites: the world ends the episode (not won), its hp falling while a monster is in
    # sight, the agent neither moving away nor fighting in those steps
    hp = lambda s: next((int(a[3:-1]) for a in s.get("reading", []) if a.startswith("hp(")), None)
    if e["ep"]["end"] == "done" and not e["ep"]["won"] and steps:
        tail = steps[-6:]
        hps = [hp(s) for s in tail if hp(s) is not None]
        if len(hps) > 1 and hps[-1] < hps[0] and any(a.startswith("monster(") for s in tail for a in s.get("reading", [])):
            out.append({"kind": "killed_while_a_monster_bites", "step": steps[-1]["step"], "hp": hps,
                        "intents": sorted({(s.get("j") or {}).get("intent") for s in tail})})
    intents = Counter(s.get("j", {}).get("intent") for s in steps)
    if v["door"] != "none" and not e["ep"]["won"]:
        if not any(i in intents for i in ("OPEN", "KICK", "APPLY")):
            seen = next((s["step"] for s in steps if "door is" in (s.get("text") or "")), None)
            out.append({"kind": "never_opens_the_door", "step": seen, "intents": dict(intents)})
    if v["item"] == "key" and not any("holds(skeleton_key)" in s.get("reading", []) for s in steps):
        on = next((s["step"] for s in steps if "skeleton key (item) is here" in (s.get("text") or "")), None)
        out.append({"kind": "never_picks_up_the_key", "step": on, "picked": intents.get("PICKUP", 0)})
    if v["trap"] != "none" and any("said(fell_pit)" in ((s.get("result") or {}).get("events") or []) for s in steps):
        s = next(s for s in steps if "said(fell_pit)" in ((s.get("result") or {}).get("events") or []))
        out.append({"kind": "falls_into_the_pit", "step": s["step"], "command": cmd(s)})
    if not e["ep"]["won"] and e["ep"]["end"] == "cap" and not any(("stairs down" in (s.get("text") or "") or "the goal" in (s.get("text") or "")) for s in steps):
        out.append({"kind": "never_sees_the_stairs", "step": None})
    if not e["ep"]["won"] and any(("the stairs down is here" in (s.get("text") or "") or "the goal (a staircase) is here" in (s.get("text") or "")) for s in steps) and "DOWN" not in intents:
        s = next(s for s in steps if "is here" in (s.get("text") or "") and ("stairs down" in s["text"] or "the goal" in s["text"]))
        out.append({"kind": "on_the_stairs_never_descends", "step": s["step"]})
    return out


def report(out):
    eps = episodes(out)
    by = {f: defaultdict(lambda: [0, 0]) for f in FEATURES}
    intents, steps_n, refused = Counter(), [], []
    kinds = defaultdict(list)
    for e in eps:
        ep = e["ep"]
        for f in FEATURES:
            by[f][ep["variant"][f]][0] += ep["won"]
            by[f][ep["variant"][f]][1] += 1
        intents.update(ep.get("intents") or {})
        steps_n.append(ep["steps"])
        refused.append(ep["refusals"])
        for s in surprises(e):
            kinds[s["kind"]].append(dict(s, episode=e["name"]))
    table = {f: {k: {"won": w, "of": n, "rate": round(w / n, 3)} for k, (w, n) in sorted(d.items())} for f, d in by.items()}
    failing = [(f, k) for f, d in table.items() for k, x in d.items() if x["rate"] < 1]
    # one named surprise per failing feature value: the feature's own kind when an episode of that value shows
    # it (a door's, a key's, a monster's, a pit's), else the first surprise of the first lost episode of it
    OWN = {"door": ("never_opens_the_door",), "item": ("never_picks_up_the_key",),
           "monster": ("killed_while_a_monster_bites", "walks_into_a_monster"), "trap": ("falls_into_the_pit",)}
    named = {}
    for f, k in failing:
        lost = [(e, surprises(e)) for e in eps if e["ep"]["variant"][f] == k and not e["ep"]["won"]]
        own = [(e, s) for e, ss in lost for s in ss if k != "none" and s["kind"] in OWN.get(f, ())]
        pick = own[0] if own else next(((e, ss[0]) for e, ss in lost if ss), None)
        if pick:
            named["%s=%s" % (f, k)] = dict(pick[1], episode=pick[0]["name"])
    rep = {"episodes": len(eps), "won": sum(e["ep"]["won"] for e in eps),
           "ends": dict(Counter(e["ep"]["end"] for e in eps)), "mean_steps": round(sum(steps_n) / max(1, len(steps_n)), 2),
           "refusals_per_episode": round(sum(refused) / max(1, len(refused)), 2), "intents": dict(intents.most_common()),
           "features": table, "surprise_kinds": {k: {"episodes": len(v), "first": v[0]} for k, v in kinds.items()},
           "named_per_failing_feature": named, "cost": 0}
    (Path(out) / "report.json").write_text(json.dumps(rep, indent=1))
    print("episodes %d, won %d, ends %s, mean steps %.1f, refusals/episode %.1f" % (
        rep["episodes"], rep["won"], rep["ends"], rep["mean_steps"], rep["refusals_per_episode"]))
    for f, d in table.items():
        print("  %-8s " % f + "  ".join("%s %d/%d" % (k, x["won"], x["of"]) for k, x in d.items()))
    print("  intents", rep["intents"])
    for k, v in kinds.items():
        print("  surprise %-30s %2d episodes, e.g. %s step %s" % (k, len(v), v[0]["episode"], v[0]["step"]))
    print("  named per failing feature: %d of %d" % (len(named), len(failing)))
    return rep


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("what", choices=["run", "report"])
    ap.add_argument("out")
    ap.add_argument("--split", default="discovery")
    ap.add_argument("--max-steps", type=int, default=40)
    ap.add_argument("--n", type=int, default=None)
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--model", default=None)
    a = ap.parse_args()
    if a.what == "run":
        run(Path(a.out), a.split, a.max_steps, a.n, a.seed, a.model)
    report(Path(a.out))
