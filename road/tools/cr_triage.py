"""cr_triage.py — the harvest's triage (commonroad-world s-9b7591fb step 3b, nina's half; the batch is george's cr_batch.py).

A round is one law pin's harvest: /bigdata/work/harvest/<pin>/<host>/{rows,records,traces}/ (road/docs/harvest.md, george's
layout and row schema), every host's results pulled to taycann. The triage reads it with no agent in the loop:

    python road/tools/cr_triage.py run   ROUND [--jobs N]          kind every failed record, cluster, write triage.md + clusters.json
    python road/tools/cr_triage.py curve ROUND [ROUND ...]          the curve over rounds (pins): new clusters per 100 scenarios, by kind
    python road/tools/cr_triage.py import ROUND --to road/.metis   one representative per cluster into the loop's workspace

1. KIND: metis.trace's triage (metis.surprise_kind, spec 20 §4) on every failed row's record, over its trace, with the member's
   program (road/domains/<member>/<member>.llp, the family by METIS_HOME). Cached per record in ROUND/triage/<id>.json, so a
   rerun (more rows pulled, a crash) does only the new ones.
2. SIGNATURE: what makes two failures one mechanism. (member, the failed measure, the kind, the commands fired in the window,
   the NEAR MISSES: the command rules one guard away that never fired there, short of an atom that is not one of the host's
   exclusive classes (keep_limit one at_target away while below_target holds is the law's ordinary branching), by their base
   names, and the preds of the atoms they miss.) Ground arguments (lane ids, object ids) stay out: the same
   missing `route_lane(D)` on two maps is one mechanism. The measure is the row's (harvest.md): error:<kind> for a run that did not
   finish, else the first of `failed` (contact, sumo_collision, goal, off_lanelet, violation). A row with no record (an error
   run: the world's or the conversion's fault, never the family's) clusters by (measure, "no record").
3. CLUSTERS: by signature, with their count, their scenarios, and ONE representative: the earliest in run order (the row's
   `started`, then id), so a rerun of the same round picks the same one.
4. THE CURVE: rows in run order, per 100 the clusters first seen in that hundred, by kind. Per pin (one round each): the law has
   stopped moving when a full round adds no new STRUCTURAL cluster (the user's refactoring trigger) — `curve` prints it.
5. IMPORT: each cluster's representative into road/.metis (its trace copied to traces/harvest-<pin>-<scenario>, the record
   dropped through the workspace with `harvest` {pin, cluster, count, measure, rules, atoms}; the loop kinds it again on its
   own): the loop sees one record per mechanism, never thousands (the architect's Q1). TO/harvest.json keeps which clusters
   are in, so a second import adds only the new ones."""
import argparse
import hashlib
import json
import os
import shutil
import sys
from pathlib import Path

ROAD = Path(__file__).resolve().parent.parent
MEASURES = ("contact", "sumo_collision", "goal", "off_lanelet", "violation")   # a row's `failed`, in harvest.md's order
IMPORT_LIMIT = 20                                                         # representatives per import, in all
STRUCTURAL = ("ontological", "structural")                                # the kinds the law's shape answers (spec 20 §5)


# ── a round ──
def hosts(round_dir):
    """The host directories of ROUND (each with rows/)."""
    return sorted(p for p in Path(round_dir).iterdir() if p.is_dir() and (p / "rows").is_dir())


def rows(round_dir):
    """Every row of ROUND, each with `_host` (its directory), in run order (started, then id)."""
    out = []
    for h in hosts(round_dir):
        for f in sorted((h / "rows").glob("*.json")):
            try:
                r = json.loads(f.read_text())
            except (OSError, ValueError):
                continue                                    # a row being written (or torn): the next run reads it
            r["_host"] = str(h)
            out.append(r)
    return sorted(out, key=lambda r: (str(r.get("started") or ""), str(r.get("id"))))


def measure(row):
    """The row's failure (road/docs/harvest.md: a row passes when `error` is null and `failed` is empty): error:<kind> for a run
    that did not finish (convert | world | timeout | crash), else the first of `failed` in MEASURES' order; None: passed."""
    err = row.get("error")
    if err:
        return "error:%s" % (err.get("kind") if isinstance(err, dict) else "?")
    failed = row.get("failed") or []
    for m in MEASURES:
        if m in failed:
            return m
    return failed[0] if failed else None


