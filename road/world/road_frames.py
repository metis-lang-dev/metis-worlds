"""road_frames.py — the road page's world/* frames (road-agent s-357becc7 step 1), read off the SUMO host's Loop, which stays the one TraCI
client: world/net (the lanes, the ego's way, the net as the 3D client reads it) and world/scene (the movers as SUMO has them; the roles and the
fold as the ego's belief has them; the command and its cut)."""
import math
import xml.etree.ElementTree as ET

from sumo_world import SCENARIOS

STAGES = ("restrict", "sumo", "perceive", "project", "account")     # the Loop's stages, each tick's seconds
LIGHTS_EVERY = 10     # ticks between two readings of the lights: every one costs TraCI calls, a big town has hundreds
LAND = 100.0          # the land around the road, m: margin on every side (a straight net's boundary has no height of its own)


DRAW_TOLERANCE = 0.15   # m: how far a drawn lane may leave the net's shape
DOCS = {}             # net path -> its document for the client
FLOORS = {}           # net path -> the net's lowest point, m: CARLA's big towns lie hundreds of metres up, the client's ground is at 0


def floor_of(path):
    if path not in FLOORS:
        zs = (float(p.split(",")[2]) for la in ET.parse(path).getroot().iter("lane") for p in la.get("shape", "").split() if p.count(",") == 2)
        FLOORS[path] = min(zs, default=0.0)
    return FLOORS[path]


def lowered(shape, floor):
    """A shape's points with the floor taken from their height."""
    def point(p):
        q = p.split(",")
        return ",".join(q[:2] + ["%.2f" % (float(q[2]) - floor)]) if len(q) == 3 else p
    return " ".join(point(p) for p in shape.split())


def simpler(shape, tol=DRAW_TOLERANCE):
    """A lane's shape with the points it can spare (Douglas-Peucker in x, y and height). A town's net has a point every metre or so of road; what is drawn does not need them, and the
    client's time goes with their number. Only the drawing: SUMO and the lane map keep the net's own."""
    pts = [([float(n) for n in p.split(",")] + [0.0])[:3] for p in shape.split()]
    if len(pts) < 3:
        return shape
    keep, todo = {0, len(pts) - 1}, [(0, len(pts) - 1)]
    while todo:
        a, b = todo.pop()
        (ax, ay, az), (bx, by, bz) = pts[a], pts[b]
        length, worst, at = math.hypot(bx - ax, by - ay) or 1e-9, 0.0, None
        for i in range(a + 1, b):
            d = max(abs((bx - ax) * (ay - pts[i][1]) - (ax - pts[i][0]) * (by - ay)) / length, abs(pts[i][2] - az - (bz - az) * (i - a) / (b - a)))
            if d > worst:
                worst, at = d, i
        if worst > tol:
            keep.add(at)
            todo += [(a, at), (at, b)]
    return " ".join("%.2f,%.2f,%.2f" % tuple(pts[i]) for i in sorted(keep))


def net_json(path):
    """A .net.xml as the 3D client's /network: {net: {location, edge: [{..., lane: [...]}], junction: [...]}}, every value a string, what the client draws only: no internal edges
    (it draws the junctions' polygons), the signals' connections alone. Once per net: the page's next hello asks again."""
    if path not in DOCS:
        DOCS[path] = _net_json(path)
    return DOCS[path]


