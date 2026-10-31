"""road_frames.py — the road page's world/* frames (road-agent s-357becc7 step 1), read off the SUMO host's Loop, which stays the one TraCI
client: world/net (the lanes, the ego's way, the net as the 3D client reads it) and world/scene (the movers as SUMO has them; the roles and the
fold as the ego's belief has them; the command and its cut)."""
import xml.etree.ElementTree as ET

STAGES = ("restrict", "sumo", "perceive", "project", "account")     # the Loop's stages, each tick's seconds
LAND = 100.0          # the land around the road, m: a straight net's boundary has no height, and the client's ground would have no area


def net_json(path):
    """A .net.xml as the 3D client's /network: {net: {location, edge: [{..., lane: [...]}], junction: [...]}}, every value a string."""
    root = ET.parse(path).getroot()
    x0, y0, x1, y1 = (float(v) for v in root.find("location").get("convBoundary").split(","))
    location = dict(root.find("location").attrib, convBoundary="%.2f,%.2f,%.2f,%.2f" % (x0 - LAND, y0 - LAND, x1 + LAND, y1 + LAND))
    edges = [dict(e.attrib, lane=[dict(la.attrib) for la in e.findall("lane")]) for e in root.findall("edge")]
    return {"net": dict(root.attrib, location=location, edge=edges, junction=[dict(j.attrib) for j in root.findall("junction")])}


def net_frame(loop):
    doc = net_json(loop.world.net)
    lanes = [{"id": la["id"], "index": int(la["index"]), "speed": float(la["speed"]), "length": float(la["length"]),
              "shape": [[float(n) for n in p.split(",")] for p in la["shape"].split()]}
             for e in doc["net"]["edge"] for la in e["lane"]]
    route = (loop.prev_truth.get(loop.ego_id) or {}).get("route", [])
    return {"ev": "world/net", "lanes": lanes, "route": route, "dest": loop.level_dest, "scenario": loop.scenario, "seed": loop.seed, "net": doc}


def scene_frame(loop):
    movers = [{"id": k, "x": round(p["x"], 2), "y": round(p["y"], 2), "heading": round(p["heading"], 4), "lane": p["lane"], "s": round(p["s"], 2),
               "speed": round(p["speed"], 2), "class": p["vclass"], "type": p["type"], "length": p["length"], "width": p["width"],
               "signals": p.get("signals", 0)} for k, p in sorted(loop.prev_truth.items())]
    last = loop.log[-1] if loop.log else {}
    fold = loop.proj.get("fold") or {}
    return {"ev": "world/scene", "tick": loop.tick, "t": loop.t, "ego": loop.ego_id, "movers": movers, "roles": loop.proj.get("binding") or {},
            "fold": {"resp_lon": fold.get("resp_lon", "none"), "resp_lat": fold.get("resp_lat", "none")},
            "cmd": last.get("cmd"), "a": last.get("a"), "restricted": loop.restricted, "seen": last.get("seen"), "tracks": last.get("tracks"),
            "arrived": loop.arrived(), "collisions": loop.world.ego_collisions, "violations": len(loop.violations), "optimistic": len(loop.optimistic),
            "ms": round(sum(loop.ms[-1][k] for k in STAGES) * 1000, 1) if loop.ms else None}


def summary_frame(loop):
    """The run at its end, for the dashboard: the summary's plain numbers."""
    return {"ev": "world/summary", **{k: v for k, v in loop.summary().items() if isinstance(v, (int, float, bool))}}
