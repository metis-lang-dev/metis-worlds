"""cr_world — a CommonRoad scenario on SUMO (commonroad-world s-9b7591fb step 1; road/docs/commonroad.md): the scenario kind
`cr:<scenario id>`, a sibling of the cards' `card:` (scenario_director), under sumo_world.SumoWorld.

    scenario name: cr:ID          e.g. cr:ZAM_Tjunction-1_100_T-1
    build(name, work, seed) → (net, routes, script, director)     sumo_world.SCENARIOS' contract, plus the director

The Live's venv never imports CommonRoad: it reads the CACHE (../.worlds/cr-cache/ID/: the SUMO net and cr.json, the interface,
version CR_JSON_VERSION), which road/tools/cr_convert.py writes in the conversion venv (road/.venv-cr); a scenario not yet
in the cache is converted once, here, by running that tool (COMMONROAD_CONVERT_PY, default road/.venv-cr/bin/python).

- The ego: the planning problem's initial state (its centre, heading, speed at its time step), on the nearest lane whose
  heading is within EGO_HEADING_DEG of it; its route the net's shortest way to the goal's lanelet's edge (cr.json `edges`:
  edge → its lanelets), else to the edge nearest the goal region; it arrives (SUMO removes it) at that edge's end.
- The obstacles: every recorded one (cr.json `obstacles`: the trajectory by time step) is a SUMO vehicle of its kind's vClass
  and its own length and width, added at its first step and put at its recorded pose each step (moveToXY, keepRoute 2: the
  recording is the truth, not SUMO's car following), removed after its last; a static one stays at its pose.
- The measures (`cr` in report(); the Leaderboard's beside them): goal reached (the ego's centre in a goal region, its time
  step in the goal's window and its speed and heading in the goal's intervals when it has them) and the position alone,
  contact (the ego's box against every obstacle's recorded box, CommonRoad's own test: SUMO's collisions are kept too),
  off-lanelet (the ego's centre outside every lanelet's polygon: ticks and metres). A scenario file has no cost function
  (that is the benchmark id's): none is computed."""
import json
import math
import os
import subprocess
import sys
from pathlib import Path

CR_JSON_VERSION = 3
MIN_ROUTE_M = 5.0                                      # a route shorter than this is no route to the goal
ROAD = Path(__file__).resolve().parents[1]
# outside road/ (the workspace's .worlds/cr-cache): the Live walks its catalog root, road/, about 10 times a tick, and a cache of
# the whole catalog under it made a tick 1.6 s (cr-harvest s-f4e297da)
CACHE = Path(os.environ.get("COMMONROAD_CACHE", str(ROAD.parents[1] / ".worlds" / "cr-cache")))
CONVERT = ROAD / "tools" / "cr_convert.py"
EGO = "ego"
EGO_HEADING_DEG = 45.0       # the ego's lane: the nearest within this of its heading
LANE_SEARCH_M = 6.0          # how far from the ego's start a lane is looked for
VCLASS = {"car": "passenger", "truck": "truck", "bus": "bus", "bicycle": "bicycle", "motorcycle": "motorcycle",
          "pedestrian": "pedestrian", "priorityVehicle": "emergency", "train": "rail", "taxi": "taxi"}


def _sumolib():
    sys.path.append(os.path.join(os.environ.get("SUMO_HOME", "/usr/share/sumo"), "tools"))
    import sumolib
    return sumolib


def scenario_id(name):
    return name[3:] if name.startswith("cr:") else name


def load(sid, cache=CACHE, convert=True):
    """cr.json of SID, converting it once into the cache when it is not there (the conversion venv's tool)."""
    meta = Path(cache) / sid / "cr.json"
    stale = meta.is_file() and json.loads(meta.read_text()).get("version") != CR_JSON_VERSION
    if (not meta.is_file() or stale) and convert:          # a cache of an older version is converted again, once
        if stale:
            meta.unlink()
        py = os.environ.get("COMMONROAD_CONVERT_PY", str(ROAD / ".venv-cr" / "bin" / "python"))
        if not os.path.exists(py):
            raise RuntimeError("cr:%s is not in the cache %s and there is no conversion venv at %s: road/setup-commonroad.sh" % (sid, cache, py))
        r = subprocess.run([py, str(CONVERT), sid, "--cache", str(cache)], capture_output=True, text=True)
        if r.returncode != 0:
            raise RuntimeError("cr:%s: the conversion failed: %s" % (sid, (r.stderr or r.stdout).strip()[-600:]))
    doc = json.loads(meta.read_text())
    if doc.get("version") != CR_JSON_VERSION:
        raise RuntimeError("cr:%s: cr.json version %s, this world reads %d: convert again (cr_convert.py --force)" % (sid, doc.get("version"), CR_JSON_VERSION))
    return doc


