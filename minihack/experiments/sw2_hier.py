"""sw2_hier.py — semantic-world step 2's cases (s-227b8e1b, design §4 cases 1-3 and 7) on MiniHack's HIERARCHY
(world/mh_hier.py: director, task, nav, act over roles; the map semantic_world.grid), on CPU through metis-agent's
own service object (Live: the director, the domains, the journal; the person's REACH typed — WIRE.md intent{domain,
id, j}, no model). Each case runs in its own process (the domain modules are cached per process).

    .worlds/mh/bin/python experiments/sw2_hier.py setup OUT
    cd metis-agent/py && PYTHONPATH=$PWD .venv/bin/python …/experiments/sw2_hier.py run OUT [CASE …] [--out F]

Cases (each its own root OUT/<case>; every domain compiled over the capacity, no level in any source):
- room (1):    room_medium_apple_newt_closed_none: a closed door on the way (nav → closed → act opens → nav again)
- mines (2):   the exerciser's cave (semantic_world.dungeon.cave, the Mines' shape, from the article's algorithm),
               76 × 21 (MiniHack's largest MAP; the screen is 79 × 21), dark: the same program
- mines-k16:   the same cave over the capacity at k = 16 (the grounding is the program's, not the level's)
- gates (3):   the exerciser's rooms, two: a closed door out of the first, a locked one into the stairs' room
               (act opens, is told it is locked, kicks until it gives)
- view (7):    the exerciser's rooms, five, in view mode: nothing known at the start, the goal role a frontier cell
               until the stairs are seen
- beast:       a corridor with a newt in it (nav → guarded → act fights → nav again)
Every domain's watch runs blind (arm A: the reading applied, no verdict): MiniHack's world brings what no rule
predicts — a room seen as its door opens, a beast's own step — and a surprise waits for a consult, which needs
the model (none on this CPU step)."""
import json
import os
import queue
import subprocess
import sys
import threading
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
WORLD = HERE.parent / "world"
sys.path.insert(0, str(HERE))
from sw2_roles import VARIANT, corridor_des  # noqa: E402


def cases():
    """{case: (level, view, k, max_steps)}: a des (the exerciser's through Level.des()) or the room variant."""
    from semantic_world import dungeon
    cave = dungeon.cave(76, 21, 1).des()
    return {"room": (VARIANT, False, 8, 400), "mines": (cave, False, 8, 800), "mines-k16": (cave, False, 16, 800),
            "gates": (dungeon.rooms(76, 21, 3, n=2, doors=("closed", "locked"), spur=False).des(), False, 8, 800),
            "view": (dungeon.rooms(76, 21, 6, doors=("doorway", "open", "closed")).des(), True, 8, 1500),
            "beast": (corridor_des(), False, 8, 200)}


def setup(out):
    sys.path.insert(0, str(WORLD))
    import mh_hier
    out = Path(out)
    for c, (lv, view, k, steps) in cases().items():
        root = out / c
        mh_hier.install(lv, str(root), view=view, k=k, name=c, max_steps=steps)
        print(c, root)


class NoModel:
    BOOK = ("begin_dialog",)

    def sibling(self, n):
        return self

    def __getattr__(self, name):
        if name in self.BOOK:
            return lambda *a, **k: 0
        raise RuntimeError("the model is not loaded (%s)" % name)


