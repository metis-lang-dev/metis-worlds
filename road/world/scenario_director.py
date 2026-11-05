"""scenario_director — a scene card on SUMO (road-scenarios s-e23be780 step 2b): the card at one of its SITES in a CARLA
town (road/maps), its actors placed along the ego's route from the site, its triggers armed and its steps applied each
SUMO step through TraCI. sumo_world.SumoWorld calls the director before every simulationStep (the SUMO host's Loop
stays the one TraCI client).

    scenario name: card:NAME[:VARIANT]@TOWN#SITE      e.g. card:ParkedObstacle@Town03#42
    build(name, work, seed) → (net, routes, script, director)     sumo_world.SCENARIOS' contract, plus the director

Placement (scenario_cards.carla_to_sumo gives the site's pose in SUMO's frame):
- the site's lane: the nearest lane whose heading is within 30° of the pose's; its edge and the position on it;
- the ego: AT the site, departing at the card's speed (CARLA places a scenario's actors relative to its trigger point,
  where the ego is when the scenario starts; the exerciser places them relative to the ego's start: the same), its
  route onward straight through the next junctions for ONWARD_M;
- an actor `at {ahead | behind, lane}`: AHEAD m past (BEHIND m before: back along straight predecessors) the site
  along the ego's route, on the site's lane + LANE (SUMO's lane index grows to the left: +1 left, as the card's).
  The card's main distance is clipped to the free run (the site's
  edge past the site) minus FREE_MARGIN_M (nina's review: the S1 poses sit 10–22 m before a junction), every actor
  moved by the same amount;
- `at {road: side}`: the junction at the end of the site's edge, an incoming edge of another approach, the actor
  SIDE_M before the junction on it (the source's _source_dist 30), its route straight across; added when its trigger
  fires (a car the source spawns moving).
Triggers (as the exerciser's, road_world._arm): `gap` (the ego's driving distance to the actor's rear), `tta`/`dist`
`beside` the actor (the ego's driving distance to the actor's position) or `at: junction` (to the end of the site's
edge), `traveled` (the actor's odometer), `t`. Steps: v (setSpeed), brake (setDecel + setSpeed 0), lane (changeLane
over CHANGE_S), go, speed (a side actor added at that speed, else setSpeed), `after` a delay.
"""
import math
import os
import random
import sys
from functools import lru_cache

import scenario_cards as C

FLOW_MAX = 80                # a flow's cars in one run at most
SYNC_VMAX = 25.0             # a sync actor's top speed (actor_t's maxSpeed)
SYNC_HOLD_S = 1.0            # the sync holds its speed from the ego's last second before the conflict
ONWARD_M = 200.0             # the ego's route past the site (the scenario ends at its junction, as CARLA's WaitEndIntersection: a longer way only adds later junctions)
FREE_MARGIN_M = 66.0         # nina: the card's distance clipped to the free run minus this
SIDE_M = 30.0                # the side actor's start before the junction (the source's _source_dist)
CHANGE_S = 3.0               # a scripted lane change (the source's CutIn change_time)
EGO = "ego"


def _sumolib():
    sys.path.append(os.path.join(os.environ.get("SUMO_HOME", "/usr/share/sumo"), "tools"))
    import sumolib
    return sumolib


@lru_cache(maxsize=None)
def net_of(town):
    return _sumolib().net.readNet(str(C.MAPS / ("%s.net.xml" % town)))


@lru_cache(maxsize=None)
def inet_of(town):
    """The net with its internal lanes: the ways across a junction (OVTP's conflict point)."""
    return _sumolib().net.readNet(str(C.MAPS / ("%s.net.xml" % town)), withInternal=True)


def _via_shape(town, frm, to, li):
    """The shape of the way across the junction from lane LI of FRM onto TO (its internal lanes chained), or None."""
    inet = inet_of(town)
    for c in inet.getEdge(frm.getID()).getConnections(inet.getEdge(to.getID())):
        if c.getFromLane().getIndex() == li and c.getViaLaneID():
            lane = inet.getLane(c.getViaLaneID())
            shape = list(lane.getShape())
            for _ in range(4):
                outs = [x for x in lane.getOutgoingLanes() if x.getID().startswith(":")]
                if not outs:
                    break
                lane = outs[0]
                shape += list(lane.getShape())[1:]
            return shape
    return None


def _cross(P, Q):
    """Where polylines P and Q first cross: (m along P, m along Q), or None."""
    dp = 0.0
    for p0, p1 in zip(P, P[1:]):
        dq = 0.0
        for q0, q1 in zip(Q, Q[1:]):
            rx, ry, sx, sy = p1[0] - p0[0], p1[1] - p0[1], q1[0] - q0[0], q1[1] - q0[1]
            den = rx * sy - ry * sx
            if abs(den) > 1e-9:
                qx, qy = q0[0] - p0[0], q0[1] - p0[1]
                t, u = (qx * sy - qy * sx) / den, (qx * ry - qy * rx) / den
                if 0.0 <= t <= 1.0 and 0.0 <= u <= 1.0:
                    return dp + t * math.hypot(rx, ry), dq + u * math.hypot(sx, sy)
            dq += math.hypot(sx, sy)
        dp += math.hypot(rx, ry)
    return None


def parse(name):
    """card:NAME[:VARIANT]@TOWN#SITE → (card name with its variant, town, site index)."""
    body = name[5:] if name.startswith("card:") else name
    card, _, rest = body.partition("@")
    town, _, site = rest.partition("#")
    site, _, direction = site.partition("~")                # OVTP's direction at a site: #1~left (nina's 2c review §1)
    if direction and direction not in ("left", "right"):
        raise ValueError("%r: a direction is ~left or ~right" % name)
    if not town or not (site.isdigit() or C.SITE_REF.fullmatch(site)):
        raise ValueError("%r: a SUMO card is card:NAME[:VARIANT]@TOWN#SITE" % name)
    return card, town, int(site) if site.isdigit() else site, direction or None


