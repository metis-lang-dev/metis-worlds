"""trajplan.py — perotheia-packages/planner's trajectory planner IN PROCESS (metis-plugin s-df4ff191 step 5): the C++
trajplan::Planner (its lane plan, its OCP, its obstacle / stop / gap floors) through its C ABI, libtrajplan_c.so
(planner repo: trajplan/capi/, `bazel build //trajplan:libtrajplan_c.so`), loaded with ctypes. No dependency, no
Python-version coupling (the Live's venv, 3.12, and the planner venv, 3.11, both load it). Every road world uses it:
the SUMO world (sumo_world.PlannedSumoWorld, run spec "traj": "trajplan") and the CommonRoad-native world
(cr_native, CR_TRAJ=trajplan).

    TRAJPLAN_LIB   the library (default $PLANNER_REPO/bazel-bin/trajplan/libtrajplan_c.so)
    PLANNER_REPO   the planner checkout (default ~/repo/perotheia-packages/wayplan)

    lanes_file(lanemap, path)              the semantic LaneMap (SUMO net or lanelets) → the planner's lane map v2
    p = Trajplan(lanes, vehicle, **params) vehicle {wheelbase, b (centre → rear axle), length, width}
    p.route([(x, y), ...]) · p.command(kind, v_target, x, y) · p.obstacles(t, rows) · p.plan(t, x, y, phi, v, a, delta)
    → (stats dict, [(t, x, y, phi, v, a, kappa)] at the CENTRE)

The behaviour → planner interface is contracts' BehaviourCmd (KINDS below); a new seq is issued whenever the command
changes (the planner acts on a new seq). command_of() maps restrict.py's command (the road family's, restricted) onto it."""
import ctypes
import math
import os
from pathlib import Path

PLANNER_REPO = Path(os.environ.get("PLANNER_REPO", str(Path.home() / "repo" / "perotheia-packages" / "wayplan")))
LIB = Path(os.environ.get("TRAJPLAN_LIB", str(PLANNER_REPO / "bazel-bin" / "trajplan" / "libtrajplan_c.so")))
ABI = 1
KINDS = {"keep": 0, "follow": 1, "stop_at": 2, "yield": 3, "change_left": 4, "change_right": 5, "pass_opposite": 6}
V_STOP = 1e-3                    # a stop asked without a point: KEEP at this (the planner's 0 is "the lane's limit")
SB_VEHICLE = {"length": 4.3, "width": 1.7, "wheelbase": 2.3, "b": 1.15}   # = ocp.SB_VEHICLE (the CommonRoad bench's car)
MAX_PTS = 256

_lib = None


def lib():
    global _lib
    if _lib is None:
        L = ctypes.CDLL(str(LIB))
        D, P, I, U = ctypes.c_double, ctypes.c_void_p, ctypes.c_int, ctypes.c_uint32
        DP, CP = ctypes.POINTER(ctypes.c_double), ctypes.c_char_p
        L.tp_version.restype = I
        L.tp_create.argtypes, L.tp_create.restype = [CP, CP, CP, I], P
        L.tp_destroy.argtypes = [P]
        L.tp_lanes.argtypes, L.tp_lanes.restype = [P], I
        L.tp_route.argtypes, L.tp_route.restype = [P, U, DP, I], I
        L.tp_command.argtypes, L.tp_command.restype = [P, I, U, D, D, D, U, U, D], I
        L.tp_obstacles.argtypes, L.tp_obstacles.restype = [P, D, DP, I], I
        L.tp_plan.argtypes, L.tp_plan.restype = [P, D, D, D, D, D, D, D, DP, I, DP, CP, I], I
        if L.tp_version() != ABI:
            raise RuntimeError("trajplan: %s has ABI %d, this binding %d" % (LIB, L.tp_version(), ABI))
        _lib = L
    return _lib


