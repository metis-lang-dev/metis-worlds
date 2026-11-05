"""The scene cards (road-scenarios s-e23be780 step 2): the CARLA challenge scenarios as road/scenarios/*.yaml. Each card
loads with its source and its license; its sites (CARLA's Leaderboard 1.0 trigger poses) land on a lane of our net by
CARLA's own co-simulation transform; its variants are the research note's §4b (two clear, three borderline); and the
road family plays every card on the exerciser as its expectation says (the replay CI runs; SUMO stays out of CI)."""
import importlib.util
import math
import os
import sys
import xml.etree.ElementTree as ET
from functools import lru_cache
from pathlib import Path

import pytest

ROAD = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROAD / "world"))
import scenario_cards as C  # noqa: E402

CARDS = C.names()


def test_every_card_has_its_source_its_license_and_a_place():
    assert len(CARDS) >= 8
    for n in CARDS:
        c = C.load(n)
        assert c["scenario"] == n, n
        src = c["source"]
        assert src["suite"] in ("lb1", "lb2") and src["code"].startswith("srunner/scenarios/") and src["pin"], n
        assert "MIT License, Copyright (c) 2018 CARLA" in src["license"], n
        assert c["verdict"] in ("PORTABLE", "PORTABLE-WALKER"), n
        assert c.get("exercises") and c.get("expect") is not None, n
        assert c.get("sites", {}).get("towns"), n
    assert (C.SITES.parent / "LICENSE").read_text().startswith("The trigger poses in this directory are CARLA's data")


@pytest.mark.parametrize("town,carla,sumo", [          # nina's landmarks (step 1 §b): the bridge's transform, our offsets
    ("Town01", (319.64, -2.20, 180), (319.70, 330.81, 270)),
    ("Town02", (26.65, 187.56, 180), (32.11, 117.00, 270)),
    ("Town03", (114.84, -76.55, 181), (268.15, 275.41, 271)),
])
def test_carlas_transform_with_the_nets_offset(town, carla, sumo):
    x, y, a = C.carla_to_sumo(*carla, town)
    assert (round(x, 2), round(y, 2), round(a)) == sumo


@lru_cache(maxsize=None)
def lanes(town):
    """The net's lanes a car may drive (not internal): [(id, [(x, y), …])]."""
    out = []
    for edge in ET.parse(C.MAPS / ("%s.net.xml" % town)).getroot().iter("edge"):
        if edge.get("function") == "internal":
            continue
        for ln in edge.iter("lane"):
            allow, disallow = ln.get("allow") or "", ln.get("disallow") or ""
            if (allow and "passenger" not in allow) or "passenger" in disallow.split():
                continue
            out.append((ln.get("id"), [tuple(map(float, p.split(",")[:2])) for p in ln.get("shape").split()]))
    return out


def nearest(town, x, y):
    """(distance, SUMO heading of that segment, lane) of the nearest lane segment to (x, y)."""
    best = (1e9, None, None)
    for lid, pts in lanes(town):
        for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
            dx, dy = x1 - x0, y1 - y0
            L2 = dx * dx + dy * dy or 1e-9
            t = max(0.0, min(1.0, ((x - x0) * dx + (y - y0) * dy) / L2))
            d = math.hypot(x - (x0 + t * dx), y - (y0 + t * dy))
            if d < best[0]:
                best = (d, math.degrees(math.atan2(dx, dy)) % 360.0, lid)
    return best


@pytest.mark.parametrize("name", CARDS)
def test_every_site_lands_on_a_lane_of_our_net_heading_its_way(name):
    card = C.load(name)
    for town in card["sites"]["towns"]:
        for s in C.sites(card, town):
            d, heading, lane = nearest(town, s["sumo"]["x"], s["sumo"]["y"])
            dh = abs((heading - s["sumo"]["angle"] + 180.0) % 360.0 - 180.0)
            assert d < 2.0 and dh < 30.0, (town, s, d, heading, lane)


def test_the_variants_are_two_clear_and_three_borderline_per_threshold():
    c = C.load("ParkedObstacle")
    v = C.variants(c)
    assert sorted(v) == ["distance-border-at", "distance-border-hi", "distance-border-lo", "distance-clear1", "distance-clear2"]
    assert [v["distance-border-%s" % k]["actors.parked.at.ahead"] for k in ("lo", "at", "hi")] == [28.8, 32.0, 35.2]
    assert v["distance-clear1"]["actors.parked.at.ahead"] == 80.0 and v["distance-clear2"]["actors.parked.at.ahead"] == 112.0
    b = C.load("ParkedObstacle:distance-border-lo")
    assert b["actors"][0]["at"]["ahead"] == 28.8 and b["params"]["distance"]["value"] == 28.8 and b["variant"] == "distance-border-lo"
    assert C.variants(C.load("HardBreakRoute")) == {}                       # no parameter: no variant
    with pytest.raises(KeyError, match="has no variant"):
        C.load("ParkedObstacle:nope")


