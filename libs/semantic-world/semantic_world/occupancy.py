"""occupancy — the mixed map's predict step rendered over a short horizon, for a local planner (wc-motion s-efcc13bf step 2;
the wheelchair's docs/MOTION.md §1, §6.2), and its zones rasterised to a grid aligned to its cells. Numbers and rows only: the
planner over them, and whatever it hands them to, are the host's.

    occupancy.render(m, horizon, step, credible) → Occupancy     a time-indexed occupancy; it reads the map and writes nothing
    occupancy.rasterise(m, factor) → Raster                      the zones and kinds on a grid `factor` to a map cell a side

SOFT, belief × intent × dynamics, per track: P(its body is in a cell at time t).
- An intent persists over the horizon: each intent's kernel is rolled alone, then weighted by p(intent), so keep 0.5, stop 0.5 is
  two blobs and not one at half speed. (`meets` redraws the intent a tick: its thresholds are fitted to that.)
- `stop` stands, and so does every intent of a track at speed 0.
- The people's kernels roll on the cells wherever a crossing has them. A cell's neighbours in the one graph include a crosswalk's
  road.BIN m lane bins, a jump the map's predict keeps; rolled over a horizon it runs at about twice the walker's speed.
- The REACH bound: mass is cut where the track's class cannot get in the time (situation.stated with no brake, from its pose or,
  unseen, from its belief at t = 0). The fractional walk's tails go further than that.
- An unconfirmed birth is its belief × its mass, as `meets`.
- A vehicle's body covers its lane's width over its length, so a bin's mass is every cell under it. A person's body is one cell,
  so a bin's mass (a crosswalk with no cells) is shared among those under it.
The cell ids are the map's grid; those under a lane may lie off the map's cells.

HARD, never enter: the RSS set of the pair the map already forms (the same test as MixedMap.pairs), the chair's side by EGO
(situation.Dynamics at the speed asked about; None: the object's side alone).
- UNSTRUCTURED, a walker or a cyclist off the strips: a disc around each place of the track's CREDIBLE set at t (the smallest
  set holding that much of its mass; at t = 0 a track seen this tick is its pose), radius brake_set(obj) + brake_set(ego) + the
  floor + the two RADIUS. At t = 0 this is check_unstructured: outside it the pair is safe.
- STRIP, a cyclist on a strip beside the chair's: a capsule along its heading from its pose to speed · t ahead, radius the two half
  widths + situation.safe_lat_dist (lemma 4): the pass in the other half stays clear. Its disc would be 11.5 m at 4.5 m/s.
- VEHICLE on a lane: the cells under its body at t, plus the chair's RADIUS. Its disc would be 69.5 m at 11 m/s, and the crossings'
  priority is the responder's, over the structured pair: a car waiting at a red light does not close a walk-signal crossing.
- BIRTH, an unconfirmed birth: none. The epistemic case is the behaviour's (the walker's level).
Never a reach disc over the horizon: RSS's worst case is for a response time, then the check again next tick, so beyond it
the set moves with the prediction; the reach disc at 3 s closes about 8 m around a walker and the chair freezes.

The RASTER. A cell's zone wins; then a lane's strip, lanes by id, where there is no cell. A link is no raster: a zone left out of
the mask is what keeps a chair off a curb. Its origin is a whole number of map cells, so a fine cell's map cell is an integer
division. Rows from the origin, `rows[iy][ix]`."""
import math

from . import mixed, road
from .lane import dynamics_for
from .sensing import point_at
from .situation import brake_set, safe_lat_dist, stated

CREDIBLE = 0.9                                 # the mass a track's hard set is anchored on


def _sq_gap(a, b):
    """The gap between two axis-aligned squares (x, y, half side)."""
    dx, dy = abs(a[0] - b[0]) - a[2] - b[2], abs(a[1] - b[1]) - a[2] - b[2]
    return math.hypot(max(0.0, dx), max(0.0, dy))


def _on_strip(x, y, ln):
    """(x, y) on the lane's strip: within its half width of the centre line, and not past its ends. → (on it, s)."""
    dist, s = mixed._seg_dist(x, y, ln.shape)
    if dist > ln.width / 2:
        return False, s
    (ax, ay), (bx, by) = ln.shape[:2]
    if s <= 0 and (x - ax) * (bx - ax) + (y - ay) * (by - ay) < 0:
        return False, s
    (ax, ay), (bx, by) = ln.shape[-2:]
    if s >= ln.length and (x - bx) * (bx - ax) + (y - by) * (by - ay) > 0:
        return False, s
    return True, s


