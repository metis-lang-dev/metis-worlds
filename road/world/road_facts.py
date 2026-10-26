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
- a role nobody fills: type(o, not_relevant), safe_long(o), safe_lat(o), safe_lat_left(o), safe_lat_right(o) — a
  vacant role is no danger;
- the lanes: adjacent(D) for a same-direction neighbour on side D; changing(D) while a lane change to D runs;
  settled(D) when no change runs and the ego did not leave side D within SETTLE_S (LEFT_FROM: the world's (side, age
  s) of its last change): an observed fact of its own manoeuvre, never a belief (road step 5: the planner's change
  ping-pong between two lanes whose leads both read slow);
- progress: below_limit (the ego under its lane's speed limit by more than 0.5 m/s), else at_limit; lead_slow (the
  lead within SLOW_RANGE ahead, slower than the ego's limit by more than SLOW_MARGIN, and the ego not slower than it
  by more than SLOW_MARGIN: nothing to gain behind it), else lead_ok (accel_ok then brings the ego up to it); accel_ok when
  two plans (2 PLAN_T) of full acceleration keep the lead at a safe distance (gap_room), else accel_no; keep_ok when
  two plans at the speed it has do, else keep_no; at_dest;
- the next zone on the ego's route (role nextzone): zone_at(nextzone, C) with C far | near | at | in (the ego's
  front at d_enter: beyond its reach far — its stated braking distance + NEAR_MARGIN, at least NEAR_RANGE — within it
  near, ≤ AT_RANGE at, inside in), and zone_at(nextzone, none) when no zone is ahead; zprio(nextzone, P) ego | obj |
  same (the zone's priority lane: the ego's, another's, none); can_stop(nextzone) (the ego's stated braking
  distance at brake_min, after its response time, ≤ d_enter: RSS's zone-entry rule), else late(nextzone); zfree(nextzone) when no mover
  at all is inside (every mover, not the bound ones only), and holder(nextzone, O) for zone_roles' holder; zclear(nextzone) when it is free and no
  mover on another of its lanes is within APPROACH of it, else zbusy(nextzone); conflict(nextzone) for crossing axes (a zone with a
  priority), share(nextzone) for a merge's (none); turn(nextzone) at a merge when the last to enter came from
  another lane (the zipper's alternation, TURN: the host's {zone: the lane of the last entrant}) and no mover on
  another of its lanes reaches the line first, else wait_turn(nextzone) (road step 5, yield_merge: the alternation
  alone gave the ego the turn while the ramp's car arrived first, and the responder braked for its cut-in);
- the walker: crossing(vru1, on) while it is on a crosswalk lane that crosses the ego's route ahead, near when
  it waits within NEAR_WALK of it;
- the beat: now (one a tick; the command rules consume it)."""
from dataclasses import replace

from semantic_world.situation import Situation, safe_same_dir, stated

OBJ_ROLES = ("lead", "follower", "leadleft", "followleft", "leadright", "followright", "a1", "a2", "a3", "vru1")
NEAR_RANGE, AT_RANGE, APPROACH, NEAR_MARGIN = 30.0, 3.0, 40.0, 10.0
SLOW_RANGE, SLOW_MARGIN, NEAR_WALK = 60.0, 2.0, 1.0
PLAN_T = 1.0                      # the planner's period (s): accel_ok looks one plan ahead


def inside(z, m):
    """M is inside zone Z: [s − length, s] overlaps the zone's span on its lane (the library's rule)."""
    if m.lane not in z.lanes:
        return False
    a, b = z.lanes[m.lane]
    return m.s >= a and m.s - m.length <= b


def gap_room(pairs, ego, v, cap, accel, t=2 * PLAN_T):
    """The ego may hold ACCEL for T and stay at a safe distance behind its lead (RSS rule 1): the gap after T, the lead
    holding its speed, still above Lemma 2's safe distance at the speed it reaches. T is two plans: the planner acts
    once a period, and its next decision takes a period to act. No lead: room."""
    lead = next((p for p in pairs if p.role == "lead" and p.type == "same_dir" and p.lon == "in_front"), None)
    if lead is None:
        return True
    v1 = max(0.0, min(cap, v + accel * t))
    tc = t if accel == 0 or v1 in (cap, 0.0) and accel == 0 else min(t, abs((v1 - v) / accel)) if accel else t
    run = 0.5 * (v + v1) * tc + v1 * (t - tc)
    gap1 = lead.d_lon + lead.obj.vmin * t - run
    return gap1 > safe_same_dir(replace(ego.dyn, vmin=v1, vmax=v1), lead.obj)


SETTLE_S = 10.0                 # s: the side the ego left is not settled again before this


def facts(lm, ego, v, movers, sit, changing=None, dest=None, turn=None, lights=None, speeds=None, left_from=None):
    """SPEEDS {mover id: v}: the movers' speeds (the lead's for lead_slow). LEFT_FROM (side, age s): the side the
    ego's last lane change left, and how long ago."""
    ego.route = ego.route or [ego.lane]
    roles = lm.roles(ego, movers, lights=lights)
    role_of = {m: r for r, m in roles.items()}
    pairs = lm.pairs(ego, movers, role_of=lambda o: role_of.get(o.id), lights=lights)
    states = sit.check(pairs)
    fold = Situation.fold(states, ego.dyn)
    out = {}
    for a, n in Situation.facts(states, fold, detail=True).items():
        if a.startswith("resp_lat(") and a.count(",") == 2:        # the pair's lateral response: its own name (a
            a = "resp_side(" + a[len("resp_lat("):]               # pred has one arity; resp_lat(R) is the fold's)
        out[a] = n
    bound = set(roles)
    for r in OBJ_ROLES:
        if r not in bound:
            out.update({"type(%s,not_relevant)" % r: 1, "safe_long(%s)" % r: 1, "safe_lat(%s)" % r: 1,
                        "safe_lat_left(%s)" % r: 1, "safe_lat_right(%s)" % r: 1})
    lane = lm.lanes[ego.lane]
    for side in ("left", "right"):
        if getattr(lane, side) and not getattr(lane, side + "_opposite"):
            out["adjacent(%s)" % side] = 1
    if changing:
        out["changing(%s)" % changing] = 1
    else:
        for side in ("left", "right"):
            if not (left_from and left_from[0] == side and left_from[1] < SETTLE_S):
                out["settled(%s)" % side] = 1
    cap = lm.vcap(ego.lane)
    out["below_limit" if v < cap - 0.5 else "at_limit"] = 1
    by_id = {m.id: m for m in movers}
    if "lead" in roles:
        lead = by_id[roles["lead"]]
        d = lm.ahead(ego.route, ego.s, lead.lane, lead.s)
        lv = (speeds or {}).get(lead.id, lead.dyn.vmax)
        if d is not None and 0 <= d <= SLOW_RANGE and lv < cap - SLOW_MARGIN and v >= lv - SLOW_MARGIN:
            out["lead_slow"] = 1
    if "lead_slow" not in out:
        out["lead_ok"] = 1
    out["accel_ok" if gap_room(pairs, ego, v, cap, ego.dyn.accel) else "accel_no"] = 1
    out["keep_ok" if gap_room(pairs, ego, v, cap, 0.0) else "keep_no"] = 1
    if dest is not None and ego.s >= dest:
        out["at_dest"] = 1
    zr = lm.zone_roles(ego, movers, roles)                      # the zone binding: the library's, never by hand
    near = lm.nearest_zone(ego.route, ego.s, length=ego.length) if zr["nextzone"] else None
    if near is not None and near[0].id == zr["nextzone"]:
        z, rl, d_in, d_out = near
        front = d_in
        d = ego.dyn
        reach = max(NEAR_RANGE, stated(v, 0.0, d.rho, d.brake_min) + NEAR_MARGIN)   # near: within its stopping reach
        cls = "in" if front <= 0 < d_out else "at" if front <= AT_RANGE else "near" if front <= reach else "far"
        out["zone_at(nextzone,%s)" % cls] = 1
        prio = lm.priority(z, lights)
        out["zprio(nextzone,%s)" % ("same" if prio is None else "ego" if prio == rl else "obj")] = 1
        out["can_stop(nextzone)" if stated(v, 0.0, d.rho, d.brake_min) <= max(0.0, front) else "late(nextzone)"] = 1
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
