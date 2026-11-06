"""road_facts — the road domains' world facts over roles (road-world s-e812715d step 2): the one projection every road
host makes (the exerciser's road_host, the SUMO host), truth-free: from the LaneMap, the ego's Mover and speed, the
movers it knows of, and the situation layer (whose memory the host keeps across ticks).

    facts(lm, ego, v, movers, sit, changing=None, dest=None, turn=None, lights=None, speeds=None)
        -> (facts {atom: 1}, roles {role: mover id}, fold, states)

The binding: LaneMap.roles (semantic_world.lane: lead, follower, leadleft, followleft, leadright, followright,
a1..a3, vru1). The facts (every number stays here; the rules read classes):
- the situation layer, Situation.facts(detail=True), for every bound role: type(o, K), safe_long(o), safe_lat(o),
  dangerous(o), safe_before(o, B), resp(o, R), safe_lat_left/right(o), resp_side(o, side, R) (the library's
  resp_lat(o, side, R): renamed, a pred has one arity), xing_case(o, C),
  xing_before(o, C); and the fold's resp_lon(R), resp_lat(R), resp_lat_left(R), resp_lat_right(R);
- a role nobody fills: role_empty(o) and nothing else (spec 20 §2, surprise-kinds s-7a02c2ac: no class and no safety fact
  where the host saw nobody; not_relevant is a SEEN mover's class); side_clear(D) when the D side is free to change into:
  adjacent(D), and its lead and follower each unfilled or safe_long and safe_lat by the fold;
- the other cars, as observed (road-2 item 2; a mover's `signal` / `settled`, sumo_perceive): signalled(R, S) while
  the role's indicator shows side S, settled_to(R, D) for a while after its lane change to side D is seen complete;
  a pair whose other has settled into a lane not the ego's is left out of the fold (released);
- the lanes: adjacent(D) for a same-direction neighbour on side D; own_kind(K) of the ego's lane and lane_kind(D, K) of each
  side every tick (K driving | parking | bidirectional, none: no same-direction lane there); changing(D) while a lane change to D runs;
  settled(D) when no change runs and the ego did not leave side D within SETTLE_S (LEFT_FROM: the world's (side, age
  s) of its last change): an observed fact of its own manoeuvre, never a belief (road step 5: the planner's change
  ping-pong between two lanes whose leads both read slow);
- progress: below_target (the ego under what it wants by more than 0.5 m/s), above_target (over it by more than PACE_BAND), else at_target:
  what it wants is min(pace, the limit in law; law_limit: inside a junction, the limit it came in on); change_reason(D): a person's wish only (road_wishes); lead_slow (the
  lead within SLOW_RANGE ahead, slower than the ego's limit by more than SLOW_MARGIN, and the ego not slower than it
  by more than SLOW_MARGIN: nothing to gain behind it), else lead_ok (accel_ok then brings the ego up to it); accel_ok when
  two plans (2 PLAN_T) of full acceleration keep the lead at a safe distance (gap_room), else accel_no; keep_ok when
  two plans at the speed it has do, else keep_no; at_dest;
- sight, by duty (SIGHT: the sensor's, a host with no sensor says seen_ahead and no road class): seen_ahead (its own way, to its stopping reach) else unseen_ahead;
  road_in_view(nextzone) else road_hidden(nextzone), where the zone's priority is not the ego's and no red or amber governs (the crossing lanes back APPROACH);
  stop_sign(nextzone): the next link's state is SUMO's 's'; there inch_room waits for one standing tick at the line (STOOD: the host's);
  with road_hidden, inch_room(nextzone) (at a walk, room behind any lead, short of the crossing lane by more than min_dist + INCH_MARGIN) else inch_no(nextzone);
- signal(nextzone, L): the light on the next junction link of the way (signal_of), off with none or inside a junction; can_halt(nextzone):
  its line is within the hardest braking;
- the next zone on the ego's route (role nextzone), or the next junction itself when its link has none (class by the line): zone_at(nextzone, C) with C far | near | at | in (the ego's
  front at d_enter: beyond its reach far — its stated braking distance + NEAR_MARGIN, at least NEAR_RANGE — within it
  near, ≤ AT_RANGE at, inside in), and zone_at(nextzone, none) when no zone is ahead; zprio(nextzone, P) ego | obj |
  same (the zone's priority lane: the ego's, another's, none); can_stop(nextzone) (the ego's stated braking
  distance at brake_min, after its response time, ≤ d_enter: RSS's zone-entry rule), else late(nextzone); zfree(nextzone) when no mover
  at all is inside (every mover, not the bound ones only), and holder(nextzone, O) for zone_roles' holder; zclear(nextzone) when it is free and no
  mover on another of its lanes is within APPROACH of it, else zbusy(nextzone); cross_unsettled(nextzone) while a car on a
  crossing lane, near the zone or in it, still moves, else cross_settled(nextzone) (RSS rule 5 form B: the planner's accel
  waits; also with no zone ahead, and at a merge); cross_overlap(nextzone) in place of cross_unsettled when, on the ego's
  priority, that car's time at the zone is within a response time of the ego's and another plan at this speed would lose
  the ability to stop short (the planner's soft brake keeps it); conflict(nextzone) for crossing axes (a zone with a
  priority), share(nextzone) for a merge's (none); turn(nextzone) at a merge when the last to enter came from
  another lane (the zipper's alternation, TURN: the host's {zone: the lane of the last entrant}) and no mover on
  another of its lanes reaches the line first, else wait_turn(nextzone) (road step 5, yield_merge: the alternation
  alone gave the ego the turn while the ramp's car arrived first, and the responder braked for its cut-in);
- the walker: crossing(vru1, on) while it is on a crosswalk lane that crosses the ego's route ahead, near when
  it waits within NEAR_WALK of it;
- the beat: now (one a tick; the command rules consume it)."""
from dataclasses import replace