def lanes_file(lanemap, path, speed_default=13.9, ds=0.5):
    """The planner's LANE MAP (format v2: the planner's tools/xodr_lanes.py docstring) from a semantic LaneMap: the
    driving lanes (SUMO's normal + internal, a lanelet map's lanes) with a centre line; the centre resampled every DS m
    with the lane's width; left / right the same-direction neighbours, opposite the oncoming one beside; junction = an
    internal lane; succ by the map's successors. → {lane id: index}."""
    lanes = [ln for ln in lanemap.lanes.values() if ln.shape and len(ln.shape) >= 2
             and getattr(ln, "function", "normal") in ("normal", "internal")
             and getattr(ln, "kind", "driving") in ("driving", "bidirectional")
             and not (ln.allow and "passenger" not in ln.allow) and not (ln.disallow and "passenger" in ln.disallow)]
    idx = {ln.id: i for i, ln in enumerate(lanes)}
    out = ["lanemap 2 semantic"]
    succ = []
    for i, ln in enumerate(lanes):
        pts = _resample(ln.shape, ds)
        left = idx.get(ln.left, -1) if ln.left and not ln.left_opposite else -1
        right = idx.get(ln.right, -1) if ln.right and not ln.right_opposite else -1
        opp = idx.get(ln.left, -1) if ln.left and ln.left_opposite else -1
        out.append("lane %d %s 0 %d %d %.4f %d %d %d %d" % (i, str(ln.id).replace(" ", "_"), int(ln.index or 0),
                                                         1 if ln.internal else 0, float(ln.speed or speed_default),
                                                         len(pts), left, right, opp))
        w = float(ln.width or 3.5)
        out.extend("p %.4f %.4f %.3f" % (x, y, w) for x, y in pts)
        s = [idx[n] for n in ln.succ or [] if n in idx]
        if s:
            succ.append("succ %d %s" % (i, " ".join(map(str, s))))
    Path(path).write_text("\n".join(out + succ) + "\n")
    return idx


def _resample(shape, ds):
    pts = [tuple(map(float, p[:2])) for p in shape]
    cum = [0.0]
    for a, b in zip(pts, pts[1:]):
        cum.append(cum[-1] + math.hypot(b[0] - a[0], b[1] - a[1]))
    L = cum[-1]
    if L < 1e-6:
        return pts[:1]
    n = max(1, int(math.ceil(L / ds)))
    out, j = [], 0
    for i in range(n + 1):
        s = min(L, i * L / n)
        while j < len(cum) - 2 and cum[j + 1] < s:
            j += 1
        u = (s - cum[j]) / max(cum[j + 1] - cum[j], 1e-12)
        out.append((pts[j][0] + u * (pts[j + 1][0] - pts[j][0]), pts[j][1] + u * (pts[j + 1][1] - pts[j][1])))
    return out


class Trajplan:
    def __init__(self, lanes, vehicle, **params):
        kv = dict(wheelbase=vehicle["wheelbase"], b=vehicle["b"], length=vehicle["length"], width=vehicle["width"])
        kv.update(params)
        self.params = kv
        err = ctypes.create_string_buffer(512)
        self.h = lib().tp_create(str(lanes).encode(), " ".join("%s=%s" % (k, v) for k, v in kv.items()).encode(),
                                 err, 512)
        if not self.h:
            raise RuntimeError("trajplan: %s" % err.value.decode())
        self.seq, self.last_cmd = 0, None
        self._out = (ctypes.c_double * (7 * MAX_PTS))()
        self._st = (ctypes.c_double * 8)()
        self._why = ctypes.create_string_buffer(256)

    def route(self, pts, seq=1):
        pts = [p for p in pts or [] if p is not None]
        if not pts:
            return None
        arr = (ctypes.c_double * (2 * len(pts)))(*[c for p in pts for c in p[:2]])
        return lib().tp_route(self.h, seq, arr, len(pts))

    def command(self, kind, v_target=0.0, x=0.0, y=0.0, lead_id=0, yield_id=0, min_gap=0.0, seq=None):
        """The BehaviourCmd. SEQ given (a commander's: commander.py): sent when it is new; else a new seq whenever the
        command changes. → whether it was sent."""
        if seq is not None:
            if seq == self.seq:
                return False
            self.seq = int(seq)
        else:
            key = (kind, round(v_target, 2), round(x, 1), round(y, 1), lead_id, yield_id, round(min_gap, 2))
            if key == self.last_cmd:
                return False
            self.last_cmd = key
            self.seq += 1
        lib().tp_command(self.h, KINDS[kind], self.seq, float(v_target), float(x), float(y), int(lead_id), int(yield_id),
                         float(min_gap))
        return True

    def obstacles(self, t, obs):
        """obs: [(id, x, y, yaw, v, length, width, static)] box centres."""
        rows = []
        for (i, x, y, yaw, v, L, W, st) in obs:
            rows += [float(i), x, y, yaw, v * math.cos(yaw), v * math.sin(yaw), 0.5 * L, 0.5 * W, 1.0 if st else 0.0]
        arr = (ctypes.c_double * max(1, len(rows)))(*rows)
        lib().tp_obstacles(self.h, float(t), arr, len(obs))

    def plan(self, t, x, y, phi, v, a=0.0, delta=0.0):
        n = lib().tp_plan(self.h, float(t), float(x), float(y), float(phi), float(v), float(a), float(delta), self._out,
                          MAX_PTS, self._st, self._why, 256)
        s = self._st
        st = {"ok": n > 0, "lane": int(s[1]), "change": int(s[2]), "limit": int(s[3]), "lead_gap": s[4], "ms": round(s[5], 2),
              "status": int(s[6]), "iters": int(s[7]), "why": self._why.value.decode(errors="replace")}
        o = self._out
        return st, [tuple(o[7 * i:7 * i + 7]) for i in range(max(0, n))]

    def close(self):
        if self.h:
            lib().tp_destroy(self.h)
            self.h = None

    def __del__(self):
        try:
            self.close()
        except Exception:
            pass