def test_the_driving_score_is_the_leaderboards():
    assert C.driving_score({}) == 100.0
    assert C.driving_score({"collisions_vehicle": 1, "red_light": 1}) == 42.0            # 100 × 0.60 × 0.70
    assert C.driving_score({"collisions_pedestrian": 2}, 50.0) == 12.5                    # 50 × 0.5²
    assert C.driving_score({"outside_route_lanes": 10, "min_speed_infractions": 50}) == 76.5   # 100 × 0.9 × 0.85


def test_a_sumo_only_card_refuses_the_exerciser():
    with pytest.raises(ValueError, match="does not play on the exerciser"):
        C.exerciser("card:ParkedObstacleTwoWays")


def test_a_card_plays_on_the_exerciser_with_its_trigger_armed():
    import random
    spec = C.exerciser("card:StaticCutIn")(random.Random(1))
    cut = next(a for a in spec["agents"] if a["id"] == "cutin")
    want = {"beside": True, "tta": 2.7, "dist": 15.0}                 # the source's TTA to the point beside it (nina's review)
    assert cut["lane"] == "e_0" and cut["armed"] == [(want, [("v", 11.1, 0.0)]), (want, [("lane", "e_1", 1.5)])]
    side = C.exerciser("card:OppositeVehicleTakingPriority")(random.Random(1))["agents"][0]
    assert side["lane"] == "c_0" and side["v"] == 0.0 and side["moving"] is False
    assert side["armed"] == [({"at": 400.0, "tta": 2.2, "dist": 12.0}, [("go", True, 0.0), ("speed", 16.7, 0.0)])]


# ── the family on the exerciser: every card as the source places it (CI; a variant is the full run's, scenarios.py) ──
needs_agent = pytest.mark.skipif(importlib.util.find_spec("metis_agent") is None, reason="no metis_agent (its venv)")
# a card the family does not hold: a surprise record of the road workspace (metis-worlds road/.metis/surprises), for the
# pi loop (step 3); the card stays as the source places it, the family is what changes
KNOWN = {
    "OppositeVehicleTakingPriority": "20261105T031542-503be4 (no brake for a car taking priority at TTA 2.2 s)",
    "StaticCutIn": "20261105T031542-40f229 (no brake for a close cut-in: RSS's duty is the other's)",
    "ParkingCutIn": "20261105T031542-87279b (no brake for a car pulling out at 20 km/h)",
}