# ── geometry (the Live's venv: no shapely) ──

def inside(pt, poly):
    """Whether point PT is inside polygon POLY (its vertices; ray casting)."""
    x, y = pt
    n, hit = len(poly), False
    for i in range(n):
        x1, y1 = poly[i]
        x2, y2 = poly[(i + 1) % n]
        if (y1 > y) != (y2 > y) and x < (x2 - x1) * (y - y1) / ((y2 - y1) or 1e-12) + x1:
            hit = not hit
    return hit


def box(x, y, theta, length, width):
    c, s, hl, hw = math.cos(theta), math.sin(theta), 0.5 * length, 0.5 * width
    return [(x + c * a - s * b, y + s * a + c * b) for a, b in ((hl, hw), (-hl, hw), (-hl, -hw), (hl, -hw))]


def overlap(p, q):
    """Two convex polygons overlap (separating axes)."""
    for poly in (p, q):
        for i in range(len(poly)):
            (x1, y1), (x2, y2) = poly[i], poly[(i + 1) % len(poly)]
            ax, ay = y1 - y2, x2 - x1
            a = [ax * x + ay * y for x, y in p]
            b = [ax * x + ay * y for x, y in q]
            if max(a) < min(b) or max(b) < min(a):
                return False
    return True


def lanelet_polygon(la):
    return [tuple(v) for v in la["left"]] + [tuple(v) for v in reversed(la["right"])]


def centroid(poly):
    return (sum(x for x, _ in poly) / len(poly), sum(y for _, y in poly) / len(poly))


def at(traj, k):
    """The recorded state at (fractional) step K, linear between steps; None outside the trajectory."""
    if not traj or k < traj[0]["k"] - 1e-9 or k > traj[-1]["k"] + 1e-9:
        return None
    lo = 0
    while lo + 1 < len(traj) and traj[lo + 1]["k"] <= k:
        lo += 1
    a = traj[lo]
    if lo + 1 >= len(traj) or traj[lo + 1]["k"] == a["k"]:
        return a
    b = traj[lo + 1]
    f = (k - a["k"]) / (b["k"] - a["k"])
    dth = math.atan2(math.sin((b["theta"] or 0) - (a["theta"] or 0)), math.cos((b["theta"] or 0) - (a["theta"] or 0)))
    return {"k": k, "x": a["x"] + f * (b["x"] - a["x"]), "y": a["y"] + f * (b["y"] - a["y"]),
            "theta": (a["theta"] or 0) + f * dth, "v": (a["v"] or 0) + f * ((b["v"] or 0) - (a["v"] or 0))}


# ── the placement ──

def ego_lane(net, x, y, theta):
    """The lane the ego starts on: the nearest within LANE_SEARCH_M whose heading at the point is within EGO_HEADING_DEG.
    → (lane, position of the centre on it)."""
    best = None
    for lane, d in net.getNeighboringLanes(x, y, LANE_SEARCH_M, includeJunctions=False):
        pos, _ = lane.getClosestLanePosAndDist((x, y))
        shape = lane.getShape()
        h = None
        run = 0.0
        for (x1, y1), (x2, y2) in zip(shape, shape[1:]):
            seg = math.hypot(x2 - x1, y2 - y1)
            if run + seg >= pos or (x2, y2) == shape[-1]:
                h = math.atan2(y2 - y1, x2 - x1)
                break
            run += seg
        if h is None or abs(math.degrees(math.atan2(math.sin(h - theta), math.cos(h - theta)))) > EGO_HEADING_DEG:
            continue
        if best is None or d < best[2]:
            best = (lane, pos, d)
    if best is None:
        raise RuntimeError("cr: no lane within %.0f m of the ego's start (%.1f, %.1f) heading its way" % (LANE_SEARCH_M, x, y))
    return best[0], best[1]


def lanelet_poly(la):
    return [tuple(p) for p in la["left"]] + [tuple(p) for p in reversed(la["right"])]


