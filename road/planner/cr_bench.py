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
            "goal_window": None, "goal_kind": None, "traffic": None, "reason": None, "file": None, "solution": None, "seconds": None}


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


def drive_reactive(cfg, ref_fn, last_step, row, d):
    """run_planner's loop (the package's example): plan every replanning_frequency steps, follow the plan between."""
    from commonroad_rp.reactive_planner import ReactivePlanner
    from commonroad_rp.utility.utils_coordinate_system import create_coordinate_system
    ref_path = ref_fn()
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


def drive_stub(cfg, ref_fn, last_step, row, d):
    """No planner: the initial speed kept along the reference path (tests; checks the bench, not a planner)."""
    import numpy as np
    from commonroad_rp.reactive_planner import ReactivePlannerState
    pp = cfg.planning_problem
    x0 = ReactivePlannerState.create_from_initial_state(pp.initial_state, cfg.vehicle.wheelbase, cfg.vehicle.wb_rear_axle)
    path = np.asarray(ref_fn())
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


SB_PY = Path(os.environ.get("SB2023_PY", str(ROAD / ".venv-sb2023" / "bin" / "python")))
SB_VEHICLE_TYPE = 1    # CommonRoad's FORD_ESCORT (4.298 x 1.674 m, wheelbase 2.391): the nearest to SB's 4.3 x 1.7, 2.3


class _CentredVehicle:
    """SB's states are at the centre already: no shift; the solution's vehicle type is SB_VEHICLE_TYPE."""
    wb_rear_axle = 0.0
    id_type_vehicle = SB_VEHICLE_TYPE


def drive_sb2023(cfg, ref_fn, last_step, row, d, collision_avoidance=False, vlim=False):
    """The original SB-2023 planner in its own venv (road/planner/sb_bench.py, Python 3.8): one shot over the goal window;
    its decision record (d/record.json) becomes the states; its failure a row with the reason. No reference of ours."""
    import numpy as np
    from commonroad_rp.reactive_planner import ReactivePlannerState
    d.mkdir(parents=True, exist_ok=True)
    (d / "record.json").unlink(missing_ok=True)
    cmd = [str(SB_PY), str(HERE / "sb_bench.py"), row["file"], str(d)] + \
        (["--collision-avoidance"] if collision_avoidance else []) + (["--vlim"] if vlim else [])
    with open(d / "sb.log", "w") as log:
        try:
            subprocess.run(cmd, stdout=log, stderr=subprocess.STDOUT, timeout=max(60.0, TIMEOUT - 30))
        except subprocess.TimeoutExpired:
            row["error"] = True
            row["reason"] = {"child": "sb_bench timeout after %ds" % max(60, TIMEOUT - 30)}
            return [], _CentredVehicle()
    f = d / "record.json"
    if not f.is_file():
        row["error"] = True
        row["reason"] = {"child": "sb_bench wrote no record (see sb.log)"}
        return [], _CentredVehicle()
    rec = json.loads(f.read_text())
    t = rec.get("times") or {}
    row["ms_decision"] = round(1000 * t["decision_s"], 1) if "decision_s" in t else None
    row["ms_low_level"] = round(1000 * t["low_level_s"], 1) if "low_level_s" in t else None
    row["ms_cycle"] = round((row["ms_decision"] or 0) + (row["ms_low_level"] or 0), 1)
    row["cycles"] = len(rec.get("solves") or []) or 1
    sol = (rec.get("solves") or [{}])[-1]
    row["solver"] = {"status": sol.get("status"), "iterations": sol.get("iterations")} if sol else None
    row["record"] = str(f)
    fail = rec.get("failure")
    if fail:
        last = (fail.get("where") or ["?"])[-1].split(":")[0]
        if fail.get("kind") == "exception" and last == "sb_bench.py":
            row["error"] = True                          # the wrapper's own fault, not SB's
        else:
            row["infeasible"] = True
        row["reason"] = {"sb": fail}
        return [], _CentredVehicle()
    states = []
    for p in rec["trajectory"]:
        st = ReactivePlannerState(time_step=int(p["k"]), position=np.array([p["x"], p["y"]]), velocity=p["v"],
                                  orientation=p["phi"], steering_angle=p["delta"], acceleration=p["a"], yaw_rate=0.0)
        states.append(st)
    return states, _CentredVehicle()


