"""observer.py — what a headless road run reports to the Metis plugin (metis-plugin s-df4ff191 v3: the headless runner).

    obs = Observer(loop, sink, run, scenario, seed); obs.tick() after each Live tick; obs.end(summary, check)

The observer reads the road world the run drives (sumo_host.Loop or the exerciser's RoadWorld: both keep `violations`
and the ego's collisions), never the page. Each finding becomes ONE surprise through SINK (road_runner.Interface: the
standard surprise interface; a list in the tests):
  collision   the ego's contact with another (SUMO's check / the box test), merged as the Leaderboard does
              (sumo_host.collision_events' rule: the same other within MERGE_S is one event)
  violation   an RSS violation of the accounting (an accel above the response, a change into a pair made dangerous, a
              zone entered without priority unable to stop)
  rule        a European road rule the run broke (road/tools/rulecheck.py over the run's log, at the end)
  end         the run's end when the card's own checks fail (its standing and why); every end is also an EVENT
A surprise names its window in the run's trace: WINDOW_S before the tick to POST_S after it, clamped to the run. The
findings are QUEUED while the run goes (`pending`, the status's counts) and posted by flush() once the trace is closed:
the interface keeps the window from the trace on disk, which is complete only then."""
import math

WINDOW_S, POST_S = 4.0, 1.0
MERGE_S = 5.0
DT = 0.1


def _ego_collisions(loop):
    """The ego's collision rows: SUMO's (sumo_host.Loop.world.collisions: collider / victim, every vehicle's) or the
    exerciser's (RoadWorld.collisions: the ego's only, the other as `with`)."""
    w = getattr(loop, "world", None)
    rows = w.collisions if w is not None and hasattr(w, "collisions") else getattr(loop, "collisions", [])
    return [c for c in rows or [] if isinstance(c, dict) and ("with" in c or "ego" in (c.get("collider"), c.get("victim")))]


def _other(c):
    if "with" in c:
        return c["with"]
    return c.get("victim") if c.get("collider") == "ego" else c.get("collider")


class Observer:
    def __init__(self, loop, sink, run, scenario, seed, dt=DT):
        self.loop, self.sink, self.run, self.scenario, self.seed, self.dt = loop, sink, run, scenario, int(seed), dt
        self.n_coll, self.n_viol = 0, 0
        self.last_with = {}                       # the other -> the t of its last collision event (the merge)
        self.sent, self.pending = [], []

    def _tick_of(self, row):
        if row.get("tick") is not None:
            return int(row["tick"])
        if row.get("t") is not None:
            return int(round(float(row["t"]) / self.dt))
        return int(getattr(self.loop, "tick", 0))

    def _send(self, kind, k, words, extra=None):
        body = {"run": self.run, "kind": kind, "words": words, "scenario": self.scenario, "seed": self.seed, "tick": k}
        if extra:
            body.update(extra)
        self.pending.append(body)
        return body

    def counts(self):
        out = {}
        for b in self.pending + self.sent:
            out[b["kind"]] = out.get(b["kind"], 0) + 1
        return out

    def flush(self, last_tick=None):
        """Post the queued surprises (the trace closed): each with its window clamped to [0, LAST_TICK]."""
        last = int(last_tick if last_tick is not None else getattr(self.loop, "tick", 0))
        out = []
        for b in self.pending:
            k = min(int(b["tick"]), last)
            b["window"] = [max(0, k - int(WINDOW_S / self.dt)), min(last, k + int(POST_S / self.dt))]
            out.append(self.sink.surprise(b))
            self.sent.append(b)
        self.pending = []
        return out

    def tick(self, loop=None):
        """After a Live tick (road_tree.run's on_tick hands the world)."""
        if loop is not None:
            self.loop = loop
        cols = _ego_collisions(self.loop)
        for c in cols[self.n_coll:]:
            other = _other(c)
            t = float(c.get("t") or 0.0)
            if other is not None and other in self.last_with and t - self.last_with[other] < MERGE_S:
                self.last_with[other] = t
                continue
            self.last_with[other] = t
            k = self._tick_of(c)
            self._send("collision", k, "the ego collided with %s (%s) at t %.1f s%s" % (
                other, c.get("type") or c.get("how") or "contact", t, " at %s" % (c["xy"],) if c.get("xy") else ""),
                {"other": other})
        self.n_coll = len(cols)
        viol = getattr(self.loop, "violations", []) or []
        for v in viol[self.n_viol:]:
            k = self._tick_of(v)
            what = v.get("what", "an RSS violation")
            self._send("violation", k, "RSS violation: %s%s at t %.1f s" % (
                what, " (pair %s)" % v["pair"] if v.get("pair") else "", k * self.dt), {"what": what})
        self.n_viol = len(viol)

    def rules(self, broken):
        """BROKEN: [(tick, rule, words)] from rulecheck over the run's log."""
        for k, rule, words in broken:
            self._send("rule", int(k), "road rule broken: %s: %s" % (rule, words), {"rule": rule})

    def end(self, summary, check=None):
        """The run's end: an EVENT always; a SURPRISE when the card's checks fail (CHECK: {standing, fails})."""
        k = int(getattr(self.loop, "tick", 0))
        ev = {"run": self.run, "edge": "end", "k0": 0, "k1": k, "scenario": self.scenario, "seed": self.seed,
              "words": "run over: arrived %s, collisions %s, violations %s%s" % (
                  summary.get("arrived"), summary.get("collisions"), summary.get("violations"),
                  ", standing %s" % check.get("standing") if check else "")}
        self.sink.event(ev)
        if check and check.get("standing") not in (None, "pass"):
            fails = check.get("fails") or []
            self._send("end", k, "the card's checks failed (%s): %s" % (check.get("standing"), "; ".join(map(str, fails))
                                                                         or "no reason given"), {"standing": check.get("standing")})
        return ev