def _extent(ln):
    """The corners of a lane's strip, segment by segment."""
    out = []
    for (ax, ay), (bx, by) in zip(ln.shape, ln.shape[1:]):
        length = math.hypot(bx - ax, by - ay) or 1.0
        nx, ny = -(by - ay) / length * ln.width / 2, (bx - ax) / length * ln.width / 2
        out += [(ax + nx, ay + ny), (ax - nx, ay - ny), (bx + nx, by + ny), (bx - nx, by - ny)]
    return out


def _credible(mass, q):
    """The smallest set of places holding Q of MASS {place: m}, the heaviest first, ties by id."""
    z, acc, out = sum(mass.values()), 0.0, []
    for p, v in sorted(mass.items(), key=lambda x: (-x[1], x[0])):
        out.append(p)
        acc += v
        if acc >= q * z:
            break
    return out


class Track:
    """One track's occupancy (see the module's doc). cls, seen, mass (existence: 1, or a birth's), speed, form: unstructured |
    strip | vehicle | birth."""

    def __init__(self, name, cls, seen, mass, speed, form, cell, soft, shapes, dyn, body, chair):
        self.name, self.cls, self.seen, self.mass, self.speed, self.form = name, cls, seen, mass, speed, form
        self.cell, self._soft, self._shapes, self._dyn, self._body, self._chair = cell, soft, shapes, dyn, body, chair

    def soft(self, k):
        """{cell id: P(the body is in the cell at times[k])}."""
        return self._soft[k]

    def radius(self, ego=None):
        """How far from its shape a chair centre is not clear, at EGO."""
        if self.form == "strip":
            return mixed.CHAIR_BODY[1] / 2 + self._body + safe_lat_dist(ego or dynamics_for(mixed.CHAIR), self._dyn)
        if self.form == "vehicle":
            return self._chair
        floor = max(self._dyn.min_dist, ego.min_dist if ego else 0.0)
        return brake_set(self._dyn) + (brake_set(ego) if ego else 0.0) + floor + self._chair + self._body

    def _gap(self, k, x, y):
        best = math.inf
        for s in self._shapes[k]:
            g = mixed._seg_dist(x, y, s)[0] if self.form == "strip" else _sq_gap((x, y, 0.0), s)
            best = min(best, g)
        return best

    def clear(self, k, x, y, ego=None):
        """A chair centre at (x, y) is clear of the set at times[k]."""
        return self._gap(k, x, y) > self.radius(ego)

    def hard(self, k, ego=None):
        """{cell ids} whose centre is not clear at times[k]."""
        r, cell, out = self.radius(ego), self.cell, set()
        for s in self._shapes[k]:
            pts = s if self.form == "strip" else [s[:2]]
            h = 0.0 if self.form == "strip" else s[2]
            xs, ys = [p[0] for p in pts], [p[1] for p in pts]
            for i in range(int(math.floor((min(xs) - h - r) / cell)), int(math.floor((max(xs) + h + r) / cell)) + 1):
                for j in range(int(math.floor((min(ys) - h - r) / cell)), int(math.floor((max(ys) + h + r) / cell)) + 1):
                    x, y = (i + 0.5) * cell, (j + 0.5) * cell
                    g = mixed._seg_dist(x, y, s)[0] if self.form == "strip" else _sq_gap((x, y, 0.0), s)
                    if g <= r:
                        out.add(mixed.cell_id(i, j))
        return out


class Occupancy:
    """times, seconds from now; cell, metres; tracks {name: Track}; soft(k), hard(k, ego), clear(k, x, y, ego) over them."""

    def __init__(self, times, cell, tracks):
        self.times, self.cell, self.tracks = times, cell, tracks

    def soft(self, k):
        """{cell id: P(some track's body is in the cell at times[k])}: the tracks independent."""
        free = {}
        for t in self.tracks.values():
            for c, p in t.soft(k).items():
                free[c] = free.get(c, 1.0) * (1.0 - min(1.0, p))
        return {c: 1.0 - f for c, f in sorted(free.items())}

    def hard(self, k, ego=None):
        return set().union(*(t.hard(k, ego) for t in self.tracks.values())) if self.tracks else set()

    def clear(self, k, x, y, ego=None):
        return all(t.clear(k, x, y, ego) for t in self.tracks.values())


