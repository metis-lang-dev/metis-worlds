"""road_world — the road EXERCISER (road-world s-e812715d step 2): a pure-python lane world over semantic_world.lane and
.situation, ground truth, no belief, no simulator. The road domains (road/domains) run on it through
road_host.py exactly as they will on the SUMO host (step 4).

The road: one edge `e`, three lanes e_0 (right) e_1 e_2 (left), 600 m at 16.67 m/s (60 km/h); a crosswalk w_0 over
it at s 250 (the walker has priority: zones cw_0..cw_2), a side road c_0 crossing it at s 400 (zones j_0..j_2, the
main road's priority unless a scenario gives it to the side road), an on-ramp r_0 merging into e_0 at s 500 (zone m:
compatible axes, by alternation, the zipper). Movers: the ego, scripted cars (cruise, brake at t, cut in at t, cross
at t, merge) and walkers (cross at t at a speed), each a semantic_world.lane.Mover with its class's Dynamics.

One step is DT = 0.1 s:
- the ego's command (set by the host from the domains' commands: accel, keep, brake R, change D, yield, stop_lat)
  becomes a target acceleration and a lane change;
- the RESTRICTOR (framework L4) caps it by the fold of the situation layer's proper response: resp_lon brake_min_correct
  / brake_min → at most −that braking; resp_lat on a side → no lateral move toward it (a lane change that way is
  refused or aborted); never above the lane's speed limit;
- every mover moves; the accounting runs.

The accounting, ground truth:
- a COLLISION: two movers' footprints overlap (a mover's s is its FRONT, its footprint [s − length, s], as in the
  library and SUMO: the same lane and the footprints overlap; a crossing: both inside one zone at once; the ego counts
  on both lanes while it changes lane);
- an RSS VIOLATION: a tick the ego's applied acceleration exceeds the proper response's bound (the restrictor
  makes it 0 by construction; counted as the check of the restrictor), or a pair turned dangerous by the ego's own
  act (BLAME): the ego was the rear one of a same-direction pair and accelerated, it began a lane change, or it
  entered a zone it had no priority at while it was not able to stop;
- RESTRICTED: a tick the restrictor cut the domains' command (the domain asked for more than RSS allows: not a
  violation, it is what L4 is for; reported).

Scenarios (SCENARIOS, by name; `seed` varies the traffic's speeds and times within each): cruise, lead_brake
(road-close: the lead brakes hard), lead_lanes_free (prodcat: a slow lead, the adjacent lanes free), junction (a car
crosses at the side road; `side_prio`: the side road has priority; junction_rb: it does not yield), cpna25 / cpfa50 (Euro NCAP AEB VRU, metispy
euroncap_vru.py: a walking adult from the nearside, a running adult from the farside), merge (the zipper), demo (the
tree demo: all of the above on one road, in turn)."""
import math
import random
from dataclasses import dataclass, field

from semantic_world.lane import Lane, LaneMap, Mover, Zone, dynamics_for
from semantic_world.situation import Situation

import restrict
import road_facts

DT = 0.1
LANE_W = 3.5
SPEED = 16.67                      # the main road's limit (60 km/h)
KMH = 1 / 3.6
CROSSWALK_S, JUNCTION_S, MERGE_S = 250.0, 400.0, 500.0


