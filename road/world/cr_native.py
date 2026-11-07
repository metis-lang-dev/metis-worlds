"""cr_native — a CommonRoad scenario in its NATIVE loop, no SUMO process (planner-loop s-0dcc5ed1 step 2, deliverable 3;
the architect's GO 2026-11-07): `NativeCrWorld` presents SumoWorld's face to sumo_host.Loop, so the road family runs
through the UNCHANGED Loop (perceive, belief, road_facts, the fold, the restrictor) while the ego is driven by the
trajectory planner (OUR OCP, road/planner/ocp_server.py, a child in the planner venv: the Live never imports CommonRoad).

    run spec: {"world": "crnative", "scenario": "cr:ID" | "cr:/path/ID.xml", "seed", "work"?, "record"?: PATH}
    road_host.new_world → sumo_host.Loop(run, world=NativeCrWorld)

- The map: the scenario's LANELETS, no SUMO conversion (the user's option 1): the JSON road/planner/cr_lanelets.py
  writes ($CR_LANES_JSON), turned into the LaneMap by cr_lanes.lanemap_from (edges from same-direction neighbours, the
  oncoming lane as left_opposite, junction lanes, zones); a lane id IS its lanelet id; CommonRoad coordinates (no offset).
- The obstacles: cr.json's recorded trajectories, net coordinates (+ net_offset), each at its pose of the step,
  present from its first recorded step to its last (a static one throughout). Lane and s by map matching on the lane
  map's shapes (the front bumper's position on the nearest lane within MATCH_HEADING_DEG of its heading).
- The ego: the planner's plan, one state a step; a new plan every REPLAN steps, at a new command, or when the plan runs
  out. The family's command (handed over by the Loop: world.command(cmd, accel, cap, gap), the one shared line) becomes
  the planner's setpoints (road/planner/iface.setpoints_of); the restrictor's cap clips the executed speed AFTER the
  planner (v ≤ v_prev + cap·dt: the shield outside, belt and braces). A change to a sibling (control's lane index) or a
  carry through the opposite lane (carry_start) sends that lane's centreline as the reference path.
- The accounting: contacts (the ego's box against every present obstacle's: cr_world's test) as `collisions`; the goal
  (the centre in a goal polygon inside the window) ends the run; the director's report carries cr_world's `cr` keys.
- The record (record.json v1, the SB column's shape, mode receding): per step the lanelet (the matched lane's edge →
  cr.json's edge lanelets, the one whose polygon holds the centre), the reference speed asked, the command; a solves
  entry per plan; the executed trajectory. Written to the run's `record` path (or WORK/record.json) at close."""
import json
import math
import os
import subprocess
import sys
import time
from pathlib import Path

import cr_world
from sumo_world import EGO

HERE = Path(__file__).resolve().parent
ROAD = HERE.parent
PLANNER_PY = os.environ.get("PLANNER_PY", str(ROAD / ".venv-planner" / "bin" / "python"))
OCP_SERVER = ROAD / "planner" / "ocp_server.py"   # OUR OCP (ocp.py: SB's low-level optimisation), step 3 M3
REPLAN = 10                    # steps between solves (1 s), besides a new command; each solve: the remaining window
MIN_HORIZON = 30               # steps a solve covers at least (past the goal's window: 3 s ahead)
MATCH_HEADING_DEG = 45.0
MATCH_PAD_M = 6.0
PATH_AHEAD_M = 250.0           # the length of a lane's centreline sent as a reference path
BEAT_S = 1.0                   # brake(R)'s desired speed: the restricted deceleration over this


def _seg_project(px, py, ax, ay, bx, by):
    dx, dy = bx - ax, by - ay
    L2 = dx * dx + dy * dy
    u = 0.0 if L2 <= 1e-12 else max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / L2))
    qx, qy = ax + u * dx, ay + u * dy
    return u, math.hypot(px - qx, py - qy), math.atan2(dy, dx), qx, qy


