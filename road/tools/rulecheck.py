#!/usr/bin/env python3
"""rulecheck.py — the road's accounting on a run's log: the ego against a short list of European road rules, from the log's ticks and the net's lanes, connections and light programs.
An account, not a judge: no rule of the road's domains reads it; what it counts are the loop's surprises later. README.md says which rules and what the counts leave out.

    python3 road/tools/rulecheck.py road/.metis/road/log.jsonl road/maps/Town03.net.xml
    python3 road/tools/rulecheck.py --sort TRACE_DIR [--cases DIR] LOG          (the run's RSS violations, each sorted: sort_rows; needs metis.trace)"""
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


# The RSS violations (sumo_host.account: the applied acceleration above the bound of the truth's fold when it was decided), each sorted
# into why it is one, from the log's row and the responder's facts on the trace (the architect's five, s-357becc7):
BOUND = {"brake_min": -4.0, "brake_min_correct": -3.0}     # the passenger ego's (semantic_world.lane VCLASS), the bound each response gives
RECENT_TICKS = 60                                          # how far back a release's lane change is looked for: settled_to holds 2 s
CLASSES = {1: "checker", 2: "projection", 3: "competing", 4: "responder", 5: "gap", 6: "unseen, the other's duty"}


def bound(pairs):
    """The tightest bound of a row's dangerous pairs, None when no response binds."""
    return min((BOUND[p["resp"]] for p in pairs if p["resp"] in BOUND), default=None)


def violations(rows):
    """(the row the command was decided on, the row it was applied in), as sumo_host.account counts them."""
    return [(a, b) for a, b in zip(rows, rows[1:]) if b["a"] is not None and bound(a["truth"]) is not None and b["v"] > 0 and b["a"] > bound(a["truth"]) + 1e-9]


def edge_of(lane):
    return lane.rsplit("_", 1)[0]


def changed_lane(rows, pair):
    """Did the truth see PAIR's car change lanes on one road in ROWS (the rows before)? True, False, or None when it did not see the car: a truth row names its car."""
    car = pair["id"].split(":")[0]
    seen = [p["lane"] for r in rows for p in r["truth"] if p["id"].split(":")[0] == car and p["lane"]]
    return any(a != b and edge_of(a) == edge_of(b) for a, b in zip(seen, seen[1:] + [pair["lane"]])) if seen else None


def sort_row(before, row, facts, recent=()):
    """One violation → (class, the reason in words). FACTS: the responder's atoms when BEFORE's projection had reached it (the trace's tick after, ROW's).
    RECENT: the rows before BEFORE, to check a release's settled_to against the truth."""
    cmd = row["cmd"][0] if row["cmd"] else None
    braking = [a for a in facts if a.startswith("resp_lon(brake")]
    believed = [p for p in before["danger"] if p["resp"] in BOUND]
    seen = before.get("seen_ids")        # a log before the field: not sorted here
    bound_pairs = [p for p in before["truth"] if p["resp"] in BOUND]
    if seen is not None and bound_pairs and all(":xing_ego_prio" in p["id"] and p["id"].split(":")[0] not in seen for p in bound_pairs):
        return 6, "the truth has %s dangerous, the ego has the way over it and the sensor does not see it: the yielder's violation, listed, as sumo_host.account does" % bound_ids(before)
    if cmd == "brake" and row["cmd"][1] in BOUND:
        return 4, "the command is the shield's, and the acceleration is above the bound only by rounding or the car's limit"
    if braking:
        return 3, "the responder's fact held (%s) and the command is %s: another rule held the controls" % (braking[0], cmd)
    if believed:
        settled = [a for a in facts if a.startswith("settled_to(%s," % believed[0]["role"])]
        real = next((p for p in before["truth"] if (p["lane"], p["s"]) == (believed[0]["lane"], believed[0]["s"])), None)
        if settled and real is not None and changed_lane(recent, real) is False:
            return 2, "the fold released %s on %s, and %s is false: the truth saw that car change no lane" % (believed[0]["id"], settled[0], settled[0])
        if settled:
            return 1, "the belief has %s dangerous, the fold released it (%s): the projection's ruled release, which the truth's fold does not have" % (believed[0]["id"], settled[0])
        return 5, "the belief has %s dangerous, no response in the facts and no release: nothing read it" % believed[0]["id"]
    return 2, "the truth has %s dangerous, the belief no dangerous pair: the projection's facts are false against the world" % bound_ids(before)


def bound_ids(row):
    return ", ".join(p["id"] for p in row["truth"] if p["resp"] in BOUND)


def facts_at(trace_dir, ticks):
    """The responder's atoms at each of TICKS, walked from its checkpoint and its beats on the trace."""
    from metis import trace
    wanted, out = set(ticks), {}
    segs = trace.read(trace_dir)
    counts = dict(segs[0].checkpoint["sessions"]["responder"]["counts"])
    for seg in segs:
        for t in seg.ticks:
            for item in (t["members"].get("responder") or {}).get("seq") or ():
                for line in list(item.get("take", ())) + list(item.get("beat", ())):
                    if line[0] == "+":
                        counts[line[1:].split(" ")[0]] = 1
                    else:
                        counts.pop(line[1:].split(" ")[0], None)
            if t["k"] in wanted:
                out[t["k"]] = sorted(counts)
    return out


def sort_rows(log, trace_dir, cases=None):
    """The verdict rows of a run: {tick, norm, class, name, why, command, a, v, zone, truth, belief}; CASES: a surprise case per violation there."""
    rows = [r for r in map(json.loads, open(log)) if "resp" in r]
    found = violations(rows)
    facts = facts_at(trace_dir, [b["tick"] for _, b in found])
    out = []
    at = {r["tick"]: i for i, r in enumerate(rows)}
    for a, b in found:
        n, why = sort_row(a, b, facts.get(b["tick"], ()), rows[max(0, at[a["tick"]] - RECENT_TICKS):at[a["tick"]]])
        out.append({"tick": b["tick"], "norm": "rss_response", "class": n, "name": CLASSES[n], "why": why, "command": b["cmd"], "a": b["a"], "v": a["v"], "zone": a["zone"],
                    "truth": [p["id"] for p in a["truth"] if p["resp"] in BOUND], "belief": [p["id"] for p in a["danger"] if p["resp"] in BOUND]})
    if cases:
        from metis import trace
        os.makedirs(cases, exist_ok=True)
        for r in out:
            with open(os.path.join(cases, "surprise-%d.yaml" % r["tick"]), "w") as f:
                f.write(trace.case(trace_dir, "responder", r["tick"], out=["brake_lon*"], note="class %d %s: %s" % (r["class"], r["name"], r["why"])))
    return out


def main_sort(args):
    cases = args[args.index("--cases") + 1] if "--cases" in args else None
    rows = sort_rows(args[-1], args[args.index("--sort") + 1], cases)
    for r in rows:
        print(json.dumps(r))
    print(json.dumps({"violations": len(rows), "by_class": {CLASSES[n]: sum(r["class"] == n for r in rows) for n in CLASSES}}))


if __name__ == "__main__":
    if "--sort" in sys.argv:
        main_sort(sys.argv[1:])
        sys.exit(0)
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    main(sys.argv[1], sys.argv[2])