def drive_sb2023_ca(cfg, ref_fn, last_step, row, d):
    return drive_sb2023(cfg, ref_fn, last_step, row, d, collision_avoidance=True)


def drive_sb2023_vlim(cfg, ref_fn, last_step, row, d):
    return drive_sb2023(cfg, ref_fn, last_step, row, d, vlim=True)


AGENT_PY = Path(os.environ.get("METIS_AGENT_PY", str(WS / "metis-agent" / "py" / ".venv" / "bin" / "python")))
CONVERT_PY = Path(os.environ.get("COMMONROAD_CONVERT_PY", str(ROAD / ".venv-cr" / "bin" / "python")))
CR_CACHE = Path(os.environ.get("COMMONROAD_CACHE", str(WS / ".worlds" / "cr-cache")))
SUMO_BIN = Path(os.environ.get("SUMO_VENV", str(WS / ".worlds" / "road"))) / "bin"


class _ReactiveVehicle(_CentredVehicle):
    """The composition's executed states are at the centre already; its vehicle is the reactive planner's (id 2)."""
    id_type_vehicle = 2


def cache_for(xml):
    """The conversion cache of XML: the shared cache for a file of the pinned checkout (its id is unique there), else
    its own under cr-cache-ext/<the file's directory, hashed> (sb100's 2018b files share ids with the 2020a checkout)."""
    import hashlib
    xml = Path(xml).resolve()
    if str(xml).startswith(str((CR_ROOT / "scenarios").resolve())) or str(xml).startswith(str((CR_ROOT / "interactive").resolve())):
        return CR_CACHE
    return CR_CACHE.parent / "cr-cache-ext" / hashlib.sha256(str(xml.parent).encode()).hexdigest()[:12]


def drive_composition(cfg, ref_fn, last_step, row, d):
    """The family's command per beat as the reactive planner's setpoints (deliverable 3): road_tree.py --world crnative
    (the Live: perceive, belief, facts, fold, restrictor; road/world/cr_native.py), its record.json → the states."""
    import numpy as np
    from commonroad_rp.reactive_planner import ReactivePlannerState
    xml = Path(row["file"])
    sid = xml.name[:-len(".cr.xml")] if xml.name.endswith(".cr.xml") else xml.stem
    cache = cache_for(xml)
    d.mkdir(parents=True, exist_ok=True)
    env = dict(os.environ, COMMONROAD_CACHE=str(cache), PLANNER_PY=sys.executable, CR_NATIVE_RECORD=str(d / "record.json"),
               PYTHONPATH=str(REPO / "libs" / "semantic-world"), PATH=str(SUMO_BIN) + os.pathsep + os.environ.get("PATH", ""))
    if not env.get("METIS_HOME"):
        row["error"] = True
        row["reason"] = {"child": "METIS_HOME unset: the family's catalog pin (a detached worktree at road/domains/catalog.pin)"}
        return [], _ReactiveVehicle()
    (d / "record.json").unlink(missing_ok=True)
    with open(d / "live.log", "w") as log:
        if not (cache / sid / "cr.json").is_file():
            subprocess.run([str(CONVERT_PY), str(ROAD / "tools" / "cr_convert.py"), str(xml), "--cache", str(cache)],
                           stdout=log, stderr=subprocess.STDOUT, env=env, timeout=600)
        k0 = int(cfg.planning_problem.initial_state.time_step)
        cmd = [str(AGENT_PY), str(ROAD / "experiments" / "road_tree.py"), "cr:" + sid, "1", "--world", "crnative",
               "--ticks", str(int(last_step) - k0 + 10), "--out", str(d / "live")]
        try:
            p = subprocess.run(cmd, cwd=str(AGENT_PY.parents[2]), stdout=subprocess.PIPE, stderr=log, text=True, env=env,
                               timeout=max(60.0, TIMEOUT - 30))
        except subprocess.TimeoutExpired:
            row["error"] = True
            row["reason"] = {"child": "road_tree timeout after %ds" % max(60, TIMEOUT - 30)}
            return [], _ReactiveVehicle()
        log.write(p.stdout or "")
    summ = next((json.loads(l) for l in reversed((p.stdout or "").splitlines()) if l.startswith("{")), None)
    f = d / "record.json"
    if not f.is_file() or summ is None:
        row["error"] = True
        row["reason"] = {"child": "road_tree exit %s, no %s (see live.log)" % (p.returncode, "record" if not f.is_file() else "summary")}
        return [], _ReactiveVehicle()
    rec = json.loads(f.read_text())
    ms = [s["ms"] for s in rec.get("solves") or [] if s.get("ms") is not None]
    row["ms_cycle"] = round(sum(ms) / len(ms), 1) if ms else None
    row["cycles"] = len(rec.get("solves") or [])
    row["plan_failures"] = sum(1 for s in rec.get("solves") or [] if not s.get("success"))
    row["record"] = str(f)
    row["family"] = {"responder": summ.get("responder_kinds"), "planner": summ.get("planner_kinds"),
                     "planner_cmds": summ.get("planner_cmds"), "responder_cmds": summ.get("responder_cmds"),
                     "restricted": summ.get("restricted"), "lane_changes": len(rec.get("lane_changes") or [])}
    states = [ReactivePlannerState(time_step=int(p_["k"]), position=np.array([p_["x"], p_["y"]]), velocity=p_["v"],
                                   orientation=p_["phi"], steering_angle=p_.get("delta") or 0.0,
                                   acceleration=p_.get("a") or 0.0, yaw_rate=0.0) for p_ in rec.get("trajectory") or []]
    return states, _ReactiveVehicle()


