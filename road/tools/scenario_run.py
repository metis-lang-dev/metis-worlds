"""scenario_run.py — the one runner of the scenario catalog (scenario-catalog s-92e0b650 step 2; the card: road/docs/SCENARIO-CARD.md).
A card is played on a host by the road family (road_tree's Live), measured once (the Leaderboard's, CommonRoad's, ours), given
its standing (pass | soft | fail | world) and compared with the card's `verdict`.

    road/tools/scenario_run.py run CARD.yaml [--host exerciser|sumo] [--seed S] [--out DIR] [--trace DIR]   one card → one row
    road/tools/scenario_run.py check CARD|DIR … [--host H] [--rows DIR]     every card's standing against its verdict; exit 1 on a move
    road/tools/scenario_run.py verdict CARD … [--host H]                   measure and write the card's verdict (with since)
    road/tools/scenario_run.py batch plan|work|launch|status|pull|recover …  cr_batch over cards (jobs carry the card's path)
    road/tools/scenario_run.py index [DIR]                                  road/catalog/index.json (id, source, tags, verdict, map)
    road/tools/scenario_run.py coverage [DIR] [--host H]                    tags x standings from the verdicts (CI's coverage)
    road/tools/scenario_run.py list [DIR] [--host sumo] [--set S] [--chunks N]  the cards a host plays, JSON (CI's matrix; N groups)
    road/tools/scenario_run.py sets [DIR]                                   the §6c default set: into every card without one

Two kinds of card, one row: a card on a town (the CARLA cards: map.town / sites, played as road_tree's `card:NAME`, measured by
scenario_cards.check as road/experiments/scenarios.py does) and a card on a stored net (map.net + map.data: played as `cr:ID`
with the card's own directory as the conversion cache, measured as the harvest's row, cr_batch.make_row). The world-fault rules
(SCENARIO-CARD §6a) are the runner's: `standing` names the rule in the row; cr_triage reads it."""
import argparse
import importlib.util
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROAD = Path(__file__).resolve().parents[1]
WORLDS = ROAD.parent
CATALOG = ROAD / "catalog"
sys.path.insert(0, str(ROAD / "world"))


