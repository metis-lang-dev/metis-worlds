"""iface.py — the planner levels' interface (planner-loop s-0dcc5ed1 step 2, deliverable 4; PLANNER.md §1, §2, §5 step 1).

Plain dataclasses, no dependency (the Live's venv and the planner venv both import it): what crosses between the
behaviour level (the road family's command per beat), the trajectory level (the reactive planner now, ours in step 3)
and the oracle. No new vocabulary for the family: a Command is the family's held command as sumo_host.Loop holds it
(`Loop.cmd`, the tuple restrict.command makes of a fired rule), read, never re-decided.

  Command    the beat's command: kind (accel, keep, brake, yield, inch, change, change_back, stop_lat, ...) + its args
  Setpoints  what the trajectory level is told for the beat (the composition's mapping, setpoints_of): a desired speed,
             a stop point, the lane whose centreline is the reference path
  Reference  PLANNER.md §2's four pieces: path, profile, corridor, guess (step 3 builds all four; the composition only
             the path and the setpoints)
  Plan       one planner cycle's output: the states for the horizon, feasible, cost, why not, the solver's time
  Row        the oracle's row (cr_bench.blank_row's keys, the table's columns)
"""
from dataclasses import dataclass, field
from typing import List, Optional, Tuple

STOP_V = 0.0          # the speed a stop setpoint asks for


@dataclass(frozen=True)
class Command:
    kind: str
    args: Tuple = ()

    @classmethod
    def of(cls, held):
        """From the Loop's held command: a tuple (kind, *args), a bare kind, or None (= keep)."""
        if held is None:
            return cls("keep")
        if isinstance(held, str):
            return cls(held)
        held = tuple(held)
        return cls(str(held[0]), tuple(held[1:]))


@dataclass
class Setpoints:
    desired_v: Optional[float] = None         # m/s: the speed to keep (velocity keeping)
    stop_xy: Optional[Tuple[float, float]] = None   # a stop point (CommonRoad coordinates): stopping mode
    lane: Optional[str] = None                # the lane whose centreline is the reference path (None: the route's)
    why: str = ""                             # the command it came from, for the record


@dataclass
class Reference:
    path: List[Tuple[float, float]] = field(default_factory=list)
    profile: List[float] = field(default_factory=list)        # v per path point (step 3)
    corridor: List[object] = field(default_factory=list)      # per step half-spaces (step 3)
    guess: List[Tuple[float, ...]] = field(default_factory=list)   # (x, y, psi, v, a, delta) per step (step 3)


@dataclass
class Plan:
    states: List[dict] = field(default_factory=list)   # {k, x, y, v, phi, delta, a} at the vehicle's centre
    feasible: bool = False
    cost: Optional[float] = None
    reason: Optional[dict] = None                     # why not feasible (the planner's own counts / exception)
    ms: Optional[float] = None


ROW_KEYS = ("id", "planner", "outcome", "goal", "collision", "offroad", "feasible", "cost", "cost_function", "ms_cycle",
            "cycles", "steps", "goal_window", "goal_kind", "traffic", "reason", "file", "solution", "seconds")


def _target(facts_target, limit):
    """The family's target speed: its own target when the facts carry one, else the lane's limit."""
    return facts_target if facts_target is not None else limit


def setpoints_of(cmd, ego_v, limit, target=None, stop_xy=None, sibling=None, own=None, brake_bound=None, beat_s=1.0):
    """The composition's mapping, one Command → Setpoints (brief planner-step2.md deliverable 3; the day-1 review's
    ruling b: the desired speed is the FAMILY's target, never the initial speed):
      accel, keep          → desired_v = the target (the facts' target speed, else the lane's limit)
      brake(R)             → desired_v = max(0, ego_v - bound * beat): R's bound (m/s², positive) over the beat
      yield, inch          → stop at stop_xy (the zone line ahead) when known, else desired_v = 0
      change(side)         → the sibling lane's centreline as the path, desired_v = the target
      change_back          → the own lane's centreline, desired_v = the target
      anything else        → keep's
    `limit` the lane's speed limit, `target` the facts' target (the pace), `sibling` / `own` the lane ids."""
    c = cmd if isinstance(cmd, Command) else Command.of(cmd)
    v_t = _target(target, limit)
    why = c.kind + ("(%s)" % ",".join(str(a) for a in c.args) if c.args else "")
    if c.kind == "brake":
        b = brake_bound if brake_bound is not None else 4.0
        return Setpoints(desired_v=max(0.0, ego_v - abs(b) * beat_s), lane=own, why=why)
    if c.kind in ("yield", "inch"):
        if stop_xy is not None:
            return Setpoints(stop_xy=tuple(stop_xy), lane=own, why=why)
        return Setpoints(desired_v=STOP_V, lane=own, why=why)
    if c.kind == "change":
        return Setpoints(desired_v=v_t, lane=sibling if sibling is not None else own, why=why)
    if c.kind == "change_back":
        return Setpoints(desired_v=v_t, lane=own, why=why)
    return Setpoints(desired_v=v_t, lane=own, why=why)
