"""scenarios.py — every scene card (road/scenarios/*.yaml) and its generated variants run by the road family on a world,
one row per run: arrived, collisions, violations, the planner's commands, the card's expectation, the Leaderboard
2.0's infractions and Driving Score beside ours (road-scenarios s-e23be780 step 2). Run from metis-agent/py's venv
(road_tree's Live), METIS_HOME at the road family when the checkout is not beside metis-catalog.

    python road/experiments/scenarios.py OUT [--cards NAME,…] [--no-variants] [--seed N] [--world exerciser|sumo] [--trace DIR]
    → OUT/scenarios.jsonl (a row per run) and OUT/scenarios.md (the table)
"""
import argparse
import importlib.util
import json
import sys
from pathlib import Path

ROAD = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROAD / "world"))
import scenario_cards as C  # noqa: E402

TIMEOUT_S = 240.0                     # ScenarioTimeout(240) of the obstacle cards (route_obstacles.py:89)


def road_tree():
    spec = importlib.util.spec_from_file_location("road_tree", ROAD / "experiments" / "road_tree.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def infractions(card, out):
    """The Leaderboard's infractions this run shows, as far as the exerciser can count them: a vehicle collision per
    collision EVENT (contact with the same other within 5 s is one, CARLA's CollisionTest; nina's review), a scenario
    timeout when the card has one and the ego did not pass within it."""
    inf = {}
    n = out.get("collision_events", out.get("collisions"))
    if n:
        inf["collisions_vehicle"] = n
    timeouts = [x for x in (card.get("infractions") or {}).get("scenario") or [] if isinstance(x, dict) and "scenario_timeout" in x]
    if timeouts and (card.get("expect") or {}).get("arrived") and not out.get("arrived"):
        inf["scenario_timeouts"] = 1
    return inf


def row(card, name, out):
    fails = C.check(card, out, arrived=out.get("arrived"))
    inf = infractions(card, out)
    done = 100.0 if out.get("arrived") or not (card.get("expect") or {}).get("arrived") else 0.0
    return {"card": card["scenario"], "variant": card.get("variant") or "", "run": name, "arrived": out.get("arrived"),
            "t": out.get("t"), "collisions": out.get("collisions"), "collision_events": out.get("collision_events"),
            "violations": out.get("violations"),
            "planner": out.get("planner_kinds"), "responder": out.get("responder_kinds"), "first": out.get("first"), "fails": fails,
            "lb": inf, "ds": C.driving_score(inf, done), "exercises": card.get("exercises")}


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("out")
    ap.add_argument("--cards", help="NAME,… (default: every card)")
    ap.add_argument("--no-variants", action="store_true")
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--world", default=None, help="sumo: the SUMO host (default: the exerciser)")
    ap.add_argument("--trace", help="a directory: each run's trace (metis.trace) under it")
    a = ap.parse_args(argv)
    out_dir = Path(a.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    rt = road_tree()
    rows = []
    for n in (a.cards.split(",") if a.cards else C.names()):
        card = C.load(n)
        if (card.get("exerciser") or {}).get("skip") and a.world != "sumo":
            continue
        runs = [n] + ([] if a.no_variants else ["%s:%s" % (n, v) for v in C.variants(card)])
        for name in runs:
            c = C.load(name)
            res = rt.run("card:" + name, a.seed, out_dir / "runs", ticks=int(c.get("ticks", 1500)), world_kind=a.world,
                         trace=a.trace)
            r = row(c, name, res)
            rows.append(r)
            print(json.dumps(r), flush=True)
    (out_dir / "scenarios.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows))
    lines = ["| card | variant | arrived | t | contact ticks | collisions (events) | violations | planner | card's expect | LB infractions | DS |",
             "|---|---|---|---|---|---|---|---|---|---|---|"]
    for r in rows:
        lines.append("| %s | %s | %s | %s | %s | %s | %s | %s | %s | %s | %s |" % (
            r["card"], r["variant"] or "(as the source)", r["arrived"], r["t"], r["collisions"], r["collision_events"], r["violations"],
            ",".join(r["planner"] or []), "; ".join(r["fails"]) or "held",
            ", ".join("%s %s" % kv for kv in r["lb"].items()) or "—", r["ds"]))
    (out_dir / "scenarios.md").write_text("\n".join(lines) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
