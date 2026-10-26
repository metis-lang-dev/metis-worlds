"""road-world step 4: the lane adapter's belief (semantic_world.road) on a synthetic three-lane road — a keeping car
stays keep, a car drifting left becomes change_left, unseen the support spreads along and across, two cars with no
identity keep their own tracks through the gate, the per-tick table's hazard into the ego's danger region is high
under the intent that brings the car in."""
from semantic_world import road
from semantic_world.lane import Lane, LaneMap


def three_lanes(length=300.0):
    ls = [Lane("e_0", length, left="e_1"), Lane("e_1", length, left="e_2", right="e_0"), Lane("e_2", length, right="e_1")]
    return LaneMap(ls)


def rmap(tmp_path):
    return road.RoadMap.build(str(tmp_path / "road.json"), three_lanes(), dt=0.5)


def det(lane, s, v=10.0, cls="passenger"):
    return {"class": cls, "lane": lane, "s": s, "speed": v}


def test_a_keeping_car_stays_keep(tmp_path):
    m = rmap(tmp_path)
    for i in range(8):
        m.cycle([det("e_1", 50 + 5 * i)])
    p = m.load()["intent"]
    (t,) = p
    assert max(p[t], key=p[t].get) == "keep" and p[t]["keep"] > 0.7


def test_a_car_drifting_left_becomes_change_left(tmp_path):
    m = rmap(tmp_path)
    path = [("e_0", 50), ("e_0", 55), ("e_1", 60), ("e_1", 65), ("e_2", 70)]
    for lane, s in path:
        m.cycle([det(lane, s)])
    (t,) = m.load()["intent"]
    p = m.load()["intent"][t]
    assert max(p, key=p.get) == "change_left", p


def test_unseen_the_support_spreads(tmp_path):
    m = rmap(tmp_path)
    m.cycle([det("e_1", 50)])
    sizes = []
    for _ in range(6):
        m.cycle([])
        (t,) = m.load()["belief"]
        sizes.append(len([c for c, p in m.load()["belief"][t].items() if p >= 0.01]))
    assert sizes == sorted(sizes) and sizes[-1] > sizes[0], sizes


def test_two_cars_keep_their_tracks_through_the_gate(tmp_path):
    m = rmap(tmp_path)
    for i in range(5):
        m.cycle([det("e_0", 40 + 5 * i), det("e_2", 120 + 5 * i)])
    d = m.load()
    assert len(d["things"]) == 2
    lanes = sorted(road.of(next(iter(d["belief"][t])))[0] for t in d["things"])
    assert lanes == ["e_0", "e_2"]


def test_the_table_hazard_follows_the_intent(tmp_path):
    """The ego in e_0 at s 40, 10 m/s; a car beside-ahead in e_1 at s 55, 10 m/s: under change_right it comes into
    the ego's lane inside its safe distance (a high first-tick hazard), under keep it does not."""
    m = rmap(tmp_path)
    ego = {"lane": "e_0", "s": 40.0, "speed": 10.0, "route": ["e_0"]}
    m.cycle([det("e_1", 55)], ego=ego)
    t = m.predict_table(4)
    (n,) = t["tracks"]
    cr = [r["closing(%s,change_right)" % n] for r in t["rows"]]
    kp = [r["closing(%s,keep)" % n] for r in t["rows"]]
    assert t["unit"] == "tick" and len(t["rows"]) == 4
    assert cr[0] > 0.1 and all(k < 0.02 for k in kp), (cr, kp)
    assert set(t["intent"][n]) == set(road.INTENTS)


def test_cars_a_bin_apart_keep_their_tracks_by_exact_sighting():
    """Three cars on one lane a few metres apart, moving together: each keeps its track tick after tick (the exact
    association; a cell gate swapped them, and the situation layer's pair memory followed the wrong car)."""
    from semantic_world.lane import Lane, LaneMap
    from semantic_world.road import RoadMap
    import tempfile, os
    lm = LaneMap([Lane("a", 500.0, left="b"), Lane("b", 500.0, right="a")])
    m = RoadMap.build(os.path.join(tempfile.mkdtemp(), "m.json"), lm, dt=0.1)
    cars = {"x": 20.0, "y": 27.0, "z": 33.0}
    names = None
    for k in range(30):
        dets = [{"class": "passenger", "lane": "a", "s": s + 0.7 * k, "speed": 7.0} for s in cars.values()]
        m.cycle(dets, (), {"lane": "a", "s": 0.0, "speed": 7.0, "route": ["a"]})
        d = m.load()
        order = sorted(d["pos"], key=lambda t: d["pos"][t]["s"])
        names = names or order
        assert order == names and len(d["pos"]) == 3
