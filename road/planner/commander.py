"""commander.py — the road family's fired command rules → ONE BehaviourCmd (contracts), as the vehicle stack decides it:
a PORT of RoadDomain's Commander (perotheia-packages/road core/command.cc at fb638d0; its docs/DESIGN.md section 2), so the
road world's trajectory level (sumo_planned, metis-plugin s-df4ff191 step 5) gets the commands the C++ planner gets in
CARLA. Two copies until the C3 framework makes one implementation (the toolchains brief): keep it EQUAL to command.cc,
rule for rule (road/tests/test_commander.py pins the table below); a change goes into command.cc first.

    c = Commander(); c.fired(member, rule, rd, ego); c.command(holder, status) → BehaviourCmd dict | None

- a member's last command stands until it commands again; the holder of the controls (the director's grant:
  responder > signals > planner) decides, else the planner member's;
- a decision keeps its seq until it changes (`same`); a CHANGE_* / PASS_OPPOSITE keeps its seq against the planner
  member's next decisions and the responder's brake_lon until the planner's status says it ended (CHANGE_* on DONE,
  ABORTED, REFUSED_NO_LANE; PASS_OPPOSITE on DONE or ABORTED); the responder's lateral stop always goes.
- rd (the reading): cap (the pace, m/s; 0 = none: the lane's limit), line (the front bumper to the zone line, m),
  stop (x, y) of a red light's stop line or None, roles {role: obstacle id}; ego {x, y, heading, speed} at the CENTRE
  (EGO_FRONT: the centre → the front bumper, the caller's vehicle)."""
import math
from dataclasses import dataclass, replace

KEEP, FOLLOW, STOP_AT, YIELD, CHANGE_LEFT, CHANGE_RIGHT, PASS_OPPOSITE = range(7)
NAMES = {KEEP: "keep", FOLLOW: "follow", STOP_AT: "stop_at", YIELD: "yield", CHANGE_LEFT: "change_left",
         CHANGE_RIGHT: "change_right", PASS_OPPOSITE: "pass_opposite"}
CHANGE_NONE, CHANGE_ACTIVE, CHANGE_DONE, REFUSED_NO_GAP, REFUSED_NO_LANE, ABORTED, ABORT_BLOCKED = range(7)


def brake_of(r):
    return 8.0 if r == "brake_max" else 3.0 if r == "brake_min_correct" else 4.0


def rule_base(rule):
    return rule.split("[", 1)[0]


def rule_bindings(rule):
    _, _, rest = rule.partition("[")
    return dict(kv.split("=", 1) for kv in rest.rstrip("]").split(",") if "=" in kv) if rest else {}


def is_change(k):
    return k in (CHANGE_LEFT, CHANGE_RIGHT, PASS_OPPOSITE)


@dataclass
class Decision:
    kind: int = KEEP
    v_target: float = 0.0
    lead_id: int = 0
    min_gap: float = 0.0
    x: float = 0.0
    y: float = 0.0
    yield_id: int = 0
    reason: str = ""
    member: str = ""

    def same(self, o):
        if self.kind == o.kind and self.reason.startswith("brake_lon") and o.reason.startswith("brake_lon"):
            return self.reason == o.reason
        if self.kind == o.kind and self.reason == "stop_wish" and o.reason == "stop_wish":
            return True
        return (self.kind == o.kind and self.lead_id == o.lead_id and self.yield_id == o.yield_id
                and abs(self.v_target - o.v_target) < 0.25 and abs(self.x - o.x) < 1.0 and abs(self.y - o.y) < 1.0)


