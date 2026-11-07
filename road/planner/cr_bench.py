#!/usr/bin/env python3
"""cr_bench.py — the CommonRoad native loop + the BSD reactive planner baseline (planner-loop s-0dcc5ed1 step 2).

    road/.venv-planner/bin/python road/planner/cr_bench.py run ID [--planner reactive|stub] [--out DIR]
    road/.venv-planner/bin/python road/planner/cr_bench.py batch LIST [--jobs 4] [--out DIR] [--table FILE]

run: the scenario ID (a catalog card's source.code, else found under $COMMONROAD_ROOT or the reactive planner's examples) and
its first planning problem → commonroad-route-planner's shortest reference path → the reactive planner driven natively, cycle
by cycle, against the scenario's own recorded obstacles (no SUMO, no family yet) until the goal, a failed plan, or the goal's
last time step → OUT/ID/solution.xml (a CommonRoad solution, read back) + OUT/ID/row.json, the oracle's row:
  outcome   goal | collision | offroad | infeasible | window | error   (the first that holds, in this order of precedence:
            error > collision > offroad > infeasible > goal > window)
  goal      the drivability checker's goal_reached over the solution (position and the goal's time window)
  collision obstacle_collision; offroad: boundary_collision; feasible: solution_feasible (KS model, input reconstruction)
  cost      the JB1 cost (CommonRoad 2020a XML files name no cost function: JB1 is the reactive planner's own choice)
  ms_cycle  the planner's mean plan() time per cycle; cycles, steps
  reason    for infeasible: the planner's infeasible_reason_dict of the failing cycle + its collision/kinematics counts
batch: each ID of LIST (one per line, # comments) as its own `run` child under a MemoryMax=6G scope, nice, --jobs at most 4
(never all cores), a per-run timeout (PLANNER_TIMEOUT, 900 s): a child that dies or times out is a row `error` with its
reason, never a crash of the batch; then the table FILE (default road/planner/tables/baseline-<worlds sha>.md).
OUT defaults to ../.worlds/planner (PLANNER_OUT), outside every repo. The stub planner (tests, no network) keeps the lane at
the initial speed along the reference path.
"""
import argparse
import json
import math
import os
import subprocess
import sys
import time
import traceback
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROAD = HERE.parent
REPO = ROAD.parent
WS = Path(os.environ.get("PLANNER_WS", str(Path.home() / "repo" / "perotheia-packages")))
OUT = Path(os.environ.get("PLANNER_OUT", str(WS / ".worlds" / "planner")))
CR_ROOT = Path(os.environ.get("COMMONROAD_ROOT", "/bigdata/datasets/commonroad"))
EXAMPLES = Path(os.environ.get("PLANNER_EXAMPLES", str(CR_ROOT / "reactive-planner-examples")))
CATALOG = ROAD / "catalog" / "commonroad"
TIMEOUT = float(os.environ.get("PLANNER_TIMEOUT", "900"))
MAX_JOBS = 4
OUTCOMES = ("goal", "collision", "offroad", "infeasible", "window", "error")


# ---------------------------------------------------------------- finding a scenario
def card_path(sid):
    """The catalog card's source.code, when a card names the scenario (a plain read: no yaml dependency)."""
    f = CATALOG / (sid + ".yaml")
    if not f.is_file():
        return None
    for line in f.read_text().splitlines():
        s = line.strip()
        if s.startswith("code:"):
            p = Path(s.split(":", 1)[1].strip())
            return p if p.is_file() else None
    return None


def find(sid):
    p = Path(sid)
    if p.suffix == ".xml" and p.is_file():
        return p
    c = card_path(sid)
    if c:
        return c
    for base in (EXAMPLES, CR_ROOT / "scenarios" / "scenarios" / "recorded"):
        for f in base.rglob(sid + ".xml"):
            return f
    for f in CR_ROOT.rglob(sid + ".cr.xml"):
        return f
    raise FileNotFoundError("no scenario %s (card, %s, %s)" % (sid, EXAMPLES, CR_ROOT))


