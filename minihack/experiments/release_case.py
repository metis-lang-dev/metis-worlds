"""release_case.py — the stale release on NLE (release-race s-c88bf623 step 0): a newt in the lane, then a locked door,
so act fights by itself and then gets a new grant for the door, as on pascal's real game. Beside the journal it keeps,
per tick, the protocol's tokens in the director's and the members' sessions.

    .worlds/mh/bin/python experiments/release_case.py setup OUT [SEED …]
    cd metis-agent/py && METIS_MH_PY=… .venv/bin/python …/experiments/release_case.py run OUT [SEED …]
"""
import json
import os
import queue
import sys
import threading
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "world"))
import beast_case  # noqa: E402

ROWS = ["|||||||||||||||||||||||",
        "|...|||||||||||||||...|",
        "|.....................|",
        "|...|||||||||||||||...|",
        "|||||||||||||||||||||||"]
START, STAIRS = (2, 2), (20, 2)
NEWT = (int(os.environ.get("RACE_NEWT_X", 8)), 2)
DOOR = (int(os.environ.get("RACE_DOOR_X", 14)), 2)
WATCH = ("tick__release(", "late(", "nolate(", "late_release(", "holder(", "held(", "free(", "want(", "queued(", "active(", "sleep(", "wake(")


def des():
    from minihack import LevelGenerator
    lvl = LevelGenerator(map="\n".join(ROWS) + "\n", lit=True)
    lvl.set_start_rect(START, START)
    lvl.add_stair_down(place=STAIRS)
    if os.environ.get("RACE_NEWT") != "none":
        lvl.add_monster("newt", place=NEWT)
    lvl.add_door(os.environ.get("RACE_DOOR", "locked"), place=DOOR)
    if os.environ.get("RACE_DOOR2_X"):           # a further door, for a third grant
        lvl.add_door(os.environ.get("RACE_DOOR2", "locked"), place=(int(os.environ["RACE_DOOR2_X"]), 2))
    return lvl.get_des()


def setup(out, seeds=(1,)):
    import mh_hier
    for s in seeds:
        root = Path(out) / ("seed%d" % s)
        mh_hier.install(des(), str(root), view=False, k=8, seed=s, name="lane_newt_door", max_steps=int(os.environ.get("RACE_STEPS", 120)), tree=True)
        print(s, root)


def tokens(repl):
    return sorted("%s=%d" % (a, n) for a, n in repl.counts.items() if n > 0 and a.startswith(WATCH))


def run(root, timeout=float(os.environ.get("RACE_TIMEOUT", 120))):
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
    live = Live(cfg, beast_case.NoModel(), emit=emit)
    live.journal.emit = emit
    for ag in live.agents.agents.values():
        ag.watch.blind = True
    if os.environ.get("RACE_DROP"):             # pascal's drop (NhHost.tick): a member's release with no grant in its session
        for name in ("nav", "act"):
            host = live.agents.agents[name].host
            inner = getattr(host, "inner", host)
            base = inner.tick

            def dropping(counts, base=base, name=name):
                dos = base(counts)
                rel, grant = "tick__release(%s,motion)" % name, "tick__grant(%s,motion)" % name
                if dos is not None and counts.get(rel, 0) > 0 and counts.get(grant, 0) <= 0:
                    dos.append("-%s %d" % (rel, counts[rel]))
                return dos
            inner.tick = dropping
    # after each tick: the sessions' tokens, the state the journal's rows don't carry
    trace, tick = [], live.tick

    def traced():
        tick()
        trace.append({"beat": live.beat, "holder": live.holder, "sessions": {n: tokens(a.repl) for n, a in live.agents.agents.items()}})
    live.tick = traced
    threading.Thread(target=live.run, daemon=True).start()
    live.started.set()
    q = queue.Queue()
    k = len(frames)
    live.jobs.put(("call", live.typed, ("task", "c1", {"intent": "REACH"}), q.put))
    q.get(timeout=60)
    end, deadline = None, time.time() + timeout
    while time.time() < deadline and end is None:
        with lock:
            end = next((f for f in frames[k:] if f.get("ev") == "world/status" and f.get("state") in ("over", "done", "stuck", "asking")), None)
        time.sleep(0.05)
    live.stop.set()
    time.sleep(0.2)
    return {"end": {x: (end or {}).get(x) for x in ("state", "text")}, "won": live.agents.agents["nav"].host.inner.won, "recs": list(live.journal.recs),
            "steps": [json.loads(l) for l in open(steps_log)] if steps_log.exists() else [], "trace": trace}


def report(res):
    """The tree's and the members' fired rows by beat, with the director's tokens where they changed."""
    rows = {}
    for r in res["recs"]:
        if r.get("kind") == "dlg-trace":
            for row in r.get("fired") or []:
                if row.get("kind") != "exo":
                    rows.setdefault(r.get("beat"), []).append("%s:%s" % (r.get("domain"), row["event"].split("[")[0]))
    return rows


if __name__ == "__main__":
    cmd, out = sys.argv[1], sys.argv[2]
    seeds = [int(s) for s in sys.argv[3:]] or [1]
    if cmd == "setup":
        setup(out, seeds)
    else:
        for s in seeds:
            res = run(Path(out) / ("seed%d" % s))
            (Path(out) / ("seed%d.json" % s)).write_text(json.dumps(res, default=str))
            print("== seed", s, res["end"], "won", res["won"], "beats", len(res["trace"]), "steps", len(res["steps"]))