def _heading_at(shape, pos):
    """SUMO's heading (degrees clockwise from north) of SHAPE at POS m along it."""
    run = 0.0
    for (x0, y0), (x1, y1) in zip(shape, shape[1:]):
        seg = math.hypot(x1 - x0, y1 - y0)
        if run + seg >= pos or (x1, y1) == shape[-1]:
            return math.degrees(math.atan2(x1 - x0, y1 - y0)) % 360.0
        run += seg
    return 0.0


def locate(town, x, y, angle):
    """The lane at (x, y) heading ANGLE (SUMO's degrees): (lane, position on it)."""
    sl = _sumolib()
    best = None
    for lane, d in net_of(town).getNeighboringLanes(x, y, 5.0):
        if not lane.allows("passenger"):
            continue
        shape = lane.getShape()
        pos = sl.geomhelper.polygonOffsetWithMinimumDistanceToPoint((x, y), shape, perpendicular=False)
        dh = abs((_heading_at(shape, pos) - angle + 180.0) % 360.0 - 180.0)
        if dh < 30.0 and (best is None or d < best[2]):
            best = (lane, pos, d)
    if best is None:
        raise ValueError("%s: no lane at (%.1f, %.1f) heading %.0f°" % (town, x, y, angle))
    return best[0], best[1]


def _straight_next(edge, lane_index):
    """The edge a car on LANE_INDEX of EDGE goes on to: straight from that lane first, else any way on."""
    outs = []
    for to, conns in edge.getOutgoing().items():
        for c in conns:
            mine = c.getFromLane().getIndex() == lane_index
            outs.append((0 if mine else 1, 0 if c.getDirection() == "s" else 1, to.getID(), to))
    return sorted(outs, key=lambda o: o[:3])[0][3] if outs else None


def _plain_prev(edge):
    """The edge before EDGE when their node is a plain continuation (one way in, one way on, the ways back aside): a
    walk back over it stays on the same straight (nina's gap-cards review §3, §4); None at a real junction."""
    node = edge.getFromNode()
    ins = [e for e in node.getIncoming() if e.getFromNode() != edge.getToNode()]
    outs = [e for e in node.getOutgoing() if not ins or e.getToNode() != ins[0].getFromNode()]
    return ins[0] if len(ins) == 1 and len(outs) == 1 else None


def _plain_next(edge):
    """The edge after EDGE when their node is a plain continuation; None at a real junction."""
    node = edge.getToNode()
    outs = [e for e in node.getOutgoing() if e.getToNode() != edge.getFromNode()]
    ins = [e for e in node.getIncoming() if not outs or e.getFromNode() != outs[0].getToNode()]
    return outs[0] if len(outs) == 1 and len(ins) == 1 else None


def _room_behind(edge, pos):
    """The straight behind POS on EDGE, back over plain continuations only: (metres, [edges, first first])."""
    room, way = pos, [edge]
    while True:
        prev = _plain_prev(way[0])
        if prev is None or prev in way:
            return room, way
        way.insert(0, prev)
        room += prev.getLength()