# ---------------------------------------------------------------- the row
def blank_row(sid, planner):
    return {"id": sid, "planner": planner, "outcome": "error", "goal": None, "collision": None, "offroad": None,
            "feasible": None, "cost": None, "cost_function": "JB1", "ms_cycle": None, "cycles": 0, "steps": 0,
            "goal_window": None, "reason": None, "file": None, "solution": None, "seconds": None}


def classify(row):
    """The outcome by precedence: a crash, then a collision, off the road, a failed plan, the goal, the window missed."""
    if row.get("reason") and row.get("error"):
        return "error"
    if row["collision"]:
        return "collision"
    if row["offroad"]:
        return "offroad"
    if row.get("infeasible"):
        return "infeasible"
    if row["goal"]:
        return "goal"
    return "window"


# ---------------------------------------------------------------- the planners
def configure(scenario, pps, pp):
    from commonroad_rp.utility.config import ReactivePlannerConfiguration
    cfg = ReactivePlannerConfiguration()
    cfg.vehicle.update_vehicle_config({})            # the CommonRoad vehicle model's parameters (id 2, BMW 320i)
    cfg.debug.multiproc = False                      # parallelism is the batch's, never the planner's own pool
    cfg.debug.show_plots = cfg.debug.save_plots = cfg.debug.show_evaluation_plots = False
    cfg.debug.logging_level = "WARNING"
    cfg.planning.dt = scenario.dt
    cfg.update(scenario=scenario, planning_problem=pp)
    cfg.planning_problem_set = pps
    return cfg


EXTEND_M = 150.0     # the reference path's straight extension past its end: the planner samples up to horizon x v beyond
BACK_M = 20.0        # and before its start: the route starts at the ego's centre, the planner's state is its rear axle


def reference_path(scenario, pp):
    """The package's own helper: commonroad-route-planner's shortest route → its reference path (polyline), extended
    straight past its last point by EXTEND_M along the end tangent: the route ends at the goal and the sampler's horizon
    reaches past it (DEU_Test-1_1_T-1: CurvilinearProjectionDomainLongitudinalError without it), and BACK_M before its
    first point along the start tangent (ZAM_Ramp-1_1-T-1: the ego starts on the path's first point, its rear axle 1.4 m
    behind it, CartesianProjectionDomainError without it)."""
    import numpy as np
    from commonroad_rp.utility.utils_coordinate_system import create_initial_ref_path
    ref = np.asarray(create_initial_ref_path(scenario.lanelet_network, pp))
    t = ref[-1] - ref[-2]
    t = t / max(np.linalg.norm(t), 1e-9)
    tail = ref[-1] + np.outer(np.arange(2.0, EXTEND_M + 1e-9, 2.0), t)
    h = ref[1] - ref[0]
    h = h / max(np.linalg.norm(h), 1e-9)
    head = ref[0] - np.outer(np.arange(BACK_M, 1e-9, -2.0), h)
    return np.vstack([head, ref, tail])


def goal_last_step(pp):
    ends = [st.time_step.end for st in pp.goal.state_list if getattr(st, "time_step", None) is not None]
    return int(max(ends)) if ends else None


