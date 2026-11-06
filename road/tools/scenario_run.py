"""scenario_run.py — the one runner of the scenario catalog (scenario-catalog s-92e0b650 step 2; the card: road/docs/SCENARIO-CARD.md).
A card is played on a host by the road family (road_tree's Live), measured once (the Leaderboard's, CommonRoad's, ours), given
its standing (pass | soft | fail | world) and compared with the card's `verdict`.

    road/tools/scenario_run.py run CARD.yaml [--host exerciser|sumo] [--seed S] [--out DIR] [--trace DIR]   one card → one row
    road/tools/scenario_run.py check CARD|DIR … [--host H] [--rows DIR]     every card's standing against its verdict; exit 1 on a move
    road/tools/scenario_run.py verdict CARD … [--host H]                   measure and write the card's verdict (with since)
    road/tools/scenario_run.py batch plan|work|launch|status|pull|recover …  cr_batch over cards (jobs carry the card's path)
    road/tools/scenario_run.py index [DIR]                                  road/catalog/index.json (id, source, tags, verdict, map)

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


def cards_in(paths):
    out = []
    for a in paths:
        p = Path(a)
        out += sorted(p.rglob("*.yaml")) if p.is_dir() else [p]
    return [x for x in out if x.name != "index.json" and "sites" not in x.parts]


# ── one run ──

def run_town(card, host, seed, out, trace):
    """A card on a town: road_tree's `card:NAME` (its first site on SUMO), measured as scenarios.py's row."""
    import scenario_cards as C
    sc = _mod("scenarios", ROAD / "experiments" / "scenarios.py")
    rt = sc.road_tree()
    name = card["scenario"]
    if host == "sumo":
        towns = (card.get("sites") or {}).get("towns") or {}
        town = sorted(towns)[0] if towns else None
        if town is None:
            raise SystemExit("scenario_run: %s has no SUMO site" % name)
        name = "%s@%s#%s" % (name, town, C.sites(C.load(card["scenario"]), town)[0]["i"])
    c = C.load(card["scenario"])
    res = rt.run("card:" + name, seed, Path(out) / "runs", ticks=sc.ticks_of(c, host), world_kind=host if host == "sumo" else None,
                 trace=trace)
    r = sc.row(c, name, res)
    return {"card": card_id(card), "host": host, "seed": seed, "run": name, "fails": r["fails"], "arrived": r["arrived"],
            "collisions": r["collisions"], "collision_events": r["collision_events"], "violations": r["violations"],
            "lb": r["lb"], "rc": r["rc"], "ds": r["ds"], "summary": res}


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
    p = subprocess.run(cmd, cwd=str(WORLDS), env=env, capture_output=True, text=True, timeout=int(os.environ.get("CR_TIMEOUT", 900)))
    summ = B.last_json(p.stdout) if p.returncode == 0 else None
    job = {"id": sid, "set": (card.get("source") or {}).get("set"), "source": (card.get("source") or {}).get("suite"),
           "country": sid.split("_")[0], "tags": card.get("tags") or []}
    row = B.make_row(job, None, seed, started, time.time() - t0, summ, p.stderr, p.returncode, False)
    row.update(card=card_id(card), host=host, run="cr:%s-%d" % (sid, seed))
    return row


def run(card, host="exerciser", seed=1, out=None, trace=None):
    out = out or tempfile.mkdtemp(prefix="scenario-run-")
    row = (run_net if on_net(card) else run_town)(card, host, seed, out, trace)
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


def write_verdict(card, st):
    """The card's verdict block, rewritten in place (the rest of the file as the author wrote it)."""
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
    v = {"status": st["status"], "since": since()}
    if st.get("why"):
        v["note"] = st["why"][:200]
    out.append(yaml.safe_dump({"verdict": v}, sort_keys=False, allow_unicode=True).rstrip())
    p.write_text("\n".join(out) + "\n")


def expected(card):
    v = card.get("verdict")
    return v.get("status") if isinstance(v, dict) else None


# ── commands ──

def cmd_run(a):
    row = run(load(a.card), a.host, a.seed, a.out, a.trace)
    print(json.dumps(row, default=str))


def host_of(card, host):
    return "sumo" if on_net(card) else host


def cmd_check(a):
    moved, lines = 0, ["| card | host | verdict | measured | why |", "|---|---|---|---|---|"]
    for path in cards_in(a.cards):
        card = load(path)
        h = host_of(card, a.host)
        if not on_net(card) and h == "exerciser" and (card.get("exerciser") or {}).get("skip"):
            continue
        trace = tempfile.mkdtemp(prefix="scenario-trace-") if on_net(card) else None
        row = run(card, h, a.seed, a.out, trace)
        st, exp = row["standing"], expected(card)
        if exp and st["status"] != exp:
            moved += 1
        lines.append("| %s | %s | %s | %s%s | %s |" % (card_id(card), h, exp or "(none)", st["status"],
                                                       " **MOVED**" if exp and st["status"] != exp else "", (st.get("why") or "")[:120]))
        print(lines[-1], flush=True)
    print("\n".join(lines))
    print("moved: %d" % moved)
    sys.exit(1 if moved else 0)


def cmd_verdict(a):
    for path in cards_in(a.cards):
        card = load(path)
        h = host_of(card, a.host)
        trace = tempfile.mkdtemp(prefix="scenario-trace-") if on_net(card) else None
        st = run(card, h, a.seed, a.out, trace)["standing"]
        write_verdict(card, st)
        print("%s %s %s" % (card_id(card), st["status"], st.get("why") or ""))


def cmd_index(a):
    rows = []
    for path in cards_in([a.dir]):
        c = load(path)
        rows.append({"id": card_id(c), "scenario": c.get("scenario"), "source": (c.get("source") or {}).get("suite"),
                     "tags": c.get("tags") or [], "verdict": expected(c), "map": (c.get("map") or {}).get("town") or (c.get("map") or {}).get("net")})
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
    ix = sub.add_parser("index")
    ix.add_argument("dir", nargs="?", default=str(CATALOG))
    a = ap.parse_args(argv)
    {"run": cmd_run, "check": cmd_check, "verdict": cmd_verdict, "index": cmd_index}[a.cmd](a)


if __name__ == "__main__":
    main()
