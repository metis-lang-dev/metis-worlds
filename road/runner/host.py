"""host.py — the ROAD's host face for the generic runtime (metis-agent metis_agent/runtime/host.py; RUNTIME-INTERFACE v1.5
§3): what one road run needs from the domain, for runtime.run.Run. The run's setup is road_tree.run's (the run spec
file road_host reads, the Live's config, the members' watch made blind, the run-end rules), the loop is the runtime's.

    host = RoadHost(scenario, seed, world_kind="sumo", card=None, kind="scenario", stop_after=None)
    Run(workspace, host, feed).go(road_config(seed), ticks, stem)

- prepare: the run spec file (scenario, seed, the log, its key = the run's name, the world, the trace dir for the truth
  column) as METIS_ROAD_RUN, before the Live makes the world
- start: every member's watch blind (a world that moves by itself: no surprise from its motion, as road_tree); the
  world found in road_host.SHARED by the run's key
- findings: observer.Observer.new(world) (collisions merged, RSS violations) at the world's tick (= the trace's)
- done: arrived (not while a cr: goal window holds it), held at the route's end, the cr: window over (stop_after)
- summary: road_tree.report's measures + the card's standing (cards.check_of); end_findings: rulecheck's broken
  rules over the run's log (SUMO) + 'end' when the card's checks fail; close: the world shut (one SUMO at a time)"""
import importlib.util
import json
import os
import shutil
import sys
import tempfile
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROAD = HERE.parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(ROAD / "world"))
import cards  # noqa: E402
import observer as O  # noqa: E402

from metis_agent.runtime.host import RuntimeHost  # noqa: E402

KEEP = ("arrived", "collisions", "collision_events", "violations", "ticks", "t", "rc", "s", "wall_s", "stopped", "held",
        "planner_kinds", "responder_kinds", "restricted", "undue_brakes")


def road_tree():
    m = sys.modules.get("road_tree")
    if m is None:
        spec = importlib.util.spec_from_file_location("road_tree", ROAD / "experiments" / "road_tree.py")
        m = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(m)
        sys.modules["road_tree"] = m
    return m


def road_config(seed):
    """The road family's Live config for one run (road_tree's: no model), with the road's trace keys (every 200,
    ring 0: the whole run, its world commands named)."""
    rt = road_tree()
    cfg = rt.config("journal.jsonl", int(seed))          # the runtime gives the run its own journal
    cfg["trace"] = {"every": 200, "ring": 0, "commands": rt.world_commands()}
    return cfg


class RoadHost(RuntimeHost):
    name = "road"
    domain = "road"
    window = (40, 10)                     # 4 s before a finding, 1 s after (0.1 s ticks)

    def __init__(self, scenario="straight", seed=1, world_kind="sumo", card=None, kind="scenario", stop_after=None,
                 vehicles=None, sensor_range=None):
        self.scenario, self.seed, self.world_kind = scenario, int(seed), world_kind
        self.card, self.kind, self.stop_after = card, kind, stop_after
        self.vehicles, self.sensor_range = vehicles, sensor_range
        self.obs = O.Observer()
        self.world = self.shared = self.key = None
        self.res, self.check, self.t0 = None, None, None
        self.tmp = None
        self.saved_env = None

    def prepare(self, cfg, run, trace_dir):
        self.tmp = Path(tempfile.mkdtemp(prefix="road-run-"))
        self.log = self.tmp / ("%s-%d.jsonl" % (self.scenario, self.seed))
        self.key = run
        spec = {"scenario": self.scenario, "seed": self.seed, "log": str(self.log), "key": run, "trace": trace_dir}
        if self.world_kind:
            spec["world"] = self.world_kind
        if self.vehicles is not None:
            spec["vehicles"] = int(self.vehicles)
        if self.sensor_range is not None:
            spec["sensor"] = {"range": float(self.sensor_range)}
        f = self.tmp / "run.json"
        f.write_text(json.dumps(spec))
        self.saved_env = os.environ.get("METIS_ROAD_RUN")
        os.environ["METIS_ROAD_RUN"] = str(f)

    def start(self, live, cfg):
        import road_host
        for ag in live.agents.agents.values():
            ag.watch.blind = True                      # a world that moves by itself: no surprise from its motion
        self.shared = road_host.SHARED[self.key]
        self.world = self.shared["world"]
        self.t0 = time.perf_counter()

    def findings(self, live, k):
        return self.obs.new(self.world)

    def done(self, live, k):
        rt, w, sh = road_tree(), self.world, self.shared
        held = self.stop_after is not None and rt.hold(w, sh, self.stop_after)
        if w.arrived() and not held:
            return True
        if sh.get("held") and not held:
            self.stopped = "held"
            return True
        if self.stop_after is not None and rt.window_over(w, self.stop_after):
            self.stopped = "window+%g" % self.stop_after
            return True
        return False

    def summary(self, live):
        rt = road_tree()
        res = rt.report(self.world, list(live.journal.recs), self.log, time.perf_counter() - (self.t0 or time.perf_counter()))
        res["stopped"] = getattr(self, "stopped", None)
        res["held"] = bool(self.shared.get("held"))
        self.res = res
        self.check = cards.check_of(self.card, self.kind, self.scenario, res) if self.card is not None else None
        out = {k: res[k] for k in KEEP if k in res}
        if self.check is not None:
            out["check"] = {k: self.check.get(k) for k in ("standing", "fails")}
        return out

    def end_findings(self, live, summary):
        net = getattr(getattr(self.world, "world", None), "net", None)
        out = [{"kind": "rule", "k": k, "rule": rule, "slug": cards.slug(rule), "words": "road rule broken: %s: %s" % (rule, words)}
               for k, rule, words in cards.broken_rules(self.log, net)]
        return out + self.obs.end(self.res or {}, self.check)

    def close(self, live):
        import road_host
        w = self.world
        if w is None and self.key in road_host.SHARED:          # the Live made the world, the run failed before start
            w = road_host.SHARED[self.key].get("world")
        if w is not None and getattr(w, "close", None):
            try:
                w.close()
            except Exception as e:
                sys.stderr.write("road runner: the world's close failed: %s\n" % e)
        road_host.SHARED.pop(self.key, None)
        if self.saved_env is None:
            os.environ.pop("METIS_ROAD_RUN", None)
        else:
            os.environ["METIS_ROAD_RUN"] = self.saved_env
        if self.tmp is not None:
            shutil.rmtree(self.tmp, ignore_errors=True)