def road(side_prio=False):
    """The LaneMap: three main lanes, the crosswalk, the side road, the on-ramp, their zones."""
    lanes = [Lane("e_0", 600.0, LANE_W, left="e_1", speed=SPEED, edge="e", index=0),
             Lane("e_1", 600.0, LANE_W, left="e_2", right="e_0", speed=SPEED, edge="e", index=1),
             Lane("e_2", 600.0, LANE_W, right="e_1", speed=SPEED, edge="e", index=2),
             Lane("w_0", 3 * LANE_W + 3.0, 2.0, speed=3.0, edge="w"),            # the crosswalk, nearside first
             Lane("c_0", 80.0, LANE_W, speed=13.9, edge="c"),                     # the side road, from the right
             Lane("r_0", MERGE_S + 20.0, LANE_W, speed=SPEED, edge="r")]          # the on-ramp beside e_0
    zones = []
    for k in range(3):
        a = 1.5 + k * LANE_W                                                       # the walker's s across lane k
        zones.append(Zone("cw_%d" % k, {"e_%d" % k: (CROSSWALK_S, CROSSWALK_S + 4.0), "w_0": (a, a + LANE_W)},
                          priority="w_0"))
        c = 30.0 + k * LANE_W
        zones.append(Zone("j_%d" % k, {"e_%d" % k: (JUNCTION_S, JUNCTION_S + LANE_W), "c_0": (c, c + LANE_W)},
                          priority="c_0" if side_prio else "e_%d" % k))
    zones.append(Zone("m", {"e_0": (MERGE_S, MERGE_S + 20.0), "r_0": (MERGE_S, MERGE_S + 20.0)}, priority=None))
    return LaneMap(lanes, zones)


@dataclass
class Agent:
    """A mover and its script: [(t, what, arg)] — 'v' a target speed, 'brake' a deceleration until stopped,
    'lane' a cut to that lane, 'go' start moving (a walker or a crossing car waits until then)."""
    m: Mover
    v: float
    script: list = field(default_factory=list)
    a: float = 0.0
    target: float = None
    moving: bool = True
    done: bool = False                  # left the map
    breaks_rules: bool = False          # junction_rb: never yields to an ego with the priority


@dataclass
class Ego:
    m: Mover
    v: float
    a: float = 0.0
    cmd: tuple = ("keep", None)         # the domains' last command and its arg
    cmd_life: int = 0                   # ticks it still holds (its issuer's period)
    changing: str = None                # the lane it leaves while it changes lane
    change_side: str = None             # … and the side it moves to
    change_t: float = 0.0
    left_from: tuple = None             # (the side the last change left, its start t): settled(D)
    yield_s: float = None               # yield: stop before this s