def place(card, town, site, direction=None):
    """The card at SITE of TOWN: {site: (edge, lane, pos), ego: {route, lane, pos, v}, actors: [...], junction_s}."""
    card = _sumo_card(card)
    poses = C.sites(card, town)
    p = next((q for q in poses if q["i"] == site), None)
    if p is None:
        raise ValueError("%s: site %s of %s is not one of its sites (%s)" % (card["scenario"], site, town, [q["i"] for q in poses]))
    lane, pos = locate(town, p["sumo"]["x"], p["sumo"]["y"], p["sumo"]["angle"])
    edge, li = lane.getEdge(), lane.getIndex()
    site_pos = pos
    start_s = (card.get("sumo") or {}).get("start_s")         # the ego from START_S on the site's edge (the same straight):
    if start_s is not None and pos > float(start_s):          # ParkingCutIn's poses sit 10-22 m before their edge's end
        pos = float(start_s)
    # an actor BEHIND on the same straight, no junction between (the architect's ruling on nina's §2): when the straight
    # behind the site is shorter, the ego starts that much further into the run (`fit`, recorded)
    behinds = [float(a["at"]["behind"]) for a in card.get("actors") or [] if "behind" in a.get("at", {})]
    fit = 0.0
    if behinds:
        room, _ = _room_behind(edge, pos)
        fit = max(0.0, max(behinds) - room + 0.5)
        if pos + fit > edge.getLength() - 10.0:
            raise ValueError("%s at %s#%s: %.0f m behind does not fit the straight (%.0f m behind, %.0f m on)"
                             % (card["scenario"], town, site, max(behinds), room, edge.getLength() - pos))
        pos += fit
    back, depart = [], pos                          # the ego at the site
    route, run, e = [edge], edge.getLength() - pos, edge
    onward = float((card.get("sumo") or {}).get("onward", ONWARD_M))   # a card whose actor needs a longer way (the emergency vehicle)
    while run < onward:
        e = _straight_next(e, li)
        if e is None or e in route:
            break
        route.append(e)
        run += e.getLength()
    free = edge.getLength() - pos
    # the card's main distance clipped to the free run (nina's review), every actor moved by the same amount
    aheads = [a["at"].get("ahead", 0.0) for a in card.get("actors") or [] if "ahead" in a.get("at", {})]
    clip = "distance" in (card.get("params") or {})          # an obstacle's distance; traffic ahead may pass a junction
    shift = min(0.0, (free - FREE_MARGIN_M) - min(aheads)) if aheads and clip else 0.0
    actors = []
    expanded = []
    for a in card.get("actors") or []:                       # a flow: `count` cars `gap` m apart
        for k in range(int(a.get("count", 1))):
            b = dict(a, id=a["id"] if "count" not in a else "%s_%d" % (a["id"], k), at=dict(a["at"]))
            b["at"]["ahead"] = float(a["at"].get("ahead", 0.0)) + k * float(a.get("gap", 0.0))
            expanded.append(b)
    for a in expanded:
        at = a["at"]
        item = dict(a)
        if at.get("road") == "side":                         # timed: at its speed it reaches the junction as the ego
            tta = float((a.get("trigger") or {}).get("tta", 0.0))      # does from the trigger's TTA (the source's sync)
            sp = max([float(st.get("speed", 0.0)) for st in a.get("script") or []] + [0.0])
            item["place"] = _side(edge, route, sp * tta if sp and tta else SIDE_M, town=town, li=li, sp=sp, tta=tta,
                                  side=direction or at.get("from"))
            if a.get("sync"):                                # CARLA's way and the exerciser's (the architect's 2d): in the
                item["place"]["spawn"] = False               # run standing at its start from t 0, started at the trigger;
                                                             # spawned moving at the trigger it was unseen until then
        elif at.get("opposite") and a.get("flow"):          # a continuous flow's source (OppositeActorFlow): AHEAD m
            ref = next((b for b in expanded if b["id"] == at.get("beyond")), None)      # beyond the BEYOND actor
            s_src = pos + shift + float(at.get("ahead", 0.0)) + (float(ref["at"].get("ahead", 0.0)) if ref else 0.0)
            item["place"] = _opposite(edge, min(s_src, edge.getLength() - 0.2), a, town, site)
            item["place"].update(spawn=True, flow=True, src_m=round(s_src - pos, 1))
        elif at.get("opposite"):
            try:
                item["place"] = _opposite(edge, pos + float(at.get("ahead", 0.0)) + shift, a, town, site)
            except ValueError:
                if "_" in a["id"] and a["id"].rsplit("_", 1)[1].isdigit():
                    continue                                 # a flow's car past the road's end: the flow is the cars that fit
                raise
        else:
            s = pos + float(at.get("ahead", 0.0)) + shift - float(at.get("behind", 0.0))
            way, ri = list(route), 0
            while s < 0:                                     # behind the site: back over plain continuations (fit)
                prev = _plain_prev(way[0])
                if prev is None:
                    raise ValueError("%s at %s#%s: no road %.0f m behind the site" % (a["id"], town, site, -s))
                way.insert(0, prev)
                s += prev.getLength()
            route_a = way
            while s > route_a[ri].getLength() and ri + 1 < len(route_a):
                s -= route_a[ri].getLength()
                ri += 1
            eid = route_a[ri]
            idx = li + int(at.get("lane", 0))
            if not 0 <= idx < eid.getLaneNumber():
                if a.get("script") and any("lane" in st for st in a["script"]):
                    raise ValueError("%s at %s#%d: lane %d off %s (%d lanes)" % (a["id"], town, site, idx, eid.getID(), eid.getLaneNumber()))
                idx = max(0, min(eid.getLaneNumber() - 1, idx))   # traffic on a lane the road lacks: queued on this one,
                s += 15.0                                         # further ahead (Town01/02: one lane each way)
                while s > route_a[ri].getLength() and ri + 1 < len(route_a):
                    s -= route_a[ri].getLength()
                    ri += 1
                eid = route_a[ri]
            if not 0 <= idx < eid.getLaneNumber():
                raise ValueError("%s at %s#%d: lane %d off %s" % (a["id"], town, site, idx, eid.getID()))
            item["place"] = {"route": [x.getID() for x in route_a[ri:]], "lane": idx, "pos": round(max(0.1, s), 2)}
        actors.append(item)
    back = float((card.get("sumo") or {}).get("back", 0.0))  # a junction card whose site is too near its junction for the
    ego_li, s = li, depart - back                            # trigger's TTA: the ego starts BACK m before it (the actors stay)
    while s < 0:                                             # on the same straight only (nina's §4)
        prev = _plain_prev(route[0])
        if prev is None or prev in route or prev.getLaneNumber() <= ego_li:
            s = 0.1
            break
        route.insert(0, prev)
        s += prev.getLength()
    depart = max(0.1, s) if back else depart
    return {"site": (edge.getID(), li, round(site_pos, 2)), "free": round(free, 1), "shift": round(shift, 1), "fit": round(fit, 1),
            "town": town,
            "junction": {"edge": edge.getID(), "pos": edge.getLength()},
            "ego": {"route": [x.getID() for x in route], "lane": li, "pos": round(depart, 2), "v": float(card["ego"]["v"]),
                    "len": round(sum(x.getLength() for x in route) - depart, 1)},
            "actors": actors}


def _opposite(edge, s, a, town, site):
    """The oncoming lane of EDGE (its reverse edge's lane 0) at the point S m along EDGE: the actor faces the ego."""
    rev = next((e for e in edge.getToNode().getOutgoing() if e.getToNode() == edge.getFromNode()), None)
    if rev is None:
        raise ValueError("%s at %s#%d: %s has no oncoming lane" % (a["id"], town, site, edge.getID()))
    p = rev.getLength() - s
    if p < 0.1:
        raise ValueError("%s at %s#%d: %.0f m along %s is past its oncoming lane" % (a["id"], town, site, s, edge.getID()))
    rl = _drive_lane(rev)
    nxt = _straight_next(rev, rl)
    return {"route": [rev.getID()] + ([nxt.getID()] if nxt is not None else []), "lane": rl, "pos": round(p, 2)}


