"""baseline.py — the simulator's gold paths through the HOST, command by command (world-scienceworld
step 1): the harness reproduces score 100 on N variations of a family, and the perception vector
per step is recorded. `METIS_SW_PY=… python experiments/baseline.py --family conductivity --n 20 --split train`
writes experiments/records/baseline-<family>-<split>-<n>.json (gitignored) and prints the table."""
import argparse, json, os, re, sys, tempfile, time
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "world"))
import families  # noqa: E402
import gen_instance  # noqa: E402
from sw_host import SwHost  # noqa: E402


def command_event(text):
    """A gold action's text → the host's event name (a fired rule with its bindings)."""
    u = lambda s: s.strip().replace(" ", "_")  # noqa: E731
    m = re.match(r"go to (.+)", text)
    if m: return "cmd_go[R=%s]" % u(m.group(1))
    m = re.match(r"open (.+)", text)
    if m: return "cmd_open[D=%s]" % u(m.group(1))
    m = re.match(r"close (.+)", text)
    if m: return "cmd_close[D=%s]" % u(m.group(1))
    m = re.match(r"pick up (.+)", text)
    if m: return "cmd_take[O=%s]" % u(m.group(1))
    m = re.match(r"drop (.+)", text)
    if m: return "cmd_drop[O=%s]" % u(m.group(1))
    m = re.match(r"focus on (.+)", text)
    if m: return "cmd_focus[O=%s]" % u(m.group(1))
    m = re.match(r"connect (.+) to (.+)", text)
    if m: return "cmd_connect[A=%s,B=%s]" % (u(m.group(1)), u(m.group(2)))
    m = re.match(r"move (.+) to (.+)", text)
    if m: return "cmd_move[O=%s,C=%s]" % (u(m.group(1)), u(m.group(2)))
    m = re.match(r"activate (.+)", text)
    if m: return "cmd_activate[O=%s]" % u(m.group(1))
    m = re.match(r"use (.+?) on (.+)", text)
    if m: return "cmd_use[A=%s,B=%s]" % (u(m.group(1)), u(m.group(2)))
    m = re.match(r"examine (.+)", text)
    if m: return "cmd_examine[O=%s]" % u(m.group(1))
    m = re.match(r"deactivate (.+)", text)
    if m: return "cmd_deactivate[O=%s]" % u(m.group(1))
    if text.startswith("wait"): return "cmd_wait"
    if text.startswith("look around"): return "cmd_look"
    return None


def run_variation(task, variation, workdir):
    pkg, _ = gen_instance.generate(task, variation, workdir)
    h = SwHost(pkg)
    try:
        gold = h.gym.call("gold")["gold"]
        preds, sizes, unmapped, refused = set(), [], [], 0
        t0 = time.time()
        for a in gold:
            ev = command_event(a)
            if not ev:
                unmapped.append(a); continue
            h.on_event(ev, ())
            if any(e in ("said(unknown)", "said(cant)", "said(ambiguous)") for e in h.events):
                refused += 1
            r = h.reading()
            preds |= {k.split("(")[0] for k in r} | {e.split("(")[0] for e in h.events if e.startswith("measured(")}   # one beat
            sizes.append(len(r))
            if h.done:
                break
        return {"task": task, "variation": variation, "gold": len(gold), "steps": h.t, "won": h.won, "score": h.score,
                "refused": refused, "unmapped": unmapped, "preds": sorted(preds), "atoms_mean": round(sum(sizes) / max(1, len(sizes)), 1),
                "atoms_max": max(sizes) if sizes else 0, "seconds": round(time.time() - t0, 1)}
    finally:
        h.gym.close()


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--family", default="conductivity"); ap.add_argument("--split", default="train")
    ap.add_argument("--n", type=int, default=20); ap.add_argument("--per-task", type=int, default=None)
    a = ap.parse_args(argv)
    vs = families.variations(a.family, a.split, a.per_task or max(1, a.n // len(families.FAMILIES[a.family])))[:a.n]
    work = tempfile.mkdtemp(prefix="sw-baseline-")
    recs = []
    for task, v in vs:
        r = run_variation(task, v, work)
        recs.append(r)
        print("%-42s v=%-4d gold=%2d steps=%2d score=%5.1f won=%s refused=%d unmapped=%d atoms~%s" % (
            task, v, r["gold"], r["steps"], r["score"], r["won"], r["refused"], len(r["unmapped"]), r["atoms_mean"]))
    won = sum(r["won"] for r in recs)
    preds = sorted(set().union(*[set(r["preds"]) for r in recs])) if recs else []
    out = {"family": a.family, "split": a.split, "n": len(recs), "won": won, "preds": preds, "records": recs}
    os.makedirs(os.path.join(HERE, "records"), exist_ok=True)
    p = os.path.join(HERE, "records", "baseline-%s-%s-%d.json" % (a.family, a.split, len(recs)))
    json.dump(out, open(p, "w"), indent=1)
    print("won %d/%d; predicates %s; record %s" % (won, len(recs), " ".join(preds), p))
    return 0


if __name__ == "__main__":
    sys.exit(main())