class RoadWorld:
    def __init__(self, scenario="cruise", seed=1):
        self.name, self.seed, self.rng = scenario, seed, random.Random(seed)
        self.t, self.tick = 0.0, 0
        spec = SCENARIOS[scenario](self.rng)
        self.map = road(side_prio=spec.get("side_prio", False))
        e = spec["ego"]
        self.ego = Ego(Mover("ego", e["lane"], e["s"], length=4.5, width=1.8), e["v"])
        self.agents = [Agent(Mover(a["id"], a["lane"], a["s"], route=a.get("route"), vclass=a.get("vclass", "passenger"),
                                   length=a.get("length", 0.5 if a.get("vclass") == "pedestrian" else 4.5),
                                   width=a.get("width", 0.5 if a.get("vclass") == "pedestrian" else 1.8)),
                             a["v"], sorted(a.get("script", [])), moving=a.get("moving", True),
                             breaks_rules=a.get("breaks_rules", False))
                       for a in spec["agents"]]
        self.dest = spec.get("dest", 580.0)
        self.sit = Situation()
        self.collisions, self.violations, self.restricted, self.log = [], [], 0, []
        self.zone_turn = {"m": None}                # the zipper: the lane the last entrant came from
        self.last_in = {}                           # zone -> movers inside last step
        self._dyn()

    # ── the movers' dynamics, the pairs, the situation ──
    def _dyn(self):
        lm = self.map
        self.ego.m.dyn = dynamics_for("passenger", v=self.ego.v, lane=lm.lanes[self.ego.m.lane], ego=True)
        for ag in self.agents:
            ag.m.dyn = dynamics_for(ag.m.vclass, v=ag.v, lane=lm.lanes[ag.m.lane])

    def _all(self):
        return [self.ego.m] + [ag.m for ag in self.live()]

    def live(self):
        return [ag for ag in self.agents if not ag.done]

    def observe(self):
        """This tick's facts over roles (road_facts, every host's projection), once a tick: the situation layer's
        memory moves one cycle per tick, and the restrictor's fold is the domains'. → (facts, roles, fold, states)."""
        if getattr(self, "_obs_tick", None) != self.tick:
            self.ego.m.route = [self.ego.m.lane]
            live = self.live()
            self._obs = road_facts.facts(self.map, self.ego.m, self.ego.v, [ag.m for ag in live], self.sit,
                                         changing=self.ego.change_side, dest=self.dest, turn=self.zone_turn,
                                         left_from=(self.ego.left_from[0], self.t - self.ego.left_from[1]) if self.ego.left_from else None,
                                         speeds={ag.m.id: ag.v for ag in live})
            self._obs_tick = self.tick
        return self._obs

    def states(self, role_of=None, memory=True):
        """The situation layer's states, the ego against every live mover (the pairs: semantic_world.lane)."""
        self.ego.m.route = [self.ego.m.lane]
        pairs = self.map.pairs(self.ego.m, [ag.m for ag in self.live()], role_of=role_of)
        sit = self.sit if memory else Situation()
        return sit.check(pairs), pairs

    def fold(self, states):
        return Situation.fold(states, self.ego.m.dyn)

    # ── the ego's command → an acceleration and a lane (restrict.py, every road host's) ──
    def command(self, cmd, life=1):
        """The domains' command (restrict.command's (kind, arg)), held LIFE ticks (its issuer's period)."""
        self.ego.cmd, self.ego.cmd_life = cmd, life
        if cmd[0] == "yield":
            z = self.map.nearest_zone([self.ego.m.lane], self.ego.m.s)
            self.ego.yield_s = z[0].lanes[z[1]][0] if z else None

    def yield_gap(self):
        if self.ego.cmd[0] != "yield" or self.ego.yield_s is None:
            return None
        return self.ego.yield_s - self.ego.m.s                     # the front bumper (s) to the zone line

    # ── one step ──
    def step(self):
        _, _, fold, states = self.observe()
        cmd = self.ego.cmd if self.ego.cmd_life > 0 else ("keep", None)
        d, v0 = self.ego.m.dyn, self.ego.v
        a, lane = restrict.restrict(cmd, fold, d, v0, changing=self.ego.change_side, yield_gap=self.yield_gap())
        hi = restrict.bound(fold, d)
        if restrict.capped(cmd, fold, d, v0, self.yield_gap()):
            self.restricted += 1
        began = False
        if lane == "abort":
            self.ego.m.lane, self.ego.changing, self.ego.change_side = self.ego.changing, None, None
        elif lane in ("left", "right"):
            to = getattr(self.map.lanes[self.ego.m.lane], lane)
            if to:
                self.ego.changing, self.ego.change_side, self.ego.change_t = self.ego.m.lane, lane, 0.0
                self.ego.left_from = ("right" if lane == "left" else "left", self.t)
                self.ego.m.lane, began = to, True
        prev = {s.id: s for s in states}
        v = max(0.0, min(v0 + a * DT, self.map.vcap(self.ego.m.lane)))
        self.ego.m.s += 0.5 * (v0 + v) * DT
        a = (v - v0) / DT                                        # the effective acceleration (the cap, a stop)
        self.ego.v, self.ego.a = v, a
        if self.ego.changing:
            self.ego.change_t += DT
            if self.ego.change_t >= restrict.CHANGE_S:
                self.ego.changing, self.ego.change_side = None, None
        if self.ego.cmd_life > 0:
            self.ego.cmd_life -= 1
        before = {z.id: {m.id for m in self._all() if road_facts.inside(z, m)} for z in self.map.zones if z.priority is None}
        for ag in self.live():
            self._script(ag)
        for z in self.map.zones:
            if z.priority is None:
                for m in self._all():
                    if road_facts.inside(z, m) and m.id not in before[z.id]:
                        self.zone_turn[z.id] = m.lane                     # the zipper's alternation: who entered last
        self.t, self.tick = self.t + DT, self.tick + 1
        self._dyn()
        after, pairs = self.states(memory=False)
        self._account(prev, after, a, hi, {"accel": a > 0, "change": began}, {q.id: q.lon for q in pairs})
        self.log.append({"t": round(self.t, 2), "s": round(self.ego.m.s, 2), "v": round(v, 2), "a": round(a, 2),
                         "lane": self.ego.m.lane, "cmd": list(cmd), "resp": fold["resp_lon"]})

    def _script(self, ag):
        while ag.script and ag.script[0][0] <= self.t + 1e-9:
            _, what, arg = ag.script.pop(0)
            if what == "v":
                ag.target = arg
            elif what == "brake":
                ag.a, ag.target = -arg, 0.0
            elif what == "lane":
                ag.m.lane = arg
            elif what == "go":
                ag.moving = True
        if not ag.moving:
            return
        line = None if ag.breaks_rules else self._must_yield(ag)
        if line is not None:                                      # right of way is given: it holds before the line
            if ag.m.s >= line - 0.5:
                ag.v, ag.a = 0.0, 0.0
                return
            ag.a = -min(6.0, ag.v * ag.v / (2 * max(0.5, line - ag.m.s)))
        if ag.target is not None and ag.a >= 0:
            ag.a = max(-3.0, min(2.0, (ag.target - ag.v) / 1.0))
        v = max(0.0, ag.v + ag.a * DT)
        if ag.target is not None and ag.a < 0 and v <= ag.target:
            v, ag.a = ag.target, 0.0
        ag.m.s += 0.5 * (ag.v + v) * DT
        ag.v = v
        lane = self.map.lanes[ag.m.lane]
        if ag.m.s > lane.length:
            if lane.id == "r_0":                                    # the ramp's end: onto e_0
                ag.m.lane, ag.m.s = "e_0", ag.m.s
            else:
                ag.done = True

    def _must_yield(self, ag, band=60.0):
        """A scripted car at the next zone on its lane yields to the ego approaching or inside it when the ego's lane
        has the zone's priority (an other that keeps the rules): → the s of its line, or None."""
        if ag.m.vclass in ("pedestrian", "bicycle"):
            return None
        ego = self.ego.m
        for z in self.map.zones:
            if ag.m.lane not in z.lanes or ego.lane not in z.lanes or z.priority != ego.lane or ag.m.lane == ego.lane:
                continue                                          # only on another lane, to an ego with the priority
            a, _ = z.lanes[ag.m.lane]
            if ag.m.s >= a or a - ag.m.s > band:
                continue                                          # its front at the line or past it (it clears), or far
            e_in, e_out = z.lanes[ego.lane]
            if -band <= ego.s - e_in and ego.s - ego.length <= e_out:   # the ego coming, or in it
                return a
        return None

    # ── the accounting ──
    def _footprint_lanes(self):
        return {self.ego.m.lane} | ({self.ego.changing} if self.ego.changing else set())

    def zones_of(self, m, lanes=None):
        out = set()
        for z in self.map.zones:
            for ln in (lanes or {m.lane}):
                if ln in z.lanes:
                    a, b = z.lanes[ln]
                    if m.s >= a and m.s - m.length <= b:            # s is the FRONT (the library's, SUMO's)
                        out.add(z.id)
        return out

    def _account(self, prev, after, a, hi, act, lon):
        ego = self.ego.m
        lanes = self._footprint_lanes()
        ego_zones = self.zones_of(ego, lanes)
        for ag in self.live():
            o = ag.m
            same = o.lane in lanes and o.s > ego.s - ego.length and ego.s > o.s - o.length   # [s − length, s] overlap
            cross = bool(ego_zones & self.zones_of(o))
            if same or cross:
                self.collisions.append({"t": round(self.t, 2), "with": o.id, "how": "lane" if same else "zone"})
        if a > hi + 1e-9 and self.ego.v > 0:                     # standing still meets any braking response
            self.violations.append({"t": round(self.t, 2), "what": "accel above the response", "a": a, "max": hi})
        for s in after:
            p = prev.get(s.id)
            if not s.dangerous or p is None or p.dangerous:
                continue                                         # dangerous already, or not newly
            blame = None
            if act["change"] and s.type in ("same_dir", "opp_dir"):
                blame = "a lane change into it"
            elif s.type == "same_dir" and lon.get(s.id) == "in_front" and act["accel"]:
                blame = "accelerated as the rear one"
            elif s.type in ("xing_obj_prio", "xing_same_prio") and ego_zones and not (p.xing == "able_to_stop"):
                blame = "entered a zone without priority, unable to stop"
            if blame:
                self.violations.append({"t": round(self.t, 2), "what": blame, "pair": s.id})

    # ── the ego's route progress ──
    def arrived(self):
        return self.ego.m.s >= self.dest

    def summary(self):
        return {"scenario": self.name, "seed": self.seed, "t": round(self.t, 1), "arrived": self.arrived(),
                "s": round(self.ego.m.s, 1), "collisions": len(self.collisions), "violations": len(self.violations),
                "restricted": self.restricted, "first": (self.collisions + self.violations)[:3]}


