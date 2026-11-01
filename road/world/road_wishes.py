"""road_wishes.py — what the person asked of the drive (road-agent s-357becc7 step 3): the task's rules name a wish here, and the planner's copy of the world reads it. Only the
planner's facts change, and only as far as they already gate its own rules: no new predicate, no change to the planner or the responder, road's image as it was. The planner
still decides by its keep-table, the restrictor and the responder see the world as it is, so a wish can never make the drive less safe than the planner alone.

    easy      above EASY_MS the planner reads at_limit: it stops speeding up (it does not brake)
    brisk     a lead ahead reads as slow: the planner looks for a way past sooner
    lane D    the other side unsettled, the lead slow, no speeding up or keeping the limit: `change` to D is what is left, when it is safe; else it follows
    pass      as lane, either side
    follow    no side settled: no lane change
    stop      nothing to speed up or keep: the planner's own gentle brake (brake_follow) until the car stands, and holds it; go takes it back
    a turn    no wish of the planner's: the ego's route (SumoWorld.turn); when the turn needs another lane, the lane wish for it (turn_lanes)
    the route the host's own lane wish, QUIET (nothing said): towards a lane that continues the route (SumoWorld.lane_for_route)
A one-shot wish (lane, pass) stands WISH_TICKS planner ticks, then is dropped and the reason said; at once when there is no lane on that side."""
import re

EASY_MS = 6.0
WISH_TICKS = 10
SIDES = ("left", "right")


def new():
    return {"pace": "normal", "want": None, "age": 0, "quiet": False, "own_edge": None, "follow": False, "stop": False, "turn": None, "said": []}


def take(w, rule, binding=None):
    """A fired rule of the task's → the wish; `binding` the roles, for `around`."""
    m = re.match(r"(\w+)(?:\[(?:\w+=(\w+))\])?", rule)
    name, value = m.group(1), m.group(2)
    if name == "pace":
        w["pace"] = value
    elif name == "lane":
        w.update(want=value, age=0, quiet=False, follow=False)
    elif name == "pass":
        w.update(want="any", age=0, quiet=False, follow=False)
    elif name == "stop":
        w.update(stop=True, want=None)
    elif name == "go":
        w["stop"] = False
    elif name == "follow":
        w.update(want=None, follow=True)
    elif name == "resume":
        w.update(pace="normal", want=None, follow=False, stop=False, turn=None)
    return name


def around(facts, binding):
    """The roles in words, as the ego believes them."""
    words = {"lead": "a car ahead", "follower": "a car behind", "leadleft": "a car ahead on the left", "followleft": "a car behind on the left",
             "leadright": "a car ahead on the right", "followright": "a car behind on the right"}
    seen = [w for r, w in words.items() if r in binding]
    line = "I see " + ", ".join(seen) + "." if seen else "I see no one near."
    if any(a.startswith("dangerous(") for a in facts):
        line += " One of them is too close: the responder is on it."
    return line


def why_not(facts, want):
    """Why a lane change has not come, from the planner's own conditions."""
    sides = SIDES if want == "any" else (want,)
    open_ = [s for s in sides if "adjacent(%s)" % s in facts]
    if not open_:
        return "there is no lane on the %s" % sides[0] if want != "any" else "there is no lane beside me"
    for s in open_:
        if "settled(%s)" % s not in facts:
            return "I only just left the %s lane" % s
        for role in ("lead" + s, "follow" + s):
            if "safe_long(%s)" % role not in facts or "safe_lat(%s)" % role not in facts:
                return "a car is too close on the %s" % s
    return "it is not safe yet"


def planner_facts(w, facts, v):
    """The planner's copy of the world, with the wish in it."""
    out = dict(facts)
    if w["stop"]:
        for a in ("below_limit", "at_limit", "lead_ok", "lead_slow", "accel_ok", "keep_ok"):
            out.pop(a, None)
        out["keep_no"] = 1
        return out
    if w["pace"] == "easy" and v >= EASY_MS and "below_limit" in out:
        del out["below_limit"]
        out["at_limit"] = 1
    if w["pace"] == "brisk" and "lead_ok" in out and "keep_ok" in out:
        del out["lead_ok"]
        out["lead_slow"] = 1
    if w["follow"]:
        for s in SIDES:
            out.pop("settled(%s)" % s, None)
    if w["want"]:
        for s in SIDES:
            if w["want"] not in ("any", s):
                out.pop("settled(%s)" % s, None)
        out.pop("below_limit", None)
        out.pop("at_limit", None)
        out.pop("lead_ok", None)
        out["lead_slow"] = 1
    return out


def turn_lanes(w, lane):
    """A turn asked for that leaves from other lanes of this edge: the lane wish towards them, as long as it takes. LANE: the ego's (edge, index)."""
    edge, wanted = w["turn"] or (None, ())
    if lane is None or lane[0] != edge or not wanted or lane[1] in wanted:
        return
    w.update(want="left" if lane[1] < min(wanted) else "right", age=0, quiet=False)      # SUMO counts lanes from the right


def route_lane(w, edge, side):
    """The host's wish for the lane that continues the route (SIDE, or None), unless a wish stands or the person chose the lane on this EDGE: the route then follows that lane."""
    if w["want"] and not w["quiet"]:
        w["own_edge"] = edge
    if side and not w["want"] and not w["stop"] and w["own_edge"] != edge:
        w.update(want=side, age=0, quiet=True)


def without_sides(facts, sides):
    """The world with no lane on SIDES (SumoWorld.lane_sides): a shoulder beside the ego is no lane to change to."""
    return {a: n for a, n in facts.items() if not any(a in ("adjacent(%s)" % s, "settled(%s)" % s) for s in sides)}


def planner_tick(w, facts):
    """One planner tick on the world as it is: a wish met or dropped, its words said."""
    if not w["want"]:
        return
    if any(a.startswith("changing(") for a in facts):
        if not w["quiet"]:
            w["said"].append("Changing lane now.")
        w["want"] = None
        return
    w["age"] += 1
    if w["age"] >= WISH_TICKS or not any("adjacent(%s)" % s in facts for s in (SIDES if w["want"] == "any" else (w["want"],))):
        if not w["quiet"]:
            w["said"].append("Not now: %s. I have dropped it." % why_not(facts, w["want"]))
        w["want"] = None
