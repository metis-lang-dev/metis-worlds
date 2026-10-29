"""mixed — the MIXED adapter (wc-world s-db2f8e59 step 2; the wheelchair DESIGN v5 §4, §10 and §12): ONE semantic map
for every domain that runs. Lane SEGMENTS for the roads and the crosswalks, free-space CELLS for the sidewalks, paths,
plazas and walking areas, and the LINKS between them, in one place set, one belief store and one role binding (core's).

- The places. A lane bin `lane|k` is road.RoadMap's, over a lane.LaneMap: k = ⌊s / road.BIN⌋ on the lane's centre
  line. A cell `c<i>_<j>` is a square of CELL metres whose centre is ((i + ½)·CELL, (j + ½)·CELL) in the net's frame.
- The zones. Every place is in one zone {id: {"kind": sidewalk | crossing | lane | path | plaza, …}}: a cell by its
  own zone, a lane bin by its lane's zone (a zone lists its "lanes"). A lane that no zone lists is its own zone, of
  kind lane.
- The links between zones: (z1, z2, kind), kind open | ramp | curb. Two places in DIFFERENT zones connect only through
  an open or a ramp link between their zones. A curb link connects nothing (DESIGN §3.5: it is impassable); it is a
  reading (`curb(Z1, Z2)`), as a ramp is (`ramp(Z1, Z2)`: passable, at `slow`). A scene states its topology: two zones
  with no link do not connect, whatever their geometry.
- The adjacency. Two cells are adjacent when they are 8-neighbours on the grid. A cell and a lane bin are adjacent
  when the cell's centre lies within the lane's half width plus CELL·¾ of the lane's centre line, at an s inside that
  bin. Lane bins keep RoadMap's own graph (along, the side neighbours). The cross-zone and cross-layer pairs are
  computed once at build (`adj`), so `neighbours` is a lookup.
- The belief store, the tracks, the intents, the association and the danger region are RoadMap's on the lane bins.
  People on the cells (intents, levels, the birth prior) and the readings come with the later parts of step 2; this
  part is the geometry.

One map, one INSTANCE at runtime (the architect's condition (1), 2026-10-29): in the wheelchair composition every
domain that runs (responder, planner, nav, wc) reads this one map. LaneMap.roles stays the lane ROLE BINDER, a binder
over this map's places that writes into the one binding (core's d["binding"]), never a second binding. When the road
members run on the MixedMap (the wc-member subject), road_facts reads its lane roles from this map's binding: that is
where that change lands, with the test that asks for it.

    MixedMap.build(path, lanemap, cells, zones, links, dt, cell)   the map (cells {id: (x, y, zone)}, zones, links)
    MixedMap.from_net(path, net, cell, dt)                          a SUMO net read with walking=True, rasterised
    m.neighbours(place), m.zone_of(place), m.zone_kind(zone), m.xy(place), m.link(z1, z2)
    m.zone_facts() → {atom: 1}                                      zone_kind / curb / ramp, the zones' static readings"""
import math

from . import road
from .sensing import point_at

CELL = 1.0                                     # metres a cell (a chair's footprint, a walker's step)
KINDS = ("sidewalk", "crossing", "lane", "path", "plaza")
LINKS = ("open", "ramp", "curb")
PASSABLE = ("open", "ramp")


def cell_id(i, j):
    return "c%d_%d" % (i, j)


def cell_ij(c):
    i, _, j = c[1:].partition("_")
    return int(i), int(j)


def is_cell(place):
    return "|" not in place


def _seg_dist(x, y, shape):
    """(distance, s) from (x, y) to the polyline SHAPE: the nearest point's distance and its s along the line."""
    best, acc = (math.inf, 0.0), 0.0
    for (ax, ay), (bx, by) in zip(shape, shape[1:]):
        dx, dy = bx - ax, by - ay
        L2 = dx * dx + dy * dy
        t = 0.0 if L2 == 0 else max(0.0, min(1.0, ((x - ax) * dx + (y - ay) * dy) / L2))
        d = math.hypot(x - (ax + t * dx), y - (ay + t * dy))
        if d < best[0]:
            best = (d, acc + t * math.sqrt(L2))
        acc += math.sqrt(L2)
    return best


def _inside(x, y, poly):
    """Whether (x, y) is inside the closed ring POLY (even-odd ray casting)."""
    n, inside = len(poly), False
    for k in range(n):
        (ax, ay), (bx, by) = poly[k], poly[(k + 1) % n]
        if (ay > y) != (by > y) and x < ax + (y - ay) * (bx - ax) / (by - ay):
            inside = not inside
    return inside


