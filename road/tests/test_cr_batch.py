"""cr_batch (cr-harvest s-f4e297da): the split, the row, the record, the queue's claim and recovery, with no SUMO."""
import importlib.util
import json
import os
from pathlib import Path

SPEC = importlib.util.spec_from_file_location("cr_batch", Path(__file__).resolve().parents[1] / "tools" / "cr_batch.py")
B = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(B)

JOB = {"id": "ZAM_Test-1_1_T-1", "set": "recorded", "source": "hand-crafted", "country": "ZAM", "tags": ["urban"]}


def summ(**cr):
    base = {"goal_reached": True, "goal_t": 5.0, "goal_position_t": 5.0, "goal_window_s": [[4.0, 6.0]], "contact": False,
            "contacts": [], "off_lanelet_ticks": 0, "off_lanelet_m": 0.0, "errors": []}
    base.update(cr)
    return {"ticks": 50, "t": 5.0, "arrived": True, "collision_events": 0, "violations": 0, "rc": 100.0,
            "director": {"cr": base}}


def test_split_is_the_same_everywhere_and_weighted():
    hosts = [("taycann", 12), ("panzer", 28)]
    ids = ["ID_%d" % i for i in range(4000)]
    a = [B.owner(i, hosts) for i in ids]
    assert a == [B.owner(i, list(hosts)) for i in ids]
    share = a.count("panzer") / len(a)
    assert 0.65 < share < 0.75


def test_row_pass_fail_error(tmp_path):
    r = B.make_row(JOB, tmp_path, 1, "s", 1.0, summ(), "", 0, False)
    assert r["error"] is None and r["failed"] == [] and r["goal"]["reached"]
    r = B.make_row(JOB, tmp_path, 1, "s", 1.0, summ(contact=True, contacts=[[1.0, 3]], goal_reached=False), "", 0, False)
    assert r["failed"] == ["contact", "goal"] and r["contacts"] == 1
    err = "Traceback\n  File x\nRuntimeError: sumo: the ego was not inserted in 601 steps\nQuitting (on error).\n"
    r = B.make_row(JOB, tmp_path, 1, "s", 1.0, None, err, 1, False)
    assert r["error"]["kind"] == "crash" and r["error"]["line"].startswith("RuntimeError: sumo")
    assert B.make_row(JOB, tmp_path, 1, "s", 1.0, None, "", None, True)["error"]["kind"] == "timeout"


def test_record_is_the_workspace_shape(tmp_path):
    (tmp_path / "records").mkdir()
    row = B.make_row(JOB, tmp_path, 1, "s", 1.0, summ(goal_reached=False, goal_t=None), "", 0, False)
    rid = B.make_record(row, tmp_path, tmp_path / "runs" / JOB["id"])
    rec = json.loads((tmp_path / "records" / (rid + ".json")).read_text())
    assert rec["who"] == "world" and rec["status"] == "open" and rec["member"] == "planner" and rec["reading"]
    assert rec["atoms"] == ["goal"]


def test_claim_and_recover(tmp_path, monkeypatch):
    monkeypatch.setattr(B, "HARVEST", tmp_path)
    monkeypatch.setattr(B, "pin", lambda: "abc1234")
    h = B.home("hostx")
    B.write(h / "queue" / (JOB["id"] + ".json"), JOB)
    got = B.claim(h)
    assert got == h / "running" / (JOB["id"] + ".json") and B.claim(h) is None
    (h / "running" / (JOB["id"] + ".pid")).write_text("999999999 hostx\n")       # a worker that is gone
    class A:
        host = "hostx"
    assert B.cmd_recover(A, quiet=True) == 1
    assert (h / "queue" / (JOB["id"] + ".json")).exists()
    (h / "running" / "other.json").write_text("{}")
    (h / "running" / "other.pid").write_text("%d hostx\n" % os.getpid())       # a live one stays
    assert B.cmd_recover(A, quiet=True) == 0 and (h / "running" / "other.json").exists()


def test_record_window_in_trace_ticks():
    row = B.make_row(JOB, None, 1, "s", 1.0, summ(goal_reached=False, goal_t=None, goal_window_s=[[4.0, 40.0]]), "", 0, False)
    row["t"] = 70.0
    assert B.window(row, (1, 700)) == [100, 400]
    row["t"] = 20.0                                                     # the run ends before the window does
    assert B.window(row, (1, 200)) == [1, 200]
    row = B.make_row(JOB, None, 1, "s", 1.0, summ(contact=True, contacts=[[3.0, 7]]), "", 0, False)
    assert B.window(row, (1, 500)) == [1, 30]
