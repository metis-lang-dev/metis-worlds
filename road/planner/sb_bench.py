#!/usr/bin/env python3
"""sb_bench.py — the ORIGINAL SB-2023 planner as a bench column (planner-loop s-0dcc5ed1 step 2b; PLANNER.md §6.2).

    road/.venv-sb2023/bin/python road/planner/sb_bench.py SCENARIO_XML OUT_DIR [--collision-avoidance] [--vlim]

Kochdumper's MotionPlanner @ 5434d05 (github.com/KochdumperNiklas/MotionPlanner; NO LICENSE, all rights reserved: run and
read on the bench, never copied, never a dependency; road/docs/planner-licenses.md). The clone lives OUTSIDE the tree
($SB2023_ROOT, default /bigdata/datasets/commonroad/sb2023-motionplanner); this wrapper imports its modules from there.
main.py is not used: its `bool(sys.argv[2])` never selects the optimiser. The run is the README's: the scenario read with
lanelet_assignment=True, its decision module as main.py calls it (`highLevelPlanner(scenario, planning_problem, param,
desired_velocity='init')`, every other argument at its default), then `lowLevelPlannerOptimization` at its defaults (one
shot over the goal window, collision_avoidance off, IPOPT's defaults); --collision-avoidance flips that one flag; --vlim
passes desired_velocity='speed_limit' (the function's own default; the family's target) instead of main.py's 'init'.
The repository's code is never edited. The wrapper does two things to it: it puts the clone first on sys.path, and it
replaces the optimiser module's `casadi.Opti` with a subclass that records the solver's stats (status, iterations, wall
time) and otherwise behaves the same. IPOPT's console output goes to OUT_DIR/ipopt.log.

Writes OUT_DIR/record.json, THE DECISION RECORD (version 1), the comparison's data (PLANNER.md §6.2). The family's
composition writes the same shape, with `command` filled per beat:
  record, planner, settings, scenario, dt, horizon {mode: one-shot|receding, steps, seconds}
  steps        per time step k: lanelet (the plan's), the reference x_ref, y_ref, v_ref, phi_ref; command (null for SB)
  lane_changes [{k, from, to, side: left|right|other}]: a plan step onto a lanelet that is not the current one's successor
  stops        [{from_k, to_k, x, y}]: the runs of steps with v_ref <= 0.1 m/s
  solves       [{k, stage, status, success, iterations, t_wall_s}]: one per solve (one-shot: one)
  times        {decision_s, low_level_s}
  trajectory   [{k, x, y, v, phi, delta, a}]: the planned states at the vehicle's CENTRE (CommonRoad's convention; SB
               plans at the rear axle and returns the centre), delta the steering angle, a the acceleration input
  vehicle      SB's parameters (length, width, wheelbase, b, a_max, s_max)
  failure      null | {stage: decision|low_level, kind: solver|exception, status?, exception?}
cr_bench.py (the planner venv) turns the trajectory into solution.xml and the oracle's row.json, as for the baseline.
Python 3.8 (the repository's README): no newer syntax here.
"""
import json
import os
import sys
import time
import traceback
import warnings
from pathlib import Path

SB_ROOT = Path(os.environ.get("SB2023_ROOT", "/bigdata/datasets/commonroad/sb2023-motionplanner"))
SB_PIN = "5434d0559b85d3d84733d46ee1596cd5338fe549"
RECORD_VERSION = 1


class _FdToFile(object):
    """IPOPT writes to the C stdout: redirect fd 1 to a log for the duration (Python's sys.stdout stays where it is)."""

    def __init__(self, path):
        self.path = path

    def __enter__(self):
        sys.stdout.flush()
        self.saved = os.dup(1)
        self.f = open(self.path, "a")
        os.dup2(self.f.fileno(), 1)
        return self

    def __exit__(self, *exc):
        sys.stdout.flush()
        os.dup2(self.saved, 1)
        os.close(self.saved)
        self.f.close()
        return False


def recording_opti(casadi_mod, solves, stage):
    base = casadi_mod.Opti

    class RecordingOpti(base):
        def solve(self):
            t0 = time.perf_counter()
            try:
                sol = base.solve(self)
            finally:
                st = {}
                try:
                    st = dict(self.stats())
                except Exception:
                    pass
                solves.append({"stage": stage, "status": st.get("return_status"), "success": bool(st.get("success")),
                               "iterations": st.get("iter_count"), "t_wall_s": round(time.perf_counter() - t0, 3)})
            return sol
    return RecordingOpti


def lane_changes(plan, net):
    out = []
    for k in range(1, len(plan)):
        a, b = int(plan[k - 1]), int(plan[k])
        if a == b:
            continue
        la = net.find_lanelet_by_id(a)
        if la is not None and b in (la.successor or []):
            continue
        side = "left" if la is not None and la.adj_left == b else "right" if la is not None and la.adj_right == b \
            else "other"
        out.append({"k": k, "from": a, "to": b, "side": side})
    return out


def stops(v_ref, xs, ys, k0):
    out, start = [], None
    for i, v in enumerate(list(v_ref) + [1e9]):
        if v <= 0.1 and start is None:
            start = i
        elif v > 0.1 and start is not None:
            out.append({"from_k": k0 + start, "to_k": k0 + i - 1, "x": float(xs[start]), "y": float(ys[start])})
            start = None
    return out


