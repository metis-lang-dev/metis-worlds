"""sumo_host.py — the road on SUMO (road-world s-e812715d step 4): `Loop`, a world in RoadWorld's interface (the
exerciser's, road_world.py), so road_host.RoadHost serves both: the same members, readings latched at each member's
clock, `now`, commands and restrictor; only the world differs, SUMO's truth seen through the sensing model.
road_host picks it by the run spec (`"world": "sumo"`, with scenario, seed, sensor, vehicles, work).

The interface (RoadWorld's): observe() → (facts, roles, fold, states) once a tick · command(cmd, life) · step() ·
tick, t, log (a row a step: t, s, v, a, lane, cmd, resp) · arrived() · summary().

The episode begins with the ego on the road: SUMO is stepped until the ego is inserted (its depart; not ticks), then
perceived and projected once. One tick (dt 0.1 s, the SUMO step; road_host's responder steps it):
  1. RESTRICT   the held command (held its issuer's period in responder ticks) through restrict.restrict against
                the fold of the last projection → sumo_world.control(accel, lane)
  2. STEP       one SUMO step (sumo_world.step: the collisions, the ego in or out)
  3. PERCEIVE   the truth through the sensor into the belief (sumo_perceive.Perception: RoadMap.cycle, the movers)
  4. PROJECT    road_facts.facts over the BELIEF's movers (never the truth): LaneMap.roles, the situation layer
                (one memory across ticks), the fold, the facts — every road host's projection, no other
  5. ACCOUNT    on the TRUTH: SUMO's collisions with the ego; the RSS violations by the exerciser's definitions
                (road_world: the applied acceleration above the bound of the truth's fold when it was decided, or a
                pair the ego's own act made dangerous); the latency from a truth pair's first dangerous tick to the first braking applied;
                the ms of each stage."""
import os
import time

import restrict
import road_facts
from semantic_world import net as netmod
from semantic_world.lane import Mover, dynamics_for
from semantic_world.sensing import Sensor
from semantic_world.situation import Situation

from sumo_perceive import Perception
from sumo_world import DESTS, EGO, SumoWorld



