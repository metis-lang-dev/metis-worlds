"""dungeon — a pure-python exerciser for the grid adapter: levels, monsters, sight, and the perception in NLE's
convention (the atoms world/perceive.py makes of a NetHack screen), so the library is exercised without NetHack.
It is not a world: the real tests stay NLE (metis-worlds/minihack).

The level families follow the published descriptions of NetHack's generators (Boris the Brave's article on
NetHack's map generation), re-implemented from the algorithm's description; NetHack's source is NGPL and is not
consulted or copied:
- caves (the Gnomish Mines' shape): a random fill of 40% rock, four passes of a cellular automaton (a cell is
  rock when 5 or more of the 9 cells around it, itself included, are rock), the floor's connected regions found by
  flood fill, the regions of 3 cells or fewer filled in, and each region joined to the next by an orthogonal
  (L-shaped) corridor;
- rooms and corridors: rectangular lit rooms with walls, doors in a wall in one of four states (doorway, open,
  closed, locked), rooms joined in sequence by dark corridors from door to door (an extra joint makes a junction,
  a spur a dead end).

Monsters: a hostile steps toward the ego (the next cell of a breadth-first path) SPEED times a turn and attacks
when beside it; a peaceful one holds or wanders. Sight: in a lit room the whole room and its walls; in the dark
(a corridor, a doorway, a cave) the eight cells around; terrain once seen is remembered (as NetHack's map is),
monsters are seen only in sight."""
import random
from collections import deque

STEPS = {"n": (0, -1), "e": (1, 0), "s": (0, 1), "w": (-1, 0), "ne": (1, -1), "se": (1, 1), "sw": (-1, 1), "nw": (-1, -1)}
ORTHO = ((0, -1), (1, 0), (0, 1), (-1, 0))


def cell(x, y):
    return "c%d_%d" % (x, y)


class Level:
    """tiles {(x, y): '.' room floor · '#' corridor · '|' '-' wall · '+' door · '>' stairs down}, doors {(x, y): state},
    rooms [(x0, y0, x1, y1)] (the floor's box), lit {(x, y)} (the cells of lit rooms), start (x, y)."""

    def __init__(self, w, h):
        self.w, self.h = w, h
        self.tiles, self.doors, self.rooms, self.lit = {}, {}, [], set()
        self.start = self.stairs = None

    def passable(self, p):
        t = self.tiles.get(p)
        return t in (".", "#", ">") or (t == "+" and self.doors.get(p) in ("doorway", "open", "broken"))

    def walkable(self, p):
        """Passable once its door is open (the path's view of a closed door)."""
        return self.tiles.get(p) in (".", "#", ">", "+")

    def step_ok(self, a, b):
        """NetHack's rule: no diagonal step into or out of a doorway that has a door (open, closed, locked); an empty
        or a broken doorway lets a diagonal through."""
        diag = a[0] != b[0] and a[1] != b[1]
        door = lambda p: self.tiles.get(p) == "+" and self.doors.get(p) not in ("doorway", "broken")
        return not (diag and (door(a) or door(b)))

    def bfs(self, a, goal, through_doors=True):
        ok = self.walkable if through_doors else self.passable
        prev, q = {a: None}, deque([a])
        while q:
            u = q.popleft()
            if u == goal:
                break
            for dx, dy in STEPS.values():
                v = (u[0] + dx, u[1] + dy)
                if v not in prev and ok(v) and self.step_ok(u, v):
                    prev[v] = u
                    q.append(v)
        if goal not in prev:
            return []
        out, u = [], goal
        while u is not None:
            out.append(u)
            u = prev[u]
        return out[::-1]

    def des(self):
        """The level as a MiniHack des (MAP, the doors, the stairs): the same level for NLE."""
        rows = []
        for y in range(self.h):
            rows.append("".join(self.tiles.get((x, y), " ") if self.tiles.get((x, y)) != "+" else "+" for x in range(self.w)))
        out = ["MAZE: \"exerciser\", ' '", "FLAGS:hardfloor", "INIT_MAP: solidfill,' '", "GEOMETRY:center,center", "MAP"] + rows + ["ENDMAP"]
        for (x0, y0, x1, y1) in self.rooms:
            out.append("REGION:(%d,%d,%d,%d),lit,\"ordinary\"" % (x0, y0, x1, y1))
        for (x, y), st in sorted(self.doors.items()):
            out.append("DOOR:%s,(%d,%d)" % ({"doorway": "nodoor"}.get(st, st), x, y))
        if self.stairs:
            out.append("STAIR:(%d,%d),down" % self.stairs)
        if self.start:
            out.append("BRANCH:(%d,%d,%d,%d),(0,0,0,0)" % (self.start + self.start))
        return "\n" + "\n".join(out) + "\n"


