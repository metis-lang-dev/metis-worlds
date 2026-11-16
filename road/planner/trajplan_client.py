"""trajplan_client.py — perotheia-packages/planner's trajectory planner (trajplan::Planner: the C++ lane plan + OCP,
its obstacle floors) as the native world's trajectory level (metis-plugin s-df4ff191 step 5; CR_TRAJ=trajplan).

The planner runs as a child process, `cr_plan_server` (planner repo: trajplan/cr/cr_plan_server.cc,
`bazel build //trajplan:cr_plan_server`), over a line protocol (its header); its lane map is the scenario's
lanelets converted by the planner's tools/cr_lanes.py (from the JSON cr_lanelets.py writes). Pure Python (the
Live's venv): nothing here imports CommonRoad.

    TRAJPLAN_SERVER   the server binary (default: $PLANNER_REPO/bazel-bin/trajplan/cr_plan_server)
    PLANNER_REPO      the planner checkout (default ~/repo/perotheia-packages/wayplan)

The family's command, as the world holds it (iface.setpoints_of + the world's change / carry state), becomes the
planner's BehaviourCmd: a change to a sibling → CHANGE_LEFT / CHANGE_RIGHT, a carry through the oncoming lane →
PASS_OPPOSITE, a stop point → STOP_AT, else KEEP at the desired speed (a stop asked without a point: KEEP at
V_STOP, the planner's 0 is 'the lane's limit')."""
import math
import os
import subprocess
from pathlib import Path

PLANNER_REPO = Path(os.environ.get("PLANNER_REPO", str(Path.home() / "repo" / "perotheia-packages" / "wayplan")))
SERVER = Path(os.environ.get("TRAJPLAN_SERVER", str(PLANNER_REPO / "bazel-bin" / "trajplan" / "cr_plan_server")))
CR_LANES = PLANNER_REPO / "tools" / "cr_lanes.py"
V_STOP = 1e-3


class TrajplanServer:
    def __init__(self, lanes, log, vehicle, **params):
        self.proc = subprocess.Popen([str(SERVER)], stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=log,
                                     text=True)
        kv = dict(wheelbase=vehicle["wheelbase"], b=vehicle["b"], length=vehicle["length"], width=vehicle["width"])
        kv.update(params)
        r = self._ask("init %s %s" % (lanes, " ".join("%s=%s" % (k, v) for k, v in kv.items())))
        if not r.startswith("ok"):
            raise RuntimeError("trajplan: init refused: %s" % r)
        self.seq, self.last_cmd = 0, None

    def _ask(self, line):
        self.proc.stdin.write(line + "\n")
        self.proc.stdin.flush()
        r = self.proc.stdout.readline()
        if not r:
            raise RuntimeError("trajplan: the server ended")
        return r.strip()

    def route(self, pts):
        if pts:
            return self._ask("route 1 " + " ".join("%.4f %.4f" % (x, y) for x, y in pts))
        return None

    def command(self, kind, v_target=0.0, x=0.0, y=0.0, lead_id=0, yield_id=0):
        """A new seq whenever the command changes (the planner acts on a new seq)."""
        key = (kind, round(v_target, 2), round(x, 1), round(y, 1), lead_id, yield_id)
        if key == self.last_cmd:
            return
        self.last_cmd = key
        self.seq += 1
        self._ask("cmd %s %d %.4f %.4f %.4f %d %d" % (kind, self.seq, v_target, x, y, lead_id, yield_id))

    def obstacles(self, t, obs):
        """obs: [(id, x, y, yaw, v, length, width, static)] box centres."""
        parts = ["obs %.3f %d" % (t, len(obs))]
        for (i, x, y, yaw, v, L, W, st) in obs:
            parts.append("%d %.4f %.4f %.5f %.4f %.4f %.3f %.3f %d" % (i, x, y, yaw, v * math.cos(yaw), v * math.sin(yaw),
                                                                       0.5 * L, 0.5 * W, 1 if st else 0))
        self._ask(" ".join(parts))

    def plan(self, t, x, y, phi, v, a, delta):
        """→ (head dict, [(t, x, y, phi, v, a, kappa)]) at the centre."""
        head = self._ask("plan %.3f %.5f %.5f %.6f %.5f %.5f %.6f" % (t, x, y, phi, v, a, delta))
        pts_line = self.proc.stdout.readline().split()
        h = {}
        rest = head.split(" why=", 1)
        for tok in rest[0].split()[1:]:
            k, _, val = tok.partition("=")
            h[k] = float(val) if val.replace(".", "", 1).replace("-", "", 1).isdigit() else val
        h["why"] = rest[1] if len(rest) > 1 else ""
        vals = [float(s) for s in pts_line[1:]]
        pts = [tuple(vals[i:i + 7]) for i in range(0, len(vals) - 6, 7)]
        return h, pts

    def close(self):
        try:
            self.proc.stdin.write("quit\n")
            self.proc.stdin.flush()
        except Exception:
            pass
        self.proc.kill()


def sample(pts, t_rel):
    """The plan's state at T_REL seconds from its start (linear; clamped at the end)."""
    if not pts:
        return None
    if t_rel <= pts[0][0]:
        return pts[0]
    for a, b in zip(pts, pts[1:]):
        if t_rel <= b[0]:
            u = (t_rel - a[0]) / max(b[0] - a[0], 1e-9)
            dh = math.atan2(math.sin(b[3] - a[3]), math.cos(b[3] - a[3]))
            return tuple([a[0] + u * (b[0] - a[0]), a[1] + u * (b[1] - a[1]), a[2] + u * (b[2] - a[2]), a[3] + u * dh]
                         + [a[j] + u * (b[j] - a[j]) for j in (4, 5, 6)])
    return pts[-1]
