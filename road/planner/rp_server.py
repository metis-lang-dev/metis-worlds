#!/usr/bin/env python3
"""rp_server.py — the reactive planner as a child of the composition (planner-loop s-0dcc5ed1 step 2, deliverable 3).

    road/.venv-planner/bin/python road/planner/rp_server.py      JSON lines on stdin → one JSON line each on stdout

The Live's venv never imports CommonRoad (cr_world's rule); the native CommonRoad world (road/world/cr_native.py) talks
to the planner through this process. Ops:
  {"op": "init", "scenario": XML}         → {"ok", "dt", "k0", "wb_rear", "goal_window", "initial": STATE}
  {"op": "plan", "state": STATE, "set": {"desired_v"?, "stop_xy"?, "path"?}}
                                          → {"ok": true, "states": [STATE...], "ms", "cost"} | {"ok": false, "reason"}
  {"op": "quit"}
STATE = {k, x, y, v, phi, delta, a} at the vehicle's CENTRE in CommonRoad coordinates (the server moves it to the rear
axle for the planner and back). `path` (a polyline, CommonRoad coordinates) replaces the reference path: a lane change is
a new path (set_reference_path); the path is extended as the bench's (cr_bench.reference_path: 20 m back, 150 m past)
and smoothed by the package's create_coordinate_system. `stop_xy` is projected on the current path to its s: stopping
mode (set_desired_lon_position); else `desired_v` (velocity keeping). The planner, its configuration and its collision
checker are the baseline's (cr_bench.configure: the recorded obstacles with their recorded predictions).
"""
import json
import math
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import cr_bench  # noqa: E402


def extend(ref):
    import numpy as np
    ref = np.asarray(ref, dtype=float)
    t = ref[-1] - ref[-2]
    t = t / max(np.linalg.norm(t), 1e-9)
    h = ref[1] - ref[0]
    h = h / max(np.linalg.norm(h), 1e-9)
    tail = ref[-1] + np.outer(np.arange(2.0, cr_bench.EXTEND_M + 1e-9, 2.0), t)
    head = ref[0] - np.outer(np.arange(cr_bench.BACK_M, 1e-9, -2.0), h)
    return np.vstack([head, ref, tail])


class Server:
    def __init__(self):
        self.planner = None

    def init(self, scenario):
        from commonroad.common.file_reader import CommonRoadFileReader
        from commonroad_rp.reactive_planner import ReactivePlanner
        from commonroad_rp.utility.utils_coordinate_system import create_coordinate_system
        scen, pps = CommonRoadFileReader(str(scenario)).open()
        pp = list(pps.planning_problem_dict.values())[0]
        self.cfg = cr_bench.configure(scen, pps, pp)
        self.planner = ReactivePlanner(self.cfg)
        self.path = cr_bench.reference_path(scen, pp)
        self.planner.set_reference_path(coordinate_system=create_coordinate_system(self.path))
        self.wb = float(self.cfg.vehicle.wb_rear_axle)
        x0 = pp.initial_state
        last = cr_bench.goal_last_step(pp)
        first = [int(s.time_step.start) for s in pp.goal.state_list if getattr(s, "time_step", None) is not None]
        return {"ok": True, "dt": scen.dt, "k0": int(x0.time_step), "wb_rear": self.wb,
                "goal_window": [min(first), last] if first and last is not None else None,
                "initial": {"k": int(x0.time_step), "x": float(x0.position[0]), "y": float(x0.position[1]),
                            "v": float(x0.velocity), "phi": float(x0.orientation), "delta": 0.0,
                            "a": float(getattr(x0, "acceleration", 0.0) or 0.0)}}

    def _rear(self, st):
        import numpy as np
        from commonroad_rp.reactive_planner import ReactivePlannerState
        x = st["x"] - self.wb * math.cos(st["phi"])
        y = st["y"] - self.wb * math.sin(st["phi"])
        return ReactivePlannerState(time_step=int(st["k"]), position=np.array([x, y]), orientation=float(st["phi"]),
                                    velocity=float(st["v"]), acceleration=float(st.get("a", 0.0)),
                                    yaw_rate=float(st.get("yaw_rate", 0.0)), steering_angle=float(st.get("delta", 0.0)))

    def _centre(self, s):
        return {"k": int(s.time_step), "x": float(s.position[0] + self.wb * math.cos(s.orientation)),
                "y": float(s.position[1] + self.wb * math.sin(s.orientation)), "v": float(s.velocity),
                "phi": float(s.orientation), "delta": float(s.steering_angle), "a": float(s.acceleration)}

    def plan(self, state, sp):
        from commonroad_rp.utility.utils_coordinate_system import create_coordinate_system
        p = self.planner
        t0 = time.perf_counter()
        try:
            if sp.get("path"):
                p.set_reference_path(coordinate_system=create_coordinate_system(extend(sp["path"])))
            x0 = self._rear(state)
            p.reset(initial_state_cart=x0, initial_state_curv=None, collision_checker=p.collision_checker,
                    coordinate_system=p.coordinate_system)
            if sp.get("stop_xy") is not None:
                s_stop = float(p.coordinate_system.convert_to_curvilinear_coords(*map(float, sp["stop_xy"]))[0])
                p.set_desired_lon_position(s_stop)
            else:
                # current_speed 0.0 would make the package fall back to the planning problem's speed: never 0 exactly
                dv = max(0.0, float(sp.get("desired_v") or 0.0))
                # a target of 0 is a stop: the package's stopping flag samples the end speed at it (velocity keeping
                # samples around the current speed and finds nothing at a hard stop: ZAM_Over-1_1 k 18-24)
                p.set_desired_velocity(desired_velocity=dv, current_speed=max(float(state["v"]), 1e-3),
                                       stopping=dv <= 0.0)
            out = p.plan()
        except Exception as e:                         # the planner's own failure: a reason, never a crash of the server
            return {"ok": False, "reason": {"exception": "%s: %s" % (type(e).__name__, str(e)[:200])},
                    "ms": round(1000 * (time.perf_counter() - t0), 1)}
        ms = round(1000 * (time.perf_counter() - t0), 1)
        if not out:
            return {"ok": False, "ms": ms, "reason": {
                "kinematics": int(p.infeasible_count_kinematics), "collision": int(p.infeasible_count_collision),
                "by_constraint": {k: int(v) for k, v in p.infeasible_reason_dict.items()},
                "samples": int(p.total_count_samples)}}
        traj = out[0]
        return {"ok": True, "ms": ms, "cost": float(p.optimal_cost), "states": [self._centre(s) for s in traj.state_list]}


def main():
    srv = Server()
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
            op = msg.get("op")
            if op == "init":
                out = srv.init(msg["scenario"])
            elif op == "plan":
                out = srv.plan(msg["state"], msg.get("set") or {})
            elif op == "quit":
                print(json.dumps({"ok": True}), flush=True)
                return 0
            else:
                out = {"ok": False, "reason": {"op": "unknown op %r" % op}}
        except Exception as e:
            out = {"ok": False, "reason": {"server": "%s: %s" % (type(e).__name__, str(e)[:300])}}
        print(json.dumps(out), flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