def record_of(row):
    """(the record dict, its trace's directory) of a failed row, or (None, None). The worker writes records/<record_id>.json with
    trace `traces/<run>`, the trace itself in runs/<scenario id>/trace/ (harvest.md); a trace under the host's traces/ is read too."""
    rid = row.get("record_id")
    if not rid:
        return None, None
    h = Path(row["_host"])
    p = h / "records" / ("%s.json" % rid)
    if not p.is_file():
        return None, None
    rec = json.loads(p.read_text())
    scen = rec.get("scenario") or row.get("id")
    for tr in ([h / "runs" / str(scen) / "trace"] + ([h / rec["trace"]] if rec.get("trace") else [])):
        if tr.is_dir():
            return rec, tr
    return rec, None


# ── 1. kind ──
def _program(member):
    p = ROAD / "domains" / member / ("%s.llp" % member)
    return str(p) if p.is_file() else None


def kind_one(row):
    """The triage of ROW's record → {kind, also, signature parts}; never raises (a failure of the triage is its own row)."""
    rec, tr = record_of(row)
    if rec is None:
        return {"kind": None, "member": None, "rules": [], "atoms": [], "why": "no record"}
    member = rec.get("member")
    out = {"member": member, "record": rec.get("id"), "rules": [], "atoms": []}
    if tr is None:
        return dict(out, kind=None, why="no trace")
    try:
        from metis import surprise_kind as SK
        t = SK.triage(rec, tr, _program(member) if member else None)
    except Exception as e:                                  # noqa: BLE001 — the triage of one record never stops the round
        return dict(out, kind="computational", why="the triage failed: %s" % str(e).splitlines()[0][:200])
    law = (t.get("evidence") or {}).get("law") or {}
    try:
        from metis import trace as MT
        commands = set((MT.read(str(tr))[0].header or {}).get("commands") or ())
    except Exception:                                       # noqa: BLE001 — no header: every rule counts
        commands = set()
    near = [o for o in law.get("one_guard_away") or () if near_miss(o, commands)]
    fired = sorted({_base(n) for n in law.get("commands_fired") or ()})
    return dict(out, kind=t.get("kind"), also=t.get("also") or [], fired=fired, rules=sorted({o["rule"] for o in near}),
                atoms=sorted({o["missing"].split("(")[0] for o in near}),
                ground=sorted({"%s ⟵ %s" % (o["ground"], o["missing"]) for o in near})[:12],
                missing_columns=(t.get("evidence") or {}).get("missing") or [])


# the host's exclusive classes (road_facts): a rule one of these short while its sibling holds is the law's ordinary branching,
# never a near miss (keep_limit one `at_target` away while below_target holds)
EXCLUSIVE = {"below_target", "at_target", "above_target", "accel_ok", "accel_no", "keep_ok", "keep_no", "lead_ok", "lead_slow",
             "seen_ahead", "unseen_ahead", "cross_settled", "cross_unsettled", "cross_overlap", "side_clear", "side_busy",
             "oncoming_clear", "oncoming_busy", "can_stop", "late", "zfree", "zbusy", "zclear", "inch_room", "inch_no",
             "road_in_view", "road_hidden", "safe_long", "safe_lat", "role_empty", "zone_at", "signal"}


def _base(name):
    return str(name).split("(")[0].split("@")[0]


def near_miss(o, commands):
    """A one-guard-away row that says something: a COMMAND rule (no protocol rule: drive, arrive, cancel, released) that did not
    fire in the window, short of an atom that is not one of the host's exclusive classes."""
    if commands and o["rule"] not in commands:
        return False
    if o.get("fired_at"):
        return False
    return o["missing"].split("(")[0] not in EXCLUSIVE


def kinds(round_dir, todo, jobs=1, kinder=kind_one):
    """KINDER over the failed rows TODO, cached in ROUND/triage/<row id>.json. → {row id: result}."""
    cache = Path(round_dir) / "triage"
    cache.mkdir(exist_ok=True)
    out, fresh = {}, []
    for r in todo:
        if not r.get("record_id"):                         # an error run: no record, nothing to replay
            out[r["id"]] = {"kind": None, "member": None, "rules": [], "atoms": [], "why": "no record"}
            continue
        f = cache / ("%s.json" % _safe(r["id"]))
        if f.is_file():
            out[r["id"]] = json.loads(f.read_text())
        else:
            fresh.append(r)
    if jobs > 1 and len(fresh) > 1:
        from multiprocessing import Pool
        with Pool(jobs) as pool:
            done = pool.map(kinder, fresh, chunksize=1)
    else:
        done = [kinder(r) for r in fresh]
    for r, k in zip(fresh, done):
        out[r["id"]] = k
        (cache / ("%s.json" % _safe(r["id"]))).write_text(json.dumps(k, indent=1) + "\n")
    return out


def _safe(name):
    return "".join(c if c.isalnum() or c in "-_." else "_" for c in str(name))


