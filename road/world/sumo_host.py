"""sumo_host.py — the road on SUMO as a catalog host (road-world s-e812715d step 4), the shape of road_host.py (the
exerciser's) and mh_host.py: the same roles, facts and commands, the world SUMO's truth seen through the sensing model.

One responder tick (dt 0.1 s, the SUMO step), stepped by the host whose level.json says `steps: true` (the
responder's; a hierarchy's other hosts share the world by `shared`, as mh_host's SHARED, and read the latest):
  1. RESTRICT   the held command (restrict.command of the fired rule, held its issuer's period in responder ticks)
                through restrict.restrict against the fold of the last projection → sumo_world.control(accel, lane)
  2. STEP       one SUMO step (sumo_world.step: the collisions, the ego in or out)
  3. PERCEIVE   the truth through the sensor into the belief (sumo_perceive.Perception: RoadMap.cycle, the movers)
  4. PROJECT    LaneMap.roles / zone_roles over the BELIEF's movers (never the truth), the pairs with their roles,
                Situation.check (one memory across ticks), the fold, the facts (`facts`: the one adapter)
  5. SYNC       only the owned preds (the role facts and `now`) retracted / asserted; the members' tokens never
  6. ACCOUNT    on the TRUTH: SUMO's collisions with the ego; the RSS violations by the exerciser's definitions
                (road_world: the applied acceleration above the truth fold's bound, or a pair the ego's own act
                made dangerous); the latency from a truth pair's first dangerous tick to the first braking applied;
                the ms of each stage.

The facts the domains read come from ONE adapter, `facts()`: road_facts.facts, the projection every road host makes
(opus's, beside restrict.py; the architect's ruling: no host writes its own), the roles through LaneMap.roles.

    make(case, package_dir) -> SumoHost   (level.json: scenario, seed, work, sensor {range, miss}, steps, shared,
                                           period, observe, max_ticks)"""
import json
import os
import time

import restrict
import road_facts
from semantic_world import net as netmod
from semantic_world.lane import Mover, dynamics_for
from semantic_world.sensing import Sensor
from semantic_world.situation import Situation

from sumo_perceive import Perception
from sumo_world import EGO, SumoWorld

OWNED = {"type", "safe_long", "safe_lat", "dangerous", "safe_before", "resp", "safe_lat_left", "safe_lat_right",
         "resp_lat", "xing_case", "xing_before", "resp_lon", "resp_lat_left", "resp_lat_right", "adjacent", "changing",
         "below_limit", "lead_slow", "at_dest", "zone_at", "zprio", "can_stop", "zfree", "zclear", "holder", "share",
         "conflict", "turn", "crossing", "now"}
SHARED = {}                    # a hierarchy's one SUMO: {key: Loop}


def facts(lm, ego, movers, sit, changing=None, lights=None, turn=None, dest=None):
    """THE ADAPTER: road_facts.facts (opus's, every road host's) over the belief's movers. → (facts, roles, fold)."""
    out, roles, fold, _ = road_facts.facts(lm, ego, ego.dyn.vmax, movers, sit, changing=changing, dest=dest, turn=turn,
                                           lights=lights)
    return out, roles, fold