def run(xml, out, collision_avoidance=False, vlim=False):
    import numpy as np
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    warnings.filterwarnings("ignore")
    sys.path.insert(0, str(SB_ROOT))
    from commonroad.common.file_reader import CommonRoadFileReader
    from vehicle.vehicleParameter import vehicleParameter
    from src.highLevelPlanner import highLevelPlanner
    import src.lowLevelPlannerOptimization as LLO

    desired = "speed_limit" if vlim else "init"
    rec = {"record": RECORD_VERSION, "planner": "sb2023" + ("-ca" if collision_avoidance else "") + ("-vlim" if vlim else ""),
           "settings": {"source": "github.com/KochdumperNiklas/MotionPlanner@" + SB_PIN,
                        "decision": "highLevelPlanner(..., desired_velocity=%r), the rest at its defaults" % desired,
                        "low_level": "lowLevelPlannerOptimization defaults; collision_avoidance=%s" % collision_avoidance},
           "scenario": str(xml), "dt": None, "horizon": None, "steps": [], "lane_changes": [], "stops": [],
           "solves": [], "times": {}, "trajectory": [], "vehicle": None, "failure": None}
    log = out / "ipopt.log"
    log.write_text("")
    param = vehicleParameter()
    rec["vehicle"] = {k: param[k] for k in ("length", "width", "wheelbase", "b", "a_max", "s_max")}
    scenario, pp = CommonRoadFileReader(str(xml)).open(lanelet_assignment=True)
    rec["dt"] = scenario.dt
    planning_problem = list(pp.planning_problem_dict.values())[0]
    k0 = int(planning_problem.initial_state.time_step)
    LLO.casadi.Opti = recording_opti(LLO.casadi, rec["solves"], "low_level")
    stage = "decision"
    t0 = time.perf_counter()
    try:
        with _FdToFile(str(log)):
            # main.py passes the planning problem SET (CommonRoadFileReader's second value) to both stages
            plan, space, ref = highLevelPlanner(scenario, pp, param, desired_velocity=desired)
        t1 = time.perf_counter()
        rec["times"]["decision_s"] = round(t1 - t0, 3)
        ref = np.asarray(ref)
        n = ref.shape[1]
        rec["horizon"] = {"mode": "one-shot", "steps": n - 1, "seconds": round((n - 1) * scenario.dt, 3)}
        rec["steps"] = [{"k": k0 + i, "lanelet": int(plan[i]) if i < len(plan) else None,
                         "x_ref": float(ref[0, i]), "y_ref": float(ref[1, i]), "v_ref": float(ref[2, i]),
                         "phi_ref": float(ref[3, i]), "command": None} for i in range(n)]
        rec["lane_changes"] = [dict(c, k=k0 + c["k"]) for c in lane_changes(list(plan), scenario.lanelet_network)]
        rec["stops"] = stops(ref[2], ref[0], ref[1], k0)
        stage = "low_level"
        with _FdToFile(str(log)):
            x, u, _controller = LLO.lowLevelPlannerOptimization(scenario, pp, param, space, ref,
                                                                 collision_avoidance=collision_avoidance)
        rec["times"]["low_level_s"] = round(time.perf_counter() - t1, 3)
        if x is None:
            rec["failure"] = {"stage": stage, "kind": "solver", "status": "no trajectory returned"}
        else:
            # lowLevelPlannerOptimization's x is at the CENTRE already (its simulate_trajectory moves it back from the
            # rear axle); before 2026-11-07 this wrapper shifted it by b again (every SB row 1.15 m ahead)
            for i in range(x.shape[1]):
                j = min(i, u.shape[1] - 1)
                rec["trajectory"].append({"k": k0 + i, "x": float(x[0, i]),
                                          "y": float(x[1, i]), "v": float(x[2, i]),
                                          "phi": float(x[3, i]), "delta": float(u[1, j]), "a": float(u[0, j])})
    except Exception as e:
        rec["times"].setdefault(stage + "_s", round(time.perf_counter() - t0, 3))
        last = rec["solves"][-1] if rec["solves"] else None
        if stage == "low_level" and last is not None and not last["success"]:
            rec["failure"] = {"stage": stage, "kind": "solver", "status": last["status"]}
        else:
            tb = traceback.extract_tb(sys.exc_info()[2])
            where = ["%s:%d %s" % (Path(f.filename).name, f.lineno, f.name) for f in tb[-3:]]
            rec["failure"] = {"stage": stage, "kind": "exception", "exception": "%s: %s" % (type(e).__name__,
                                                                                          str(e)[:300]),
                              "where": where}
    (out / "record.json").write_text(json.dumps(rec, indent=1))
    return rec


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    ca = "--collision-avoidance" in argv
    args = [a for a in argv if not a.startswith("--")]
    if len(args) != 2:
        sys.stderr.write(__doc__.split("\n\n")[1] + "\n")
        return 2
    rec = run(args[0], args[1], ca, "--vlim" in argv)
    f = rec["failure"]
    print(json.dumps({"planner": rec["planner"], "steps": len(rec["trajectory"]), "failure": f,
                      "times": rec["times"], "solves": rec["solves"]}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
