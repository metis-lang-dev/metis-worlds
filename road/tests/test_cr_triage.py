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
    assert T.named_things(tr, [0, 5]) == ["cr7"]                         # the run's first contact, past the window
    rows[2]["ego"]["contact"] = []
    (tr / "truth.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows))
    assert T.named_things(tr, [0, 5]) == ["cr1", "cr3"]                  # no contact at all: the bound, the near roles first
    assert T.named_things(tmp_path / "none", [0, 5]) == []


def test_a_contact_from_behind_on_a_recording_is_the_worlds_the_rest_the_laws(tmp_path):
    def truth(tr, partner_lane, partner_s):
        rows = [{"truth": 1, "cannot": []},
                {"k": 13, "ego": {"lane": "a", "s": 20.0, "contact": []}, "things": [{"id": "cr9", "lane": partner_lane, "s": partner_s - 2}]},
                {"k": 14, "ego": {"lane": "a", "s": 21.0, "contact": ["cr9"]}, "things": [{"id": "cr9", "lane": partner_lane, "s": partner_s}]}]
        (tr / "truth.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows))
    d = make_round(tmp_path, "p4", {"taycann": [row("R-1", "1", failed=["contact"]), row("F-1", "2", failed=["contact"]),
                                                row("S-1", "3", failed=["contact"]), row("I-1", "4", failed=["contact"], set="interactive")]})
    for rid, lane, s in (("R-1", "a", 18.0), ("F-1", "a", 26.0), ("S-1", "b", 21.0), ("I-1", "a", 18.0)):
        truth(d / "taycann" / "runs" / rid / "trace" / ("cr_%s-1" % rid), lane, s)
    sides = {r["id"]: T.contact_side(T.record_of(r)[1]) for r in T.rows(d)}
    assert sides == {"R-1": ("behind", "cr9"), "F-1": ("front", "cr9"), "S-1": ("side", "cr9"), "I-1": ("behind", "cr9")}
    k = T.kind_one(next(r for r in T.rows(d) if r["id"] == "R-1"))
    assert k["kind"] == "world" and "from behind on a recorded trajectory" in k["why"]

    def kinder_(r):                                            # the law's half (the real triage is not run here)
        k = T.kind_one(r) if r["id"] == "R-1" else {"kind": "structural", "member": "responder", "record": r["record_id"],
                                                     "rules": ["brake_lon"], "atoms": ["resp_lon"]}
        if r["id"] != "R-1":
            k["partner"] = sides[r["id"]][0]
        return k
    out = T.run(d, kinder=kinder_)
    got = sorted((c["measure"], c["kind"], c["count"]) for c in out["clusters"])
    assert got == [("contact:behind", "structural", 1), ("contact:behind", "world", 1),      # the interactive one stays the law's
                   ("contact:front", "structural", 1), ("contact:side", "structural", 1)]
    made = T.import_round(d, tmp_path / "road" / ".metis", limit=20)
    recs = [json.loads((tmp_path / "road" / ".metis" / "surprises" / ("%s.json" % s)).read_text()) for s in made]
    assert "R-1" not in {r["harvest"]["scenario"] for r in recs}                         # the world's: not the loop's


def test_a_scenario_the_world_could_not_pose_is_an_error_of_the_worlds():
    """The architect's ruling (the catalog at d5c7c72): no goal edge, or a run of at most 5 ticks, is error:world, never a fail."""
    def cr(goal_edge, ticks, failed=("goal",)):
        return row("x", "1", failed=list(failed), ticks=ticks, summary={"director": {"cr": {"goal_edge": goal_edge}}})
    assert T.measure(cr(None, 300)) == "error:world"
    assert T.measure(cr("e12", 3)) == "error:world"
    assert T.measure(cr("e12", 300)) == "goal:position"
    assert T.measure(cr(None, 300, failed=())) == "error:world"               # even a pass
    assert T.measure(row("y", "1", failed=["goal"])) == "goal:position"        # no summary (older rows): as before


def test_a_time_only_goal_is_soft_only_and_the_provenance_table_counts_by_set(tmp_path):
    """The architect's ruling (2026-11-06): a time-only goal (cr_world's route note) has no place: its goal is soft, never
    goal:position nor error:world; a region goal with no edge stays error:world; the provenance table counts by set/source."""
    to = {"director": {"cr": {"goal_edge": "e9", "route_note": "a time-only goal: the ego drives on"}}}
    no_edge = {"director": {"cr": {"goal_edge": None, "route_note": None}}}
    assert T.measure(row("t", "1", failed=["goal"], ticks=300, summary=to)) == T.SOFT
    assert T.measure(row("t", "1", failed=["goal", "contact"], ticks=300, summary=to)) == "contact"
    assert T.measure(row("r", "1", failed=["goal"], ticks=300, summary=no_edge)) == "error:world"
    d = make_round(tmp_path, "p6", {"taycann": [row("A", "1", ticks=300, summary=to), row("B", "2", failed=["goal"], ticks=300, summary=to),
                                                row("C", "3", failed=["contact"], ticks=300, source="NGSIM")]})
    out = T.run(d, kinder=kinder({"C": LATE}))
    assert out["provenance"]["recorded/hand-crafted"] == {"rows": 2, "pass": 1, "soft": 1, "fail": 0, "error": 0}
    assert out["provenance"]["recorded/NGSIM"]["fail"] == 1 and "## By provenance" in (d / "triage.md").read_text()


def test_a_rerun_row_is_triaged_again(tmp_path):
    d = make_round(tmp_path, "p7", {"taycann": [row("A-1", "1", failed=["contact"])]})
    calls = []

    def k(r):
        calls.append(r["record_id"])
        return kinder({"A-1": LATE})(r)
    T.run(d, kinder=k)
    f = d / "taycann" / "rows" / "A-1.json"
    r = json.loads(f.read_text())
    r["record_id"] = "rec-A-1-rerun"
    f.write_text(json.dumps(r))
    (d / "taycann" / "records" / "rec-A-1.json").rename(d / "taycann" / "records" / "rec-A-1-rerun.json")
    T.run(d, kinder=k)
    assert calls == ["rec-A-1", "rec-A-1-rerun"]


def test_the_named_things_fall_back_to_the_runs_first_contact_then_the_nearest_on_the_lane(tmp_path):
    tr = tmp_path / "tr"
    tr.mkdir()
    rows = [{"truth": 1, "cannot": []},
            {"k": 5, "ego": {"lane": "a", "s": 10.0, "contact": []}, "things": [{"id": "far", "lane": "a", "s": 60.0}, {"id": "near", "lane": "a", "s": 15.0}]},
            {"k": 9, "ego": {"lane": "a", "s": 12.0, "contact": ["cr4"]}, "things": []}]
    (tr / "truth.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows))
    assert T.named_things(tr, [0, 5]) == ["cr4"]                       # the run's first contact, outside the window
    rows[2]["ego"]["contact"] = []
    (tr / "truth.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows))
    assert T.named_things(tr, [0, 5]) == ["near"]                       # nobody bound: the nearest on the ego's lane


def test_a_goal_edge_with_no_route_to_it_is_the_worlds():
    nr = {"director": {"cr": {"goal_edge": "205", "route_note": "no way from 114 to the goal's edge 205"}}}
    assert T.measure(row("n", "1", failed=["goal"], ticks=300, summary=nr)) == "error:world"


def test_the_first_contact_tick_of_the_truth(tmp_path):
    tr = tmp_path / "tr"
    tr.mkdir()
    rows = [{"truth": 1}, {"k": 3, "ego": {"contact": []}, "things": []}, {"k": 8, "ego": {"contact": ["cr2"]}, "things": []}]
    (tr / "truth.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows))
    assert T.first_contact_tick(tr) == 8 and T.first_contact_tick(tmp_path / "none") is None


def test_ruling_b_a_follower_or_an_initial_contact_is_the_worlds(tmp_path):
    def write(tr, rows):
        tr.mkdir(parents=True)
        (tr / "truth.jsonl").write_text("".join(json.dumps(r) + "\n" for r in [{"truth": 1}] + rows))
    write(tmp_path / "f", [{"k": 20, "ego": {"lane": ":j_1", "s": 1.0, "contact": []}, "things": [{"id": "c1", "lane": "a", "s": 9.0, "role": "follower"}]},
                           {"k": 40, "ego": {"lane": ":j_1", "s": 3.0, "contact": ["c1"]}, "things": [{"id": "c1", "lane": ":j_2", "s": 2.0, "role": None}]}])
    write(tmp_path / "i", [{"k": 2, "ego": {"lane": "a", "s": 5.0, "contact": ["c2"]}, "things": [{"id": "c2", "lane": "a", "s": 9.0, "role": "lead"}]}])
    write(tmp_path / "s", [{"k": 40, "ego": {"lane": "a", "s": 5.0, "contact": ["c3"]}, "things": [{"id": "c3", "lane": "b", "s": 9.0, "role": "a1"}]}])
    assert T.contact_side(tmp_path / "f") == ("behind", "c1")             # a follower turning onto a sibling lane
    assert T.contact_side(tmp_path / "i") == ("initial", "c2")
    assert T.contact_side(tmp_path / "s") == ("side", "c3")               # the law's


def test_a_partner_standing_while_reported_moving_is_the_worlds(tmp_path):
    def write(tr, moving):
        tr.mkdir(parents=True)
        rows = [{"truth": 1}] + [{"k": k, "ego": {"lane": "a", "s": 30.0 + k, "contact": ["L"] if k == 40 else []},
                                  "things": [{"id": "L", "lane": "a", "s": 80.0 + (k if moving else 0), "v": 24.0, "role": "lead"}]}
                                 for k in range(12, 41)]
        (tr / "truth.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows))
    write(tmp_path / "frozen", False)
    write(tmp_path / "moving", True)
    assert T.frozen_partner(tmp_path / "frozen", "L") and not T.frozen_partner(tmp_path / "moving", "L")


def test_a_partner_jumping_across_lanes_is_the_worlds(tmp_path):
    tr = tmp_path / "j"
    tr.mkdir()
    lanes = [":j_2", ":j_11", ":j_1", ":j_4", ":j_10", ":j_8"]
    rows = [{"truth": 1}] + [{"k": k, "ego": {"lane": ":j_6", "s": 5.0, "contact": ["P"] if k == 40 else []},
                              "things": [{"id": "P", "lane": lanes[(k // 2) % 6], "s": 10.0, "v": 9.0}]} for k in range(28, 41)]
    (tr / "truth.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows))
    assert T.lane_jumping(tr, "P")
    (tr / "truth.jsonl").write_text("".join(json.dumps(dict(r, things=[dict(x, lane=":j_8") for x in r.get("things", [])]) if "k" in r else r) + "\n" for r in rows))
    assert not T.lane_jumping(tr, "P")


def test_the_ego_standing_when_hit_is_the_worlds(tmp_path):
    tr = tmp_path / "w"
    tr.mkdir()
    rows = [{"truth": 1}, {"k": 30, "ego": {"lane": "a", "s": 4.0, "v": 0.0, "contact": ["P"]}, "things": [{"id": "P", "lane": "a", "s": 8.0, "v": 3.0}]}]
    (tr / "truth.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows))
    assert T.ego_standing(tr)
    rows[1]["ego"]["v"] = 2.0
    (tr / "truth.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows))
    assert not T.ego_standing(tr)


def test_ruling_l2_a_met_cut_in_and_an_unavoidable_start_are_the_worlds(tmp_path):
    """(i) a partner coming from another lane, bound before, lead under 1 s before the contact, with brake_max asked in that second;
    not when the ego came onto the partner's lane, nor for a partner never bound. (iii) at the first moving tick no brake stops
    within the gap to the lead (the lead braking at its hardest meanwhile)."""
    def run(name, things_by_k, resp_by_k=None, ego_lane="a"):
        tr = tmp_path / name / "trace" / "cr_x-1"
        tr.mkdir(parents=True)
        rows = [{"truth": 1}] + [{"k": k, "ego": {"lane": ego_lane, "s": 10.0 + k * 0.5, "v": 5.0, "contact": ["P"] if k == 30 else []},
                                  "things": th} for k, th in things_by_k.items()]
        (tr / "truth.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows))
        (tmp_path / name / "cr:x-1.jsonl").write_text("".join(json.dumps({"tick": k - 1, "resp": r}) + "\n" for k, r in (resp_by_k or {}).items()))
        return tr
    cut = {k: [{"id": "P", "lane": "b" if k < 25 else "a", "s": 30.0, "v": 4.0, "role": "a1" if k < 25 else "lead", "length": 4.5}] for k in range(15, 31)}
    assert T.cut_in_met(run("cut", cut, {28: "brake_max"}), "P")
    assert not T.cut_in_met(run("soft", cut, {28: "brake_min"}), "P")                 # no brake_max: the law's
    merge = {k: [{"id": "P", "lane": "a", "s": 30.0, "v": 0.0, "role": "leadright" if k < 25 else "lead", "length": 4.5}] for k in range(15, 31)}
    assert not T.cut_in_met(run("merge", merge, {28: "brake_max"}), "P")              # the ego onto the partner's lane
    start = {k: [{"id": "P", "lane": "a", "s": 13.0 + k * 0.5, "v": 0.3, "role": "lead", "length": 4.5}] for k in range(2, 31)}
    tr = run("start", start)
    rows = [json.loads(x) for x in (tr / "truth.jsonl").read_text().splitlines()]
    for r in rows:
        if "k" in r:
            r["ego"]["v"] = 15.0
    (tr / "truth.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows))
    assert T.unavoidable_start(tr, "P")                                                # 15 m/s, ~2 m behind a crawling lead
