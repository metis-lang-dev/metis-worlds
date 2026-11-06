"""scenario_cards — the CARLA challenge scenarios as the road world's scene cards (road-scenarios s-e23be780 step 2;
nina's triage in step 1). A card (road/catalog/carla/<NAME>.yaml) is one scenario TYPE of scenario_runner / the
Leaderboard: what happens, its actors placed relative to the ego and the trigger, the source's own trigger
condition and parameters (with their ranges), what the family is expected to do (the laws it exercises: the
hypothesis a surprise falsifies) and the Leaderboard's infractions. The same card plays on two worlds:

- the EXERCISER (road_world.py: one synthetic 600 m road, three lanes, a crosswalk at s 250, a side road at s 400,
  no lights): the actors placed on its road relative to the ego (`exerciser`), the trigger armed on its movers
  (road_world.Agent.armed); kinematic cards only (lead brakes, a stopped vehicle, a cut-in, a car taking priority);
- SUMO (sumo_host over TraCI, on CARLA's Town01/02/03 converted, road/maps): the card's SITES, the Leaderboard 1.0
  trigger poses of its shape in our towns (road/catalog/carla/sites/, CARLA's data, MIT), placed by CARLA's own
  co-simulation transform with the net's netOffset (`carla_to_sumo`; nina verified it on all 834 poses).

    import scenario_cards as C
    C.names()                        the cards
    C.load("ParkedObstacle")         a card (dict); "NAME:VARIANT" with a generated variant applied
    C.exerciser("card:ParkedObstacle")(rng)   its spec for road_world.RoadWorld
    C.variants(card)                 research note §4b: per main parameter two clear values and three borderline
    C.sites(card, "Town03")          its trigger poses in a town, in SUMO's frame
    C.check(card, summary)           the card's expect against a run's summary: [failure, …]
    C.driving_score(infractions, completion)   the Leaderboard 2.0's DS for one route
"""
import copy
import json
import re
from pathlib import Path

import yaml

ROAD = Path(__file__).resolve().parents[1]
SCEN = ROAD / "catalog" / "carla"            # the CARLA cards, v2 (road/docs/SCENARIO-CARD.md; in road/scenarios before scenario-catalog step 4)
SITES = SCEN / "sites" / "lb1-triggers-town010203.json"
MAPS = ROAD / "maps"
# the regulation groups a card's `tags` name (road/docs/SCENARIO-CARD.md §5; a tag is added by the architect, with its coverage.md row)
TAG_VOCABULARY = ("following", "lane-keeping", "lane-change", "overtaking", "oncoming-pass", "cut-in", "merge-zipper", "junction-priority",
                  "right-before-left", "stop-sign", "yield-sign", "traffic-light", "turning-left", "turning-right", "roundabout",
                  "pedestrian-crossing", "cyclist", "emergency-vehicle", "parking", "obstacle-static", "route-following", "speed-limit",
                  "visibility", "highway-ramp")
MODES = ("scripted", "recorded", "model")
STATUS = ("pass", "soft", "fail", "world", "skip")
HOSTS = ("exerciser", "sumo")                  # the verdict is per host (road/docs/SCENARIO-CARD.md §6b)
SITE_REF = re.compile(r"S(\d+)\.(\d+)")      # a site from another LB1 scenario's poses: "S1.157" = Scenario1's #157

# the exerciser's road (road_world.road()): the ego's lane and start, the zones a card's `at` names
EGO_LANE, EGO_S = 1, 20.0
AT = {"junction": 400.0, "crosswalk": 250.0}
KIND = {"car": ("passenger", 4.5, 1.8), "emergency": ("passenger", 5.0, 2.0), "static": ("passenger", 4.5, 1.8),
        "bicycle": ("bicycle", 1.8, 0.7), "walker": ("pedestrian", 0.5, 0.5), "pedestrian": ("pedestrian", 0.5, 0.5), "truck": ("truck", 12.0, 2.5)}

# the Leaderboard 2.0's penalties (leaderboard a87a3419 utils/statistics_manager.py, nina's step 1 §d)
PENALTY = {"collisions_pedestrian": 0.50, "collisions_vehicle": 0.60, "collisions_layout": 0.65, "red_light": 0.70,
           "stop_infraction": 0.80, "scenario_timeouts": 0.70, "yield_emergency_vehicle_infractions": 0.70}


def names():
    return sorted(p.stem for p in SCEN.glob("*.yaml"))


