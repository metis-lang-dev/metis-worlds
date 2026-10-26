"""beast_case.py — the dungeon beast case (specialist-tree s-404d001f step 3a; steps/step3a-beast-brief.md): the
inversion proper on MiniHack's hierarchy under the tick. A hostile newt comes down a one-wide lane at the robot on
its way to the stairs; act triggers ITSELF on the situation layer's oncoming(b) (semantic_world.situation over the
host's map), takes the body (motion) from nav by the instance's priority(act, nav) — the director's preempt, the one
exception to the grant hysteresis —, strikes the newt when it is beside the robot, and gives the body back; nav, which
kept its goal and its queued request, resumes with no director call.

    .worlds/mh/bin/python experiments/beast_case.py setup OUT [SEED …]
    cd metis-agent/py && METIS_MH_PY=… .venv/bin/python …/experiments/beast_case.py run OUT [SEED …]

run prints, per seed, the record and the brief's conditions checked off the journal and the NLE steps."""
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

ROWS = ["|||||||||||||||||||||||",
        "|...|||||||||||||||...|",
        "|.....................|",
        "|...|||||||||||||||...|",
        "|||||||||||||||||||||||"]
START, STAIRS = (2, 2), (20, 2)                      # two lit rooms, a one-wide lane between them, the newt in the lane
NEWT = (int(os.environ.get("BEAST_NEWT_X", 15)), 2)  # its column: the robustness runs move it along the lane


def lane_des():
    from minihack import LevelGenerator
    lvl = LevelGenerator(map="\n".join(ROWS) + "\n", lit=True)
    lvl.set_start_rect(START, START)
    lvl.add_stair_down(place=STAIRS)
    lvl.add_monster("newt", place=NEWT)
    return lvl.get_des()


def setup(out, seeds=(1,)):
    import mh_hier
    for s in seeds:
        root = Path(out) / ("seed%d" % s)
        mh_hier.install(lane_des(), str(root), view=False, k=8, seed=s, name="lane_newt", max_steps=200, tree=True)   # priority: the tree's
        print(s, root)


class NoModel:
    BOOK = ("begin_dialog", "inject")

    def sibling(self, n):
        return self

    def __getattr__(self, name):
        if name in self.BOOK:
            return lambda *a, **k: 0
        raise RuntimeError("the model is not loaded (%s)" % name)


def run(root, timeout=float(os.environ.get("BEAST_TIMEOUT", 300))):
    import yaml
    root = Path(root).resolve()
    os.environ["METIS_CATALOG"] = str(root)
    steps_log = root / ".run" / "steps.jsonl"
    if steps_log.exists():
        steps_log.unlink()
    os.environ["METIS_MH_LOG"] = str(steps_log)
    from metis_agent.service import Live
    import mh_host
    mh_host.SHARED.clear()                           # one NLE world per run (seeds run one after another)
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
    sess0 = {n: id(a.repl) for n, a in live.agents.agents.items()}
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
    recs = list(live.journal.recs)
    steps = [json.loads(l) for l in open(steps_log)] if steps_log.exists() else []
    verbs = {}
    for r in recs:
        if r.get("kind") == "dlg-domain":
            key = "%s %s" % (r.get("verb"), r.get("domain"))
            verbs[key] = verbs.get(key, 0) + 1
    return {"error": err, "end": {x: (end or {}).get(x) for x in ("state", "text")}, "won": nav.won, "recs": recs,
            "steps": steps, "reloads": sum(n for v, n in verbs.items() if v.startswith("reload ")),
            "same_sessions": sess0 == {n: id(a.repl) for n, a in live.agents.agents.items()}}


def fired(recs, dom):
    """[(tick, rule, produce)] of DOM's own fired rows, the Live's tick read off the dlg-status rows."""
    out, tick = [], 1
    for r in recs:
        if r.get("kind") == "dlg-status":
            tick = r["beat"] + 1
        elif r.get("kind") == "dlg-trace" and r.get("domain") == dom:
            out += [(tick, row["event"].split("[")[0], row.get("produce") or []) for row in r.get("fired") or [] if row.get("kind") != "exo"]
    return out