from semantic_world.situation import Situation, safe_same_dir, stated, stop
from restrict import INCH_MS

OBJ_ROLES = ("lead", "follower", "leadleft", "followleft", "leadright", "followright", "a1", "a2", "a3", "vru1")
NEAR_RANGE, AT_RANGE, APPROACH, NEAR_MARGIN = 30.0, 3.0, 40.0, 10.0
INCH_MARGIN = 1.5   # m kept to the crossing lane beyond min_dist: a planner second's step at INCH_MS stays inside it
SLOW_RANGE, SLOW_MARGIN, NEAR_WALK = 60.0, 2.0, 1.0
PACE_BAND = 3.5     # over a pace's target before the planner brakes: one planner period's accel or soft brake stays inside it, m/s
STILL = 0.1                       # m/s: a car at or under this stands
PLAN_T = 1.0                      # the planner's period (s): accel_ok looks one plan ahead
# the gap records' projection (road-scenarios s-e23be780 step 3, steps/road-gap-vocabulary-architect.md; the numbers are nina's,
# named for the architect's word): a standing obstacle, the oncoming lane's verdict for a pass, an emergency vehicle
STAND_V = 0.5                     # m/s: a lead at or under this stands (lead_standing; STILL is a car at rest)
QUEUE_GAP = 10.0                  # m: a standing lead with another car standing this close ahead of it is a queue, not an obstacle
WAIT_M = 25.0                     # m: a lead standing this close to its lane's end may wait at the junction or its light
RETURN_T = 2.0                    # s: the room to come back in front of the obstacle, at the pass speed (RETURN_M = RETURN_T · v_pass)
REACH = 100.0                     # m: the ego's sensor range (the run's sensor.range): an oncoming lane seen less far than the pass needs is busy
EMERGENCY = ("emergency",)        # the vClasses of an emergency vehicle with its lights on (SUMO's vClass; the cards' kind)


def inside(z, m):
    """M is inside zone Z: [s − length, s] overlaps the zone's span on its lane (the library's rule)."""
    if m.lane not in z.lanes:
        return False
    a, b = z.lanes[m.lane]
    return m.s >= a and m.s - m.length <= b


def windows_overlap(z, m, mv, front, d_out, v, margin):
    """Mover M, at speed MV, and the ego, at V with FRONT and D_OUT to the zone's entry and exit, are at zone Z within
    MARGIN seconds of each other: each one's time there, at the speed it has."""
    a, b = z.lanes[m.lane]
    m_in, m_out = max(0.0, a - m.s) / max(mv, 0.1), max(0.0, b + m.length - m.s) / max(mv, 0.1)
    e_in, e_out = max(0.0, front) / max(v, 0.1), max(0.0, d_out) / max(v, 0.1)
    return e_in - margin <= m_out and m_in - margin <= e_out


def keeps_stop_short(front, v, d):
    """Another plan at this speed, then easing off at the planner's own brake, would no longer stop the ego short of a zone
    FRONT away, and it can still stop short at brake_min (situation.ego_stops_short's distance): the time to ease off.
    Past that distance: clear the zone."""
    return stop(v, d.brake_min) + d.min_dist < front <= stop(v, d.brake_min_correct) + d.min_dist + v * PLAN_T


