"""cr_triage (commonroad-world s-9b7591fb step 3b): the harvest's rows (road/docs/harvest.md, george's schema and layout) clustered
into mechanisms, the curve, the import of one representative per cluster with a total limit. The triage itself
(metis.surprise_kind) is injected: the rounds are hand-built, no SUMO, no trace replay."""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "tools"))
import cr_triage as T  # noqa: E402


def row(rid, started, failed=(), record=True, **kw):
    r = {"id": rid, "set": "recorded", "source": "hand-crafted", "started": started, "arrived": not failed, "failed": list(failed),
         "goal": {"reached": "goal" not in failed}, "contact": "contact" in failed, "violations": 0, "error": None,
         "record_id": ("rec-%s" % rid) if failed and record else None}
    r.update(kw)
    return r


def make_round(tmp_path, pin, hosts):
    d = tmp_path / pin
    for host, rs in hosts.items():
        for sub in ("rows", "records", "runs"):
            (d / host / sub).mkdir(parents=True)
        for r in rs:
            (d / host / "rows" / ("%s.json" % r["id"])).write_text(json.dumps(r))
            if r.get("record_id"):
                tr = d / host / "runs" / r["id"] / "trace" / ("cr_%s-1" % r["id"])     # the worker's: runs/<id>/trace/<run>/
                tr.mkdir(parents=True)
                (tr / "seg-0.jsonl").write_text("{}\n")
                (tr / "config.yaml").write_text("model: none\n")
                (d / host / "records" / ("%s.json" % r["record_id"])).write_text(json.dumps(
                    {"id": r["record_id"], "member": "planner", "trace": "traces/cr_%s-1" % r["id"], "window": [10, 40], "k": 40,
                     "reading": "%s: %s failed" % (r["id"], r["failed"][0]), "atoms": r["failed"], "scenario": "cr:%s" % r["id"],
                     "trace_path": "runs/%s/trace/cr_%s-1" % (r["id"], r["id"]),
                     "row": "rows/%s.json" % r["id"], "who": "world", "status": "open"}))
    return d


def kinder(table):
    """A stand-in triage: the row id's entry of TABLE (kind, rules, atoms)."""
    def k(r):
        kind, rules, atoms = table[r["id"]]
        return {"kind": kind, "member": "planner", "record": r["record_id"], "rules": rules, "atoms": atoms,
                "ground": ["%s ⟵ %s(x)" % (rules[0], atoms[0])] if rules else []}
    return k


ROUTE = ("ontological", ["change_route"], ["route_lane"])
LATE = ("structural", ["brake_cross_late"], ["late"])


def test_the_rows_measure_is_harvest_mds():
    assert T.measure(row("a", "1")) is None
    assert T.measure(row("a", "1", failed=["goal"])) == "goal:position"
    assert T.measure(row("a", "1", failed=["goal"], goal={"reached": False, "position_t": 12.3, "window_ok": False})) == "goal:window"
    assert T.measure(row("a", "1", failed=["goal", "violation"], goal={"position_t": 12.3})) == "violation"   # the hard one first
    assert T.measure(row("a", "1", failed=["violation", "off_lanelet"])) == "violation"
    assert T.measure(row("a", "1", failed=["goal", "sumo_collision", "contact"])) == "contact"
    assert T.measure(row("a", "1", error={"kind": "convert", "line": "netconvert: no lanelet", "rc": 1})) == "error:convert"


def test_one_mechanism_on_two_maps_is_one_cluster_its_representative_the_earliest(tmp_path):
    rs = {"taycann": [row("USA_Peach-1", "2026-11-05T22:00:02+02:00", failed=["goal"]),
                      row("ZAM_Ok-1", "2026-11-05T22:00:01+02:00")],
          "panzer": [row("DEU_Muc-1", "2026-11-05T22:00:00+02:00", failed=["goal"]),
                     row("DEU_Cross-1", "2026-11-05T22:00:03+02:00", failed=["contact"]),
                     row("DEU_Err-1", "2026-11-05T22:00:04+02:00", error={"kind": "timeout", "line": "", "rc": -9})]}
    d = make_round(tmp_path, "d5c7c72", rs)
    out = T.run(d, kinder=kinder({"USA_Peach-1": ROUTE, "DEU_Muc-1": ROUTE, "DEU_Cross-1": LATE}))
    s = out["summary"]
    assert (s["scenarios"], s["failed"], s["clusters"]) == (5, 4, 3)
    route = next(c for c in out["clusters"] if c["rules"] == ["change_route"])
    assert route["count"] == 2 and route["representative"]["id"] == "DEU_Muc-1"        # the earliest in run order
    assert route["kind"] == "ontological" and route["measure"] == "goal:position"
    err = next(c for c in out["clusters"] if c["measure"] == "error:timeout")
    assert err["kind"] == "no record" and err["count"] == 1                                     # no record: by its measure alone
    assert (d / "triage.md").read_text().startswith("# harvest triage, law pin d5c7c72")
    assert json.loads((d / "clusters.json").read_text())["summary"]["clusters"] == 3


