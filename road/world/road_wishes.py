"""road_wishes.py — what the person asked of the drive (road-agent s-357becc7 step 3): the task's rules name a wish here, and the planner's copy of the world reads it. Only the
planner's facts change, and only as far as they already gate its own rules: no new predicate. It never says a thing of the world: lead_slow is the truth of a slow lead, and a wish is a change_reason. The planner
still decides by its keep-table, the restrictor and the responder see the world as it is, so a wish can never make the drive less safe than the planner alone.

    easy      a target speed, EASY_MS (pace_limit): the host's target classes read it (road_facts.facts, pace), so the planner brakes down to it with its own soft brake
    brisk     a lead ahead is a reason to change, each adjacent side: the planner looks for a way past sooner
    lane D    a reason to change to D, the other side unsettled: `change` to D when it is safe; until then it drives on by the target classes
    pass      as lane, either side
    follow    no side settled: no lane change
    stop      a target of 0: the planner's own gentle brake (brake_target) until the car stands (STOPPED), and it keeps that; go takes it back
    a turn    no wish of the planner's: the ego's route (SumoWorld.turn); when the turn needs another lane, the lane wish for it (turn_lanes)
    the route the host's own lane wish, QUIET (nothing said): towards a lane that continues the route (SumoWorld.lane_for_route)
A one-shot wish (lane, pass) stands WISH_TICKS planner ticks, then is dropped and the reason said; at once when there is no lane on that side."""
import re

EASY_MS = 6.0
WISH_TICKS = 10
SIDES = ("left", "right")
STOPPED = 0.1      # m/s: under this, a stop wish's target of 0 is met


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
        if "zone_at(nextzone,near)" in facts or "zone_at(nextzone,at)" in facts:
            return "too close to the junction"
        for role in ("lead" + s, "follow" + s):
            if "safe_long(%s)" % role not in facts or "safe_lat(%s)" % role not in facts:
                return "a car is too close on the %s" % s
    return "it is not safe yet"


def pace_limit(w):
    """The target speed the pace asks of the host's classes, or None."""
    return EASY_MS if w["pace"] == "easy" else None


def planner_facts(w, facts, v):
    """The planner's copy of the world, with the wish in it."""
    out = dict(facts)
    if w["stop"]:
        for a in ("below_target", "at_target", "above_target", "lead_ok", "lead_slow", "accel_ok", "change_reason(left)", "change_reason(right)"):
            out.pop(a, None)
        out["above_target" if v > STOPPED else "at_target"] = 1
        return out
    if w["pace"] == "brisk" and "type(lead,not_relevant)" not in out:
        out.update(("change_reason(%s)" % s, 1) for s in SIDES if "adjacent(%s)" % s in out)
    if w["follow"]:
        for s in SIDES:
            out.pop("settled(%s)" % s, None)
    if w["want"]:
        for s in SIDES:
            if w["want"] not in ("any", s):
                out.pop("settled(%s)" % s, None)
                out.pop("change_reason(%s)" % s, None)
            elif "adjacent(%s)" % s in out:
                out["change_reason(%s)" % s] = 1
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
    return {a: n for a, n in facts.items() if not any(a in ("adjacent(%s)" % s, "settled(%s)" % s, "change_reason(%s)" % s) for s in sides)}


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
