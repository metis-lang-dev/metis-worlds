"""sumo_host.py — the road on SUMO (road-world s-e812715d step 4): `Loop`, a world in RoadWorld's interface (the
exerciser's, road_world.py), so road_host.RoadHost serves both: the same members, readings latched at each member's
clock, `now`, commands and restrictor; only the world differs, SUMO's truth seen through the sensing model.
road_host picks it by the run spec (`"world": "sumo"`, with scenario, seed, sensor, vehicles, work).

The interface (RoadWorld's): observe() → (facts, roles, fold, states) once a tick · command(cmd, life) · step() ·
tick, t, log (a row a step: t, s, v, a, lane, cmd, resp, zone, signal, contact, danger, truth) · arrived() · summary().

The episode begins with the ego on the road: SUMO is stepped until the ego is inserted (its depart; not ticks), then
perceived and projected once. One tick (dt 0.1 s, the SUMO step; road_host's responder steps it):
  1. RESTRICT   the held command (held its issuer's period in responder ticks) through restrict.restrict against
                the fold of the last projection → sumo_world.control(accel, lane)
  2. STEP       one SUMO step (sumo_world.step: the collisions, the ego in or out)
  3. PERCEIVE   the truth through the sensor into the belief (sumo_perceive.Perception: RoadMap.cycle, the movers)
  4. PROJECT    road_facts.facts over the BELIEF's movers (never the truth): LaneMap.roles, the situation layer
                (one memory across ticks), the fold, the facts — every road host's projection, no other
  5. ACCOUNT    on the TRUTH: SUMO's collisions with the ego; the RSS violations by the exerciser's definitions
                (road_world: the applied acceleration above the bound of the truth's fold when it was decided, a lane
                change into a pair it made dangerous, a zone entered without priority unable to stop); beside them
                the OPTIMISTIC accels (a same-direction pair made dangerous by the rear ego's accel: the architect's
                ruling, its own column); the latency from a truth pair's first dangerous tick to the first braking applied;
                the ms of each stage."""
import math
import os
import pickle
import tempfile
import time

import restrict
import road_facts
from semantic_world import net as netmod
from semantic_world.lane import Mover, dynamics_for
from semantic_world.sensing import Sensor
from semantic_world.situation import Situation

from sumo_perceive import Perception
from sumo_world import DESTS, EGO, SumoWorld



CACHE = os.path.join(tempfile.gettempdir(), "metis-road-lanemaps")


def lanemap_of(path):
    """The net's lane map, zones and all: seconds to build on a big town, a fraction of one to read back, so kept on disk until the net or the code that makes it changes. Each run gets
    its own copy."""
    tag = "%s-%d-%d" % (os.path.basename(path), os.stat(path).st_mtime_ns, os.stat(netmod.__file__).st_mtime_ns)
    cached = os.path.join(CACHE, tag + ".pickle")
    try:
        with open(cached, "rb") as f:
            return pickle.load(f)
    except (OSError, EOFError, pickle.UnpicklingError, AttributeError):
        pass
    lanemap = netmod.load_net(path).lanemap()
    os.makedirs(CACHE, exist_ok=True)
    with open(cached + ".part", "wb") as f:
        pickle.dump(lanemap, f, protocol=5)
    os.replace(cached + ".part", cached)
    return lanemap


UNSEEN_DUTY = "unseen, the other's duty"
MATCH_M = 6.0                     # the truth column: a bound track and its body on one lane at most this far apart (m)
CANNOT = ["weather", "rain", "snow", "fog", "night", "animal"]   # the truth's `cannot`: what this world does not hold
LANE_FACTS = ("own_kind", "adjacent", "lane_kind", "side_", "oncoming", "lead_s", "changing", "settled(", "zone_at", "roomy")    # the log's lane facts (the passes')


def others_duty(dangerous, states, seen):
    """A response the truth asked and the ego could not know: every dangerous pair one the ego has the way over (xing_ego_prio), its other not seen. The yielder's violation by the
    ruling (the holder has no duty to a hidden side road): its own class, listed, never dropped. STATES {pair id: State} and SEEN are as the command was decided."""
    return bool(dangerous) and all(d in states and states[d].type == "xing_ego_prio" and d.split(":")[0] not in seen for d in dangerous)


