"""sm_cases.py — semantic-map step 3's cases (s-d4270bed) on CPU through metis-agent's own service
object: the director, the five specialists and the journal as the demo runs them, the person's FETCH
typed (WIRE.md intent{domain, id, j}: no model), the map in view mode (the robot sees only what stands
before it: the architect's RULING 1).

    ALFWORLD_DATA=… .worlds/alf/bin/python experiments/sm_cases.py setup ROOT [--all]
    cd metis-agent/py && METIS_CATALOG=ROOT METIS_ALF_PY=… ALFWORLD_DATA=… \\
        .venv/bin/python …/experiments/sm_cases.py run ROOT [CASE …] [--out OUT.json]

setup: demo.setup over the fixtures' kitchen (Tomato-Microwave-13) with view=True (--all: every fact).
run: the cases in order on ONE service object (the map carries over between them):
- new:     the tomato never seen (the map holds the wanted type, flat over the places that can hold a
           tomato); the robot looks place by place, the first sighting resolves it to tomato 1, the map
           and the card grow, the task wins;
- moved:   "new game" puts the tomato back on countertop 3 while the map believes it in microwave 1
           (where the robot left it): the robot looks there first, finds it absent, the belief re-ranks,
           it goes on, the task wins;
- revisit: "new game" with a changed belief: the tomato the last run took, back where a reset puts
           it (0.8) or on countertop 1 (0.2) — as the moved run found it (set by hand: the learning is
           not this step's); the robot goes there first (the look port) and wins with no search;
- revisit-wrong: the same belief the other way round (countertop 1 0.8): countertop 1 first, absent,
           then the next place by the belief;
- lost:    every place that can hold a tomato looked into without it (the belief exhausted): the task
           ends stuck, the director asks ("I can't find …"), no loop.
Per case the record: the journal's dlg-domain verbs (no reload inside the case), the spoken lines,
the belief before and after, the sessions' identities (one per domain throughout)."""
import json
import os
import queue
import sys
import threading
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
GAME = "train/pick_and_place_simple-Tomato-None-Microwave-13"
HOME = {"tomato1": "countertop3", "tomato2": "garbagecan1"}      # where the game's start puts each tomato (its facts)


def setup(root, view=True):
    sys.path.insert(0, str(HERE.parent / "world"))
    sys.path.insert(0, str(HERE))
    import demo
    import families
    game = next(Path(families.data_root(), GAME).glob("trial_*"))
    cfg, _, fetch, _ = demo.setup(game, root, view=view)
    print("setup: %s (view=%s) fetch %s" % (cfg, view, fetch))


class NoModel:
    """The service's model where none is used: a typed intent needs no turn, the agents no narration.
    The dialog's bookkeeping (begin_dialog: its token count) answers 0; a generation is an error."""
    BOOK = ("begin_dialog",)

    def sibling(self, n):
        return self

    def __getattr__(self, name):
        if name in self.BOOK:
            return lambda *a, **k: 0
        raise RuntimeError("sm_cases: the model is not loaded (%s)" % name)


class Agent:
    """metis-agent's Live in this process, its frames kept."""

    def __init__(self, root):
        import yaml
        from metis_agent.service import Live
        cfg = yaml.safe_load((Path(root) / ".run" / "config.yaml").read_text())
        cfg["domains"]["consult"] = False
        cfg["domains"].pop("narrate", None)
        self.frames, self.lock = [], threading.Lock()
        self.live = Live(cfg, NoModel(), emit=self._emit)
        self.live.journal.emit = self._emit
        self.smap_path = Path(root) / "domains" / "hier" / ".map.json"
        threading.Thread(target=self.live.run, daemon=True, name="agent").start()
        self.live.started.set()

    def _emit(self, ev, f, **kw):
        with self.lock:
            self.frames.append(dict(f, ev=ev, t=time.time()))

    def call(self, fn, *args):
        q = queue.Queue()
        self.live.jobs.put(("call", fn, args, q.put))
        return q.get(timeout=120)

    def mark(self):
        with self.lock:
            return len(self.frames)

    def since(self, k):
        with self.lock:
            return list(self.frames[k:])

    def wait(self, pred, k, timeout=40):
        end = time.time() + timeout
        while time.time() < end:
            for f in self.since(k):
                if pred(f):
                    return f
            time.sleep(0.05)
        return None

    def sessions(self):
        return {n: id(a.repl) for n, a in self.live.agents.agents.items()}

    def belief(self):
        import yaml
        d = json.loads(self.smap_path.read_text())
        card = yaml.safe_load((self.smap_path.parent / "task" / "intent.yaml").read_text())
        return {"belief": d["belief"], "things": sorted(d["things"]), "binding": {r: h for r, h in d["binding"].items() if not r.startswith("l")},
                "looked": d.get("looked", {}), "resolved": d.get("resolved", {}), "card": card["slots"]["object"]["enum"]}


END = ("over", "done", "stuck", "asking")