# ── the scenarios ─────────────────────────────────────────────────────────────────────────────────────────────

def _ego(rng, lane="e_1", s=20.0, v=11.1):
    return {"lane": lane, "s": s, "v": v}


def cruise(rng):
    return {"ego": _ego(rng), "dest": 580.0,
            "agents": [{"id": "car1", "lane": "e_1", "s": 70.0 + rng.uniform(0, 20), "v": 13.0 + rng.uniform(0, 2)},
                       {"id": "car2", "lane": "e_2", "s": 40.0 + rng.uniform(0, 20), "v": 15.0},
                       {"id": "car3", "lane": "e_0", "s": 10.0, "v": 12.0}]}


def lead_brake(rng):
    """road-close: the lead in the ego's lane brakes hard (a_max,brake 8 m/s²) at t."""
    t = 3.0 + rng.uniform(0, 2)
    return {"ego": _ego(rng, v=13.0), "dest": 300.0,
            "agents": [{"id": "lead", "lane": "e_1", "s": 60.0, "v": 13.0, "script": [(t, "brake", 8.0)]}]}


def lead_lanes_free(rng):
    """prodcat lead-lanes-free: a slow lead ahead in the ego's lane, both adjacent lanes free."""
    return {"ego": _ego(rng, v=13.0), "dest": 330.0,
            "agents": [{"id": "slow", "lane": "e_1", "s": 70.0 + rng.uniform(0, 10), "v": 6.0, "script": [(0.0, "v", 6.0)]}]}