def test_the_real_triage_says_no_trace_when_the_run_dir_is_gone(tmp_path):
    d = make_round(tmp_path, "p0", {"taycann": [row("A-1", "1", failed=["goal"])]})
    import shutil
    shutil.rmtree(d / "taycann" / "runs" / "A-1")
    assert T.record_of(T.rows(d)[0])[1] is None
    r = T.rows(d)[0]
    assert T.kind_one(r)["why"] == "no trace"


def test_the_triage_is_cached_per_row(tmp_path):
    d = make_round(tmp_path, "p1", {"taycann": [row("A-1", "1", failed=["contact"])]})
    calls = []

    def k(r):
        calls.append(r["id"])
        return kinder({"A-1": LATE})(r)
    T.run(d, kinder=k)
    T.run(d, kinder=k)
    assert calls == ["A-1"]


def test_the_curve_counts_new_clusters_per_hundred_and_over_pins(tmp_path):
    many = [row("S-%03d" % i, "%03d" % i) for i in range(150)]
    many[5] = row("S-005", "005", failed=["contact"])
    many[120] = row("S-120", "120", failed=["goal"])
    many[130] = row("S-130", "130", failed=["contact"])
    table = {"S-005": LATE, "S-120": ROUTE, "S-130": LATE}
    d1 = make_round(tmp_path, "pin1", {"taycann": many})
    out = T.run(d1, kinder=kinder(table))
    assert [(p["n"], p["new"], p["total"]) for p in out["curve"]] == [(100, {"structural": 1}, 1), (150, {"ontological": 1}, 2)]
    d2 = make_round(tmp_path, "pin2", {"taycann": [row("S-005", "005", failed=["contact"])]})
    T.run(d2, kinder=kinder(table))
    over = T.curve_over([d1, d2])
    assert [(p["pin"], p["clusters"], p["new"], p["new_structural"]) for p in over] == [("pin1", 2, 2, 2), ("pin2", 1, 0, 0)]   # ontological and structural both


def test_import_one_representative_per_cluster_biggest_first_within_the_limit_and_once(tmp_path):
    rs = {"taycann": [row("A-1", "1", failed=["contact"]), row("B-1", "2", failed=["contact"]),
                      row("C-1", "3", failed=["goal"]), row("D-1", "4", failed=["off_lanelet"])]}
    d = make_round(tmp_path, "d5c7c72", rs)
    T.run(d, kinder=kinder({"A-1": LATE, "B-1": LATE, "C-1": ROUTE, "D-1": ("perception", ["keep_lead"], ["role_empty"])}))
    ws = tmp_path / "road" / ".metis"
    made = T.import_round(d, ws, limit=2)
    assert len(made) == 2
    recs = [json.loads((ws / "surprises" / ("%s.json" % sid)).read_text()) for sid in made]
    assert recs[0]["harvest"]["rules"] == ["brake_cross_late"] and recs[0]["harvest"]["count"] == 2   # the biggest first
    assert recs[0]["harvest"]["scenario"] == "A-1" and recs[0]["status"] == "open" and recs[0]["who"] == "world"
    assert recs[0]["trace"].startswith("traces/") and (ws / "traces" / "harvest-d5c7c72-A-1" / "seg-0.jsonl").is_file()
    assert len(T.import_round(d, ws, limit=2)) == 1                                    # the rest, never one twice
    assert T.import_round(d, ws, limit=2) == []


def test_a_goal_reached_out_of_its_window_is_soft_counted_and_never_a_cluster(tmp_path):
    late = {"reached": False, "position_t": 9.0, "window_ok": False}
    d = make_round(tmp_path, "p3", {"taycann": [row("W-1", "1", failed=["goal"], goal=late), row("W-2", "2", failed=["goal"], goal=late),
                                                row("H-1", "3", failed=["contact"]), row("P-1", "4")]})
    calls = []

    def k(r):
        calls.append(r["id"])
        return kinder({"H-1": LATE})(r)
    out = T.run(d, kinder=k)
    s = out["summary"]
    assert (s["passed"], s["soft"], s["failed"], s["clusters"]) == (1, 2, 1, 1) and calls == ["H-1"]
    assert s["by_measure"] == {"goal:window": 2, "contact": 1}
    assert "2 SOFT" in (d / "triage.md").read_text()


def test_a_machine_record_is_about_its_contact_partner_else_its_bound_things(tmp_path):
    tr = tmp_path / "tr"
    tr.mkdir()
    rows = [{"truth": 1, "cannot": []},
            {"k": 5, "ego": {"lane": "a", "contact": []}, "things": [{"id": "cr3", "role": "a1"}, {"id": "cr1", "role": "lead"}]},
            {"k": 6, "ego": {"lane": "a", "contact": ["cr7"]}, "things": []}]
    (tr / "truth.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows))
    assert T.named_things(tr, [0, 6]) == ["cr7"]
    assert T.named_things(tr, [0, 5]) == ["cr1", "cr3"]                  # the near roles first
    assert T.named_things(tmp_path / "none", [0, 5]) == []
