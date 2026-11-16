#!/usr/bin/env python3
"""run_card.py — ONE headless road run (metis-plugin s-df4ff191 v3: the road runtime's child; road_runtime.py starts one per
run, one at a time): a catalog card by id (or a scenario name), played by the road family through road_tree.run with its
trace written INTO the workspace, watched by observer.Observer; it reports on stdout, one JSON object per line:

    road/runtime/run_card.py '{"card": ID | "scenario": NAME, "seed": 1, "host": "sumo"|"exerciser", "site": I?,
                               "ticks": N?, "workspace": ROOT, "run": NAME?}'

    {"type": "started", "run", "scenario", "card", "seed", "host", "trace": "traces/<run>"}
    {"type": "status", "run", "tick", "counts"}             every STATUS_TICKS ticks
    {"type": "finding", "id", "ref", "key", "run", "kind", "window", "tick", "member", "words"}   after the trace is
        closed: the surprise WRITTEN into the workspace first (the SDK's drop_surprise(rec, key=), its window kept),
        then reported (the runtime signals surprise.new; spec SURPRISE-INTERFACE.md v1 §6)
    {"type": "ended", "run", "summary", "check": {standing, fails}, "trace"}
    {"type": "error", "run", "error"}                       the run could not be played (and the exit status is 1)

- the card: road/catalog/**/<ID>.yaml (scenario_run's kinds): a CARLA card on a town (on SUMO one site: SITE, default the
  first, as card:NAME@TOWN#SITE), a card on a stored net (cr:ID, its directory as the conversion cache, the window stop of
  scenario_run), a level-k intersection card (ix:NAME:LEVEL on the exerciser, its first level).
- the run's name: <scenario, ':' '@' '#' made '_'>-<seed>-<UTC stamp>, one directory under the workspace's traces/ (the
  page's convention), its config.yaml beside it (the judge's replay).
- a finding's KEY is deterministic: <run>:<kind>:<tick> (a broken rule: <run>:rule:<slug>:<tick>); the SDK gives the
  id, the existing one when a surprise has that key (one surprise by two paths); the member: the most worded firings in
  the window, never the director (member_of: the bridge's rule, until the SDK has it).
- the end: the card's own checks (scenario_run's standing: pass | soft | fail | world) and the road rules rulecheck counts
  over the run's log (SUMO): each timed item (a lane change at the stop line, an abrupt speed loss) a finding at its tick,
  the counted ones (red / amber entries, over the limit, a change in a junction) one finding at the end."""
import importlib.util
import json
import os
import shutil
import sys
import tempfile
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROAD = HERE.parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(ROAD / "world"))
import observer as O  # noqa: E402

STATUS_TICKS = 50


