"""road_wishes.py — what the person asked of the drive (road-agent s-357becc7 step 3): the task's rules name a wish here, and the planner's copy of the world reads it. Only the
planner's facts change, and only as far as they already gate its own rules: no new predicate, no change to the planner or the responder, road's image as it was. The planner
still decides by its keep-table, the restrictor and the responder see the world as it is, so a wish can never make the drive less safe than the planner alone.

    easy      above EASY_MS the planner reads at_limit: it stops speeding up (it does not brake)
    brisk     a lead ahead reads as slow: the planner looks for a way past sooner
    lane D    the other side unsettled, the lead slow, no speeding up or keeping the limit: `change` to D is what is left, when it is safe; else it follows
    pass      as lane, either side
    follow    no side settled: no lane change
A one-shot wish (lane, pass) stands WISH_TICKS planner ticks, then is dropped and the reason said."""
import re

EASY_MS = 6.0
WISH_TICKS = 10
SIDES = ("left", "right")


def new():
    return {"pace": "normal", "want": None, "age": 0, "follow": False, "said": []}


def take(w, rule, binding=None):
    """A fired rule of the task's → the wish; `binding` the roles, for `around`."""
    m = re.match(r"(\w+)(?:\[(?:\w+=(\w+))\])?", rule)
    name, value = m.group(1), m.group(2)
    if name == "pace":
        w["pace"] = value
    elif name == "lane":
        w.update(want=value, age=0, follow=False)
    elif name == "pass":
        w.update(want="any", age=0, follow=False)
    elif name == "follow":
        w.update(want=None, follow=True)
    elif name == "resume":
        w.update(pace="normal", want=None, follow=False)
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


def planner_tick(w, facts):
    """One planner tick on the world as it is: a wish met or dropped, its words said."""
    if not w["want"]:
        return
    if any(a.startswith("changing(") for a in facts):
        w["said"].append("Changing lane now.")
        w["want"] = None
        return
    w["age"] += 1
    if w["age"] >= WISH_TICKS:
        w["said"].append("Not now: %s. I have dropped it." % why_not(facts, w["want"]))
        w["want"] = None