class LaneIndex:
    """The lane map's shapes for matching: per lane its points, cumulative s and bounding box."""

    def __init__(self, lanemap):
        self.lanes = {}
        for lid, ln in lanemap.lanes.items():
            pts = [tuple(map(float, p[:2])) for p in (ln.shape or [])]
            if len(pts) < 2:
                continue
            acc = [0.0]
            for a, b in zip(pts, pts[1:]):
                acc.append(acc[-1] + math.hypot(b[0] - a[0], b[1] - a[1]))
            xs, ys = [p[0] for p in pts], [p[1] for p in pts]
            self.lanes[lid] = (pts, acc, (min(xs), min(ys), max(xs), max(ys)), ln)

    def project(self, lid, x, y):
        """(s, distance, segment heading, lateral offset: + left) of the point on lane LID's shape."""
        pts, acc, _, ln = self.lanes[lid]
        best = None
        for i in range(len(pts) - 1):
            u, d, h, qx, qy = _seg_project(x, y, pts[i][0], pts[i][1], pts[i + 1][0], pts[i + 1][1])
            if best is None or d < best[1]:
                ax, ay, bx, by = pts[i][0], pts[i][1], pts[i + 1][0], pts[i + 1][1]
                cross = (bx - ax) * (y - ay) - (by - ay) * (x - ax)        # > 0: the point is left of the shape
                best = (acc[i] + u * (acc[i + 1] - acc[i]), d, h, d if cross > 0 else -d)
        s = min(best[0] * (ln.length / acc[-1]) if acc[-1] > 0 else best[0], ln.length)
        return s, best[1], best[2], best[3]

    def match(self, x, y, heading=None, prefer=None):
        """→ (lane, s, lat) of the nearest lane whose direction is within MATCH_HEADING_DEG of HEADING (None: any),
        PREFER kept while the point is inside its width + 0.5 m (no flicker between a lane and its junction's)."""
        cands = []
        for lid, (pts, acc, bb, ln) in self.lanes.items():
            if not (bb[0] - MATCH_PAD_M <= x <= bb[2] + MATCH_PAD_M and bb[1] - MATCH_PAD_M <= y <= bb[3] + MATCH_PAD_M):
                continue
            s, d, h, lat = self.project(lid, x, y)
            if heading is not None:
                dh = abs((h - heading + math.pi) % (2 * math.pi) - math.pi)
                if dh > math.radians(MATCH_HEADING_DEG):
                    continue
            cands.append((d, lid, s, lat, ln))
        if not cands:
            return None
        if prefer is not None:
            for d, lid, s, lat, ln in cands:
                if lid == prefer and d <= 0.5 * (ln.width or 3.2) + 0.5:
                    return lid, s, lat
        d, lid, s, lat, _ = min(cands, key=lambda c: c[0])
        return lid, s, lat

    def centreline(self, lid, s0, ahead=PATH_AHEAD_M, reverse=False, route=None):
        """The lane's shape from s0 on (REVERSE: the opposite lane driven against its direction, from s0 back to its
        start), then its successors' (the route's first, else the first), AHEAD metres; the cut points interpolated;
        net coordinates."""
        out, lane, s, left = [], lid, s0, ahead
        while lane in self.lanes and left > 0:
            pts, acc, _, ln = self.lanes[lane]
            if reverse:
                pts, acc = list(reversed(pts)), [acc[-1] - a for a in reversed(acc)]
                s = acc[-1] - s
            s = max(0.0, min(s, acc[-1]))
            e = min(acc[-1], s + left)
            piece = [_at(pts, acc, s)] + [p for a, p in zip(acc, pts) if s < a < e] + [_at(pts, acc, e)]
            out.extend(piece if not out else piece[1:])
            left -= e - s
            if reverse:
                break
            nxt = [n for n in (ln.succ or []) if n in self.lanes]
            pick = [n for n in nxt if route and self.lanes[n][3].edge in route]
            lane, s = ((pick or nxt)[0] if nxt else None), 0.0
        return out


