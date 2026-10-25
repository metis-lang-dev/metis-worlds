"""sensing — the road's SENSING MODEL (road-world s-e812715d step 4, the framework brief's L1): what the ego sees of the
world's truth each step. No simulator here: a host (metis-worlds/road's TraCI host) hands in the poses.

- A body is a rectangle: its centre (x, y), heading (radians, 0 = +x), length and width.
- A target is SEEN when it is within RANGE of the ego's centre, the straight line from the ego's centre to the
  target's is not blocked by another body (any vehicle but the two) nor by an occluding polygon (a building, a wall:
  the net's surroundings, given as [(x, y)…]), and a seeded draw passes the detection miss rate.
- A detection names no identity: its class, its lane and s (the host's projection of the target's position onto
  the net), its speed. The ego's VISIBLE cells (the belief's negative evidence) are the cells whose centre is in
  range and in line of sight, by the same test.

    Sensor(range, miss, seed).sense(ego, bodies, occluders) → [body seen]   (bodies: {id: Body}; ego: Body)
    Sensor.visible(ego, points, bodies, occluders) → [key]                   (points: {key: (x, y)})
"""
import math
import random
from dataclasses import dataclass


@dataclass
class Body:
    x: float
    y: float
    heading: float = 0.0
    length: float = 4.5
    width: float = 1.8

    def corners(self):
        c, s = math.cos(self.heading), math.sin(self.heading)
        hl, hw = self.length / 2, self.width / 2
        return [(self.x + dx * c - dy * s, self.y + dx * s + dy * c) for dx, dy in ((hl, hw), (hl, -hw), (-hl, -hw), (-hl, hw))]


def _cross(o, a, b):
    return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])


def segments_cross(p1, p2, q1, q2):
    """Whether the segments p1p2 and q1q2 cross (touching counts)."""
    d1, d2 = _cross(q1, q2, p1), _cross(q1, q2, p2)
    d3, d4 = _cross(p1, p2, q1), _cross(p1, p2, q2)
    if ((d1 > 0) != (d2 > 0)) and ((d3 > 0) != (d4 > 0)) and d1 and d2 and d3 and d4:
        return True

    def on(a, b, c):
        return min(a[0], b[0]) - 1e-9 <= c[0] <= max(a[0], b[0]) + 1e-9 and min(a[1], b[1]) - 1e-9 <= c[1] <= max(a[1], b[1]) + 1e-9
    return (d1 == 0 and on(q1, q2, p1)) or (d2 == 0 and on(q1, q2, p2)) or (d3 == 0 and on(p1, p2, q1)) or (d4 == 0 and on(p1, p2, q2))


def blocks(poly, a, b):
    """Whether the polygon POLY (a closed ring of points) blocks the segment a→b."""
    n = len(poly)
    return any(segments_cross(a, b, poly[i], poly[(i + 1) % n]) for i in range(n))


class Sensor:
    def __init__(self, range=60.0, miss=0.0, seed=1):
        self.range, self.miss = float(range), float(miss)
        self.rnd = random.Random(seed)

    def line_of_sight(self, ego, target, bodies, occluders, skip=()):
        a, b = (ego.x, ego.y), target
        if math.hypot(b[0] - a[0], b[1] - a[1]) > self.range:
            return False
        for k, body in bodies.items():
            if k in skip:
                continue
            if blocks(body.corners(), a, b):
                return False
        return not any(blocks(p, a, b) for p in occluders)

    def sense(self, ego, bodies, occluders=(), ego_id=None):
        """The ids of the bodies seen (in range, in line of sight past the others and the occluders, and the miss
        draw passed), sorted. The ego (EGO_ID) and the target itself never block."""
        out = []
        for k in sorted(bodies):
            if k == ego_id:
                continue
            b = bodies[k]
            if not self.line_of_sight(ego, (b.x, b.y), bodies, occluders, skip=(k, ego_id)):
                continue
            if self.miss and self.rnd.random() < self.miss:
                continue
            out.append(k)
        return out

    def visible(self, ego, points, bodies, occluders=(), ego_id=None):
        """The keys of POINTS {key: (x, y)} in range and in line of sight (no miss draw: what could be seen)."""
        return sorted(k for k, p in points.items() if self.line_of_sight(ego, p, bodies, occluders, skip=(ego_id,)))


def point_at(shape, s):
    """The point at distance S along a polyline SHAPE [(x, y)…] (clamped to its ends)."""
    if not shape:
        return None
    acc = 0.0
    for (x0, y0), (x1, y1) in zip(shape, shape[1:]):
        seg = math.hypot(x1 - x0, y1 - y0)
        if acc + seg >= s and seg > 0:
            f = (s - acc) / seg
            return (x0 + f * (x1 - x0), y0 + f * (y1 - y0))
        acc += seg
    return tuple(shape[-1])


def cell_points(lanemap, bin_m):
    """Every (lane, s-bin) cell's centre on its lane's shape: {"lane|k": (x, y)} (the visible test's points)."""
    out = {}
    for lid, lane in lanemap.lanes.items():
        if not lane.shape:
            continue
        n = max(1, int(math.ceil(lane.length / bin_m)))
        for k in range(n):
            p = point_at(lane.shape, min(lane.length, (k + 0.5) * bin_m))
            if p:
                out["%s|%d" % (lid, k)] = p
    return out
