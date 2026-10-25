"""grid — the `grid` adapter: a level of cells (NetHack's, MiniHack's, the dungeon exerciser's) over the core.

The world's atoms are the perception's (one convention for NLE and the exerciser): `agent_at(C)`, `floor(C)`,
`wall(C)`, `corridor(C)`, `door(C, open|closed|locked)`, `stairs_down(C)`, `stairs_up(C)`, `obj(NAME, C)`,
`monster(NAME, C)`, `holds(NAME)`; cells are `c<x>_<y>`.

- The map: every cell's kind and a door's state, from a level's des (`all`: known at the start) or as the ego sees
  them (`view`); the things (items) and the beasts with a belief over cells.
- The segment graph (`segments`): areas (cells in a 2×2 block of passable cells), one-wide lanes, junctions (a
  lane cell with three or more passable orthogonal neighbours), gates (doors, with their state), dead ends (a lane
  cell with one passable neighbour) and the frontier (a known passable cell beside an unknown one).
- The visible set: the ego's area (a lit room) with its rim, else its eight neighbours (a lane, a doorway, the dark).
- The route: Dijkstra over the known passable cells with gate costs (a closed door +2, a locked one +6, a cell a
  hostile is believed on +3), NetHack's rule kept (no diagonal step into or out of a doorway); the goal is the
  stairs down, or the nearest frontier cell while they are unseen.
- Motion (`models`): a hostile beast chases the ego (bayes.walk over the passable cells, biased by the distance
  to the ego along the map), a peaceful one holds (bayes.still); the alive decay is bayes.predict's.
- The roles: `goal` (the route's end) and p1..pk (the ego's cell, the route's next cells, the beasts' cells) bound
  STABLY, thing roles `target` `other`, beast roles b1 b2; the facts the rules read are between bound cells:
  next(p, d, q), toward(p) (the route's next cell), step(p) (can be stepped on now), door(p, open|closed) and
  stairs_down(p) (the map's), the message said(K) as it is, and the segment kinds
  lane(p) junction(p) gate(p) area(p) deadend(p). The directions stay the action's own constants."""
import heapq
import re

from . import core, ports
from .project import stable_slots

K = 8
STEPS = {"n": (0, -1), "e": (1, 0), "s": (0, 1), "w": (-1, 0), "ne": (1, -1), "se": (1, 1), "sw": (-1, 1), "nw": (-1, -1)}
WORDS = {"n": "north", "e": "east", "s": "south", "w": "west", "ne": "northeast", "se": "southeast", "sw": "southwest", "nw": "northwest"}
ORTHO = ((0, -1), (1, 0), (0, 1), (-1, 0))
THING_ROLES = ("target", "other")
BEAST_ROLES = ("b1", "b2")
PASSABLE = ("floor", "corridor", "stairs_down", "stairs_up", "door")
STEP = ("floor", "corridor", "stairs_down", "stairs_up")
RANK = {"stairs_down": 0, "stairs_up": 1, "door": 2, "corridor": 3, "wall": 4, "floor": 5}
READ = ("agent_at", "floor", "door", "stairs_down", "obj", "monster", "holds", "said")
CHASE = {"stay": 0.1, "bias": 3.0}           # a hostile: moves each turn, a step closer e³ likelier than one aside
GATE_COST = {"closed": 2, "locked": 6}
REFUGE = {"area": ("area",), "junction": ("junction", "area")}     # a passing place: where one can stand aside
HOSTILE_COST = 3


def xy(c):
    x, y = c[1:].split("_")
    return int(x), int(y)


def name(x, y):
    return "c%d_%d" % (x, y)


def cell_roles(k=K):
    return ("goal",) + tuple("p%d" % i for i in range(1, k + 1))