class MixedMap(road.RoadMap):
    """The one map over lane segments and cells (see the module's doc)."""

    @classmethod
    def build(cls, path, lanemap, cells, zones, links=(), dt=0.1, cell=CELL, priors=None, journal=None):
        """CELLS {cell id: (x, y, zone)} (an id is cell_id(i, j) of its centre), ZONES {id: {"kind", "lanes"?, …}},
        LINKS [(z1, z2, kind)]. → the map, its adjacency computed."""
        m = super().build(path, lanemap, dt=dt, priors=priors, journal=journal)
        zones = {z: dict(v) for z, v in sorted(zones.items())}
        for z, v in zones.items():
            if v.get("kind") not in KINDS:
                raise ValueError("zone %s: kind %r is none of %s" % (z, v.get("kind"), ", ".join(KINDS)))
        lane_zone = {l: z for z, v in zones.items() for l in v.get("lanes") or ()}
        for l in sorted(lanemap.lanes):                # a lane in no zone: its own zone, kind lane
            if l not in lane_zone:
                zones.setdefault(l, {"kind": "lane", "lanes": [l]})
                lane_zone[l] = l
        lk = {}
        for z1, z2, kind in links:
            if kind not in LINKS:
                raise ValueError("link %s–%s: kind %r is none of %s" % (z1, z2, kind, ", ".join(LINKS)))
            for z in (z1, z2):
                if z not in zones:
                    raise ValueError("link %s–%s: no zone %s" % (z1, z2, z))
            lk[tuple(sorted((z1, z2)))] = kind
        m.data.update(cell=float(cell), cells={c: [float(x), float(y), z] for c, (x, y, z) in sorted(cells.items())},
                      zones=zones, lane_zone=lane_zone,
                      links=[[a, b, k] for (a, b), k in sorted(lk.items())])
        for c, (_, _, z) in m.data["cells"].items():
            if z not in zones:
                raise ValueError("cell %s: no zone %s" % (c, z))
        m.data["adj"] = m._adjacency()
        m.save()
        return m

    # ── the geometry ──
    def link(self, z1, z2):
        """The link between two zones (open | ramp | curb), None when there is none; a zone with itself: open."""
        if z1 == z2:
            return "open"
        a, b = sorted((z1, z2))
        for x, y, k in self.load().get("links") or ():
            if (x, y) == (a, b):
                return k
        return None

    def zone_of(self, place):
        d = self.load()
        if is_cell(place):
            return d["cells"][place][2]
        lane, _ = road.of(place)
        return d["lane_zone"].get(lane, lane)

    def zone_kind(self, zone):
        return (self.load()["zones"].get(zone) or {}).get("kind")

    def xy(self, place):
        """A place's centre in the net's frame: a cell's, or a lane bin's point on its lane's centre line (None when the
        lane has no shape)."""
        d = self.load()
        if is_cell(place):
            x, y, _ = d["cells"][place]
            return (x, y)
        lane, k = road.of(place)
        ln = self.lanemap.lanes.get(lane)
        if ln is None or not ln.shape:
            return None
        return point_at(ln.shape, min(ln.length, (k + 0.5) * road.BIN))

    def _adjacency(self):
        """{place: [places]} — the cells' grid neighbours and the cell ↔ lane bin pairs, both kept only where their
        zones connect (the same zone, or an open or ramp link): the cross-zone graph, computed once."""
        d = self.data
        cells, cell = d["cells"], d["cell"]
        adj = {}

        def ok(a, b):
            return self._passable(self._zone(a), self._zone(b))
        for c in cells:
            i, j = cell_ij(c)
            for di in (-1, 0, 1):
                for dj in (-1, 0, 1):
                    n = cell_id(i + di, j + dj)
                    if (di or dj) and n in cells and ok(c, n):
                        adj.setdefault(c, []).append(n)
        for lid, ln in sorted(self.lanemap.lanes.items()):
            if not ln.shape:
                continue
            reach = ln.width / 2 + cell * 0.75
            for c, (x, y, _) in cells.items():
                dist, s = _seg_dist(x, y, ln.shape)
                if dist > reach:
                    continue
                b = road.cell(lid, min(s, max(0.0, ln.length - 1e-9)))
                if not ok(c, b):
                    continue
                adj.setdefault(c, []).append(b)
                adj.setdefault(b, []).append(c)
        return {p: sorted(set(v)) for p, v in sorted(adj.items())}

    def _zone(self, place):
        d = self.data
        if is_cell(place):
            return d["cells"][place][2]
        lane, _ = road.of(place)
        return d["lane_zone"].get(lane, lane)

    def _passable(self, z1, z2):
        if z1 == z2:
            return True
        a, b = sorted((z1, z2))
        return any((x, y) == (a, b) and k in PASSABLE for x, y, k in self.data.get("links") or ())

    def neighbours(self, place):
        """A place's neighbours over the one graph: a cell's (its grid neighbours and the lane bins it touches, where
        the zones connect); a lane bin's (RoadMap's along and side bins, and the cells it touches)."""
        d = self.load()
        extra = (d.get("adj") or {}).get(place, [])
        if is_cell(place):
            return list(extra)
        return list(super().neighbours(place)) + [p for p in extra if p not in super().neighbours(place)]

    def cells_of(self, zone):
        return sorted(c for c, (_, _, z) in self.load()["cells"].items() if z == zone)

    # ── the zones' readings (the static part of the mixed host's world.out) ──
    def zone_facts(self):
        """zone_kind(Z, K) for every zone, curb(Z1, Z2) and ramp(Z1, Z2) for every link of that kind, both ways."""
        d = self.load()
        out = {"zone_kind(%s,%s)" % (z, v["kind"]): 1 for z, v in d["zones"].items()}
        for a, b, k in d.get("links") or ():
            if k in ("curb", "ramp"):
                out["%s(%s,%s)" % (k, a, b)] = 1
                out["%s(%s,%s)" % (k, b, a)] = 1
        return dict(sorted(out.items()))

    # ── from a SUMO net ──
    @classmethod
    def from_net(cls, path, net, cell=CELL, dt=0.1, priors=None, journal=None):
        """A net read with walking=True (net.load_net(path, walking=True)) as the one map: its walking areas
        rasterised into cells (a centre inside the area's polygon), its sidewalks (a normal edge's lane that allows
        pedestrians only) into cells (a centre within the lane's half width of its centre line), the first claim
        winning (walking areas, then sidewalks, by id). Zones: a walking area or a sidewalk lane, kind sidewalk; a
        crosswalk lane, kind crossing; every vehicle lane, kind lane (one zone per lane). Links, from the geometry
        (two zones whose places touch): sidewalk–sidewalk open, sidewalk–crossing ramp, sidewalk–lane curb. The
        vehicle LaneMap (net.lanemap(), the crosswalks added as lanes of their own) carries the segments."""
        lm = net.lanemap()
        walk = {l: ln for l, ln in net.lanes.items() if ln.function in ("crossing", "walkingarea")}
        for l, ln in walk.items():
            if ln.function == "crossing":
                lm.lanes[l] = ln
        side = {l: ln for l, ln in net.lanes.items()
                if ln.function == "normal" and not ln.internal and ln.allow == ("pedestrian",) and ln.shape}
        zones, cells = {}, {}

        def claim(zone, test, xs, ys):
            for i in range(int(math.floor(min(xs) / cell)), int(math.ceil(max(xs) / cell)) + 1):
                for j in range(int(math.floor(min(ys) / cell)), int(math.ceil(max(ys) / cell)) + 1):
                    x, y = (i + 0.5) * cell, (j + 0.5) * cell
                    if cell_id(i, j) not in cells and test(x, y):
                        cells[cell_id(i, j)] = (x, y, zone)
        for l in sorted(l for l, ln in walk.items() if ln.function == "walkingarea" and ln.shape):
            poly = walk[l].shape
            zones[l] = {"kind": "sidewalk"}
            claim(l, lambda x, y, p=poly: _inside(x, y, p), [p[0] for p in poly], [p[1] for p in poly])
        for l in sorted(side):
            ln = side[l]
            zones[l] = {"kind": "sidewalk"}
            hw = ln.width / 2
            claim(l, lambda x, y, s=ln.shape, h=hw: _seg_dist(x, y, s)[0] <= h,
                  [p[0] - hw for p in ln.shape] + [p[0] + hw for p in ln.shape],
                  [p[1] - hw for p in ln.shape] + [p[1] + hw for p in ln.shape])
        for l in sorted(l for l, ln in walk.items() if ln.function == "crossing"):
            zones[l] = {"kind": "crossing", "lanes": [l]}
        for l in sorted(side) + sorted(l for l, ln in walk.items() if ln.function == "walkingarea"):
            lm.lanes.pop(l, None)                      # a sidewalk lane and a walking area are cells, not segments
        for ln in lm.lanes.values():
            ln.succ = [s for s in ln.succ if s in lm.lanes]
            for w in ("left", "right"):
                if getattr(ln, w) not in lm.lanes:
                    setattr(ln, w, None)
        # the links, from the geometry: every pair of zones whose places touch (cells 8-adjacent, a cell on a lane)
        def kind_of(z):
            return zones[z]["kind"] if z in zones else "lane"
        touch = set()
        for c, (x, y, z) in cells.items():
            i, j = cell_ij(c)
            for di in (-1, 0, 1):
                for dj in (-1, 0, 1):
                    n = cells.get(cell_id(i + di, j + dj))
                    if n and n[2] != z:
                        touch.add(tuple(sorted((z, n[2]))))
            for lid, ln in lm.lanes.items():
                if ln.shape and _seg_dist(x, y, ln.shape)[0] <= ln.width / 2 + cell * 0.75:
                    touch.add(tuple(sorted((z, lid))))
        links = []
        for a, b in sorted(touch):
            ka, kb = kind_of(a), kind_of(b)
            if "lane" in (ka, kb):
                links.append((a, b, "curb"))
            elif "crossing" in (ka, kb):
                links.append((a, b, "ramp"))
            else:
                links.append((a, b, "open"))
        return cls.build(path, lm, cells, zones, links, dt=dt, cell=cell, priors=priors, journal=journal)
