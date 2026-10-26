"""road_host — the road domains' host on the EXERCISER (road-world s-e812715d step 2), in mh_host's shape: each member
of road/domains (responder, planner; the director has its own) gets one, and every host of a run shares
one RoadWorld (SHARED, keyed by the run). The world's facts come from road_facts (the projection every road host makes),
the commands go through restrict (the one restrictor), so the SUMO host (step 4) speaks the same interface.

    the run: $METIS_ROAD_RUN, a JSON file {"scenario", "seed", "log"?, "world"?, ...}; without it, the cruise
                       scenario, seed 1; "world": "sumo" runs sumo_host.Loop(run) instead of the exerciser (new_world)
    reading(counts)    the world's facts (road_facts.facts), filtered to the member's world-private preds, latched at
                       the member's clock period (the planner sees the world every tenth step)
    tick(counts)       the responder's host steps the world one DT (the fast member is the world's clock); then the
                       sync: the owned preds asserted / retracted, the member's own tokens untouched
    on_event(rule)     a fired rule that is a command (restrict.command) becomes the ego's, held for the member's
                       clock period (the planner's for ten ticks, the responder's for one)
The log ($METIS_ROAD_LOG, or the run's "log"): one JSON line a world step (the ego's t, s, v, a, lane, the command,
the fold), and the run's summary at the end (summary())."""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import restrict  # noqa: E402
import road_world  # noqa: E402
from semantic_world.ports import sync_diff  # noqa: E402

SHARED = {}                       # run key -> {"world": RoadWorld}


def run_spec():
    p = os.environ.get("METIS_ROAD_RUN")
    if p and os.path.exists(p):
        spec = json.load(open(p))
        spec.setdefault("key", os.path.abspath(p))
        return spec
    return {"scenario": "cruise", "seed": 1, "key": "default"}


def new_world(run):
    """The run's world: the exerciser (RoadWorld), or with "world": "sumo" nina's sumo_host.Loop, which presents
    RoadWorld's face (observe, command, step, tick, t, log, arrived, summary)."""
    if run.get("world") == "sumo":
        import sumo_host
        return sumo_host.Loop(run)
    return road_world.RoadWorld(run.get("scenario", "cruise"), int(run.get("seed", 1)))


def manifest(package_dir):
    p = os.path.join(package_dir, "domain.yaml")
    if not os.path.exists(p):
        return {}
    import yaml
    return yaml.safe_load(open(p)) or {}


class RoadHost:
    PAIRS = ()

    def __init__(self, package_dir, case=None):
        self.package_dir, self.case = package_dir, case
        self.spec = os.path.basename(os.path.normpath(package_dir))
        man = manifest(package_dir)
        self.observed = {p for p, d in (man.get("shared") or {}).items() if d == "world-private"}
        self.period = int(((man.get("clock") or {}).get("period")) or 1)
        self.steps = self.spec == "responder"
        run = run_spec()
        if run["key"] not in SHARED:
            SHARED[run["key"]] = {"world": new_world(run), "log": run.get("log") or os.environ.get("METIS_ROAD_LOG")}
        self.shared = SHARED[run["key"]]
        self.road = self.shared["world"]           # (the world(lines) face is AgentHost's: no attribute of that name)
        self.beat, self.due, self.script, self.last = 0, (), {}, None
        self.latched, self.latched_at, self.now_due = None, None, True

    # ── the world's facts, latched at the member's clock ──
    def fresh(self):
        facts = self.road.observe()[0]
        if self.observed:
            return {a: n for a, n in facts.items() if a.split("(")[0] in self.observed}
        return dict(facts)

    def reading(self, counts=None):
        """The member's copy of the world: refreshed once a clock period (the planner's every tenth world step, the
        responder's every step), so a slow member's copies change, and it beats, at its own rate (the tick's rule 1);
        `now` from the refresh until the member's command (one command a period)."""
        t = self.road.tick
        if self.latched is None or self.latched_at < t - t % self.period:
            self.latched, self.latched_at, self.now_due = self.fresh(), t, True
        out = {a: n for a, n in self.latched.items() if a != "now"}
        if self.now_due:
            out["now"] = 1
        return out

    def latch(self):
        """The Live's rule 2 (the world as it stood at the boundary) is this host's own: a member reads the world at
        its clock's refresh (reading), the fast member the step it made. Nothing to snapshot here."""

    def unlatch(self):
        pass

    def observe(self, counts):
        return self.reading(counts)

    def tick(self, counts):
        self.beat += 1
        if self.steps and self.beat > 1 and not self.road.arrived():
            self.road.step()
            self._log(self.road.log[-1])
        return self.sync(counts)

    def sync(self, counts):
        r = self.reading(counts)
        return sync_diff(r, counts, self.observed or {a.split("(")[0] for a in r})

    # ── the commands ──
    def on_event(self, name, args):
        cmd = restrict.command(name)
        if cmd is not None:
            self.now_due = False                       # this period's command is given
            self.road.command(cmd, life=self.period)
            self._log({"t": round(self.road.t, 2), "member": self.spec, "rule": name, "command": list(cmd)})

    def bind(self, reg):
        pass

    def world(self, lines):
        raise ValueError("world lines: the road is the world")

    def pending(self):
        return False

    def snapshot(self):
        return {"beat": self.beat}

    def restore(self, snap):
        self.beat = snap.get("beat", 0)

    def _log(self, rec):
        p = self.shared.get("log")
        if p:
            with open(p, "a") as f:
                f.write(json.dumps(rec) + "\n")


def make(case=None, package_dir=None):
    return RoadHost(package_dir or HERE, case)