def des_cells(des):
    """A des's MAP block and its placements, in the level's own coordinates: ({cell: kind}, {cell: door state},
    [(thing, cell)], [(beast, cell)])."""
    m = re.search(r"\nMAP\n(.*?)\nENDMAP", des, re.S)
    rows = m.group(1).split("\n") if m else []
    kinds, doors = {}, {}
    for y, row in enumerate(rows):
        for x, ch in enumerate(row):
            k = {".": "floor", "|": "wall", "-": "wall", "+": "door", "#": "corridor"}.get(ch)
            if k:
                kinds[name(x, y)] = k
                if k == "door":
                    doors[name(x, y)] = "closed"
    for st, x, y in re.findall(r"^DOOR:\s*(\w+),\s*\((\d+),\s*(\d+)\)", des, re.M):
        kinds[name(int(x), int(y))] = "door"
        doors[name(int(x), int(y))] = "open" if st in ("open", "nodoor", "broken") else ("locked" if st == "locked" else "closed")
    for x, y, d in re.findall(r"^STAIR:\s*\((\d+),\s*(\d+)\),\s*(\w+)", des, re.M):
        kinds[name(int(x), int(y))] = "stairs_down" if d == "down" else "stairs_up"
    things = [(n.replace(" ", "_"), name(int(x), int(y))) for n, x, y in re.findall(r"^OBJECT:\s*\('.',\s*\"([^\"]+)\"\),\s*\((\d+),\s*(\d+)\)", des, re.M)]
    beasts = [(n.replace(" ", "_"), name(int(x), int(y))) for n, x, y in re.findall(r"^MONSTER:\s*(?:'.',\s*)?\"([^\"]+)\",\s*\((\d+),\s*(\d+)\)", des, re.M)]
    return kinds, doors, things, beasts