def lanelets_at(doc, x, y):
    """The scenario's lanelets whose polygon holds (x, y)."""
    return [la for la in doc.get("lanelets") or () if inside((x, y), lanelet_poly(la))]


def _net_lane(net, lid):
    try:
        return net.getLane(lid) if lid and net.hasEdge(lid.rpartition("_")[0]) else None
    except Exception:                                                    # noqa: BLE001 — merged away by netconvert
        return None


def nearest_in_net(doc, net, la_id, first="predecessors", depth=3):
    """A lanelet's SUMO lane through `lanelet_lane`, or, when netconvert folded it into a junction (an intersection's
    lanelet becomes an internal lane), the nearest lanelet along FIRST then the other way whose lane the net has.
    → (lane, steps along, which way) or None."""
    lanes = doc.get("lanelet_lane") or {}
    by_id = {la["id"]: la for la in doc.get("lanelets") or ()}
    other = "successors" if first == "predecessors" else "predecessors"
    lane = _net_lane(net, lanes.get(str(la_id)))
    if lane is not None:
        return lane, 0, None
    for way in (first, other):
        frontier, seen = [la_id], {la_id}
        for step in range(1, depth + 1):
            frontier = [n for f in frontier for n in (by_id.get(f) or {}).get(way, []) if n not in seen]
            seen.update(frontier)
            for n in frontier:
                lane = _net_lane(net, lanes.get(str(n)))
                if lane is not None:
                    return lane, step, way
    return None


def start_lane(net, doc, x, y, theta):
    """The ego's start through the converter's lanelet -> lane map (cr.json `lanelet_lane`): the lanelet holding the start,
    its SUMO lane; a start inside a junction (its lanelet an internal lane) begins at the END of the lane leading into it,
    or at the start of the one leaving it. None: ego_lane's geometry then."""
    for la in lanelets_at(doc, x, y):
        got = nearest_in_net(doc, net, la["id"], first="predecessors")
        if got is None:
            continue
        lane, step, way = got
        if step == 0:
            pos, _ = lane.getClosestLanePosAndDist((x, y))
        else:
            pos = max(0.0, lane.getLength() - 1.0) if way == "predecessors" else 0.5
        return lane, pos
    return None


def goal_edge(net, doc, goal, start=None):
    """The edge the ego's route ends on: of the goal's lanelets' edges (cr.json `edges`), the one farthest along a way from START
    (a goal of several regions down a road: the route passes through them all), else the edge nearest the goal region's centre."""
    of = {la: e for e, las in doc["edges"].items() for la in las}
    of.update({int(la): e for la, e in (doc.get("lanelet_edge") or {}).items()})     # the converter's own map first
    cands = []
    goal_lanelets = list(goal.get("lanelets") or ())
    for poly in goal.get("polygons") or ():                                         # a region with no lanelets named
        cx, cy = centroid(poly)
        goal_lanelets += [la["id"] for la in lanelets_at(doc, cx, cy) if la["id"] not in goal_lanelets]
    for la in goal_lanelets:                                   # a goal lanelet folded into a junction: the edge leaving it
        got = nearest_in_net(doc, net, la, first="successors") if doc.get("lanelet_lane") else None
        if got is not None and got[0].getEdge() not in cands:
            cands.append(got[0].getEdge())
            continue
        e = of.get(la)
        if e is not None and net.hasEdge(str(e)):
            cands.append(net.getEdge(str(e)))
    for poly in goal.get("polygons") or ():        # the converter's edge map loses the edges netconvert merged: the region's own edge too
        cx, cy = centroid(poly)
        near = [ed for ed, _ in sorted(net.getNeighboringEdges(cx, cy, 6.0), key=lambda x: x[1]) if not ed.getID().startswith(":")]
        if near and near[0] not in cands:
            cands.append(near[0])
    if cands:
        if start is None:
            return cands[0]
        far = None
        for ed in cands:
            path, cost = net.getShortestPath(start, ed, vClass="passenger") if ed.getID() != start.getID() else ([start], 0.0)
            if path and (far is None or cost > far[1]):
                far = (ed, cost)
        return far[0] if far else cands[0]
    polys = goal.get("polygons") or []
    if not polys:
        return None
    cx, cy = centroid(polys[0])
    near = sorted(net.getNeighboringEdges(cx, cy, 15.0), key=lambda ed: ed[1])
    return near[0][0] if near else None