def drive_reactive(cfg, ref_path, last_step, row):
    """run_planner's loop (the package's example): plan every replanning_frequency steps, follow the plan between."""
    from commonroad_rp.reactive_planner import ReactivePlanner
    from commonroad_rp.utility.utils_coordinate_system import create_coordinate_system
    planner = ReactivePlanner(cfg)
    # the package's coordinate system (spline smoothing + adaptive resampling); set_reference_path(polyline) alone passes
    # clcs 2025.2 no params and fails ('NoneType' has no attribute 'processing_option')
    planner.set_reference_path(coordinate_system=create_coordinate_system(ref_path))
    planner.record_state_and_input(deepcopy(planner.x_0))
    freq = cfg.planning.replanning_frequency
    optimal = None
    times = []
    while True:
        if planner.goal_reached():
            break
        if planner.x_0.time_step >= last_step:
            break
        k = len(planner.record_state_list) - 1
        if k % freq == 0 or optimal is None:
            planner.set_desired_velocity(current_speed=planner.x_0.velocity)
            n0 = len(planner.planning_times)
            try:
                optimal = planner.plan()
            except Exception as e:                   # the planner's own failure is a row (infeasible + why), not a crash
                optimal = None
                row["planner_exception"] = "%s: %s" % (type(e).__name__, str(e)[:200])
            times.extend(planner.planning_times[n0:])
            row["cycles"] += 1
            if not optimal:
                row["infeasible"] = True
                row["reason"] = {"cycle": row["cycles"], "time_step": int(planner.x_0.time_step),
                                 "kinematics": int(planner.infeasible_count_kinematics),
                                 "collision": int(planner.infeasible_count_collision),
                                 "by_constraint": {k_: int(v) for k_, v in planner.infeasible_reason_dict.items()},
                                 "samples": int(planner.total_count_samples)}
                if row.get("planner_exception"):
                    row["reason"]["exception"] = row["planner_exception"]
                break
            j = 1
        else:
            j = 1 + k % freq
        traj, lon, lat = optimal
        if j >= len(traj.state_list):
            optimal = None
            continue
        planner.record_state_and_input(traj.state_list[j])
        planner.reset(initial_state_cart=planner.record_state_list[-1], initial_state_curv=(lon[j], lat[j]),
                      collision_checker=planner.collision_checker, coordinate_system=planner.coordinate_system)
    row["ms_cycle"] = round(1000 * sum(times) / len(times), 1) if times else None
    return planner.record_state_list, cfg.vehicle


def drive_stub(cfg, ref_path, last_step, row):
    """No planner: the initial speed kept along the reference path (tests; checks the bench, not a planner)."""
    import numpy as np
    from commonroad_rp.reactive_planner import ReactivePlannerState
    pp = cfg.planning_problem
    x0 = ReactivePlannerState.create_from_initial_state(pp.initial_state, cfg.vehicle.wheelbase, cfg.vehicle.wb_rear_axle)
    path = np.asarray(ref_path)
    seg = np.linalg.norm(np.diff(path, axis=0), axis=1)
    s_acc = np.concatenate([[0.0], np.cumsum(seg)])
    s0 = float(s_acc[int(np.argmin(np.linalg.norm(path - x0.position, axis=1)))])
    v = float(x0.velocity)
    states = [x0]
    t0 = time.perf_counter()
    steps = (last_step or 50) - x0.time_step
    for i in range(1, steps + 1):
        s = min(s0 + v * cfg.planning.dt * i, float(s_acc[-1]) - 1e-6)
        k = int(np.searchsorted(s_acc, s, side="right") - 1)
        k = min(k, len(seg) - 1)
        a = (s - s_acc[k]) / max(seg[k], 1e-9)
        pos = path[k] + a * (path[k + 1] - path[k])
        th = math.atan2(*(path[k + 1] - path[k])[::-1])
        st = deepcopy(x0)
        st.time_step, st.position, st.orientation, st.velocity = x0.time_step + i, pos, th, v
        st.acceleration, st.yaw_rate, st.steering_angle = 0.0, 0.0, 0.0
        states.append(st)
    row["cycles"] = 1
    row["ms_cycle"] = round(1000 * (time.perf_counter() - t0), 1)
    return states, cfg.vehicle


PLANNERS = {"reactive": drive_reactive, "stub": drive_stub}