def _net_json(path):
    root = ET.parse(path).getroot()
    x0, y0, x1, y1 = (float(v) for v in root.find("location").get("convBoundary").split(","))
    location = dict(root.find("location").attrib, convBoundary="%.2f,%.2f,%.2f,%.2f" % (x0 - LAND, y0 - LAND, x1 + LAND, y1 + LAND))
    floor = floor_of(path)
    edges = [dict(e.attrib, lane=[dict(la.attrib, shape=simpler(lowered(la.get("shape", ""), floor))) for la in e.findall("lane")]) for e in root.findall("edge")
             if e.get("function", "normal") not in ("internal", "walkingarea")]
    ids = {e["id"] for e in edges}
    logics = [dict(t.attrib, phase=[dict(p.attrib) for p in t.findall("phase")]) for t in root.findall("tlLogic")]
    # the client looks a program's states up by name: `off` (SUMO's own) as one phase of unlit signals
    logics += [{"id": t["id"], "type": "static", "offset": "0", "programID": "off", "phase": [{"duration": "1", "state": "x" * len(t["phase"][0]["state"])}]} for t in list(logics)]
    return {"net": dict(root.attrib, location=location, edge=edges, junction=[dict(j.attrib, shape=lowered(j.get("shape", ""), floor), z="%.2f" % (float(j.get("z", floor)) - floor)) for j in root.findall("junction")],
                        connection=[dict(c.attrib) for c in root.findall("connection") if "tl" in c.attrib and c.get("from") in ids], tlLogic=logics)}


def net_frame(loop):
    doc = net_json(loop.world.net)
    lanes = [{"id": la["id"], "index": int(la["index"]), "speed": float(la["speed"]), "length": float(la["length"])} for e in doc["net"]["edge"] for la in e["lane"]]
    route = (loop.prev_truth.get(loop.ego_id) or {}).get("route", [])
    out = {"ev": "world/net", "lanes": lanes, "route": route, "dest": loop.level_dest, "scenario": loop.scenario, "seed": loop.seed, "net": doc, "scenarios": list(SCENARIOS)}
    d = getattr(loop.world, "director", None)
    if d is not None and hasattr(d, "goal_polys"):                     # a CommonRoad run (cr_world): its goal regions, drawn in the view
        out["goal"] = d.goal_polys
    return out


def scene_frame(loop):
    floor = floor_of(loop.world.net)
    movers = [{"id": k, "x": round(p["x"], 2), "y": round(p["y"], 2), "z": round(p.get("z", floor) - floor, 2), "heading": round(p["heading"], 4), "lane": p["lane"], "s": round(p["s"], 2),
               "speed": round(p["speed"], 2), "class": p["vclass"], "type": p["type"], "length": p["length"], "width": p["width"],
               "signals": p.get("signals", 0)} for k, p in sorted(loop.prev_truth.items())]
    last = loop.log[-1] if loop.log else {}
    fold = loop.proj.get("fold") or {}
    return {"ev": "world/scene", "tick": loop.tick, "t": loop.t, "ego": loop.ego_id, "movers": movers, "roles": loop.proj.get("binding") or {},
            "fold": {"resp_lon": fold.get("resp_lon", "none"), "resp_lat": fold.get("resp_lat", "none")},
            "cmd": last.get("cmd"), "a": last.get("a"), "restricted": loop.restricted, "seen": last.get("seen"), "tracks": last.get("tracks"),
            "arrived": loop.arrived(), "collisions": loop.world.ego_collisions, "violations": len(loop.violations), "unseen_other_duty": len(loop.unseen_duty), "optimistic": len(loop.optimistic),
            "ms": round(sum(loop.ms[-1][k] for k in STAGES) * 1000, 1) if loop.ms else None,
            "lights": loop.world.light_states() if loop.tick % LIGHTS_EVERY == 0 and hasattr(loop.world, "light_states") else None,
            "cr": loop.world.director.live() if hasattr(getattr(loop.world, "director", None), "live") else None}


def summary_frame(loop):
    """The run at its end, for the dashboard: the summary's plain numbers."""
    s = loop.summary()
    out = {"ev": "world/summary", **{k: v for k, v in s.items() if isinstance(v, (int, float, bool))}}
    cr = (s.get("director") or {}).get("cr") if isinstance(s.get("director"), dict) else None
    if cr:                                                              # a CommonRoad run's measures (cr_world.Director.report)
        out["cr"] = {k: cr.get(k) for k in ("goal_reached", "goal_t", "goal_position_t", "goal_window_s", "contact", "off_lanelet_m")}
    return out