def _at(pts, acc, s):
    """The point at arc length S on the polyline PTS (cumulative ACC)."""
    for i in range(len(pts) - 1):
        if acc[i] <= s <= acc[i + 1]:
            u = (s - acc[i]) / max(acc[i + 1] - acc[i], 1e-12)
            return (pts[i][0] + u * (pts[i + 1][0] - pts[i][0]), pts[i][1] + u * (pts[i + 1][1] - pts[i][1]))
    return pts[-1] if s > acc[-1] else pts[0]


class _Vehicle:
    def __init__(self, world):
        self.world = world

    def getLaneIndex(self, vid):
        ln = self.world.lanes.lanes.get(self.world.ego_lane)
        return ln[3].index if ln else 0


class _Conn:
    def __init__(self, world):
        self.vehicle = _Vehicle(world)


class Director:
    """cr_world's director face for the Loop and road_tree: extend_lanemap, goal_lanes, window_open / window_over, report."""

    def __init__(self, world):
        self.w = world
        self.goal_lanes = None

    def _windows(self):
        return [g.get("time") for g in self.w.goals]

    def window_open(self, margin):
        ws = self._windows()
        if self.w.goal_t is not None or not ws or any(not x for x in ws):
            return False
        return self.w.t <= max((x[1] - self.w.k0) * self.w.dt for x in ws) + margin

    def window_over(self, margin):
        ws = self._windows()
        if self.w.goal_t is not None or not ws or any(not x for x in ws):
            return False
        return self.w.t > max((x[1] - self.w.k0) * self.w.dt for x in ws) + margin

    def report(self):
        w = self.w
        return {"rc": None, "cr": {"id": w.doc["id"], "goal_reached": w.goal_t is not None, "goal_t": w.goal_t,
                                   "contact": bool(w.contacts), "contacts": w.contacts[:10], "native": True,
                                   "plans": len(w.record["solves"]), "plan_failures": w.plan_failures,
                                   "record": str(w.record_path)}}


def _inside(pt, poly):
    return cr_world.inside(pt, poly)


