#!/usr/bin/env python3
"""road/maps/lane_speeds.py NET... — the post-pass build.sh runs after netconvert (road-scenarios s-e23be780, 2026-11-05).

CARLA's OpenDRIVE states no speed for its parking and bidirectional (centre) lanes, so netconvert gives them its
default, 1.39 m/s. CARLA has no such cap, and the family's keep_limit reads a lane's limit as the road's rule: a pass
or a return over such a lane crawled. This pass sets the speed of every lane whose OpenDRIVE kind is parking or
bidirectional to its edge's driving speed (the max over the edge's driving lanes). Nothing else moves: the lane types
(the edge's `type`, one kind per lane by index, or one kind for all its lanes), the shapes and the net's offset stay
byte for byte; only those lanes' `speed` attributes change. An edge with no driving lane, or whose kinds do not match
its lanes, is left as it is and named on stderr. Internal (junction) lanes have no kind and are not touched.
Idempotent: a second run changes nothing. Standard library only (no sumolib).
"""
import re
import sys

LIFT = {"parking", "bidirectional"}
EDGE = re.compile(r'(<edge id="([^"]*)"([^>]*)>)(.*?)(</edge>)', re.S)
LANE = re.compile(r'<lane id="[^"]*" index="(\d+)"[^>]*?speed="([-\d.]+)"')


def kinds(attrs, n):
    """The kind of each of the edge's n lanes, by index, or None when the edge's type does not say."""
    m = re.search(r'\stype="([^"]*)"', attrs)
    if not m:
        return None
    t = m.group(1).split("|")
    return t * n if len(t) == 1 else t if len(t) == n else None


def lift(text, name="net"):
    changed, skipped = 0, []

    def edge(m):
        nonlocal changed
        head, eid, attrs, body, tail = m.groups()
        if 'function="' in attrs:
            return m.group(0)
        lanes = LANE.findall(body)
        ks = kinds(attrs, len(lanes))
        if ks is None or not LIFT & set(ks):
            return m.group(0)
        drive = [float(v) for (i, v) in lanes if ks[int(i)] == "driving"]
        if not drive:
            skipped.append(eid)
            return m.group(0)
        top = max(drive)

        def lane(lm):
            nonlocal changed
            i, v = int(lm.group(1)), lm.group(2)
            if ks[i] in LIFT and float(v) != top:
                changed += 1
                g, s = lm.group(0), lm.start(0)
                return g[: lm.start(2) - s] + "%.2f" % top + g[lm.end(2) - s:]
            return lm.group(0)

        return head + LANE.sub(lane, body) + tail

    out = EDGE.sub(edge, text)
    for eid in skipped:
        print("%s: edge %s has parking/bidirectional lanes and no driving lane: left as it is" % (name, eid), file=sys.stderr)
    return out, changed


def main(paths):
    for p in paths:
        with open(p) as f:
            text = f.read()
        out, n = lift(text, p)
        if out != text:
            with open(p, "w") as f:
                f.write(out)
        print("%s: %d parking/bidirectional lanes set to their edge's driving speed" % (p, n))


if __name__ == "__main__":
    main(sys.argv[1:])
