"""sumo_loop.py — the road's closed loop on SUMO (road-world s-e812715d step 4): the SUMO host's Loop per seed, the
ego's commands from a DRIVER, the accounting per seed and the ms table.

    python3 road/experiments/sumo_loop.py OUT [SEED …] [--driver plain] [--scenario straight] [--ticks N] [--vehicles 10]

Drivers:
  plain   the shield alone: a planner that asks `accel` every planner tick (10 responder ticks), no responder;
          what reaches SUMO is the restrictor's cut of it (the proper response's bound over the belief's fold)
The tree (opus's responder + planner under the director) runs through road_tree.py on the agent's Live, road_host's
members over the same Loop (the run spec's "world": "sumo").

Prints per seed: ticks, ego done, collisions (the ego's), violations, restricted, the latency (ticks from a truth
pair's first dangerous tick to the first braking applied; ρ = 10), ms per stage; writes OUT/seedN.json and OUT/log_N.jsonl.
One SUMO at a time (the seeds run in turn)."""
import argparse
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "world"))
import sumo_host  # noqa: E402

PLANNER_PERIOD = 10


def plain(loop):
    if loop.tick % PLANNER_PERIOD == 0:
        loop.cmd, loop.life = ("accel", None), PLANNER_PERIOD


DRIVERS = {"plain": plain}


def run(out, seed, driver="plain", scenario="straight", ticks=1500, vehicles=10):
    level = {"scenario": scenario, "seed": seed, "sensor": {"range": 60.0, "miss": 0.0}, "vehicles": vehicles}
    loop = sumo_host.Loop(level, os.path.join(out, "work_%d" % vehicles))
    try:
        while loop.tick < ticks:
            DRIVERS[driver](loop)
            if not loop.step() or loop.arrived():
                break
    finally:
        loop.close()
    sm = loop.summary()
    sm["driver"], sm["scenario"], sm["vehicles"] = driver, scenario, vehicles
    with open(os.path.join(out, "seed%d.json" % seed), "w") as f:
        json.dump(dict(sm, violations_all=loop.violations, optimistic_all=loop.optimistic), f, indent=1)
    with open(os.path.join(out, "log_%d.jsonl" % seed), "w") as f:
        for r in loop.log:
            f.write(json.dumps(r) + "\n")
    return sm


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("out")
    ap.add_argument("seeds", nargs="*", type=int, default=[1, 2, 3])
    ap.add_argument("--driver", default="plain")
    ap.add_argument("--scenario", default="straight")
    ap.add_argument("--ticks", type=int, default=1500)
    ap.add_argument("--vehicles", type=int, default=10)
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    for s in a.seeds:
        sm = run(a.out, s, a.driver, a.scenario, a.ticks, a.vehicles)
        lat = sm["latency_ticks"]
        print("== seed %d: ticks %d arrived %s collisions %d (all %d) violations %d optimistic %d restricted %d latency max %s n %d; "
              "ms %s; vehicles ≤ %d" % (s, sm["ticks"], sm["arrived"], sm["collisions"], sm["all_collisions"],
                                        sm["violations"], sm["optimistic"], sm["restricted"], max(lat) if lat else None, len(lat),
                                        sm["ms"], sm["vehicles_max"]))
        for v in sm["first"]:
            print("   ", v)