def junction(rng, side_prio=False):
    t = 20.0 + rng.uniform(-2, 2)
    return {"ego": _ego(rng, s=300.0, v=11.1), "dest": 460.0, "side_prio": side_prio,
            "agents": [{"id": "xcar", "lane": "c_0", "s": 5.0, "v": 0.0, "moving": False,
                        "script": [(t - 20.0 + 6.0, "go", None), (t - 20.0 + 6.0, "v", 10.0)]}]}


def junction_side(rng):
    return junction(rng, side_prio=True)


def junction_rb(rng):
    """The rule-breaker (road step 5): the main road has priority, and the side road's car does not yield — it
    goes so that, unbraked, it reaches the junction as the ego does (the gate: 0 ego-blamed collisions, the
    response within rho)."""
    # the ego (s 300, the planner accelerating it to the limit) reaches the junction line (s 400) at about t 6.1; the
    # car, from rest at s 5 (about 2 m/s² to 10 m/s), its line at s 33.5 about 5.5 s after it goes: it enters just
    # before the ego and takes its right of way
    start = 0.4 + rng.uniform(0.0, 0.4)
    return {"ego": _ego(rng, s=300.0, v=11.1), "dest": 460.0, "side_prio": False,
            "agents": [{"id": "xcar", "lane": "c_0", "s": 5.0, "v": 0.0, "moving": False, "breaks_rules": True,
                        "script": [(start, "go", None), (start, "v", 10.0)]}]}


