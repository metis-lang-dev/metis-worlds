"""cr_bench (planner-loop s-0dcc5ed1 step 2): the oracle row's outcome by precedence, the list and the table; with the planner
venv (road/planner/setup-venv.sh), the bench end to end on a built straight-road scenario with the stub planner (no network,
no dataset) and its solution file written and read back."""
import importlib.util
import json
from pathlib import Path

import pytest

ROAD = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("cr_bench", ROAD / "planner" / "cr_bench.py")
B = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(B)


def row(**kw):
    r = B.blank_row("X", "reactive")
    r.update(goal=False, collision=False, offroad=False, feasible=True)
    r.update(kw)
    return r


@pytest.mark.parametrize("kw, outcome", [
    ({"goal": True}, "goal"),
    ({}, "window"),
    ({"infeasible": True, "reason": {"cycle": 1}}, "infeasible"),
    ({"goal": True, "collision": True}, "collision"),
    ({"goal": True, "offroad": True}, "offroad"),
    ({"collision": True, "offroad": True}, "collision"),
    ({"infeasible": True, "collision": True}, "collision"),
    ({"error": True, "reason": {"exception": "E: x"}, "goal": True}, "error"),
])
def test_outcome_by_precedence(kw, outcome):
    assert B.classify(row(**kw)) == outcome


def test_list_skips_comments_and_keeps_the_id(tmp_path):
    p = tmp_path / "l.txt"
    p.write_text("# head\nA_1  # why\n\n  B_2\n#C_3\n")
    assert B.read_list(p) == ["A_1", "B_2"]


def test_table_counts_and_reasons():
    rows = [row(id="A", goal=True, outcome="goal", goal_kind="region", traffic="none", cost=1.5, ms_cycle=90.0, cycles=3, steps=9, goal_window=[8, 9]),
            row(id="B", outcome="infeasible", infeasible=True,
                reason={"cycle": 2, "time_step": 6, "kinematics": 5, "collision": 1, "samples": 6,
                        "by_constraint": {"kappa": 4, "velocity": 1, "yaw_rate": 0}}),
            row(id="C", outcome="error", reason={"child": "timeout after 900s"})]
    t = B.table(rows, "t")
    assert "3 scenarios: goal 1, infeasible 1, error 1." in t
    assert "| A | goal | region | none | yes | no | no | yes | 1.5 | 90.0 | 3 | 9 | 8–9 |" in t
    assert "Goal kinds: region 1, — 2; traffic: none 1, — 2." in t
    assert "no feasible sample at step 6 (cycle 2): 5 of 6 kinematic [kappa 4, velocity 1], 1 collision" in t
    assert "timeout after 900s" in t


def test_jobs_never_exceed_four(tmp_path, monkeypatch):
    seen = []
    monkeypatch.setattr(B, "child", lambda s, p, o: (seen.append(s), row(id=s, outcome="window"))[1])
    monkeypatch.setattr(B, "ThreadPoolExecutor", lambda max_workers: (seen.append(("w", max_workers)),
                                                                      __import__("concurrent.futures").futures
                                                                      .ThreadPoolExecutor(max_workers))[1])
    lst = tmp_path / "l.txt"
    lst.write_text("A\nB\n")
    rows, tf = B.batch(lst, jobs=32, out=tmp_path, table_file=tmp_path / "t.md")
    assert ("w", 4) in seen and [r["id"] for r in rows] == ["A", "B"] and tf.is_file()


# ---------------------------------------------------------------- with the planner venv
def straight_scenario(path):
    """A 200 m straight two-boundary lanelet, no obstacles; the ego at x=10 at 10 m/s; the goal a box at x 50..70 in 3..6 s."""
    import numpy as np
    from commonroad.common.file_writer import CommonRoadFileWriter, OverwriteExistingFile
    from commonroad.common.util import Interval
    from commonroad.geometry.shape import Rectangle
    from commonroad.planning.goal import GoalRegion
    from commonroad.planning.planning_problem import PlanningProblem, PlanningProblemSet
    from commonroad.scenario.lanelet import Lanelet, LaneletNetwork
    from commonroad.scenario.scenario import Scenario, ScenarioID
    from commonroad.scenario.state import CustomState, InitialState
    xs = np.linspace(0.0, 200.0, 41)
    lan = Lanelet(left_vertices=np.c_[xs, np.full_like(xs, 1.75)], center_vertices=np.c_[xs, np.zeros_like(xs)],
                  right_vertices=np.c_[xs, np.full_like(xs, -1.75)], lanelet_id=1)
    scen = Scenario(0.1, ScenarioID(country_id="ZAM", map_name="Bench", map_id=1))
    scen.add_objects(LaneletNetwork.create_from_lanelet_list([lan]))
    init = InitialState(time_step=0, position=np.array([10.0, 0.0]), velocity=10.0, orientation=0.0, yaw_rate=0.0,
                        slip_angle=0.0, acceleration=0.0)
    goal = GoalRegion([CustomState(time_step=Interval(30, 60), position=Rectangle(20.0, 3.0, np.array([60.0, 0.0])))])
    pps = PlanningProblemSet([PlanningProblem(1, init, goal)])
    CommonRoadFileWriter(scen, pps, "bench", "TUM", "", set()).write_to_file(str(path), OverwriteExistingFile.ALWAYS)
    return path


def test_stub_run_writes_a_solution_and_its_row(tmp_path):
    pytest.importorskip("commonroad_rp", reason="the planner venv: road/planner/setup-venv.sh")
    from commonroad.common.solution import CommonRoadSolutionReader
    xml = straight_scenario(tmp_path / "ZAM_Bench-1_1_T-1.xml")
    r = B.run(str(xml), planner="stub", out=tmp_path / "out")
    assert r["outcome"] == "goal", r
    assert r["goal"] and not r["collision"] and not r["offroad"] and r["feasible"]
    assert r["goal_window"] == [30, 60] and r["steps"] == 60 and r["cost"] is not None
    assert r["goal_kind"] == "region" and r["traffic"] == "none"
    back = CommonRoadSolutionReader.open(r["solution"])
    assert len(back.planning_problem_solutions[0].trajectory.state_list) == 61
    assert json.loads((tmp_path / "out" / "ZAM_Bench-1_1_T-1" / "row.json").read_text())["outcome"] == "goal"


def test_a_missing_scenario_is_an_error_row_not_a_crash(tmp_path):
    pytest.importorskip("commonroad_rp", reason="the planner venv: road/planner/setup-venv.sh")
    r = B.run("ZAM_Nowhere-9_9_T-9", planner="stub", out=tmp_path)
    assert r["outcome"] == "error" and "FileNotFoundError" in r["reason"]["exception"]
