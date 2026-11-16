"""observer.py — the road's FINDINGS for the generic runtime (metis-plugin s-df4ff191; RUNTIME-INTERFACE v1.5 §3: what a
kernel cannot see), read from the road world the run drives (sumo_host.Loop or the exerciser's RoadWorld: both keep
`violations` and the ego's collisions), never the page:

    ob = Observer(); ob.new(world) -> [finding]   after each tick: what is new since the last call
    ob.end(summary, check) -> [finding]           the card's checks failed: one finding kind 'end'

  collision   the ego's contact with another, merged as the Leaderboard does (the same other within MERGE_S is one)
  violation   an RSS violation of the accounting (an accel above the response, a change into a pair made dangerous, a
              zone entered without priority unable to stop)
  end         the run's end when the card's own checks fail (its standing and why)
A finding: {kind, k, words, slug?, other? / what? / standing?}; its k is the world's tick (= the trace's: road_tree's
Live ticks the world once a tick, checked in test_road_runner); the runtime keeps its window [k-40, k+10]."""
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
    def __init__(self, dt=DT):
        self.dt = dt
        self.n_coll, self.n_viol = 0, 0
        self.last_with = {}

    def _tick_of(self, row, loop):
        if row.get("tick") is not None:
            return int(row["tick"])
        if row.get("t") is not None:
            return int(round(float(row["t"]) / self.dt))
        return int(getattr(loop, "tick", 0))

    def new(self, loop):
        out = []
        cols = _ego_collisions(loop)
        for c in cols[self.n_coll:]:
            other = _other(c)
            t = float(c.get("t") or 0.0)
            if other is not None and other in self.last_with and t - self.last_with[other] < MERGE_S:
                self.last_with[other] = t
                continue
            self.last_with[other] = t
            out.append({"kind": "collision", "k": self._tick_of(c, loop), "other": other, "slug": str(other),
                        "words": "the ego collided with %s (%s) at t %.1f s%s" % (
                            other, c.get("type") or c.get("how") or "contact", t, " at %s" % (c["xy"],) if c.get("xy") else "")})
        self.n_coll = len(cols)
        viol = getattr(loop, "violations", []) or []
        for v in viol[self.n_viol:]:
            k = self._tick_of(v, loop)
            what = v.get("what", "an RSS violation")
            out.append({"kind": "violation", "k": k, "what": what, "slug": "".join(ch if ch.isalnum() else "-" for ch in what)[:30],
                        "words": "RSS violation: %s%s at t %.1f s" % (what, " (pair %s)" % v["pair"] if v.get("pair") else "", k * self.dt)})
        self.n_viol = len(viol)
        return out

    def end(self, summary, check=None):
        if check and check.get("standing") not in (None, "pass"):
            fails = check.get("fails") or []
            return [{"kind": "end", "standing": check.get("standing"),
                     "words": "the card's checks failed (%s): %s" % (check.get("standing"), "; ".join(map(str, fails)) or "no reason given")}]
        return []
