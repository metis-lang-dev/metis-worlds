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
- Motion (`models`): a hostile beast walks toward the ego (bayes.walk over the passable cells, biased by the
  Chebyshev distance to the ego), a peaceful one holds (bayes.still); the alive decay is bayes.predict's.
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
GATE_COST = {"closed": 2, "locked": 6}
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
    def build(cls, path, size, des=None, view=False, k=K, want=(), peaceful=(), journal=None, cells=None, flat=False):
        """The level's map: SIZE (w, h); `all` (view False) knows every cell from DES (or CELLS: {cell: kind}, a
        door's state in kind "door:<state>"); `view` knows nothing until seen. want: the things the task wants;
        peaceful: the beasts that do not come for the ego. flat: no roles — the reading is the level's own cells with
        the route's next cell (a program compiled over the level itself: the comparison with roles)."""
        m = cls(path, journal)
        w, h = size
        d = {"w": w, "h": h, "view": bool(view), "k": k, "cells": {}, "doors": {}, "seen": [], "things": {}, "belief": {},
             "exists": {}, "looked": {}, "agent": {"at": None, "holding": None, "holds": []}, "binding": {}, "path": [],
             "task": {"goal": "stairs_down", "want": sorted(want)}, "peaceful": sorted(peaceful), "look": None, "flat": bool(flat)}
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
        kind, named, monsters = {}, {}, set()
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
            elif p in ("obj", "monster"):
                n, c = ports.args(a)
                named[n] = c
                if p == "monster":
                    monsters.add(n)
            elif p == "agent_at":
                at = ports.args(a)[0]
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

    def observe(self, atoms, save=True, predicted=False):
        """The core's observe; in `all` mode (the cells known, not the beasts) a beast not seen where it is believed,
        in view of the ego, is not there: negative evidence over the visible cells, its belief dropped when nothing
        is left (killed, or gone out of sight: the motion model and the alive decay carry it from there)."""
        changed = super().observe(atoms, save=False, predicted=predicted)
        d = self.load()
        if not d.get("view") and d["agent"]["at"]:
            from . import bayes
            seen = {ports.args(a)[0]: ports.args(a)[1] for a in atoms if a.startswith("monster(")}
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

    def grow(self, d, thing):
        return {"in": None, "kind": "beast" if thing in d.get("_monsters", ()) else "item"}

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

    def models(self, d=None):
        """The movers' models for bayes.predict: a hostile beast walks toward the ego, a peaceful one holds."""
        from . import bayes
        d = d or self.load()
        at = d["agent"]["at"]
        ax, ay = xy(at) if at else (0, 0)
        toward = (lambda c: max(abs(xy(c)[0] - ax), abs(xy(c)[1] - ay))) if at else None
        out = {}
        for n, t in d["things"].items():
            if t.get("kind") == "beast":
                out[n] = bayes.still if n in d["peaceful"] else bayes.walk(lambda c: self.neighbours(c, d), toward)
        return out

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


def capacity(k=K):
    """The role vocabulary as an LLP capacity instance's text (the world keeps the file)."""
    return "\n".join(["%% capacity — a grid's roles (semantic_world.grid, k = %d): the cells a goal needs, the things" % k,
                      "% and the beasts; the level is the host's map.",
                      "catalog capacity 1.", 'provenance text "the grid role vocabulary at capacity %d" "2026-10-25".' % k,
                      "type cell {%s}." % " ".join(cell_roles(k)), "type thing {%s}." % " ".join(THING_ROLES),
                      "type beast {%s}." % " ".join(BEAST_ROLES), ""])