def _side(edge, route, before=None, town=None, li=0, sp=0.0, tta=0.0, side=None):
    """The side actor's way: an incoming edge of the junction at EDGE's end that is not the ego's (nor its reverse),
    BEFORE m (default SIDE_M) before the junction, back over its straight predecessors when it is shorter, and on
    straight across. With TOWN (OVTP's SyncArrival, nina's gap-cards review §5): only an approach whose straight way
    across CROSSES the ego's straight way (a minor arm that only turns onto the ego's road is no such conflict), from
    SIDE (right | left of the ego's heading) when given; BEFORE then times it to the conflict point: at SP it gets
    there as the ego does from the trigger's TTA, at the town's limit; `conflict` is for the director's sync."""
    before = SIDE_M if before is None else before
    node = edge.getToNode()
    mine = {x.getID() for x in route}
    ego_way = _via_shape(town, edge, route[1], li) if town and len(route) > 1 else None
    found = []
    for frm in sorted(node.getIncoming(), key=lambda x: x.getID()):
        if frm.getID() in mine or frm.getFromNode() == edge.getToNode() or frm.getToNode() != node:
            continue
        if frm.getFromNode() == edge.getFromNode():
            continue                               # the ego's reverse
        if not any(ln.allows("passenger") for ln in frm.getLanes()):
            continue
        fl = _drive_lane(frm)
        nxt = _straight_next(frm, fl)
        if nxt is None:
            continue
        conflict = None
        if ego_way is not None:
            if not any(c.getDirection() == "s" for c in frm.getConnections(nxt)):
                continue                           # a turn onto the ego's road (1135, 82): the source's adversary goes straight
            adv_way = _via_shape(town, frm, nxt, fl)
            hit = _cross(ego_way, adv_way) if adv_way else None
            if hit is None:
                continue                           # it turns onto the ego's road: no straight-across conflict
            (hx, hy), (px, py) = (ego_way[1][0] - ego_way[0][0], ego_way[1][1] - ego_way[0][1]), frm.getFromNode().getCoord()
            cx, cy = ego_way[0]
            right = hx * (py - cy) - hy * (px - cx) < 0.0
            conflict = {"ego_in": round(hit[0], 1), "adv_in": round(hit[1], 1), "frm": frm.getID(), "lane": fl,
                        "frm_len": round(frm.getLength(), 2), "side": "right" if right else "left"}
            if side and conflict["side"] != side:
                found.append((frm, nxt, conflict))
                continue
            if sp and tta:
                before = max(1.0, sp * (tta + hit[0] / _ego_v(edge, li)) - hit[1])
        return _side_way(frm, nxt, before, mine, conflict)
    if found:                                      # none from SIDE: the other side's (recorded in `conflict`)
        frm, nxt, conflict = found[0]
        if sp and tta:
            before = max(1.0, sp * (tta + conflict["ego_in"] / _ego_v(edge, li)) - conflict["adv_in"])
        return _side_way(frm, nxt, before, mine, conflict)
    raise ValueError("no side road at the junction after %s%s" % (edge.getID(), " crossing the ego's way" if ego_way else ""))


def _ego_v(edge, li):
    """The ego's speed on lane LI of EDGE for timing: that lane's limit. (sumolib's Edge.getSpeed() is the edge's LAST
    lane's: Town03's 3 reads 1.39 m/s from its bidirectional centre lane 3_2; nina's 2d review.)"""
    return edge.getLane(li).getSpeed()


def lane_type(edge, i):
    """OpenDRIVE's type of lane I of EDGE, as netconvert keeps it in the edge's type ("parking|driving",
    "driving|driving|bidirectional", lane 0 first); "driving" when the net says nothing (Town01/02)."""
    parts = (edge.getType() or "").split("|")
    if len(parts) == edge.getLaneNumber():
        return parts[i]
    return parts[0] if len(parts) == 1 and parts[0] in ("parking", "bidirectional") else "driving"


def _drive_lane(edge):
    """EDGE's rightmost DRIVING lane: Town03's net carries parking and bidirectional lanes, open to cars at 1.39 m/s
    (nina's 2d review: 20_0, -19_0 are parking; the minor arms' driving lane is _1)."""
    for ln in edge.getLanes():
        if ln.allows("passenger") and lane_type(edge, ln.getIndex()) == "driving":
            return ln.getIndex()
    return 0


def _sumo_card(card):
    """The card with its `sumo.at` overrides merged into its actors' `at` (ParkingCutIn on Town03's parking lanes: the
    source's 28 / 35 m from the ego started at `start_s`)."""
    over = (card.get("sumo") or {}).get("at") or {}
    if not over:
        return card
    return dict(card, actors=[dict(a, at=dict(a.get("at") or {}, **over.get(a["id"], {}))) for a in card.get("actors") or []])


def _side_way(frm, nxt, before, mine, conflict):
    if True:
        way, p = [frm], frm.getLength() - before
        while p < 0:                                   # over plain continuations only: never across a junction
            prev = _plain_prev(way[0])
            if prev is None or prev in way or prev.getID() in mine:
                p = 0.1
                break
            way.insert(0, prev)
            p += prev.getLength()
        return {"route": [x.getID() for x in way] + [nxt.getID()], "lane": _drive_lane(frm), "pos": round(max(0.1, p), 2), "spawn": True,
                "conflict": conflict}


