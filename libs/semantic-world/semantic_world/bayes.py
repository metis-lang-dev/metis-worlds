"""bayes — the belief over where each thing is, as pure steps over the store's document `d`:

- predict(d, dt, models, alive): the motion step before an observation, dt in turns (a float), a model per
  mover — still (identity: a
  room's things move only by the robot's hand, a peaceful beast holds), walk (a random walk over the adapter's
  graph, biased toward a place: a hostile beast comes for the ego; a fractional speed or dt mixes in the next
  step with its probability) — and the alive decay: a mover's `exists` falls by
  a rate per turn (a sighting raises it again), and below the floor its belief is dropped (gone).
- seen(d, thing, place): an observation's likelihood 1 at the place it is seen in, 0 elsewhere: the posterior
  collapses; place None (in hand) drops the belief.
- missed(d, place, seen, prior): the three-way sensor model's negative evidence — a place looked into without a
  thing it may be in: 0 there, the rest renormalized; nothing left, the prior (an adapter's function, less the places
  looked into). A place not looked into is occluded: its belief is unchanged. Exists falls by log(1 − p), p the
  mass the place held.
- exists[thing]: log-odds that the thing is in the world at all (SuperMap's: confirmed +, disappeared −, occluded
  unchanged), clamped to ±L_MAX; a reading for ports, no rule reads it yet."""
import math

L_HIT, L_MISS, L_MAX = 0.85, 0.4, 4.0     # L_MISS: the constant miss before step 3b (missed weighs the evidence now)


def predict(d, dt=1, models=None, alive=None):
    """The motion step: for every thing with a model, belief ← model(belief, dt). dt is time in turns, a float (a
    road's clock: 0.3 of a turn; 0 is the identity). alive (rate, floor): each modelled thing's exists falls by
    rate × dt; below the floor its belief is dropped and it is recorded `gone`. → changed. Identity without
    models."""
    changed = False
    for thing, model in sorted((models or {}).items(), key=lambda x: x[0]):
        bel = d["belief"].get(thing)
        if bel:
            new = model(dict(bel), dt)
            if new != bel:
                d["belief"][thing] = new
                changed = True
        if alive and thing in d["belief"]:
            rate, floor = alive
            _exists(d, thing, -rate * dt)
            if d["exists"][thing] < floor:
                d["belief"].pop(thing)
                d.setdefault("gone", []).append(thing)
                changed = True
    return changed


def still(bel, dt):
    """A thing that does not move by itself (identity)."""
    return bel


def walk(neighbours, toward=None, stay=0.25, bias=1.0, speed=1, eps=1e-4):
    """A random walk over a graph: NEIGHBOURS(place) → the places one step away. Per step each place keeps STAY of
    its mass and spreads the rest over its neighbours, weighted exp(−BIAS × TOWARD(n)) — TOWARD(place) a distance
    to what draws it (the ego, for a hostile; None: a uniform wander); SPEED steps a turn; mass below EPS dropped
    (renormalized). A float dt: speed × dt = n whole steps and a fraction f, the belief after n steps mixed with
    one step more, (1 − f) · bel + f · step(bel) (the step happened with probability f). → model(belief, dt)."""
    import math

    def model(bel, dt):
        n, f = divmod(max(0.0, speed * dt), 1.0)
        for _ in range(int(n)):
            bel = one(bel)
        if f > 1e-9:
            more = one(bel)
            mixed = {p: (1 - f) * bel.get(p, 0.0) + f * more.get(p, 0.0) for p in set(bel) | set(more)}
            keep = {p: m for p, m in mixed.items() if m >= eps}
            z = sum(keep.values())
            bel = {p: m / z for p, m in sorted(keep.items())} if z > 0 else bel
        return bel

    def one(bel):
        """One step of the walk."""
        new = {}
        for p, m in bel.items():
            ns = neighbours(p)
            if not ns:
                new[p] = new.get(p, 0.0) + m
                continue
            new[p] = new.get(p, 0.0) + m * stay
            ws = [math.exp(-bias * toward(n)) if toward else 1.0 for n in ns]
            z = sum(ws)
            for n, w in zip(ns, ws):
                new[n] = new.get(n, 0.0) + m * (1 - stay) * w / z
        keep = {p: m for p, m in new.items() if m >= eps}
        z = sum(keep.values())
        return {p: m / z for p, m in sorted(keep.items())} if z > 0 else bel
    return model