# ── 2. signature, 3. clusters ──
def signature(row, k):
    """The mechanism's signature of a failed ROW with its triage K (a tuple, hashable)."""
    m = measure(row)
    if not k or (k.get("kind") is None and k.get("why") in ("no record", "no trace")):
        return (None, m, "no record", (), (), ())
    return (k.get("member"), m, k.get("kind"), tuple(k.get("fired") or ()), tuple(k.get("rules") or ()), tuple(k.get("atoms") or ()))


def cluster_id(sig):
    return hashlib.sha1(json.dumps(sig).encode()).hexdigest()[:8]


def clusters(all_rows, ks):
    """The failed rows grouped by signature, in order of first appearance. → [cluster dict]."""
    by = {}
    for i, r in enumerate(all_rows):
        if measure(r) is None:
            continue
        sig = signature(r, ks.get(r["id"]))
        c = by.get(sig)
        if c is None:
            k = ks.get(r["id"]) or {}
            c = by[sig] = {"id": cluster_id(sig), "member": sig[0], "measure": sig[1], "kind": sig[2], "fired": list(sig[3]),
                           "rules": list(sig[4]), "atoms": list(sig[5]), "count": 0, "scenarios": [], "first": i,
                           "representative": {"id": r["id"], "record": k.get("record"), "host": r.get("_host"),
                                              "set": r.get("set"), "ground": k.get("ground") or []}}
        c["count"] += 1
        c["scenarios"].append(r["id"])
    return sorted(by.values(), key=lambda c: c["first"])


# ── 4. the curve ──
def curve(all_rows, cl, per=100):
    """[{n: the hundred's end, new: {kind: n}, total}] over ALL_ROWS in run order."""
    first = {}
    for c in cl:
        first.setdefault(c["first"], []).append(c)
    out, total = [], 0
    for start in range(0, len(all_rows), per):
        new = {}
        for i in range(start, min(start + per, len(all_rows))):
            for c in first.get(i, ()):
                key = c["kind"] or "no record"
                new[key] = new.get(key, 0) + 1
                total += 1
        out.append({"n": min(start + per, len(all_rows)), "new": new, "total": total})
    return out


# ── the round's table ──
def run(round_dir, jobs=1, kinder=kind_one, write=True):
    all_rows = rows(round_dir)
    failed = [r for r in all_rows if measure(r) is not None]
    ks = kinds(round_dir, failed, jobs=jobs, kinder=kinder)
    cl = clusters(all_rows, ks)
    cv = curve(all_rows, cl)
    pin = Path(round_dir).name
    summary = {"pin": pin, "scenarios": len(all_rows), "failed": len(failed), "clusters": len(cl),
               "by_kind": _count(c["kind"] or "no record" for c in cl),
               "by_measure": _count(measure(r) for r in failed),
               "structural_new": sum(1 for c in cl if c["kind"] in STRUCTURAL)}
    out = {"summary": summary, "clusters": cl, "curve": cv}
    if write:
        Path(round_dir, "clusters.json").write_text(json.dumps(out, indent=1, default=str) + "\n")
        Path(round_dir, "triage.md").write_text(render(out))
    return out


def _count(xs):
    out = {}
    for x in xs:
        out[x] = out.get(x, 0) + 1
    return dict(sorted(out.items(), key=lambda kv: -kv[1]))


def render(out):
    s = out["summary"]
    lines = ["# harvest triage, law pin %s" % s["pin"], "",
             "%d scenarios, %d failed, **%d distinct mechanisms** (%s). Failures by measure: %s." % (
                 s["scenarios"], s["failed"], s["clusters"], ", ".join("%s %d" % kv for kv in s["by_kind"].items()) or "none",
                 ", ".join("%s %d" % kv for kv in s["by_measure"].items()) or "none"), "",
             "| cluster | count | kind | member | measure | fired (commands) | one guard away (rules) | missing (preds) | representative |",
             "|---|---|---|---|---|---|---|---|---|"]
    for c in sorted(out["clusters"], key=lambda c: -c["count"]):
        lines.append("| %s | %d | %s | %s | %s | %s | %s | %s | %s |" % (
            c["id"], c["count"], c["kind"] or "—", c["member"] or "—", c["measure"], ", ".join(c.get("fired") or ()) or "—",
            ", ".join(c["rules"]) or "—",
            ", ".join(c["atoms"]) or "—", c["representative"]["id"]))
    lines += ["", "## The curve (new clusters per 100 scenarios, in run order)", "", "| scenarios | new | by kind | total |",
              "|---|---|---|---|"]
    for p in out["curve"]:
        lines.append("| %d | %d | %s | %d |" % (p["n"], sum(p["new"].values()), ", ".join("%s %d" % kv for kv in sorted(p["new"].items())) or "—",
                                               p["total"]))
    return "\n".join(lines) + "\n"