def build(name, work, seed=1, n=0, **_):
    """sumo_world.SCENARIOS' contract for a card: (net, routes, script, director)."""
    cname, town, site, direction = parse(name)
    card = C.load(cname)
    pl = place(card, town, site, direction)
    from semantic_world.lane import VCLASS             # the ego's bounds are the family's (the architect's ruling): the law
    b = VCLASS["passenger"]                             # commands brake_max, so the host must be able to execute it
    ego_t = '<vType id="ego_t" accel="%.1f" decel="%.1f" emergencyDecel="%.1f" sigma="0" maxSpeed="20" length="4.5" width="1.8"/>' % (
        b["accel"], b["brake_max"], max(b["brake_max"], 9.0))
    rows = ['<routes>', ego_t,
            '<vType id="actor_t" accel="3.0" decel="8.0" sigma="0" maxSpeed="25" length="4.5" width="1.8"/>',
            '<vType id="emergency_t" vClass="emergency" accel="3.5" decel="8.0" sigma="0" maxSpeed="30" speedFactor="normc(2.2,0,0.2,2.2)" length="5.0" width="2.0"/>']
    e = pl["ego"]
    rows.append('<vehicle id="%s" type="ego_t" depart="0" departLane="%d" departPos="%.2f" departSpeed="%.2f"><route edges="%s"/></vehicle>'
                % (EGO, e["lane"], e["pos"], e["v"], " ".join(e["route"])))
    for a in pl["actors"]:
        pa = a["place"]
        if pa.get("spawn"):
            continue
        vt = "emergency_t" if a.get("kind") == "emergency" else "actor_t"
        length = float(a.get("length", C.KIND[a.get("kind", "car")][1]))
        # speedFactor 2.2: SUMO caps a vehicle at the lane's limit x its speedFactor (13.9 x 2.2 = 30.6), so the source's
        # ego + 25 m/s reaches emergency_t's maxSpeed 30. No bluelight device: SUMO's would move the ego aside itself (it changes others' lanes whatever their lane-change
        # mode), doing the yielding the card asks of the family; the emergency vehicle is its vClass and its speed
        dev = ""
        rows.append('<vehicle id="%s" type="%s" depart="0" departLane="%d" departPos="%.2f" departSpeed="%.2f" length="%.1f"><route edges="%s"/>%s</vehicle>'
                    % (a["id"], vt, pa["lane"], pa["pos"], float(a.get("v", 0.0)), length, " ".join(pa["route"]), dev))
    rows.append("</routes>")
    routes = os.path.join(work, "%s.rou.xml" % name.replace(":", "_").replace("@", "_").replace("#", "_"))
    with open(routes, "w") as f:
        f.write("\n".join(rows) + "\n")
    return str(C.MAPS / ("%s.net.xml" % town)), routes, [], Director(card, pl, seed)