class Loop:
    """The world one hierarchy shares: the SUMO process, the perception, the situation memory, the held command, the
    last projection and the accounting."""

    def __init__(self, level, work, traci=None):
        self.world = SumoWorld(level.get("scenario", "straight"), work, seed=int(level.get("seed", 1)), traci=traci,
                               **level.get("scenario_args", {}))
        self.lanemap = netmod.load_net(self.world.net).lanemap()
        sen = level.get("sensor", {})
        self.perc = Perception(self.lanemap, Sensor(range=sen.get("range", 60.0), miss=sen.get("miss", 0.0),
                                                    seed=int(level.get("seed", 1))), dt=self.world.dt)
        self.sit, self.truth_sit = Situation(), Situation()
        self.cmd, self.life = ("keep", None), 0
        self.changing = None                          # (side, source lane index, ticks left)
        self.proj = {"binding": {}, "facts": {"now": 1}, "fold": None, "states": []}
        self.tick = 0
        self.level_dest = level.get("dest")
        self.violations, self.restricted, self.latency, self.ms = [], 0, [], []
        self.danger_since = None                      # the tick a truth pair first turned dangerous (latency)
        self.prev_truth = {}
        self.log = []
        self.world.start()

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
        z = self.lanemap.nearest_zone(ego.route or [ego.lane], ego.s)
        if not z:
            return None
        zone, lane = z[0], z[1]
        d = self.lanemap.ahead(ego.route or [ego.lane], ego.s, lane, zone.lanes[lane][0])
        return d

    # ── 2-6 ──
    def step(self):
        """One responder tick. → whether the episode goes on."""
        t0 = time.perf_counter()
        ego_t = self.prev_truth.get(EGO)
        applied = None
        if ego_t is not None and self.proj.get("ego") is not None:
            applied = self.restrict(self.proj["ego"])
        t1 = time.perf_counter()
        on = self.world.step()
        t2 = time.perf_counter()
        self.tick += 1
        if not on:
            self.prev_truth = {}
            return not self.world.ego_done
        truth = self.world.truth()
        movers, ego = self.perc.step(truth, EGO)
        t3 = time.perf_counter()
        lights = self.world.lights()
        f, binding, fold = facts(self.lanemap, ego, movers, self.sit, changing=self.changing[0] if self.changing else None,
                                 lights=lights, dest=self.level_dest)
        self.proj = {"binding": binding, "facts": f, "fold": fold, "ego": ego}
        t4 = time.perf_counter()
        self.account(truth, ego, applied, lights)
        t5 = time.perf_counter()
        self.ms.append({"restrict": t1 - t0, "sumo": t2 - t1, "perceive": t3 - t2, "project": t4 - t3, "account": t5 - t4,
                        "vehicles": len(truth)})
        self.prev_truth = truth
        self.log.append({"tick": self.tick, "t": self.world.t, "s": round(ego.s, 2), "v": round(ego.dyn.vmax, 2),
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
        if applied is not None:
            a, lane, _ = applied
            hi = restrict.bound(fold, ego.dyn)
            if a > hi + 1e-9:
                self.violations.append({"tick": self.tick, "what": "accel above the truth response", "a": a, "max": hi,
                                        "dangerous": fold["dangerous"]})
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
        return {"seed": w.seed, "ticks": self.tick, "t": w.t, "ego_done": w.ego_done, "collisions": w.ego_collisions,
                "all_collisions": len(w.collisions), "violations": len(self.violations), "restricted": self.restricted,
                "latency_ticks": self.latency, "first": self.violations[:3],
                "ms": {k: mean(k) for k in ("restrict", "sumo", "perceive", "project", "account")},
                "vehicles_max": max((m["vehicles"] for m in self.ms), default=0)}

    def close(self):
        self.world.close()


class SumoHost:
    """bind(reg) · tick(counts) -> do-lines | None · on_event(name, args) · observe(counts) -> {atom: n} · pending()
    · ports() · snapshot() / restore(snap) (no replay: SUMO's episode is not reset mid-run)."""

    def __init__(self, package_dir, case=None):
        self.package_dir, self.case = package_dir, case
        self.level = json.load(open(os.path.join(package_dir, "level.json")))
        self.key = self.level.get("shared") or package_dir
        self.steps = bool(self.level.get("steps", True))
        self.period = int(self.level.get("period", 1))
        self.max_ticks = int(self.level.get("max_ticks", 3000))
        self.observed = set(self.level["observe"]) if "observe" in self.level else None
        if self.key not in SHARED:
            SHARED[self.key] = Loop(self.level, self.level.get("work") or os.path.join(package_dir, ".run", "sumo"))
        self.loop = SHARED[self.key]
        self.seen_tick, self.done = -1, False

    def bind(self, reg):
        pass

    def pending(self):
        return self.loop.tick != self.seen_tick

    def reading(self):
        f = self.loop.proj["facts"]
        keep = self.observed if self.observed is not None else OWNED
        return {a: 1 for a in f if a.split("(")[0] in keep}

    def observe(self, counts):
        return {} if self.done else self.reading()

    def tick(self, counts):
        if self.done:
            return None
        if self.steps:
            go = self.loop.step() and self.loop.tick < self.max_ticks
            if not go:
                self.done = True
                return None
        self.seen_tick = self.loop.tick
        return self.sync(counts)

    def sync(self, counts):
        dos, reading = [], self.reading()
        for a, n in sorted(reading.items()):
            if n > counts.get(a, 0):
                dos.append("+%s %d" % (a, n - counts.get(a, 0)))
        for a, have in sorted(counts.items()):
            if have > 0 and a not in reading and a.split("(")[0] in OWNED:
                dos.append("-%s %d" % (a, have))
        return dos

    def on_event(self, name, args):
        cmd = restrict.command(name)
        if cmd is not None:
            self.loop.cmd, self.loop.life = cmd, self.period

    def speak(self, text, binding=None):
        return text

    def world(self, lines):
        raise ValueError("world lines: SUMO is the world; choose another scenario or seed")

    def ports(self):
        return {"level": {"scenario": self.level.get("scenario"), "seed": self.loop.world.seed, "tick": self.loop.tick,
                          "done": self.done}, "observed": sorted(OWNED), "commands": list(restrict.KINDS)}

    def snapshot(self):
        return {"tick": self.loop.tick}

    def restore(self, snap):
        pass

    def summary(self):
        return self.loop.summary()

    def close(self):
        self.loop.close()
        SHARED.pop(self.key, None)


def make(case=None, package_dir=None):
    return SumoHost(package_dir or os.getcwd(), case)