class Commander:
    def __init__(self, ego_front=3.8):
        self.last, self.current, self.seq = {}, None, 0
        self.ego_front = ego_front

    def fired(self, member, rule, rd, ego):
        base, b = rule_base(rule), rule_bindings(rule)
        v = max(0.0, float(ego["speed"]))
        cap = float(rd.get("cap") or 0.0)
        pace = cap if 0 < cap < 1e3 else 0.0
        roles = rd.get("roles") or {}

        def ahead(d, x):
            x.x = ego["x"] + (self.ego_front + d) * math.cos(ego["heading"])
            x.y = ego["y"] + (self.ego_front + d) * math.sin(ego["heading"])
        d = Decision(reason=rule, member=member)
        if base in ("accel", "keep_limit", "brake_target"):
            d.kind, d.v_target = KEEP, pace
            if rd.get("cap") is not None and 0 <= cap < 0.3:   # a target of 0 (the person's stop): KEEP 0 is the limit,
                d.kind = STOP_AT                              # so the planner's gentle stop ahead (2 m/s²), held
                ahead(v * v / (2.0 * 2.0) + 0.5, d)
                d.reason = "stop_wish"
        elif base in ("keep_gap", "keep_cross"):
            d.kind, d.v_target = KEEP, max(0.5, v)
        elif base in ("brake_cross", "brake_cross_late", "brake_unseen"):
            d.kind, d.v_target = KEEP, max(0.0, v - 3.0 * 1.0)
        elif base == "inch_hidden":
            d.kind, d.v_target = KEEP, 1.5
        elif base in ("keep_lead", "brake_follow", "brake_pass_blocked"):
            d.kind, d.lead_id = FOLLOW, int(roles.get("lead") or 0)
        elif base in ("change", "change_pass", "change_aside", "change_back", "change_route") \
                or base.startswith("change_emergency"):
            side = b.get("D", "").lower()
            if side not in ("left", "right"):
                return
            d.kind = CHANGE_LEFT if side == "left" else CHANGE_RIGHT
        elif base == "change_oncoming":
            d.kind, d.lead_id = PASS_OPPOSITE, int(roles.get("lead") or 0)
        elif base in ("change_home", "drive_away"):
            return
        elif base in ("yield_red", "yield_amber"):
            d.kind = STOP_AT
            if rd.get("stop") is not None:
                d.x, d.y = rd["stop"]
            else:
                ahead(max(0.0, rd.get("line") or 0.0), d)
        elif base in ("yield_zone", "yield_merge", "yield_hidden", "yield_walker"):
            d.kind = YIELD
            ahead(max(0.0, rd.get("line") or 0.0), d)
            d.yield_id = int(roles.get("vru1") or 0) if base == "yield_walker" else 0
        elif base == "brake_lon":
            d.kind, d.min_gap = STOP_AT, 0.01
            ahead(v * v / (2.0 * brake_of(b.get("R", ""))), d)
        elif base in ("stop_lat_left", "stop_lat_right"):
            d.kind, d.v_target = KEEP, max(0.5, v)
        else:
            return
        self.last[member] = d

    def changing(self, status):
        c = self.current
        if c is None or not status or status.get("cmd_seq") != self.seq or not is_change(c.kind):
            return ""
        if status.get("change") != CHANGE_ACTIVE:
            return ""
        return "right" if c.kind == CHANGE_RIGHT else "left"

    def command(self, holder, status=None):
        want = self.last.get(holder) if holder and holder in self.last else self.last.get("planner")
        if want is None and self.current is None:
            return None
        if want is not None and (self.current is None or not want.same(self.current)):
            hold = False
            longitudinal = want.member == "planner" or (want.member == "responder" and want.reason.startswith("brake_lon"))
            if self.current is not None and is_change(self.current.kind) and longitudinal:
                mine = bool(status) and status.get("cmd_seq") == self.seq
                c = status.get("change", CHANGE_NONE) if status else CHANGE_NONE
                ended = mine and (c in (CHANGE_DONE, ABORTED) or (self.current.kind != PASS_OPPOSITE and c == REFUSED_NO_LANE))
                hold = not ended
            if not hold:
                self.current = replace(want)
                self.seq += 1
        c = self.current
        return {"seq": self.seq, "kind": c.kind, "name": NAMES[c.kind], "v_target": c.v_target, "lead_id": c.lead_id,
                "min_gap": c.min_gap, "x": c.x, "y": c.y, "yield_id": c.yield_id, "reason": c.reason, "member": c.member}
