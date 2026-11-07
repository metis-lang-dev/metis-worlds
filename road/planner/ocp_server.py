#!/usr/bin/env python3
"""ocp_server.py — OUR OCP (ocp.py, SB's low-level optimisation; additions off) as the native world's planner child
(planner-loop s-0dcc5ed1 step 3 M3). JSON lines on stdin → one JSON line each on stdout; the planner venv (casadi).

  {"op": "init", "scenario": XML}  → {"ok", "dt", "k0", "initial": STATE, "vehicle": {length, width, ...}}
  {"op": "plan", "x0": [x, y, v, φ], "k": K, "ref": [[x, y, v, φ] * N]}
                                   → {"ok": true, "states": [STATE * N], "status", "iterations", "ms"} | {"ok": false, ...}
  {"op": "quit"}
STATE = {k, x, y, v, phi, delta, a} at the CENTRE, CommonRoad coordinates; the reference is the world's (reference.py
over the LaneMap from the family's command), N steps from K."""
import json
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import ocp  # noqa: E402


def init(xml):
    from commonroad.common.file_reader import CommonRoadFileReader
    sc, pps = CommonRoadFileReader(str(xml)).open()
    x0 = list(pps.planning_problem_dict.values())[0].initial_state
    return {"ok": True, "dt": sc.dt, "k0": int(x0.time_step), "vehicle": ocp.SB_VEHICLE,
            "initial": {"k": int(x0.time_step), "x": float(x0.position[0]), "y": float(x0.position[1]),
                        "v": float(x0.velocity), "phi": float(x0.orientation), "delta": 0.0, "a": 0.0}}


def plan(msg, dt):
    import numpy as np
    ref = np.array(msg["ref"], dtype=float).T
    t0 = time.perf_counter()
    r = ocp.solve(ref, [float(v) for v in msg["x0"]], dt=dt)
    ms = round(1000 * (time.perf_counter() - t0), 1)
    if not r.ok:
        return {"ok": False, "status": r.status, "iterations": r.iterations, "ms": ms}
    k = int(msg["k"])
    states = [{"k": k + i, "x": float(r.x[0, i]), "y": float(r.x[1, i]), "v": float(r.x[2, i]), "phi": float(r.x[3, i]),
               "delta": float(r.u[1, min(i, r.u.shape[1] - 1)]), "a": float(r.u[0, min(i, r.u.shape[1] - 1)])}
              for i in range(r.x.shape[1])]
    return {"ok": True, "states": states, "status": r.status, "iterations": r.iterations, "ms": ms}


def main():
    dt = 0.1
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
            if msg.get("op") == "init":
                out = init(msg["scenario"])
                dt = out["dt"]
            elif msg.get("op") == "plan":
                out = plan(msg, dt)
            elif msg.get("op") == "quit":
                print(json.dumps({"ok": True}), flush=True)
                return 0
            else:
                out = {"ok": False, "reason": "unknown op"}
        except Exception as e:
            out = {"ok": False, "reason": {"server": "%s: %s" % (type(e).__name__, str(e)[:300])}}
        print(json.dumps(out), flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