def _mod(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def batch_mod():
    return _mod("cr_batch", ROAD / "tools" / "cr_batch.py")


def triage_mod():
    return _mod("cr_triage", ROAD / "tools" / "cr_triage.py")


# ── the card ──

def load(path):
    import yaml
    p = Path(path)
    card = yaml.safe_load(p.read_text())
    card["_path"] = str(p.resolve())
    card.setdefault("card", 1)
    return card


def card_id(card):
    p = Path(card["_path"])
    try:
        return str(p.relative_to(CATALOG).with_suffix(""))
    except ValueError:
        return card["scenario"]


def card_file(card, rel):
    """A path the card names: `catalog/...` from road/ (SCENARIO-CARD's examples), else from the card's own directory."""
    return ROAD / rel if str(rel).startswith("catalog/") else Path(card["_path"]).parent / rel


def on_net(card):
    return bool((card.get("map") or {}).get("net"))


def on_world(card):
    """A card on one of our own small worlds (`map: {world: intersection}`, road/intersection): the exerciser plays it."""
    return bool((card.get("map") or {}).get("world"))


def cards_in(paths):
    out = []
    for a in paths:
        p = Path(a)
        out += sorted(p.rglob("*.yaml")) if p.is_dir() else [p]
    return [x for x in out if x.name != "index.json" and "sites" not in x.parts]


# ── one run ──

def town_runs(card, host):
    """The runs of a card on a town (SCENARIO-CARD §6b (2)): the exerciser's `card:NAME`; on SUMO every site of the card's one
    `map.town` (else its sites' first town), `card:NAME@TOWN#SITE`."""
    import scenario_cards as C
    name = card["scenario"]
    if host != "sumo":
        return [name]
    towns = (card.get("sites") or {}).get("towns") or {}
    town = (card.get("map") or {}).get("town") or (sorted(towns)[0] if towns else None)
    if town is None:
        raise SystemExit("scenario_run: %s has no SUMO site" % name)
    return ["%s@%s#%s" % (name, town, p["i"]) for p in C.sites(C.load(name), town)]


def run_town(card, host, seed, out, trace):
    """A card on a town: road_tree's `card:NAME` per run (town_runs), measured as scenarios.py's row; on SUMO the WORST site
    decides (§6b (2)): the row is that site's, every site's fails beside it."""
    import scenario_cards as C
    sc = _mod("scenarios", ROAD / "experiments" / "scenarios.py")
    rt = sc.road_tree()
    c = C.load(card["scenario"])
    rows = []
    for name in town_runs(card, host):
        res = rt.run("card:" + name, seed, Path(out) / "runs", ticks=sc.ticks_of(c, host), world_kind=host if host == "sumo" else None,
                     trace=trace)
        r = sc.row(c, name, res)
        rows.append({"card": card_id(card), "host": host, "seed": seed, "run": name, "fails": r["fails"], "arrived": r["arrived"],
                     "collisions": r["collisions"], "collision_events": r["collision_events"], "violations": r["violations"],
                     "lb": r["lb"], "rc": r["rc"], "ds": r["ds"], "summary": res})
    worst = max(rows, key=lambda r: len(r["fails"]) > 0)
    worst["sites"] = {r["run"]: r["fails"] for r in rows}
    return worst


def run_net(card, host, seed, out, trace):
    """A card on a stored net: `cr:ID` on SUMO with the card's directory as the cache (no conversion), the harvest's row."""
    if host != "sumo":
        raise SystemExit("scenario_run: %s plays on a stored net: --host sumo" % card["scenario"])
    net = card_file(card, card["map"]["net"])
    cache, sid = net.parent.parent, net.parent.name
    B = batch_mod()
    env = B.env()
    env["COMMONROAD_CACHE"] = str(cache)
    run_dir = Path(out) / "runs" / sid
    run_dir.mkdir(parents=True, exist_ok=True)
    ticks = int(card.get("ticks") or 1500)
    cmd = [B.agent_py(), str(ROAD / "experiments" / "road_tree.py"), "cr:" + sid, str(seed), "--world", "sumo", "--ticks", str(ticks),
           "--out", str(run_dir), "--stop-after-window", "30"] + (["--trace", str(trace)] if trace else [])
    started = B.now()
    import time
    t0 = time.time()
    rc, out, err, timed_out = B.run_bounded(cmd, str(WORLDS), env, int(os.environ.get("CR_TIMEOUT", 900)))
    summ = B.last_json(out) if rc == 0 else None
    job = {"id": sid, "set": (card.get("source") or {}).get("set"), "source": (card.get("source") or {}).get("suite"),
           "country": sid.split("_")[0], "tags": card.get("tags") or []}
    row = B.make_row(job, None, seed, started, time.time() - t0, summ, err, rc, timed_out)
    row.update(card=card_id(card), host=host, run="cr:%s-%d" % (sid, seed))
    return row


def run_world(card, host, seed, out, trace):
    """A card on our level-k intersection (road/intersection): `ix:NAME:LEVEL` per variant (the others' level, params.level),
    road_tree's run on the exerciser; the WORST variant decides (as a town card's sites), every variant's measures beside."""
    if host != "exerciser":
        raise SystemExit("scenario_run: %s plays on the exerciser only" % card["scenario"])
    sys.path.insert(0, str(ROAD / "intersection"))
    import intersection as I
    sc = _mod("scenarios", ROAD / "experiments" / "scenarios.py")
    rt = sc.road_tree()
    rows = []
    for lv in I.levels_of(card):
        name = "ix:%s:%s" % (card["scenario"], lv)
        res = rt.run(name, seed, Path(out) / "runs", ticks=int(card.get("ticks") or 600), trace=trace)
        rows.append({"card": card_id(card), "host": host, "seed": seed, "run": name, "level": lv, "fails": I.check(card, res),
                     "arrived": res.get("arrived"), "collisions": res.get("collisions"),
                     "collision_events": res.get("collision_events"), "violations": res.get("violations"),
                     "deadlock_s": res.get("deadlock_s"), "delay": res.get("delay"), "drivers": res.get("drivers"),
                     "others_contacts": res.get("others_contacts"), "summary": res})
    worst = dict(max(rows, key=lambda r: len(r["fails"]) > 0))
    worst["fails"] = ["%s: %s" % (r["level"], f) for r in rows for f in r["fails"]]
    worst["levels"] = {r["level"]: {k: r[k] for k in ("fails", "arrived", "collision_events", "deadlock_s", "delay", "drivers")}
                       for r in rows}
    return worst


def run(card, host="exerciser", seed=1, out=None, trace=None):
    out = out or tempfile.mkdtemp(prefix="scenario-run-")
    row = (run_net if on_net(card) else run_world if on_world(card) else run_town)(card, host, seed, out, trace)
    row["standing"] = standing(card, row, trace)
    return row


# ── the standing: expect, and the world-fault rules (SCENARIO-CARD §6, §6a) ──

def world_fault(card, row, trace):
    """The rule's name when the world cannot pose the card honestly, else None. A row the run could not make; no route / no
    goal edge / a run of ticks <= 5 (cr_triage.no_goal); a contact whose partner the triage's world rules name (from behind,
    frozen, lane-jumping, a foe gap, a met cut-in, an unavoidable start, the ego standing, the initial state)."""
    err = row.get("error")
    if err and err.get("kind") in ("world", "convert"):
        return "%s: %s" % (err["kind"], err.get("line") or "")
    if not on_net(card):
        return None
    T = triage_mod()
    if T.no_goal(row):
        return "no route or no goal edge"
    if not trace or not set(row.get("failed") or []) & {"contact", "sumo_collision"}:
        return None
    runs = [d for d in Path(trace).iterdir() if d.is_dir()] if Path(trace).is_dir() else []
    if not runs:
        return None
    rec = {"id": None, "member": "responder", "trace": "traces/" + runs[0].name, "trace_path": str(runs[0])}
    keep = T.record_of
    T.record_of = lambda r: (rec, runs[0])
    try:
        k = T.kind_one(dict(row, summary=row.get("summary")))
    finally:
        T.record_of = keep
    return k.get("why") if k.get("kind") == "world" else None


def standing(card, row, trace=None):
    """pass | soft | fail | world (+ why) of a row against the card's expect."""
    w = world_fault(card, row, trace)
    if w:
        return {"status": "world", "why": w}
    if row.get("error"):
        return {"status": "error", "why": "%s: %s" % (row["error"].get("kind"), row["error"].get("line"))}
    if not on_net(card):
        fails = row.get("fails") or []
        return {"status": "fail", "why": "; ".join(fails)} if fails else {"status": "pass"}
    failed = row.get("failed") or []
    hard = [m for m in ("contact", "sumo_collision", "violation", "off_lanelet") if m in failed]
    if hard:
        return {"status": "fail", "why": ",".join(hard)}
    if "goal" in failed:
        g = row.get("goal") or {}
        if g.get("position_t") is not None or not (card.get("ego") or {}).get("goal", {}).get("region", True):
            return {"status": "soft", "why": "the goal's place reached, its window missed"}
        return {"status": "fail", "why": "goal: its place never reached"}
    return {"status": "pass"}


def since():
    head = subprocess.run(["git", "-C", str(WORLDS), "rev-parse", "--short=7", "HEAD"], capture_output=True, text=True).stdout.strip()
    return {"worlds": head, "catalog": (ROAD / "domains" / "catalog.pin").read_text().strip()[:7]}


def write_verdict(card, st, host):
    """The card's verdict block, rewritten in place (the rest of the file as the author wrote it): HOST's entry set, the other
    hosts' kept (SCENARIO-CARD §6b (1): verdict: {exerciser: {...}, sumo: {...}})."""
    import yaml
    p = Path(card["_path"])
    lines = p.read_text().splitlines()
    out, skip = [], False
    for ln in lines:
        if ln.startswith("verdict:"):
            skip = True
            continue
        if skip and (ln.startswith(" ") or not ln.strip()):
            continue
        skip = False
        out.append(ln)
    e = {"status": st["status"], "since": since()}
    if st.get("why"):
        e["note"] = st["why"][:200]
    old = card.get("verdict")
    v = {h: x for h, x in old.items() if h in HOSTS} if isinstance(old, dict) else {}
    v[host] = e
    out.append(yaml.safe_dump({"verdict": v}, sort_keys=False, allow_unicode=True).rstrip())
    p.write_text("\n".join(out) + "\n")


HOSTS = ("exerciser", "sumo")


def entry(card, host):
    """The card's verdict entry for HOST: a dict, the word "skip" (or {skip: why}), or None. A v2 verdict of one entry
    (status at the top) is read as the host's it was measured on: the card's sumo for a stored net, else the exerciser."""
    v = card.get("verdict")
    if not isinstance(v, dict):
        return None
    if "status" in v:
        return v if host == ("sumo" if on_net(card) else "exerciser") else None
    return v.get(host)


def skipped(card, host):
    e = entry(card, host)
    return e == "skip" or (isinstance(e, dict) and ("skip" in e or e.get("status") == "skip"))


SETS = ("regression", "working")


def card_set(card):
    """SCENARIO-CARD §6c: `set: regression | working`; a card without the field is working."""
    return card.get("set") if card.get("set") in SETS else "working"


def played(card):
    """The hosts the card plays (not skipped) with their verdict status."""
    return {h: expected(card, h) for h in HOSTS if entry(card, h) is not None and not skipped(card, h)}


def default_set(card):
    """regression iff every host the card plays stands at pass (and it plays at least one), else working (§6c defaults)."""
    st = played(card)
    return "regression" if st and all(v == "pass" for v in st.values()) else "working"


def format_error(card):
    """A regression card whose verdicts are not all pass/skip is a format error (§6c)."""
    if card_set(card) != "regression":
        return None
    bad = {h: v for h, v in played(card).items() if v != "pass"}
    return "set: regression but verdict %s" % ", ".join("%s %s" % kv for kv in sorted(bad.items())) if bad else None


def write_set(card, value):
    """The card's `set:` line, inserted before its verdict block (or at the end) when the card has none."""
    p = Path(card["_path"])
    lines = p.read_text().splitlines()
    if any(l.startswith("set:") for l in lines):
        return False
    i = next((k for k, l in enumerate(lines) if l.startswith("verdict:")), len(lines))
    lines.insert(i, "set: %s" % value)
    p.write_text("\n".join(lines) + "\n")
    card["set"] = value
    return True


def expected(card, host=None):
    host = host or ("sumo" if on_net(card) else "exerciser")
    e = entry(card, host)
    return e.get("status") if isinstance(e, dict) else None


# ── commands ──

def cmd_run(a):
    row = run(load(a.card), a.host, a.seed, a.out, a.trace)
    print(json.dumps(row, default=str))


def host_of(card, host):
    return "sumo" if on_net(card) else host


def cmd_check(a):
    """Every card against its verdict. A REGRESSION card fails the run when its measured standing is not pass, or its
    verdicts are not all pass/skip (a format error); a WORKING card never fails it: its row is information (§6c), and a
    working card measured pass is a promotion candidate."""
    moved, failing, candidates = 0, 0, []
    lines = ["| card | set | host | verdict | measured | why |", "|---|---|---|---|---|---|"]
    for path in cards_in(a.cards):
        card = load(path)
        if a.set and card_set(card) != a.set:
            continue
        fe = format_error(card)
        if fe:
            failing += 1
            lines.append("| %s | regression | - | - | **FORMAT** | %s |" % (card_id(card), fe))
            print(lines[-1], flush=True)
            continue
        if on_net(card) and a.host == "exerciser":            # a stored net plays on SUMO only
            continue
        h = host_of(card, a.host)
        if skipped(card, h) or (not on_net(card) and h == "exerciser" and (card.get("exerciser") or {}).get("skip")):
            continue
        trace = tempfile.mkdtemp(prefix="scenario-trace-") if on_net(card) else None
        row = run(card, h, a.seed, a.out, trace)
        st, exp, cs = row["standing"], expected(card, h), card_set(card)
        mv = bool(exp) and st["status"] != exp
        moved += mv
        if cs == "regression" and st["status"] != "pass":
            failing += 1
        if cs == "working" and st["status"] == "pass":
            candidates.append(card_id(card))
        lines.append("| %s | %s | %s | %s | %s%s | %s |" % (card_id(card), cs, h, exp or "(none)", st["status"],
                                                            " **MOVED**" if mv else "", (st.get("why") or "")[:120]))
        print(lines[-1], flush=True)
    print("\n".join(lines))
    print("moved: %d; regression not at pass: %d; promotion candidates (working, measured pass): %s"
          % (moved, failing, ", ".join(candidates) or "none"))
    if os.environ.get("GITHUB_STEP_SUMMARY"):                  # CI: the table on the run's page
        with open(os.environ["GITHUB_STEP_SUMMARY"], "a") as f:
            f.write("### scenario_run check (%s, %s set): %d moved, %d regression not at pass\n\n%s\n\n**Promotion candidates:** %s\n"
                    % (a.host, a.set or "every", moved, failing, "\n".join(lines), ", ".join(candidates) or "none"))
    sys.exit(1 if failing else 0)


def cmd_verdict(a):
    for path in cards_in(a.cards):
        card = load(path)
        h = host_of(card, a.host)
        trace = tempfile.mkdtemp(prefix="scenario-trace-") if on_net(card) else None
        if skipped(card, h):
            continue
        st = run(card, h, a.seed, a.out, trace)["standing"]
        write_verdict(card, st, h)
        if "set" not in card:                                  # the default at the card's FIRST verdict, never flipped after
            write_set(load(path), default_set(load(path)))
        print("%s %s %s" % (card_id(card), st["status"], st.get("why") or ""))


def coverage(paths, host=None):
    """The coverage table (SCENARIO-CARD §6, step 5): per regulation group (the card's `tags`), the cards' standings per host
    from their verdicts. → markdown."""
    table, hosts = {}, [host] if host else list(HOSTS)
    for path in cards_in(paths):
        c = load(path)
        for t in c.get("tags") or ["(untagged)"]:
            for h in hosts:
                st = "skip" if skipped(c, h) else expected(c, h)
                if st:
                    table.setdefault(t, {}).setdefault(h, {}).setdefault(st, 0)
                    table[t][h][st] += 1
    sets = {}
    for path in cards_in(paths):
        c = load(path)
        for t in c.get("tags") or ["(untagged)"]:
            sets.setdefault(t, {"regression": 0, "working": 0})[card_set(c)] += 1
    head = ["| tag | regression (proven) | working (exercised) |", "|---|---|---|"]
    head += ["| %s | %d | %d |" % (t, v["regression"], v["working"]) for t, v in sorted(sets.items())]
    cols = ["pass", "soft", "fail", "world", "skip"]
    lines = head + ["", "| tag | host | " + " | ".join(cols) + " |", "|---|---|" + "---|" * len(cols)]
    for t in sorted(table):
        for h in hosts:
            if h in table[t]:
                lines.append("| %s | %s | %s |" % (t, h, " | ".join(str(table[t][h].get(c, 0)) for c in cols)))
    return "\n".join(lines) + "\n"


def cmd_coverage(a):
    md = coverage(a.cards, a.host)
    print(md)
    if os.environ.get("GITHUB_STEP_SUMMARY"):
        with open(os.environ["GITHUB_STEP_SUMMARY"], "a") as f:
            f.write("### Coverage\n\n" + md)


def cmd_list(a):
    """The cards a host plays, as a JSON list (CI's matrix)."""
    out = []
    for path in cards_in(a.cards):
        c = load(path)
        if skipped(c, a.host) or (a.host == "exerciser" and on_net(c)) or (a.set and card_set(c) != a.set):
            continue
        if a.host == "sumo" and not on_net(c) and not (c.get("sites") or {}).get("towns"):
            continue
        out.append(str(Path(path).resolve().relative_to(WORLDS)))
    if a.chunks:                                           # CI's matrix in groups: one job checks a group (step 5, batched)
        n = max(1, min(a.chunks, len(out)))
        out = [" ".join(out[i::n]) for i in range(n)] if out else []
    print(json.dumps(out))


def cmd_sets(a):
    """Writes the §6c default `set:` into every card that has none, from its verdicts on file (no run)."""
    for path in cards_in(a.cards):
        c = load(path)
        if "set" not in c and played(c):
            v = default_set(c)
            write_set(c, v)
            print("%s %s" % (card_id(c), v))


def cmd_index(a):
    rows = []
    for path in cards_in([a.dir]):
        c = load(path)
        if on_net(c):
            runs = ["cr:" + card_file(c, c["map"]["net"]).parent.name]
        elif on_world(c):
            sys.path.insert(0, str(ROAD / "intersection"))
            import intersection as I
            runs = ["ix:%s:%s" % (c["scenario"], lv) for lv in I.levels_of(c)]
        else:
            try:
                runs = town_runs(c, "sumo")
            except (SystemExit, Exception):                  # noqa: BLE001 — a card with no SUMO site: the exerciser's run
                runs = [c.get("scenario")]
            runs = ["card:" + r for r in runs]
        rows.append({"id": card_id(c), "scenario": c.get("scenario"), "source": (c.get("source") or {}).get("suite"),
                     "tags": c.get("tags") or [], "verdict": {h: expected(c, h) for h in HOSTS if expected(c, h)},
                     "map": (c.get("map") or {}).get("town") or (c.get("map") or {}).get("net") or (c.get("map") or {}).get("world"),
                     "run": runs[0], "runs": runs})
    (Path(a.dir) / "index.json").write_text(json.dumps({"cards": rows}, indent=1) + "\n")
    print("index: %d cards" % len(rows))


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if argv[:1] == ["batch"]:                                   # the harvest's batch mode, its jobs cards (cr_batch)
        sys.argv = ["cr_batch.py"] + argv[1:]
        return batch_mod().main()
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run")
    r.add_argument("card")
    for p in [r] + [sub.add_parser(n) for n in ("check", "verdict")]:
        if p is not r:
            p.add_argument("cards", nargs="+")
        p.add_argument("--host", default="exerciser", choices=["exerciser", "sumo"])
        p.add_argument("--seed", type=int, default=1)
        p.add_argument("--out")
        if p is r:
            p.add_argument("--trace")
        else:
            p.add_argument("--set", choices=list(SETS))
    cv = sub.add_parser("coverage")
    cv.add_argument("cards", nargs="*", default=[str(CATALOG)])
    cv.add_argument("--host", choices=list(HOSTS))
    ls = sub.add_parser("list")
    ls.add_argument("cards", nargs="*", default=[str(CATALOG)])
    ls.add_argument("--host", default="sumo", choices=list(HOSTS))
    ls.add_argument("--chunks", type=int, default=0, help="N groups of cards, round-robin, each a space-separated string")
    ls.add_argument("--set", choices=list(SETS))
    st_ = sub.add_parser("sets")
    st_.add_argument("cards", nargs="*", default=[str(CATALOG)])
    ix = sub.add_parser("index")
    ix.add_argument("dir", nargs="?", default=str(CATALOG))
    a = ap.parse_args(argv)
    {"run": cmd_run, "check": cmd_check, "verdict": cmd_verdict, "index": cmd_index, "coverage": cmd_coverage,
     "list": cmd_list, "sets": cmd_sets}[a.cmd](a)


if __name__ == "__main__":
    main()
