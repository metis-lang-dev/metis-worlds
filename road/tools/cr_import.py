"""cr_import.py — CommonRoad scenarios into OUR catalog as scenario cards v2 (scenario-catalog s-92e0b650 step 3, nina;
road/docs/SCENARIO-CARD.md is the format).

    python road/tools/cr_import.py card ID [ID ...] [--round DIR] [--out road/catalog/commonroad]   one card per id
    python road/tools/cr_import.py select ROUND [--n 200] [--seed 1] [--out FILE]                       the selection's ids
    python road/tools/cr_import.py import ROUND [--n 200] [--out road/catalog/commonroad]               select, then card each

A CARD is `<out>/<id>.yaml` with `<out>/<id>/` beside it: the stored converted net and cr.json (the conversion cache's,
road/tools/cr_convert.py; cr_world reads them), one trajectory file per obstacle (obstacles/<obstacle>.jsonl: t, x, y, heading, v
per step), and NOTICE (the CommonRoad repository's BSD-3 license text, verbatim: the license asks for it on redistribution).
- source: suite commonroad, type the set/source (recorded / scenario-factory …), code the scenario file's path in its checkout,
  pin the repository's commit (road/docs/commonroad.md), license the notice's line; source.tags the scenario's own tags.
- map: net + data (the stored files); ego: at {lane, s} and route from cr_world.place (the converter's lanelet maps), v, and
  the goal from the planning problem (time in seconds from the start; a goal without a region is time-only, §3).
- actors: every obstacle; mode recorded (a trajectory to play) for the recorded sets, model for an interactive scenario's
  one-state obstacle (SUMO's to drive: cr-harvest-4), static for a static one; kind from CommonRoad's type.
- tags (§5's vocabulary only): from the scene (intersections, signs, lights, right_before_left, the obstacles' kinds, the
  scenario's tags) and from the harvest's mechanism (the cluster the row falls in); patches [] (a person adds to it, §4).
- verdict: per host (§6b): sumo from the harvest's row of the id in ROUND (pass | soft | fail | world), with since {worlds,
  catalog} from the row; absent when no round is given or the id has no row there (the runner writes it otherwise, §6); no
  exerciser entry (it cannot play a CommonRoad map).

The SELECTION over a triaged round (cr_triage's clusters.json + rows): one card per cluster (its representative; no-record
clusters out), then a stratified sample over (country, map type) of the rest: every stratum at least one, the remainder in
proportion, the total N (150-300). Deterministic for a seed."""
import argparse
import json
import random
import shutil
import sys
from pathlib import Path

ROAD = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROAD / "world"))
sys.path.insert(0, str(ROAD / "tools"))
CATALOG = ROAD / "catalog" / "commonroad"
CHECKOUT = Path("/bigdata/datasets/commonroad")
PINS = {"scenarios": ("commonroad-scenarios 2416dc27faf3ee36b6799f42712da72a34a2c8fd", "LICENSE.txt"),
        "interactive": ("commonroad-interactive-scenarios 749e342013cc069980039fa91ba587f62993aaaf", "LICENSE")}
LICENSE_LINE = {"scenarios": "CommonRoad scenarios, BSD 3-Clause License, Copyright (c) 2019 Technical University of Munich",
                "interactive": "CommonRoad interactive scenarios, BSD 3-Clause License, Copyright (c) 2023 Technical University of Munich"}
KIND = {"car": "car", "truck": "truck", "bus": "truck", "bicycle": "bicycle", "motorcycle": "car", "pedestrian": "pedestrian",
        "priorityVehicle": "emergency", "taxi": "car", "parkedVehicle": "static", "constructionZone": "static",
        "roadBoundary": "static", "building": "static", "pillar": "static", "median_strip": "static"}
# §5's vocabulary from a CommonRoad scenario tag (source.tags keeps the scenario's own)
TAG_FROM_SOURCE = {"turn_left": "turning-left", "turn_right": "turning-right", "lane_change": "lane-change",
                   "merging_lanes": "merge-zipper", "roundabout": "roundabout", "illegal_cutin": "cut-in",
                   "slip_road": "highway-ramp", "traffic_jam": "following", "emergency_braking": "following",
                   "oncoming_traffic": "oncoming-pass", "intersection": "junction-priority"}
# §5's vocabulary from the harvest's mechanism (the cluster's measure and member)
TAG_FROM_MECHANISM = {"contact:side": "junction-priority", "contact:front": "following", "contact:behind": "following",
                      "goal:position": "route-following", "off_lanelet": "lane-keeping"}
