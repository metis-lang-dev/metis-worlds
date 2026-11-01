#!/usr/bin/env python3
"""rulecheck.py — the road's accounting on a run's log: the ego against a short list of European road rules, from the log's ticks and the net's lanes, connections and light programs.
An account, not a judge: no rule of the road's domains reads it; what it counts are the loop's surprises later. README.md says which rules and what the counts leave out.

    python3 road/tools/rulecheck.py road/.metis/road/log.jsonl road/maps/Town03.net.xml"""
import collections
import json
import sys
import xml.etree.ElementTree as ET

CRAWL_MS = 3.0        # a lane limited below this is a parking lane or a shoulder in CARLA's nets, not a lane to drive
OVER_MS = 0.3         # what counts as over a limit
LATE_M = 30.0         # a lane change this near the lane's end is at the stop line
ABRUPT_MS = 1.0       # speed lost in one tick (0.1 s): no brake does this


def read_net(path):
    root = ET.parse(path).getroot()
    speed, length, entry, lights = {}, {}, {}, {}
    for e in root.findall("edge"):
        for la in e.findall("lane"):
            speed[la.get("id")], length[la.get("id")] = float(la.get("speed")), float(la.get("length"))
    for t in root.findall("tlLogic"):
        phases = [(float(p.get("duration")), p.get("state")) for p in t.findall("phase")]
        lights[t.get("id")] = (float(t.get("offset") or 0), phases, sum(d for d, _ in phases))
    for c in root.findall("connection"):
        if c.get("via") and not c.get("from", "").startswith(":"):   # a turn's second internal segment is no entry to a junction
            entry[c.get("via")] = c
    return {"speed": speed, "length": length, "entry": entry, "lights": lights}


def light_at(net, c, t):
    """The state of connection C's light at SUMO time T, from the net's program."""
    offset, phases, total = net["lights"][c.get("tl")]
    x = (t + offset) % total
    for d, s in phases:
        if x < d:
            return s[int(c.get("linkIndex"))]
        x -= d


def runs_of(rows):
    """The log's runs (a new run starts again at tick 1): the tick rows of each."""
    runs = []
    for r in rows:
        if r.get("tick") == 1:
            runs.append([])
        if runs and "tick" in r:
            runs[-1].append(r)
    return runs


def check(ticks, net):
    """One run's counts."""
    edge = lambda lane: lane.rsplit("_", 1)[0]
    limit = lambda r: net["speed"].get(r["lane"], float("inf"))
    over = [r for r in ticks if r["v"] > limit(r) + OVER_MS]
    out = {"ticks": len(ticks), "moving": sum(r["v"] > 0 for r in ticks),
           "over_limit": sum(1 for r in over if not r["lane"].startswith(":")), "fast_in_junction": sum(1 for r in over if r["lane"].startswith(":")),
           "worst_over": max((round(r["v"] - limit(r), 1) for r in over if not r["lane"].startswith(":") and limit(r) >= CRAWL_MS), default=0.0),
           "red_entries": 0, "amber_entries": 0, "signal_entries": 0, "minor_entries": 0, "minor_at_speed": [], "change_in_junction": 0, "change_at_line": [],
           "stood": sum(r["v"] == 0 for r in ticks), "stood_in_junction": sum(r["v"] == 0 and r["lane"].startswith(":") for r in ticks), "on_crawl_lane": sum(limit(r) < CRAWL_MS for r in ticks),
           "abrupt": [], "stood_by_lane": dict(collections.Counter(r["lane"] for r in ticks if r["v"] == 0).most_common(5))}
    for a, b in zip(ticks, ticks[1:]):
        if a["lane"] != b["lane"] and edge(a["lane"]) == edge(b["lane"]):
            if a["lane"].startswith(":"):
                out["change_in_junction"] += 1
            elif net["length"].get(a["lane"], 0.0) - a["s"] < LATE_M:
                out["change_at_line"].append((b["t"], a["lane"], b["lane"], b["v"]))
        if a["v"] - b["v"] > ABRUPT_MS:
            out["abrupt"].append((b["t"], a["v"], b["v"], b["lane"]))
        c = net["entry"].get(b["lane"])
        if a["lane"] != b["lane"] and c is not None:
            if c.get("tl"):
                state = light_at(net, c, b["sumo_t"])
                out["signal_entries"] += 1
                out["red_entries"] += state in "rR"
                out["amber_entries"] += state in "yY"
            elif c.get("state") in ("m", "w", "s"):
                out["minor_entries"] += 1
                out["minor_at_speed"].append(b["v"])
    return out


def main(log, netfile):
    with open(log) as f:
        rows = [json.loads(line) for line in f]
    net = read_net(netfile)
    for n, ticks in enumerate(runs_of(rows)):
        print("run %d: %s" % (n, json.dumps(check(ticks, net))))


if __name__ == "__main__":
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    main(sys.argv[1], sys.argv[2])
