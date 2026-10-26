"""nav_belief.py — the navigation playground (nav-belief s-794cf4c1 step 1): a lit Mines-style level of lanes and
junctions, the stairs behind them, three beasts of different NetHack behaviour — a jackal that chases, a peaceful
gnome that wanders, a white unicorn that keeps its distance — and the map's categorical intent belief per beast
(semantic_world.intent through GridMap's intents: priors by species, update from the observed displacement, the
position predicted along the lanes while unseen, NLE's line of sight as the observation). Today's nav and act run
unchanged (the CONTROL): the host logs, per world step, each beast's intent belief and levels and the per-step table.

    .worlds/mh/bin/python experiments/nav_belief.py setup OUT [SEED …]
    cd metis-agent/py && METIS_MH_PY=… .venv/bin/python …/experiments/nav_belief.py run OUT [SEED …]

run prints per seed: steps, waits, the outcome, and the levels per tick (from OUT/seedN/.run/steps.jsonl)."""
import json
import os
import queue
import sys
import threading
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
WORLD = HERE.parent / "world"
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(WORLD))

W, H = 41, 10
START, STAIRS = (1, 4), (38, 4)
NORTH = (9, 19, 29, 35)                 # junctions with a branch to the north lane (row 1): loops
SOUTH = (13, 23, 35)                    # junctions with a branch to a south chamber (rows 7-8)
CHAMBERS = ((11, 15), (21, 25), (33, 37))
# the beasts in intermittent view: the jackal down the main lane (seen as it comes), the gnome and the unicorn on the
# north lane (glimpsed up the branches); the peaceful gnome off the main lane (walking into it asks "Really attack?")
BEASTS = [("jackal", (31, 4), ()), ("gnome", (14, 1), ("peaceful",)), ("white unicorn", (27, 1), ())]
# the beasts' intent priors (hand-set from NetHack's behaviour: a jackal chases, a gnome here wanders, a unicorn
# keeps its distance) and their speeds (cells a turn, the hero's 12 = 1): the map's only knowledge of them
PRIORS = {"jackal": {"hostile": 0.5, "wandering": 0.3, "fleeing": 0.2},
          "gnome": {"hostile": 0.3, "wandering": 0.5, "fleeing": 0.2},
          "white_unicorn": {"hostile": 0.2, "wandering": 0.3, "fleeing": 0.5}}   # the map's names: NLE's, spaces as _
SPEEDS = {"jackal": 1.0, "gnome": 0.5, "white_unicorn": 2.0}


def rows():
    """The level's map: rock (' ') everywhere but the lanes and chambers, a wall frame."""
    g = [[" "] * W for _ in range(H)]
    for x in range(W):
        g[0][x] = g[H - 1][x] = "-"
    for y in range(1, H - 1):
        g[y][0] = g[y][W - 1] = "|"
    for x in range(1, W - 1):
        g[4][x] = "."                                     # the main lane
    for x in range(NORTH[0], NORTH[-1] + 1):
        g[1][x] = "."                                     # the north lane
    for x in NORTH:
        for y in (2, 3):
            g[y][x] = "."
    for x in SOUTH:
        for y in (5, 6):
            g[y][x] = "."
    for x0, x1 in CHAMBERS:
        for x in range(x0, x1 + 1):
            for y in (7, 8):
                g[y][x] = "."
    for x in (1, 2, 3):                                   # the start chamber
        for y in (3, 4, 5):
            g[y][x] = "."
    return ["".join(r) for r in g]


def level_des():
    from minihack import LevelGenerator
    lvl = LevelGenerator(map="\n".join(rows()) + "\n", lit=True)
    lvl.set_start_rect(START, START)
    lvl.add_stair_down(place=STAIRS)
    for sp, place, args in BEASTS:
        lvl.add_monster(sp, place=place, args=args)
    return lvl.get_des()


def setup(out, seeds=(1,)):
    import mh_hier
    for s in seeds:
        root = Path(out) / ("seed%d" % s)
        mh_hier.install(level_des(), str(root), view=False, k=8, seed=s, name="nav_mines", max_steps=300, tree=True,
                        intents={"priors": PRIORS, "los": True}, speeds=SPEEDS)
        print("setup:", root)


