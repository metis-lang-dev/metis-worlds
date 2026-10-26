"""sumo_perceive.py — the TraCI host's PERCEPTION (road-world s-e812715d step 4, L1 → L2): the world's truth of a step
through the sensing model into the lane adapter's belief, and the belief back out as the movers the situation layer
pairs with the ego. Nothing here talks to SUMO: the truth is sumo_world's {id: pose}.

- SENSE: the ego's sensor (semantic_world.sensing: range, occlusion by the other bodies and the occluders, a seeded
  miss rate) over the bodies near enough to matter (within range + a body length: the rest can neither be seen nor
  block); a detection says the class, lane, s, speed and size, never the id.
- VISIBLE: the cells (5 m bins) within range and in line of sight — the belief's negative evidence; only the cells
  near the ego are tested (the net's cell centres are computed once).
- CYCLE: semantic_world.road.RoadMap.cycle(detections, visible, ego).
- MOVERS: one lane.Mover per live track, the stack's view of the world:
    seen this tick   at its exact sighting (lane, s), its speed;
    unseen           at the WORST CASE of its belief's support: the cell nearest ahead of the ego along the ego's
                     way, its front at the cell's near edge (else the likeliest cell), its last speed.
  A Mover's s is its front (SUMO's lane position is the front bumper too); its vclass the belief's class.
  The class's Dynamics (lane.dynamics_for at the track's lane's limit).

    p = Perception(lanemap, sensor, dt); p.step(truth, ego_id) → movers, ego_mover; p.map (the RoadMap)"""
import math
import os
import tempfile

from semantic_world import road, sensing
from semantic_world.lane import Mover, dynamics_for

CLASS = {"pedestrian": "pedestrian"}            # the belief's classes: a walker, else a car (the priors' table)


def belief_class(vclass):
    return CLASS.get(vclass, "passenger")


def ego_route(lanemap, lane, edges):
    """The ego's way as lanes: its lane, then each later edge of its route at the same index (clamped to the
    edge's lanes), the internal lanes between filled in (LaneMap.route_through). An edge the lane map cannot
    reach ends the way there."""
    by_edge = {}
    for l in lanemap.lanes.values():
        if l.edge and not l.internal:
            by_edge.setdefault(l.edge, []).append(l)
    cur = lanemap.lanes[lane]
    if cur.internal or cur.edge not in edges:
        return [lane]
    idx, out = cur.index, [lane]
    for e in edges[edges.index(cur.edge) + 1:]:
        ls = sorted(by_edge.get(e, ()), key=lambda l: l.index)
        if not ls:
            break
        nxt = ls[min(idx, len(ls) - 1)].id
        try:
            out = lanemap.route_through(out + [nxt])
        except ValueError:
            break
    return out


class Perception:
    def __init__(self, lanemap, sensor, dt=0.1, occluders=(), path=None, priors=None):
        self.lanemap, self.sensor, self.dt, self.occluders = lanemap, sensor, float(dt), list(occluders)
        path = path or os.path.join(tempfile.mkdtemp(prefix="road-map-"), "map.json")
        self.map = road.RoadMap.build(path, lanemap, dt=dt, priors=priors)
        self.points = sensing.cell_points(lanemap, road.BIN)
        self.last = {}

    def near(self, ego, poses, pad):
        r = self.sensor.range + pad
        return {k: p for k, p in poses.items() if math.hypot(p[0] - ego.x, p[1] - ego.y) <= r}

    def step(self, truth, ego_id="ego"):
        """One tick of the truth TRUTH {id: pose} (sumo_world.truth). → (movers [lane.Mover], ego lane.Mover), the
        tick's sense recorded in self.last (seen ids, detections, visible cells: the log's and the tests')."""
        e = truth[ego_id]
        ego_b = sensing.Body(e["x"], e["y"], e["heading"], e["length"], e["width"])
        others = {k: p for k, p in truth.items() if k != ego_id and p["lane"] in self.lanemap.lanes}
        bodies = {k: sensing.Body(p["x"], p["y"], p["heading"], p["length"], p["width"])
                  for k, p in others.items() if math.hypot(p["x"] - e["x"], p["y"] - e["y"]) <= self.sensor.range + p["length"]}
        seen = self.sensor.sense(ego_b, bodies, self.occluders, ego_id=ego_id)
        dets = [{"class": belief_class(others[k]["vclass"]), "lane": others[k]["lane"], "s": others[k]["s"],
                 "speed": others[k]["speed"], "length": others[k]["length"], "width": others[k]["width"]} for k in seen]
        pts = {c: xy for c, xy in self.points.items() if abs(xy[0] - e["x"]) <= self.sensor.range and abs(xy[1] - e["y"]) <= self.sensor.range}
        visible = set(self.sensor.visible(ego_b, pts, bodies, self.occluders, ego_id=ego_id))
        seen_cells = {road.cell(x["lane"], x["s"]) for x in dets}
        visible -= seen_cells                         # a cell with a detection in it is no negative evidence
        route = ego_route(self.lanemap, e["lane"], e.get("route") or []) if e["lane"] in self.lanemap.lanes else [e["lane"]]
        ego = {"lane": e["lane"], "s": e["s"], "speed": e["speed"], "route": route, "class": belief_class(e["vclass"])}
        self.map.cycle(dets, sorted(visible), ego)
        self.last = {"seen": seen, "detections": dets, "visible": len(visible), "truth_ids": sorted(others)}
        lane_ = self.lanemap.lanes.get(e["lane"])
        ego_m = Mover(ego_id, e["lane"], e["s"], dynamics_for(e["vclass"], v=e["speed"], lane=lane_, ego=True),
                      route=route, length=e["length"], width=e["width"], vclass=e["vclass"])
        return self.movers(ego_m), ego_m

    def movers(self, ego):
        d = self.map.load()
        seen, out = set(d.get("_seen") or ()), []
        for t in sorted(d["belief"]):
            bel = d["belief"][t]
            if not bel:
                continue
            th, v = d["things"][t], d["speed"].get(t, 0.0)
            if t in seen:
                lane, s = d["pos"][t]["lane"], d["pos"][t]["s"]
            else:
                lane, s = self.worst(ego, bel, th.get("length", 4.5))
            out.append(Mover(t, lane, s, dynamics_for(th["class"], v=v, lane=self.lanemap.lanes.get(lane)),
                             length=th.get("length", 4.5), width=th.get("width", 1.8), vclass=th["class"]))
        return out

    def worst(self, ego, bel, length=4.5):
        """The unseen track's position for the pairs. A Mover's s is its FRONT (its rear s − LENGTH), and the belief's
        cells hold the front's s (a detection's lane position): the support cell nearest ahead of the ego on its way,
        the track's front at that cell's near edge — on the ego's own lane never nearer than its rear touching the
        ego's front; else (nothing of it ahead on the way) its likeliest cell, the front at the cell's far edge (a
        track behind: as near the ego as the cell allows)."""
        best = None
        way = ego.route or [ego.lane]
        for c in bel:
            lane, k = road.of(c)
            front = k * road.BIN
            if self.lanemap.ahead(way, ego.s, lane, front + road.BIN) is None:
                continue
            if lane == ego.lane:
                front = max(front, min(front + road.BIN, ego.s + length))
            dd = self.lanemap.ahead(way, ego.s, lane, front)
            if dd is not None and dd >= 0 and (best is None or dd < best[0]):
                best = (dd, lane, front)
        if best is not None:
            return best[1], best[2]
        c = max(sorted(bel), key=bel.get)
        lane, k = road.of(c)
        return lane, min(self.lanemap.lanes[lane].length, (k + 1) * road.BIN)