VOCAB = {"following", "lane-keeping", "lane-change", "overtaking", "oncoming-pass", "cut-in", "merge-zipper",
         "junction-priority", "right-before-left", "stop-sign", "yield-sign", "traffic-light", "turning-left", "turning-right",
         "roundabout", "pedestrian-crossing", "cyclist", "emergency-vehicle", "parking", "obstacle-static", "route-following",
         "speed-limit", "visibility", "highway-ramp"}


# ── the scene ──
def repo_of(doc):
    src = str(doc.get("source") or "")
    return "interactive" if "/interactive/" in src or doc.get("interactive") else "scenarios"


def set_of(doc):
    """The scenario's set and source in its checkout (recorded / scenario-factory, interactive / SUMO …)."""
    parts = Path(str(doc.get("source") or "")).parts
    for key in ("recorded", "interactive", "hand-crafted"):
        if key in parts:
            i = parts.index(key)
            nxt = parts[i + 1] if i + 1 < len(parts) and not parts[i + 1].endswith((".xml", ".cr.xml")) else None
            return key if key != "hand-crafted" else "recorded", nxt or key
    return ("interactive" if doc.get("interactive") else "recorded"), "?"


def scene_tags(doc):
    """§5 tags the scene itself shows: its lights, stop / yield signs and speed limits, right-before-left junctions, its
    obstacles' kinds, the scenario's own tags mapped; route-following always (a CommonRoad card is a route to a goal)."""
    tags = {"route-following"}
    for t in doc.get("tags") or ():
        if t in TAG_FROM_SOURCE:
            tags.add(TAG_FROM_SOURCE[t])
    if doc.get("lights"):
        tags.add("traffic-light")
    if doc.get("right_before_left"):
        tags.add("right-before-left")
    for s in doc.get("signs") or ():
        for e in s.get("elements") or ():
            k = str(e.get("id", "")).upper()
            if k == "MAX_SPEED":
                tags.add("speed-limit")
            elif k in ("STOP", "206"):
                tags.add("stop-sign")
            elif k in ("YIELD", "205"):
                tags.add("yield-sign")
    for o in doc.get("obstacles") or ():
        kind = KIND.get(o.get("type"), "car")
        extra = {"pedestrian": "pedestrian-crossing", "bicycle": "cyclist", "emergency": "emergency-vehicle",
                 "static": "obstacle-static"}.get(kind)
        if extra:                                    # a car is no tag by itself: `following` comes from the mechanism or the source
            tags.add(extra)
    return tags


def goal_of(doc, k0, dt):
    """The planning problem's first goal in the card's terms (§3): region (lanelets or polygons), time [t0, t1] in seconds from
    the start, v and heading ranges; a goal without a region is time-only."""
    pp = doc["planning"][0]
    g = (pp.get("goals") or [{}])[0]
    out = {}
    if g.get("lanelets"):
        out["region"] = {"lanelets": list(g["lanelets"])}
    elif g.get("polygons"):
        out["region"] = {"polygons": g["polygons"]}
    if g.get("time"):
        out["time"] = [round((float(g["time"][0]) - k0) * dt, 3), round((float(g["time"][1]) - k0) * dt, 3)]
    if g.get("velocity"):
        out["v"] = list(g["velocity"])
    if g.get("orientation"):
        out["heading"] = list(g["orientation"])
    return out


def actors_of(doc, interactive, rel=""):
    """Every obstacle as a card actor: static, model (an interactive one-state obstacle: SUMO's to drive) or recorded."""
    out = []
    for o in doc.get("obstacles") or ():
        kind = KIND.get(o.get("type"), "car")
        traj = o.get("trajectory") or []
        first = traj[0] if traj else {}
        a = {"id": "cr%s" % o["id"], "kind": kind, "length": o.get("length"), "width": o.get("width"),
             "at": {"x": first.get("x"), "y": first.get("y"), "heading": first.get("theta")}, "v": first.get("v", 0.0)}
        if o.get("role") == "static" or kind == "static":
            a["mode"] = "static" if kind == "static" else "recorded"
            if kind == "static":
                a["kind"] = "static"
        elif interactive and len(traj) <= 1:
            a["mode"] = "model"
        else:
            a["mode"] = "recorded"
            a["trajectory"] = "%s/obstacles/cr%s.jsonl" % (rel, o["id"]) if rel else "obstacles/cr%s.jsonl" % o["id"]
        out.append(a)
    return out