def load(name):
    """The card NAME (road/catalog/carla/NAME.yaml); "NAME:VARIANT" applies one of its generated variants."""
    name = name[5:] if name.startswith("card:") else name
    base, _, var = name.partition(":")
    card = yaml.safe_load((SCEN / ("%s.yaml" % base)).read_text())
    if var:
        vs = variants(card)
        if var not in vs:
            raise KeyError("%s has no variant %r (it has: %s)" % (base, var, ", ".join(vs)))
        card = apply(card, vs[var])
        card["variant"] = var
    return card


# ── the parameters and their variants (research note §4b) ──
def _path(card, path):
    """A card's value at a dotted path: actors.ID.KEY… (an actor by its id), else keys."""
    node, keys = card, path.split(".")
    for i, k in enumerate(keys):
        if isinstance(node, list):
            node = next(x for x in node if x.get("id") == k)
        elif i == len(keys) - 1:
            return node, k
        else:
            node = node[k]
    raise KeyError(path)


def apply(card, overrides):
    """CARD with OVERRIDES {dotted path: value} set (a copy)."""
    out = copy.deepcopy(card)
    for path, v in overrides.items():
        node, k = _path(out, path)
        node[k] = v
        for p in (out.get("params") or {}).values():          # the parameter's value follows what drives it
            if p.get("drives") == path:
                p["value"] = v
    return out


def variants(card):
    """§4b: for each parameter with a `threshold` (the value at which the law's behaviour flips: the ego can no longer
    stop, change or yield in time), two CLEAR values far on its `safe` side and three BORDERLINE next to it (×0.9,
    ×1.0, ×1.1), within the source's range where it has one. → {name: {path: value}}."""
    out = {}
    for pname, p in (card.get("params") or {}).items():
        th, path = p.get("threshold"), p.get("drives")
        if th is None or not path:
            continue
        lo, hi = (p.get("range") or [None, None])[:2]
        far = [th * 2.5, th * 3.5] if p.get("safe", "above") == "above" else [th * 0.4, th * 0.25]
        clamp = lambda v: v if lo is None or lo >= hi else max(lo, min(hi, v))   # noqa: E731 (one value: no range to keep)
        for i, v in enumerate(far, 1):
            out["%s-clear%d" % (pname, i)] = {path: round(clamp(v), 2)}
        for tag, f in (("lo", 0.9), ("at", 1.0), ("hi", 1.1)):
            out["%s-border-%s" % (pname, tag)] = {path: round(th * f, 2)}
    return out


# ── the exerciser ──
def _lane(offset):
    return "e_%d" % max(0, min(2, EGO_LANE + int(offset or 0)))


def exerciser(name):
    """The card's spec for road_world.RoadWorld: the ego on e_1 at s 20 (or the card's `exerciser.ego_s`), each actor
    `at` {ahead | behind: m, lane: offset (+1 left, −1 right)} or {road: side, s} (the side road), its script steps
    {t | when: {...} | when: trigger, after: s, go | speed | v | brake | lane (offset)}; `when` is the source's trigger
    on this road (road_world._arm), `after` delays a step past it (a cut-in's lane change within its change time)."""
    card = load(name)
    ex = card.get("exerciser") or {}
    if ex.get("skip"):
        raise ValueError("%s does not play on the exerciser: %s" % (card["scenario"], ex["skip"]))

    def spec(rng):
        ego_s = float(ex.get("ego_s", EGO_S))
        ego = {"lane": _lane(0), "s": ego_s, "v": float(card["ego"]["v"])}
        agents = []
        for a in card.get("actors") or []:
            vclass, length, width = KIND[a.get("kind", "car")]
            at = a["at"]
            if at.get("road") == "side":
                lane, s = "c_0", float(at.get("s", 5.0))
            elif a.get("kind") == "pedestrian":                  # a walker crosses on the exerciser's crosswalk w_0 (road_world._walker)
                lane, s = "w_0", 0.0
            else:
                lane = _lane(at.get("lane", 0))
                s = ego_s + float(at.get("ahead", 0.0)) - float(at.get("behind", 0.0))
            ag = {"id": a["id"], "lane": lane, "s": s, "v": float(a.get("v", 0.0)), "vclass": vclass,
                  "length": float(a.get("length", length)), "width": float(a.get("width", width)),
                  "moving": a.get("moving", True), "breaks_rules": a.get("breaks_rules", False), "script": [], "armed": []}
            for st in a.get("script") or []:
                after = float(st.get("after", 0.0))       # a step `after` s past its trigger (a cut-in: speed, then the lane)
                steps = [(k, (_lane(at.get("lane", 0) + st[k]) if k == "lane" else st[k]), after)
                         for k in ("go", "speed", "v", "brake", "lane") if k in st]
                if "when" in st:
                    w = dict(a["trigger"] if st["when"] == "trigger" else st["when"])   # the actor's own trigger: a variant drives it
                    if isinstance(w.get("at"), str):
                        w["at"] = AT[w["at"]]
                    ag["armed"].append((w, steps))
                else:
                    ag["script"] += [(float(st.get("t", 0.0)) + d, k, v) for k, v, d in steps]
            agents.append(ag)
        return {"ego": ego, "dest": float(ex.get("dest", 580.0)), "side_prio": bool(ex.get("side_prio", False)),
                "agents": agents}
    return spec


