"""cards.py — how a road scenario becomes a run (metis-plugin s-df4ff191: scenario running is the DOMAIN's, separate from
the runtime): a catalog card by id (road/catalog/**/<ID>.yaml; scenario_run's kinds) or a scenario name -> road_tree's
scenario, its host, ticks and window stop; the card's standing on the run (scenario_run's measures); rulecheck's
European road rules over the run's log.

    plan(spec) -> (scenario, host, ticks, stop_after, env, card | None, kind)    spec: card | scenario, host, ticks, site
    check_of(card, kind, scenario, summary) -> {standing, fails, detail} | None
    broken_rules(log, net) -> [(k, rule, words)]

- a CARLA card on a town: on SUMO one site (SITE, default the first) as card:NAME@TOWN#SITE; on the exerciser card:NAME
- a card on a stored net: cr:ID, its directory the conversion cache, scenario_run's window stop (30 s)
- a level-k intersection card: ix:NAME:LEVEL on the exerciser, its first level"""
import importlib.util
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROAD = HERE.parent
sys.path.insert(0, str(ROAD / "world"))
DT = 0.1


def _mod(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def card_path(cid):
    hits = sorted(p for p in (ROAD / "catalog").rglob("%s.yaml" % cid) if "sites" not in p.parts)
    if not hits:
        raise SystemExit("run_card: no card %s under road/catalog" % cid)
    return hits[0]


def plan(spec):
    """→ (scenario name for road_tree, host, ticks, stop_after, env, card dict | None, kind)."""
    host = spec.get("host") or "sumo"
    if spec.get("scenario"):
        return spec["scenario"], host, int(spec.get("ticks") or 1500), None, {}, None, "scenario"
    SR = _mod("scenario_run", ROAD / "tools" / "scenario_run.py")
    card = SR.load(card_path(spec["card"]))
    if SR.on_net(card):
        net = SR.card_file(card, card["map"]["net"])
        return ("cr:" + net.parent.name, "sumo", int(spec.get("ticks") or card.get("ticks") or 1500), 30.0,
                {"COMMONROAD_CACHE": str(net.parent.parent)}, card, "net")
    if SR.on_world(card):
        sys.path.insert(0, str(ROAD / "intersection"))
        import intersection as I
        lv = I.levels_of(card)[0]
        return ("ix:%s:%s" % (card["scenario"], lv), "exerciser", int(spec.get("ticks") or card.get("ticks") or 600), None,
                {}, card, "world")
    sc = _mod("scenarios", ROAD / "experiments" / "scenarios.py")
    if host == "sumo":
        runs = SR.town_runs(card, "sumo")
        i = int(spec.get("site") or 0)
        name = runs[min(i, len(runs) - 1)]
    else:
        name = card["scenario"]
    return "card:" + name, host, int(spec.get("ticks") or sc.ticks_of(card, host)), None, {}, card, "town"


def check_of(card, kind, name, res):
    """The card's standing on this run (scenario_run's measures), {standing, fails}; None for a bare scenario."""
    if card is None:
        return None
    SR = _mod("scenario_run", ROAD / "tools" / "scenario_run.py")
    if kind == "town":
        sc = _mod("scenarios", ROAD / "experiments" / "scenarios.py")
        import scenario_cards as C
        r = sc.row(C.load(card["scenario"]), name[len("card:"):], res)
        row = {"card": SR.card_id(card), "fails": r["fails"], "arrived": r["arrived"], "collisions": r["collisions"],
               "collision_events": r["collision_events"], "violations": r["violations"], "lb": r["lb"], "rc": r["rc"],
               "ds": r["ds"], "summary": res}
    elif kind == "world":
        sys.path.insert(0, str(ROAD / "intersection"))
        import intersection as I
        row = {"card": SR.card_id(card), "fails": I.check(card, res), "arrived": res.get("arrived"),
               "collision_events": res.get("collision_events"), "violations": res.get("violations"), "summary": res}
    else:
        B = SR.batch_mod()
        job = {"id": name[3:], "set": (card.get("source") or {}).get("set"), "source": (card.get("source") or {}).get("suite"),
               "country": name[3:].split("_")[0], "tags": card.get("tags") or []}
        row = B.make_row(job, None, 1, B.now(), res.get("wall_s") or 0.0, res, "", 0, False)
        row["fails"] = row.get("fails") or ([] if row.get("verdict") in (None, "pass") else [row.get("verdict")])
    try:
        st = SR.standing(card, row, None)
    except Exception as e:                                       # a measure the row lacks: the standing unknown, said so
        st = "unknown (%s)" % e
    detail = st if isinstance(st, dict) else {}
    if isinstance(st, dict):                                     # scenario_run's standing: {status, rule?, ...}
        st = st.get("status")
    return {"standing": st, "fails": [str(f) for f in row.get("fails") or []], "detail": detail}


def broken_rules(log, net):
    """rulecheck's European rules over the run's log: [(tick, rule, words)]."""
    rc = _mod("rulecheck", ROAD / "tools" / "rulecheck.py")
    rows = [json.loads(l) for l in open(log)] if Path(log).is_file() else []
    ticks = [r for r in rows if "v" in r and "lane" in r and "t" in r]
    if not ticks or not net or not Path(net).is_file():
        return []
    out = rc.check(ticks, rc.read_net(net))
    k = lambda t: int(round(float(t) / DT))
    found = [(k(t), "change at the stop line", "%s -> %s at %.1f m/s" % (a, b, v)) for t, a, b, v in out["change_at_line"]]
    found += [(k(t), "abrupt braking", "%.1f -> %.1f m/s in one tick on %s" % (a, b, ln)) for t, a, b, ln in out["abrupt"]]
    counted = [("red light entries", out["red_entries"]), ("amber entries", out["amber_entries"]),
               ("ticks over the speed limit", out["over_limit"]), ("lane changes inside a junction", out["change_in_junction"])]
    end = max((k(r["t"]) for r in ticks), default=0)
    found += [(end, name, "%d over the run" % n) for name, n in counted if n]
    return found


def slug(text):
    return "".join(c if c.isalnum() else "-" for c in str(text).lower()).strip("-")[:40]
