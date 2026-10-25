"""bayes — the belief over where each thing is, as pure steps over the store's document `d`:

- predict(d, dt, models, alive): the motion step before an observation, a model per mover — still (identity: a
  room's things move only by the robot's hand, a peaceful beast holds), walk (a random walk over the adapter's
  graph, biased toward a place: a hostile beast comes for the ego) — and the alive decay: a mover's `exists` falls by
  a rate per turn (a sighting raises it again), and below the floor its belief is dropped (gone).
- seen(d, thing, place): an observation's likelihood 1 at the place it is seen in, 0 elsewhere: the posterior
  collapses; place None (in hand) drops the belief.
- missed(d, place, seen, prior): the three-way sensor model's negative evidence — a place looked into without a
  thing it may be in: 0 there, the rest renormalized; nothing left, the prior (an adapter's function, less the places
  looked into). A place not looked into is occluded: its belief is unchanged.
- exists[thing]: log-odds that the thing is in the world at all (SuperMap's: confirmed +, disappeared −, occluded
  unchanged), clamped to ±L_MAX; a reading for ports, no rule reads it yet."""
L_HIT, L_MISS, L_MAX = 0.85, 0.4, 4.0


def predict(d, dt=1, models=None, alive=None):
    """The motion step: for every thing with a model, belief ← model(belief, dt). alive (rate, floor): each modelled
    thing's exists falls by rate × dt; below the floor its belief is dropped and it is recorded `gone`. → changed.
    Identity without models."""
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
    (renormalized). → model(belief, dt)."""
    import math

    def model(bel, dt):
        for _ in range(max(0, int(round(speed * dt)))):
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
            bel = {p: m / z for p, m in sorted(keep.items())} if z > 0 else bel
        return bel
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
    """PLACE looked into: every thing believed there and not seen there (SEEN_AT: {thing: place}) loses it. → the
    things that lost it, in order."""
    out = []
    for thing in sorted(d["belief"]):
        bel = d["belief"][thing]
        if bel.get(place, 0) > 0 and seen_at.get(thing) != place:
            d.setdefault("looked", {}).setdefault(thing, []).append(place)
            del bel[place]
            z = sum(bel.values())
            d["belief"][thing] = {x: p / z for x, p in bel.items()} if z > 0 else prior(thing)
            _exists(d, thing, -L_MISS)
            out.append(thing)
    return out


def normalized(bel, among):
    """The belief over AMONG only, normalized (1.0 flat when it holds none of them): → {place: p}."""
    z = sum(p for r, p in bel.items() if r in among)
    return {r: (bel.get(r, 0.0) / z if z > 0 else 1.0) for r in among}