def run_case(root, timeout=900):
    import yaml
    os.environ["METIS_CATALOG"] = str(Path(root).resolve())
    from metis_agent.service import Live
    cfg = yaml.safe_load((Path(root) / ".run" / "config.yaml").read_text())
    cfg["domains"]["consult"] = False
    frames, lock = [], threading.Lock()

    def emit(ev, f, **kw):
        with lock:
            frames.append(dict(f, ev=ev, t=time.time()))
    t0 = time.perf_counter()
    live = Live(cfg, NoModel(), emit=emit)
    live.journal.emit = emit
    t_load = time.perf_counter() - t0
    for ag in live.agents.agents.values():
        ag.watch.blind = True
    sess0 = {n: id(a.repl) for n, a in live.agents.agents.items()}
    mp = Path(root) / "domains" / "hier" / ".map.json"
    before = json.loads(mp.read_text())
    threading.Thread(target=live.run, daemon=True).start()
    live.started.set()
    q = queue.Queue()
    k = len(frames)
    t1 = time.perf_counter()
    live.jobs.put(("call", live.typed, ("task", "c1", {"intent": "REACH"}), q.put))
    err = q.get(timeout=60)
    end = None
    deadline = time.time() + timeout
    while time.time() < deadline and end is None:
        with lock:
            end = next((f for f in frames[k:] if f.get("ev") == "world/status" and f.get("state") in ("over", "done", "stuck", "asking")), None)
        time.sleep(0.05)
    t_end = time.perf_counter() - t1
    import mh_host
    shared = mh_host.SHARED.get(str(mp.resolve())) or next(iter(mh_host.SHARED.values()), {})
    won_at = shared.get("won_at")
    with lock:
        fr = list(frames[k:])
    recs = [f.get("rec") or {} for f in fr if f.get("ev") == "journal"]
    verbs = {}
    for r in recs:
        if r.get("kind") == "dlg-domain":
            key = "%s %s" % (r.get("verb"), r.get("domain"))
            verbs[key] = verbs.get(key, 0) + 1
    said = [r.get("text") for r in recs if r.get("kind") == "dlg-say"]
    director = [(r.get("arrival"), r.get("effects")) for r in recs if r.get("kind") == "dlg-director"]
    after = json.loads(mp.read_text())
    host = live.agents.agents["nav"].host.inner
    res = {"error": err, "end": {x: (end or {}).get(x) for x in ("state", "text")}, "load_s": round(t_load, 2),
           "to_win_s": round(won_at - t1, 3) if won_at else None, "to_end_s": round(t_end, 3), "steps": sum(getattr(a.host.inner, "t", 0) for a in live.agents.agents.values()),
           "won": host.won, "reloads": sum(n for v, n in verbs.items() if v.startswith("reload ")), "verbs": verbs,
           "same_sessions": sess0 == {n: id(a.repl) for n, a in live.agents.agents.items()}, "said": said,
           "director": [a for a, _ in director], "before": {"known": len(before["cells"]), "belief": before["belief"]},
           "after": {"known": len(after["cells"]), "seen": len(after["seen"]), "belief": after["belief"]}}
    live.stop.set()
    return res


def ground(root):
    from metis.lang.compiler import load_llp
    out = {}
    for sp in ("task", "nav", "act", "director"):
        p = Path(root) / "domains" / "hier" / sp / ("%s.llp" % sp)
        t0 = time.perf_counter()
        prog = load_llp(p).catalog.ground({})
        out[sp] = {"events": sum(len(v) for v in prog.stages.values()) + len(prog.links), "ms": round((time.perf_counter() - t0) * 1000, 1)}
    return out


if __name__ == "__main__":
    if sys.argv[1] == "setup":
        setup(sys.argv[2])
    elif sys.argv[1] == "one":                          # one case in this process: its record as JSON on stdout's last line
        sys.path.insert(0, str(WORLD))
        root = sys.argv[2]
        r = run_case(root)
        r["ground"] = ground(root)
        print("RESULT " + json.dumps(r, default=str))
    else:
        dest = sys.argv[sys.argv.index("--out") + 1] if "--out" in sys.argv else None
        names = [a for a in sys.argv[3:] if not a.startswith("--") and a != dest] or ["room", "mines", "mines-k16", "gates", "view", "beast"]
        res = {}
        for c in names:
            root = Path(sys.argv[2]) / c
            p = subprocess.run([sys.executable, __file__, "one", str(root)], capture_output=True, text=True)
            line = next((l for l in p.stdout.splitlines()[::-1] if l.startswith("RESULT ")), None)
            if line is None:
                print("== %s: FAILED rc %d\n%s" % (c, p.returncode, (p.stderr or p.stdout)[-3000:]))
                continue
            r = res[c] = json.loads(line[7:])
            print("== %s: %s %r; won %s; to the win %s s, to the end %s s (load %.2f s); reloads %d; same sessions %s" % (
                c, r["end"]["state"], r["end"]["text"], r["won"], r["to_win_s"], r["to_end_s"], r["load_s"], r["reloads"], r["same_sessions"]))
            print("   verbs", r["verbs"])
            print("   director", r["director"][:16])
            print("   said", r["said"][:14])
            print("   ground", r["ground"])
            print("   map known", r["before"]["known"], "->", r["after"]["known"], "belief", r["before"]["belief"], "->", r["after"]["belief"])
            sys.stdout.flush()
        if dest:
            Path(dest).write_text(json.dumps(res, indent=1, default=str))
