"""trajplan (metis-plugin s-df4ff191 step 5): the commander (road/planner/commander.py) decides as RoadDomain's
Commander (road core/command.cc fb638d0) rule for rule; the lane map writer; the binding plans when its library is
built (TRAJPLAN_LIB or the planner checkout's bazel-bin; skipped otherwise)."""
import importlib.util
import math
from pathlib import Path
from types import SimpleNamespace

import pytest

ROAD = Path(__file__).resolve().parents[1]


def _load(name):
    spec = importlib.util.spec_from_file_location(name, ROAD / "planner" / (name + ".py"))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


C = _load("commander")
T = _load("trajplan")
EGO = {"x": 0.0, "y": 0.0, "heading": 0.0, "speed": 10.0}
RD = {"cap": None, "line": 20.0, "stop": None, "roles": {"lead": 7, "vru1": 9}}


def decide(rule, rd=RD, member="planner", ego=EGO):
    c = C.Commander(ego_front=3.8)
    c.fired(member, rule, rd, ego)
    return c.command(member)


# command.cc's table: rule -> (kind, v_target, lead_id, yield_id, x of the point or None)
TABLE = [
    ("accel", C.KEEP, 0.0, 0, 0, None),
    ("keep_limit", C.KEEP, 0.0, 0, 0, None),
    ("keep_gap", C.KEEP, 10.0, 0, 0, None),
    ("brake_cross", C.KEEP, 7.0, 0, 0, None),
    ("inch_hidden", C.KEEP, 1.5, 0, 0, None),
    ("keep_lead", C.FOLLOW, 0.0, 7, 0, None),
    ("change[D=left]", C.CHANGE_LEFT, 0.0, 0, 0, None),
    ("change_pass[D=right]", C.CHANGE_RIGHT, 0.0, 0, 0, None),
    ("change_oncoming", C.PASS_OPPOSITE, 0.0, 7, 0, None),
    ("yield_red", C.STOP_AT, 0.0, 0, 0, 3.8 + 20.0),
    ("yield_zone", C.YIELD, 0.0, 0, 0, 3.8 + 20.0),
    ("yield_walker", C.YIELD, 0.0, 0, 9, 3.8 + 20.0),
    ("brake_lon[R=brake_min]", C.STOP_AT, 0.0, 0, 0, 3.8 + 100.0 / 8.0),
    ("brake_lon[R=brake_max]", C.STOP_AT, 0.0, 0, 0, 3.8 + 100.0 / 16.0),
    ("stop_lat_left", C.KEEP, 10.0, 0, 0, None),
]


@pytest.mark.parametrize("rule,kind,v,lead,yld,x", TABLE)
def test_commander_table(rule, kind, v, lead, yld, x):
    d = decide(rule)
    assert d["kind"] == kind and abs(d["v_target"] - v) < 1e-6 and d["lead_id"] == lead and d["yield_id"] == yld
    if x is not None:
        assert abs(d["x"] - x) < 1e-6


def test_commander_no_command():
    for rule in ("change_home", "drive_away", "change[D=up]", "drive"):
        assert decide(rule) is None


def test_commander_stop_wish():
    d = decide("accel", rd=dict(RD, cap=0.1))
    assert d["kind"] == C.STOP_AT and d["reason"] == "stop_wish" and abs(d["x"] - (3.8 + 100 / 4.0 + 0.5)) < 1e-6