def check(res):
    """The brief's pass conditions → {name: (ok, why)}."""
    recs, out = res["recs"], {}
    relay = [r for r in recs if r.get("kind") == "dlg-relay"]
    reports = [(r["stamp"], a) for r in relay if r.get("what") == "report" and r.get("from") == "act" for a in r.get("lines") or []]
    want = next((s for s, a in reports if "tick__want(act,motion)" in a), None)
    active = any("tick__active(act)" in a for _, a in reports)
    arrivals = [r.get("arrival") for r in recs if r.get("kind") == "dlg-director"]
    effects = [e for r in recs if r.get("kind") == "dlg-director" for e in r.get("effects") or []]
    out["1 act's own trigger"] = (want is not None and active and not any(str(a).startswith(("guarded(", "fight(")) for a in arrivals)
                                  and not any(e.startswith("forward(act,") for e in effects),
                                  "want@%s active %s; arrivals %s" % (want, active, arrivals[:6]))
    pre = [(t, p) for t, rule, p in fired(recs, "director") if rule == "preempt"]
    grants = [(r["stamp"], r["what"], r["domain"]) for r in relay if r.get("what") in ("grant", "revoke")]
    out["2 priority"] = (bool(pre) and want is not None and pre[0][0] - want <= 2
                         and any("tick__revoke(nav,motion)" in p for _, p in pre) and any("tick__grant(act,motion)" in p for _, p in pre),
                         "preempt@%s want@%s grants %s" % ([t for t, _ in pre], want, grants))
    holders = [(r["beat"], r.get("holder")) for r in recs if r.get("kind") == "dlg-status"]
    turn = next((b for (b0, h0), (b, h) in zip(holders, holders[1:]) if h0 == "nav" and h == "act"), None)
    out["2 priority"] = (out["2 priority"][0] and turn is not None and pre and turn - pre[0][0] <= 1,
                         out["2 priority"][1] + "; holder nav → act @%s" % turn)
    revoked = next((s for s, w, d in grants if w == "revoke" and d == "nav"), None)
    back = next((s for s, w, d in grants if w == "grant" and d == "nav" and revoked is not None and s > revoked), None)
    moves = [t for t, rule, _ in fired(recs, "nav") if rule == "move" and revoked is not None and revoked < t <= (back or 1 << 30)]
    held = [r for r in recs if r.get("kind") == "dlg-held"]
    out["3 no state ahead"] = (revoked is not None and not moves and not held, "nav moves while revoked %s, held %d" % (moves, len(held)))
    rel = next((s for s, a in reports if "tick__release(act,motion)" in a), None)
    goto_after = [e for r in recs if r.get("kind") == "dlg-director" for e in r.get("effects") or [] if e.startswith("forward(nav,")]
    out["5 unwinding"] = (rel is not None and back is not None and back - rel <= 2,
                          "release@%s nav back@%s; director forwards to nav: %d" % (rel, back, len(goto_after)))
    # the safety property (RSS, semantic-world case 4): a relocation while a beast is dangerous only within the
    # response time (RHO turns: what the safe distance allows), and never into the cell beside it
    import mh_host
    reloc = [(s.get("t"), s.get("gaps") or []) for s in res["steps"] if str(s.get("rule", "")).split("[")[0] == "move"]
    risky = [(t, min(g[2] for g in gs if g[3])) for t, gs in reloc if any(g[3] for g in gs)]
    out["4 safety"] = (len(risky) <= mh_host.RHO and all(gap > 2 for _, gap in risky),
                       "relocations while dangerous (turn, gap before): %s; the response time %s turns" % (risky, mh_host.RHO))
    strikes = [s for s in res["steps"] if str(s.get("rule", "")).startswith("move_strike")]
    out["4b the newt met by act"] = (bool(strikes), "act's strikes: %d, messages %s" % (len(strikes), [s.get("message") for s in strikes][:4]))
    out["6 outcome"] = (bool(res["won"]) and res["reloads"] == 0 and res["same_sessions"],
                        "won %s reloads %d same sessions %s end %s" % (res["won"], res["reloads"], res["same_sessions"], res["end"]))
    return out


if __name__ == "__main__":
    cmd, out = sys.argv[1], sys.argv[2]
    seeds = [int(s) for s in sys.argv[3:]] or [1]
    if cmd == "setup":
        setup(out, seeds)
    else:
        for s in seeds:
            res = run(Path(out) / ("seed%d" % s))
            c = check(res)
            print("== seed %d: %s" % (s, "PASS" if all(ok for ok, _ in c.values()) else "FAIL"))
            for name, (ok, why) in c.items():
                print("  %-22s %s  %s" % (name, "ok " if ok else "NO ", why))
            print("  steps:", [(st.get("rule"), st.get("action"), st.get("message")) for st in res["steps"]][:40])