def drive_ours_parity(cfg, ref_fn, last_step, row, d):
    """M2's PARITY PROOF: SB's own reference (its record's steps: x_ref, y_ref, v_ref, phi_ref, from the sb2023 column of
    the same set) into OUR OCP (ocp.py, every addition off), from the planning problem's initial state; SB's vehicle.
    The row beside SB's tells whether our trajectory planner is SB's: the same outcome, the trajectory within tolerance."""
    import numpy as np
    from commonroad_rp.reactive_planner import ReactivePlannerState
    sys.path.insert(0, str(HERE))
    import ocp
    sb_dir = Path(os.environ.get("PARITY_SB_DIR", str(d.parent.parent.parent / "sb2023" / d.parent.name)))
    f = sb_dir / d.name / "record.json"
    if not f.is_file():
        row["error"] = True
        row["reason"] = {"child": "parity: no SB record at %s (run --planner sb2023 on this set first)" % f}
        return [], _CentredVehicle()
    rec = json.loads(f.read_text())
    steps = rec.get("steps") or []
    if not steps:
        row["infeasible"] = True
        row["reason"] = {"sb": dict(rec.get("failure") or {}, parity="SB gave no reference")}
        return [], _CentredVehicle()
    ref = np.array([[s["x_ref"] for s in steps], [s["y_ref"] for s in steps], [s["v_ref"] for s in steps],
                    [s["phi_ref"] for s in steps]])
    x0 = cfg.planning_problem.initial_state
    res = ocp.solve(ref, [float(x0.position[0]), float(x0.position[1]), float(x0.velocity), float(x0.orientation)],
                    dt=cfg.scenario.dt)
    row["ms_cycle"], row["cycles"] = round(1000 * res.seconds, 1), 1
    sb_solve = (rec.get("solves") or [{}])[-1]
    row["solver"] = {"status": res.status, "iterations": res.iterations,
                     "sb_status": sb_solve.get("status"), "sb_iterations": sb_solve.get("iterations")}
    if not res.ok:
        row["infeasible"] = True
        row["reason"] = {"sb": {"stage": "low_level", "kind": "solver", "status": res.status}}
        return [], _CentredVehicle()
    k0 = int(steps[0]["k"])
    tr = rec.get("trajectory") or []
    if tr:
        dev = [math.hypot(res.x[0, i] - p["x"], res.x[1, i] - p["y"]) for i, p in enumerate(tr[:res.x.shape[1]])]
        row["parity"] = {"max_dxy_m": round(max(dev), 4), "mean_dxy_m": round(sum(dev) / len(dev), 4)}
    states = []
    for i in range(res.x.shape[1]):
        j = min(i, res.u.shape[1] - 1)
        states.append(ReactivePlannerState(time_step=k0 + i, position=np.array([res.x[0, i], res.x[1, i]]),
                                           velocity=float(res.x[2, i]), orientation=float(res.x[3, i]),
                                           steering_angle=float(res.u[1, j]), acceleration=float(res.u[0, j]),
                                           yaw_rate=0.0))
    return states, _CentredVehicle()