def fetch(ag, obj, rec, iid):
    k = ag.mark()
    err = ag.call(ag.live.typed, "task", iid, {"intent": "FETCH", "object": obj.upper(), "receptacle": rec.upper()})
    end = ag.wait(lambda f: f.get("ev") == "world/status" and f.get("state") in END, k)
    return k, err, end


def record(ag, k, before, sess0, err, end, t0):
    fr = ag.since(k)
    recs = [f.get("rec") or f for f in fr if f.get("ev") == "journal"] + [f for f in fr if f.get("kind", "").startswith("dlg-")]
    verbs = {}
    for r in recs:
        if r.get("kind") == "dlg-domain":
            key = "%s %s" % (r.get("verb"), r.get("domain"))
            verbs[key] = verbs.get(key, 0) + 1
    said = []
    for f in fr:
        if f.get("ev") == "journal" and (f.get("rec") or {}).get("kind") == "dlg-say":
            said.append(f["rec"].get("text"))
    lines = [f.get("text") for f in fr if f.get("ev") == "line" or (f.get("ev") == "narration" and f.get("text"))]
    goals = [f.get("goal") for f in fr if f.get("ev") == "world/status" and f.get("goal")]
    return {"error": err, "end": {k2: (end or {}).get(k2) for k2 in ("state", "text", "options")}, "seconds": round(time.time() - t0, 2),
            "verbs": verbs, "reloads": sum(n for v, n in verbs.items() if v.startswith("reload ")),
            "said": said or lines, "goals": goals, "belief_before": before, "belief_after": ag.belief(),
            "same_sessions": ag.sessions() == sess0, "kinds": sorted({(f.get("rec") or {}).get("kind") for f in fr if f.get("ev") == "journal"} - {None})}


def run(root, cases, out=None):
    ag = Agent(root)
    res = {}
    for i, case in enumerate(cases):
        if case != "new":
            k = ag.mark()
            ag.call(ag.live.new_game)
            ag.wait(lambda f: f.get("ev") == "world/status" and f.get("state") == "waiting", k, timeout=60)
            time.sleep(1.0)
        sess0 = ag.sessions()                       # after the reset: a new game reloads the task and the director (its own rows)
        if case.startswith("revisit"):              # a changed belief: where the thing was last found after a reset
            d = json.loads(ag.smap_path.read_text())
            t = d["resolved"]["tomato"]               # the tomato "a tomato" resolves to: the one the last run took
            home = HOME[t]                            # … where a reset puts it back, as the moved run found it
            d["belief"][t] = {home: 0.8, "countertop1": 0.2} if case == "revisit" else {"countertop1": 0.8, home: 0.2}
            d["looked"].pop(t, None)
            ag.smap_path.write_text(json.dumps(d, indent=1, sort_keys=True))
        if case == "lost":                          # the belief exhausted: every place looked into, the tomato in none
            d = json.loads(ag.smap_path.read_text())
            for o in list(d["belief"]):
                if o.startswith("tomato"):
                    d["looked"][o] = sorted(set(d["looked"].get(o, [])) | set(d["belief"][o]))
                    d["belief"][o] = {}
            ag.smap_path.write_text(json.dumps(d, indent=1, sort_keys=True))
        before, t0 = ag.belief(), time.time()
        k, err, end = fetch(ag, "tomato", "microwave1", "c%d" % (i + 1))
        if end is None:                             # stalled: what each session holds, for the record
            for n, a in ag.live.agents.agents.items():
                held = sorted(x for x, c in a.repl.counts.items() if c > 0 and not x.startswith(("notdest(", "nottarget(")))
                print("   stalled %s: %s" % (n, held[:60]))
            print("   binding", json.loads(ag.smap_path.read_text())["binding"])
        time.sleep(1.0)
        res[case] = record(ag, k, before, sess0, err, end, t0)
        r = res[case]
        print("== %s: %s %r in %.1fs; reloads %d; same sessions %s" % (case, r["end"]["state"], r["end"]["text"], r["seconds"],
                                                                     r["reloads"], r["same_sessions"]))
        print("   verbs", r["verbs"])
        print("   goals", r["goals"])
        print("   said", r["said"][:20])
        print("   belief before", json.dumps(before["belief"])[:300])
        print("   belief after ", json.dumps(r["belief_after"]["belief"])[:300])
        print("   card", before["card"], "->", r["belief_after"]["card"], "; journal kinds", r["kinds"])
    if out:
        Path(out).write_text(json.dumps(res, indent=1, default=str))
    ag.live.stop.set()
    return res


if __name__ == "__main__":
    import logging
    logging.basicConfig(level=os.environ.get("SM_LOG", "WARNING"), format="%(asctime)s %(message)s")
    if sys.argv[1] == "setup":
        setup(sys.argv[2], view="--all" not in sys.argv)
    else:
        args = [a for a in sys.argv[3:] if not a.startswith("--") and a != (sys.argv[sys.argv.index("--out") + 1] if "--out" in sys.argv else None)]
        run(sys.argv[2], args or ["new", "moved", "revisit", "revisit-wrong", "lost"], sys.argv[sys.argv.index("--out") + 1] if "--out" in sys.argv else None)