def _exists(d, thing, delta):
    ex = d.setdefault("exists", {})
    ex[thing] = round(max(-L_MAX, min(L_MAX, ex.get(thing, 0.0) + delta)), 6)


def seen(d, thing, place):
    """THING seen at PLACE (None: in hand). → changed (its belief or its `in` moved)."""
    t = d["things"][thing]
    post = {place: 1.0} if place else {}
    changed = False
    if t["in"] != place or d["belief"].get(thing) != post:
        t["in"], changed = place, True
        if post:
            d["belief"][thing] = post
        else:
            d["belief"].pop(thing, None)
    _exists(d, thing, L_HIT)
    return changed


def missed(d, place, seen_at, prior):
    """PLACE looked into: every thing believed there and not seen there (SEEN_AT: {thing: place}) loses it. Its
    exists falls by the evidence the look was: log(1 − p), p the mass it had there (a sure sensor: a miss where it
    was surely is the full L_MAX, a miss where it may have been by 1% is −0.01) — a constant per look let many
    looks at a belief's tails declare a thing gone that was believed elsewhere. → the things that lost it, in
    order."""
    out = []
    for thing in sorted(d["belief"]):
        bel = d["belief"][thing]
        if bel.get(place, 0) > 0 and seen_at.get(thing) != place:
            d.setdefault("looked", {}).setdefault(thing, []).append(place)
            total = sum(bel.values())
            frac = bel.pop(place) / total if total > 0 else 1.0
            z = sum(bel.values())
            d["belief"][thing] = {x: q / z for x, q in bel.items()} if z > 0 else prior(thing)
            _exists(d, thing, max(-L_MAX, math.log(max(1e-12, 1 - frac))))
            out.append(thing)
    return out


def normalized(bel, among):
    """The belief over AMONG only, normalized (1.0 flat when it holds none of them): → {place: p}."""
    z = sum(p for r, p in bel.items() if r in among)
    return {r: (bel.get(r, 0.0) / z if z > 0 else 1.0) for r in among}


# ── the reachable set: RSS's worst case as a motion model (semantic-world step 3a, the user's amendment) ──

def travel(v, dt, accel=0.0, brake=None, vmax=None):
    """The distance a mover at speed V covers in DT under a constant ACCEL (≥ 0: speeding up, capped at VMAX) or,
    with BRAKE (> 0), braking from V until it stops: the two ends of RSS's kinematic interval. → a distance ≥ 0."""
    if brake:
        t = min(dt, v / brake) if brake > 0 else dt
        return max(0.0, v * t - 0.5 * brake * t * t)
    if vmax is not None and accel > 0 and v + accel * dt > vmax:
        t = max(0.0, (vmax - v) / accel)
        return v * t + 0.5 * accel * t * t + vmax * (dt - t)
    return v * dt + 0.5 * accel * dt * dt


def interval(dt, vmin=0.0, vmax=1.0, accel=0.0, brake=0.0, vcap=None):
    """RSS's kinematic interval over DT for a mover whose speed lies in [VMIN, VMAX]: the least distance (from VMIN,
    braking at BRAKE; no braking: VMIN · DT) and the most (from VMAX, accelerating at ACCEL up to VCAP). Car
    dynamics: a road's speeds and bounds; a dungeon's beast: speed in cells a turn, no accel, it may stop
    (vmin 0). → (lo, hi)."""
    lo = travel(vmin, dt, brake=brake) if brake else vmin * dt
    hi = travel(vmax, dt, accel=accel, vmax=vcap)
    return lo, max(lo, hi)