class _Places:
    """What one render reads of the map's places: their squares, the cells under a stretch of lane, the people's graph."""

    def __init__(self, m, d):
        self.m, self.d, self.cell = m, d, d["cell"]
        self._graph, self._under = {}, {}

    def square(self, p):
        if mixed.is_cell(p):
            x, y, _ = self.d["cells"][p]
            return (x, y, self.cell / 2)
        x, y = self.m.xy(p) or (0.0, 0.0)
        return (x, y, road.BIN / 2)

    def graph(self, p):
        """The one graph without the lane bins that lie on cells: a person's walk rolls on the cells where there are any."""
        if p not in self._graph:
            self._graph[p] = [n for n in self.m.neighbours(p) if mixed.is_cell(n) or self._grid(*self.square(n)[:2]) not in self.d["cells"]]
        return self._graph[p]

    def _grid(self, x, y):
        return mixed.cell_id(int(math.floor(x / self.cell)), int(math.floor(y / self.cell)))

    def under(self, lane, s0, s1):
        """The grid's cells whose centre lies on LANE's strip between s0 and s1."""
        key = (lane, s0, s1)
        if key not in self._under:
            self._under[key] = self._cells_under(self.m.lanemap.lanes[lane], s0, s1)
        return self._under[key]

    def _cells_under(self, ln, s0, s1):
        if not ln.shape:
            return []
        s0, s1, cell, hw = max(0.0, s0), min(ln.length, s1), self.cell, ln.width / 2
        pts = [point_at(ln.shape, s0), point_at(ln.shape, s1)]
        acc = 0.0
        for a, b in zip(ln.shape, ln.shape[1:]):
            acc += math.hypot(b[0] - a[0], b[1] - a[1])
            if s0 < acc < s1:
                pts.append(b)
        out = []
        for i in range(int(math.floor((min(p[0] for p in pts) - hw) / cell)), int(math.floor((max(p[0] for p in pts) + hw) / cell)) + 1):
            for j in range(int(math.floor((min(p[1] for p in pts) - hw) / cell)), int(math.floor((max(p[1] for p in pts) + hw) / cell)) + 1):
                on, s = _on_strip((i + 0.5) * cell, (j + 0.5) * cell, ln)
                if on and s0 <= s <= s1:
                    out.append(mixed.cell_id(i, j))
        return out or [self._grid(*point_at(ln.shape, (s0 + s1) / 2))]


def _roll_person(m, d, t, n, step, pl):
    """[{place: mass}] for k = 0..N: each intent's kernel alone, cut at the reach, weighted by p(intent)."""
    ms = m.people_models(dict(d, dt=step), t, neighbours=pl.graph)
    dyn = dynamics_for(d["things"][t]["class"], v=d["speed"].get(t, 0.0))
    p0 = (d.get("pos") or {}).get(t)
    seen = t in (d.get("_people_seen") or ())
    start = [(p0["x"], p0["y"], 0.0)] if seen and p0 else [pl.square(c) for c in d["belief"][t]]

    def cut(bel, tk):
        limit = stated(dyn.vmax, dyn.accel, tk, None, dyn.vcap)
        keep = {c: v for c, v in bel.items() if any(_sq_gap(pl.square(c), a) <= limit for a in start)}
        z = sum(keep.values())
        return {c: v / z for c, v in keep.items()} if z > 0 else bel
    out = [{} for _ in range(n + 1)]
    for i in mixed.PEOPLE_INTENTS:
        w = d["intent"][t].get(i, 0.0)
        if w <= 0:
            continue
        bel = dict(d["belief"][t])
        for k in range(n + 1):                 # the walk goes on uncut: a cut carried on would stall it behind the pose
            if k and i != "stop":
                bel = ms[i](bel)
            for c, v in (cut(bel, k * step) if k else bel).items():
                out[k][c] = out[k].get(c, 0.0) + w * v
    return out


def _roll_vehicle(m, d, t, n, step):
    """… a vehicle's: RoadMap's kernels, an intent persisting."""
    out = [{} for _ in range(n + 1)]
    for i in road.INTENTS:
        w = d["intent"][t].get(i, 0.0)
        if w <= 0:
            continue
        kernel, bel = m.kernel(i, d["speed"].get(t, 0.0), step), dict(d["belief"][t])
        for k in range(n + 1):
            if k:
                bel = kernel(bel)
            for c, v in bel.items():
                out[k][c] = out[k].get(c, 0.0) + w * v
    return out


