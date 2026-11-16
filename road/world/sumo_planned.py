"""sumo_planned.py — the SUMO road world with a TRAJECTORY LEVEL (metis-plugin s-df4ff191 step 5; the toolchains brief's
planner row): the ego follows perotheia-packages/planner's plan (the C++ lane plan + OCP, in process through
road/planner/trajplan.py), the vehicle stack's planner, instead of being commanded speeds and lane changes directly.

    run spec: {"world": "sumo", "traj": "trajplan", ...}   road_host.new_world → sumo_host.Loop(run, world=PlannedSumoWorld)
    road_tree.py SCENARIO SEED --world sumo --traj trajplan

What changes against SumoWorld, and what not:
- the family, the Loop, perceive / project / restrict / account: UNCHANGED.
- the family's fired command rules (road_host.on_event hands each to `fired`) become contracts' BehaviourCmd exactly as
  the vehicle stack decides it: road/planner/commander.py, the port of RoadDomain's Commander (keep_limit / accel → KEEP
  at the pace, keep_gap → KEEP at the present speed, keep_lead → FOLLOW the lead, brake_lon → STOP_AT at the stopping
  distance under R, yield_* → STOP_AT / YIELD at the zone line, change[D] → CHANGE_*, change_oncoming → PASS_OPPOSITE;
  the holder of the controls decides, a member's last command stands, a change holds its seq until the planner says it
  ended). The planner carries out a change or a pass itself: the restrictor's lane / carry outputs are not executed.
- RSS stays the HOST'S: the plan's next state is CLIPPED by the restrictor's bound (v ≤ v + bound·dt; a held brake(R)
  by its restricted deceleration too), outside the planner, as on cr_native.
- each step the planner plans from the ego's truth (its centre, speed; the previous step's a and steering) against every
  other vehicle and person of the truth (boxes at their poses and speeds), over the net's lane map (the Loop's LaneMap
  written as the planner's: trajplan.lanes_file) along the ego's SUMO route (its edges' lanes as waypoints); SUMO puts
  the ego at the plan's state one step ahead: moveToXY (the front bumper; keepRoute 1 on its route, 2 while a
  PASS_OPPOSITE runs, the route restored after), setSpeed + setPreviousSpeed (the speed the step reports).
- the first ticks after the insertion, while the body still reaches back past the lane's start: SumoWorld's control.
- no plan (the planner refuses): the ego brakes at 4 m/s² on its heading (the shield's stop), counted as a failure.
- the record: ROAD_PLANNED_LOG (default WORK/planned.jsonl), a row per step: the held command, the BehaviourCmd, the
  plan's stats; summary() → the Loop's summary["planned"] (plans, failures, commands, ms p50 / max)."""
import json
import math
import os
import sys
import time
from pathlib import Path

from sumo_world import EGO, SumoWorld, sumo_angle

HERE = Path(__file__).resolve().parent
ROAD = HERE.parent
sys.path.insert(0, str(ROAD / "planner"))
import commander as cm  # noqa: E402
import trajplan as tp  # noqa: E402

VEHICLE = {"wheelbase": 2.9, "b": 1.45}      # the ego's centre → rear axle: half the wheelbase (a SUMO passenger car)
BRAKE_NO_PLAN = 4.0