def gap_room(pairs, ego, v, cap, accel, t=2 * PLAN_T):
    """The ego may hold ACCEL for T and stay at a safe distance behind its lead (RSS rule 1): the gap after T still above
    Lemma 2's safe distance at the speed it reaches. T is two plans: the planner acts once a period, and its next decision
    takes a period to act. To keep its speed, the lead holds its own. To speed up, the lead may brake its hardest: an
    accel is held for a period the responder cannot shorten, so it must not turn the pair dangerous whatever the lead
    does (RSS's blame; lead_brake seed 1). No lead: room."""
    lead = next((p for p in pairs if p.role == "lead" and p.type == "same_dir" and p.lon == "in_front"), None)
    if lead is None:
        return True
    v1 = max(0.0, min(cap, v + accel * t))
    tc = t if accel == 0 or v1 in (cap, 0.0) and accel == 0 else min(t, abs((v1 - v) / accel)) if accel else t
    run = 0.5 * (v + v1) * tc + v1 * (t - tc)
    if accel <= 0 or not lead.obj.brake_max:
        gap1 = lead.d_lon + lead.obj.vmin * t - run
        return gap1 > safe_same_dir(replace(ego.dyn, vmin=v1, vmax=v1), lead.obj)
    lv = max(0.0, lead.obj.vmin - lead.obj.brake_max * t)         # the lead braking its hardest over T
    ran = (lead.obj.vmin * lead.obj.vmin - lv * lv) / (2.0 * lead.obj.brake_max)
    gap1 = lead.d_lon + ran - run
    return gap1 > safe_same_dir(replace(ego.dyn, vmin=v1, vmax=v1), replace(lead.obj, vmin=lv, vmax=lv))


SETTLE_S = 10.0                 # s: the side the ego left is not settled again before this
ROUTE_REACH = 150.0             # m: route_lane(D) is stated this far before the ego's lane ends (early enough to change while the zone is far)


def route_side(lm, ego):
    """route_lane(D) (ec8088, the architect's vocabulary): the ego's lane does not continue along its route (no way out of it reaches
    the route's next edge) within ROUTE_REACH of its end, and a same-direction lane toward D does (the first such, right before left).
    Never inside a junction, never on the route's last edge, never with no route's edges (the exerciser: `ego.route_edges` unset).
    → "left" | "right" | None."""
    edges = getattr(ego, "route_edges", None)
    lane = lm.lanes.get(ego.lane)
    if not edges or lane is None or lane.internal or lane.edge not in edges:
        return None
    i = edges.index(lane.edge)
    if i + 1 >= len(edges) or lane.length - ego.s > ROUTE_REACH:
        return None
    nxt = edges[i + 1]

    def on(l):
        return any(lm.lanes[w[-1]].edge == nxt for w in lm.ways(l.id))
    if on(lane):
        return None
    return toward(lm, lane, on)


def toward(lm, lane, good):
    """The first side (right before left) whose same-direction lanes, walked outward from LANE, reach one GOOD has. → side or None."""
    for side in ("right", "left"):
        cur = lane
        while getattr(cur, side) and not getattr(cur, side + "_opposite", False):
            cur = lm.lanes[getattr(cur, side)]
            if good(cur):
                return side
    return None


def goal_side(lm, ego):
    """route_lane(D) toward the goal's lane (a CommonRoad planning problem's goal region on one lane of a multi-lane road: the
    ego.goal_lanes the cr world gives): on the goal's edge, the ego's lane not one of them, the side whose lanes reach one.
    Never inside a junction. → side or None (no goal lanes: the cards, the exerciser)."""
    goals = set(getattr(ego, "goal_lanes", None) or ())
    lane = lm.lanes.get(ego.lane)
    if not goals or lane is None or lane.internal or ego.lane in goals:
        return None
    if not any(lm.lanes[g].edge == lane.edge for g in goals if g in lm.lanes):
        return None
    return toward(lm, lane, lambda l: l.id in goals)


LIGHTS = {"G": "green", "g": "green_yield", "y": "amber", "Y": "amber", "r": "red", "u": "red", "s": "red"}


def signal_of(link, lights):
    """The light on LINK (a Connection) by the world's phase states LIGHTS: green, green_yield, amber, red, or off with none. Truth, not
    sensed: the lights have no occlusion and no range here. Red and amber together, and red with a turn allowed, count as red."""
    if link is None or link.tl is None or link.tl_link is None or not lights or link.tl not in lights:
        return "off"
    st = lights[link.tl]
    return LIGHTS.get(st[link.tl_link], "off") if link.tl_link < len(st) else "off"


def law_limit(lm, lane):
    """The limit in law at LANE. An internal lane's speed is netconvert's, from the turn's geometry, and no limit: inside a junction it is the
    limit of the lane the ego came in on (where the map says none came in, the lane it comes out on)."""
    for step in (lambda l: [o.id for o in lm.lanes.values() if l.id in o.succ], lambda l: l.succ):
        cur = lm.lanes[lane]
        for _ in range(8):                      # an internal chain's few lanes
            if not cur.internal:
                return lm.vcap(cur.id)
            ways = step(cur)
            if not ways:
                break
            cur = lm.lanes[ways[0]]
    return lm.vcap(lane)