class Loop:
    """The world one hierarchy shares: the SUMO process, the perception, the situation memory, the held command, the
    last projection and the accounting."""

    def __init__(self, level, work=None, traci=None):
        work = work or level.get("work") or tempfile.mkdtemp(prefix="road-sumo-")
        args = dict(level.get("scenario_args", {}))
        if "vehicles" in level:
            args["n"] = int(level["vehicles"])
        self.scenario, self.seed, self.ego_id = level.get("scenario", "straight"), int(level.get("seed", 1)), EGO
        self.world = SumoWorld(self.scenario, work, seed=self.seed, traci=traci, **args)
        self.lanemap = lanemap_of(self.world.net)
        sen = level.get("sensor", {})
        self.perc = Perception(self.lanemap, Sensor(range=sen.get("range", SENSOR_RANGE), miss=sen.get("miss", 0.0),
                                                    seed=int(level.get("seed", 1))), dt=self.world.dt)
        self.sit, self.truth_sit = Situation(), Situation()
        self.cmd, self.life = ("keep", None), 0
        self.changing = None                          # (side, source lane index, ticks left)
        self.passes = []                              # the carries through the opposite lane: {t, s, into, back: (t, why), end}
        self.proj = {"binding": {}, "facts": {"now": 1}, "fold": None, "states": [], "ego": None}
        self.tick, self.t, self.warmup = 0, 0.0, 0
        self.level_dest = level.get("dest", DESTS.get(level.get("scenario", "straight")))
        self.violations, self.optimistic, self.restricted, self.latency, self.ms = [], [], 0, [], []
        self.stood = set()                            # the stop signs' zones the ego has stood at (road_facts.stood_at_sign)
        self.unseen_duty = []                         # the accounting's own class: a pair the ego has the way over, the other hidden (others_duty)
        self.pace = None                              # the person's target speed, under the lanes' limits (road_wishes)
        self.undue = []                               # a responder brake with no dangerous pair in its fold (road-2: none)
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
                                                    speeds={m.id: m.dyn.vmax for m in movers}, pace=self.pace, sight=self.perc.last.get("sight"), stood=self.stood,
                                                    left_from=(self.left_from[0], self.t - self.left_from[1])
                                                    if getattr(self, "left_from", None) else None)
        self.proj = {"binding": binding, "facts": f, "fold": fold, "states": states, "ego": ego}
        self.prev_truth, self.last_movers = truth, movers
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
        ticks = int(round(restrict.CHANGE_S / self.world.dt))
        here = self.lanemap.lanes[ego.lane]
        if self.world.carry is not None:              # passing through the opposite lane: the carry's (sumo_world), its route lane
            if (lane == "abort" and self.changing or lane == "right") and self.world.carry["to"]:   # the ego's right (heading_frame): home
                self.world.carry_back()
                self.changing = None if lane == "abort" else ("right", idx, ticks)
                if lane == "right":
                    self.left_from = ("left", self.t)
                self.passes[-1]["back"] = (self.t, "abort" if lane == "abort" else "change")
        elif lane == "abort" and self.changing:
            target, self.changing = self.changing[1], None
        elif lane in ("left", "right") and getattr(here, lane) and getattr(here, lane + "_opposite"):
            # the oncoming lane (change_oncoming, 668e45): no changeLane target in SUMO; the host carries the ego's body
            # through it (the architect's option (b), road-gap-sumo: sumo_world.carry_start)
            self.world.carry_start(getattr(here, lane))
            self.changing = (lane, idx, ticks)           # no left_from: the lane is lent for the pass, its way back is the plan
            self.passes.append({"t": self.t, "s": round(ego.s, 1), "into": getattr(here, lane)})
        elif lane in ("left", "right") and getattr(here, lane):
            target = idx + (1 if lane == "left" else -1)             # SUMO's index 0 is the rightmost
            self.changing = (lane, idx, ticks)
            self.left_from = ("right" if lane == "left" else "left", self.t)     # settled(D): the side it left
        self.world.control(a, target)
        if self.passes and "end" not in self.passes[-1] and self.world.carry is None:
            self.passes[-1]["end"] = self.t                # the body on its route lane again
        if self.life > 0:
            self.life -= 1
        if self.changing:
            self.changing = (self.changing[0], self.changing[1], self.changing[2] - 1) if self.changing[2] > 1 else None
        return a, lane, cmd

    def yield_gap(self, ego):
        """The ego's front to the next junction's stop line on its way, inside one to the next zone's (d_enter; restrict keeps min_dist)."""
        link = None if self.lanemap.lanes[ego.lane].internal else self.lanemap.next_link(ego.route or [ego.lane], ego.s)
        if link is not None:                          # the stop line, before a junction
            return link[1]
        z = self.lanemap.nearest_zone(ego.route or [ego.lane], ego.s, length=ego.length)
        return z[2] if z else None

    # ── one tick ──
    def step(self):
        """One responder tick. → whether the ego is still on the road."""
        t0 = time.perf_counter()
        applied = None
        if self.proj.get("ego") is not None and not self.world.ego_done:
            fold = self.proj["fold"] or {}                # the fold the command was decided on
            applied = self.restrict(self.proj["ego"])
            if tuple(applied[2][:2]) == ("brake", "brake_min") and not fold.get("dangerous"):
                self.undue.append(self.tick)              # the responder's brake (brake_min) without a dangerous pair
        t1 = time.perf_counter()
        hits = len(self.world.collisions)
        on = self.world.step()
        hits = [c for c in self.world.collisions[hits:] if EGO in (c["collider"], c["victim"])]
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
                         "seen": len(self.perc.last["seen"]), "seen_ids": sorted(self.perc.last["seen"]), "sight": [a for a in self.proj["facts"] if a.startswith(("unseen_ahead", "road_hidden"))], "lanes": [a for a in self.proj["facts"] if a.startswith(LANE_FACTS)], "tracks": len(movers), "binding": binding,
                         "zone": next((a[len("zone_at(nextzone,"):-1] for a in self.proj["facts"] if a.startswith("zone_at(nextzone")), None),
                         "signal": next((a[len("signal(nextzone,"):-1] for a in self.proj["facts"] if a.startswith("signal(nextzone")), None),
                         "contact": self.contacts(hits),
                         "danger": danger_rows(self.proj["states"], {m.id: (m.lane, m.s, m.dyn.vmax) for m in movers}),
                         "truth": danger_rows(self._truth_states, {k: (p["lane"], p["s"], p["speed"]) for k, p in truth.items()}, self._truth_pairs)})
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
        lm, ego_f = self.lanemap, ego
        home = road_facts.oncoming_home(lm, ego)
        if home is not None:                              # on the opposite lane: the truth's pairs in the ego's heading too
            lm, ego_f, others, _ = road_facts.heading_frame(lm, ego, others, home)
        pairs = {p.id: p for p in lm.pairs(ego_f, others, lights=lights)}
        states = self.truth_sit.check(list(pairs.values()))
        self._truth_states, self._truth_pairs = states, pairs
        fold = Situation.fold(states, ego.dyn)
        before = getattr(self, "_truth_fold", None)       # the truth as it stood when the command was decided
        if applied is not None and before is not None:
            a, lane, _ = applied
            hi = restrict.bound(before, ego.dyn)
            if a > hi + 1e-9 and ego.dyn.vmax > 0:           # standing still meets any braking response (road_world's)
                row = {"tick": self.tick, "what": "accel above the truth response", "a": a, "max": hi, "dangerous": before["dangerous"]}
                if others_duty(before["dangerous"], getattr(self, "_prev_states", {}), getattr(self, "_seen_then", ())):
                    self.unseen_duty.append(dict(row, what=UNSEEN_DUTY))
                else:
                    self.violations.append(row)
        self._truth_fold = fold
        prev = getattr(self, "_prev_states", {})
        for s in states:
            p = prev.get(s.id)
            if not s.dangerous or p is None or p.dangerous or applied is None:
                continue
            a, lane, _ = applied
            if lane in ("left", "right") and s.type in ("same_dir", "opp_dir"):
                self.violations.append({"tick": self.tick, "what": "a lane change into it", "pair": s.id})
            elif s.type in ("xing_obj_prio", "xing_same_prio") and self.in_zone(ego) and p.xing != "able_to_stop":
                self.violations.append({"tick": self.tick, "what": "entered a zone without priority, unable to stop",
                                        "pair": s.id})
            elif s.type == "same_dir" and pairs[s.id].lon == "in_front" and a > 0:
                # the architect's ruling (2026-10-26): an OPTIMISTIC accel, its own column beside the violations
                self.optimistic.append({"tick": self.tick, "what": "accelerated as the rear one", "pair": s.id})
        self._prev_states = {s.id: s for s in states}
        self._seen_then = set(self.perc.last["seen"])     # what the next tick's command is decided on
        bad = [s for s in states if s.dangerous and s.resp_lon != "none"]
        if bad and self.danger_since is None:
            self.danger_since = self.tick
        if self.danger_since is not None and applied is not None and applied[0] <= -(ego.dyn.brake_min or 0.0) + 1e-9:
            self.latency.append(self.tick - self.danger_since)
            self.danger_since = None
        elif not bad:
            self.danger_since = None

    # ── the truth column (spec 20 §10.2; cr-harvest s-f4e297da): what the world held, beside the trace ──
    def truth_row(self):
        """This tick's row of TRACE/truth.jsonl (road_host writes it with the trace's k): the ego's lane, its kind and this step's
        contacts; every body within the sensor range, its world class (SUMO's vClass), `as` obj, the role the projection bound it to
        this tick (a perceived track matched to the body on its lane within MATCH_M; null when unbound: unseen, out of range,
        passive), lane, s, v and its lane's kind. None before the ego is on the road."""
        truth, ego = getattr(self, "prev_truth", None), self.proj.get("ego")
        if not truth or ego is None or EGO not in truth:
            return None
        e = truth[EGO]
        carry = getattr(self.world, "carry", None)
        ego_kind = "oncoming" if carry is not None and self.world.carry_side() == "opp" else \
            getattr(self.lanemap.lanes.get(e["lane"]), "kind", None)
        contact = sorted({c["id"] for c in (self.log[-1].get("contact") or [])}) if self.log else []
        reach = self.perc.sensor.range
        near = {k: p for k, p in truth.items() if k != EGO and math.hypot(p["x"] - e["x"], p["y"] - e["y"]) <= reach}
        role_of = self._roles_on(near)
        things = []
        for k in sorted(near):
            p = near[k]
            lane = self.lanemap.lanes.get(p["lane"])
            things.append({"id": k, "class": p.get("vclass"), "as": "obj", "role": role_of.get(k), "lane": p["lane"],
                           "s": round(p["s"], 2), "v": round(p["speed"], 2), "kind": getattr(lane, "kind", None) if lane else None,
                           "length": p.get("length")})
        return {"ego": {"lane": e["lane"], "s": round(e["s"], 2), "v": round(e["speed"], 2), "kind": ego_kind, "contact": contact},
                "things": things}

    def _roles_on(self, near):
        """{truth id: role} for the projection's binding: each bound track matched to the nearest body on its lane within MATCH_M."""
        by = {m.id: m for m in getattr(self, "last_movers", None) or ()}
        out, taken = {}, set()
        for role, tid in sorted((self.proj.get("binding") or {}).items()):
            m = by.get(tid)
            if m is None:
                continue
            best = min(((abs(p["s"] - m.s), k) for k, p in near.items() if p["lane"] == m.lane and k not in taken), default=None)
            if best is not None and best[0] <= MATCH_M:
                out[best[1]] = role
                taken.add(best[1])
        return out

    def contacts(self, hits):
        """SUMO's contacts of this step with the ego, each with the type the truth's pair of that body had (any type, not only the
        dangerous): a contact on a `not_relevant` pair is nobody's pair (T10)."""
        types = {k.split(":")[0]: p.type for k, p in (getattr(self, "_truth_pairs", None) or {}).items()}
        out = []
        for c in hits:
            other = c["victim"] if c["collider"] == EGO else c["collider"]
            out.append({"id": other, "type": types.get(other)})
        return out

    def in_zone(self, ego):
        return any(road_facts.inside(z, ego) for z in self.lanemap.zones)

    def summary(self):
        w = self.world
        def mean(k):
            xs = [m[k] for m in self.ms]
            return round(1000 * sum(xs) / len(xs), 3) if xs else None
        ego = self.proj.get("ego")
        return {"seed": w.seed, "ticks": self.tick, "t": self.t, "sumo_t": w.t, "arrived": self.arrived(),
                "s": round(ego.s, 1) if ego is not None else None, "dest": self.level_dest, "ego_done": w.ego_done, "collisions": w.ego_collisions,
                "collision_events": collision_events(w.collisions),
                # the ego's first SUMO collision (t, the other, its type, where): the record's tick beside CommonRoad's box contact
                "collision_first": next(({k: c.get(k) for k in ("t", "collider", "victim", "type", "xy")} for c in w.collisions
                                         if EGO in (c["collider"], c["victim"])), None),
                "rc": 100.0 if self.arrived() else ((w.director.report()["rc"]) if getattr(w, "director", None) is not None else None),
                "director": w.director.report() if getattr(w, "director", None) is not None else None,
                "all_collisions": len(w.collisions), "violations": len(self.violations), "unseen_other_duty": len(self.unseen_duty), "optimistic": len(self.optimistic), "restricted": self.restricted,
                "latency_truth": self.latency, "first": self.violations[:3],
                "ms": {k: mean(k) for k in ("restrict", "sumo", "perceive", "project", "account")},
                "vehicles_max": max((m["vehicles"] for m in self.ms), default=0),
                "undue_brakes": len(self.undue), "passes": self.passes, "rss": dict(rss_card(), sensor_range=self.perc.sensor.range),
                "sensor_range": self.perc.sensor.range}


    def close(self):
        self.world.close()