def drive_ours(cfg, ref_fn, last_step, row, d):
    """M3, OUR planner: the road family's command per beat over the LaneMap from the scenario's LANELETS (cr_lanelets →
    cr_lanes: no SUMO conversion), the reference (reference.py) into OUR OCP (ocp.py, SB's), through road_tree.py --world
    crnative (the Live: perception, belief, facts, fold, restrictor); SB's vehicle; the record → the states."""
    import numpy as np
    from commonroad_rp.reactive_planner import ReactivePlannerState
    sys.path.insert(0, str(HERE))
    import cr_lanelets
    xml = Path(row["file"])
    sid = xml.name[:-len(".cr.xml")] if xml.name.endswith(".cr.xml") else xml.stem
    d.mkdir(parents=True, exist_ok=True)
    lanes = cr_lanelets.export(xml, d / "lanes.json")
    env = dict(os.environ, CR_LANES_JSON=str(lanes), PLANNER_PY=sys.executable, CR_NATIVE_RECORD=str(d / "record.json"),
               PYTHONPATH=str(REPO / "libs" / "semantic-world"))
    if not env.get("METIS_HOME"):
        row["error"] = True
        row["reason"] = {"child": "METIS_HOME unset: the family's catalog pin (a detached worktree at road/domains/catalog.pin)"}
        return [], _CentredVehicle()
    (d / "record.json").unlink(missing_ok=True)
    k0 = int(cfg.planning_problem.initial_state.time_step)
    cmd = [str(AGENT_PY), str(ROAD / "experiments" / "road_tree.py"), "cr:" + sid, "1", "--world", "crnative",
           "--ticks", str(int(last_step) - k0 + 10), "--out", str(d / "live")]
    with open(d / "live.log", "w") as log:
        try:
            p = subprocess.run(cmd, cwd=str(AGENT_PY.parents[2]), stdout=subprocess.PIPE, stderr=log, text=True, env=env,
                               timeout=max(60.0, TIMEOUT - 30))
        except subprocess.TimeoutExpired:
            row["error"] = True
            row["reason"] = {"child": "road_tree timeout after %ds" % max(60, TIMEOUT - 30)}
            return [], _CentredVehicle()
        log.write(p.stdout or "")
    summ = next((json.loads(l) for l in reversed((p.stdout or "").splitlines()) if l.startswith("{")), None)
    f = d / "record.json"
    if not f.is_file() or summ is None:
        row["error"] = True
        row["reason"] = {"child": "road_tree exit %s, no %s (see live.log)" % (p.returncode, "record" if not f.is_file() else "summary")}
        return [], _CentredVehicle()
    rec = json.loads(f.read_text())
    ms = [s_["ms"] for s_ in rec.get("solves") or [] if s_.get("ms") is not None]
    row["ms_cycle"] = round(sum(ms) / len(ms), 1) if ms else None
    row["cycles"] = len(rec.get("solves") or [])
    row["plan_failures"] = sum(1 for s_ in rec.get("solves") or [] if not s_.get("success"))
    row["record"] = str(f)
    row["family"] = {"responder": summ.get("responder_kinds"), "planner": summ.get("planner_kinds"),
                     "restricted": summ.get("restricted"), "lane_changes": len(rec.get("lane_changes") or [])}
    states = [ReactivePlannerState(time_step=int(q["k"]), position=np.array([q["x"], q["y"]]), velocity=q["v"],
                                   orientation=q["phi"], steering_angle=q.get("delta") or 0.0,
                                   acceleration=q.get("a") or 0.0, yaw_rate=0.0) for q in rec.get("trajectory") or []]
    return states, _CentredVehicle()