class GridMap(core.SemanticMap):
    OBJECT_ROLES = THING_ROLES + BEAST_ROLES
    LOCATED = ("obj", "monster")

    @classmethod
    def build(cls, path, size, des=None, view=False, k=K, want=(), peaceful=(), journal=None, cells=None, flat=False, speeds=None):
        """The level's map: SIZE (w, h); `all` (view False) knows every cell from DES (or CELLS: {cell: kind}, a
        door's state in kind "door:<state>"); `view` knows nothing until seen. want: the things the task wants;
        peaceful: the beasts that do not come for the ego; speeds: {beast: cells a turn} where it is known (NetHack's
        newt: half the player's, 0.5), else one. flat: no roles — the reading is the level's own cells with
        the route's next cell (a program compiled over the level itself: the comparison with roles)."""
        m = cls(path, journal)
        w, h = size
        d = {"w": w, "h": h, "view": bool(view), "k": k, "cells": {}, "doors": {}, "seen": [], "things": {}, "belief": {},
             "exists": {}, "looked": {}, "agent": {"at": None, "holding": None, "holds": []}, "binding": {}, "path": [],
             "task": {"goal": "stairs_down", "want": sorted(want)}, "peaceful": sorted(peaceful), "look": None, "flat": bool(flat),
             "speeds": dict(speeds or {})}
        if not view and des:
            kinds, doors, things, beasts = des_cells(des)
            d["cells"], d["doors"] = kinds, doors
            for n, c in things:
                d["things"][n] = {"in": None, "kind": "item"}
                d["belief"][n] = {c: 1.0}
            for n, c in beasts:
                d["things"][n] = {"in": None, "kind": "beast"}
                d["belief"][n] = {c: 1.0}
        elif not view and cells:
            for c, kd in cells.items():
                kind, _, st = kd.partition(":")
                d["cells"][c] = kind
                if kind == "door":
                    d["doors"][c] = st or "closed"
        m.data = d
        m.save()
        return m

    # ── the role families ──
    def place_roles(self, k):
        return cell_roles(k)

    def named_roles(self, k):
        return set(self.OBJECT_ROLES) | set(cell_roles(k))

    # ── the core's hooks ──
    def evidence(self, d, atoms):
        """The cells the atoms name (their most specific kind: a door or the stairs never downgraded to the floor
        of what stands on them), the doors' states, the ego's cell and kit, the items and beasts seen."""
        kind, named, monsters, sightings = {}, {}, set(), []
        changed = False
        at = d["agent"]["at"]
        for a in atoms:
            p = a.split("(")[0]
            if p in RANK:
                c = ports.args(a)[0]
                if RANK[p] < RANK.get(kind.get(c), 9):
                    kind[c] = p
                if p == "door":
                    st = ports.args(a)[1]
                    if d["doors"].get(c) != st and not (st == "closed" and d["doors"].get(c) == "locked"):
                        d["doors"][c], changed = st, True
            elif p == "obj":
                n, c = ports.args(a)
                named[n] = c
            elif p == "monster":
                sightings.append(tuple(ports.args(a)))
            elif p == "agent_at":
                at = ports.args(a)[0]
        # beasts that look alike (two newts both read monster(newt, …)): the association gate names the instance
        for n, c in self.associate(d, sightings):
            named[n] = c
            monsters.add(n)
        d["_beasts_seen"] = {n: named[n] for n in sorted(monsters)}
        on = {named[n] for n in named if named[n]} | ({at} if at else set())      # cells something stands on
        for c, k2 in kind.items():
            # what stands on a door or the stairs draws over it: not a downgrade; a door seen as floor with nothing
            # on it is a doorway now (broken, or never a door)
            keep = k2 == "floor" and (d["cells"].get(c) in ("stairs_down", "stairs_up") or (d["cells"].get(c) == "door" and c in on))
            if not keep and d["cells"].get(c) != k2:
                d["cells"][c], changed = k2, True
                if k2 != "door":
                    d["doors"].pop(c, None)
        if at:                                           # the cells in view, rock included: not a frontier once seen
            v = set(d.get("viewed", ())) | set(self._sight(d, at))
            if len(v) != len(d.get("viewed", ())):
                d["viewed"] = sorted(v)
        holds = sorted(ports.args(a)[0] for a in atoms if a.startswith("holds("))
        if holds != d["agent"]["holds"]:
            d["agent"]["holds"], changed = holds, True
        d["_monsters"] = sorted(monsters)                   # for grow: a beast or an item
        for n in holds:
            named.setdefault(n, None)
        return at, None, named, changed

    def associate(self, d, sightings):
        """SIGHTINGS [(kind, cell)] → [(instance, cell)]: bayes.associate over the passable cells, an instance's gate
        its reach since it was last seen (its speed × the turns since, plus one cell) — the reachable set's radius,
        so a beast is never taken for another while it could have walked there."""
        from . import bayes
        if not sightings:
            return []
        speeds, clock, last = d.get("speeds") or {}, d.get("clock", 0.0), d.get("last_seen") or {}

        def radius(t):
            t0 = (last.get(t) or (None, 0.0))[1]
            return 1.0 + speeds.get(d["things"][t].get("of", t), speeds.get(t, 1.0)) * max(0.0, clock - t0)
        kinds = {t: d["things"][t].get("of", t) for t in d["things"] if d["things"][t].get("kind") == "beast"}
        sub = {"things": {t: d["things"][t] for t in kinds}, "belief": d["belief"]}
        return bayes.associate(sub, sightings, lambda c: self.neighbours(c, d), radius, kind_of=lambda t: kinds[t])

    def _sight(self, d, at):
        """Every cell in view from AT, known or not: its area with the area's rim (a lit room), else the eight around."""
        seg = self.segments()
        sid = seg["of"].get(at)
        x, y = xy(at)
        ring = {name(x + dx, y + dy) for dx in (-1, 0, 1) for dy in (-1, 0, 1)}
        if sid is not None and seg["segments"][sid]["kind"] == "area":
            cells = set(seg["segments"][sid]["cells"])
            return sorted(cells | {name(xy(c)[0] + dx, xy(c)[1] + dy) for c in cells for dx in (-1, 0, 1) for dy in (-1, 0, 1)})
        return sorted(ring)

    def visible(self, d):
        """The known cells the ego sees into now: its area with the area's rim (a lit room), else its eight neighbours."""
        at = d["agent"]["at"]
        return [c for c in self._sight(d, at) if c in d["cells"]] if at else []

    def cycle(self, atoms, dt=1, models=None, alive=None, save=True):
        """The core's cycle with the map's clock (turns, a float: dt added): the last-seen times are on it."""
        d = self.load()
        d["clock"] = round(d.get("clock", 0.0) + dt, 6)
        return super().cycle(atoms, dt, models, alive, save)

    def observe(self, atoms, save=True, predicted=False):
        """The core's observe; in `all` mode (the cells known, not the beasts) a beast not seen where it is believed,
        in view of the ego, is not there: negative evidence over the visible cells, its belief dropped when nothing
        is left (killed, or gone out of sight: the motion model and the alive decay carry it from there)."""
        changed = super().observe(atoms, save=False, predicted=predicted)
        d = self.load()
        for n, c in (d.get("_beasts_seen") or {}).items():     # a beast on the screen is in sight: its last sighting
            d.setdefault("last_seen", {})[n] = [c, d.get("clock", 0.0)]
        if not d.get("view") and d["agent"]["at"]:
            from . import bayes
            seen = dict(d.get("_beasts_seen") or {})
            beasts = {n: d["belief"][n] for n, t in d["things"].items() if t.get("kind") == "beast" and d["belief"].get(n)}
            sub = {"belief": beasts, "looked": d.setdefault("looked", {}), "exists": d.setdefault("exists", {})}
            for c in self.visible(d):
                if bayes.missed(sub, c, seen, lambda t: {}):
                    changed = True
            for n in beasts:
                if sub["belief"].get(n):
                    d["belief"][n] = sub["belief"][n]
                else:
                    d["belief"].pop(n, None)
        if changed and save:
            self.save()
            self.log("observe", at=d["agent"]["at"], holding=d["agent"]["holding"])
        return changed

    def describe(self, thing, n=3):
        """Where THING is believed, in the world's words: seen now, or last seen where and how long ago and the
        likeliest cells now ("The newt, last seen at 5, 3 two turns ago: likely at 7, 3 (0.41), 6, 3 (0.33)"); lost
        when no belief is left."""
        d = self.load()
        bel = d["belief"].get(thing) or {}
        where = lambda c: "%d, %d" % xy(c)
        name = "The " + thing.replace("_", " ")
        c0, t0 = (d.get("last_seen") or {}).get(thing, (None, None))
        ago = None if t0 is None else round(d.get("clock", 0.0) - t0, 3)
        if ago == 0 and c0:
            return "%s is at %s." % (name, where(c0))
        when = "" if c0 is None else ", last seen at %s %s ago" % (where(c0), _turns(ago))
        if not bel:
            return "%s%s: lost." % (name, when)
        top = sorted(bel.items(), key=lambda x: (-x[1], x[0]))[:n]
        return "%s%s: likely at %s." % (name, when, ", ".join("%s (%.2f)" % (where(c), p) for c, p in top))

    def grow(self, d, thing):
        if thing in d.get("_monsters", ()):            # a beast: of its kind (newt_2 is a newt)
            kind = thing.rsplit("_", 1)[0] if re.match(r".+_\d+$", thing) else thing
            return {"in": None, "kind": "beast", "of": kind}
        return {"in": None, "kind": "item"}

    def reproject(self, d):
        self._project(d, save=False)

    def believed(self, d, inv):
        """View mode: a bound item or beast at a bound cell where the belief holds it at 0.5 or more."""
        out = {}
        for orole in self.OBJECT_ROLES:
            h = d["binding"].get(orole)
            if not h:
                continue
            pred = "monster" if d["things"].get(h, {}).get("kind") == "beast" else "obj"
            for c, p in (d["belief"].get(h) or {}).items():
                if p >= 0.5 and c in inv:
                    out["%s(%s,%s)" % (pred, orole, inv[c])] = 1
        return out

    def place_facts(self, d, inv):
        """Between the bound cells: next(p, d, q), step(p), toward(p), and the segment kinds of each bound cell."""
        out = {}
        cells = [(r, h) for r, h in d["binding"].items() if r in cell_roles(d["k"])]
        beasts = {c for n, t in d["things"].items() if t.get("kind") == "beast" for c, p in (d["belief"].get(n) or {}).items() if p >= 0.5}
        seg = self.segments()
        for r1, h1 in cells:
            x1, y1 = xy(h1)
            for r2, h2 in cells:
                x2, y2 = xy(h2)
                for dn, (dx, dy) in STEPS.items():
                    if (x1 + dx, y1 + dy) == (x2, y2) and self._step_ok(d, h1, h2, dx, dy):
                        out["next(%s,%s,%s)" % (r1, dn, r2)] = 1
            k = d["cells"].get(h1)
            if k == "door":                              # the map's state (a locked door reads closed: the message tells)
                out["door(%s,%s)" % (r1, "open" if d["doors"].get(h1) == "open" else "closed")] = 1
            elif k == "stairs_down":                     # the map's: the screen draws the ego over the stairs it stands on
                out["stairs_down(%s)" % r1] = 1
            if (k in STEP or k == "door" and d["doors"].get(h1) == "open") and h1 not in beasts:
                out["step(%s)" % r1] = 1
            sid = seg["of"].get(h1)
            if sid is not None:
                out["%s(%s)" % (seg["segments"][sid]["kind"], r1)] = 1
            if h1 in seg["deadends"]:
                out["deadend(%s)" % r1] = 1
            if h1 in seg["frontier"]:
                out["frontier(%s)" % r1] = 1
        nxt = d["path"][1] if len(d["path"]) > 1 else None
        if nxt in inv:
            out["toward(%s)" % inv[nxt]] = 1
        return out

    # ── the geometry ──
    def passable(self, d, c):
        return d["cells"].get(c) in PASSABLE

    def _step_ok(self, d, a, b, dx, dy):
        return not (dx and dy and (d["cells"].get(a) == "door" or d["cells"].get(b) == "door"))

    def neighbours(self, c, d=None):
        """The passable cells one step from C (NetHack's moves)."""
        d = d or self.load()
        x, y = xy(c)
        out = []
        for dx, dy in STEPS.values():
            n = name(x + dx, y + dy)
            if self.passable(d, n) and self._step_ok(d, c, n, dx, dy):
                out.append(n)
        return out

    def segments(self):
        """The segment graph over the known passable cells: {"segments": {id: {kind, cells}}, "of": {cell: id},
        "edges": [[id, id]], "junctions": [...], "deadends": [...], "frontier": [...]}."""
        d = self.load()
        key = hash((frozenset(d["cells"].items()), frozenset(d["doors"].items()), len(d.get("viewed", ()))))
        if getattr(self, "_seg_key", None) == key:
            return self._seg
        pas = {c for c, k in d["cells"].items() if k in PASSABLE}
        gates = {c for c in pas if d["cells"][c] == "door"}

        def p(x, y):
            return name(x, y) in pas and name(x, y) not in gates
        area = set()
        for c in pas - gates:
            x, y = xy(c)
            if any(p(x + ax, y + ay) and p(x + ax + 1, y + ay) and p(x + ax, y + ay + 1) and p(x + ax + 1, y + ay + 1)
                   for ax in (-1, 0) for ay in (-1, 0)):
                area.add(c)
        lane = pas - gates - area
        junctions = sorted(c for c in lane if sum(name(xy(c)[0] + dx, xy(c)[1] + dy) in pas for dx, dy in ORTHO) >= 3)
        deadends = sorted(c for c in lane if len([n for n in self.neighbours(c, d)]) == 1)
        viewed = set(d.get("viewed", ()))
        frontier = sorted(c for c in pas if any(0 <= xy(c)[0] + dx < d["w"] and 0 <= xy(c)[1] + dy < d["h"]
                                                 and name(xy(c)[0] + dx, xy(c)[1] + dy) not in d["cells"]
                                                 and name(xy(c)[0] + dx, xy(c)[1] + dy) not in viewed
                                                 for dx, dy in STEPS.values()))
        of, segs = {}, {}
        for kind, cells in (("area", area), ("lane", lane - set(junctions))):
            for c in sorted(cells):
                if c in of:
                    continue
                sid = "%s%d" % (kind[0], len(segs))
                comp, todo = [], [c]
                of[c] = sid
                while todo:
                    u = todo.pop()
                    comp.append(u)
                    ux, uy = xy(u)
                    for dx, dy in STEPS.values():
                        n = name(ux + dx, uy + dy)
                        if n in cells and n not in of:
                            of[n] = sid
                            todo.append(n)
                segs[sid] = {"kind": kind, "cells": sorted(comp)}
        for kind, cells in (("junction", junctions), ("gate", sorted(gates))):
            for c in cells:
                sid = "%s%d" % (kind[0], len(segs))
                of[c] = sid
                segs[sid] = {"kind": kind, "cells": [c], **({"state": d["doors"].get(c)} if kind == "gate" else {})}
        edges = set()
        for c, a in of.items():
            for n in self.neighbours(c, d):
                b = of.get(n)
                if b and b != a:
                    edges.add(tuple(sorted((a, b))))
        self._seg_key = key
        self._seg = {"segments": segs, "of": of, "edges": sorted([list(e) for e in edges]), "junctions": junctions,
                     "deadends": deadends, "frontier": frontier}
        return self._seg

    def route(self):
        """Dijkstra from the ego's cell to the goal over the known passable cells with gate costs. → [cell, …]."""
        d = self.load()
        at = d["agent"]["at"]
        if not at:
            return []
        goals = {c for c, k in d["cells"].items() if k == d["task"]["goal"]}
        frontier = set(self.segments()["frontier"]) - {at} if not goals else set()
        hostile = {c for n, t in d["things"].items() if t.get("kind") == "beast" and n not in d["peaceful"]
                   for c, p in (d["belief"].get(n) or {}).items() if p >= 0.5}
        blocked = {c for n in d["task"].get("avoid") or () for c, p in (d["belief"].get(n) or {}).items() if p >= 0.5}
        refuge = d["task"].get("refuge")
        if refuge:                                       # the passing place: the nearest cell of that kind, away from
            seg = self.segments()                        # every beast (their cells closed to the route)
            kinds = REFUGE[refuge]
            blocked = {c for n, t in d["things"].items() if t.get("kind") == "beast"
                       for c, p in (d["belief"].get(n) or {}).items() if p >= 0.5}
            goals = {c for c, sid in seg["of"].items() if seg["segments"][sid]["kind"] in kinds and c not in blocked}
            if at in goals:
                return [at]
            frontier = set()
        dist, prev, q = {at: 0}, {at: None}, [(0, at)]
        end = None
        while q:
            g, c = heapq.heappop(q)
            if g > dist[c]:
                continue
            if c in goals or c in frontier:
                end = c
                break
            for n in self.neighbours(c, d):
                if n in blocked:
                    continue
                cost = 1 + GATE_COST.get(d["doors"].get(n), 0) * (d["cells"].get(n) == "door") + HOSTILE_COST * (n in hostile)
                if g + cost < dist.get(n, 1e18):
                    dist[n], prev[n] = g + cost, c
                    heapq.heappush(q, (g + cost, n))
        if end is None:
            return []
        out = []
        while end is not None:
            out.append(end)
            end = prev[end]
        return out[::-1]

    def models(self, d=None, reach=False):
        """The movers' models for bayes.predict: a hostile beast chases the ego — a walk over the passable cells
        biased by the distance to the ego ALONG the map (breadth first from the ego: round walls, through
        doorways), strongly (CHASE: a step closer is e³ likelier than a step aside), rarely holding (it moves
        each turn, as NetHack's hostiles do) at its speed (`speeds`; a fraction: a step that turn with that
        probability, bayes.walk's float dt); a peaceful one holds. REACH: a hostile's model is the reachable set
        (bayes.reachable: its mass over every cell within its speed's reach, evenly)."""
        from . import bayes
        d = d or self.load()
        at = d["agent"]["at"]
        dist = self._dist_from(d, at) if at else {}
        far = max(dist.values(), default=0) + 1
        toward = (lambda c: dist.get(c, far)) if at else None
        out = {}
        for n, t in d["things"].items():
            if t.get("kind") == "beast" and reach and n not in d["peaceful"]:
                # REACH: the reachable set instead of the chase (RSS's worst case: anywhere its speed allows, no
                # intent assumed) — the belief a safety check must clear rather than the likeliest track
                out[n] = bayes.reachable(lambda c: self.neighbours(c, d), vmin=0.0,
                                         vmax=(d.get("speeds") or {}).get(t.get("of", n), (d.get("speeds") or {}).get(n, 1)))
            elif t.get("kind") == "beast":
                out[n] = bayes.still if n in d["peaceful"] else bayes.walk(lambda c: self.neighbours(c, d), toward,
                                                                           speed=(d.get("speeds") or {}).get(n, 1), **CHASE)
        return out

    def _dist_from(self, d, at):
        """Steps from AT to every known passable cell (NetHack's moves): {cell: steps}."""
        dist, q = {at: 0}, [at]
        for c in q:
            for nb in self.neighbours(c, d):
                if nb not in dist:
                    dist[nb] = dist[c] + 1
                    q.append(nb)
        return dist

    # ── the situation layer's pairs (semantic_world.situation; RSS on a dungeon: reach for braking) ──
    def pairs(self, horizon=6, rho=1.0, min_dist=1.0, d=None):
        """The RSS pairs of the ego and each beast believed within HORIZON steps, at its likeliest cell. Along the
        ego's way (its route ahead): lon in_front, the gap the route's steps to it; a hostile comes at the ego
        (opp_dir), a peaceful stands in the way (same_dir, speed 0 to its own). Off the way: beside it (lat at_left,
        the gap across the steps between them, along the way overlapping). Lateral room only in an area (a lane, a
        junction, a doorway: one-wide). The ego steps one cell a turn and stops at will; a beast moves at its
        `speeds` (cells a turn), from rest. The pair's id is the beast and its type (stable while both stand), its
        role the beast's role. → [situation.Pair]."""
        from .situation import Dynamics, Pair
        d = d or self.load()
        at = d["agent"]["at"]
        if not at:
            return []
        dist = self._dist_from(d, at)
        path = d["path"] or [at]
        seg = self.segments()
        room = seg["segments"].get(seg["of"].get(at), {}).get("kind") == "area"
        inv = {h: r for r, h in d["binding"].items()}
        ego = Dynamics(vmin=0.0, vmax=1.0, rho=rho, min_dist=min_dist)
        out = []
        for n in sorted(d["things"]):
            t = d["things"][n]
            bel = d["belief"].get(n)
            if t.get("kind") != "beast" or not bel:
                continue
            c = sorted(bel.items(), key=lambda x: (-x[1], x[0]))[0][0]
            g = dist.get(c)
            if g is None or g > horizon:
                continue
            speed = (d.get("speeds") or {}).get(t.get("of", n), (d.get("speeds") or {}).get(n, 1.0))
            hostile = n not in d["peaceful"]
            obj = Dynamics(vmin=0.0, vmax=speed if hostile else 0.0, rho=rho, min_dist=min_dist,
                           lat_v=speed if hostile else 0.0)   # across an area it comes at the ego as fast as along
            kind = "opp_dir" if hostile else "same_dir"
            if c in path[1:]:
                out.append(Pair("%s:%s" % (n, kind), kind, "in_front", "overlap", float(path.index(c)), 0.0, ego, obj,
                                lateral_room=room, role=inv.get(n)))
            elif hostile:                                  # off the way, it still comes at the ego: along the map
                out.append(Pair("%s:%s" % (n, kind), kind, "in_front", "at_left" if room else "overlap", float(g),
                                float(g) if room else 0.0, ego, obj, lateral_room=room, role=inv.get(n)))
            else:                                          # a peaceful off the way: in nobody's way
                out.append(Pair("%s:not_relevant" % n, "not_relevant", role=inv.get(n), ego=ego, obj=obj))
        return out

    def hazard(self, thing, horizon=1.0, d=None):
        """P(THING can be at the ego's cell within HORIZON turns): its belief's mass within its reach of the ego (the
        reachable set's radius: its speed × HORIZON), a weight port's reading (`reach(B)`)."""
        from . import bayes
        d = d or self.load()
        at, bel = d["agent"]["at"], d["belief"].get(thing) or {}
        speed = (d.get("speeds") or {}).get(d["things"].get(thing, {}).get("of", thing), 1.0)
        return bayes.mass_within(bel, lambda c: self.neighbours(c, d), at, speed * horizon) if at else 0.0

    # ── the binding ──
    def project(self, k=None):
        """Bind the roles as the ego stands now, stably: `goal` the route's end, p1..pk the ego's cell, the route's
        next cells and the cells the beasts are believed on (most likely first); b1 b2 the beasts nearest, target the
        wanted thing. Saved; → the binding."""
        d = self.load()
        if k:
            d["k"] = k
        if d.get("flat"):
            d["path"] = self.route()
            self.save()
            return {}
        self._project(d)
        return dict(d["binding"])

    def _project(self, d, save=True):
        k = d["k"]
        p = self.route()
        d["path"] = p
        at = d["agent"]["at"]
        goal = p[-1] if p else None
        ax, ay = xy(at) if at else (0, 0)
        beasts = [n for n, t in d["things"].items() if t.get("kind") == "beast" and d["belief"].get(n)]
        near = sorted(beasts, key=lambda n: (min(max(abs(xy(c)[0] - ax), abs(xy(c)[1] - ay)) for c in d["belief"][n]), n))[:len(BEAST_ROLES)]
        want = [n for n in d["task"]["want"] if n in d["things"]][:1]
        work = []
        for c in ([at] if at else []) + p[1:] + [c for n in near + want
                                                 for c, _ in sorted((d["belief"].get(n) or {}).items(), key=lambda x: (-x[1], x[0]))]:
            if c and c != goal and c not in work:
                work.append(c)
        work = work[:k]
        b = {"goal": goal} if goal else {}
        b.update(stable_slots(d["binding"], lambda h: h in work, work, k))
        b.update(zip(BEAST_ROLES, near))
        if want:
            b["target"] = want[0]
        d["binding"] = {r: h for r, h in sorted(b.items()) if h}
        if save:
            self.save()
            self.log("project", goal=goal, binding=d["binding"])

    def say(self, text, binding=None):
        """A rule's line in roles in the world's words (the binding its rule fired under, when given): a direction
        word, a cell as what is there ("the door at 3, 1", "the stairs down at 4, 0", "the cell at 2, 1"), a thing or
        beast as its name. The first letter capitalized."""
        d = self.load()
        b = binding if binding is not None else d["binding"]

        def sub(m):
            t = m.group(0)
            if t in WORDS:
                return WORDS[t]
            h = b.get(t)
            if h is None:
                return t
            if re.match(r"^c\d+_\d+$", h):
                word = {"door": "the door", "stairs_down": "the stairs down"}.get(d["cells"].get(h), "the cell")
                return "%s at %d, %d" % (word, *xy(h))
            return "the " + h.replace("_", " ")
        roles = sorted(set(cell_roles(d["k"])) | set(self.OBJECT_ROLES) | set(WORDS), key=len, reverse=True)
        out = re.sub(r"\b(%s)\b" % "|".join(roles), sub, text)
        return out[:1].upper() + out[1:]

    def role_reading(self, reading, binding=None):
        """The perception in roles (the predicates the grid's role bases declare), with the place facts. Flat: the
        perception as it is, with toward(the route's next cell)."""
        reading = {a: n for a, n in reading.items() if a.split("(")[0] in READ}
        d = self.load()
        if d.get("flat"):
            out = dict(reading)
            if len(d["path"]) > 1:
                out["toward(%s)" % d["path"][1]] = 1
            return out
        out = super().role_reading(reading, binding)
        out.update({a: n for a, n in reading.items() if a.startswith("said(")})   # the message: no role in it
        return out


def _turns(t):
    """A duration in turns, said: "a turn", "two turns", "2.5 turns"."""
    words = {1: "a turn", 2: "two turns", 3: "three turns", 4: "four turns", 5: "five turns"}
    return words.get(t) if t in words else "%g turns" % t


def capacity(k=K):
    """The role vocabulary as an LLP capacity instance's text (the world keeps the file)."""
    return "\n".join(["%% capacity — a grid's roles (semantic_world.grid, k = %d): the cells a goal needs, the things" % k,
                      "% and the beasts; the level is the host's map.",
                      "catalog capacity 1.", 'provenance text "the grid role vocabulary at capacity %d" "2026-10-25".' % k,
                      "type cell {%s}." % " ".join(cell_roles(k)), "type thing {%s}." % " ".join(THING_ROLES),
                      "type beast {%s}." % " ".join(BEAST_ROLES), ""])