class Loop:
    """The world one hierarchy shares: the SUMO process, the perception, the situation memory, the held command, the
    last projection and the accounting."""

    def __init__(self, level, work=None, traci=None):
        import tempfile
        work = work or level.get("work") or tempfile.mkdtemp(prefix="road-sumo-")
        args = dict(level.get("scenario_args", {}))
        if "vehicles" in level:
            args["n"] = int(level["vehicles"])
        self.world = SumoWorld(level.get("scenario", "straight"), work, seed=int(level.get("seed", 1)), traci=traci,
                               **args)
        self.lanemap = netmod.load_net(self.world.net).lanemap()
        sen = level.get("sensor", {})
        self.perc = Perception(self.lanemap, Sensor(range=sen.get("range", 60.0), miss=sen.get("miss", 0.0),
                                                    seed=int(level.get("seed", 1))), dt=self.world.dt)
        self.sit, self.truth_sit = Situation(), Situation()
        self.cmd, self.life = ("keep", None), 0
        self.changing = None                          # (side, source lane index, ticks left)
        self.proj = {"binding": {}, "facts": {"now": 1}, "fold": None, "states": [], "ego": None}
        self.tick, self.t, self.warmup = 0, 0.0, 0
        self.level_dest = level.get("dest", DESTS.get(level.get("scenario", "straight")))
        self.violations, self.restricted, self.latency, self.ms = [], 0, [], []
        self.danger_since = None                      # the tick a truth pair first turned dangerous (latency)
        self.prev_truth = {}
        self.log = []
        self.world.start()
        while not self.world.step():                  # the ego's depart: the episode begins with it on the road
            self.warmup += 1
            if self.warmup > int(level.get("max_warmup", 600)):
                raise RuntimeError("sumo: the ego was not inserted in %d steps" % self.warmup)
        truth, _, ego, lights, _ = self.perceive_project()
        self.account(truth, ego, None, lights)       # tick 0's truth: a danger there starts the latency's clock

    # ── RoadWorld's interface ──
    def observe(self):
        p = self.proj
        return p["facts"], p["binding"], p["fold"] or {"resp_lon": "none"}, p["states"]

    def command(self, cmd, life=1):
        self.cmd, self.life = cmd, int(life)

    def arrived(self):
        """The exerciser's meaning: the ego's s at the destination (else, with none, the ego off the net)."""
        ego = self.proj.get("ego")
        if self.level_dest is not None and ego is not None and ego.s >= self.level_dest:
            return True
        return self.world.ego_done

    def perceive_project(self):
        truth = self.world.truth()
        movers, ego = self.perc.step(truth, EGO)
        t3 = time.perf_counter()
        lights = self.world.lights()
        f, binding, fold, states = road_facts.facts(self.lanemap, ego, ego.dyn.vmax, movers, self.sit,
                                                    changing=self.changing[0] if self.changing else None,
                                                    dest=self.level_dest, lights=lights,
                                                    speeds={m.id: m.dyn.vmax for m in movers})
        self.proj = {"binding": binding, "facts": f, "fold": fold, "states": states, "ego": ego}
        self.prev_truth = truth
        return truth, movers, ego, lights, t3

    # ── 1. restrict ──
    def restrict(self, ego):
        fold = self.proj["fold"] or {"resp_lon": "none"}
        cmd = self.cmd if self.life > 0 else ("keep", None)
        d, v = ego.dyn, ego.dyn.vmax
        gap = self.yield_gap(ego) if cmd[0] == "yield" else None
        a, lane = restrict.restrict(cmd, fold, d, v, changing=self.changing[0] if self.changing else None, yield_gap=gap)
        if restrict.capped(cmd, fold, d, v, gap):
            self.restricted += 1
        idx, target = self.world.conn.vehicle.getLaneIndex(EGO), None
        if lane == "abort" and self.changing:
            target, self.changing = self.changing[1], None
        elif lane in ("left", "right") and getattr(self.lanemap.lanes[ego.lane], lane):
            target = idx + (1 if lane == "left" else -1)             # SUMO's index 0 is the rightmost
            self.changing = (lane, idx, int(round(restrict.CHANGE_S / self.world.dt)))
        self.world.control(a, target)
        if self.life > 0:
            self.life -= 1
        if self.changing:
            self.changing = (self.changing[0], self.changing[1], self.changing[2] - 1) if self.changing[2] > 1 else None
        return a, lane, cmd

    def yield_gap(self, ego):
        """The ego's front to the next zone's line on its way (LaneMap.nearest_zone's d_enter; restrict keeps min_dist)."""
        z = self.lanemap.nearest_zone(ego.route or [ego.lane], ego.s, length=ego.length)
        return z[2] if z else None

    # ── one tick ──
    def step(self):
        """One responder tick. → whether the ego is still on the road."""
        t0 = time.perf_counter()
        applied = None
        if self.proj.get("ego") is not None and not self.world.ego_done:
            applied = self.restrict(self.proj["ego"])
        t1 = time.perf_counter()
        on = self.world.step()
        t2 = time.perf_counter()
        self.tick = self.tick + 1
        self.t = round(self.tick * self.world.dt, 6)    # the episode's clock (SUMO's own counts the ego's depart)
        if not on:
            self.prev_truth, self.proj["ego"] = {}, None
            return False
        truth, movers, ego, lights, t3 = self.perceive_project()
        fold = self.proj["fold"]
        binding = self.proj["binding"]
        t4 = time.perf_counter()
        self.account(truth, ego, applied, lights)
        t5 = time.perf_counter()
        self.ms.append({"restrict": t1 - t0, "sumo": t2 - t1, "perceive": t3 - t2, "project": t4 - t3, "account": t5 - t4,
                        "vehicles": len(truth)})
        self.log.append({"tick": self.tick, "t": self.t, "sumo_t": self.world.t, "s": round(ego.s, 2), "v": round(ego.dyn.vmax, 2),
                         "lane": ego.lane, "a": None if applied is None else round(applied[0], 2),
                         "cmd": None if applied is None else list(applied[2]), "resp": fold["resp_lon"],
                         "seen": len(self.perc.last["seen"]), "tracks": len(movers), "binding": binding})
        return True

    def truth_movers(self, truth):
        out = []
        for k, p in truth.items():
            if k == EGO or p["lane"] not in self.lanemap.lanes:
                continue
            out.append(Mover(k, p["lane"], p["s"], dynamics_for(p["vclass"], v=p["speed"], lane=self.lanemap.lanes[p["lane"]]),
                             length=p["length"], width=p["width"], vclass=p["vclass"]))
        return out

    def account(self, truth, ego, applied, lights):
        """The RSS accounting on the truth (road_world's definitions; SUMO counts the collisions)."""
        others = self.truth_movers(truth)
        pairs = {p.id: p for p in self.lanemap.pairs(ego, others, lights=lights)}
        states = self.truth_sit.check(list(pairs.values()))
        fold = Situation.fold(states, ego.dyn)
        before = getattr(self, "_truth_fold", None)       # the truth as it stood when the command was decided
        if applied is not None and before is not None:
            a, lane, _ = applied
            hi = restrict.bound(before, ego.dyn)
            if a > hi + 1e-9:
                self.violations.append({"tick": self.tick, "what": "accel above the truth response", "a": a, "max": hi,
                                        "dangerous": before["dangerous"]})
        self._truth_fold = fold
        prev = getattr(self, "_prev_states", {})
        for s in states:
            p = prev.get(s.id)
            if not s.dangerous or p is None or p.dangerous or applied is None:
                continue
            blame = None
            a, lane, _ = applied
            if lane in ("left", "right") and s.type in ("same_dir", "opp_dir"):
                blame = "a lane change into it"
            elif s.type == "same_dir" and pairs[s.id].lon == "in_front" and a > 0:
                blame = "accelerated as the rear one"
            if blame:
                self.violations.append({"tick": self.tick, "what": blame, "pair": s.id})
        self._prev_states = {s.id: s for s in states}
        bad = [s for s in states if s.dangerous and s.resp_lon != "none"]
        if bad and self.danger_since is None:
            self.danger_since = self.tick
        if self.danger_since is not None and applied is not None and applied[0] <= -(ego.dyn.brake_min or 0.0) + 1e-9:
            self.latency.append(self.tick - self.danger_since)
            self.danger_since = None
        elif not bad:
            self.danger_since = None

    def summary(self):
        w = self.world
        def mean(k):
            xs = [m[k] for m in self.ms]
            return round(1000 * sum(xs) / len(xs), 3) if xs else None
        ego = self.proj.get("ego")
        return {"seed": w.seed, "ticks": self.tick, "t": self.t, "sumo_t": w.t, "arrived": self.arrived(),
                "s": round(ego.s, 1) if ego is not None else None, "dest": self.level_dest, "ego_done": w.ego_done, "collisions": w.ego_collisions,
                "all_collisions": len(w.collisions), "violations": len(self.violations), "restricted": self.restricted,
                "latency_ticks": self.latency, "first": self.violations[:3],
                "ms": {k: mean(k) for k in ("restrict", "sumo", "perceive", "project", "account")},
                "vehicles_max": max((m["vehicles"] for m in self.ms), default=0)}

    def close(self):
        self.world.close()
