"""cr_lanes — the semantic LaneMap straight from a CommonRoad scenario's lanelets, NO SUMO conversion (planner-loop
s-0dcc5ed1, the user's option 1, 2026-11-07). Reads the JSON road/planner/cr_lanelets.py writes (commonroad-io's
lanelets in CommonRoad coordinates); pure Python (the Live's venv never imports CommonRoad).

    lanemap_from(doc) → semantic_world.lane.LaneMap

- A lanelet is a Lane (id = the lanelet id): its centre line the shape, its length the centre line's, its width the mean
  gap of its bounds, its speed the scenario's limit (cr_lanelets: TrafficSignInterpreter; None when unsigned), its
  successors succ.
- Neighbours: same-direction adjacent lanelets form one EDGE (index 0 the rightmost, the net's convention, so a change is
  an index step as on SUMO); an adjacent lanelet the other way is the leftmost lane's left with left_opposite (the
  oncoming lane a pass borrows) and symmetric on the right.
- A lanelet an intersection's incoming leads into (its left / straight / right successors) is the junction's internal
  lane (junction = the intersection id).
- ZONES: two lanelets whose centre lines run inside each other's polygon, neither the other's successor or neighbour and
  not leaving one predecessor together (a fork shares no area that matters), meet in a zone; each lane's (s_enter,
  s_leave) the span of its centre line inside the other's polygon. Priority: the lane WITHOUT a yield / stop sign when
  exactly one of the two approaches has one; None otherwise (the family's own rules: right before left)."""
import math

from semantic_world.lane import Lane, LaneMap, Zone

YIELD_SIGNS = ("YIELD", "STOP")          # commonroad-io's TrafficSignIDGermany names (the element ids in the rows)


def _len(pts):
    return sum(math.hypot(b[0] - a[0], b[1] - a[1]) for a, b in zip(pts, pts[1:]))


def _cum(pts):
    out = [0.0]
    for a, b in zip(pts, pts[1:]):
        out.append(out[-1] + math.hypot(b[0] - a[0], b[1] - a[1]))
    return out


def inside(pt, poly):
    x, y = pt
    n, hit = len(poly), False
    for i in range(n):
        x1, y1 = poly[i]
        x2, y2 = poly[(i + 1) % n]
        if (y1 > y) != (y2 > y) and x < (x2 - x1) * (y - y1) / ((y2 - y1) or 1e-12) + x1:
            hit = not hit
    return hit


def polygon(la):
    return [tuple(p) for p in la["left"]] + [tuple(p) for p in reversed(la["right"])]


def _bbox(poly):
    xs, ys = [p[0] for p in poly], [p[1] for p in poly]
    return min(xs), min(ys), max(xs), max(ys)


def _width(la):
    n = min(len(la["left"]), len(la["right"]))
    if n == 0:
        return 3.5
    return sum(math.hypot(la["left"][i][0] - la["right"][i][0], la["left"][i][1] - la["right"][i][1]) for i in range(n)) / n


def _dense(pts, step=0.5):
    """The polyline resampled every STEP metres (a zone's span is read off these points)."""
    out = [tuple(pts[0])]
    for a, b in zip(pts, pts[1:]):
        d = math.hypot(b[0] - a[0], b[1] - a[1])
        n = max(1, int(d / step))
        out += [(a[0] + (b[0] - a[0]) * i / n, a[1] + (b[1] - a[1]) * i / n) for i in range(1, n + 1)]
    return out


def groups(rows):
    """Same-direction neighbours → edges: {lanelet id: (edge id, index)}, index 0 the rightmost."""
    by = {r["id"]: r for r in rows}
    out = {}
    for r in rows:
        if r["id"] in out:
            continue
        start = r                                        # walk right to the rightmost same-direction neighbour
        seen = {start["id"]}
        while start.get("adj_right") is not None and start.get("adj_right_same") and start["adj_right"] in by \
                and start["adj_right"] not in seen:
            start = by[start["adj_right"]]
            seen.add(start["id"])
        chain, cur = [], start
        while cur is not None and cur["id"] not in [c["id"] for c in chain]:
            chain.append(cur)
            nxt = cur.get("adj_left")
            cur = by.get(nxt) if nxt is not None and cur.get("adj_left_same") else None
        edge = "e%d" % min(c["id"] for c in chain)
        for i, c in enumerate(chain):
            out.setdefault(c["id"], (edge, i))
    return out


def lanemap_from(doc):
    rows = doc.get("lanelets") or []
    by = {r["id"]: r for r in rows}
    grp = groups(rows)
    junction_of = {}
    for it in doc.get("intersections") or []:
        for inc in it.get("incomings") or []:
            for lid in (inc.get("left") or []) + (inc.get("straight") or []) + (inc.get("right") or []):
                junction_of[lid] = str(it["id"])
    signs = {s["id"]: s for s in doc.get("signs") or []}

    def yields(lid):
        r = by.get(lid) or {}
        for sid in r.get("signs") or []:
            if any(e.get("id") in YIELD_SIGNS for e in (signs.get(sid) or {}).get("elements") or []):
                return True
        return False

    lanes = []
    for r in rows:
        lid = r["id"]
        shape = [tuple(p) for p in r.get("center") or []]
        edge, index = grp[lid]
        ln = Lane(id=str(lid), length=_len(shape), width=_width(r), succ=[str(s) for s in r.get("successors") or []],
                  speed=r.get("speed"), shape=shape, edge=edge, index=index,
                  internal=lid in junction_of, junction=junction_of.get(lid))
        for side in ("left", "right"):
            other = r.get("adj_" + side)
            if other is None or other not in by:
                continue
            same = bool(r.get("adj_%s_same" % side))
            setattr(ln, side, str(other))
            setattr(ln, side + "_opposite", not same)
        lanes.append(ln)

    zones = []
    polys = {r["id"]: polygon(r) for r in rows}
    boxes = {k: _bbox(p) for k, p in polys.items()}
    dense = {r["id"]: _dense(r.get("center") or [[0, 0], [0, 0]]) for r in rows}
    cums = {k: _cum(v) for k, v in dense.items()}
    ids = sorted(by)
    for i, a in enumerate(ids):
        ra = by[a]
        for b in ids[i + 1:]:
            rb = by[b]
            if b in (ra.get("successors") or []) or a in (rb.get("successors") or []):
                continue
            if b in (ra.get("adj_left"), ra.get("adj_right")) or grp[a][0] == grp[b][0]:
                continue
            if set(ra.get("predecessors") or []) & set(rb.get("predecessors") or []):
                continue
            ba, bb = boxes[a], boxes[b]
            if ba[2] < bb[0] or bb[2] < ba[0] or ba[3] < bb[1] or bb[3] < ba[1]:
                continue
            sa = [cums[a][k] for k, p in enumerate(dense[a]) if inside(p, polys[b])]
            sb = [cums[b][k] for k, p in enumerate(dense[b]) if inside(p, polys[a])]
            if not sa or not sb:
                continue
            ya, yb = yields(a) or yields(_pred_of(by, a)), yields(b) or yields(_pred_of(by, b))
            prio = str(b) if ya and not yb else str(a) if yb and not ya else None
            zones.append(Zone(id="z%d_%d" % (a, b), lanes={str(a): (min(sa), max(sa)), str(b): (min(sb), max(sb))},
                              priority=prio, junction=junction_of.get(a) or junction_of.get(b)))
    return LaneMap(lanes, zones)


def _pred_of(by, lid):
    """The approach of a junction lanelet: its (first) predecessor, where the yield sign stands."""
    preds = (by.get(lid) or {}).get("predecessors") or []
    return preds[0] if preds else None