# ── the verdict from a harvest row ──
def verdict_of(row, cluster=None):
    """The card's standing from the harvest's row (§6): pass | soft | fail | world, since the row's worlds and catalog pin."""
    if row is None:
        return None
    import cr_triage as T
    m = T.measure(row)
    if m is None:
        status = "pass"
    elif T.soft(m):
        status = "soft"
    elif m.startswith("error") or (cluster or {}).get("kind") == "world":
        status = "world"
    else:
        status = "fail"
    v = {"status": status, "since": {"worlds": row.get("worlds"), "catalog": row.get("pin")}}
    if status == "fail" and row.get("record_id"):
        v["record"] = row["record_id"]
    if status == "world":
        v["record"] = (cluster or {}).get("why") or m
    if m and status != "pass":
        v["note"] = m
    return v


# ── one card ──
def card(sid, cache, out=CATALOG, row=None, cluster=None, checkout=CHECKOUT, force=False):
    """Write the card of SID (its cr.json and net from CACHE/<sid>/) under OUT. → the card's path. A card already there (a
    hand-made one: george's three) is kept unless FORCE."""
    if (Path(out) / ("%s.yaml" % sid)).exists() and not force:
        return Path(out) / ("%s.yaml" % sid)
    import cr_world
    src = Path(cache) / sid
    doc = json.loads((src / "cr.json").read_text())
    net_file = src / doc.get("net", "%s.net.xml" % sid)
    sumolib = cr_world._sumolib()
    net = sumolib.net.readNet(str(net_file), withInternal=True)
    try:
        pl = cr_world.place(doc, net)
    except RuntimeError as e:                                  # no route / no goal edge: the card is still the scene, standing world
        pl = {"ego": None, "goal_edge": None, "route_note": str(e)}
    repo, (kind, source) = repo_of(doc), set_of(doc)
    pin, lic_file = PINS[repo]
    d = Path(out) / sid
    (d / "obstacles").mkdir(parents=True, exist_ok=True)
    shutil.copy2(net_file, d / net_file.name)
    shutil.copy2(src / "cr.json", d / "cr.json")
    for cfg in src.glob("*.sumo.cfg"):                      # the runner plays the card with its directory as the conversion cache
        shutil.copy2(cfg, d / cfg.name)
    notice = Path(checkout) / repo / lic_file
    (d / "NOTICE").write_text(("%s\n%s\n\n" % (LICENSE_LINE[repo], "The scenario and its map, converted to a SUMO net and cr.json; "
                                "the obstacles as the scenario states them.")) + (notice.read_text() if notice.is_file() else ""))
    for o in doc.get("obstacles") or ():
        traj = o.get("trajectory") or []
        if len(traj) > 1:
            (d / "obstacles" / ("cr%s.jsonl" % o["id"])).write_text("".join(json.dumps(
                {"t": round(p["k"] * doc["dt"], 3), "x": p["x"], "y": p["y"], "heading": p.get("theta"), "v": p.get("v")}) + "\n"
                for p in traj))
    pp = doc["planning"][0]
    k0, dt = pp["initial"].get("k", 0), doc["dt"]
    ego = {"v": round(pp["initial"].get("v") or 0.0, 3)}
    if pl.get("ego"):
        e = pl["ego"]
        ego.update(at={"lane": "%s_%d" % (e["edge"], e["lane"]), "s": round(e["pos"], 2)}, route=list(e["route"]))
    goal = goal_of(doc, k0, dt)
    if goal:
        ego["goal"] = goal
    tags = scene_tags(doc)
    if cluster and cluster.get("measure") in TAG_FROM_MECHANISM:
        tags.add(TAG_FROM_MECHANISM[cluster["measure"]])
    tags &= VOCAB
    rel = Path("catalog") / "commonroad" / sid
    c = {"card": 2, "scenario": sid,
         "title": "CommonRoad %s (%s / %s)" % (sid, kind, source),
         "source": {"suite": "commonroad", "type": "%s/%s" % (kind, source), "code": str(doc.get("source") or ""),
                    "pin": pin, "license": LICENSE_LINE[repo], "tags": list(doc.get("tags") or [])},
         "patches": [], "tags": sorted(tags),
         "exercises": "the family on CommonRoad's planning problem" + (": the harvest's mechanism %s (%s)" % (
             cluster["id"], cluster.get("measure")) if cluster else ""),
         "map": {"net": str(rel / net_file.name), "data": str(rel / "cr.json")},
         "dt": dt, "ticks": 1500, "ego": ego,
         "exerciser": {"skip": "a CommonRoad map: the exerciser has no net of its own"},
         "actors": actors_of(doc, bool(doc.get("interactive")), str(rel)),
         "expect": {"goal": True, "collisions": 0, "violations": 0, "off_lanelet": 0}}
    if pl.get("route_note"):
        c["map"]["route_note"] = pl["route_note"]
    v = verdict_of(row, cluster)
    if v:
        c["verdict"] = {"exerciser": "skip", "sumo": v}     # per host (spec §6b): the harvest ran on SUMO; the exerciser cannot play it
    import yaml
    path = Path(out) / ("%s.yaml" % sid)
    path.write_text(yaml.safe_dump(c, sort_keys=False, allow_unicode=True, width=140))
    return path


