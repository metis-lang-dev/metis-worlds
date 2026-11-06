"""walkers — a walker on SUMO as a HOST-SIDE body on a VIRTUAL crosswalk (scenario-catalog s-92e0b650 step 4; the architect's ruling
on nina's option 2, road-scenarios step 1's walker check).

Our towns' nets have no sidewalk, no crossing and no walking area, so no SUMO person can walk on them (nina: none even with
--opendrive.import-all-lanes). A card's `kind: pedestrian` actor is therefore not a SUMO body at all: the director carries it as a
pose in the truth (sumo_world.truth) that SUMO's own cars do not see, on a lane the HOST adds to the run's lane map: the walker's
path across the carriageway, the exerciser's crosswalk w_0 on a town. Each road lane the path crosses gets a Zone with it, so the
family's crossing(vru1, on | near), yield_walker and the responder's vru pairs read it unchanged (no new vocabulary): geometry is
the host's (rule 2).

The path (the source's placement, srunner/scenarios/object_crash_vehicle.py, pedestrian_crossing.py): the crossing point is the
actor's `at` on the ego's route (as a card's car is placed); the walker starts CURB_M beyond the road's right edge there (`side:
left`: the left edge), and walks straight across both directions' lanes to CURB_M beyond the far edge, turned by `crossing_angle`
(degrees, the source's: toward the ego's direction of travel), at its script's speed once its trigger fires (the source's
InTimeToArrivalToLocation OR InTriggerDistanceToLocation to the crossing point). Its crosswalk has the walker's priority when the
card says `crossing: zebra` (PedestrianCrossing's junction entry), none mid-block (DynamicObjectCrossing, ParkingCrossingPedestrian:
the source's jaywalker; the responder's brake is the law under test). Contact with the ego is the walker's box against the ego's
(SUMO's own check cannot see a host-side body): SumoWorld counts it as a collision."""
import math

from semantic_world.lane import Lane, Zone

WALK_W = 2.0           # the virtual crosswalk's width, m
ZONE_HALF = 2.0        # the stretch of each road lane the crosswalk covers, either side of its crossing point (the exerciser's 4 m)
CURB_M = 1.5           # the walker's start beyond the road's edge (the source: 1.2 m off the sidewalk waypoint)
BODY = (0.5, 0.5)      # a walker's length and width (scenario_cards.KIND)


def _at(shape, pos):
    """The point POS m along SHAPE and the heading (radians from +x) of its segment there."""
    run = 0.0
    for (x0, y0), (x1, y1) in zip(shape, shape[1:]):
        seg = math.hypot(x1 - x0, y1 - y0)
        if run + seg >= pos or (x1, y1) == shape[-1]:
            f = 0.0 if seg == 0 else max(0.0, min(1.0, (pos - run) / seg))
            return (x0 + f * (x1 - x0), y0 + f * (y1 - y0)), math.atan2(y1 - y0, x1 - x0)
        run += seg
    (x0, y0), (x1, y1) = shape[-2], shape[-1]
    return (x1, y1), math.atan2(y1 - y0, x1 - x0)


def _reverse(edge):
    return next((e for e in edge.getToNode().getOutgoing() if e.getToNode() == edge.getFromNode()), None)