class Director:
    """The card's triggers and steps, applied before each SUMO step (SumoWorld.step)."""

    def __init__(self, card, placed, seed=1):
        self.card, self.pl = card, placed
        self.rng = random.Random(seed)
        self.flows = {}                                                    # a flow actor: {on, n, last, gap, at}
        self.armed, self.queue, self.started, self.spawned = [], [], set(), set()
        for a in placed["actors"]:
            for st in a.get("script") or []:
                when = st.get("when")
                steps = [(k, st[k]) for k in ("go", "speed", "v", "brake", "lane", "flow") if k in st]
                after = float(st.get("after", 0.0))
                if when is None:
                    self.queue.append((float(st.get("t", 0.0)) + after, a, steps))
                else:
                    self.armed.append((a, dict(a["trigger"] if when == "trigger" else when), steps, after))
        self.fired = []                                                    # [(t, actor id, what)] for the report
        self.spawn_v = {}                                                  # a trigger-spawned actor: its speed at insertion
        self.held = {}                                                     # an emergency vehicle: s it was held behind the ego (ours)
        self.lb_ev = {}                                                    # an emergency vehicle: LB 2.0's YieldToEmergencyVehicleTest
        self.triggered = []                                                # [{t, id, ego_tta}]: an armed trigger that fired
        self.removed = []                                                  # [(t, id)]: an other removed at its contact with the ego
        self.driven = 0.0
        self.outside_m = 0.0                                               # the ego's metres off Driving/Parking lanes
        self.ended, self.stood = None, 0.0                                 # the card's `end` (FollowLeadingVehicle's)
        self.sync = {}                                                     # a `sync` actor: {phase, v, t_hold, closest_m}
        self.going = set()                                                 # actors whose go/speed step has fired

    def _dist(self, c, edge, pos):
        try:
            d = c.vehicle.getDrivingDistance(EGO, edge, pos)
        except Exception:                                                  # noqa: BLE001 — not on its route
            return None
        return None if d is None or d < -1e6 else d

    def _target(self, c, a, when):
        """The point the trigger WHEN measures to (nina's 2c review §3) and the ego's distance to it at firing:
        (beside | junction | gap | near | time | traveled | junction_ahead, metres or None)."""
        ids = c.vehicle.getIDList()
        if when.get("beside") and a["id"] in ids:
            return "beside", self._dist(c, c.vehicle.getRoadID(a["id"]), c.vehicle.getLanePosition(a["id"]))
        if when.get("at") == "junction":
            j = self.pl["junction"]
            return "junction", self._dist(c, j["edge"], j["pos"] - 0.1)
        if "gap" in when and a["id"] in ids:
            return "gap", self._dist(c, c.vehicle.getRoadID(a["id"]),
                                     max(0.0, c.vehicle.getLanePosition(a["id"]) - c.vehicle.getLength(a["id"])))
        if "near" in when and when["near"] in ids:
            (ex, ey), (ox, oy) = c.vehicle.getPosition(EGO), c.vehicle.getPosition(when["near"])
            return "near", math.hypot(ex - ox, ey - oy)
        return next((k for k in ("t", "traveled", "junction_ahead") if k in when), "other"), None

    def _hit(self, c, t, a, when):
        if "t" in when and t >= when["t"] - 1e-9:
            return True
        if "near" in when and when["near"] in c.vehicle.getIDList():      # the ego within DIST of that actor
            (ex, ey), (ox, oy) = c.vehicle.getPosition(EGO), c.vehicle.getPosition(when["near"])
            if math.hypot(ex - ox, ey - oy) <= float(when.get("dist", 50.0)):
                return True
        pa = a["place"]
        if "gap" in when and a["id"] in c.vehicle.getIDList():
            d = self._dist(c, c.vehicle.getRoadID(a["id"]), max(0.0, c.vehicle.getLanePosition(a["id"]) - c.vehicle.getLength(a["id"])))
            if d is not None and 0.0 <= d <= when["gap"]:
                return True
        if when.get("beside") or "at" in when:
            if when.get("beside") and a["id"] in c.vehicle.getIDList():
                d = self._dist(c, c.vehicle.getRoadID(a["id"]), c.vehicle.getLanePosition(a["id"]))
            elif when.get("at") == "junction":
                j = self.pl["junction"]
                d = self._dist(c, j["edge"], j["pos"] - 0.1)
            else:
                d = None
            v = max(c.vehicle.getSpeed(EGO), 0.1)
            if d is not None and d >= 0.0 and (d <= when.get("dist", 0.0) or d / v <= when.get("tta", 0.0)):
                return True
        if "traveled" in when and a["id"] in c.vehicle.getIDList() and c.vehicle.getDistance(a["id"]) >= when["traveled"]:
            return True
        if "junction_ahead" in when and a["id"] in c.vehicle.getIDList():          # its lane's end is the next junction
            lane = c.vehicle.getLaneID(a["id"])
            if not lane.startswith(":"):                                   # to the next REAL junction: on over plain
                d = c.lane.getLength(lane) - c.vehicle.getLanePosition(a["id"])   # continuations (nina's §3)
                e = net_of(self.pl["town"]).getEdge(c.vehicle.getRoadID(a["id"]))
                for _ in range(20):
                    e = _plain_next(e)
                    if e is None or d > when["junction_ahead"]:
                        break
                    d += e.getLength()
                if d <= when["junction_ahead"]:
                    return True
        return False

    def _apply(self, c, t, a, steps):
        """A trigger's steps on actor A; a step TraCI refuses is recorded (fired: "failed …"), never the run's end."""
        for what, arg in steps:
            try:
                self._step(c, t, a, steps, what, arg)
            except Exception as e:  # noqa: BLE001 — traci.TraCIException; the run goes on and the report says it
                self.fired.append((round(t, 2), a["id"], "failed %s: %s" % (what, str(e)[:120])))

    def _step(self, c, t, a, steps, what, arg):
        vid, pa = a["id"], a["place"]
        if what in ("go", "speed"):
            self.going.add(vid)
        if what == "flow":                                                 # start the flow: its first car now
            self.flows[vid] = {"on": True, "n": 0, "last": None, "gap": None, "at": round(t, 2)}
            self._flow_car(c, a)
            self.fired.append((round(t, 2), vid, what))
            return
        if True:
            if what in ("go", "speed") and pa.get("spawn") and vid not in self.spawned:
                self.spawned.add(vid)                                      # added once: inserted at the next step
                rid = "r_" + vid
                c.route.add(rid, pa["route"])
                sp = float(dict(steps).get("speed", a.get("v", 0.0)) or 0.0)
                # inserted standing (SUMO refuses a fast insertion before a minor road's junction: "unpriorised junction
                # too close"), then at SP from its first step (setPreviousSpeed): the source's car spawned moving
                c.vehicle.add(vid, rid, typeID="actor_t", departLane=str(pa["lane"]), departPos=str(pa["pos"]), departSpeed="0")
                self.spawn_v[vid] = sp
            elif pa.get("spawn") and what in ("go", "speed"):
                return                                                     # spawned already, at that speed
            elif vid not in c.vehicle.getIDList():
                return
            elif what == "v":
                c.vehicle.setSpeed(vid, float(arg))
            elif what == "speed":
                c.vehicle.setSpeed(vid, float(arg))
            elif what == "brake":
                c.vehicle.setDecel(vid, float(arg))
                c.vehicle.setSpeed(vid, 0.0)
            elif what == "lane":
                c.vehicle.changeLane(vid, pa["lane"] + int(arg), CHANGE_S)
            elif what == "go":
                c.vehicle.setSpeed(vid, -1)
            self.fired.append((round(t, 2), vid, what))

    def tick(self, c, t):
        """Before a SUMO step at time T: hold the actors at their speeds once inserted, fire what is due."""
        ids = set(c.vehicle.getIDList())
        for vid in [v for v in self.spawn_v if v in ids and v not in self.started and v not in {a["id"] for a in self.pl["actors"]}]:
            self.started.add(vid)                      # a flow's car: at its speed from its first step
            c.vehicle.setPreviousSpeed(vid, self.spawn_v[vid])
            c.vehicle.setSpeed(vid, self.spawn_v[vid])
        for a in self.pl["actors"]:
            if a["id"] in ids and a["id"] not in self.started:
                self.started.add(a["id"])
                c.vehicle.setLaneChangeMode(a["id"], 0)                    # an actor goes where its script says only
                if a["id"] in self.spawn_v:                                # spawned by its trigger: at its step's speed
                    c.vehicle.setPreviousSpeed(a["id"], self.spawn_v[a["id"]])
                    c.vehicle.setSpeed(a["id"], self.spawn_v[a["id"]])
                elif a.get("script") or not a.get("moving", True) or float(a.get("v", 0.0)) == 0.0:
                    c.vehicle.setSpeed(a["id"], float(a.get("v", 0.0)))
                if a.get("breaks_rules"):
                    c.vehicle.setSpeedMode(a["id"], 0)
                elif a.get("kind") == "emergency":                         # lights on: through red lights and right of way,
                    c.vehicle.setSpeedMode(a["id"], 7)                     # still its safe gap to the car ahead (Town03 #49: its
                                                                           # walk back crosses a lit junction; it waited 50 s at red)
        if EGO not in ids:
            return
        ego_v = c.vehicle.getSpeed(EGO)
        d = c.vehicle.getDistance(EGO)
        lane = c.vehicle.getLaneID(EGO)
        if not lane.startswith(":") and self.pl.get("town"):       # LB's outside_route_lanes: off Driving and Parking lanes
            e = net_of(self.pl["town"]).getEdge(c.vehicle.getRoadID(EGO))   # (Town03's bidirectional centre lanes)
            if lane_type(e, c.vehicle.getLaneIndex(EGO)) not in ("driving", "parking"):
                self.outside_m += max(0.0, d - self.driven)
        self.driven = d
        self._yield_test(c, t, ids)
        self._end(c, t, ids, ego_v)
        self._sync(c, t, ids, ego_v)
        for a in self.pl["actors"]:                    # a flow: the next car once the last has driven its drawn gap
            f = self.flows.get(a["id"])
            if f and f["on"] and f["n"] < FLOW_MAX and (f["last"] not in ids or c.vehicle.getDistance(f["last"]) >= f["gap"]):
                self._flow_car(c, a)
        for a in self.pl["actors"]:                    # v_rel: the source's "the ego's speed + N" (the ego takes the town's limit)
            if "v_rel" in a and a["id"] in ids:
                c.vehicle.setSpeed(a["id"], min(c.vehicle.getMaxSpeed(a["id"]), ego_v + float(a["v_rel"])))
        for a in self.pl["actors"]:                    # yield_emergency_vehicle (LB 2.0): held behind the ego within 30 m
            if a.get("kind") == "emergency" and a["id"] in ids:
                lead = c.vehicle.getLeader(a["id"], 30.0)
                if lead and lead[0] == EGO and c.vehicle.getSpeed(a["id"]) < c.vehicle.getAllowedSpeed(a["id"]) * 0.9 \
                        and not self._at_red(c):
                    self.held[a["id"]] = round(self.held.get(a["id"], 0.0) + 0.1, 1)
        keep = []
        for a, when, steps, after in self.armed:
            if self._hit(c, t, a, when):
                j = self.pl["junction"]
                d = self._dist(c, j["edge"], j["pos"] - 0.1)
                kind, dt = self._target(c, a, when)
                self.triggered.append({"t": round(t, 2), "id": a["id"],
                                       "ego_tta": round(d / max(ego_v, 0.1), 2) if d is not None and d >= 0 else None,
                                       "target": kind, "target_m": None if dt is None else round(dt, 1),
                                       "target_tta": None if dt is None else round(dt / max(ego_v, 0.1), 2)})
                if after > 0:
                    self.queue.append((t + after, a, steps))
                else:
                    self._apply(c, t, a, steps)
            else:
                keep.append((a, when, steps, after))
        self.armed = keep
        due = [q for q in self.queue if q[0] <= t + 1e-9]
        self.queue = [q for q in self.queue if q[0] > t + 1e-9]
        for _, a, steps in due:
            self._apply(c, t, a, steps)


    @staticmethod
    def _at_red(c):
        """The ego stopped for a red or yellow light within 40 m: not a refusal to yield (its 600 m way passes lights)."""
        tls = c.vehicle.getNextTLS(EGO)
        return bool(tls) and tls[0][2] <= 40.0 and tls[0][3] in "rRyYu" and c.vehicle.getSpeed(EGO) < 1.0

    def _yield_test(self, c, t, ids):
        """LB 2.0's YieldToEmergencyVehicleTest (atomic_criteria.py:2110-2169, nina's 2b review): FAILURE while the ego is
        ahead of the vehicle along the vehicle's heading; the scenario ends 10 s after the vehicle first comes within
        50 m of the ego, or once the vehicle is in front and has driven 50 m (yield_to_emergency_vehicle.py:144-155);
        one infraction if FAILURE at the end (at the run's end when it never ends)."""
        ex, ey = c.vehicle.getPosition(EGO)
        for a in self.pl["actors"]:
            aid = a["id"]
            if a.get("kind") != "emergency" or aid not in ids:
                continue
            ax, ay = c.vehicle.getPosition(aid)
            h = math.radians(c.vehicle.getAngle(aid))                     # SUMO: degrees clockwise from north
            ahead = (ex - ax) * math.sin(h) + (ey - ay) * math.cos(h) > 0.0
            st = self.lb_ev.setdefault(aid, {"near": None, "pass_d": None, "end": None, "status": None})
            st["status"] = "FAILURE" if ahead else "SUCCESS"
            if st["end"] is not None:
                continue
            if st["near"] is None and math.hypot(ex - ax, ey - ay) <= 50.0:
                st["near"] = round(t, 2)
            dist = c.vehicle.getDistance(aid)
            st["pass_d"] = None if ahead else (dist if st["pass_d"] is None else st["pass_d"])
            if (st["near"] is not None and t - st["near"] >= 10.0) or (st["pass_d"] is not None and dist - st["pass_d"] >= 50.0):
                st["end"], st["failure"] = round(t, 2), ahead

    def _sync(self, c, t, ids, ego_v):
        """SyncArrival (CARLA's older red-light scenario; the architect's step 2c): once its trigger fired, a `sync`
        actor's speed is set each tick so that it reaches the conflict point (where the two straight ways across the
        junction cross) when the ego does at its present speed; from the ego's last SYNC_HOLD_S before the conflict
        (or the actor within 10 m of it) it holds that speed: the ego's braking then is its own."""
        for a in self.pl["actors"]:
            vid, cf = a["id"], a["place"].get("conflict")
            if not a.get("sync") or not cf or vid not in ids or vid not in self.going:
                continue
            st = self.sync.setdefault(vid, {"phase": "sync", "v": None, "t_hold": None, "closest_m": None})
            (ex, ey), (ax, ay) = c.vehicle.getPosition(EGO), c.vehicle.getPosition(vid)
            gap = math.hypot(ex - ax, ey - ay)
            st["closest_m"] = round(gap, 1) if st["closest_m"] is None else round(min(st["closest_m"], gap), 1)
            if st["phase"] != "sync":
                continue
            j = self.pl["junction"]
            ego_d = self._dist(c, j["edge"], j["pos"] - 0.1)
            try:
                adv_d = c.vehicle.getDrivingDistance(vid, cf["frm"], cf["frm_len"] - 0.1)
            except Exception:                                              # noqa: BLE001 — past its approach
                adv_d = None
            if ego_d is None or adv_d is None or ego_d < -1e6 or adv_d < -1e6:
                st["phase"], st["t_hold"] = "hold", round(t, 2)
                continue
            ego_d, adv_d = ego_d + cf["ego_in"], adv_d + cf["adv_in"]
            tt = ego_d / max(ego_v, 0.5)
            st["v"] = round(min(SYNC_VMAX, max(0.0, adv_d / tt)), 2)
            c.vehicle.setSpeed(vid, st["v"])
            if tt <= SYNC_HOLD_S or adv_d <= 10.0:
                st["phase"], st["t_hold"] = "hold", round(t, 2)

    def _flow_car(self, c, a):
        """One car of A's flow at its source; the gap to the next drawn from its `flow.gap` [from, to] (the source's
        `frequency`, OppositeActorFlow atomic_behaviors.py:3541-3701: continuous, not a fixed platoon)."""
        f, pa = self.flows[a["id"]], a["place"]
        rid = "r_" + a["id"]
        if f["n"] == 0:
            c.route.add(rid, pa["route"])
        vid = "%s_%d" % (a["id"], f["n"])
        c.vehicle.add(vid, rid, typeID="actor_t", departLane=str(pa["lane"]), departPos=str(pa["pos"]), departSpeed="0")
        c.vehicle.setLaneChangeMode(vid, 0)
        self.spawn_v[vid] = float(a.get("v", 0.0))
        lo, hi = (a["flow"].get("gap") or [20.0, 100.0])
        f["n"], f["last"], f["gap"] = f["n"] + 1, vid, round(self.rng.uniform(float(lo), float(hi)), 1)

    def _end(self, c, t, ids, ego_v):
        """The card's `end: {near: ID, within: m, stand_s: s}`: the source's end (FollowLeadingVehicle L137-143: the ego
        within 20 m of the lead, standing for 1 s), after which CARLA destroys the actor: removed here too."""
        e = self.card.get("end")
        if not e or self.ended is not None or e["near"] not in ids:
            return
        (ex, ey), (ox, oy) = c.vehicle.getPosition(EGO), c.vehicle.getPosition(e["near"])
        near = math.hypot(ex - ox, ey - oy) <= float(e.get("within", 20.0))
        self.stood = self.stood + 0.1 if near and ego_v < 0.1 else 0.0
        if self.stood >= float(e.get("stand_s", 1.0)) - 1e-9:
            c.vehicle.remove(e["near"])
            self.ended = round(t, 2)

    def on_collision(self, c, other, t):
        """The ego's contact with OTHER: the other removed (CARLA's bodies part; SUMO's `collision.action warn` keeps them
        overlapped, StaticCutIn #135's 1137 contact ticks). The row says "removed at contact": the road ahead is then
        freer than CARLA's, so the first event is the score and a later hold on that row is not evidence."""
        if other != EGO and other in c.vehicle.getIDList():
            c.vehicle.remove(other)
            self.removed.append((round(t, 2), other))

    def report(self):
        """What the run's table reads: the steps fired and the triggers (with the ego's TTA to the junction at firing),
        the ones never fired, the route completion, LB 2.0's emergency test and our held seconds, the removals."""
        lb = {aid: dict(st, failure=st.get("failure") if st["end"] is not None else st["status"] == "FAILURE")
              for aid, st in self.lb_ev.items()}
        for a in self.pl["actors"]:                                        # never in the run (nor near): FAILURE at the end
            if a.get("kind") == "emergency" and a["id"] not in lb:
                lb[a["id"]] = {"near": None, "end": None, "status": None, "failure": True}
        length = max(1.0, self.pl["ego"].get("len", 1.0))
        return {"fired": self.fired, "triggered": self.triggered,
                "unfired": sorted({a["id"] for a, *_ in self.armed} | {a["id"] for _, a, _ in self.queue}),
                "rc": round(min(100.0, 100.0 * self.driven / length), 1), "outside_m": round(self.outside_m, 1),
                "outside_pct": round(100.0 * self.outside_m / self.driven, 2) if self.driven > 0 else 0.0, "driven_m": round(self.driven, 1), "route_m": length,
                "emergency_lb": lb, "emergency_held_s": self.held, "removed": self.removed, "ended": self.ended,
                "sync": self.sync, "flows": {k: {"cars": f["n"], "at": f["at"]} for k, f in self.flows.items()}, "conflict": {a["id"]: a["place"]["conflict"] for a in self.pl["actors"]
                                                if a["place"].get("conflict")},
                "site": self.pl["site"], "free": self.pl["free"], "shift": self.pl["shift"], "town": self.pl.get("town")}