def _person_track(m, d, t, n, step, q, pl, cx, strips):
    th, speed = d["things"][t], d["speed"].get(t, 0.0)
    roll = _roll_person(m, d, t, n, step, pl)
    mass = th.get("birth")
    soft = []
    for bel in roll:
        cells = {}
        for p, v in bel.items():
            if mixed.is_cell(p):
                under = [p]
            else:
                lane, b = road.of(p)
                under = pl.under(lane, b * road.BIN, (b + 1) * road.BIN)
            for c in under:
                cells[c] = cells.get(c, 0.0) + (mass if mass is not None else 1.0) * v / len(under)
        soft.append(dict(sorted(cells.items())))
    dyn = dynamics_for(th["class"], v=speed)
    seen = t in (d.get("_people_seen") or ())
    p0 = (d.get("pos") or {}).get(t)
    chair = m.RADIUS["chair"]
    if mass is not None:
        return Track(t, th["class"], False, mass, speed, "birth", pl.cell, soft, [[] for _ in roll], dyn, 0.0, chair)
    if p0 is not None and cx is not None and m._cyclist_mover(d, t, cx, strips) is not None:
        h = (d.get("heading") or {}).get(t, 0.0)
        ux, uy = math.cos(h), math.sin(h)
        shapes = [[[(p0["x"], p0["y"]), (p0["x"] + ux * speed * k * step, p0["y"] + uy * speed * k * step)]] for k in range(n + 1)]
        return Track(t, th["class"], seen, 1.0, speed, "strip", pl.cell, soft, shapes, dyn, mixed.BODY["bicycle"][1] / 2, chair)
    shapes = [[pl.square(p) for p in _credible(bel, q)] for bel in roll]
    if seen and p0 is not None:
        shapes[0] = [(p0["x"], p0["y"], 0.0)]
    return Track(t, th["class"], seen, 1.0, speed, "unstructured", pl.cell, soft, shapes, dyn, m.RADIUS.get(th["class"], 0.3), chair)


def _vehicle_track(m, d, t, n, step, q, pl):
    th, speed = d["things"][t], d["speed"].get(t, 0.0)
    length = th.get("length", 4.5)
    roll = _roll_vehicle(m, d, t, n, step)

    def body(p):
        lane, b = road.of(p)
        return pl.under(lane, b * road.BIN - length, (b + 1) * road.BIN)
    soft, shapes = [], []
    for bel in roll:
        cells = {}
        for p, v in bel.items():
            for c in body(p):
                cells[c] = min(1.0, cells.get(c, 0.0) + v)
        soft.append(dict(sorted(cells.items())))
        shapes.append([_grid_square(c, pl.cell) for c in sorted({c for p in _credible(bel, q) for c in body(p)})])
    return Track(t, th["class"], t in (d.get("_seen") or ()), 1.0, speed, "vehicle", pl.cell, soft, shapes,
                 dynamics_for(th["class"], v=speed), 0.0, m.RADIUS["chair"])


def _grid_square(c, cell):
    i, j = mixed.cell_ij(c)
    return ((i + 0.5) * cell, (j + 0.5) * cell, cell / 2)


def render(m, horizon=3.0, step=None, credible=CREDIBLE, d=None):
    """The occupancy of every track with a belief over HORIZON seconds (see the module's doc): k = 0 is now, then every STEP
    seconds (None: the map's dt), the kernels at that step. It reads the map and writes nothing."""
    d = d or m.load()
    step = float(step if step is not None else d["dt"])
    n = int(round(float(horizon) / step))
    pl = _Places(m, d)
    _, cx = m._chair_on_strip(d)
    strips = m.strips()[1] if cx is not None else None
    tracks = {}
    for t in sorted(t for t, v in d["belief"].items() if v):
        if d["things"][t].get("layer") == "people":
            tracks[t] = _person_track(m, d, t, n, step, credible, pl, cx, strips)
        else:
            tracks[t] = _vehicle_track(m, d, t, n, step, credible, pl)
    return Occupancy([round(k * step, 9) for k in range(n + 1)], d["cell"], tracks)