def sample(pts, t_rel):
    """The plan's state at T_REL seconds from its start (linear; the heading the short way; clamped at the end)."""
    if not pts:
        return None
    if t_rel <= pts[0][0]:
        return pts[0]
    for a, b in zip(pts, pts[1:]):
        if t_rel <= b[0]:
            u = (t_rel - a[0]) / max(b[0] - a[0], 1e-9)
            dh = math.atan2(math.sin(b[3] - a[3]), math.cos(b[3] - a[3]))
            return (a[0] + u * (b[0] - a[0]), a[1] + u * (b[1] - a[1]), a[2] + u * (b[2] - a[2]), a[3] + u * dh,
                    a[4] + u * (b[4] - a[4]), a[5] + u * (b[5] - a[5]), a[6] + u * (b[6] - a[6]))
    return pts[-1]


def command_of(cmd, v, limit, stop_xy=None, brake=None, change=None, carry=False, beat_s=1.0, inch_ms=1.0, away_ms=3.0):
    """restrict.py's held command (the road family's, after the restrictor) → BehaviourCmd (kind, v_target, x, y):
      accel                 → keep at the lane's limit (or the pace: LIMIT is the caller's target)
      keep, stop_lat        → keep at the present speed (hold it)
      brake(R)              → keep at max(0, v − BRAKE·beat): R's deceleration (m/s², positive) over the beat
      inch / drive_away     → keep at restrict's INCH_MS / AWAY_MS
      yield                 → stop_at STOP_XY (the zone line, min_dist short), else keep at a stop
      a change begun        → change_left / change_right (CHANGE: the side); a carry → pass_opposite
    the speed clip of the restrictor's bound stays the world's (after the planner)."""
    kind = (cmd or ("keep",))[0]
    if carry:
        return "pass_opposite", max(V_STOP, limit), 0.0, 0.0
    if change in ("left", "right"):
        return "change_" + change, max(V_STOP, limit), 0.0, 0.0
    if kind == "yield":
        if stop_xy is not None:
            return "stop_at", 0.0, stop_xy[0], stop_xy[1]
        return "keep", V_STOP, 0.0, 0.0
    if kind == "accel":
        vt = limit
    elif kind == "brake":
        vt = max(0.0, v - abs(brake if brake is not None else 4.0) * beat_s)
    elif kind == "inch":
        vt = inch_ms
    elif kind == "drive_away":
        vt = away_ms
    else:                                            # keep, stop_lat, anything else: hold the speed
        vt = v
    return "keep", max(V_STOP, vt), 0.0, 0.0