# ── the selection ──
def map_type(row, doc_tags=()):
    tags = set(row.get("tags") or ()) | set(doc_tags)
    for t in ("interstate", "highway", "intersection", "urban", "rural"):
        if t in tags:
            return t
    return "other"


def select(round_dir, n=200, seed=1):
    """The ids: one per cluster of ROUND's clusters.json (its representative; no-record and world clusters out), then a
    stratified sample over (country, map type) of the other rows: every stratum at least one, the rest in proportion, N in all."""
    import cr_triage as T
    data = json.loads((Path(round_dir) / "clusters.json").read_text())
    reps = [c["representative"]["id"] for c in data["clusters"] if c["kind"] not in (None, "no record", "world")]
    rows = [r for r in T.rows(round_dir) if not (T.measure(r) or "").startswith("error")]
    chosen = list(dict.fromkeys(reps))[:n]
    rest = [r for r in rows if r["id"] not in set(chosen)]
    strata = {}
    for r in rest:
        strata.setdefault((r.get("country") or r["id"].split("_")[0], map_type(r)), []).append(r["id"])
    rng = random.Random(seed)
    left = max(0, n - len(chosen))
    if left and strata:
        keys = sorted(strata)
        take = {k: 1 for k in keys}
        if left < len(keys):
            take = {k: 1 for k in rng.sample(keys, left)}
        else:
            spare = left - len(keys)
            total = sum(len(strata[k]) for k in keys)
            for k in keys:
                take[k] += int(spare * len(strata[k]) / total)
        for k in sorted(take):
            ids = sorted(strata[k])
            chosen += rng.sample(ids, min(take[k], len(ids)))
    return chosen[:n] if len(chosen) > n else chosen


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("card")
    c.add_argument("ids", nargs="+")
    c.add_argument("--cache", default=None, help="the conversion cache (default cr_world's)")
    c.add_argument("--round", help="a triaged harvest round: the verdict from its row")
    c.add_argument("--out", default=str(CATALOG))
    c.add_argument("--force", action="store_true", help="overwrite a card already in the catalog")
    s = sub.add_parser("select")
    s.add_argument("round")
    s.add_argument("--n", type=int, default=200)
    s.add_argument("--seed", type=int, default=1)
    s.add_argument("--out")
    i = sub.add_parser("import")
    i.add_argument("round")
    i.add_argument("--n", type=int, default=200)
    i.add_argument("--seed", type=int, default=1)
    i.add_argument("--cache", default=None)
    i.add_argument("--out", default=str(CATALOG))
    a = ap.parse_args(argv)
    import cr_world
    cache = getattr(a, "cache", None) or str(cr_world.CACHE)
    if a.cmd == "select":
        ids = select(a.round, a.n, a.seed)
        text = "\n".join(ids) + "\n"
        (Path(a.out).write_text(text) if a.out else sys.stdout.write(text))
        return 0
    rows, clus = {}, {}
    rnd = getattr(a, "round", None)
    if rnd:
        import cr_triage as T
        rows = {r["id"]: r for r in T.rows(rnd)}
        f = Path(rnd) / "clusters.json"
        if f.is_file():
            for cl in json.loads(f.read_text())["clusters"]:
                for sid in cl["scenarios"]:
                    clus[sid] = cl
    ids = a.ids if a.cmd == "card" else select(a.round, a.n, a.seed)
    done, failed = 0, []
    for sid in ids:
        try:
            card(sid, cache, a.out, rows.get(sid), clus.get(sid), force=getattr(a, "force", False))
            done += 1
        except Exception as e:                                 # noqa: BLE001 — one scenario never stops the import
            failed.append((sid, str(e).splitlines()[0][:160]))
    print("cards %d, failed %d%s" % (done, len(failed), "".join("\n  %s: %s" % f for f in failed[:20])))
    return 0 if not failed else 1


if __name__ == "__main__":
    sys.exit(main())