class Raster:
    """The zones and kinds on a grid `factor` to a map cell a side (see the module's doc). origin (x, y), res metres, nx, ny;
    zones [ids], zone rows of indices into them; kinds mixed.KINDS, kind rows of indices into them; −1 unzoned."""

    def __init__(self, origin, cell, factor, nx, ny, zones, zone, zone_kinds):
        self.origin, self.cell, self.factor, self.nx, self.ny = origin, cell, factor, nx, ny
        self.res = cell / factor
        self.zones, self.zone, self.kinds = zones, zone, mixed.KINDS
        self._zone_kinds = zone_kinds
        self._kind = None

    @property
    def kind(self):
        if self._kind is None:
            table = [self.kinds.index(k) for k in self._zone_kinds] + [-1]     # −1 reads the last
            self._kind = [[table[z] for z in row] for row in self.zone]
        return self._kind

    def index(self, x, y):
        """The fine cell a point is in, None off the grid."""
        ix, iy = int(math.floor((x - self.origin[0]) / self.res)), int(math.floor((y - self.origin[1]) / self.res))
        return (ix, iy) if 0 <= ix < self.nx and 0 <= iy < self.ny else None

    def xy(self, ix, iy):
        """A fine cell's centre."""
        return (self.origin[0] + (ix + 0.5) * self.res, self.origin[1] + (iy + 0.5) * self.res)

    def cell_at(self, ix, iy):
        """A fine cell's map cell id."""
        return mixed.cell_id(int(round(self.origin[0] / self.cell)) + ix // self.factor,
                             int(round(self.origin[1] / self.cell)) + iy // self.factor)

    def zone_at(self, x, y):
        at = self.index(x, y)
        z = self.zone[at[1]][at[0]] if at else -1
        return self.zones[z] if z >= 0 else None

    def kind_at(self, x, y):
        at = self.index(x, y)
        k = self.kind[at[1]][at[0]] if at else -1
        return self.kinds[k] if k >= 0 else None

    def mask(self, zones):
        """Rows of 0/1: the fine cells in ZONES."""
        table = [int(z in zones) for z in self.zones] + [0]                     # −1 reads the last
        return [[table[z] for z in row] for row in self.zone]


def rasterise(m, factor):
    """The map's zones and kinds on a grid of FACTOR fine cells a map cell a side, over the extent of its cells and lanes."""
    if not isinstance(factor, int) or factor < 1:
        raise ValueError("factor %r: a whole number of fine cells a map cell, at least 1" % (factor,))
    d = m.load()
    cell = d["cell"]
    lanes = [ln for _, ln in sorted(m.lanemap.lanes.items()) if ln.shape]
    ijs = [mixed.cell_ij(c) for c in d["cells"]]
    xs, ys = [v for i, _ in ijs for v in (i * cell, (i + 1) * cell)], [v for _, j in ijs for v in (j * cell, (j + 1) * cell)]
    for ln in lanes:
        xs += [p[0] for p in _extent(ln)]
        ys += [p[1] for p in _extent(ln)]
    if not xs:
        raise ValueError("a map with no cells and no lanes has no extent")
    i0, i1 = int(math.floor(min(xs) / cell)), int(math.ceil(max(xs) / cell))
    j0, j1 = int(math.floor(min(ys) / cell)), int(math.ceil(max(ys) / cell))
    nx, ny = (i1 - i0) * factor, (j1 - j0) * factor
    zones = sorted(d["zones"])
    index = {z: n for n, z in enumerate(zones)}
    rows = [[-1] * nx for _ in range(ny)]
    for c, (_, _, z) in d["cells"].items():
        i, j = mixed.cell_ij(c)
        a, b = (i - i0) * factor, (j - j0) * factor
        for iy in range(b, b + factor):
            rows[iy][a:a + factor] = [index[z]] * factor
    res = cell / factor
    x0, y0 = i0 * cell, j0 * cell
    for ln in lanes:                               # a lane's strip where no cell has spoken
        z = index[d["lane_zone"].get(ln.id, ln.id)]
        corners = _extent(ln)
        ax, bx = min(p[0] for p in corners), max(p[0] for p in corners)
        ay, by = min(p[1] for p in corners), max(p[1] for p in corners)
        for iy in range(max(0, int((ay - y0) / res)), min(ny, int(math.ceil((by - y0) / res)))):
            row, y = rows[iy], y0 + (iy + 0.5) * res
            for ix in range(max(0, int((ax - x0) / res)), min(nx, int(math.ceil((bx - x0) / res)))):
                if row[ix] < 0 and _on_strip(x0 + (ix + 0.5) * res, y, ln)[0]:
                    row[ix] = z
    return Raster((x0, y0), cell, factor, nx, ny, zones, rows, [d["zones"][z]["kind"] for z in zones])