class PlannedSumoWorld(SumoWorld):
    def __init__(self, scenario, work, seed=1, **kw):
        super().__init__(scenario, work, seed=seed, **kw)
        self.work = Path(work)
        self.traj = None
        self.cmdr = None
        self.loop = None
        self.holder = None                                     # the member whose command the Loop holds
        self.held = (("keep", None), None, None, None)          # (restrict's cmd, accel, bound, gap) from the Loop
        self.ids = {}                                          # SUMO id → the planner's obstacle id
        self.status = {"cmd_seq": 0, "change": cm.CHANGE_NONE}
        self.route_saved = None
        self.state = {"a": 0.0, "delta": 0.0}
        self.last_truth = None
        self.rows, self.ms, self.failures, self.sent = [], [], 0, 0

    # ── the planner ──
    def _start_planner(self, e):
        import sumo_host
        lanes = self.work / "trajplan.lanes"
        tp.lanes_file(sumo_host.lanemap_of(self.net), lanes)
        veh = dict(VEHICLE, length=e["length"], width=e["width"])
        params = {"replan_tol": 0, "replan_lon": 0, "replan_dv": 0}    # the ego IS the plan's state (the clip aside)
        params.update({k[len("TRAJPLAN_"):].lower(): x for k, x in os.environ.items()
                       if k.startswith("TRAJPLAN_") and k != "TRAJPLAN_LIB"})
        self.traj = tp.Trajplan(lanes, veh, **params)
        self.cmdr = self.cmdr or cm.Commander(ego_front=0.5 * e["length"])
        self.cmdr.ego_front = 0.5 * e["length"]                # the truth's pose is the centre
        c = self.conn
        pts = []
        for edge in c.vehicle.getRoute(EGO):                   # the route: the middle of each edge's rightmost lane
            try:
                shape = c.lane.getShape("%s_0" % edge)
            except Exception:
                continue
            if len(shape) >= 2:
                m = len(shape) // 2
                pts.append((0.5 * (shape[m - 1][0] + shape[m][0]), 0.5 * (shape[m - 1][1] + shape[m][1])))
        self.traj.route([(e["x"], e["y"])] + pts)

    def _id(self, sid):
        if sid not in self.ids:
            self.ids[sid] = len(self.ids) + 1
        return self.ids[sid]

    # ── the Loop's lines ──
    def truth(self):
        self.last_truth = super().truth()
        return self.last_truth

    def fired(self, member, rule, loop):
        """A fired command rule of MEMBER (road_host.on_event), on the Loop's reading now."""
        self.loop = loop
        truth = self.last_truth or super().truth()
        e = truth.get(EGO)
        if e is None:
            return
        if self.cmdr is None:
            self.cmdr = cm.Commander(ego_front=0.5 * e["length"])
        ego = loop.proj.get("ego")
        line = None
        if ego is not None:
            try:
                line = loop.yield_gap(ego)
            except Exception:
                line = None
        binding = loop.proj.get("binding") or {}
        rd = {"cap": loop.pace, "line": line, "stop": None,
              "roles": {r: self._id(v) for r, v in binding.items() if isinstance(v, str)}}
        self.cmdr.fired(member, rule, rd, {"x": e["x"], "y": e["y"], "heading": e["heading"], "speed": e["speed"]})
        if cm.rule_base(rule) not in ("change_home", "drive_away"):
            self.holder = member

    def command(self, cmd, accel=None, bound=None, gap=None):
        self.held = (cmd, accel, bound, gap)

    def carry_start(self, opp):
        pass                                                   # the planner's PASS_OPPOSITE (change_oncoming) carries it

    def carry_back(self):
        pass

    def control(self, accel=None, lane=None):
        if not self.ego_seen or self.ego_done:
            return
        t0 = time.perf_counter()
        v = self.conn.vehicle
        truth = self.last_truth or super().truth()
        e = truth[EGO]
        if self.traj is None and e["s"] < e["length"]:
            # just inserted: its body still reaches back past the lane's start (the planner's reference begins
            # there): the commanded speeds of the plain world until the whole body is on the lane
            return super().control(accel, lane)
        if self.traj is None:
            self._start_planner(e)
        cmd, _, bound, _ = self.held
        holder = self.holder if self.loop is not None and self.loop.life > 0 else None
        bc = self.cmdr.command(holder, self.status) if self.cmdr is not None else None
        if bc is not None and self.traj.command(bc["name"], bc["v_target"], bc["x"], bc["y"], bc["lead_id"],
                                                bc["yield_id"], bc["min_gap"], seq=bc["seq"]):
            self.sent += 1
        passing = bc is not None and bc["kind"] == cm.PASS_OPPOSITE
        obs = [(self._id(k), p["x"], p["y"], p["heading"], p["speed"], p["length"], p["width"], False)
               for k, p in truth.items() if k != EGO]
        self.traj.obstacles(self.t, obs)
        a_in = self.state["a"]
        st, pts = self.traj.plan(self.t, e["x"], e["y"], e["heading"], e["speed"], a_in, self.state["delta"])
        self.status = {"cmd_seq": self.traj.seq, "change": st["change"]}
        self.ms.append(st["ms"])
        if not st["ok"] or len(pts) < 2:
            self.failures += 1
            sp = max(0.0, e["speed"] - BRAKE_NO_PLAN * self.dt)
            h = e["heading"]
            x, y = e["x"] + sp * self.dt * math.cos(h), e["y"] + sp * self.dt * math.sin(h)
            a_now, delta = (-BRAKE_NO_PLAN if e["speed"] > 0 else 0.0), 0.0
        else:
            q = tp.sample(pts, self.dt)
            x, y, h, sp, a_now = q[1], q[2], q[3], max(0.0, q[4]), q[5]
            delta = math.atan(q[6] * VEHICLE["wheelbase"])
            cap = bound
            if (cmd or ("keep",))[0] == "brake" and accel is not None:      # the family's brake: its deceleration
                cap = accel if cap is None else min(cap, accel)
            if cap is not None and sp > e["speed"] + cap * self.dt + 1e-9:     # the restrictor's envelope: clip
                sp2 = max(0.0, e["speed"] + cap * self.dt)
                ds_plan = math.hypot(x - e["x"], y - e["y"])
                u = (0.5 * (e["speed"] + sp2) * self.dt) / ds_plan if ds_plan > 1e-9 else 0.0
                x, y = e["x"] + u * (x - e["x"]), e["y"] + u * (y - e["y"])
                sp, a_now = sp2, (sp2 - e["speed"]) / self.dt
        self.state = {"a": a_now, "delta": delta}
        L = e["length"]
        fx, fy = x + 0.5 * L * math.cos(h), y + 0.5 * L * math.sin(h)      # SUMO's position: the front bumper
        if passing and self.route_saved is None:
            self.route_saved = list(v.getRoute(EGO))
        v.moveToXY(EGO, v.getRoadID(EGO), v.getLaneIndex(EGO), fx, fy, angle=sumo_angle(h),
                   keepRoute=2 if (passing or self.route_saved) else 1)
        v.setSpeed(EGO, sp)                                         # a held setSpeed (the insertion's) would stand
        v.setPreviousSpeed(EGO, sp)
        if self.route_saved and not passing:                        # back from the pass: the route restored
            road = v.getRoadID(EGO)
            if road in self.route_saved:
                v.setRoute(EGO, self.route_saved[self.route_saved.index(road):])
                self.route_saved = None
        self.rows.append({"t": self.t, "cmd": list(cmd) if cmd else None, "holder": holder,
                          "bc": None if bc is None else [bc["name"], bc["seq"], round(bc["v_target"], 2), bc["reason"]],
                          "ms": st["ms"], "it": st["iters"], "limit": st["limit"], "change": st["change"], "ok": st["ok"],
                          "v": round(sp, 2), "v_plan": round(pts[1][4], 2) if len(pts) > 1 else None, "bound": bound,
                          "lead_gap": round(st["lead_gap"], 1), "wall_ms": round(1e3 * (time.perf_counter() - t0), 2),
                          "in": [round(e["speed"], 3), round(a_in, 3)],
                          "prof": [round(pts[i][4], 2) for i in (1, 10, 30, 50) if i < len(pts)]})

    def close(self):
        if self.rows:
            out = os.environ.get("ROAD_PLANNED_LOG") or str(self.work / "planned.jsonl")
            with open(out, "w") as f:
                for r in self.rows:
                    f.write(json.dumps(r) + "\n")
        if self.traj is not None:
            self.traj.close()
            self.traj = None
        super().close()

    def summary(self):
        ms = sorted(self.ms) or [0.0]
        return {"planner": "trajplan", "plans": len(self.ms), "failures": self.failures, "cmds": self.sent,
                "ms_p50": ms[len(ms) // 2], "ms_max": ms[-1]}