class NoModel:
    BOOK = ("begin_dialog",)

    def sibling(self, n):
        return self

    def __getattr__(self, name):
        if name in self.BOOK:
            return lambda *a, **k: 0
        raise RuntimeError("nav_belief: the model is not loaded (%s)" % name)


def run(root, timeout=float(os.environ.get("NAV_TIMEOUT", 300))):
    import yaml
    root = Path(root).resolve()
    os.environ["METIS_CATALOG"] = str(root)
    steps_log = root / ".run" / "steps.jsonl"
    if steps_log.exists():
        steps_log.unlink()
    os.environ["METIS_MH_LOG"] = str(steps_log)
    from metis_agent.service import Live
    import mh_host
    mh_host.SHARED.clear()
    cfg = yaml.safe_load((root / ".run" / "config.yaml").read_text())
    cfg["domains"]["consult"] = False
    frames, lock = [], threading.Lock()

    def emit(ev, f, **kw):
        with lock:
            frames.append(dict(f, ev=ev, t=time.time()))
    live = Live(cfg, NoModel(), emit=emit)
    live.journal.emit = emit
    for ag in live.agents.agents.values():
        ag.watch.blind = True
    threading.Thread(target=live.run, daemon=True).start()
    live.started.set()
    q = queue.Queue()
    k = len(frames)
    live.jobs.put(("call", live.typed, ("task", "c1", {"intent": "REACH"}), q.put))
    err = q.get(timeout=60)
    end, deadline = None, time.time() + timeout
    while time.time() < deadline and end is None:
        with lock:
            end = next((f for f in frames[k:] if f.get("ev") == "world/status" and f.get("state") in ("over", "done", "stuck", "asking")), None)
        time.sleep(0.05)
    live.stop.set()
    nav = live.agents.agents["nav"].host.inner
    steps = [json.loads(l) for l in open(steps_log)] if steps_log.exists() else []
    return {"error": err, "end": {x: (end or {}).get(x) for x in ("state", "text")}, "won": nav.won, "steps": steps}


def summary(res):
    """Steps (the world's actions), waits (a turn the robot stood: an action that left it where it was), the outcome,
    and the levels per tick: per beast its intent level and closing level as the map's record had them."""
    acts = [s for s in res["steps"] if "action" in s]
    recs = [s for s in res["steps"] if "intents" in s]
    waits, at = 0, None
    for r in recs:
        if r.get("agent") == at:
            waits += 1
        at = r.get("agent")
    trace = []
    for r in recs:
        row = {"t": r.get("t"), "at": r.get("agent")}
        for b, x in r["intents"].items():
            cl = "closing_sure" if x["closing"] >= 0.7 else ("closing_maybe" if x["closing"] >= 0.3 else None)
            row[b] = {"hostile": x["p"]["hostile"], "level": x["level"], "closing": cl, "seen": x["seen"], "support": x["support"]}
        trace.append(row)
    return {"steps": len(acts), "waits": max(0, waits - 1), "won": bool(res["won"]), "end": res["end"], "trace": trace,
            "levels": recs[0]["levels"] if recs else None}


if __name__ == "__main__":
    cmd, out = sys.argv[1], sys.argv[2]
    seeds = [int(s) for s in sys.argv[3:]] or [1]
    if cmd == "setup":
        setup(out, seeds)
    else:
        for s in seeds:
            sm = summary(run(Path(out) / ("seed%d" % s)))
            Path(out, "seed%d.json" % s).write_text(json.dumps(sm, indent=1))
            print("== seed %d: won %s steps %d waits %d end %s; levels %s" % (s, sm["won"], sm["steps"], sm["waits"], sm["end"], sm["levels"]))
            for row in sm["trace"]:
                print("   t%-3s %-6s %s" % (row["t"], row["at"], "  ".join("%s:%s/%s%s" % (b.split()[0][:6], (v["level"] or "-").replace("hostile_", "h."),
                                                                                            (v["closing"] or "-").replace("closing_", "c."), "" if v["seen"] else "?")
                                                                     for b, v in row.items() if isinstance(v, dict))))
