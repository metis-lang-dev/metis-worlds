"""reference.py — the reference trajectory from the road family's command over the LaneMap (planner-loop s-0dcc5ed1 step
3 M3; PLANNER.md §2): what SB-2023's decision module hands its optimiser, built from OUR decisions. Pure Python (the
Live's venv). Nothing of SB's code: its idea of a window-fitted speed is a sentence, the profile below is ours.

    build(path, pos, v0, dt, n, target_v, stop_s=None, goal_s=None, window=None, a_des=1.0, b_stop=3.0) → [(x, y, v, φ)] * n

- path: the lane sequence's centre line ahead (CommonRoad coordinates), from the family's lane decision (route lane,
  change, the oncoming lane of a pass), as the world gives it; the ego's lateral offset from it decays to 0 over
  max(10 m, 2 s × v) (a change is the same decay onto the sibling's line).
- the speed profile, per step: accelerate / decelerate at a_des toward the TARGET (the family's: the lane's limit or the
  pace; never above it); a STOP at stop_s (yield, inch: the zone line) caps v by √(2 b_stop (stop_s − s)); a goal on the
  path at goal_s with a time WINDOW (seconds from now) [t1, t2]: if the target reaches goal_s before t1, the cruise is
  lowered so the arrival lands at t1 (the window-fitted speed); arriving after t2 is not sped up past the target (the law's
  limit stands: that row reads 'window').
- φ from the path's tangent; positions by the arc length the profile covers each step."""
import math


def _cum(path):
    out = [0.0]
    for a, b in zip(path, path[1:]):
        out.append(out[-1] + math.hypot(b[0] - a[0], b[1] - a[1]))
    return out


def project(path, p):
    """(s, lateral offset vector) of point P on PATH (the nearest segment)."""
    cum, best = _cum(path), None
    for i in range(len(path) - 1):
        ax, ay = path[i]
        bx, by = path[i + 1]
        dx, dy = bx - ax, by - ay
        L2 = dx * dx + dy * dy
        u = 0.0 if L2 <= 1e-12 else max(0.0, min(1.0, ((p[0] - ax) * dx + (p[1] - ay) * dy) / L2))
        qx, qy = ax + u * dx, ay + u * dy
        d = math.hypot(p[0] - qx, p[1] - qy)
        if best is None or d < best[0]:
            best = (d, cum[i] + u * math.sqrt(L2), (p[0] - qx, p[1] - qy))
    return best[1], best[2]


def at(path, cum, s):
    """The point and tangent heading at arc length S (clamped to the path)."""
    s = max(0.0, min(s, cum[-1]))
    for i in range(len(path) - 1):
        if cum[i] <= s <= cum[i + 1] or i == len(path) - 2:
            seg = max(cum[i + 1] - cum[i], 1e-12)
            u = (s - cum[i]) / seg
            (ax, ay), (bx, by) = path[i], path[i + 1]
            return ax + u * (bx - ax), ay + u * (by - ay), math.atan2(by - ay, bx - ax)
    return path[-1][0], path[-1][1], 0.0


def _profile(v0, dt, n, cruise, a_des, stop_rel=None, b_stop=3.0):
    """Speeds and distances per step: toward CRUISE at a_des, capped by a stop at distance STOP_REL."""
    vs, ds, v, d = [v0], [0.0], v0, 0.0
    for _ in range(n - 1):
        want = cruise
        if stop_rel is not None:
            want = min(want, math.sqrt(max(0.0, 2.0 * b_stop * (stop_rel - d))))
        if v < want:
            v2 = min(want, v + a_des * dt)
        else:
            v2 = max(want, v - max(a_des, b_stop) * dt)
        d += 0.5 * (v + v2) * dt
        v = max(0.0, v2)
        vs.append(v)
        ds.append(d)
    return vs, ds


def _arrival(ds, dt, goal_rel):
    for i, d in enumerate(ds):
        if d >= goal_rel:
            return i * dt
    return None


def build(path, pos, v0, dt, n, target_v, stop_s=None, goal_s=None, window=None, a_des=1.0, b_stop=3.0):
    path = [tuple(map(float, p[:2])) for p in path]
    if len(path) < 2 or n < 2:
        return []
    cum = _cum(path)
    s0, off = project(path, pos)
    target_v = max(0.0, float(target_v or 0.0))
    stop_rel = None if stop_s is None else max(0.0, stop_s - s0)
    cruise = target_v
    vs, ds = _profile(v0, dt, n, cruise, a_des, stop_rel, b_stop)
    if goal_s is not None and window is not None and stop_rel is None:
        goal_rel, (t1, t2) = goal_s - s0, window
        t = _arrival(ds, dt, goal_rel)
        if goal_rel > 0 and t is not None and t < t1 - 1e-9 and t1 > 0:
            lo, hi = 0.0, cruise                       # the cruise that lands the arrival at t1 (bisection)
            for _ in range(40):
                mid = 0.5 * (lo + hi)
                _, dm = _profile(v0, dt, n, mid, a_des, None, b_stop)
                tm = _arrival(dm, dt, goal_rel)
                if tm is None or tm > t1:
                    lo = mid
                else:
                    hi = mid
            cruise = hi
            vs, ds = _profile(v0, dt, n, cruise, a_des, None, b_stop)
    decay = max(10.0, 2.0 * max(v0, target_v))
    out = []
    for v, d in zip(vs, ds):
        x, y, h = at(path, cum, s0 + d)
        w = max(0.0, 1.0 - d / decay)
        w = w * w * (3 - 2 * w)                        # smoothstep: the offset fades without a kink
        out.append((x + w * off[0], y + w * off[1], v, h))
    for i in range(1, len(out)):                       # unwrap the heading (the OCP tracks φ continuously)
        x, y, v, h = out[i]
        p = out[i - 1][3]
        while h - p > math.pi:
            h -= 2 * math.pi
        while h - p < -math.pi:
            h += 2 * math.pi
        out[i] = (x, y, v, h)
    return out
