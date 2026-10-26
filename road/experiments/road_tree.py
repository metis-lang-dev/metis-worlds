"""road_tree.py — the road domains' TREE DEMO on the exerciser (road-world s-e812715d step 2): metis-catalog domains/road
(responder, planner, road_director) on metis-agent's Live with domains.tick (the specialist tree: the director's
grants, priority(responder, planner), the responder's clock every step, the planner's every tenth), the world the
exerciser (road/world: road_world through road_host). No model, no person: the planner drives itself to the
destination, the responder answers the situation layer.

    cd metis-agent/py && METIS_CATALOG=<metis-catalog> PYTHONPATH=$PWD:<worlds>/libs/semantic-world \\
        .venv/bin/python <worlds>/road/experiments/road_tree.py SCENARIO SEED [SEED …] [--ticks N] [--out DIR] \\
        [--world sumo] [--vehicles N]

--world sumo runs nina's SUMO loop (road_host.new_world) in place of the exerciser; --vehicles goes into its run spec.

One process runs the seeds one after another (a run is its own key in road_host.SHARED). Per run, one JSON line: the
world's summary (collisions, violations, restricted, arrived, t), the journal's (grants, preempts, the responder's
commands, the planner's, the ping-pong count: a planner command revoked by the responder and the planner's next one
re-issued within the responder's hold), the latency from the first tick a response is asked to the first brake the
responder commands (in ticks, against ρ = 2), and the beats per domain."""
import json
import os
import sys
import tempfile
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
WORLD = HERE.parent / "world"
sys.path.insert(0, str(WORLD))
os.environ.setdefault("METIS_ROAD_WORLD", str(WORLD))
NAMES = ["responder", "planner", "road_director"]


class NoModel:
    BOOK = ("begin_dialog", "inject")

    def sibling(self, n):
        return self

    def __getattr__(self, name):
        if name in self.BOOK:
            return lambda *a, **k: 0
        raise RuntimeError("the model is not loaded (%s)" % name)


def run(scenario, seed, out_dir, ticks=1500, world_kind=None, vehicles=None):
    from metis_agent import service as S
    import road_host
    out_dir.mkdir(parents=True, exist_ok=True)
    spec = out_dir / ("%s-%d.json" % (scenario, seed))
    log = out_dir / ("%s-%d.jsonl" % (scenario, seed))
    if log.exists():
        log.unlink()
    run_spec = {"scenario": scenario, "seed": seed, "log": str(log), "key": "%s-%d-%f" % (scenario, seed, time.time())}
    if world_kind:
        run_spec["world"] = world_kind
    if vehicles is not None:
        run_spec["vehicles"] = vehicles
    spec.write_text(json.dumps(run_spec))
    os.environ["METIS_ROAD_RUN"] = str(spec)
    agent = Path(S.__file__).resolve().parents[1]
    cfg = S.load_config(agent / "config.live.yaml")
    cfg["intent"] = {"grammar": str(agent.parent / "go" / "grammar" / "e11-next.gbnf")}
    cfg["v3"].update(journal=str(out_dir / ("j-%s-%d.jsonl" % (scenario, seed))), catalog=[], loaded=NAMES, director="road_director")
    cfg["domains"].update(names=NAMES, narrate=None, consult=False, records=None, quiet=[], pairs=[], seed=seed,
                          clocks=[{"domain": d, "n": 1} for d in NAMES], tick=True)
    lv = S.Live(cfg, NoModel())
    for ag in lv.agents.agents.values():
        ag.watch.blind = True                       # a world that moves by itself: no surprise from its motion
    key = json.loads(spec.read_text())["key"]
    world = road_host.SHARED[key]["world"]
    t0 = time.perf_counter()
    for _ in range(ticks):
        lv.tick()
        if world.arrived():
            break
    wall = time.perf_counter() - t0
    recs = list(lv.journal.recs)
    out = report(world, recs, log, wall)
    close = getattr(world, "close", None)          # one SUMO at a time: the next seed's world opens after this one shuts
    if close:
        close()
    road_host.SHARED.pop(key, None)
    return out


def report(world, recs, log, wall):
    rows = [json.loads(l) for l in open(log)] if log.exists() else []
    steps = [r for r in rows if "resp" in r]
    cmds = [r for r in rows if "command" in r]
    first_resp = next((i for i, r in enumerate(steps) if r["resp"] != "none"), None)
    first_brake = next((r["t"] for r in cmds if r["member"] == "responder" and r["command"][0] == "brake"), None)
    lat = None
    if first_resp is not None and first_brake is not None:
        lat = round(round(first_brake / 0.1) - (first_resp + 1), 0)
    relay = [r for r in recs if r.get("kind") == "dlg-relay"]
    grants = [(r["stamp"], r["what"], r["domain"]) for r in relay if r.get("what") in ("grant", "revoke")]
    pre = sum(1 for r in recs if r.get("kind") == "dlg-trace" and r.get("domain") == "road_director"
              for row in r.get("fired") or [] if str(row.get("event", "")).startswith("preempt"))
    beats = {}
    for r in recs:
        if r.get("kind") == "dlg-trace":
            beats[r["domain"]] = beats.get(r["domain"], 0) + 1
    # ping-pong: the planner's command, then the responder's within its hold, then the planner's same command again
    pp, last = 0, None
    for r in cmds:
        if r["member"] == "planner":
            if last and last[0] == "responder" and last[1] is not None and last[1] == r["command"]:
                pp += 1
            last = ("planner", r["command"])
        elif r["member"] == "responder":
            last = ("responder", last[1] if last else None)
    s = world.summary()
    s.update({"wall_s": round(wall, 2), "ticks": world.tick, "grants": len([g for g in grants if g[1] == "grant"]),
              "preempts": pre, "responder_cmds": sum(1 for r in cmds if r["member"] == "responder"),
              "planner_cmds": sum(1 for r in cmds if r["member"] == "planner"),
              "planner_kinds": sorted({r["command"][0] for r in cmds if r["member"] == "planner"}),
              "responder_kinds": sorted({r["command"][0] for r in cmds if r["member"] == "responder"}),
              "latency_ticks": lat, "ping_pong": pp, "trace_rows": beats})
    return s


def main(argv):
    opts, args, it = {}, [], iter(argv)
    for a in it:
        if a.startswith("--"):
            opts[a] = next(it)
        else:
            args.append(a)
    ticks = int(opts.get("--ticks", 1500))
    world_kind = opts.get("--world")
    vehicles = int(opts["--vehicles"]) if "--vehicles" in opts else None
    out = Path(opts["--out"]) if "--out" in opts else Path(tempfile.mkdtemp(prefix="road-tree-"))
    scenario, seeds = args[0], [int(x) for x in args[1:]] or [1]
    for seed in seeds:
        print(json.dumps(run(scenario, seed, out, ticks, world_kind, vehicles)))
        sys.stdout.flush()


if __name__ == "__main__":
    main(sys.argv[1:])
