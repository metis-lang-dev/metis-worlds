#!/usr/bin/env python3
"""rulecheck.py — the road's accounting on a run's log: the ego against a short list of European road rules, from the log's ticks and the net's lanes, connections and light programs.
An account, not a judge: no rule of the road's domains reads it; what it counts are the loop's surprises later. README.md says which rules and what the counts leave out.

    python3 road/tools/rulecheck.py road/.metis/road/log.jsonl road/maps/Town03.net.xml
    python3 road/tools/rulecheck.py --sort TRACE_DIR [--cases DIR] LOG          (the run's RSS violations, each sorted: sort_rows; needs metis.trace)
    python3 road/tools/rulecheck.py --truth LOG [TRACE_DIR]                     (a class against the truth: truth_rows; the trace for the classes)"""
import collections
import json
import os
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
                state = {"red": "r", "amber": "y"}.get(a.get("signal"), "G") if "signal" in a else light_at(net, c, b["sumo_t"])    # the log's light where it has one
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


# The RSS violations, each sorted into why it is one: metispy's `python -m metis.trace sort` (lifted from here, checks-open
# s-17e557f0, so the chair's logs sort too). These are its road defaults and thin calls, imported late: the counts above need no metis.
BOUND = {"brake_min": -4.0, "brake_min_correct": -3.0}     # the passenger ego's (semantic_world.lane VCLASS), the bound each response gives


def bound(pairs):
    """The tightest bound of a row's dangerous pairs, None when no response binds."""
    return min((BOUND[p["resp"]] for p in pairs if p["resp"] in BOUND), default=None)


def violations(rows):
    from metis.trace import sort_violations
    return sort_violations(rows, BOUND)


def changed_lane(rows, pair):
    from metis.trace import changed_lane as f
    return f(rows, pair)


def sort_row(before, row, facts, recent=()):
    from metis.trace import sort_row as f
    return f(before, row, facts, recent, BOUND)


def sort_rows(log, trace_dir, cases=None):
    """The verdict rows of a run (metis.trace.sort with the road's defaults)."""
    from metis.trace import sort
    return sort(trace_dir, log, cases=cases)


# T10 truth (checks-open s-17e557f0; Fact against truth, Nobody's pair): the road's, since it reads the role binding of the log row,
# the truth's (lane, s) to match a track to a body, and SUMO's contacts, none of which metis.trace knows.
MOTION = ("settled_to",)          # role classes that claim the body moved: a lane change seen complete
TRUTH_WINDOW = 60                 # rows looked back for the lane change (settled_to holds 2 s)


def truth_rows(log, trace_dir=None, member="responder"):
    """(a) a motion class held of a body the truth shows doing nothing: one row per window {from, to, class, role, body, kind: idle};
    (b) a contact on a pair the projection calls not_relevant: {tick, body, kind: "no pair", type}. A log without `contact` gives
    one note row for (b), never a silent pass; (a) needs the trace."""
    rows = [r for r in map(json.loads, open(log)) if "resp" in r]
    out = []
    if trace_dir:
        from metis.trace import changed_lane, member_atoms
        facts = member_atoms(trace_dir, member, [r["tick"] + 1 for r in rows])
        held = {}
        for i, r in enumerate(rows):
            for a in facts.get(r["tick"] + 1, ()):
                pred, _, args = a.partition("(")
                if pred not in MOTION:
                    continue
                role = args.split(",")[0]
                mine = next((p for p in r.get("danger", ()) if p["role"] == role), None)
                real = mine and next((p for p in r.get("truth", ()) if (p["lane"], p["s"]) == (mine["lane"], mine["s"])), None)
                if real is None or changed_lane(rows[max(0, i - TRUTH_WINDOW):i], real) is not False:
                    continue
                key = (a, real["id"].split(":")[0])
                w = held.get(key)
                if w and w["to"] == rows[i - 1]["tick"]:
                    w["to"] = r["tick"]
                else:
                    held[key] = w = {"from": r["tick"], "to": r["tick"], "class": a, "role": role, "body": key[1], "kind": "idle"}
                    out.append(w)
    if not any("contact" in r for r in rows):
        out.append({"kind": "note", "why": "no contact records in this log: (b) not checked"})
    for r in rows:
        for c in r.get("contact") or ():
            if c.get("type") in (None, "not_relevant"):
                out.append({"tick": r["tick"], "body": c["id"], "kind": "no pair", "type": c.get("type")})
    return out


def main_sort(args):
    cases = args[args.index("--cases") + 1] if "--cases" in args else None
    rows = sort_rows(args[-1], args[args.index("--sort") + 1], cases)
    for r in rows:
        print(json.dumps(r))
    from metis.trace import sort_summary
    print(json.dumps(sort_summary(rows)))


if __name__ == "__main__":
    if "--truth" in sys.argv:
        args = sys.argv[sys.argv.index("--truth") + 1:]
        for r in truth_rows(args[0], args[1] if len(args) > 1 else None):
            print(json.dumps(r))
        sys.exit(0)
    if "--sort" in sys.argv:
        main_sort(sys.argv[1:])
        sys.exit(0)
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    main(sys.argv[1], sys.argv[2])