# ---------------------------------------------------------------- the oracle
def solution_of(cfg, states, vehicle):
    from commonroad.common.solution import Solution, PlanningProblemSolution, VehicleModel, VehicleType, CostFunction
    from commonroad.scenario.trajectory import Trajectory
    from commonroad_rp.reactive_planner import ReactivePlannerState
    shifted = [ReactivePlannerState.shift_state_to_center(s, vehicle.wb_rear_axle) for s in states]
    # the solution's KS states: position, steering angle, velocity, orientation, time step (CommonRoad's convention)
    from commonroad.scenario.state import KSState
    ks = [KSState(time_step=int(s.time_step), position=s.position, steering_angle=float(s.steering_angle),
                  velocity=float(s.velocity), orientation=float(s.orientation)) for s in shifted]
    traj = Trajectory(initial_time_step=ks[0].time_step, state_list=ks)
    pps = PlanningProblemSolution(planning_problem_id=cfg.planning_problem.planning_problem_id,
                                  vehicle_type=VehicleType(cfg.vehicle.id_type_vehicle), vehicle_model=VehicleModel.KS,
                                  cost_function=CostFunction.JB1, trajectory=traj)
    return Solution(cfg.scenario.scenario_id, [pps])


def check(cfg, solution, row):
    from commonroad_dc.feasibility import solution_checker as sc
    from commonroad_dc.costs.evaluation import CostFunctionEvaluator
    scen, ppset = cfg.scenario, cfg.planning_problem_set
    notes = {}

    def probe(name, fn):
        try:
            return fn()
        except Exception as e:                       # the checker raises on a failed property: the property is False
            notes[name] = "%s: %s" % (type(e).__name__, str(e)[:200])
            return None
    ok = probe("goal", lambda: sc.goal_reached(scen, ppset, solution))
    row["goal"] = bool(ok)
    col = probe("collision", lambda: sc.obstacle_collision(scen, ppset, solution))
    row["collision"] = col is None and "collision" in notes and "Collision" in notes["collision"]
    off = probe("offroad", lambda: sc.boundary_collision(scen, ppset, solution))
    row["offroad"] = off is None and "offroad" in notes and "Collision" in notes["offroad"]
    feas = probe("feasible", lambda: sc.solution_feasible(solution, scen.dt, ppset))
    row["feasible"] = bool(feas) and all(v[0] for v in feas.values())
    if feas is not None and not row["feasible"]:
        row["infeasible_transitions"] = bad_transitions(solution, scen.dt)
    res = probe("cost", lambda: CostFunctionEvaluator.init_from_solution(solution).evaluate_solution(scen, ppset, solution))
    if res is not None:
        row["cost"] = round(float(res.total_costs), 3)
    row["checker"] = notes or None
    for k in ("collision", "offroad"):               # a checker error that is not a collision verdict is a bench error
        if k in notes and "Collision" not in notes[k]:
            row["error"] = True
            row["reason"] = row.get("reason") or {"checker": notes[k]}


def bad_transitions(solution, dt):
    """The transitions the KS input reconstruction rejects (the checker's own tolerances), as [count, of, first steps]."""
    import numpy as np
    from commonroad.common.solution import VehicleModel
    from commonroad_dc.feasibility.feasibility_checker import (VehicleDynamics, state_transition_feasibility,
                                                               position_orientation_objective,
                                                               position_orientation_feasibility_criteria)
    pps = solution.planning_problem_solutions[0]
    vd = VehicleDynamics.from_model(VehicleModel.KS, pps.vehicle_type)
    st = pps.trajectory.state_list
    bad = []
    for x0, x1 in zip(st[:-1], st[1:]):
        try:
            ok, _ = state_transition_feasibility(x0, x1, vd, dt, position_orientation_objective,
                                                 position_orientation_feasibility_criteria, 1e-8,
                                                 np.array([2e-2, 2e-2, 3e-2]), 4, 100, False)
        except Exception:
            ok = False
        if not ok:
            bad.append(int(x0.time_step))
    return [len(bad), len(st) - 1, bad[:8]]