PLANNERS = {"ours": drive_ours, "ours-parity": drive_ours_parity, "reactive": drive_reactive, "stub": drive_stub, "sb2023": drive_sb2023, "sb2023-ca": drive_sb2023_ca,
            "sb2023-vlim": drive_sb2023_vlim, "composition": drive_composition}


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
                                  vehicle_type=VehicleType(getattr(vehicle, "id_type_vehicle", cfg.vehicle.id_type_vehicle)),
                                  vehicle_model=VehicleModel.KS,
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
        row["goal_kind"] = "region" if any(getattr(g, "position", None) is not None for g in pp.goal.state_list) \
            else "time-only"
        row["traffic"] = "recorded" if scenario.dynamic_obstacles else "none"
        if last is None:
            last = int(pp.initial_state.time_step) + 200
        states, vehicle = PLANNERS[planner](cfg, lambda: reference_path(scenario, pp), last, row, d)
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
    if "_S-" in Path(sid).stem and rc != "timeout":
        row["reason"]["world"] = SET_BASED
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
    if "world" in x:
        return "world: " + x["world"]
    if "child" in x:
        return x["child"]
    if "checker" in x:
        return "checker: " + x["checker"][:100]
    if "sb" in x:
        f = x["sb"]
        if f.get("kind") == "solver":
            return "SB %s: IPOPT %s" % (f.get("stage"), f.get("status"))
        return "SB %s raised %s (%s)" % (f.get("stage"), (f.get("exception") or "")[:90], (f.get("where") or ["?"])[-1])
    if "by_constraint" in x:
        bad = ", ".join("%s %d" % kv for kv in sorted(x["by_constraint"].items(), key=lambda kv: -kv[1]) if kv[1])
        why = "no feasible sample at step %d (cycle %d): %d of %d kinematic [%s], %d collision" % (
            x["time_step"], x["cycle"], x["kinematics"], x["samples"], bad, x["collision"])
        return why + ("; raised " + x["exception"][:80] if x.get("exception") else "")
    return json.dumps(x)[:120]


HOW = {
    "reactive": "The reference path: the package's create_initial_ref_path (route planner's shortest route), extended %g m back "
                "and %g m past its end, smoothed by create_coordinate_system; the feasibility count depends on it (the 20 m "
                "back extension moved DEU_BadEssen-1_3_T-1 from 17 to 1 bad transitions)." % (BACK_M, EXTEND_M),
    "composition": "The road family's command per beat (road_tree --world crnative: the Live, the belief, the fold, the restrictor; "
                   "no SUMO process) as the reactive planner's setpoints (iface.setpoints_of: the target speed is the lane's limit, "
                   "brake lowers it by the restricted deceleration over 1 s, yield stops at the zone line, change sends the sibling's "
                   "centreline); the restrictor's cap clips the executed speed after the planner; replanned every 3 steps or at a new setpoint.",
    "sb2023": "SB-2023 @ 5434d05 as its main.py calls it: its own decision module (desired_velocity='init'), the "
              "Optimization planner at its defaults, ONE SHOT over the goal window, collision_avoidance off; ms/cycle = "
              "decision + low level; the solution's vehicle FORD_ESCORT (the nearest CommonRoad type to SB's 4.3 x 1.7 m, "
              "wheelbase 2.3). KS feasibility as measured; footnote: no steering-rate bound, zero input weights.",
}
HOW["ours"] = ("OUR planner: the road family's command per beat (road_tree --world crnative over the LaneMap from the "
               "scenario's lanelets, no SUMO) → the reference (reference.py: the lane the command names, the target speed, "
               "stops, the window-fitted arrival) → OUR OCP (ocp.py = SB's, parity proven), re-solved over the remaining "
               "window at a new command or every 1 s; the restrictor's cap clips the executed speed; SB's vehicle.")
HOW["ours-parity"] = ("OUR OCP (ocp.py: SB's low-level optimisation from its equations, every addition off) on SB's OWN "
                      "reference (the sb2023 column's record), one shot, SB's vehicle: the parity proof of M2.")