# ── the sites (SUMO) ──
def offset(town):
    """The net's netOffset (road/maps/TOWN.net.xml): what netconvert added to CARLA's x and −y."""
    with open(MAPS / ("%s.net.xml" % town)) as f:
        for line in f:
            m = re.search(r'netOffset="([-\d.]+),([-\d.]+)"', line)
            if m:
                return float(m.group(1)), float(m.group(2))
    raise ValueError("%s: no netOffset" % town)


def carla_to_sumo(x, y, yaw, town):
    """CARLA's co-simulation bridge (bridge_helper.get_sumo_transform) with the net's offset: x + ox, −y + oy, yaw + 90
    (CARLA is left-handed). SUMO places a vehicle by its FRONT: the director adds half the length along the heading."""
    ox, oy = offset(town)
    return x + ox, -y + oy, (yaw + 90.0) % 360.0


def sites(card, town):
    """The card's trigger poses in TOWN, in SUMO's frame: [{i, carla: {x, y, yaw}, sumo: {x, y, angle}}]."""
    s = card.get("sites") or {}
    if not s.get("lb1") or town not in (s.get("towns") or {}):
        return []
    data = json.loads(SITES.read_text())["data"][town]
    poses = data.get(s["lb1"], [])                    # Town01/02 have no S2 poses: FollowLeadingVehicle's S1.N sites there
    want = s["towns"][town]
    out = []
    for i in (range(len(poses)) if want == "all" else want):
        m = SITE_REF.fullmatch(str(i))                 # OVTP's junction 1082 sits in Scenario1's poses (nina's review §5)
        p = data["Scenario%s" % m.group(1)][int(m.group(2))] if m else poses[i]
        x, y, yaw = float(p["x"]), float(p["y"]), float(p["yaw"])
        sx, sy, ang = carla_to_sumo(x, y, yaw, town)
        out.append({"i": i, "carla": {"x": x, "y": y, "yaw": yaw}, "sumo": {"x": round(sx, 2), "y": round(sy, 2), "angle": round(ang, 1)}})
    return out


# ── the expectation and the score ──
def check(card, summary, arrived=None):
    """The card's `expect` against a run's summary (road_world.summary(): collisions, violations, …) and its arrival:
    [failure, …], empty when it held."""
    exp = card.get("expect") or {}
    out = []
    for k in ("collisions", "violations"):
        if k in exp and summary.get(k, 0) > exp[k]:
            out.append("%s %s > %s" % (k, summary.get(k), exp[k]))
    if exp.get("arrived") and arrived is False:
        out.append("not arrived")
    held = sum(((summary.get("director") or {}).get("emergency_held_s") or {}).values())
    if "emergency_held_s" in exp and held > exp["emergency_held_s"]:
        out.append("held the emergency vehicle %.1f s > %s" % (held, exp["emergency_held_s"]))
    return out


def driving_score(infractions, completion=100.0):
    """The Leaderboard 2.0's DS for one route: route completion (%) × the product of the penalties per infraction
    ({kind: count}); outside_route_lanes and min_speed as percentages: (1 − pct/100), 1 − 0.3·(1 − pct/100)."""
    p = 1.0
    for kind, n in (infractions or {}).items():
        if kind in PENALTY:
            p *= PENALTY[kind] ** int(n)
        elif kind == "outside_route_lanes":
            p *= 1.0 - float(n) / 100.0
        elif kind == "min_speed_infractions":
            p *= 1.0 - 0.3 * (1.0 - float(n) / 100.0)
    return round(completion * p, 2)
