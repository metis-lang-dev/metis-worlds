"""ocp.py — OUR trajectory planner: SB-2023's low-level optimisation, function for function, written from its equations
(planner-loop s-0dcc5ed1 step 3 M2; PLANNER.md §3, §7; steps/sb2023-reading-opus.md §2–3, §6). SB's repository has no
licence: nothing of it is copied; the method is a handful of equations, written here in our own code over CasADi.

    solve(ref, x0, veh, dt, opts) → Result(x, u, ok, status, iterations, seconds)

- ref: 4 × N, per step the CENTRE's x, y, the speed v, the heading φ (CommonRoad coordinates). x0: the centre's x, y,
  the speed, the heading at the first step. veh: wheelbase L, b (centre to rear axle), a_max, s_max (steering).
- The model: the kinematic single track at the REAR axle, x = (x_r, y_r, v, φ), u = (a, δ): ẋ_r = v cos φ,
  ẏ_r = v sin φ, v̇ = a, φ̇ = v tan δ / L; discretised by CasADi's fixed-step Runge-Kutta integrator over dt with two
  finite elements.
- The cost: Σ uᵀRu + Σ (u_i − u_{i+1})ᵀ R_Δ (u_i − u_{i+1}) + Σ_i ‖ref_xy,i − (x_r,i + b cos φ_i, y_r,i + b sin φ_i)‖²
  (the centre's position error only). R = R_Δ = 0 by default (SB's defaults).
- The constraints: the dynamics; |a| ≤ a_max; |δ| ≤ s_max; v ≥ −0.01; x_0 = x0 moved to the rear axle; Kamm's circle
  a² + (v² tan δ / L)² ≤ a_max².
- The warm start: the reference moved to the rear axle; δ_i = atan(L · Δφ_i/dt / max(½(v_i + v_{i+1}), 0.1)) and
  a_i = Δv_i/dt, both clipped to their bounds.
- The solver: IPOPT through CasADi's Opti at IPOPT's defaults; one solve over the whole reference (ONE SHOT).
- After the solve: the inputs re-simulated from x_0 step by step (scipy's solve_ivp, its defaults), the states moved
  back to the centre: the returned trajectory.
OUR ADDITIONS, all OFF by default (opts): `steer_rate` (|δ_{i+1} − δ_i| ≤ rate·dt), `R` / `R_diff` (input weights),
`speed_weight` (a v-tracking term), `corridor` (per-step half-spaces), `print` (IPOPT's console). The parity proof
(cr_bench --planner ours-parity) runs with every addition off."""
import math
import time
from dataclasses import dataclass, field

import numpy as np

SB_VEHICLE = {"length": 4.3, "width": 1.7, "wheelbase": 2.3, "b": 1.15, "a_max": 9.0, "s_max": 1.0}


@dataclass
class Result:
    x: np.ndarray = None           # 4 × N at the centre: x, y, v, φ
    u: np.ndarray = None           # 2 × (N − 1): a, δ
    ok: bool = False
    status: str = None
    iterations: int = None
    seconds: float = None
    extra: dict = field(default_factory=dict)


def _model(veh, dt):
    import casadi as ca
    xs = ca.MX.sym("x", 4)
    us = ca.MX.sym("u", 2)
    rhs = ca.vertcat(xs[2] * ca.cos(xs[3]), xs[2] * ca.sin(xs[3]), us[0], xs[2] * ca.tan(us[1]) / veh["wheelbase"])
    step = ca.integrator("step", "rk", {"x": xs, "p": us, "ode": rhs},
                         {"tf": dt, "simplify": True, "number_of_finite_elements": 2})
    return ca.Function("f", [xs, us], [step(x0=xs, p=us)["xf"]])


def warm_start(ref, veh, dt):
    ref = np.array(ref, dtype=float)
    rear = ref.copy()
    rear[0] -= np.cos(ref[3]) * veh["b"]
    rear[1] -= np.sin(ref[3]) * veh["b"]
    v_mid = np.maximum(0.5 * (ref[2, 1:] + ref[2, :-1]), 0.1)
    delta = np.arctan(veh["wheelbase"] * (np.diff(ref[3]) / dt) / v_mid)
    delta = np.clip(delta, -veh["s_max"], veh["s_max"])
    acc = np.clip(np.diff(ref[2]) / dt, -veh["a_max"], veh["a_max"])
    return rear, np.vstack([acc, delta])