class NativeCrWorld:
    """SumoWorld's face for sumo_host.Loop over a CommonRoad scenario with no SUMO process."""

    def __init__(self, scenario, work, seed=1, dt=None, traci=None, label=None, record=None, **kw):
        lanes_json = os.environ.get("CR_LANES_JSON")    # cr_bench writes it (cr_lanelets.export) before the run
        if not lanes_json or not Path(lanes_json).is_file():
            raise RuntimeError("cr_native: $CR_LANES_JSON names no lanelet file (road/planner/cr_lanelets.py writes it)")
        self.doc, self.seed, self.work = json.loads(Path(lanes_json).read_text()), int(seed), Path(work)
        self.sid = self.doc["id"]
        self.path = self.doc.get("source")
        self.net = lanes_json                          # the Loop's lane map comes from self.lanemap (its fallback reads a net)
        self.dt = float(self.doc.get("dt") or 0.1)
        self.off = (0.0, 0.0)
        pl = (self.doc.get("planning") or [{}])[0]
        self.k0 = int(pl["initial"]["k"])
        self.goals = pl.get("goals") or []
        self.director = Director(self)
        import cr_lanes
        lm = cr_lanes.lanemap_from(self.doc)
        self.lanes = LaneIndex(lm)
        self.lanemap = lm
        self.conn = _Conn(self)
        self.collisions, self.contacts, self.ego_collisions = [], [], 0
        self.carry, self.ego_done, self.ego_seen = None, False, True
        self.t, self.tick, self.goal_t = 0.0, 0, None
        self.cmd = ("keep", None)
        self.cap, self.accel, self.gap = None, None, None
        self.target_lane, self.ref_lane, self.reverse = None, None, False
        self.plan, self.plan_i, self.last_plan_tick, self.last_set = [], 0, None, None
        self.plan_failures = 0
        self.proc = None
        self.started = False
        rec = record or os.environ.get("CR_NATIVE_RECORD")       # cr_bench --planner composition sets it per run
        self.record_path = Path(rec) if rec else self.work / "record.json"
        self.record = {"record": 1, "planner": "composition", "settings": {
            "world": "cr_native (lanelets, no SUMO)", "planner": "ocp.py (SB's low-level OCP) via ocp_server.py",
            "reference": "reference.py over the LaneMap from the family's command",
            "mapping": "iface.setpoints_of", "replan_steps": REPLAN, "clip": "v <= v_prev + cap*dt after the planner"},
            "scenario": self.doc.get("source"), "dt": self.dt, "horizon": {"mode": "receding", "steps": None,
                                                                             "seconds": None},
            "steps": [], "lane_changes": [], "stops": [], "solves": [], "times": {}, "trajectory": [],
            "vehicle": None, "failure": None}
        self.lanelet_poly = {int(la["id"]): cr_world.lanelet_poly(la) for la in self.doc.get("lanelets") or []}
        self.obstacles = self.doc.get("obstacles") or []
        goal_lanes = set()
        for g in self.goals:
            for la in g.get("lanelets") or []:
                if str(la) in lm.lanes:
                    goal_lanes.add(str(la))
            for poly in g.get("polygons") or []:
                cx = sum(p[0] for p in poly) / len(poly) + self.off[0]
                cy = sum(p[1] for p in poly) / len(poly) + self.off[1]
                m = self.lanes.match(cx, cy)
                if m:
                    goal_lanes.add(m[0])
        self.director.goal_lanes = sorted(goal_lanes) or None

    # ── the planner child ──
    def _ask(self, msg):
        self.proc.stdin.write(json.dumps(msg) + "\n")
        self.proc.stdin.flush()
        while True:
            line = self.proc.stdout.readline()
            if not line:
                raise RuntimeError("cr_native: the planner server ended (see %s)" % (self.work / "ocp_server.log"))
            if line.startswith("{"):
                return json.loads(line)

    def start(self):
        self.work.mkdir(parents=True, exist_ok=True)
        log = open(self.work / "ocp_server.log", "w")
        self.proc = subprocess.Popen([PLANNER_PY, str(OCP_SERVER)], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                     stderr=log, text=True)
        src = self.doc.get("source") or self.path
        r = self._ask({"op": "init", "scenario": src})
        if not r.get("ok"):
            raise RuntimeError("cr_native: the planner server refused the scenario: %s" % r.get("reason"))
        self.ego = dict(r["initial"])                  # CommonRoad coordinates, the centre
        veh = r.get("vehicle") or {}
        self.EGO_L, self.EGO_W = float(veh.get("length", self.EGO_L)), float(veh.get("width", self.EGO_W))
        self.record["vehicle"] = dict(veh, type="SB's car (ocp.SB_VEHICLE); the oracle's FORD_ESCORT")
        m = self._match_ego()
        self.ego_lane, self.ego_s, self.ego_lat = m
        self.home_lane = self.ego_lane
        self.ego_route = self._route(self.ego_lane)

    def close(self):
        if self.proc is not None:
            try:
                self._ask({"op": "quit"})
            except Exception:
                pass
            self.proc.kill()
            self.proc = None
        self.record["trajectory"] = self.record.get("trajectory") or []
        self.record_path.parent.mkdir(parents=True, exist_ok=True)
        self.record_path.write_text(json.dumps(self.record, indent=1))

    # ── coordinates and matching ──
    def to_net(self, x, y):
        return x + self.off[0], y + self.off[1]

    def to_cr(self, x, y):
        return x - self.off[0], y - self.off[1]

    def _front(self, x, y, h, length):
        return x + 0.5 * length * math.cos(h), y + 0.5 * length * math.sin(h)

    EGO_L, EGO_W = 4.508, 1.61                         # the reactive planner's vehicle (CommonRoad id 2)

    def _match_ego(self):
        e = self.ego
        nx, ny = self.to_net(e["x"], e["y"])
        fx, fy = self._front(nx, ny, e["phi"], self.EGO_L)
        heading = e["phi"] if self.carry is None else e["phi"] + math.pi     # carried: on the opposite lane's direction
        m = self.lanes.match(fx, fy, heading, prefer=getattr(self, "ego_lane", None))
        if m is None:
            m = self.lanes.match(fx, fy, None)
        if m is None:
            return getattr(self, "ego_lane", None), getattr(self, "ego_s", 0.0), 0.0
        return m

    def _route(self, lane):
        """The edges from LANE to a goal lane over the lane map's successors (breadth first), else LANE's edge."""
        goal = set(self.director.goal_lanes or [])
        lm = self.lanemap.lanes
        if lane not in lm:
            return []
        prev, todo, seen = {lane: None}, [lane], {lane}
        hit = lane if lane in goal else None
        while todo and hit is None:
            cur = todo.pop(0)
            for n in lm[cur].succ or []:
                if n in lm and n not in seen:
                    seen.add(n)
                    prev[n] = cur
                    todo.append(n)
                    if n in goal:
                        hit = n
                        break
        chain = []
        x = hit
        while x is not None:
            chain.append(x)
            x = prev[x]
        chain = list(reversed(chain)) or [lane]
        edges = []
        for l in chain:
            ln = lm[l]
            if not ln.internal and ln.edge and (not edges or edges[-1] != ln.edge):
                edges.append(ln.edge)
        return edges

    # ── SumoWorld's face ──
    def command(self, cmd, accel=None, cap=None, gap=None):
        """The Loop's held command for this step (the one shared line in sumo_host.Loop.restrict): the setpoints' source."""
        self.cmd, self.accel, self.cap, self.gap = cmd, accel, cap, gap

    def control(self, accel=None, lane=None):
        """The restrictor's output: ACCEL is the restricted command (kept as the clip when command() gave no cap);
        LANE a target lane index on the ego's edge (a change to that sibling)."""
        if accel is not None and self.cap is None:
            self.cap = accel
        if lane is not None:
            here = self.lanemap.lanes.get(self.ego_lane)
            if here is not None:
                for side in ("left", "right"):
                    other = getattr(here, side)
                    if other and other in self.lanemap.lanes and self.lanemap.lanes[other].index == lane \
                            and not getattr(here, side + "_opposite"):
                        self.target_lane, self.reverse = other, False
                        self.record["lane_changes"].append({"k": self.k, "from": self.ego_lane, "to": other,
                                                            "side": side})

    def carry_start(self, lane):
        self.carry = {"to": self.ego_lane, "home": self.ego_lane, "s": self.ego_s, "into": lane, "near_end": False}
        self.target_lane, self.reverse = lane, True
        self.record["lane_changes"].append({"k": self.k, "from": self.ego_lane, "to": lane, "side": "opposite"})

    def carry_back(self):
        if self.carry is not None:
            self.target_lane, self.reverse = self.carry["home"], False
            self.record["lane_changes"].append({"k": self.k, "from": self.carry["into"], "to": self.carry["home"],
                                                "side": "back"})

    def carry_side(self):
        return "opp" if self.carry is not None else None

    def lights(self):
        return {}

    @property
    def k(self):
        return int(self.ego["k"]) if getattr(self, "ego", None) else self.k0

    def _limit(self):
        ln = self.lanemap.lanes.get(self.ego_lane)
        return float(ln.speed) if ln is not None and ln.speed else 13.9

    def _setpoints(self):
        sys.path.insert(0, str(ROAD / "planner"))
        import iface
        kind = (self.cmd or ("keep",))[0]
        stop = None
        if kind in ("yield", "inch") and self.gap is not None and self.gap >= 0:
            stop = self._along(self.gap + 0.5 * self.EGO_L)
        brake_b = abs(self.accel) if (kind == "brake" and self.accel is not None) else None
        sp = iface.setpoints_of(self.cmd, self.ego["v"], self._limit(), stop_xy=stop, brake_bound=brake_b,
                                beat_s=BEAT_S, own=self.ego_lane, sibling=self.target_lane)
        return sp

    def _along(self, d):
        """The CommonRoad point D metres ahead of the ego's centre along its lane (the stop line for a yield)."""
        if self.ego_lane not in self.lanes.lanes:
            return None
        line = self.lanes.centreline(self.ego_lane, self.ego_s - 0.5 * self.EGO_L, ahead=d + 1.0, route=self.ego_route)
        if not line:
            return None
        acc, last = 0.0, line[0]
        for p in line[1:]:
            seg = math.hypot(p[0] - last[0], p[1] - last[1])
            if acc + seg >= d:
                u = (d - acc) / max(seg, 1e-9)
                return self.to_cr(last[0] + u * (p[0] - last[0]), last[1] + u * (p[1] - last[1]))
            acc, last = acc + seg, p
        return self.to_cr(*line[-1])

    def _path_for(self, lane, reverse, ahead=None):
        if lane not in self.lanes.lanes:
            return None
        s0, _, _, _ = self.lanes.project(lane, *self.to_net(self.ego["x"], self.ego["y"]))
        line = self.lanes.centreline(lane, max(0.0, s0 - 5.0) if not reverse else s0 + 5.0, reverse=reverse,
                                     route=self.ego_route, ahead=ahead or PATH_AHEAD_M)
        return [list(self.to_cr(*p)) for p in line] if len(line) >= 2 else None

    def _goal_on(self, path):
        """The first goal polygon's centre projected on PATH (its s) when it lies within 4 m of it, and the window."""
        import reference
        g = self.goals[0] if self.goals else {}
        polys, w = g.get("polygons") or [], g.get("time")
        if not polys:
            return None, None
        cx = sum(p[0] for p in polys[0]) / len(polys[0])
        cy = sum(p[1] for p in polys[0]) / len(polys[0])
        s, off = reference.project(path, (cx, cy))
        return (s if math.hypot(*off) <= 4.0 else None), w

    def _replan(self, sp):
        """A solve over the remaining window: the reference (reference.build) along the lane the family's command names
        (the route lane, the sibling of a change, the oncoming lane of a pass), its speed the setpoints'."""
        sys.path.insert(0, str(ROAD / "planner"))
        import reference
        lane = self.target_lane or self.ego_lane
        t0 = time.perf_counter()
        last = max([int(g["time"][1]) for g in self.goals if g.get("time")] or [self.k + MIN_HORIZON])
        n = max(MIN_HORIZON, last - self.k) + 1
        reach = n * self.dt * max(self.ego["v"], self._limit()) + 50.0
        path = self._path_for(lane, self.reverse and lane == self.target_lane, ahead=max(PATH_AHEAD_M, reach))
        r = {"ok": False, "status": "no path"}
        if path:
            stop_s = reference.project(path, sp.stop_xy)[0] if sp.stop_xy is not None else None
            goal_s, w = self._goal_on(path)
            window = None if w is None else ((w[0] - self.k) * self.dt, (w[1] - self.k) * self.dt)
            target = sp.desired_v if sp.desired_v is not None else self._limit()
            ref = reference.build(path, (self.ego["x"], self.ego["y"]), self.ego["v"], self.dt, n, target,
                                  stop_s=stop_s, goal_s=goal_s, window=window)
            if ref:
                r = self._ask({"op": "plan", "x0": [self.ego["x"], self.ego["y"], self.ego["v"], self.ego["phi"]],
                               "k": self.k, "ref": [list(p) for p in ref]})
                self.record["steps"][-1].update(v_ref=round(ref[min(1, len(ref) - 1)][2], 3))
        self.record["solves"].append({"k": self.k, "stage": "plan", "status": r.get("status"), "success": bool(r.get("ok")),
                                      "iterations": r.get("iterations"), "t_wall_s": round(time.perf_counter() - t0, 3),
                                      "ms": r.get("ms"), "lane": lane, "n": n})
        if r.get("ok") and len(r.get("states") or []) > 1:
            self.plan, self.plan_i = r["states"], 1
            if self.record["horizon"]["steps"] is None:
                self.record["horizon"].update(steps=n - 1, seconds=round((n - 1) * self.dt, 2))
        else:
            self.plan_failures += 1
            self.plan, self.plan_i = [], 0

    def step(self):
        """One step: the first call only presents the ego at its initial state (the episode's start); after it, the ego
        follows the plan (replanned as the setpoints ask), clipped by the cap, the obstacles move to their recorded pose."""
        if not self.started:
            self.started = True
            self._log_step(None)
            return True
        if self.ego_done:
            return False
        sp = self._setpoints()
        key = (sp.desired_v and round(sp.desired_v, 1), sp.stop_xy and tuple(round(c, 1) for c in sp.stop_xy),
               self.target_lane, self.reverse)
        due = (not self.plan or self.plan_i >= len(self.plan) or key != self.last_set
               or (self.tick - (self.last_plan_tick or 0)) >= REPLAN)
        if due:
            self._replan(sp)
            self.last_plan_tick, self.last_set = self.tick, key
        prev = dict(self.ego)
        if self.plan and self.plan_i < len(self.plan):
            nxt = dict(self.plan[self.plan_i])
            self.plan_i += 1
        else:                                           # no plan: the ego brakes on its heading (the shield's stop)
            v = max(0.0, prev["v"] - 4.0 * self.dt)
            nxt = dict(prev, k=prev["k"] + 1, v=v, a=-4.0 if prev["v"] > 0 else 0.0,
                       x=prev["x"] + v * self.dt * math.cos(prev["phi"]), y=prev["y"] + v * self.dt * math.sin(prev["phi"]))
        cap = self.cap
        if cap is not None and nxt["v"] > prev["v"] + cap * self.dt + 1e-9:
            v = max(0.0, prev["v"] + cap * self.dt)    # the restrictor's cap after the planner: shorten the step
            ds_plan = math.hypot(nxt["x"] - prev["x"], nxt["y"] - prev["y"])
            ds = 0.5 * (prev["v"] + v) * self.dt
            u = ds / ds_plan if ds_plan > 1e-9 else 0.0
            nxt.update(v=v, a=(v - prev["v"]) / self.dt, x=prev["x"] + u * (nxt["x"] - prev["x"]),
                       y=prev["y"] + u * (nxt["y"] - prev["y"]))
            self.plan = []                              # the plan is no longer where the ego is: replan next step
        nxt["k"] = prev["k"] + 1
        self.ego = nxt
        self.tick += 1
        self.t = round(self.tick * self.dt, 6)
        self.ego_lane, self.ego_s, self.ego_lat = self._match_ego()
        if self.carry is not None:
            if self.target_lane == self.carry["home"] and self.ego_lane == self.carry["home"]:
                self.carry = None
            elif self.carry["home"] in self.lanes.lanes:
                hs, _, _, _ = self.lanes.project(self.carry["home"], *self.to_net(self.ego["x"], self.ego["y"]))
                self.carry["s"] = hs
        if self.target_lane is not None and self.ego_lane == self.target_lane and self.carry is None:
            self.target_lane, self.ref_lane = None, None
            self.ego_route = self._route(self.ego_lane)
        self._contacts()
        self._goal()
        self._log_step(sp)
        last = max([int(g["time"][1]) for g in self.goals if g.get("time")] or [self.k0 + 200])
        if self.goal_t is not None or self.ego["k"] >= last:
            self.ego_done = True
        return not self.ego_done or self.goal_t is not None

    # ── truth, contacts, goal ──
    def _present(self, o, k):
        tr = o.get("trajectory") or []
        if not tr:
            return None
        if o.get("role") == "static" or len(tr) == 1:
            return tr[0]
        return cr_world.at(tr, k)

    def truth(self):
        out = {}
        e = self.ego
        nx, ny = self.to_net(e["x"], e["y"])
        out[EGO] = {"x": nx, "y": ny, "z": 0.0, "heading": e["phi"], "length": self.EGO_L, "width": self.EGO_W,
                    "speed": e["v"], "lane": self.ego_lane, "s": self.ego_s, "signals": 0, "lat": self.ego_lat,
                    "vclass": "passenger", "index": self.conn.vehicle.getLaneIndex(EGO), "type": "ego",
                    "route": list(self.ego_route)}
        if self.carry is not None:
            out[EGO]["carry"] = {"home": self.carry["home"], "s": self.carry["s"]}
        for o in self.obstacles:
            p = self._present(o, self.k)
            if p is None:
                continue
            x, y = self.to_net(p["x"], p["y"])
            L, W = float(o.get("length") or 4.5), float(o.get("width") or 1.8)
            fx, fy = self._front(x, y, p.get("theta", 0.0), L)
            m = self.lanes.match(fx, fy, p.get("theta"), prefer=None) or self.lanes.match(fx, fy, None)
            if m is None:
                continue
            vclass = cr_world.VCLASS.get(o.get("type"), "passenger")
            out["cr%s" % o["id"]] = {"x": x, "y": y, "z": 0.0, "heading": p.get("theta", 0.0), "length": L, "width": W,
                                     "speed": float(p.get("v") or 0.0), "lane": m[0], "s": m[1], "signals": 0,
                                     "lat": m[2], "vclass": "pedestrian" if vclass == "pedestrian" else vclass,
                                     "index": self.lanemap.lanes[m[0]].index, "type": o.get("type")}
        return out

    def _contacts(self):
        e = self.ego
        eb = cr_world.box(e["x"], e["y"], e["phi"], self.EGO_L, self.EGO_W)
        for o in self.obstacles:
            p = self._present(o, self.k)
            if p is None:
                continue
            ob = cr_world.box(p["x"], p["y"], p.get("theta", 0.0), float(o.get("length") or 4.5),
                              float(o.get("width") or 1.8))
            if cr_world.overlap(eb, ob):
                vid = "cr%s" % o["id"]
                if not any(c["victim"] == vid and self.t - c["t"] < 1.0 for c in self.collisions):
                    c = {"t": self.t, "collider": EGO, "victim": vid, "type": "box", "xy": [round(e["x"], 2), round(e["y"], 2)]}
                    self.collisions.append(c)
                    self.contacts.append({"t": self.t, "obstacle": o["id"]})
                    self.ego_collisions += 1

    def _goal(self):
        e = self.ego
        for g in self.goals:
            w = g.get("time")
            if w and not (w[0] <= e["k"] <= w[1]):
                continue
            polys = g.get("polygons") or []
            if polys and not any(_inside((e["x"], e["y"]), poly) for poly in polys):
                continue
            if not polys and not g.get("lanelets"):
                if self.goal_t is None:
                    self.goal_t = self.t
                return
            if g.get("lanelets") and not polys:
                lid = self._lanelet()
                if lid not in [int(x) for x in g["lanelets"]]:
                    continue
            if self.goal_t is None:
                self.goal_t = self.t
            return

    def _lanelet(self):
        return int(self.ego_lane) if self.ego_lane is not None and str(self.ego_lane).isdigit() else None

    def _log_step(self, sp):
        e = self.ego
        self.record["steps"].append({"k": int(e["k"]), "lanelet": self._lanelet(), "lane": self.ego_lane,
                                     "x_ref": None, "y_ref": None, "v_ref": None if sp is None else sp.desired_v,
                                     "phi_ref": None, "stop_xy": None if sp is None else sp.stop_xy,
                                     "command": None if self.cmd is None else list(self.cmd),
                                     "cap": self.cap})
        self.record["trajectory"].append({k: (round(float(e[k]), 6) if isinstance(e.get(k), (int, float)) else e.get(k))
                                          for k in ("k", "x", "y", "v", "phi", "delta", "a")})