def collision_events(collisions, gap_s=5.0, radius_m=5.0):
    """The ego's collisions as events, the Leaderboard's way (CARLA's CollisionTest: the same other within 5 s is one,
    and so is any contact within 5 m of the last event's place, COLLISION_RADIUS; nina's reviews): SUMO reports a
    collision per step while two overlap."""
    return merge_events([(c["t"], c["victim"] if c["collider"] == EGO else c["collider"], c.get("xy"))
                         for c in collisions if EGO in (c["collider"], c["victim"])], gap_s, radius_m)


def merge_events(contacts, gap_s=5.0, radius_m=5.0):
    """[(t, other, (x, y) or None)] → the number of collision events: a new one unless the same other touched within
    GAP_S, or the place is within RADIUS_M of the last event's."""
    n, last, at = 0, {}, None
    for t, other, xy in contacts:
        same = other in last and t - last[other] <= gap_s
        near = xy is not None and at is not None and math.hypot(xy[0] - at[0], xy[1] - at[1]) <= radius_m
        if not (same or near):
            n += 1
            at = xy
        last[other] = t
    return n


def danger_rows(states, where, pairs=None):
    """The log's dangerous pairs, which the fold's response answers: the other (WHERE: id → lane, s, speed), its verdict,
    each side's response time and a crossing's distances to enter and leave the zone (PAIRS: the truth's, by the pair's id
    "other:type[:zone]")."""
    out = []
    for s in states:
        if s.dangerous:
            lane, at, v = where.get(s.id.split(":")[0], (None, None, None))
            row = {"id": s.id, "role": s.role, "type": s.type, "resp": s.resp_lon, "d_lon": round(s.d_lon, 2), "d_safe": round(s.d_safe, 2),
                   "xing": s.xing, "lane": lane, "s": None if at is None else round(at, 2), "v": None if v is None else round(v, 2)}
            p = (pairs or {}).get(s.id)
            if p is not None:
                row.update(rho=[p.ego.rho, p.obj.rho])
            if p is not None and p.d_enter is not None:
                row.update({k: round(getattr(p, k), 2) for k in ("d_enter", "d_leave", "o_enter", "o_leave") if getattr(p, k) is not None})
            out.append(row)
    return out


SENSOR_RANGE = 100.0      # the ego's sensor range (m), the run's `sensor.range`; both hosts' default (road-scenarios 2f)


def rss_card():
    """The run card's RSS parameters: the ego's response time, a drive away's speed and, per class, ρ, brake_min, brake_max, min_dist
    (semantic_world.lane VCLASS: the values every pair of the run used)."""
    from semantic_world.lane import EGO_RHO, VCLASS
    return {"ego_rho": EGO_RHO, "away_ms": restrict.AWAY_MS, "classes": {c: {k: p.get(k) for k in ("rho", "brake_min", "brake_max", "min_dist")}
                                            for c, p in sorted(VCLASS.items())}}