def resimulate(x_rear0, u, veh, dt):
    from scipy.integrate import solve_ivp
    L = veh["wheelbase"]

    def ode(t, s, a, d):
        return [s[2] * math.cos(s[3]), s[2] * math.sin(s[3]), a, s[2] * math.tan(d) / L]
    n = u.shape[1] + 1
    x = np.zeros((4, n))
    x[:, 0] = x_rear0
    for i in range(n - 1):
        sol = solve_ivp(ode, [0.0, dt], x[:, i], args=(float(u[0, i]), float(u[1, i])), dense_output=True)
        x[:, i + 1] = sol.sol(dt)
    x[0] += np.cos(x[3]) * veh["b"]
    x[1] += np.sin(x[3]) * veh["b"]
    return x


def solve(ref, x0, veh=None, dt=0.1, opts=None):
    import casadi as ca
    veh = dict(SB_VEHICLE, **(veh or {}))
    opts = dict(opts or {})
    ref = np.asarray(ref, dtype=float)
    n = ref.shape[1]
    f = _model(veh, dt)
    R = np.asarray(opts.get("R", np.zeros((2, 2))), dtype=float)
    Rd = np.asarray(opts.get("R_diff", np.zeros((2, 2))), dtype=float)
    opti = ca.Opti()
    X = opti.variable(4, n)
    U = opti.variable(2, n - 1)
    b = veh["b"]
    x0r = np.array([x0[0] - math.cos(x0[3]) * b, x0[1] - math.sin(x0[3]) * b, x0[2], x0[3]])
    J = 0
    for i in range(n - 1):
        J += ca.mtimes([U[:, i].T, R, U[:, i]])
        if i < n - 2:
            du = U[:, i] - U[:, i + 1]
            J += ca.mtimes([du.T, Rd, du])
    for i in range(n):
        J += (ref[0, i] - X[0, i] - ca.cos(X[3, i]) * b) ** 2 + (ref[1, i] - X[1, i] - ca.sin(X[3, i]) * b) ** 2
    if opts.get("speed_weight"):
        J += opts["speed_weight"] * ca.sumsqr(X[2, :] - ref[2, :])
    opti.minimize(J)
    for i in range(n - 1):
        opti.subject_to(X[:, i + 1] == f(X[:, i], U[:, i]))
    opti.subject_to(U[0, :] >= -veh["a_max"])          # SB's rows, one by one in its order (IPOPT's path follows them)
    opti.subject_to(U[0, :] <= veh["a_max"])
    opti.subject_to(U[1, :] >= -veh["s_max"])
    opti.subject_to(U[1, :] <= veh["s_max"])
    opti.subject_to(X[2, :] >= -0.01)
    opti.subject_to(X[:, 0] == x0r)
    for i in range(n - 1):
        opti.subject_to(U[0, i] ** 2 + (X[2, i] ** 2 * ca.tan(U[1, i]) / veh["wheelbase"]) ** 2 <= veh["a_max"] ** 2)
    if opts.get("steer_rate"):
        r = float(opts["steer_rate"]) * dt
        for i in range(n - 2):
            opti.subject_to(opti.bounded(-r, U[1, i + 1] - U[1, i], r))
    for (i, nx, ny, c) in opts.get("corridor") or []:       # half-spaces on the centre: nx·x + ny·y ≤ c at step i
        opti.subject_to(nx * (X[0, i] + ca.cos(X[3, i]) * b) + ny * (X[1, i] + ca.sin(X[3, i]) * b) <= c)
    ipopt = {} if opts.get("print") else {"ipopt.print_level": 0, "print_time": False, "ipopt.sb": "yes"}
    opti.solver("ipopt", ipopt)
    xg, ug = warm_start(ref, veh, dt)
    opti.set_initial(X, xg)
    opti.set_initial(U, ug)
    t0 = time.perf_counter()
    res = Result()
    try:
        sol = opti.solve()
        u = np.atleast_2d(sol.value(U))
        res.ok = True
    except RuntimeError:
        sol, u = None, None
    st = opti.stats()
    res.status, res.iterations = st.get("return_status"), st.get("iter_count")
    res.seconds = round(time.perf_counter() - t0, 3)
    if res.ok:
        res.u = u
        res.x = resimulate(x0r, u, veh, dt)
    return res