# ── over pins ──
def curve_over(round_dirs):
    """Per round (pin): its clusters, and those NEW against every earlier round given (by signature id)."""
    seen, out = set(), []
    for d in round_dirs:
        f = Path(d, "clusters.json")
        if not f.is_file():
            raise SystemExit("%s: no clusters.json (run `cr_triage.py run %s` first)" % (d, d))
        cl = json.loads(f.read_text())["clusters"]
        new = [c for c in cl if c["id"] not in seen]
        seen.update(c["id"] for c in cl)
        out.append({"pin": Path(d).name, "clusters": len(cl), "new": len(new),
                    "new_structural": sum(1 for c in new if c["kind"] in STRUCTURAL), "new_by_kind": _count(c["kind"] or "no record" for c in new)})
    return out


# ── 5. import ──
def import_round(round_dir, to, limit=IMPORT_LIMIT):
    """Each cluster's representative into the workspace TO (road/.metis): its trace copied, the record dropped with the
    cluster it stands for. One per mechanism, the biggest clusters first, at most LIMIT in all (the user's word, 2026-11-05:
    one failure per kind, the total limited). Already imported clusters (TO's harvest.json) are skipped. → [new ids]."""
    from metis.catalog import workspace as W
    to = Path(to)
    ws = W.Workspace(to.parent)
    data = json.loads(Path(round_dir, "clusters.json").read_text())
    done_f = to / "harvest.json"
    done = json.loads(done_f.read_text()) if done_f.is_file() else {}
    made = []
    for c in sorted(data["clusters"], key=lambda c: (-c["count"], c["first"])):
        if len(made) >= limit:
            break
        key = "%s:%s" % (data["summary"]["pin"], c["id"])
        if key in done or c["kind"] in (None, "no record"):
            continue
        rep = c["representative"]
        rec, tr = record_of({"record_id": rep["record"], "_host": rep["host"], "id": rep["id"]})
        if rec is None or tr is None:
            continue
        run_name = "harvest-%s-%s" % (data["summary"]["pin"][:7], _safe(rep["id"]))
        dst = to / "traces" / run_name
        if not dst.exists():
            shutil.copytree(tr, dst)
        new = {k: v for k, v in rec.items() if k not in ("id", "ts", "status", "kind", "evidence", "response", "then", "also")}
        new.update(trace="traces/%s" % run_name, who="world",
                   harvest={"pin": data["summary"]["pin"], "cluster": c["id"], "count": c["count"], "measure": c["measure"],
                            "rules": c["rules"], "atoms": c["atoms"], "scenario": rep["id"], "set": rep.get("set")})
        new.pop("config", None)
        if (dst / "config.yaml").is_file():
            new["config"] = ".metis/traces/%s/config.yaml" % run_name
        sid = ws.drop_surprise(new, who="world")
        done[key] = sid
        made.append(sid)
    done_f.write_text(json.dumps(done, indent=1) + "\n")
    return made


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run", help="kind every failed record, cluster, write triage.md and clusters.json")
    r.add_argument("round")
    r.add_argument("--jobs", type=int, default=max(1, (os.cpu_count() or 2) // 2))
    c = sub.add_parser("curve", help="the curve over rounds (pins): new clusters, new structural ones")
    c.add_argument("rounds", nargs="+")
    i = sub.add_parser("import", help="one representative per cluster into the loop's workspace")
    i.add_argument("round")
    i.add_argument("--to", default=str(ROAD / ".metis"))
    i.add_argument("--limit", type=int, default=IMPORT_LIMIT, help="representatives in all, the biggest clusters first")
    a = ap.parse_args(argv)
    if a.cmd == "run":
        out = run(a.round, jobs=a.jobs)
        s = out["summary"]
        print("%s: %d scenarios, %d failed, %d clusters %s -> %s" % (s["pin"], s["scenarios"], s["failed"], s["clusters"], s["by_kind"],
                                                                     Path(a.round, "triage.md")))
    elif a.cmd == "curve":
        rows_ = curve_over(a.rounds)
        for p in rows_:
            print("%-12s clusters %4d  new %4d  new structural %3d  %s" % (p["pin"][:12], p["clusters"], p["new"], p["new_structural"], p["new_by_kind"]))
        if len(rows_) > 1 and rows_[-1]["new_structural"] == 0:
            print("the last round added no new structural cluster: the refactoring trigger (the user's)")
    else:
        made = import_round(a.round, a.to, a.limit)
        print("imported %d representatives: %s" % (len(made), " ".join(made)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