def cave(w=76, h=21, seed=1, fill=0.40, passes=4, smallest=3):
    """A cave level (the Mines' shape), joined: → Level."""
    rng = random.Random(seed)
    rock = {(x, y): (x in (0, w - 1) or y in (0, h - 1) or rng.random() < fill) for y in range(h) for x in range(w)}
    for _ in range(passes):
        nxt = {}
        for (x, y) in rock:
            n = sum(rock.get((x + dx, y + dy), True) for dx in (-1, 0, 1) for dy in (-1, 0, 1))
            nxt[(x, y)] = n >= 5 or x in (0, w - 1) or y in (0, h - 1)
        rock = nxt
    seen, regions = set(), []
    for p in sorted((p for p, r in rock.items() if not r), key=lambda p: (p[0], p[1])):
        if p in seen:
            continue
        comp, q = [], deque([p])
        seen.add(p)
        while q:
            u = q.popleft()
            comp.append(u)
            for dx, dy in ORTHO:
                v = (u[0] + dx, u[1] + dy)
                if v not in seen and not rock.get(v, True):
                    seen.add(v)
                    q.append(v)
        regions.append(comp)
    for comp in regions:                               # the small regions filled in
        if len(comp) <= smallest:
            for p in comp:
                rock[p] = True
    regions = [c for c in regions if len(c) > smallest]
    lv = Level(w, h)
    for p, r in rock.items():
        if not r:
            lv.tiles[p] = "."
    for a, b in zip(regions, regions[1:]):             # each region joined to the next, orthogonally
        (ax, ay), (bx, by) = min(a), min(b)
        for x in range(min(ax, bx), max(ax, bx) + 1):
            lv.tiles.setdefault((x, ay), "#")
        for y in range(min(ay, by), max(ay, by) + 1):
            lv.tiles.setdefault((bx, y), "#")
    for p in list(lv.tiles):                           # the rock beside the open cells as wall (what the screen draws)
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                q = (p[0] + dx, p[1] + dy)
                if 0 <= q[0] < w and 0 <= q[1] < h and q not in lv.tiles:
                    lv.tiles[q] = "-"
    floor = sorted(p for p, t in lv.tiles.items() if t in (".", "#"))
    lv.start = floor[0]
    lv.stairs = max(floor, key=lambda p: (len(lv.bfs(lv.start, p)), p))
    lv.tiles[lv.stairs] = ">"
    return lv


def rooms(w=76, h=21, seed=1, n=5, doors=("doorway", "open", "closed", "locked"), spur=True):
    """A rooms-and-corridors level: → Level. Doors take their states from DOORS in turn (the first door of the level
    the first state, …), so a test knows what stands on the way."""
    rng = random.Random(seed)
    lv = Level(w, h)
    boxes = []
    tries = 0
    while len(boxes) < n and tries < 2000:
        tries += 1
        rw, rh = rng.randint(3, 8), rng.randint(2, 4)
        x0, y0 = rng.randint(1, w - rw - 2), rng.randint(1, h - rh - 2)
        box = (x0, y0, x0 + rw - 1, y0 + rh - 1)
        if any(not (box[2] + 3 < b[0] or b[2] + 3 < box[0] or box[3] + 3 < b[1] or b[3] + 3 < box[1]) for b in boxes):
            continue
        boxes.append(box)
    boxes.sort()
    for (x0, y0, x1, y1) in boxes:
        for x in range(x0 - 1, x1 + 2):
            for y in range(y0 - 1, y1 + 2):
                edge = x in (x0 - 1, x1 + 1) or y in (y0 - 1, y1 + 1)
                lv.tiles[(x, y)] = ("|" if x in (x0 - 1, x1 + 1) else "-") if edge else "."
                if not edge:
                    lv.lit.add((x, y))
        lv.rooms.append((x0, y0, x1, y1))
    states = list(doors)

    def door(box, side):
        x0, y0, x1, y1 = box
        if side == "e":
            p = (x1 + 1, rng.randint(y0, y1))
        elif side == "w":
            p = (x0 - 1, rng.randint(y0, y1))
        elif side == "s":
            p = (rng.randint(x0, x1), y1 + 1)
        else:
            p = (rng.randint(x0, x1), y0 - 1)
        if p not in lv.doors:
            lv.tiles[p] = "+"
            lv.doors[p] = states[len(lv.doors) % len(states)]
        return p

    def out(p, box):                                   # the corridor cell just outside a door
        x0, y0, x1, y1 = box
        return (p[0] + (1 if p[0] > x1 else -1 if p[0] < x0 else 0), p[1] + (1 if p[1] > y1 else -1 if p[1] < y0 else 0))

    def corridor(a, b):
        """A corridor from A to B through the rock (orthogonal steps, around the rooms): breadth first."""
        free = lambda p: 0 <= p[0] < w and 0 <= p[1] < h and lv.tiles.get(p) in (None, " ", "#")
        prev, q = {a: None}, deque([a])
        while q:
            u = q.popleft()
            if u == b:
                break
            for dx, dy in ORTHO:
                v = (u[0] + dx, u[1] + dy)
                if v not in prev and free(v):
                    prev[v] = u
                    q.append(v)
        u = b if b in prev else None
        while u is not None:
            if lv.tiles.get(u) in (None, " "):
                lv.tiles[u] = "#"
            u = prev[u]
    for a, b in zip(boxes, boxes[1:]):
        da, db = door(a, "e"), door(b, "w")
        corridor(out(da, a), out(db, b))
    if len(boxes) > 2:                                 # an extra joint: a junction in the corridors
        da, db = door(boxes[0], "s"), door(boxes[2], "s")
        corridor(out(da, boxes[0]), out(db, boxes[2]))
    if spur:                                           # a dead end
        x0, y0, x1, y1 = boxes[-1]
        p = door(boxes[-1], "n")
        q = out(p, boxes[-1])
        for y in range(q[1], max(0, q[1] - 3), -1):
            if lv.tiles.get((q[0], y)) in (None, " "):
                lv.tiles[(q[0], y)] = "#"
    lv.start = (boxes[0][0], boxes[0][1])
    lv.stairs = (boxes[-1][2], boxes[-1][3])
    lv.tiles[lv.stairs] = ">"
    return lv


