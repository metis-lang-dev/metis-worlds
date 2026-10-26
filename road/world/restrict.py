"""restrict — the road domains' commands and the RESTRICTOR (road-world s-e812715d; framework L4), shared by every road
host (the exerciser's road_host, the SUMO host): one parsing of a fired rule into a command, one bound on what the
ego may do. Truth-free: it reads the fold of the situation layer, the ego's Dynamics and speed, and the lane state.

    command(rule) -> (kind, arg) | None
        the rule's name says the command (as mh_host's): its first token, `accel` `keep` `brake` `change` `yield`
        `stop` (stop_lat); the argument from the rule's bindings — brake[R=brake_min] the response, change[D=left]
        the side. A rule whose first token is none of these is no command.
    restrict(cmd, fold, dyn, v, changing=None, yield_gap=None) -> (accel, lane)
        accel: the commanded acceleration, capped by the proper response (RSS Def 10): resp_lon brake_min / _correct
        → at most −that braking; keep holds the speed (0); yield brakes to stop the front bumper dyn.min_dist before
        the zone line (YIELD_GAP: the distance from the front bumper to s_enter); never below −brake_max.
        lane: 'left' / 'right' to begin a change, 'abort' to go back to the lane it leaves (a lateral response
        toward the side it moves, or stop_lat), None to stay. A change begun is refused when the fold already
        has a lateral response on that side.
    capped(cmd, ...) -> True when the restrictor cut the command (the domain asked more than RSS allows)."""

KINDS = ("accel", "keep", "brake", "change", "yield", "stop")
CHANGE_S = 1.0                    # a lane change's duration (s)


def bindings(rule):
    base, _, rest = rule.partition("[")
    b = dict(kv.split("=", 1) for kv in rest.rstrip("]").split(",") if "=" in kv) if rest else {}
    return base, b


def command(rule):
    base, b = bindings(rule)
    kind = base.split("_")[0]
    if kind not in KINDS:
        return None
    if kind == "stop":
        return ("stop_lat", None) if base.startswith("stop_lat") else None
    if kind == "brake":
        return ("brake", b.get("R", "brake_min"))
    if kind == "change":
        d = b.get("D", "").lower()
        return ("change", d) if d in ("left", "right") else None
    return (kind, None)


def bound(fold, dyn):
    """The proper response's upper bound on the ego's acceleration."""
    r = fold.get("resp_lon", "none")
    if r == "brake_min":
        return -dyn.brake_min
    if r == "brake_min_correct":
        return -dyn.brake_min_correct
    return dyn.accel


def wanted(cmd, dyn, v, yield_gap=None):
    kind, arg = cmd or ("keep", None)
    if kind == "accel":
        return dyn.accel
    if kind == "brake":
        return -(getattr(dyn, arg, None) or dyn.brake_min)
    if kind == "yield" and yield_gap is not None:
        gap = yield_gap - (dyn.min_dist or 0.0)
        if gap <= 0.2:
            return -dyn.brake_max if v > 0 else 0.0
        need = v * v / (2.0 * gap)
        return -min(dyn.brake_max, need) if need > 0.3 else 0.0
    return 0.0


def restrict(cmd, fold, dyn, v, changing=None, yield_gap=None):
    a = min(wanted(cmd, dyn, v, yield_gap), bound(fold, dyn))
    a = max(a, -dyn.brake_max)
    if v <= 0.0 and a < 0.0:
        a = 0.0
    kind, arg = cmd or ("keep", None)
    lane = None
    if changing:
        if kind == "stop_lat" or fold.get("resp_lat_%s" % changing, fold.get("resp_lat", "none")) != "none":
            lane = "abort"
    elif kind == "change" and fold.get("resp_lat_%s" % arg, "none") == "none":
        lane = arg
    return a, lane


def capped(cmd, fold, dyn, v, yield_gap=None):
    return wanted(cmd, dyn, v, yield_gap) > bound(fold, dyn) + 1e-9