def road_tree():
    spec = importlib.util.spec_from_file_location("road_tree", ROAD / "experiments" / "road_tree.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@needs_agent
@pytest.mark.parametrize("name", CARDS)
def test_the_family_plays_every_card_on_the_exerciser(name, tmp_path, monkeypatch):
    for k in ("METIS_CATALOG", "METIS_ROAD_RUN", "METIS_ROAD_WORLD"):
        monkeypatch.delenv(k, raising=False)
    card = C.load(name)
    if (card.get("exerciser") or {}).get("skip"):
        pytest.skip("SUMO only: %s" % card["exerciser"]["skip"])
    if name in KNOWN:
        pytest.xfail("a known surprise: %s" % KNOWN[name])
    out = road_tree().run("card:" + name, 1, tmp_path, ticks=int(card["ticks"]))
    assert C.check(card, out, arrived=out["arrived"]) == [], (name, out)


def test_collisions_are_events_the_leaderboards_way():
    """nina's review: CARLA's CollisionTest merges contact with the same other within 5 s into one collision, so a
    rear-end held over ticks is one collisions_vehicle (×0.60), not one per tick."""
    import road_world as R
    w = R.RoadWorld("cruise", 1)
    w.collisions = [{"t": 6.4, "with": "a"}, {"t": 6.5, "with": "a"}, {"t": 9.0, "with": "a"}, {"t": 14.5, "with": "a"},
                    {"t": 6.6, "with": "b"}]
    assert w.collision_events() == 3 and w.summary()["collisions"] == 5 and w.summary()["collision_events"] == 3
    spec = importlib.util.spec_from_file_location("scenarios_x", ROAD / "experiments" / "scenarios.py")
    sx = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(sx)
    card = C.load("StaticCutIn")
    r = sx.row(card, "StaticCutIn", {"arrived": True, "collisions": 9, "collision_events": 1, "violations": 0})
    assert r["lb"] == {"collisions_vehicle": 1} and r["ds"] == 60.0


# ── SUMO (step 2b): the cards placed at their sites; sumolib only (no SUMO run: CI has none) ──
def _sumolib_or_skip():
    sys.path.append(os.path.join(os.environ.get("SUMO_HOME", "/usr/share/sumo"), "tools"))
    return pytest.importorskip("sumolib")


def test_every_card_places_at_every_site_on_sumo():
    """The ego AT the site (CARLA places a scenario's actors relative to its trigger point, the exerciser relative to the
    ego's start: the same), on the site's lane; each actor at its distance along the ego's route; the obstacles'
    distance clipped to the free run minus 66 m (nina's review); traffic on a lane the road lacks queued on this one."""
    _sumolib_or_skip()
    import scenario_director as D
    for n in CARDS:
        card = C.load(n)
        for town in card["sites"]["towns"]:
            for s in C.sites(card, town):
                pl = D.place(card, town, s["i"])
                edge, lane, pos = pl["site"]
                if (card.get("sumo") or {}).get("back"):                    # BACK m before the site, on the way to it
                    assert edge in pl["ego"]["route"] and pl["ego"]["lane"] == lane, (n, town, s)
                else:
                    assert pl["ego"]["route"][0] == edge and pl["ego"]["lane"] == lane, (n, town, s)
                    assert pl["ego"]["pos"] == round(pos + pl["fit"], 2) or abs(pl["ego"]["pos"] - pos - pl["fit"]) < 0.02, (n, town, s)
                assert pl["actors"], (n, town, s)
                for a in pl["actors"]:
                    assert a["place"]["route"] and a["place"]["pos"] > 0, (n, town, s, a["id"])


def test_a_sumo_card_name_and_the_cards_distances_from_the_ego():
    _sumolib_or_skip()
    import scenario_director as D
    assert D.parse("card:ParkedObstacle:distance-clear1@Town03#42") == ("ParkedObstacle:distance-clear1", "Town03", 42)
    with pytest.raises(ValueError, match="card:NAME"):
        D.parse("card:ParkedObstacle")
    pl = D.place(C.load("FollowLeadingVehicle"), "Town03", 0)
    lead = pl["actors"][0]["place"]
    assert lead["route"][0] == pl["site"][0] and lead["pos"] - pl["ego"]["pos"] == 25.0      # the source's 25 m ahead
    yev = D.place(C.load("YieldToEmergencyVehicle"), "Town03", 49)       # behind on the same straight: the ego `fit` m in
    amb = yev["actors"][0]["place"]
    assert amb["route"] == ["67"] and yev["ego"]["route"] == ["67"] and yev["ego"]["pos"] - amb["pos"] == 110.0 and yev["fit"] > 0
    flow = [a["id"] for a in D.place(C.load("ParkedObstacleTwoWays"), "Town01", 0)["actors"]]
    assert flow == ["parked", "oncoming"]                                 # a continuous flow: its source, not a platoon
    with pytest.raises(ValueError, match="not one of its sites"):
        D.place(C.load("ParkedObstacle"), "Town03", 7)


def test_a_cards_sumo_budget_and_way():
    """A card's `sumo` keys: its tick budget on a town (OVTP #30 waited 30 s at a red light past the exerciser's 900 ticks)
    and its onward way (the emergency vehicle needs ~19 s to close 130 m and 5 s more held: the 200 m way ends first)."""
    spec = importlib.util.spec_from_file_location("scenarios_t", ROAD / "experiments" / "scenarios.py")
    sx = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(sx)
    ovtp = C.load("OppositeVehicleTakingPriority")
    assert sx.ticks_of(ovtp, "sumo") == 1800 and sx.ticks_of(ovtp, "exerciser") == 900
    assert sx.ticks_of(C.load("Accident"), "sumo") == 1200
    _sumolib_or_skip()
    import scenario_director as D
    yev = C.load("YieldToEmergencyVehicle")
    assert yev["actors"][0]["v_rel"] == 25.0 and yev["params"]["distance"]["default"] == 140
    assert yev["sumo"]["onward"] == 1 and D.place(yev, "Town03", 49)["ego"]["route"] == ["67"]   # one straight, no junction


def test_ovtp_meets_the_ego_where_the_straight_ways_cross():
    """OVTP's adversary from the right arm whose straight way crosses the ego's (nina's §5: junction 730), its conflict
    point from the internal lanes; a junction whose minor arms only turn onto the ego's road has none."""
    _sumolib_or_skip()
    import scenario_director as D
    card = C.load("OppositeVehicleTakingPriority")
    a1 = D.place(card, "Town03", 1)["actors"][0]["place"]
    a5 = D.place(card, "Town03", 5)["actors"][0]["place"]
    assert a1["conflict"]["frm"] == "-19" and a5["conflict"]["frm"] == "20"           # the two minor arms of 730
    assert (a1["conflict"]["ego_in"], a1["conflict"]["adv_in"]) == (18.4, 9.5)         # nina's table
    assert a1["conflict"]["side"] == a5["conflict"]["side"] == "right"
    with pytest.raises(ValueError, match="crossing the ego's way"):
        D.place(dict(card, sites={"lb1": "Scenario10", "towns": {"Town03": [18]}}), "Town03", 18)
    assert D.parse("card:OppositeVehicleTakingPriority@Town03#S1.157")[2] == "S1.157"


def test_plain_continuations_and_the_flow_source():
    _sumolib_or_skip()
    import scenario_director as D
    net = D.net_of("Town03")
    assert D._plain_prev(net.getEdge("-35")).getID() == "-11" and D._plain_prev(net.getEdge("-11")) is None
    pl = D.place(C.load("ParkedObstacleTwoWays"), "Town01", 1)
    flow = pl["actors"][1]["place"]
    assert flow["flow"] and flow["spawn"] and flow["src_m"] == 195.0                   # 105 m beyond the parked car's 90