def distances(neighbours, start, limit, length=None):
    """Graph distance from START to every place within LIMIT (LENGTH(a, b): an edge's length, else 1): {place: d}."""
    import heapq
    dist, q = {start: 0.0}, [(0.0, start)]
    while q:
        g, p = heapq.heappop(q)
        if g > dist[p]:
            continue
        for n in neighbours(p):
            g2 = g + (length(p, n) if length else 1.0)
            if g2 <= limit + 1e-9 and g2 < dist.get(n, 1e18):
                dist[n] = g2
                heapq.heappush(q, (g2, n))
    return dist


def reachable(neighbours, vmin=0.0, vmax=1.0, accel=0.0, brake=0.0, vcap=None, length=None, eps=1e-4):
    """The reachable-set motion model: every place's mass spread evenly over the places inside the mover's
    kinematic interval for dt (`interval`: speed range × time with braking and acceleration bounds, RSS's worst
    case) along the adapter's graph (NEIGHBOURS; LENGTH an edge's length, else one: a cell). Not a walk biased
    toward a place: no intent assumed, only what the body allows, so it is the set a safety check must clear.
    → model(belief, dt)."""
    def model(bel, dt):
        lo, hi = interval(dt, vmin, vmax, accel, brake, vcap)
        new = {}
        for p, m in bel.items():
            ring = [q for q, g in distances(neighbours, p, hi, length).items() if g >= lo - 1e-9]
            ring = ring or [p]
            for q in ring:
                new[q] = new.get(q, 0.0) + m / len(ring)
        keep = {q: m for q, m in new.items() if m >= eps}
        z = sum(keep.values())
        return {q: m / z for q, m in sorted(keep.items())} if z > 0 else bel
    return model


def mass_within(bel, neighbours, target, reach, length=None):
    """The belief's mass on the places from which TARGET is within REACH (a mover's worst-case distance over a
    horizon): P(it can be at TARGET by then), the `reach(B)` / P(hazard) reading."""
    near = distances(neighbours, target, reach, length)
    return round(sum(p for q, p in bel.items() if q in near), 6)


# ── the association gate: which instance a sighting of a kind is (SuperMap's reprojection prior) ──

def associate(d, sightings, neighbours, radius, kind_of=None):
    """SIGHTINGS [(kind, place)] of things that look alike (two newts read `monster(newt, …)` both) matched to the
    instances of their kind: an instance's prior for a sighting is its predicted mass within RADIUS(instance)
    of the place (the motion model's belief: the reprojection prior), the pairs taken greedily, likeliest first;
    a sighting no instance has mass near is a new instance (kind, kind_2, kind_3, …). KIND_OF(thing) → its kind
    (default: d["things"][t]["of"], else the name). → [(instance, place)] in SIGHTINGS' order; new instances are
    entered in d["things"] (with "of") by the caller's grow."""
    kind_of = kind_of or (lambda t: d["things"][t].get("of", t))
    cands = {}
    for t in sorted(d["things"]):
        cands.setdefault(kind_of(t), []).append(t)
    pairs = []
    for i, (kind, place) in enumerate(sightings):
        for t in cands.get(kind, ()):
            bel = d["belief"].get(t) or {}
            near = distances(neighbours, place, radius(t)) if bel else {}
            score = sum(p for q, p in bel.items() if q in near)
            if score > 0:
                pairs.append((-score, i, t))
    out, used, taken = [None] * len(sightings), set(), set()
    for _, i, t in sorted(pairs):
        if i not in taken and t not in used:
            out[i] = t
            taken.add(i)
            used.add(t)
    names = set(d["things"])
    for i, (kind, place) in enumerate(sightings):
        if out[i] is None:
            free = [t for t in cands.get(kind, ()) if t not in used and not d["belief"].get(t)]
            if free:                                       # an instance with no belief left (lost): the sighting is it
                out[i] = free[0]
            else:
                n, name = 1, kind
                while name in names:
                    n += 1
                    name = "%s_%d" % (kind, n)
                out[i] = name
                names.add(name)
            used.add(out[i])
    return list(zip(out, [p for _, p in sightings]))