def seen_ahead(lm, route, s0, sight, reach, bin_m=5.0):
    """Sight along the ego's OWN way: from s0 on ROUTE's lanes to REACH, every cell could be seen, up to the first one a car is seen on. SIGHT {cells, seen}. Beyond the sensor's
    range a cell cannot be seen, so range and occlusion are one test. Never another lane's: the side road's visibility is not the holder's duty."""
    left, s = reach, s0
    for lane in route:
        length = lm.lanes[lane].length
        k = int(max(0.0, s) // bin_m)
        while k * bin_m < length and left > 0:
            c = "%s|%d" % (lane, k)
            if c in sight["seen"]:
                return True
            if c not in sight["cells"] and (k + 1) * bin_m <= length:     # a stub at a lane's end has no cell of its own
                return False
            left -= (k + 1) * bin_m - max(s, k * bin_m)
            k += 1
        if left <= 0:
            return True
        s = 0.0
    return True


def road_in_view(lm, z, own, sight, reach, bin_m=5.0):
    """The yielder's view (StVO 8(2)): the zone Z's crossing lanes but OWN, from the zone back along each way in to REACH: every cell could be seen, up to the first one a car is seen on."""
    for lane, (a, _) in z.lanes.items():
        if lane == own:
            continue
        cur, s, left = lane, a, reach
        while left > 0:
            k = int(max(0.0, s) // bin_m)
            while k >= 0 and left > 0:
                c = "%s|%d" % (cur, k)
                if c in sight["seen"]:
                    left = 0
                    break
                if c not in sight["cells"]:
                    return False
                left -= bin_m
                k -= 1
            if left <= 0:
                break
            came = [o.id for o in lm.lanes.values() if cur in o.succ]
            if not came:
                break
            cur, s = came[0], lm.lanes[came[0]].length
    return True


def stood_at_sign(stood, zone, sign, line, v):
    """A stop sign asks one standing tick at its line before a step forward; up to the line a walk is free, and on any other link there is nothing to wait for. STOOD: the host's set of
    the zones stood at (None: nothing can stand, so nothing goes on)."""
    if not sign or line > AT_RANGE or (stood is not None and zone in stood):
        return True
    if stood is not None and v <= STILL:
        stood.add(zone)
    return False


def fold_of(states, movers, ego):
    """The fold: a dangerous pair whose other has settled into a lane not the ego's is released from it; a crossing never is: only geometry
    releases that one, or both standing (situation.respond_standing)."""
    released = {m.id for m in movers if getattr(m, "settled", None) and m.lane != ego.lane}
    return Situation.fold([s for s in states if s.type.startswith("xing") or s.id.split(":")[0] not in released], ego.dyn)


def oncoming_home(lm, ego):
    """When the ego drives on the opposite direction's lane beside its route (a pass through the oncoming lane), the route
    lane it came from, else None: a route lane whose opposite neighbour is the ego's lane."""
    for rid in ego.route or ():
        rl = lm.lanes.get(rid)
        if rl is None or rid == ego.lane:
            continue
        for side in ("left", "right"):
            if getattr(rl, side) == ego.lane and getattr(rl, side + "_opposite"):
                return rid
    return None


HEADED = "~"                                   # the frame lane's id: the opposite lane, run the ego's way


def heading_frame(lm, ego, movers, home, sight=None):
    """The ego passing on the opposite lane beside its route lane HOME, in its own heading: (lane map, ego, movers, sight) where the
    opposite lane is a lane HEADED+id of the ego's direction, of kind `oncoming`, with HOME its same-direction right neighbour, so
    the projection's own machinery reads the pass: own_kind(oncoming), adjacent(right) and lane_kind(right, K) of the route lane,
    side_clear(right) by its lead and follower (the parked car behind, standing: safe once passed), lane_kind(left, none), and an
    oncoming car on that lane a head-on pair (opp_dir, `against`) on the ego's way. A place on the opposite lane runs the other
    way: s on the frame is HOME's length minus it (the front of an oncoming car is its near end)."""
    import copy
    opp, hl = lm.lanes[ego.lane], lm.lanes[home]
    vid = HEADED + opp.id
    frame = copy.copy(lm)
    frame.lanes = dict(lm.lanes)
    frame.lanes[vid] = replace(opp, id=vid, length=hl.length, succ=list(hl.succ), left=None, left_opposite=False, right=home,
                               right_opposite=False, speed=opp.speed or hl.speed, shape=None, kind="oncoming")
    if lm.net is not None:                         # the junction ahead: its link from HOME is the frame lane's
        if getattr(lm, "_links", None) is None:
            lm.next_link([], 0.0)
        links = getattr(lm, "_links", None) or {}
        frame._links = {**links, **{(vid, via): c for (f, via), c in links.items() if f == home}}
    route = list(ego.route or [])
    after = route[route.index(home) + 1:] if home in route else []
    flip = lambda s: hl.length - s
    ego2 = replace(ego, lane=vid, s=flip(ego.s), route=[vid] + after)
    movers2 = [replace(m, lane=vid, s=flip(m.s), against=not m.against) if m.lane == opp.id else m for m in movers]
    if sight is not None:
        def cells(cs):
            out = set(cs)
            for c in cs:
                lane, _, k = c.rpartition("|")
                if lane == opp.id:
                    out.add("%s|%d" % (vid, max(0, int(flip((int(k) + 0.5) * 5.0) // 5.0))))
            return out
        sight = dict(sight, cells=cells(sight.get("cells", ())), seen=cells(sight.get("seen", ())))
    return frame, ego2, movers2, sight


def lead_standing(lm, lead, movers, speeds=None):
    """The lead stands (at or under STAND_V) and is no queue: no car stands within QUEUE_GAP ahead of it on its lane, and it is
    more than WAIT_M from its lane's end (a car waiting at the junction or its light is not an obstacle to pass)."""
    v = (speeds or {}).get(lead.id, lead.dyn.vmax or 0.0)
    if v > STAND_V:
        return False
    if lm.lanes[lead.lane].length - lead.s <= WAIT_M:
        return False
    return not any(m.id != lead.id and m.lane == lead.lane and 0.0 <= m.s - lead.s <= QUEUE_GAP + m.length
                   and (speeds or {}).get(m.id, m.dyn.vmax or 0.0) <= STAND_V for m in movers)


STAND_S = 1.0                     # s: a lead stands this long before it is lead_standing (the host's STANDING; Flensburg-10_1's one tick)


def pass_blocked(lm, ego, v, cap, roles, by_id, movers, speeds=None, sight_m=REACH):
    """In the ego's heading frame on the oncoming lane (side_busy(right): not past the car): the pass cannot complete when the
    car being passed (leadright, on the route lane ahead) no longer stands, or an oncoming car on the ego's lane ahead leaves no
    room for the rest of the pass (the oncoming_clear arithmetic over what is left: the gap to the car's front + the ego's length +
    RETURN_T at the limit)."""
    lr = by_id.get(roles.get("leadright"))
    if lr is not None and (speeds or {}).get(lr.id, lr.dyn.vmax or 0.0) > STAND_V:
        return True                                                      # it drives on: no pass to finish
    rest = (max(0.0, lr.s - ego.s) if lr is not None else 0.0) + ego.length + RETURN_T * cap
    T = pass_time(rest, v, cap, ego.dyn.accel or 1.0)
    rho = ego.dyn.rho or 0.0
    v_mean = (v + cap) / 2.0
    for m in movers:
        if m.lane != ego.lane or m.id == ego.id or not m.against:
            continue
        rel = m.s - ego.s                                                # the frame lane runs the ego's way
        if rel < 0 or rel > sight_m:
            continue
        vo = (speeds or {}).get(m.id, m.dyn.vmax or 0.0)
        if rel < (v_mean + vo) * (T + rho) + (ego.dyn.min_dist or 0.0):
            return True                                                  # the oncoming lane ahead turned busy
    return False


def pass_time(d, v, cap, accel):
    """The time to drive D metres from V under ACCEL to CAP (then at CAP)."""
    v, cap, accel = max(0.0, v), max(cap, 0.1), max(accel, 0.1)
    if v >= cap:
        return d / cap
    d_acc = (cap * cap - v * v) / (2.0 * accel)
    if d <= d_acc:
        return (-v + (v * v + 2.0 * accel * d) ** 0.5) / accel
    return (cap - v) / accel + (d - d_acc) / cap


def oncoming_clear(lm, ego, v, cap, lead, onc, movers, speeds=None, sight_m=REACH):
    """The oncoming lane ONC free for the WHOLE pass of the standing LEAD (the architect's arithmetic): the pass L = the gap to
    the lead + its length + the ego's + RETURN_M (RETURN_T at the pass speed, the lane's limit); its time T from the ego's speed
    under its accel to the limit; every mover on ONC ahead (closing) within SIGHT_M keeps (v_mean + v_onc)·(T + rho) + min_dist;
    and the lane is seen far enough: the oncoming lane's limit · (T + rho) within SIGHT_M, the file's view test (the clear-view
    duty is the overtaker's: unseen is busy)."""
    d_lead = lm.ahead(ego.route or [ego.lane], ego.s, lead.lane, lead.s)
    if d_lead is None:
        return False
    ret = RETURN_T * cap
    L = max(0.0, d_lead - lead.length) + lead.length + ego.length + ret
    T = pass_time(L, v, cap, ego.dyn.accel or 1.0)
    rho = ego.dyn.rho or 0.0
    lo = lm.lanes[onc]
    v_onc_cap = lo.speed or cap
    if v_onc_cap * (T + rho) > sight_m:
        return False                                                     # not seen far enough for the pass: busy
    v_mean = (v + cap) / 2.0
    for m in movers:
        if m.lane != onc or m.id == ego.id:
            continue
        rel = (lo.length - m.s) - ego.s                                  # its s runs the other way (Lanemap.pairs)
        if rel < 0 or rel > sight_m:
            continue                                                     # behind the ego, or beyond its sight
        vo = (speeds or {}).get(m.id, m.dyn.vmax or 0.0)
        if rel - m.length < (v_mean + vo) * (T + rho) + (ego.dyn.min_dist or 0.0):
            return False
    return True


def facts(lm, ego, v, movers, sit, changing=None, dest=None, turn=None, lights=None, speeds=None, left_from=None, pace=None, sight=None, stood=None,
          standing=None):
    """SPEEDS {mover id: v}: the movers' speeds (the lead's for lead_slow). LEFT_FROM (side, age s): the side the
    ego's last lane change left, and how long ago. PACE: a target speed under the limit; above it by PACE_BAND the ego is above_target (the
    planner's soft brake)."""
    ego.route = ego.route or [ego.lane]
    home = oncoming_home(lm, ego)
    if home is not None:                       # passing on the oncoming lane: the projection in the ego's heading (heading_frame)
        lm, ego, movers, sight = heading_frame(lm, ego, movers, home, sight)
    roles = lm.roles(ego, movers, lights=lights)
    role_of = {m: r for r, m in roles.items()}
    pairs = lm.pairs(ego, movers, role_of=lambda o: role_of.get(o.id), lights=lights)
    # a car seen settled INTO the ego's lane: its pair's memory ("laterally safe before", from the lane it came from)
    # no longer says what the pair is; Def 10 decides it afresh (along the way) while settled_to holds (road-2 item 2)
    for m in movers:
        if getattr(m, "settled", None) and m.lane == ego.lane:
            for p in pairs:
                if p.id.split(":")[0] == m.id:
                    sit.memory.pop(p.id, None)
    states = sit.check(pairs)
    # road-2 item 2: what the other cars SHOW (sumo_perceive: a mover's signal and settled), world facts, never an
    # intent belief: fold_of
    fold = fold_of(states, movers, ego)
    out = {}
    for a, n in Situation.facts(states, fold, detail=True).items():
        if a.startswith("resp_lat(") and a.count(",") == 2:        # the pair's lateral response: its own name (a
            a = "resp_side(" + a[len("resp_lat("):]               # pred has one arity; resp_lat(R) is the fold's)
        out[a] = n
    if "resp_unst" not in fold:                                     # the responder's drive away ends on it (away_done)
        out["resp_unst(none)"] = 1
    bound = set(roles)
    for r in OBJ_ROLES:
        if r not in bound:
            out["role_empty(%s)" % r] = 1                          # nobody the host saw there: no filler (spec 20 §2)
    by_id = {m.id: m for m in movers}
    for r, mid in roles.items():
        m = by_id.get(mid)
        if m is not None and getattr(m, "signal", None):
            out["signalled(%s,%s)" % (r, m.signal)] = 1          # its indicator, this tick
        if m is not None and getattr(m, "settled", None):
            out["settled_to(%s,%s)" % (r, m.settled)] = 1        # its lane change, seen complete
    lane = lm.lanes[ego.lane]
    for r, mid in roles.items():                                     # an emergency vehicle, lights on: a class, never a belief (13b2f9)
        m = by_id.get(mid)
        if m is not None and getattr(m, "vclass", None) in EMERGENCY:
            out["emergency(%s)" % r] = 1
    out["own_kind(%s)" % getattr(lane, "kind", "driving")] = 1          # the lanes' kinds, vocabulary (change.llp decides); on
    for side in ("left", "right"):                                      # the oncoming lane in its heading frame: oncoming
        if getattr(lane, side) and not getattr(lane, side + "_opposite"):
            out["adjacent(%s)" % side] = 1
            out["lane_kind(%s,%s)" % (side, getattr(lm.lanes[getattr(lane, side)], "kind", "driving"))] = 1
            fr = roles.get("follow" + side)
            ev = fr is not None and getattr(by_id.get(fr), "vclass", None) in EMERGENCY and \
                (speeds or {}).get(fr, by_id[fr].dyn.vmax or 0.0) > v                  # an emergency vehicle closing behind on that side
            if not ev and all(r not in bound or ("safe_long(%s)" % r in out and "safe_lat(%s)" % r in out)
                              for r in ("lead" + side, "follow" + side)):
                out["side_clear(%s)" % side] = 1                    # free to change into: each role unfilled or safe
            else:
                out["side_busy(%s)" % side] = 1                     # its complement: never move into an emergency vehicle's path
        else:
            out["lane_kind(%s,none)" % side] = 1                         # no same-direction lane there
            if getattr(lane, side) and getattr(lane, side + "_opposite"):
                out["oncoming(%s)" % side] = 1                           # the opposite direction's driving lane (668e45)
    rs = (route_side(lm, ego) or goal_side(lm, ego)) if home is None else None    # a lane cut off from the route first, then the goal's lane
    if rs is not None:
        out["route_lane(%s)" % rs] = 1                               # my lane leaves my route; the D lane carries it on (change_route)
    if changing:
        out["changing(%s)" % changing] = 1
    else:
        for side in ("left", "right"):
            if not (left_from and left_from[0] == side and left_from[1] < SETTLE_S):
                out["settled(%s)" % side] = 1
    cap = law_limit(lm, ego.lane) if pace is None else min(pace, law_limit(lm, ego.lane))
    out["below_target" if v < cap - 0.5 else "above_target" if v > cap + PACE_BAND else "at_target"] = 1
    by_id = {m.id: m for m in movers}
    if "lead" in roles:
        lead = by_id[roles["lead"]]
        d = lm.ahead(ego.route, ego.s, lead.lane, lead.s)
        lv = (speeds or {}).get(lead.id, lead.dyn.vmax)
        if d is not None and 0 <= d <= SLOW_RANGE and lv < cap - SLOW_MARGIN and v >= lv - SLOW_MARGIN:
            out["lead_slow"] = 1
    if "lead_slow" not in out:                     # the pass is change.llp's (change_pass, change_aside); change_reason is a wish's
        out["lead_ok"] = 1
    if "lead" in roles and "lead_slow" in out and lead_standing(lm, by_id[roles["lead"]], movers, speeds) and \
            (standing is None or standing.get(roles["lead"], 0.0) >= STAND_S):
        out["lead_standing"] = 1                   # a standing obstacle, not a queue (668e45), standing STAND_S (cr-harvest: no flicker)
    if home is not None and "side_busy(right)" in out and pass_blocked(lm, ego, v, cap, roles, by_id, movers, speeds):
        out["pass_blocked"] = 1                    # on the oncoming lane, the pass cannot complete (brake_pass_blocked)
    for side in ("left", "right"):
        if "oncoming(%s)" % side in out:
            ok = "lead" in roles and oncoming_clear(lm, ego, v, cap, by_id[roles["lead"]], getattr(lane, side), movers, speeds, sight_m=REACH)
            out["oncoming_%s(%s)" % ("clear" if ok else "busy", side)] = 1
    out["accel_ok" if gap_room(pairs, ego, v, cap, ego.dyn.accel) else "accel_no"] = 1
    out["keep_ok" if gap_room(pairs, ego, v, cap, 0.0) else "keep_no"] = 1
    if dest is not None and ego.s >= dest:
        out["at_dest"] = 1
    zr = lm.zone_roles(ego, movers, roles)                      # the zone binding: the library's, never by hand
    near = lm.nearest_zone(ego.route, ego.s, length=ego.length) if zr["nextzone"] else None
    link = None if lm.lanes[ego.lane].internal else lm.next_link(ego.route, ego.s)   # inside a junction no line is ahead
    sign = link is not None and link[0].state == "s"
    if sign:
        out["stop_sign(nextzone)"] = 1
    elif stood and link is not None:
        stood.clear()                   # a junction with no sign behind it: the next sign asks again
    light = signal_of(link[0] if link else None, lights)
    out["signal(nextzone,%s)" % light] = 1
    d = ego.dyn
    out["seen_ahead" if sight is None or seen_ahead(lm, ego.route, ego.s, sight, stated(v, 0.0, d.rho, d.brake_min)) else "unseen_ahead"] = 1
    reach = max(NEAR_RANGE, stated(v, 0.0, d.rho, d.brake_min) + NEAR_MARGIN)       # near: within its stopping reach
    if link is not None and stop(v, d.brake_max) + d.min_dist <= link[1]:
        out["can_halt(nextzone)"] = 1                                               # a red's test: only the brakes excuse it
    if link is not None and (near is None or near[0].id != zr["nextzone"] or near[1] not in link[0].chain):
        # the next junction's link has no zone: nextzone is the junction itself, its class by the line; nothing to yield to there
        out["zone_at(nextzone,%s)" % ("at" if link[1] <= AT_RANGE else "near" if link[1] <= reach else "far")] = 1
        out["can_stop(nextzone)" if stated(v, 0.0, d.rho, d.brake_min) <= max(0.0, link[1]) else "late(nextzone)"] = 1
        out["cross_settled(nextzone)"] = 1
    elif near is not None and near[0].id == zr["nextzone"]:
        z, rl, d_in, d_out = near
        front = d_in
        line = min(front, link[1]) if link is not None else front                   # the class and the stop by the line, where there is one
        cls = "in" if line <= 0 < d_out else "at" if line <= AT_RANGE else "near" if line <= reach else "far"
        out["zone_at(nextzone,%s)" % cls] = 1
        prio = lm.priority(z, lights)
        out["zprio(nextzone,%s)" % ("same" if prio is None else "ego" if prio == rl else "obj")] = 1
        if sight is not None and prio is not None and prio != rl and light in ("off", "green_yield"):      # a red or an amber is the light's duty: no step forward
            hidden = not road_in_view(lm, z, rl, sight, APPROACH)
            out["road_hidden(nextzone)" if hidden else "road_in_view(nextzone)"] = 1
            if hidden:                  # on at a walk to where it can see: room behind any lead, and never up to the crossing lane
                room = "accel_ok" in out and v <= INCH_MS + 0.2 and front > d.min_dist + INCH_MARGIN and stood_at_sign(stood, z.id, sign, line, v)
                out["inch_room(nextzone)" if room else "inch_no(nextzone)"] = 1
        out["can_stop(nextzone)" if stated(v, 0.0, d.rho, d.brake_min) <= max(0.0, line) else "late(nextzone)"] = 1
        occupants = [m for m in movers if inside(z, m)]
        if not occupants:
            out["zfree(nextzone)"] = 1
            approaching = False
            for m in movers:
                if m.lane in z.lanes and m.lane != rl:
                    a, _ = z.lanes[m.lane]
                    if 0 <= a - m.s <= APPROACH:
                        approaching = True
            if not approaching:
                out["zclear(nextzone)"] = 1
        if "zclear(nextzone)" not in out:
            out["zbusy(nextzone)"] = 1
        # RSS rule 5, form B: a car on a crossing lane near the zone or in it, still moving: whether it yields is not yet
        # seen. It settles when it stands, or when it has left the zone. A merge's share has its own turn
        crossing = [m for m in movers if prio is not None and m.lane in z.lanes and m.lane != rl
                    and (speeds or {}).get(m.id, m.dyn.vmax) > STILL and m.s - m.length <= z.lanes[m.lane][1]
                    and z.lanes[m.lane][0] - m.s <= APPROACH]
        if prio == rl and any(windows_overlap(z, m, (speeds or {}).get(m.id, m.dyn.vmax), front, d_out, v, d.rho) for m in crossing) \
                and keeps_stop_short(front, v, d):
            out["cross_overlap(nextzone)"] = 1
        else:
            out["cross_unsettled(nextzone)" if crossing else "cross_settled(nextzone)"] = 1
        if zr["holder"]:
            out["holder(nextzone,%s)" % zr["holder"]] = 1
        if prio is None:
            out["share(nextzone)"] = 1
            last = (turn or {}).get(z.id)
            t_ego = max(0.0, front) / max(v, 0.1)
            first = any(0 <= z.lanes[m.lane][0] - m.s <= APPROACH
                        and (z.lanes[m.lane][0] - m.s) / max((speeds or {}).get(m.id, 0.0), 0.1) <= t_ego
                        for m in movers if m.lane in z.lanes and m.lane != rl and not inside(z, m))
            out["turn(nextzone)" if (last is None or last != rl) and not first else "wait_turn(nextzone)"] = 1
        else:
            out["conflict(nextzone)"] = 1
    else:
        out["zone_at(nextzone,none)"] = 1
        out["cross_settled(nextzone)"] = 1
    if "vru1" in roles:
        w = by_id[roles["vru1"]]
        for z in lm.zones:
            if w.lane in z.lanes and any(l in z.lanes for l in ego.route):
                a, b = z.lanes[w.lane]
                moving = (speeds or {}).get(w.id, w.dyn.vmax) > 0.05
                if moving and 0.0 <= w.s <= lm.lanes[w.lane].length:
                    out["crossing(vru1,on)"] = 1
                elif a - NEAR_WALK <= w.s <= b:
                    out["crossing(vru1,near)"] = 1
                break
    out["now"] = 1
    return out, roles, fold, states
