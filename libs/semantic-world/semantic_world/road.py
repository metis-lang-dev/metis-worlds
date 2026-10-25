"""road — the lane adapter's BELIEF (road-world s-e812715d step 4, the framework brief's L2): the road's movers as
tracks over metis's LaneMap (semantic_world.lane / net), in nav-belief's structure (semantic_world.intent).

- A cell is (lane, s-bin): `lane|k`, k = ⌊s / BIN⌋. The cell graph: the next bin along the lane, the first bin of each
  successor lane at its end (a junction's internal lanes included), the same s on the left and the right neighbour.
- A TRACK per mover seen: its class (vClass, `pedestrian` for a walker), its speed (the last detection's), a
  belief over cells, and a categorical INTENT belief over INTENTS = keep, change_left, change_right, yield, cross,
  its prior by class. One motion kernel per intent at the track's speed and the tick's dt:
    keep          along its lane at its speed (a bin a tick at speed·dt/BIN, the fraction as a probability);
    change_left   along, and to the left neighbour at RATE a tick;  change_right  the same to the right;
    yield         along at a third of its speed (it slows for a zone, a walker, a merge);
    cross         across: to either neighbour at RATE a tick, barely along (a walker crossing, a car cutting over).
- UPDATE from a detection (the sensing model's: class, lane, s, speed; no identity) associated through the gate
  (bayes.associate: a track's predicted mass within its reach since last seen); the intent ∝ p · (L + FLOOR)^TEMPER,
  L the intent's kernel mass at the detected cell after the gap. PREDICT unseen under the mixture; the sensor's
  visible cells where nothing was detected are negative evidence (bayes.missed); a track that leaves the map's
  range fades (the alive decay) and is dropped.
- predict_table(h, ego): per tick t = 1..h the first-passage HAZARD that a track, its intent I, enters the ego's
  danger region at t given it has not before — the cells of the ego's route ahead of its predicted position within
  the RSS safe distance (situation.safe_same_dir for the pair) — its belief rolled under I alone; the categorical
  intent beside; rows are TICKS (the ruling on nav-belief's shape, spec/16 §10.1).
Nothing here names a simulator: the TraCI host (metis-worlds/road) feeds detections and the ego's state."""
import math

from . import bayes, core
from .lane import dynamics_for
from .situation import safe_same_dir

BIN = 5.0                                      # metres a cell
INTENTS = ("keep", "change_left", "change_right", "yield", "cross")
RATE = 0.15                                    # a lane change's (or a crossing's) step a tick, under its intent
KEEP_DRIFT = 0.005                             # … under keep: a car rarely leaves its lane
TEMPER, FLOOR = 0.5, 0.005                     # a car's kinematics fit its kernels better than a NetHack beast's
                                               # (nav-belief's 0.3 / 0.02): a lane change in two ticks of four is
                                               # change_left, a floor of 0.02 would hide the drift's 0.005
PRIORS = {"passenger": {"keep": 0.7, "change_left": 0.1, "change_right": 0.1, "yield": 0.1, "cross": 0.0},
          "pedestrian": {"keep": 0.2, "change_left": 0.0, "change_right": 0.0, "yield": 0.3, "cross": 0.5}}
ALIVE = (0.05, -4.0)                           # an unseen track's exists falls 0.05 a tick, dropped below -4
EPS = 1e-4