def write_solution(solution, d):
    from commonroad.common.solution import CommonRoadSolutionWriter, CommonRoadSolutionReader
    d.mkdir(parents=True, exist_ok=True)
    name = "solution.xml"
    CommonRoadSolutionWriter(solution).write_to_file(output_path=str(d), filename=name, overwrite=True)
    back = CommonRoadSolutionReader.open(str(d / name))       # read back: the file is a valid solution
    n = len(back.planning_problem_solutions[0].trajectory.state_list)
    return str(d / name), n


def run(sid, planner="reactive", out=OUT):
    row = blank_row(sid, planner)
    t0 = time.perf_counter()
    d = Path(out) / Path(sid).stem
    try:
        from commonroad.common.file_reader import CommonRoadFileReader
        path = find(sid)
        row["file"] = str(path)
        scenario, pps = CommonRoadFileReader(str(path)).open()
        pp = list(pps.planning_problem_dict.values())[0]
        cfg = configure(scenario, pps, pp)
        last = goal_last_step(pp)
        row["goal_window"] = [min(int(s.time_step.start) for s in pp.goal.state_list if getattr(s, "time_step", None)),
                              last] if last is not None else None
        if last is None:
            last = int(pp.initial_state.time_step) + 200
        ref = reference_path(scenario, pp)
        states, vehicle = PLANNERS[planner](cfg, ref, last, row)
        row["steps"] = len(states) - 1
        if len(states) < 2:
            row["reason"] = row["reason"] or {"note": "no step driven"}
            if not row.get("infeasible"):
                row["error"] = True
        else:
            sol = solution_of(cfg, states, vehicle)
            row["solution"], _n = write_solution(sol, d)
            check(cfg, sol, row)
    except Exception as e:
        row["error"] = True
        row["reason"] = {"exception": "%s: %s" % (type(e).__name__, str(e)[:300]),
                         "where": traceback.format_exc().strip().splitlines()[-3][:200]}
    row["seconds"] = round(time.perf_counter() - t0, 1)
    row["outcome"] = classify(row)
    d.mkdir(parents=True, exist_ok=True)
    (d / "row.json").write_text(json.dumps(row, indent=1, default=str))
    return row


# ---------------------------------------------------------------- the batch
def read_list(p):
    ids = []
    for line in Path(p).read_text().splitlines():
        s = line.split("#", 1)[0].strip()
        if s:
            ids.append(s.split()[0])
    return ids


def child(sid, planner, out):
    d = Path(out) / Path(sid).stem
    d.mkdir(parents=True, exist_ok=True)
    (d / "row.json").unlink(missing_ok=True)
    cmd = [sys.executable, str(Path(__file__).resolve()), "run", sid, "--planner", planner, "--out", str(out)]
    if os.environ.get("PLANNER_NO_SCOPE") != "1":
        cmd = ["systemd-run", "--user", "--scope", "--quiet", "-p", "MemoryMax=6G", "nice", "-n", "10"] + cmd
    t0 = time.perf_counter()
    with open(d / "run.log", "w") as log:
        try:
            p = subprocess.run(cmd, stdout=log, stderr=subprocess.STDOUT, timeout=TIMEOUT)
            rc = p.returncode
        except subprocess.TimeoutExpired:
            rc = "timeout"
    f = d / "row.json"
    if f.is_file():
        return json.loads(f.read_text())
    row = blank_row(sid, planner)
    row["reason"] = {"child": "timeout after %ds" % TIMEOUT if rc == "timeout" else "exit %s, no row (see run.log)" % rc}
    row["seconds"] = round(time.perf_counter() - t0, 1)
    f.write_text(json.dumps(row, indent=1))
    return row


def fmt(v, nd=None):
    if v is None:
        return "—"
    if isinstance(v, bool):
        return "yes" if v else "no"
    return str(v)