def _walker(rng, speed_kmh, farside, ego_v_kmh=40.0):
    """A Euro NCAP AEB VRU crossing: the walker starts so that, unbraked, it meets the ego at the crosswalk."""
    v = ego_v_kmh * KMH
    ego_s = 120.0
    t_meet = (CROSSWALK_S - ego_s) / v
    walk = speed_kmh * KMH
    a = 1.5 + 1 * LANE_W + 0.5 * LANE_W                         # the ego's lane centre (e_1) along w_0
    dist = (a if not farside else (3 * LANE_W + 3.0 - a))       # nearside walks from s 0; farside from the far end
    start = max(0.0, t_meet - dist / walk + rng.uniform(-0.3, 0.3))
    return {"ego": _ego(rng, s=ego_s, v=v), "dest": 320.0,
            "agents": [{"id": "walker", "lane": "w_0", "s": 0.0 if not farside else 0.0, "v": 0.0, "moving": False,
                        "vclass": "pedestrian", "script": [(start, "go", None), (start, "v", walk)]}]}


def cpna25(rng):
    return _walker(rng, 5.0, farside=False)


def cpfa50(rng):
    return _walker(rng, 8.0, farside=True)


def merge(rng):
    return {"ego": _ego(rng, lane="e_0", s=380.0, v=11.0), "dest": 590.0,
            "agents": [{"id": "ramp1", "lane": "r_0", "s": 400.0 + rng.uniform(0, 10), "v": 11.0},
                       {"id": "ramp2", "lane": "r_0", "s": 380.0 + rng.uniform(0, 10), "v": 11.0}]}


def demo(rng):
    """The tree demo: a slow lead with the lanes free, a lead that brakes, the walker, the crossing car, the merge."""
    return {"ego": _ego(rng, v=12.0), "dest": 590.0,
            "agents": [{"id": "slow", "lane": "e_1", "s": 70.0 + rng.uniform(0, 10), "v": 7.0, "script": [(0.0, "v", 7.0)]},
                       {"id": "brakes", "lane": "e_2", "s": 170.0 + rng.uniform(0, 10), "v": 12.0,
                        "script": [(14.0 + rng.uniform(0, 2), "brake", 6.0), (19.0, "v", 12.0)]},
                       {"id": "walker", "lane": "w_0", "s": 0.0, "v": 0.0, "moving": False, "vclass": "pedestrian",
                        "script": [(17.0 + rng.uniform(0, 3), "go", None), (17.0, "v", 1.4)]},
                       {"id": "xcar", "lane": "c_0", "s": 5.0, "v": 0.0, "moving": False,
                        "script": [(28.0 + rng.uniform(0, 4), "go", None), (28.0, "v", 10.0)]},
                       {"id": "ramp1", "lane": "r_0", "s": 420.0 + rng.uniform(0, 20), "v": 9.0}]}


def junction_rb_early(rng):
    """The rule-breaker revealed early (road-2 1b): the main road has priority, and a 15 m truck from the side road
    does not yield; from rest 13.5 m before its line (s 20; the line at s 33.5) to 5 m/s it is past its last point to
    stop (5²/16 + 1 = 2.6 m before the line) at about t 3.4, when the ego (s 300, the planner accelerating it) is
    still about 53 m out against its 35.7 m stop-short distance; it occupies the zone from about t 4.0 to t 7.7,
    over the ego's unbraked arrival (t 6.1). The rule-5 response can stop the ego short."""
    go = rng.uniform(0.0, 0.3)
    return {"ego": _ego(rng, s=300.0, v=11.1), "dest": 460.0, "side_prio": False,
            "agents": [{"id": "truck", "lane": "c_0", "s": 20.0, "v": 0.0, "moving": False, "breaks_rules": True,
                        "length": 15.0, "width": 2.5, "script": [(go, "go", None), (go, "v", 5.0)]}]}


SCENARIOS = {"cruise": cruise, "lead_brake": lead_brake, "lead_lanes_free": lead_lanes_free, "junction": junction,
             "junction_side": junction_side, "junction_rb": junction_rb, "junction_rb_early": junction_rb_early, "cpna25": cpna25, "cpfa50": cpfa50, "merge": merge, "demo": demo}
