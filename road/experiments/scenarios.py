"""scenarios.py — every scene card (road/scenarios/*.yaml) and its generated variants run by the road family on a world,
one row per run: arrived, collisions, violations, the planner's commands, the card's expectation, the Leaderboard
2.0's infractions and Driving Score beside ours (road-scenarios s-e23be780 step 2). Run from metis-agent/py's venv
(road_tree's Live), METIS_HOME at the road family when the checkout is not beside metis-catalog.

    python road/experiments/scenarios.py OUT [--cards NAME,…] [--no-variants] [--seed N] [--world exerciser|sumo] [--trace DIR]
                                             [--towns Town01,…] [--sites N]
    → OUT/scenarios.jsonl (a row per run) and OUT/scenarios.md (the table)
With --world sumo every card plays at each of its sites (card:NAME@TOWN#SITE, scenario_director: one SUMO at a time),
its variants at its first site; --sites N keeps the first N sites of each town.
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
    lb = (out.get("director") or {}).get("emergency_lb") or {}          # LB 2.0's own test (the architect's ruling on
    n = sum(1 for st in lb.values() if st.get("failure"))               # nina's 2b review); the held seconds are ours
    if "yield_emergency_vehicle" in ((card.get("infractions") or {}).get("scenario") or []) and n:
        inf["yield_emergency_vehicle_infractions"] = n
    return inf


def fired(card, out):
    """The director's triggers as the table reads them: "ID t s (TTA s)" per trigger that fired; "untriggered" when an
    armed trigger never fired (a held row is evidence only with its trigger fired: the architect's ruling)."""
    d = out.get("director")
    if not d:
        return None
    parts, seen = [], set()
    for f in d.get("triggered") or []:                                  # an armed trigger (an actor's several steps: once)
        if (f["id"], f["t"]) not in seen:
            seen.add((f["id"], f["t"]))
            parts.append("%s %.1f s%s" % (f["id"], f["t"], " (TTA %.1f)" % f["ego_tta"] if f.get("ego_tta") is not None else ""))
    timed = sorted({(t, i, w) for t, i, w in d.get("fired") or [] if w in ("brake", "lane", "go", "flow") and
                    not any(f["id"] == i for f in d.get("triggered") or [])})
    parts += ["%s %s %.1f s" % (i, w, t) for t, i, w in timed]           # a timed step (HardBreakRoute's brake at 5 s)
    if d.get("unfired"):
        parts.append("untriggered: " + ",".join(d["unfired"]))
    return "; ".join(parts) or "—"


def ticks_of(card, world):
    """The run's tick budget: the card's, or its SUMO one (a town's signal cycles and longer ways)."""
    if world == "sumo" and "ticks" in (card.get("sumo") or {}):
        return int(card["sumo"]["ticks"])
    return int(card.get("ticks", 1500))


def row(card, name, out):
    fails = C.check(card, out, arrived=out.get("arrived"))
    inf = infractions(card, out)
    # the Leaderboard's route completion: the share of the route driven (nina's 2b review), never 0 for a run that moved
    done = 100.0 if out.get("arrived") or not (card.get("expect") or {}).get("arrived") else float(out.get("rc") or 0.0)
    where = name.partition("@")[2]
    d = out.get("director") or {}
    fails = fails + (["untriggered"] if d.get("unfired") else [])
    return {"card": card["scenario"], "variant": card.get("variant") or "", "where": where, "run": name, "arrived": out.get("arrived"),
            "t": out.get("t"), "collisions": out.get("collisions"), "collision_events": out.get("collision_events"),
            "violations": out.get("violations"),
            "planner": out.get("planner_kinds"), "responder": out.get("responder_kinds"), "first": out.get("first"), "fails": fails,
            "lb": inf, "rc": done, "ds": C.driving_score(inf, done), "exercises": card.get("exercises"),
            "fired": fired(card, out), "removed": d.get("removed") or [],
            "held_s": round(sum((d.get("emergency_held_s") or {}).values()), 1) if d.get("emergency_held_s") is not None
            and any(a.get("kind") == "emergency" for a in card.get("actors") or []) else None,
            "director": out.get("director")}


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("out")
    ap.add_argument("--cards", help="NAME,… (default: every card)")
    ap.add_argument("--no-variants", action="store_true")
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--world", default=None, help="sumo: the SUMO host (default: the exerciser)")
    ap.add_argument("--trace", help="a directory: each run's trace (metis.trace) under it")
    ap.add_argument("--towns", help="Town01,… (SUMO: the towns played; default every town of a card's sites)")
    ap.add_argument("--sites", type=int, default=0, help="SUMO: the first N sites of each town (default all)")
    a = ap.parse_args(argv)
    out_dir = Path(a.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    rt = road_tree()
    rows = []
    for n in (a.cards.split(",") if a.cards else C.names()):
        card = C.load(n)
        if (card.get("exerciser") or {}).get("skip") and a.world != "sumo":
            continue
        if a.world == "sumo":
            places = ["%s#%s" % (town, p["i"]) for town in card["sites"]["towns"]
                      if not a.towns or town in a.towns.split(",")
                      for j, p in enumerate(C.sites(card, town)) if not a.sites or j < a.sites]
            if not places:
                continue
            runs = ["%s@%s" % (n, p) for p in places]
            runs += [] if a.no_variants else ["%s:%s@%s" % (n, v, places[0]) for v in C.variants(card)]
        else:
            runs = [n] + ([] if a.no_variants else ["%s:%s" % (n, v) for v in C.variants(card)])
        for name in runs:
            c = C.load(name.partition("@")[0])
            res = rt.run("card:" + name, a.seed, out_dir / "runs", ticks=ticks_of(c, a.world), world_kind=a.world,
                         trace=a.trace)
            r = row(c, name, res)
            rows.append(r)
            print(json.dumps(r), flush=True)
    (out_dir / "scenarios.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows))
    sumo = any(r.get("fired") is not None for r in rows)
    head = ["card", "variant", "where", "arrived", "t", "contact ticks", "collisions (events)", "violations", "planner", "responder",
            "card's expect", "LB infractions", "RC", "DS"] + (["fired (ego's TTA to the junction)", "removed at contact",
                                                               "held s (ours)"] if sumo else [])
    lines = ["| " + " | ".join(head) + " |", "|" + "---|" * len(head)]
    for r in rows:
        cells = [r["card"], r["variant"] or "(as the source)", r["where"] or "exerciser", r["arrived"], r["t"], r["collisions"],
                 r["collision_events"], r["violations"], ",".join(r["planner"] or []), ",".join(r.get("responder") or []), "; ".join(r["fails"]) or "held",
                 ", ".join("%s %s" % kv for kv in r["lb"].items()) or "—", r["rc"], r["ds"]]
        if sumo:
            cells += [r.get("fired") or "—", ", ".join("%s %.1f s" % (i, t) for t, i in r.get("removed") or []) or "—",
                      "—" if r.get("held_s") is None else r["held_s"]]
        lines.append("| " + " | ".join(str(x) for x in cells) + " |")
    (out_dir / "scenarios.md").write_text("\n".join(lines) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