def _mod(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def emit(obj):
    sys.stdout.write(json.dumps(obj, default=str) + "\n")
    sys.stdout.flush()


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
    k = lambda t: int(round(float(t) / O.DT))
    found = [(k(t), "change at the stop line", "%s -> %s at %.1f m/s" % (a, b, v)) for t, a, b, v in out["change_at_line"]]
    found += [(k(t), "abrupt braking", "%.1f -> %.1f m/s in one tick on %s" % (a, b, ln)) for t, a, b, ln in out["abrupt"]]
    counted = [("red light entries", out["red_entries"]), ("amber entries", out["amber_entries"]),
               ("ticks over the speed limit", out["over_limit"]), ("lane changes inside a junction", out["change_in_junction"])]
    end = max((k(r["t"]) for r in ticks), default=0)
    found += [(end, name, "%d over the run" % n) for name, n in counted if n]
    return found


def slug(text):
    return "".join(c if c.isalnum() else "-" for c in str(text).lower()).strip("-")[:40]


def member_of(ws, run, k0, k1):
    """The member a window is about: the most worded firings in [k0, k1], never the director; else the most firings of
    any member but the director. (The bridge's rule, metis-agent mcp/bridge.py; to move into metispy's SDK.)"""
    from collections import Counter
    from metis import trace as T
    fired = Counter()
    for seg in T.read(ws.path("trace", run=run)):
        for t in seg.ticks:
            if k0 <= t.get("k", -1) <= k1:
                for m, v in (t.get("members") or {}).items():
                    for q in v.get("seq") or []:
                        for name in q.get("fired") or []:
                            fired[(m, name.split("[")[0])] += 1
    docs = {}
    for m in {m for m, _ in fired}:
        try:
            from metis import catalog
            from metis.domain.package import rule_docs
            docs[m] = rule_docs(catalog.get(m, ws.root).program)
        except Exception:
            docs[m] = {}
    worded, rest = Counter(), Counter()
    for (m, r), c in fired.items():
        if "director" in m:
            continue
        rest[m] += c
        if r in docs.get(m, {}):
            worded[m] += c
    best = worded or rest
    return best.most_common(1)[0][0] if best else None


def emit_finding(ws, b, run):
    """Write the finding as a surprise (its window kept by the SDK at the drop), then report it."""
    k0, k1 = b["window"]
    key = "%s:%s:%s%d" % (run, b["kind"], ("%s:" % slug(b["rule"])) if b.get("rule") else "", b["tick"])
    member = member_of(ws, run, k0, k1) or "road_director"
    rec = {"member": member, "trace": "traces/" + run, "window": [k0, k1], "k": b["tick"], "k0": k0, "words": b["words"],
           "reading": b["words"], "source": "runtime:road",
           "finding": {x: b[x] for x in ("kind", "scenario", "seed", "tick", "other", "what", "rule", "standing") if x in b}}
    if (ws.path("trace", run=run) / "config.yaml").is_file():
        rec["config"] = "traces/%s/config.yaml" % run
    try:
        sid = ws.drop_surprise(rec, who="world", key=key)
    except TypeError:                                            # an SDK before the key (metispy 5d14831): find it ourselves
        sid = next((s["id"] for s in ws.surprises() if s.get("key") == key), None) or ws.drop_surprise(dict(rec, key=key), who="world")
    out = dict(b, type="finding", id=sid, key=key, member=member, ref=str(ws.path("surprise", id=sid).relative_to(ws.root)))
    emit(out)
    return out


def run_name(scenario, seed):
    return "%s-%d-%s" % (scenario.replace(":", "_").replace("@", "_").replace("#", "_"), int(seed),
                         time.strftime("%Y%m%dT%H%M%S", time.gmtime()))


def main(spec):
    from metis.catalog import workspace as W
    ws = W.workspace(spec["workspace"])
    seed = int(spec.get("seed") or 1)
    scenario, host, ticks, stop_after, env, card, kind = plan(spec)
    os.environ.update(env)
    run = spec.get("run") or run_name(scenario, seed)
    dest = ws.path("trace", run=run)
    head = {"run": run, "scenario": scenario, "card": spec.get("card"), "seed": seed, "host": host,
            "trace": "traces/" + run}
    emit(dict(head, type="started"))
    rt = _mod("road_tree", ROAD / "experiments" / "road_tree.py")
    tmp = Path(tempfile.mkdtemp(prefix="road-runtime-"))
    obs = O.Observer(None, None, run, scenario, seed)
    state = {"world": None}

    def on_tick(world):
        state["world"] = world
        obs.tick(world)
        if getattr(world, "tick", 0) % STATUS_TICKS == 0:
            emit({"type": "status", "run": run, "tick": getattr(world, "tick", None), "counts": obs.counts()})
    try:
        res = rt.run(scenario, seed, tmp / "out", ticks=ticks, world_kind=host if host == "sumo" else None,
                     trace=str(tmp / "trace"), stop_after=stop_after, on_tick=on_tick)
        src = tmp / "trace" / ("%s-%d" % (scenario.replace(":", "_"), seed))
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(src), str(dest))
        log = tmp / "out" / ("%s-%d.jsonl" % (scenario, seed))
        w = state["world"]
        net = getattr(getattr(w, "world", None), "net", None)
        obs.rules(broken_rules(log, net))
        check = check_of(card, kind, scenario, res)

        class Sink:                                              # the findings: written, then reported
            def surprise(self, b):
                return emit_finding(ws, b, run)

            def event(self, b):
                emit(dict(b, type="event"))
        obs.sink = Sink()
        obs.end(res, check)
        obs.flush(res.get("ticks"))
        emit(dict(head, type="ended", summary=res, check=check))
        return 0
    except Exception as e:
        import traceback
        emit({"type": "error", "run": run, "error": "%s: %s" % (type(e).__name__, e), "where": traceback.format_exc()[-1500:]})
        return 1
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    sys.exit(main(json.loads(sys.argv[1])))