def test_commander_seq_and_change_hold():
    c = C.Commander(ego_front=3.8)
    c.fired("planner", "keep_limit", RD, EGO)
    assert c.command("planner")["seq"] == 1
    c.fired("planner", "keep_limit", RD, EGO)
    assert c.command("planner")["seq"] == 1                          # the same decision keeps its seq
    c.fired("planner", "change[D=left]", RD, EGO)
    assert c.command("planner")["kind"] == C.CHANGE_LEFT
    c.fired("planner", "keep_limit", RD, EGO)                         # held while the change runs
    assert c.command("planner", {"cmd_seq": 2, "change": C.CHANGE_ACTIVE})["kind"] == C.CHANGE_LEFT
    assert c.changing({"cmd_seq": 2, "change": C.CHANGE_ACTIVE}) == "left"
    assert c.command("planner", {"cmd_seq": 2, "change": C.CHANGE_DONE})["kind"] == C.KEEP    # ended: the next goes
    c.fired("planner", "change[D=right]", RD, EGO)
    c.command("planner")
    c.fired("responder", "stop_lat_right", RD, EGO)                   # the lateral stop always goes
    assert c.command("responder", {"cmd_seq": 4, "change": C.CHANGE_ACTIVE})["kind"] == C.KEEP


def lanemap():
    lanes = {"a_0": SimpleNamespace(id="a_0", shape=[(0, 0), (10, 0)], left="a_1", left_opposite=False, right=None,
                                    right_opposite=False, speed=10.0, internal=False, index=0, width=3.2, succ=["b_0"],
                                    allow=None, disallow=None, function="normal", kind="driving"),
             "a_1": SimpleNamespace(id="a_1", shape=[(0, 3.2), (10, 3.2)], left=None, left_opposite=False, right="a_0",
                                    right_opposite=False, speed=None, internal=False, index=1, width=3.2, succ=[],
                                    allow=None, disallow=None, function="normal", kind="driving"),
             "b_0": SimpleNamespace(id="b_0", shape=[(10, 0), (30, 0)], left=None, left_opposite=False, right=None,
                                    right_opposite=False, speed=10.0, internal=True, index=0, width=3.2, succ=[],
                                    allow=None, disallow=None, function="internal", kind="driving"),
             "w_0": SimpleNamespace(id="w_0", shape=[(0, -3), (10, -3)], left=None, left_opposite=False, right=None,
                                    right_opposite=False, speed=2.0, internal=False, index=0, width=2.0, succ=[],
                                    allow=("pedestrian",), disallow=None, function="normal", kind="driving")}
    return SimpleNamespace(lanes=lanes)


def test_lanes_file(tmp_path):
    idx = T.lanes_file(lanemap(), tmp_path / "m.lanes")
    text = (tmp_path / "m.lanes").read_text().splitlines()
    assert text[0] == "lanemap 2 semantic" and set(idx) == {"a_0", "a_1", "b_0"}     # the sidewalk is no lane to plan on
    heads = {l.split()[2]: l.split() for l in text if l.startswith("lane ")}
    assert heads["a_0"][8] == str(idx["a_1"]) and heads["a_1"][9] == str(idx["a_0"])    # left / right
    assert heads["b_0"][5] == "1" and heads["a_1"][6] == "13.9000"                     # junction; the default speed
    assert int(heads["a_0"][7]) == 21                                                  # 10 m every 0.5 m
    assert "succ %d %d" % (idx["a_0"], idx["b_0"]) in text


def test_binding_plans(tmp_path):
    if not T.LIB.is_file():
        pytest.skip("libtrajplan_c.so not built (planner: bazel build //trajplan:libtrajplan_c.so)")
    T.lanes_file(lanemap(), tmp_path / "m.lanes")
    p = T.Trajplan(tmp_path / "m.lanes", {"wheelbase": 2.9, "b": 1.45, "length": 4.6, "width": 1.8},
                   replan_tol=0, replan_lon=0, replan_dv=0)
    p.obstacles(0.0, [])
    p.command("keep", 0.0)
    st, pts = p.plan(0.0, 3.0, 0.0, 0.0, 5.0)
    assert st["ok"] and len(pts) > 10 and abs(pts[0][1] - 3.0) < 0.05 and pts[10][1] > pts[0][1]
    p.close()


def test_sample():
    pts = [(0.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0), (0.2, 2.0, 0.0, math.pi, 3.0, 0.0, 0.0)]
    q = T.sample(pts, 0.1)
    assert abs(q[1] - 1.0) < 1e-9 and abs(q[4] - 2.0) < 1e-9