def has_position(goal):
    return bool(goal.get("polygons") or goal.get("lanelets"))


def drive_on(net, start, limit=60):
    """A time-only goal (no region: CommonRoad's goal is the time window, with speed and heading when given): the ego drives
    on, its route to the edge farthest reachable from START by the net's shortest ways (LIMIT edges searched)."""
    import heapq
    best, dist, todo = (start, 0.0), {start.getID(): 0.0}, [(0.0, start.getID(), start)]
    while todo and len(dist) < limit:
        d, _, e = heapq.heappop(todo)
        if d > best[1]:
            best = (e, d)
        for nxt in e.getOutgoing():
            if nxt.getFunction() == "internal" or not nxt.allows("passenger"):
                continue
            nd = d + nxt.getLength()
            if nd < dist.get(nxt.getID(), float("inf")):
                dist[nxt.getID()] = nd
                heapq.heappush(todo, (nd, nxt.getID(), nxt))
    return best[0]


def place(doc, net):
    pp = doc["planning"][0]
    s0 = pp["initial"]
    lane, pos = start_lane(net, doc, s0["x"], s0["y"], s0["theta"] or 0.0) or ego_lane(net, s0["x"], s0["y"], s0["theta"] or 0.0)
    edge = lane.getEdge()
    goal = pp["goals"][0] if pp["goals"] else {}
    timed = bool(goal) and not has_position(goal)
    to = drive_on(net, edge) if timed else goal_edge(net, doc, goal, edge)
    route, why = [edge.getID()], ("a time-only goal: the ego drives on" if timed else None)
    if to is not None and to.getID() != edge.getID():
        path, _ = net.getShortestPath(edge, to, vClass="passenger")
        if path:
            route = [e.getID() for e in path]
        else:
            why = "no way from %s to the goal's edge %s" % (edge.getID(), to.getID())
    elif to is None:
        why = "no edge at the goal region"
    length = sum(net.getEdge(e).getLength() for e in route) - pos
    if goal and not timed and length < MIN_ROUTE_M:
        # a route of a few metres "arrives" at once and reads as the family's: the world's fault, said as one (the ruling)
        raise RuntimeError("cr: no goal edge: the route is %.1f m (%s)" % (length, why or "the goal's edge is the start's"))
    return {"ego": {"lane": lane.getIndex(), "edge": edge.getID(), "pos": pos, "v": s0["v"] or 0.0, "k0": s0["k"], "route": route},
            "goal_edge": to.getID() if to is not None else None, "route_note": why}


def build(name, work, seed=1, **_):
    sid = scenario_id(name)
    doc = load(sid)
    net_path = str(CACHE / sid / doc["net"])
    net = _sumolib().net.readNet(net_path)
    pl = place(doc, net)
    from semantic_world.lane import VCLASS as BOUNDS             # the ego's bounds are the family's, as the cards' (scenario_director.build)
    b = BOUNDS["passenger"]
    e = pl["ego"]
    length = 4.5
    rows = ['<routes>',
            '<vType id="ego_t" accel="%.1f" decel="%.1f" emergencyDecel="%.1f" sigma="0" maxSpeed="40" length="%.1f" width="1.8"/>'
            % (b["accel"], b["brake_max"], max(b["brake_max"], 9.0), length)]
    rows += ['<vType id="cr_%s" vClass="%s" sigma="0" maxSpeed="50"/>' % (k, v) for k, v in sorted(VCLASS.items())]
    rows.append('<vType id="cr_static" vClass="passenger" sigma="0" maxSpeed="1"/>')
    lane_len = net.getEdge(e["edge"]).getLanes()[e["lane"]].getLength()
    front = min(lane_len, e["pos"] + 0.5 * length)                 # SUMO's position is the front bumper; CommonRoad's the centre
    # insertionChecks none: the scenario puts the ego there at that speed; SUMO's own checks (a junction too close to
    # stop for, a leader too near) refused it and the run never began (DEU_Ffb-2_*: "the ego was not inserted")
    rows.append('<vehicle id="%s" type="ego_t" depart="0" departLane="%d" departPos="%.2f" departSpeed="%.2f" insertionChecks="none"><route edges="%s"/></vehicle>'
                % (EGO, e["lane"], front, max(0.0, e["v"]), " ".join(e["route"])))
    rows.append("</routes>")
    routes = os.path.join(work, "cr_%s.rou.xml" % sid)
    with open(routes, "w") as f:
        f.write("\n".join(rows) + "\n")
    return net_path, routes, [], Director(doc, pl, net)