def cell(lane, s):
    return "%s|%d" % (lane, max(0, int(s // BIN)))


def of(c):
    lane, _, k = c.rpartition("|")
    return lane, int(k)


def prior(vclass, table=None):
    table = table or PRIORS
    p = dict(table.get(vclass) or table.get("passenger") or {i: 1.0 for i in INTENTS})
    p = {i: max(0.0, float(p.get(i, 0.0))) for i in INTENTS}
    z = sum(p.values()) or 1.0
    return {i: v / z for i, v in p.items()}


class RoadMap(core.SemanticMap):
    """The road's belief over a LaneMap (held in memory: a host loads it from the net once; the store keeps the
    beliefs). build(path, lanemap, dt) → the map; cycle(detections, visible, ego) per tick."""

    def __init__(self, path, lanemap=None, journal=None):
        super().__init__(path, journal)
        self.lanemap = lanemap

    @classmethod
    def build(cls, path, lanemap, dt=0.1, priors=None, journal=None):
        m = cls(path, lanemap, journal)
        m.data = {"dt": float(dt), "bin": BIN, "things": {}, "belief": {}, "exists": {}, "intent": {}, "speed": {},
                  "last_seen": {}, "clock": 0, "agent": {"at": None, "holding": None}, "ego": None, "binding": {},
                  "k": 0, "priors": dict(priors or PRIORS), "looked": {}}
        m.save()
        return m

    # ── the cell graph ──
    def nbins(self, lane):
        return max(1, int(math.ceil(self.lanemap.lanes[lane].length / BIN)))

    def along(self, c):
        """The next cells along: the next bin, or the first bin of every successor lane."""
        lane, k = of(c)
        if k + 1 < self.nbins(lane):
            return ["%s|%d" % (lane, k + 1)]
        return ["%s|0" % s for s in self.lanemap.lanes[lane].succ if s in self.lanemap.lanes] or [c]

    def side(self, c, which):
        """The same s on the left (which = "left") or right neighbour lane, None when there is none."""
        lane, k = of(c)
        n = getattr(self.lanemap.lanes[lane], which)
        if not n or n not in self.lanemap.lanes:
            return None
        return "%s|%d" % (n, min(k, self.nbins(n) - 1))

    def neighbours(self, c):
        out = list(self.along(c))
        for w in ("left", "right"):
            s = self.side(c, w)
            if s:
                out.append(s)
        return [x for x in out if x != c]

    # ── the kernels ──
    def kernel(self, intent, speed, dt):
        """intent's one-tick motion at SPEED: model({cell: p}) → {cell: p}."""
        adv = max(0.0, speed) * dt / BIN
        if intent == "yield":
            adv /= 3.0
        if intent == "cross":
            adv /= 10.0
        lat = {"keep": {"left": KEEP_DRIFT, "right": KEEP_DRIFT}, "yield": {"left": KEEP_DRIFT, "right": KEEP_DRIFT},
               "change_left": {"left": RATE, "right": 0.0}, "change_right": {"left": 0.0, "right": RATE},
               "cross": {"left": RATE / 2, "right": RATE / 2}}[intent]

        def one(c):
            out = {}
            n, f = divmod(adv, 1.0)
            pos = {c: 1.0}
            for _ in range(int(n)):                     # whole bins this tick
                nxt = {}
                for x, m in pos.items():
                    a = self.along(x)
                    for y in a:
                        nxt[y] = nxt.get(y, 0.0) + m / len(a)
                pos = nxt
            for x, m in pos.items():                    # the fraction: one bin more with probability f
                a = self.along(x)
                out[x] = out.get(x, 0.0) + m * (1 - f)
                for y in a:
                    out[y] = out.get(y, 0.0) + m * f / len(a)
            res = {}
            for x, m in out.items():                    # then sideways
                stay = 1.0
                for w in ("left", "right"):
                    s = self.side(x, w)
                    if s and lat[w] > 0:
                        res[s] = res.get(s, 0.0) + m * lat[w]
                        stay -= lat[w]
                res[x] = res.get(x, 0.0) + m * stay
            return res

        def model(bel):
            out = {}
            for c, m in bel.items():
                for c2, q in one(c).items():
                    out[c2] = out.get(c2, 0.0) + m * q
            keep = {c: m for c, m in out.items() if m >= EPS}
            z = sum(keep.values())
            return {c: m / z for c, m in sorted(keep.items())} if z > 0 else bel
        return model

    def mixture(self, p, speed, dt):
        ks = {i: self.kernel(i, speed, dt) for i in INTENTS}

        def model(bel, ticks=1):
            for _ in range(int(ticks)):
                out = {}
                for i in INTENTS:
                    if p.get(i, 0.0) <= 0:
                        continue
                    for c, m in ks[i](bel).items():
                        out[c] = out.get(c, 0.0) + p[i] * m
                z = sum(out.values())
                bel = {c: m / z for c, m in sorted(out.items())} if z > 0 else bel
            return bel
        return model

    # ── the cycle ──
    def cycle(self, detections, visible=(), ego=None, save=True):
        """One tick: every track predicted under its intent mixture (the alive decay on the unseen), then the
        DETECTIONS [{class, lane, s, speed}] associated through the gate and folded in (a new one a new track at its
        class's prior), each seen track's intent updated from its displacement since last seen, the VISIBLE cells
        with nothing detected negative evidence. EGO {lane, s, speed, route}: the ego's state. → changed."""
        d = self.load()
        dt = d["dt"]
        d["clock"] = d.get("clock", 0) + 1
        if ego is not None:
            d["ego"] = dict(ego)
            d["agent"]["at"] = cell(ego["lane"], ego["s"])
        for t in sorted(d["belief"]):                   # predict
            if not d["belief"][t]:
                continue
            m = self.mixture(d["intent"][t], d["speed"].get(t, 0.0), dt)
            d["belief"][t] = m(d["belief"][t])
        sightings = [(x["class"], cell(x["lane"], x["s"])) for x in detections]
        last, clock = d["last_seen"], d["clock"]

        def radius(t):
            gap = clock - (last.get(t) or (None, clock))[1]
            return 1 + int(math.ceil(max(1.0, d["speed"].get(t, 0.0)) * dt * max(1, gap) / BIN * 1.5))
        kinds = {t: d["things"][t]["class"] for t in d["things"]}
        sub = {"things": d["things"], "belief": d["belief"]}
        named = bayes.associate(sub, sightings, self.neighbours, radius, kind_of=lambda t: kinds[t]) if sightings else []
        seen = {}
        for (t, c), x in zip(named, detections):
            if t not in d["things"]:
                d["things"][t] = {"class": x["class"], "of": x["class"]}
                d["intent"][t] = prior(x["class"], d["priors"])
                kinds[t] = x["class"]
            c1, t0 = last.get(t) or (None, clock)
            if c1 is not None and clock > t0:            # the intent from the displacement since last seen
                p = d["intent"][t]
                sp = d["speed"].get(t, x.get("speed", 0.0))
                post = {}
                for i in INTENTS:
                    k = self.kernel(i, sp, dt)
                    bel = {c1: 1.0}
                    for _ in range(clock - t0):
                        bel = k(bel)
                    post[i] = p.get(i, 0.0) * (bel.get(c, 0.0) + FLOOR) ** TEMPER
                z = sum(post.values())
                if z > 0:
                    d["intent"][t] = {i: round(v / z, 6) for i, v in post.items()}
            d["belief"][t] = {c: 1.0}
            d["speed"][t] = float(x.get("speed", d["speed"].get(t, 0.0)))
            d["exists"][t] = min(bayes.L_MAX if hasattr(bayes, "L_MAX") else 4.0, d["exists"].get(t, 0.0) + 1.0)
            last[t] = [c, clock]
            seen[t] = c
        for t in sorted(d["belief"]):                   # negative evidence and the alive decay on the unseen
            if t in seen or not d["belief"][t]:
                continue
            gone = [c for c in d["belief"][t] if c in set(visible)]
            if gone:
                bel = {c: m for c, m in d["belief"][t].items() if c not in set(visible)}
                z = sum(bel.values())
                d["belief"][t] = {c: m / z for c, m in bel.items()} if z > 0 else {}
            d["exists"][t] = d["exists"].get(t, 0.0) - ALIVE[0]
            if d["exists"][t] < ALIVE[1] or not d["belief"][t]:
                d["belief"][t] = {}
                d.setdefault("gone", []).append(t)
        d["_seen"] = sorted(seen)
        if save:
            self.save()
        return True

    # ── the readings ──
    def danger(self, ego, t, vt, dt):
        """The ego's danger region at tick T: its route's cells from its predicted s to s + the RSS safe distance
        against a mover at speed VT ahead of it (situation.safe_same_dir: the ego following). → set of cells."""
        route = ego.get("route") or [ego["lane"]]
        v = ego.get("speed", 0.0)
        s = ego["s"] + v * dt * t
        dyn_e = dynamics_for(ego.get("class", "passenger"), v=v, ego=True)
        dyn_o = dynamics_for("passenger", v=vt)
        reach = safe_same_dir(dyn_e, dyn_o) + 1.0
        out, i, lane = set(), 0, route[0]
        while lane is not None and lane in self.lanemap.lanes:   # walk the route from s to s + reach
            L = self.lanemap.lanes[lane].length
            if s >= L:
                s -= L
                i += 1
                lane = route[i] if i < len(route) else None
                continue
            a, b = s, s + reach
            for k in range(int(a // BIN), int(min(b, L) // BIN) + 1):
                out.add("%s|%d" % (lane, k))
            if b <= L:
                break
            reach -= L - s
            s, i = 0.0, i + 1
            lane = route[i] if i < len(route) else None
        return out

    def predict_table(self, h, d=None):
        """The per-tick table for the instrument (see the module's doc): {"h", "unit": "tick", "tracks", "roles",
        "intent": {track: {I: p}}, "rows": [{"closing(T,I)": hazard} per tick], "marginals": {"danger": [[P in the
        danger region at t] per track]}}."""
        d = d or self.load()
        ego, dt = d.get("ego"), d["dt"]
        names = sorted(t for t in d["belief"] if d["belief"][t])
        inv = {h_: r for r, h_ in (d.get("binding") or {}).items()}
        rows = [{} for _ in range(int(h))]
        marg = {"danger": []}
        if ego is None:
            return {"h": int(h), "unit": "tick", "tracks": names, "roles": {}, "intent": {}, "rows": rows, "marginals": marg}
        dangers = [self.danger(ego, t + 1, 0.0, dt) for t in range(int(h))]
        for n in names:
            sp = d["speed"].get(n, 0.0)
            for i in INTENTS:
                k = self.kernel(i, sp, dt)
                bel = dict(d["belief"][n])
                for t in range(int(h)):
                    nxt = k(bel)
                    hz = sum(m for c, m in nxt.items() if c in dangers[t])
                    z = sum(nxt.values())
                    rows[t]["closing(%s,%s)" % (inv.get(n, n), i)] = round(hz / z, 4) if z > 0 else 0.0
                    keep = {c: m for c, m in nxt.items() if c not in dangers[t]}
                    zk = sum(keep.values())
                    bel = {c: m / zk for c, m in keep.items()} if zk > 0 else nxt
        mix = {n: self.mixture(d["intent"][n], d["speed"].get(n, 0.0), dt) for n in names}
        bels = {n: dict(d["belief"][n]) for n in names}
        for t in range(int(h)):
            bels = {n: mix[n](bels[n]) for n in names}
            marg["danger"].append([round(sum(m for c, m in bels[n].items() if c in dangers[t]), 4) for n in names])
        roles = {r: n for r, n in (d.get("binding") or {}).items() if n in names}
        return {"h": int(h), "unit": "tick", "tracks": names, "roles": roles, "rows": rows, "marginals": marg,
                "intent": {n: {i: round(v, 4) for i, v in d["intent"][n].items()} for n in names}}
