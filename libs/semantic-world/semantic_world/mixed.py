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
- The belief store, the tracks, the intents, the association and the danger region are RoadMap's on the lane bins, for
  the vehicles (a detection with a lane and an s).
- PEOPLE (a walker, class pedestrian; a cyclist, class bicycle; a detection with x, y) live on the one graph's cells and
  crosswalk bins, in nav-belief's structure (intent.py): a categorical intent over PEOPLE_INTENTS, its prior by class,
  one bayes.walk per intent at the track's speed (cells a tick: speed · dt / CELL) —
    keep    along its heading (the walk drawn by the places further along it from its last sighting: social force's
            heading term), at its speed; a cyclist keeps harder (lane-following at speed on a sidewalk);
    stop    it stands (a walker who yields to us: a `yielded` reading's source, DESIGN §3.3);
    cross   toward the nearest crosswalk place (the crossing prior);
  the intent updated from the displacement since last seen (p · (L + FLOOR)^TEMPER, as road.py's), the walk's mixture
  predicting the unseen, the visible places where nothing was detected negative evidence, the alive decay.
- The BIRTH PRIOR (DESIGN §10 ruling 2): a never-seen walker at an occlusion boundary is a track before any sighting —
  its belief uniform over the boundary's places, its existence the scene's MASS — predicted like any track, removed
  by the negative evidence when its places come into view empty, taken by the association when a sighting appears
  near it (it is then that walker). Without it a walker that steps out from behind a parked car jumps from no belief
  to a high one; with it the belief that a walker's path meets ours rises through the middle as the boundary nears.
- MEETS (the library computes the belief only; the wc manifest's `at:` quantises it into walker_level / cyclist_level,
  spec/16, the architect's condition (2)): P(a track's path meets the chair's within HORIZON ticks) — its belief
  rolled under its intent mixture, the mass entering the chair's place or path absorbed tick by tick — times its
  existence for an unconfirmed birth. A weight port: weight("meets", (role,)).

One map, one INSTANCE at runtime (the architect's condition (1), 2026-10-29): in the wheelchair composition every
domain that runs (responder, planner, nav, wc) reads this one map. LaneMap.roles stays the lane ROLE BINDER, a binder
over this map's places that writes into the one binding (core's d["binding"]), never a second binding. When the road
members run on the MixedMap (the wc-member subject), road_facts reads its lane roles from this map's binding: that is
where that change lands, with the test that asks for it.

    MixedMap.build(path, lanemap, cells, zones, links, dt, cell)   the map (cells {id: (x, y, zone)}, zones, links)
    MixedMap.from_net(path, net, cell, dt)                          a SUMO net read with walking=True, rasterised
    m.neighbours(place), m.zone_of(place), m.zone_kind(zone), m.xy(place), m.link(z1, z2)
    m.zone_facts() → {atom: 1}                                      zone_kind / curb / ramp / path_width, static
    m.cycle(detections, visible, ego)                               one tick: the vehicles (RoadMap's), the people
    m.birth(name, places, cls, mass)                                a birth prior at an occlusion boundary
    m.meets(track) / m.weight("meets", (role,))                     P(the person's path meets the chair's)
    m.project(k, j) → binding                                       the one binding: lane roles and vru1..vruJ
    m.people_facts(group) → {atom: 1}                               walker_at / cyclist_at / group_at
    m.pairs(lights) → [situation.Pair]                              the people's unstructured pairs, the lane's"""
import math

from . import bayes, road
from .sensing import point_at

CELL = 1.0                                     # metres a cell (a chair's footprint, a walker's step)
KINDS = ("sidewalk", "crossing", "lane", "path", "plaza")
LINKS = ("open", "ramp", "curb")
PASSABLE = ("open", "ramp")
PEOPLE = ("pedestrian", "bicycle")
PEOPLE_INTENTS = ("keep", "stop", "cross")
PEOPLE_PRIORS = {"pedestrian": {"keep": 0.5, "stop": 0.2, "cross": 0.3},
                 "bicycle": {"keep": 0.85, "stop": 0.15, "cross": 0.0}}
WALK = {"pedestrian": {"keep": (0.05, 3.0), "stop": (0.9, 0.0), "cross": (0.1, 2.0)},    # (stay, bias) a step
        "bicycle": {"keep": (0.02, 5.0), "stop": (0.9, 0.0), "cross": (0.1, 2.0)}}
P_TEMPER, P_FLOOR = 0.5, 0.01                  # a walker's motion fits its kernels less than a car's (road.py: 0.5, 0.005)
HORIZON = 20                                   # ticks: meets' default horizon (a scene parameter)


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

    # ── people: placing, the kernels, the cycle ──
    def place_at(self, x, y):
        """The place a point is in: the cell whose square holds it, else a crosswalk bin whose strip holds it (the
        nearest), else None (off the people's graph)."""
        d = self.load()
        c = cell_id(int(math.floor(x / d["cell"])), int(math.floor(y / d["cell"])))
        if c in d["cells"]:
            return c
        best = None
        for lid, ln in sorted(self.lanemap.lanes.items()):
            if ln.function != "crossing" or not ln.shape:
                continue
            dist, s = _seg_dist(x, y, ln.shape)
            if dist <= ln.width / 2 and (best is None or dist < best[0]):
                best = (dist, road.cell(lid, min(s, max(0.0, ln.length - 1e-9))))
        return best[1] if best else None

    def _crossing_places(self, d):
        out = [c for c, (_, _, z) in d["cells"].items() if (d["zones"].get(z) or {}).get("kind") == "crossing"]
        for lid, ln in self.lanemap.lanes.items():
            if ln.function == "crossing" or (d["zones"].get(d["lane_zone"].get(lid, lid)) or {}).get("kind") == "crossing":
                out += ["%s|%d" % (lid, k) for k in range(self.nbins(lid))]
        return sorted(set(out))

    def people_models(self, d, t):
        """{intent: model(belief)} for the person track T: one bayes.walk per PEOPLE_INTENTS at its speed (cells a tick),
        keep drawn along its heading from its last sighting, cross toward the nearest crosswalk place, stop standing."""
        cls = d["things"][t]["class"]
        cell = d["cell"]
        steps = max(0.0, d["speed"].get(t, 0.0)) * d["dt"] / cell
        o, h = (d.get("pos") or {}).get(t), (d.get("heading") or {}).get(t)
        xs = {}

        def xy(p):
            if p not in xs:
                xs[p] = self.xy(p) or (0.0, 0.0)
            return xs[p]
        if o and h is not None:
            hx, hy = math.cos(h), math.sin(h)
            along = (lambda p: -((xy(p)[0] - o["x"]) * hx + (xy(p)[1] - o["y"]) * hy) / cell)
        else:
            along = None
        cross = [xy(p) for p in self._crossing_places(d)]
        to_cross = (lambda p: min(math.hypot(xy(p)[0] - a, xy(p)[1] - b) for a, b in cross) / cell) if cross else None
        out = {}
        for i in PEOPLE_INTENTS:
            stay, bias = WALK.get(cls, WALK["pedestrian"])[i]
            toward = along if i == "keep" else (to_cross if i == "cross" else None)
            w = bayes.walk(self.neighbours, toward, stay=stay, bias=bias or 1.0, speed=steps if i != "stop" else 1.0)
            out[i] = (lambda bel, _w=w: _w(bel, 1))
        return out

    @staticmethod
    def people_mixture(p, ms):
        def model(bel):
            out = {}
            for i in PEOPLE_INTENTS:
                if p.get(i, 0.0) <= 0:
                    continue
                for c, m in ms[i](dict(bel)).items():
                    out[c] = out.get(c, 0.0) + p[i] * m
            z = sum(out.values())
            return {c: m / z for c, m in sorted(out.items())} if z > 0 else bel
        return model

    def _people(self, d):
        return sorted(t for t, v in d["things"].items() if v.get("layer") == "people")

    def birth(self, name, places, cls="pedestrian", mass=0.3, save=True):
        """A birth prior (see the module's doc): the track NAME, never seen, its belief uniform over PLACES (the
        occlusion boundary), its existence MASS (a scene parameter)."""
        d = self.load()
        places = sorted(set(places))
        d["things"][name] = {"class": cls, "of": cls, "layer": "people", "birth": float(mass)}
        d["belief"][name] = {p: 1.0 / len(places) for p in places}
        d["intent"][name] = self._prior(cls, d)
        d["speed"][name] = float(d.get("birth_speed", 1.2))
        d["exists"][name] = 0.0
        if save:
            self.save()
            self.log("birth", track=name, places=len(places), mass=float(mass))

    @staticmethod
    def _prior(cls, d):
        t = dict((d.get("people_priors") or PEOPLE_PRIORS).get(cls) or {i: 1.0 for i in PEOPLE_INTENTS})
        z = sum(max(0.0, t.get(i, 0.0)) for i in PEOPLE_INTENTS) or 1.0
        return {i: max(0.0, t.get(i, 0.0)) / z for i in PEOPLE_INTENTS}

    def cycle(self, detections, visible=(), ego=None, save=True):
        """One tick over the one map: the vehicles (a detection with a lane and an s) through RoadMap's cycle, the people
        (class pedestrian | bicycle, at x, y; speed, heading optional) through the people's (see the module's doc).
        VISIBLE: the places seen into (lane bins and cells). EGO: the chair {"place" | "x", "y", "speed", "path"
        [places ahead], and "lane", "s", "route" when the host projects it on a lane (DESIGN §10 ruling 4)}."""
        d = self.load()
        people = self._people(d)
        held = {t: (d["belief"].pop(t, None), d["intent"].pop(t, None)) for t in people}
        cars = [x for x in detections if x.get("class") not in PEOPLE]
        lane_ego = ego if ego is not None and "lane" in ego else None
        super().cycle(cars, [v for v in visible if not is_cell(v)], lane_ego, save=False)
        for t, (b, i) in held.items():
            if b is not None:
                d["belief"][t] = b
            if i is not None:
                d["intent"][t] = i
        self._people_step(d, [x for x in detections if x.get("class") in PEOPLE], set(visible))
        if ego is not None:
            at = ego.get("place") or (self.place_at(ego["x"], ego["y"]) if "x" in ego else None)
            d["chair"] = {"place": at, "speed": float(ego.get("speed", 0.0)), "path": list(ego.get("path") or ())}
            if at is not None and lane_ego is None:
                d["agent"]["at"] = at
        if save:
            self.save()
        return True

    def _people_step(self, d, dets, visible):
        clock, last, dt = d["clock"], d["last_seen"], d["dt"]
        people = self._people(d)
        for t in people:                               # predict under the intent mixture
            if d["belief"].get(t):
                d["belief"][t] = self.people_mixture(d["intent"][t], self.people_models(d, t))(d["belief"][t])
        placed = [(x, self.place_at(float(x["x"]), float(x["y"]))) for x in dets]
        placed = [(x, p) for x, p in placed if p is not None]
        sub = {"things": {t: d["things"][t] for t in people}, "belief": {t: d["belief"].get(t) or {} for t in people}}

        def radius(t):
            gap = clock - (last.get(t) or (None, clock))[1]
            return 1 + int(math.ceil(max(1.0, d["speed"].get(t, 0.0)) * dt * max(1, gap) / d["cell"] * 1.5))
        named = bayes.associate(sub, [(x["class"], p) for x, p in placed], self.neighbours, radius,
                                kind_of=lambda t: sub["things"][t]["class"] if t in sub["things"] else t) if placed else []
        seen = {}
        for (t, c), (x, _) in zip(named, placed):
            if t not in d["things"]:
                d["things"][t] = {"class": x["class"], "of": x["class"], "layer": "people"}
                d["intent"][t] = self._prior(x["class"], d)
            elif d["things"][t].get("birth") is not None:          # a birth prior's walker, seen: it is that walker
                d["things"][t].pop("birth")
                self.log("born", track=t, at=c)
            c1, t0 = last.get(t) or (None, clock)
            p0 = (d.get("pos") or {}).get(t)
            if x.get("heading") is not None:
                d.setdefault("heading", {})[t] = float(x["heading"])
            elif p0 is not None and (x["x"], x["y"]) != (p0["x"], p0["y"]):
                d.setdefault("heading", {})[t] = math.atan2(float(x["y"]) - p0["y"], float(x["x"]) - p0["x"])
            if c1 is not None and clock > t0:                         # the intent from the displacement
                ms = self.people_models(d, t)
                post = {}
                for i in PEOPLE_INTENTS:
                    bel = {c1: 1.0}
                    for _ in range(clock - t0):
                        bel = ms[i](bel)
                    post[i] = d["intent"][t].get(i, 0.0) * (bel.get(c, 0.0) + P_FLOOR) ** P_TEMPER
                z = sum(post.values())
                if z > 0:
                    d["intent"][t] = {i: round(v / z, 6) for i, v in post.items()}
            d["belief"][t] = {c: 1.0}
            d.setdefault("pos", {})[t] = {"x": float(x["x"]), "y": float(x["y"])}
            d["speed"][t] = float(x.get("speed", d["speed"].get(t, 0.0)))
            d["exists"][t] = min(4.0, d["exists"].get(t, 0.0) + 1.0)
            last[t] = [c, clock]
            seen[t] = c
        for t in self._people(d):                      # negative evidence and the alive decay on the unseen
            if t in seen or not d["belief"].get(t):
                continue
            bel = {c: m for c, m in d["belief"][t].items() if c not in visible}
            if len(bel) < len(d["belief"][t]):
                z = sum(bel.values())
                d["belief"][t] = {c: m / z for c, m in bel.items()} if z > 0 else {}
            if d["things"][t].get("birth") is None:
                d["exists"][t] = d["exists"].get(t, 0.0) - road.ALIVE[0]
            if (d["exists"][t] < road.ALIVE[1] or not d["belief"][t]) and t not in (d.get("gone") or ()):
                d["belief"][t] = {}
                d.setdefault("gone", []).append(t)
                self.log("gone", track=t, why="seen empty" if d["things"][t].get("birth") is not None else "faded")
        d["_people_seen"] = sorted(seen)

    # ── meets: the belief a person's path meets the chair's (a weight port; the manifest quantises it) ──
    def meets(self, track, horizon=None, d=None):
        """P(TRACK's path meets the chair's within HORIZON ticks): its belief rolled under its intent mixture, the
        mass that enters the chair's place or path absorbed tick by tick, times its existence while it is an
        unconfirmed birth. 0.0 for a track with no belief, or with no chair."""
        d = d or self.load()
        chair = d.get("chair") or {}
        target = set(chair.get("path") or ()) | ({chair["place"]} if chair.get("place") else set())
        bel = dict(d["belief"].get(track) or {})
        if not target or not bel:
            return 0.0
        h = int(horizon if horizon is not None else d.get("horizon", HORIZON))
        model = self.people_mixture(d["intent"][track], self.people_models(d, track))
        hit = sum(m for c, m in bel.items() if c in target)
        bel = {c: m for c, m in bel.items() if c not in target}
        for _ in range(h):
            if not bel:
                break
            z = sum(bel.values())
            nxt = model({c: m / z for c, m in bel.items()})
            nxt = {c: m * z for c, m in nxt.items()}
            hit += sum(m for c, m in nxt.items() if c in target)
            bel = {c: m for c, m in nxt.items() if c not in target}
        mass = d["things"][track].get("birth")
        return round(min(1.0, hit) * (mass if mass is not None else 1.0), 6)

    def weight(self, pred, args):
        """meets(role): P(the role's person's path meets the chair's) (meets); else core's (look / where)."""
        if pred == "meets":
            role, = args
            return self.meets((self.load().get("binding") or {}).get(role, role))
        return super().weight(pred, args)

    # ── the one binding: the lane roles and the people's, into core's ──
    def project(self, k=3, j=3, lights=None):
        """The one binding (core's d["binding"]): when the host projects the chair on a lane (EGO with a lane, DESIGN
        §10 ruling 4), the lane roles LaneMap.roles binds over the vehicle tracks (lead, follower, …, a1..aK, by its
        rules); and vru1..vruJ for the people, the likeliest to meet the chair first (meets, then the track's name).
        K and J are the capacity's role counts (§12 position 3). → the binding."""
        from .lane import Mover, dynamics_for
        d = self.load()
        out = {}
        ego = d.get("ego")
        if ego is not None and ego.get("lane") in self.lanemap.lanes:
            em = Mover("ego", ego["lane"], float(ego["s"]), dynamics_for("pedestrian", v=ego.get("speed", 0.0), ego=True),
                       route=ego.get("route"), length=0.9, width=0.7, vclass="pedestrian")
            movers = []
            for t, p in sorted((d.get("pos") or {}).items()):
                th = d["things"].get(t) or {}
                if th.get("layer") == "people" or "lane" not in p or not d["belief"].get(t):
                    continue
                movers.append(Mover(t, p["lane"], p["s"], dynamics_for(th.get("class", "passenger"), v=d["speed"].get(t, 0.0)),
                                    length=th.get("length", 4.5), width=th.get("width", 1.8), vclass=th.get("class", "passenger")))
            out.update(self.lanemap.roles(em, movers, k=k, j=0, lights=lights))
        people = [t for t in self._people(d) if d["belief"].get(t)]
        ranked = sorted(people, key=lambda t: (-self.meets(t, d=d), t))
        for n, t in enumerate(ranked[:j]):
            out["vru%d" % (n + 1)] = t
        if out != d.get("binding"):
            d["binding"] = out
            self.save()
            self.log("project", binding=out)
        return dict(out)

    def roles(self):
        return set((self.load().get("binding") or {}).keys())

    # ── the situation layer's pairs: the people's unstructured, the lane's when the chair is on a lane ──
    RADIUS = {"chair": 0.45, "pedestrian": 0.3, "bicycle": 0.9}     # half a body's length (m): the discs' gap

    def pairs(self, lights=None, chair_class="pedestrian"):
        """→ [situation.Pair] of the chair and every person seen (UNSTRUCTURED, DESIGN §12 position 2: the gap between
        the bodies, the bearing from the chair, each side's class dynamics at its speed), and, when the host projects
        the chair on a lane, LaneMap.pairs over the vehicle tracks (the responder's lane case, unchanged)."""
        from .lane import Mover, dynamics_for
        from .situation import Pair
        d = self.load()
        chair = d.get("chair") or {}
        inv = {h: r for r, h in (d.get("binding") or {}).items()}
        cxy = self.xy(chair["place"]) if chair.get("place") else None
        ego = dynamics_for(chair_class, v=chair.get("speed", 0.0), ego=True)
        out = []
        if cxy is not None:
            for t in self._people(d):
                p = (d.get("pos") or {}).get(t)
                if p is None or not d["belief"].get(t) or t not in (d.get("_people_seen") or ()):
                    continue
                cls = d["things"][t]["class"]
                dx, dy = p["x"] - cxy[0], p["y"] - cxy[1]
                gap = max(0.0, math.hypot(dx, dy) - self.RADIUS["chair"] - self.RADIUS.get(cls, 0.3))
                out.append(Pair("%s:unstructured" % t, "unstructured", d_lon=gap, ego=ego,
                                obj=dynamics_for(cls, v=d["speed"].get(t, 0.0)), role=inv.get(t),
                                bearing=math.atan2(dy, dx)))
        e = d.get("ego")
        if e is not None and e.get("lane") in self.lanemap.lanes:
            em = Mover("ego", e["lane"], float(e["s"]), ego, route=e.get("route"), length=0.9, width=0.7,
                       vclass=chair_class)
            movers = []
            for t, p in sorted((d.get("pos") or {}).items()):
                th = d["things"].get(t) or {}
                if th.get("layer") == "people" or "lane" not in p or not d["belief"].get(t):
                    continue
                movers.append(Mover(t, p["lane"], p["s"], dynamics_for(th.get("class", "passenger"), v=d["speed"].get(t, 0.0)),
                                    length=th.get("length", 4.5), width=th.get("width", 1.8), vclass=th.get("class", "passenger")))
            out += self.lanemap.pairs(em, movers, role_of=lambda o: inv.get(o.id), lights=lights)
        return out

    # ── the people's readings ──
    def people_facts(self, group=3):
        """walker_at(R, Z) / cyclist_at(R, Z) for every bound person (the zone of its likeliest place), group_at(Z) for
        a zone where GROUP or more people are likeliest (a scene parameter, DESIGN §3.3). → {atom: 1}."""
        d = self.load()
        out, count = {}, {}
        for t in self._people(d):
            bel = d["belief"].get(t)
            if not bel:
                continue
            z = self.zone_of(min(bel.items(), key=lambda x: (-x[1], x[0]))[0])
            count[z] = count.get(z, 0) + 1
        for r, t in sorted((d.get("binding") or {}).items()):
            th = d["things"].get(t) or {}
            bel = d["belief"].get(t)
            if th.get("layer") != "people" or not bel:
                continue
            z = self.zone_of(min(bel.items(), key=lambda x: (-x[1], x[0]))[0])
            out["%s_at(%s,%s)" % ("cyclist" if th["class"] == "bicycle" else "walker", r, z)] = 1
        for z, n in sorted(count.items()):
            if n >= group:
                out["group_at(%s)" % z] = 1
        return out

    # ── the zones' readings (the static part of the mixed host's world.out) ──
    def zone_facts(self, narrow_below=1.6):
        """zone_kind(Z, K) for every zone, curb(Z1, Z2) and ramp(Z1, Z2) for every link of that kind, both ways, and
        path_width(Z, narrow | wide) for a zone that states its width (metres; narrow under NARROW_BELOW, a scene
        parameter: two chairs' width by default, the width a group blocks, DESIGN §3.3)."""
        d = self.load()
        out = {"zone_kind(%s,%s)" % (z, v["kind"]): 1 for z, v in d["zones"].items()}
        for z, v in d["zones"].items():
            if v.get("width") is not None:
                out["path_width(%s,%s)" % (z, "narrow" if float(v["width"]) < narrow_below else "wide")] = 1
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
