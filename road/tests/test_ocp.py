"""ocp (planner-loop s-0dcc5ed1 step 3 M2): our SB-equivalent OCP tracks a straight reference from its first state; the
additions are off by default and the steering-rate bound binds when on. Needs casadi + scipy (the planner venv)."""
import importlib.util
import math
from pathlib import Path

import pytest

ROAD = Path(__file__).resolve().parents[1]
pytest.importorskip("casadi", reason="the planner venv: road/planner/setup-venv.sh")
SPEC = importlib.util.spec_from_file_location("ocp", ROAD / "planner" / "ocp.py")
O = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(O)


def straight(n=31, v=10.0, dt=0.1, curve=0.0):
    import numpy as np
    xs = [v * dt * i for i in range(n)]
    return np.array([xs, [curve * x * x for x in xs], [v] * n, [math.atan(2 * curve * x) for x in xs]])


def test_tracks_a_straight_reference():
    ref = straight()
    r = O.solve(ref, [0.0, 0.0, 10.0, 0.0])
    assert r.ok and r.status == "Solve_Succeeded" and r.x.shape == (4, 31) and r.u.shape == (2, 30)
    assert max(abs(r.x[0, i] - ref[0, i]) + abs(r.x[1, i]) for i in range(31)) < 1e-3


def test_the_steering_rate_bound_binds_only_when_on():
    ref = straight(curve=0.01)
    off = O.solve(ref, [0.0, 0.0, 10.0, 0.0])
    on = O.solve(ref, [0.0, 0.0, 10.0, 0.0], opts={"steer_rate": 0.05})
    rate = lambda r: max(abs(r.u[1, i + 1] - r.u[1, i]) / 0.1 for i in range(r.u.shape[1] - 1))
    assert off.ok and on.ok and rate(on) <= 0.05 + 1e-6 < rate(off)
