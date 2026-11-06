"""walkers (scenario-catalog s-92e0b650 step 4): a walker on SUMO as a host-side body on a virtual crosswalk. On a fake two-way road
(sumolib's faces only: no SUMO here): the crosswalk crosses both directions' lanes from beyond the right edge, a zone per lane,
the walker's priority only on a zebra; the trigger, the walk, the pose in the truth, the contact; the lane map extended."""
import math
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "world"))
import walkers as W  # noqa: E402
from semantic_world.lane import LaneMap  # noqa: E402

LANE_W = 3.2


class Node:
    def __init__(self, nid):
        self.id, self.out = nid, []

    def getOutgoing(self):
        return self.out


class Lane:
    """A straight lane along y = Y (direction +x, or -x when REV), LANE_W wide."""

    def __init__(self, lid, y, rev=False, length=200.0):
        self.id, self.y, self.rev, self.length = lid, y, rev, length

    def getID(self):
        return self.id

    def getWidth(self):
        return LANE_W

    def getShape(self):
        return [(self.length, self.y), (0.0, self.y)] if self.rev else [(0.0, self.y), (self.length, self.y)]

    def getClosestLanePosAndDist(self, xy):
        x = xy[0]
        return (self.length - x if self.rev else x), abs(xy[1] - self.y)


class Edge:
    def __init__(self, eid, lanes, frm, to):
        self.id, self.lanes, self.frm, self.to = eid, lanes, frm, to
        frm.out.append(self)

    def getID(self):
        return self.id

    def getLanes(self):
        return self.lanes

    def getFromNode(self):
        return self.frm

    def getToNode(self):
        return self.to


class Net:
    """Edge e: two lanes the ego's way (e_0 right at y 0, e_1 at y 3.2); its reverse r: one lane at y 6.4, the other way."""

    def __init__(self):
        a, b = Node("a"), Node("b")
        self.e = Edge("e", [Lane("e_0", 0.0), Lane("e_1", LANE_W)], a, b)
        self.r = Edge("r", [Lane("r_0", 2 * LANE_W, rev=True)], b, a)

    def getEdge(self, eid):
        return {"e": self.e, "r": self.r}[eid]


def walker(**kw):
    a = {"id": "w", "kind": "pedestrian", "place": {"route": ["e"], "lane": 1, "pos": 100.0}, "at": {"ahead": 40, "side": "right"},
         "trigger": {"tta": 2.0, "dist": 6.0}, "script": [{"when": "trigger", "go": True, "v": 2.0}]}
    a.update(kw)
    return a


def test_the_crosswalk_crosses_every_lane_of_both_directions_from_beyond_the_right_edge():
    w = W.Walker(Net(), walker())
    assert math.isclose(w.start[0], 100.0) and math.isclose(w.start[1], -LANE_W / 2 - W.CURB_M)      # 1.5 m beyond e_0's right edge
    assert math.isclose(w.dir[1], 1.0, abs_tol=1e-9)                                                   # straight across, +y
    assert math.isclose(w.length, 3 * LANE_W + 2 * W.CURB_M)
    lanes = {next(k for k in z.lanes if k != w.lane_id): z.lanes[w.lane_id] for z in w.zones}
    assert set(lanes) == {"e_0", "e_1", "r_0"}
    assert lanes["e_0"][0] < lanes["e_1"][0] < lanes["r_0"][0], "met in the order it walks"
    assert all(z.priority is None for z in w.zones), "mid-block: no priority"
    assert all(z.lanes["e_1"] == (98.0, 102.0) for z in w.zones if "e_1" in z.lanes)


def test_a_zebra_gives_the_walker_the_priority_and_side_left_starts_beyond_the_far_edge():
    w = W.Walker(Net(), walker(crossing="zebra", at={"ahead": 40, "side": "left"}))
    assert all(z.priority == w.lane_id for z in w.zones)
    assert math.isclose(w.start[1], 2 * LANE_W + LANE_W / 2 + W.CURB_M) and w.dir[1] < 0


def test_the_trigger_the_walk_and_the_pose_then_gone():
    ws = W.Walkers(Net(), [walker()])
    w = ws.all[0]
    ws.tick(0.0, lambda e, p: 50.0, 10.0)                   # 5 s away, 50 m: not yet
    assert w.fired is None and ws.truth()["w"]["speed"] == 0.0
    ws.tick(0.1, lambda e, p: 15.0, 10.0)                   # TTA 1.5 s <= 2.0
    assert w.fired == 0.1 and w.go_at == 0.1
    ws.tick(0.2, lambda e, p: 14.0, 10.0)
    p = ws.truth()["w"]
    assert p["lane"] == "vw_w" and math.isclose(p["s"], 0.2) and p["vclass"] == "pedestrian" and p["speed"] == 2.0
    for k in range(200):
        ws.tick(0.3 + 0.1 * k, lambda e, p: 0.0, 0.0)
    assert w.gone and ws.truth() == {}


def test_contact_is_the_boxes_touching():
    ws = W.Walkers(Net(), [walker()])
    p = ws.truth()["w"]
    assert ws.touching({"x": p["x"], "y": p["y"] + 3.0, "heading": 0.0, "length": 4.5, "width": 1.8}, 1.0) == []
    assert ws.touching({"x": p["x"], "y": p["y"] + 1.0, "heading": 0.0, "length": 4.5, "width": 1.8}, 1.1) == ["w"]
    assert ws.contacts == [(1.1, "w")]


def test_the_lane_map_gains_the_crosswalk_and_its_zones():
    lm = LaneMap([])
    ws = W.Walkers(Net(), [walker()])
    ws.extend(lm)
    assert "vw_w" in lm.lanes and lm.lanes["vw_w"].shape[0] == ws.all[0].start and len(lm.zones) == 3