def short_reason(r):
    if not r["reason"]:
        return ""
    x = r["reason"]
    if "exception" in x and "by_constraint" not in x:
        return x["exception"][:120]
    if "child" in x:
        return x["child"]
    if "checker" in x:
        return "checker: " + x["checker"][:100]
    if "by_constraint" in x:
        bad = ", ".join("%s %d" % kv for kv in sorted(x["by_constraint"].items(), key=lambda kv: -kv[1]) if kv[1])
        why = "no feasible sample at step %d (cycle %d): %d of %d kinematic [%s], %d collision" % (
            x["time_step"], x["cycle"], x["kinematics"], x["samples"], bad, x["collision"])
        return why + ("; raised " + x["exception"][:80] if x.get("exception") else "")
    return json.dumps(x)[:120]


def table(rows, title):
    from collections import Counter
    c = Counter(r["outcome"] for r in rows)
    lines = ["# %s" % title, "",
             "%d scenarios: %s." % (len(rows), ", ".join("%s %d" % (o, c[o]) for o in OUTCOMES if c[o])), "",
             "| id | outcome | goal | collision | offroad | feasible | cost (JB1) | ms/cycle | cycles | steps | window | reason |",
             "|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for r in rows:
        w = r.get("goal_window")
        lines.append("| %s | %s | %s | %s | %s | %s | %s | %s | %s | %s | %s | %s |" % (
            r["id"], r["outcome"], fmt(r["goal"]), fmt(r["collision"]), fmt(r["offroad"]), (fmt(r["feasible"]) + (" (%d/%d bad)" % tuple(r["infeasible_transitions"][:2]) if r.get("infeasible_transitions") else "")),
            fmt(r["cost"]), fmt(r["ms_cycle"]), r["cycles"], r["steps"], "%s–%s" % tuple(w) if w else "—",
            short_reason(r).replace("|", "/")))
    return "\n".join(lines) + "\n"


def worlds_sha():
    try:
        return subprocess.run(["git", "-C", str(REPO), "rev-parse", "--short", "HEAD"], capture_output=True,
                              text=True).stdout.strip() or "nopin"
    except OSError:
        return "nopin"


def batch(lst, jobs=MAX_JOBS, planner="reactive", out=OUT, table_file=None):
    ids = read_list(lst)
    jobs = max(1, min(int(jobs), MAX_JOBS))
    with ThreadPoolExecutor(max_workers=jobs) as ex:
        rows = list(ex.map(lambda s: child(s, planner, out), ids))
    sha = worlds_sha()
    tf = Path(table_file) if table_file else HERE / "tables" / ("baseline-%s.md" % sha)
    tf.parent.mkdir(parents=True, exist_ok=True)
    tf.write_text(table(rows, "%s planner baseline over %s at metis-worlds %s" % (planner, Path(lst).name, sha)))
    (Path(out) / ("rows-%s.json" % sha)).write_text(json.dumps(rows, indent=1, default=str))
    return rows, tf


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run")
    r.add_argument("id")
    r.add_argument("--planner", default="reactive", choices=sorted(PLANNERS))
    r.add_argument("--out", default=str(OUT))
    b = sub.add_parser("batch")
    b.add_argument("list")
    b.add_argument("--jobs", type=int, default=MAX_JOBS)
    b.add_argument("--planner", default="reactive", choices=sorted(PLANNERS))
    b.add_argument("--out", default=str(OUT))
    b.add_argument("--table")
    a = ap.parse_args(argv)
    if a.cmd == "run":
        row = run(a.id, a.planner, a.out)
        print(json.dumps({k: row[k] for k in ("id", "outcome", "goal", "collision", "offroad", "feasible", "cost",
                                              "ms_cycle", "cycles", "steps", "goal_window", "reason", "seconds")},
                         default=str))
        return 0
    rows, tf = batch(a.list, a.jobs, a.planner, a.out, a.table)
    print("%d rows → %s" % (len(rows), tf))
    return 0


if __name__ == "__main__":
    sys.exit(main())
