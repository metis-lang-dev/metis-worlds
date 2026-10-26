"""tick_cases.py — specialist-tree step 2's check (s-404d001f): semantic-map step 3's five cases (sm_cases) on
the existing Live and on the tick runtime (metis-agent's TickLive: one program, a stage per specialist and the
direct stage), each run recorded whole, then compared on the WORLD-FACING stream and each specialist's own
trace (brief v2 §8 D).

    ALFWORLD_DATA=… .worlds/alf/bin/python experiments/tick_cases.py setup ROOT
    cd metis-agent/py && METIS_CATALOG=ROOT METIS_ALF_PY=… ALFWORLD_DATA=… \\
        .venv/bin/python …/experiments/tick_cases.py run ROOT OUT.jsonl [--tick] [CASE …]
    python3 experiments/tick_cases.py compare A.jsonl B.jsonl

A recording is one JSON line per frame the service emitted (ev, the frame), then one {"ev": "commands"} line
per case end with the shared commands log (every command the world took, in order). compare extracts:
- the commands (the world's input);
- the lines said (journal dlg-say: what, text);
- the world/* frames but world/hierarchy (the director's own state atoms: the tick's direct stage has others),
  their clock fields dropped;
- per specialist, its fired rows (rule, the produced and consumed atoms, the line), the exo rows (the syncs,
  the takes) set aside — the tick's rows unprefixed (the composer's reverse map) and attributed to their stage;
and reports the first difference of each."""
import json
import os
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "world"))

CLOCK = {"t", "ms", "dt", "seq", "rep", "wall", "elapsed", "first_ms", "turn_ms", "took", "beat", "ref", "record", "wake",
         "wait_ms", "seconds"}


def setup(root, tree=False):
    """The five cases' root (sm_cases.setup, view mode); tree: the tick's — gen_hier.install(tree=True) (the tree
    director, the specialists' motion extension) and the service's domains.tick flag."""
    import sm_cases
    if tree:
        import gen_hier
        install = gen_hier.install
        gen_hier.install = lambda *a, **kw: install(*a, **dict(kw, tree=True))
    sm_cases.setup(root, view=True)
    if tree:
        import yaml
        cp = Path(root) / ".run" / "config.yaml"
        cfg = yaml.safe_load(cp.read_text())
        cfg["domains"]["tick"] = True
        cp.write_text(yaml.safe_dump(cfg, sort_keys=False))


def run(root, out, cases, tick=False, flag=False):
    import sm_cases
    from metis_agent import service
    if flag:                                        # the existing Live with the tick's flag (domains.tick: true)
        import yaml
        cp = Path(root) / ".run" / "config.yaml"
        cfg = yaml.safe_load(cp.read_text())
        cfg["domains"]["tick"] = True
        cp.write_text(yaml.safe_dump(cfg, sort_keys=False))
    if tick:
        from metis_agent.tick import TickLive
        service.Live = TickLive                     # sm_cases builds service.Live: the tick runtime instead
    rec = open(out, "w")
    Agent = sm_cases.Agent
    emit0 = Agent._emit

    def emit(self, ev, f, **kw):
        emit0(self, ev, f, **kw)
        rec.write(json.dumps({"ev": ev, "f": f}, default=str) + "\n")
    Agent._emit = emit
    run0 = sm_cases.record

    def record(ag, k, *a, **kw):
        r = run0(ag, k, *a, **kw)
        log = Path(root) / "domains" / "hier" / ".commands.jsonl"
        cmds = [json.loads(l) for l in open(log)] if log.exists() else []
        rec.write(json.dumps({"ev": "commands", "f": {"end": r["end"], "commands": cmds}}) + "\n")
        rec.flush()
        return r
    sm_cases.record = record
    try:
        return sm_cases.run(root, cases)
    finally:
        rec.close()


def strip(x):
    if isinstance(x, dict):
        return {k: strip(v) for k, v in x.items() if k not in CLOCK and not k.endswith("_ms")}
    if isinstance(x, list):
        return [strip(v) for v in x]
    return x


def streams(path):
    """{name: [items]}: the world-facing streams and one per specialist's trace."""
    out = {"commands": [], "said": [], "world": []}
    for l in open(path):
        r = json.loads(l)
        ev, f = r["ev"], r["f"]
        if ev == "journal" and (f.get("rec") or f).get("kind") in ("dlg-status", "dlg-held"):
            rec = f.get("rec") or f
            out.setdefault("info:" + rec["kind"], []).append(strip(rec))
            continue
        if ev == "commands":
            out["commands"].append([c.get("command") for c in f["commands"]])
            continue
        if ev == "journal":
            rec = f.get("rec") or f
            if rec.get("kind") == "dlg-say":
                out["said"].append([rec.get("what"), rec.get("text")])
            elif rec.get("kind") == "dlg-trace":
                for row in rec.get("fired") or []:
                    if row.get("kind") == "exo":
                        continue
                    d = row.get("stage_of") or rec.get("domain")
                    item = [row.get("event"), sorted(row.get("consume") or []), sorted(row.get("produce") or []), row.get("line")]
                    if d == "director":
                        # the director's own rows are the journal's (a tree director has more: the grants, the path);
                        # its EFFECTS are the world-facing part: what it woke, put to sleep, forwarded, asked, ended
                        out.setdefault("info:director-trace", []).append(item)
                        out.setdefault("director-effects", []).extend(
                            a for a in row.get("produce") or [] if a.split("(")[0] in ("wake", "sleep", "forward", "ask", "ended"))
                    else:
                        out.setdefault("trace:" + d, []).append(item)
            continue
        if ev.startswith("world/") and ev != "world/hierarchy":
            out["world"].append([ev, strip(f)])
    return out


def compare(a, b):
    A, B = streams(a), streams(b)
    ok = True
    for k in sorted(set(A) | set(B)):
        x, y = A.get(k, []), B.get(k, [])
        if x == y:
            print("same  %-16s %d" % (k, len(x)))
            continue
        ok = ok and k.startswith("info:")
        i = next((i for i, (p, q) in enumerate(zip(x, y)) if p != q), min(len(x), len(y)))
        print("DIFF  %-16s %d vs %d, first at %d:" % (k, len(x), len(y), i))
        print("   A:", json.dumps(x[i] if i < len(x) else None)[:600])
        print("   B:", json.dumps(y[i] if i < len(y) else None)[:600])
    return ok


if __name__ == "__main__":
    import logging
    logging.basicConfig(level=os.environ.get("SM_LOG", "WARNING"), format="%(asctime)s %(message)s")
    if sys.argv[1] == "setup":
        setup(sys.argv[2], tree="--tree" in sys.argv)
    elif sys.argv[1] == "run":
        cases = [a for a in sys.argv[4:] if not a.startswith("--")] or ["new", "moved", "revisit", "revisit-wrong", "lost"]
        run(sys.argv[2], sys.argv[3], cases, tick="--tick" in sys.argv, flag="--flag" in sys.argv)
    else:
        sys.exit(0 if compare(sys.argv[2], sys.argv[3]) else 1)