class Director:
    """The recorded obstacles played, and the CommonRoad measures taken, before each SUMO step (SumoWorld.step)."""

    def __init__(self, doc, placed, net):
        self.doc, self.pl = doc, placed
        self.dt = float(doc.get("dt") or 0.1)
        self.k0 = placed["ego"]["k0"]
        self.obstacles = doc["obstacles"]
        self.added, self.gone = set(), set()
        self.lanelets = [lanelet_polygon(la) for la in doc["lanelets"]]
        pp = doc["planning"][0]
        self.goals = []
        for g in pp["goals"]:
            polys = [[tuple(v) for v in p] for p in g.get("polygons") or []]
            if not polys:                                               # a goal by lanelets alone: their polygons
                ids = set(g.get("lanelets") or ())
                polys = [lanelet_polygon(la) for la in doc["lanelets"] if la["id"] in ids]
            self.goals.append(dict(g, polys=polys))
        self.route_m = max(1.0, sum(net.getEdge(x).getLength() for x in placed["ego"]["route"]) - placed["ego"]["pos"])   # from the ego's start
        self.goal_pos_t = self.goal_t = None
        self.t_now = None
        self.off_first_t = None
        self.contacts, self.off_ticks, self.off_m, self.driven = [], 0, 0.0, 0.0
        self.last_xy, self.removed, self.errors = None, [], []

    @property
    def goal_polys(self):
        """The goal regions in the net's frame (cr.json's frame + netconvert's netOffset), for the page's view."""
        ox, oy = (self.doc.get("net_offset") or [0.0, 0.0])[:2]
        return [[[round(x + ox, 2), round(y + oy, 2)] for x, y in p] for g in self.goals for p in g["polys"]]

    def live(self):
        """The measures so far, small, for the page's scene frame (ten a second)."""
        return {"goal_t": self.goal_t, "goal_position_t": self.goal_pos_t,
                "window_s": [[round((w[0] - self.k0) * self.dt, 1), round((w[1] - self.k0) * self.dt, 1)] for w in (g.get("time") for g in self.goals) if w],
                "contacts": len(self.contacts), "off_lanelet_m": round(self.off_m, 1)}

    def k(self, t):
        return self.k0 + t / self.dt

    def _ego(self, c):
        if EGO not in c.vehicle.getIDList():
            return None
        x, y = c.vehicle.getPosition(EGO)
        h = math.radians(90.0 - c.vehicle.getAngle(EGO))
        h = math.atan2(math.sin(h), math.cos(h))                         # (-pi, pi], CommonRoad's orientation
        L = c.vehicle.getLength(EGO)
        return {"x": x - 0.5 * L * math.cos(h), "y": y - 0.5 * L * math.sin(h), "theta": h, "v": c.vehicle.getSpeed(EGO),
                "length": L, "width": c.vehicle.getWidth(EGO)}

    def tick(self, c, t):
        k = self.k(t)
        ids = set(c.vehicle.getIDList())
        for o in self.obstacles:
            vid = "cr%s" % o["id"]
            s = at(o["trajectory"], k)
            if s is None and len(o["trajectory"]) == 1 and k >= o["trajectory"][0]["k"]:
                s = o["trajectory"][0]                                   # a static obstacle: its pose for good
            if s is None or s["x"] is None:
                if vid in self.added and vid not in self.gone and k > o["trajectory"][-1]["k"]:
                    if vid in ids:
                        c.vehicle.remove(vid)
                    self.gone.add(vid)
                continue
            L, W, th = float(o["length"] or 4.5), float(o["width"] or 1.8), float(s["theta"] or 0.0)
            fx, fy = s["x"] + 0.5 * L * math.cos(th), s["y"] + 0.5 * L * math.sin(th)
            try:
                if vid not in self.added:
                    edge = self._edge_near(c, s["x"], s["y"])
                    rid = "r_" + vid
                    c.route.add(rid, [edge])
                    typ = "cr_" + o["type"] if o["type"] in VCLASS else "cr_static"
                    c.vehicle.add(vid, rid, typeID=typ, depart="now")
                    c.vehicle.setLength(vid, L)
                    c.vehicle.setWidth(vid, W)
                    c.vehicle.setSpeedMode(vid, 0)
                    self.added.add(vid)
                c.vehicle.moveToXY(vid, "", -1, fx, fy, angle=90.0 - math.degrees(th), keepRoute=2)
                c.vehicle.setSpeed(vid, max(0.0, float(s["v"] or 0.0)))
            except Exception as e:                                       # noqa: BLE001 — one obstacle's failure is the report's, not the run's end
                self.errors.append((round(t, 2), vid, str(e)[:120]))
        self._measure(c, t, k)

    def _edge_near(self, c, x, y):
        try:
            r = c.simulation.convertRoad(x, y)
            return r[0] if r and not r[0].startswith(":") else self.pl["ego"]["route"][0]
        except Exception:                                                # noqa: BLE001
            return self.pl["ego"]["route"][0]

    def _measure(self, c, t, k):
        self.t_now = t
        e = self._ego(c)
        if e is None:
            return
        xy = (e["x"], e["y"])
        if self.last_xy is not None:
            step = math.hypot(xy[0] - self.last_xy[0], xy[1] - self.last_xy[1])
            self.driven += step
            if self.lanelets and not any(inside(xy, p) for p in self.lanelets):
                self.off_ticks += 1
                if self.off_first_t is None:
                    self.off_first_t = round(t, 2)
                self.off_m += step
        self.last_xy = xy
        for g in self.goals:
            if g["polys"] and not any(inside(xy, p) for p in g["polys"]):
                continue                                          # a goal with no region: its time, speed, heading alone
            if self.goal_pos_t is None and g["polys"]:
                self.goal_pos_t = round(t, 2)
            ok = all(_in(val, g.get(key)) for key, val in (("time", k), ("velocity", e["v"]), ("orientation", e["theta"])))
            if ok and self.goal_t is None:
                self.goal_t = round(t, 2)
        mine = box(e["x"], e["y"], e["theta"], e["length"], e["width"])
        for o in self.obstacles:
            s = at(o["trajectory"], k)
            if s is None and len(o["trajectory"]) == 1 and k >= o["trajectory"][0]["k"]:
                s = o["trajectory"][0]
            if s is None or s["x"] is None:
                continue
            if overlap(mine, box(s["x"], s["y"], float(s["theta"] or 0.0), float(o["length"] or 4.5), float(o["width"] or 1.8))):
                if not self.contacts or self.contacts[-1][1] != o["id"] or t - self.contacts[-1][0] > 1.0:
                    self.contacts.append((round(t, 2), o["id"]))

    def window_over(self, margin):
        """The early stop (cr-harvest ruling, 2026-11-05): True when the goal is not reached and the run's time is past the
        last goal window's end + MARGIN s; never before that end, never for a goal without a time window."""
        if self.goal_t is not None or self.t_now is None:
            return False
        ws = [g.get("time") for g in self.goals]
        if not ws or any(not w for w in ws):
            return False
        return self.t_now > max((w[1] - self.k0) * self.dt for w in ws) + margin

    def on_collision(self, c, other, t):
        """SUMO's collision with a recorded obstacle: kept in the report; the obstacle stays (the recording plays on)."""

    def report(self):
        windows = [g.get("time") for g in self.goals]
        return {"rc": round(min(100.0, 100.0 * self.driven / self.route_m), 1), "driven_m": round(self.driven, 1), "route_m": round(self.route_m, 1),
                "cr": {"id": self.doc["id"], "goal_reached": self.goal_t is not None, "goal_t": self.goal_t,
                       "goal_position_t": self.goal_pos_t, "goal_window_s": [[round((w[0] - self.k0) * self.dt, 2), round((w[1] - self.k0) * self.dt, 2)]
                                                                            if w else None for w in windows],
                       "contact": bool(self.contacts), "contacts": self.contacts[:10], "off_lanelet_ticks": self.off_ticks,
                       "off_lanelet_m": round(self.off_m, 1), "off_lanelet_first_t": self.off_first_t, "cost": None, "goal_edge": self.pl["goal_edge"], "route_note": self.pl["route_note"],
                       "obstacles": len(self.obstacles), "played": len(self.added), "errors": self.errors[:5]}}


def _in(v, iv):
    return iv is None or v is None or (iv[0] - 1e-6 <= v <= iv[1] + 1e-6)