HOW["sb2023-ca"] = HOW["sb2023"].replace("collision_avoidance off", "collision_avoidance ON (the one flag)")
HOW["sb2023-vlim"] = HOW["sb2023"].replace("as its main.py calls it", "with the decision module's own default").replace(
    "desired_velocity='init'", "desired_velocity='speed_limit', the family's target")
SET_BASED = "set-based predictions: oracle crash"   # the architect's ruling (c): _S- scenarios stay as error:world


def table(rows, title, planner="reactive"):
    from collections import Counter
    c = Counter(r["outcome"] for r in rows)
    lines = ["# %s" % title, "",
             "%d scenarios: %s." % (len(rows), ", ".join("%s %d" % (o, c[o]) for o in OUTCOMES if c[o])),
             "Goal kinds: %s; traffic: %s. The planner is deterministic: one run per row. %s" % (
                 ", ".join("%s %d" % kv for kv in sorted(Counter(r.get("goal_kind") or "—" for r in rows).items())),
                 ", ".join("%s %d" % kv for kv in sorted(Counter(r.get("traffic") or "—" for r in rows).items())),
                 HOW.get(planner, "")), "",
             "| id | outcome | goal kind | traffic | goal | collision | offroad | feasible (bad transitions) | cost (JB1) "
             "| ms/cycle | cycles | steps | window | reason |",
             "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for r in rows:
        w = r.get("goal_window")
        if r["outcome"] == "error" and (r.get("reason") or {}).get("world"):
            r = dict(r, outcome="error:world")
        lines.append("| %s | %s | %s | %s | %s | %s | %s | %s | %s | %s | %s | %s | %s | %s |" % (
            Path(r["id"]).stem if r["id"].endswith(".xml") else r["id"], r["outcome"], fmt(r.get("goal_kind")), fmt(r.get("traffic")), fmt(r["goal"]), fmt(r["collision"]), fmt(r["offroad"]), (fmt(r["feasible"]) + (" (%d/%d bad)" % tuple(r["infeasible_transitions"][:2]) if r.get("infeasible_transitions") else "")),
            fmt(r["cost"]), fmt(r["ms_cycle"]), r["cycles"], r["steps"], "%s–%s" % tuple(w) if w else "—",
            short_reason(r).replace("|", "/")))
    return "\n".join(lines) + "\n"


def worlds_sha():
    try:
        return subprocess.run(["git", "-C", str(REPO), "rev-parse", "--short", "HEAD"], capture_output=True,
                              text=True).stdout.strip() or "nopin"
    except OSError:
        return "nopin"


def table_name(planner, lst, sha):
    """tables/<baseline|planner>-<set>-<sha>.md: the reactive planner's table is the baseline."""
    return "%s-%s-%s.md" % ("baseline" if planner == "reactive" else planner, Path(lst).stem, sha)


def batch(lst, jobs=MAX_JOBS, planner="reactive", out=OUT, table_file=None):
    ids = read_list(lst)
    out = Path(out) / planner / Path(lst).stem          # per planner and set: sb100 shares ids with the 2020a checkout
    out.mkdir(parents=True, exist_ok=True)
    jobs = max(1, min(int(jobs), MAX_JOBS))
    with ThreadPoolExecutor(max_workers=jobs) as ex:
        rows = list(ex.map(lambda s: child(s, planner, out), ids))
    sha = worlds_sha()
    tf = Path(table_file) if table_file else HERE / "tables" / table_name(planner, lst, sha)
    tf.parent.mkdir(parents=True, exist_ok=True)
    tf.write_text(table(rows, "%s over %s at metis-worlds %s" % (planner, Path(lst).name, sha), planner))
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
    t = sub.add_parser("table")
    t.add_argument("rows")
    t.add_argument("list")
    t.add_argument("--planner", default="reactive", choices=sorted(PLANNERS))
    t.add_argument("--sha", required=True)
    a = ap.parse_args(argv)
    if a.cmd == "table":
        rows = json.loads(Path(a.rows).read_text())
        tf = HERE / "tables" / table_name(a.planner, a.list, a.sha)
        tf.write_text(table(rows, "%s over %s at metis-worlds %s" % (a.planner, Path(a.list).name, a.sha), a.planner))
        print(tf)
        return 0
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