class Walker:
    """One walker: its virtual lane, its zones, its trigger and its state."""

    def __init__(self, net, actor):
        self.id, self.a = actor["id"], actor
        pl = actor["place"]
        edge = net.getEdge(pl["route"][0])
        ego_lane = edge.getLanes()[pl["lane"]]
        self.edge, self.pos = edge.getID(), float(pl["pos"])                   # the crossing point on the ego's lane
        (cx, cy), h = _at(ego_lane.getShape(), self.pos)
        right = (math.sin(h), -math.cos(h))                                    # the right of the ego's heading
        road = list(edge.getLanes()) + (list(_reverse(edge).getLanes()) if _reverse(edge) is not None else [])
        # every road lane's centre at the crossing, its offset to the right of the ego's lane centre
        cross = []
        for ln in road:
            s, _ = ln.getClosestLanePosAndDist((cx, cy))
            (lx, ly), _ = _at(ln.getShape(), s)
            cross.append((ln, s, (lx - cx) * right[0] + (ly - cy) * right[1]))
        far_right = max(o + ln.getWidth() / 2.0 for ln, _, o in cross)
        far_left = max(-o + ln.getWidth() / 2.0 for ln, _, o in cross)
        side = (actor.get("at") or {}).get("side", "right")
        sgn = 1.0 if side == "right" else -1.0                                 # starting from the right edge walks to the left
        start_off = sgn * ((far_right if side == "right" else far_left) + CURB_M)
        self.start = (cx + right[0] * start_off, cy + right[1] * start_off)
        ang = math.radians(float(actor.get("crossing_angle", 0.0)))
        d = (-sgn * right[0], -sgn * right[1])                                 # across the road, toward the far edge
        fwd = (math.cos(h), math.sin(h))
        self.dir = (d[0] * math.cos(ang) + fwd[0] * math.sin(ang), d[1] * math.cos(ang) + fwd[1] * math.sin(ang))
        self.length = (far_right + far_left + 2 * CURB_M) / max(math.cos(ang), 0.2)
        self.lane_id = "vw_%s" % self.id
        self.zebra = actor.get("crossing") == "zebra"
        self.zones = []
        for ln, s, o in cross:
            a = (start_off - o) * sgn / max(math.cos(ang), 0.2)                # the walker's s at that lane's centre
            w = ln.getWidth() / 2.0 / max(math.cos(ang), 0.2)
            self.zones.append(Zone("vz_%s_%s" % (self.id, ln.getID()), {ln.getID(): (max(0.0, s - ZONE_HALF), s + ZONE_HALF),
                                                                        self.lane_id: (max(0.0, a - w), a + w)},
                                   priority=self.lane_id if self.zebra else None))
        trig = actor.get("trigger") or {}
        self.tta, self.dist = float(trig.get("tta", 0.0)), float(trig.get("dist", 0.0))
        steps = [st for st in actor.get("script") or [] if st.get("when") == "trigger"]
        self.v = float(next((st["v"] for st in steps if "v" in st), actor.get("v", 1.4)) or 1.4)
        self.after = float(next((st.get("after", 0.0) for st in steps), 0.0))
        self.s, self.go_at, self.fired, self.gone = 0.0, None, None, False

    def lane(self):
        """The virtual crosswalk as a semantic_world Lane (the host's: geometry only)."""
        end = (self.start[0] + self.dir[0] * self.length, self.start[1] + self.dir[1] * self.length)
        return Lane(self.lane_id, self.length, WALK_W, speed=3.0, shape=[self.start, end], edge=self.lane_id, function="crossing")

    def pose(self):
        x, y = self.start[0] + self.dir[0] * self.s, self.start[1] + self.dir[1] * self.s
        return {"x": x, "y": y, "heading": math.atan2(self.dir[1], self.dir[0]), "length": BODY[0], "width": BODY[1],
                "speed": self.v if self.moving() else 0.0, "lane": self.lane_id, "s": self.s, "vclass": "pedestrian",
                "index": 0, "type": "pedestrian", "signals": 0, "lat": 0.0}

    def moving(self):
        return self.go_at is not None and not self.gone


class Walkers:
    """The run's walkers: the director's helper (scenario_director.Director holds one)."""

    def __init__(self, net, actors, dt=0.1):
        self.dt = float(dt)
        self.all = [Walker(net, a) for a in actors]
        self.contacts = []                                                     # [(t, walker id)]: the ego's box on a walker's

    def extend(self, lanemap):
        """Add the virtual crosswalks and their zones to the run's lane map (sumo_host, before the perception is built)."""
        for w in self.all:
            lanemap.lanes[w.lane_id] = w.lane()
            lanemap.zones.extend(w.zones)

    def tick(self, t, ego_dist, ego_v):
        """EGO_DIST(edge, pos): the ego's driving distance to a point (the director's _dist); arm, start, walk, end."""
        for w in self.all:
            if w.gone:
                continue
            if w.go_at is None:
                if w.fired is None:
                    d = ego_dist(w.edge, w.pos)
                    if d is not None and d >= 0 and ((w.tta and d / max(ego_v, 0.1) <= w.tta) or (w.dist and d <= w.dist)):
                        w.fired = round(t, 2)
                if w.fired is not None and t >= w.fired + w.after - 1e-9:
                    w.go_at = round(t, 2)
                continue
            w.s += w.v * self.dt
            if w.s > w.length:
                w.gone = True

    def truth(self):
        return {w.id: w.pose() for w in self.all if not w.gone}

    def touching(self, ego, t):
        """The walkers whose box the ego's box (EGO: x, y centre, heading, length, width) overlaps: a collision each new contact."""
        from cr_world import box, overlap
        mine = box(ego["x"], ego["y"], ego["heading"], ego["length"], ego["width"])
        out = []
        for w in self.all:
            if w.gone:
                continue
            p = w.pose()
            if overlap(mine, box(p["x"], p["y"], p["heading"], p["length"], p["width"])):
                out.append(w.id)
                if not self.contacts or self.contacts[-1][1] != w.id or t - self.contacts[-1][0] > 1.0:
                    self.contacts.append((round(t, 2), w.id))
        return out

    def report(self):
        return {w.id: {"fired": w.fired, "go_at": w.go_at, "crossed": w.gone, "zebra": w.zebra, "length_m": round(w.length, 1)}
                for w in self.all}