class Monster:
    def __init__(self, name, pos, hostile=True, speed=1):
        self.name, self.pos, self.hostile, self.speed = name, pos, hostile, speed


class Sim:
    """The exerciser's world: the ego in a level, monsters, sight, and NLE's perception.

        sim = Sim(level, monsters, seed)
        sim.perceive() → [atoms]     the screen as world/perceive.py would read it (seen and remembered)
        sim.act(action, dir) → message kind   move / open / kick (a direction), wait; the monsters take their turn
    """

    def __init__(self, level, monsters=(), seed=1):
        self.lv, self.monsters, self.rng = level, list(monsters), random.Random(seed)
        self.ego, self.turn, self.won, self.memory = level.start, 0, False, {}
        self.message = "welcome"
        self._look()

    def sight(self):
        """The cells in sight: the lit room the ego stands in (with its walls), else the eight around."""
        x, y = self.ego
        for (x0, y0, x1, y1) in self.lv.rooms:
            if x0 <= x <= x1 and y0 <= y <= y1:
                return {(a, b) for a in range(x0 - 1, x1 + 2) for b in range(y0 - 1, y1 + 2)}
        return {(x + dx, y + dy) for dx in (-1, 0, 1) for dy in (-1, 0, 1)}

    def _look(self):
        for p in self.sight():
            if p in self.lv.tiles:
                self.memory[p] = self.lv.tiles[p]

    def perceive(self):
        atoms = set()
        vis = self.sight()
        for p, t in self.memory.items():
            c = cell(*p)
            if t == ".":
                atoms.add("floor(%s)" % c)
            elif t == "#":
                atoms.add("corridor(%s)" % c)
            elif t in "|-":
                atoms.add("wall(%s)" % c)
            elif t == ">":
                atoms.add("stairs_down(%s)" % c)
                atoms.add("floor(%s)" % c)
            elif t == "+":
                st = self.lv.doors.get(p, "closed")
                atoms.add("floor(%s)" % c) if st in ("doorway", "broken") else atoms.add("door(%s,%s)" % (c, "open" if st == "open" else "closed"))
        atoms.add("agent_at(%s)" % cell(*self.ego))
        for m in self.monsters:
            if m.pos in vis:
                atoms.add("monster(%s,%s)" % (m.name, cell(*m.pos)))
        return sorted(atoms)

    def act(self, action, d=None):
        """The ego's action, then the monsters' turn. → the message's kind (perceive.MESSAGES' names)."""
        self.turn += 1
        kind = "other"
        if action in ("move", "open", "kick") and d in STEPS:
            dx, dy = STEPS[d]
            p = (self.ego[0] + dx, self.ego[1] + dy)
            m = next((m for m in self.monsters if m.pos == p), None)
            if action == "move" and m is not None:
                self.monsters.remove(m)
                kind = "killed"
            elif action == "move":
                if self.lv.passable(p) and self.lv.step_ok(self.ego, p):
                    self.ego = p
                    kind = "other"
                else:
                    kind = "door_closed" if self.lv.tiles.get(p) == "+" else "blocked"
            elif action == "open" and self.lv.tiles.get(p) == "+":
                st = self.lv.doors[p]
                if st == "closed":
                    self.lv.doors[p], kind = "open", "door_opened"
                elif st == "locked":
                    kind = "door_locked"
            elif action == "kick" and self.lv.tiles.get(p) == "+" and self.lv.doors[p] in ("closed", "locked"):
                if self.rng.random() < 0.5:
                    self.lv.doors[p], kind = "broken", "other"
        for m in list(self.monsters):
            for _ in range(m.speed):
                if m.hostile:
                    path = self.lv.bfs(m.pos, self.ego, through_doors=False)
                    if len(path) > 2 and not any(o.pos == path[1] for o in self.monsters):
                        m.pos = path[1]
                elif self.rng.random() < 0.3:
                    nb = [(m.pos[0] + dx, m.pos[1] + dy) for dx, dy in STEPS.values()]
                    nb = [p for p in nb if self.lv.passable(p) and p != self.ego and not any(o.pos == p for o in self.monsters)]
                    if nb:
                        m.pos = self.rng.choice(nb)
        self.won = self.ego == self.lv.stairs
        self._look()
        self.message = kind
        return kind
