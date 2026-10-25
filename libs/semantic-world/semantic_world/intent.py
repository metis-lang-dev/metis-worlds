"""intent — a mover's categorical INTENT belief, updated from its observed displacement (nav-belief s-794cf4c1 step 1).

A track carries p over INTENTS = (hostile, wandering, fleeing), one motion model per intent over the passable graph:
- hostile: toward the ego (bayes.walk biased by the distance to it along the map, rarely holding);
- wandering: a uniform random walk (no draw);
- fleeing: away from the ego (the same walk with the distance's sign turned).
UPDATE (seen at C2, last seen at C1 a gap of G turns ago): p(i) ∝ p(i) · L(i), L(i) the model's mass at C2 after G
turns from C1, tempered (TEMPER; a floor keeps every intent possible: a model is never certain). PREDICT (unseen): the position belief
moves under the MIXTURE Σ p(i) · model(i), so its support spreads along the corridor graph as the turns pass.
The levels and the per-step table are the host's to emit (semantic_world.grid); nothing here names a world.

    prior(species, table)                → {intent: p}   (uniform for a species the table does not know)
    models(neighbours, dist, speed)       → {intent: model(belief, dt)}
    update(p, c1, c2, gap, models)        → {intent: p}
    mixture(p, models)                    → model(belief, dt)
    level(p)                              → "hostile_sure" | "hostile_maybe" | None
"""
from . import bayes

INTENTS = ("hostile", "wandering", "fleeing")
HOSTILE_SURE, HOSTILE_MAYBE = 0.7, 0.3          # the intent level's thresholds (named; the host logs them)
FLOOR = 0.02                                   # every model keeps this much likelihood (none is ever ruled out)
TEMPER = 0.3                                   # the likelihood's power: the models are NetHack's movement approximated, so a
                                               # sighting counts for less (a chaser sure after 4 sightings, a random walk
                                               # of 12 steps ever sure 3% of the time; at 1.0: 2 and 16%)
MOTION = {"hostile": {"stay": 0.1, "bias": 3.0},        # the grid's CHASE: a step closer e³ likelier than one aside
          "wandering": {"stay": 0.3, "bias": 0.0},      # a uniform walk, holding a third of the time
          "fleeing": {"stay": 0.2, "bias": 2.0}}        # away from the ego


def prior(species, table=None):
    """The species' prior over INTENTS from TABLE {species: {intent: p}}; uniform when unknown. Normalized."""
    p = dict((table or {}).get(species) or {i: 1.0 for i in INTENTS})
    p = {i: max(0.0, float(p.get(i, 0.0))) for i in INTENTS}
    z = sum(p.values()) or 1.0
    return {i: v / z for i, v in p.items()}


def models(neighbours, dist, speed=1.0, motion=None):
    """One bayes.walk per intent over NEIGHBOURS, DIST(cell) the steps to the ego along the map (None: no ego: every
    model a uniform walk), SPEED cells a turn. → {intent: model(belief, dt)}."""
    motion = motion or MOTION
    out = {}
    for i in INTENTS:
        m = motion[i]
        if dist is None or not m["bias"]:
            toward = None
        elif i == "fleeing":
            toward = (lambda c, _d=dist: -_d(c))
        else:
            toward = dist
        out[i] = bayes.walk(neighbours, toward, stay=m["stay"], bias=m["bias"] or 1.0, speed=speed)
    return out


def likelihood(model, c1, c2, gap):
    """The model's mass at C2 after GAP turns from C1 (C1 = C2 and GAP 0: 1)."""
    if gap <= 0:
        return 1.0 if c1 == c2 else 0.0
    return model({c1: 1.0}, gap).get(c2, 0.0)


def update(p, c1, c2, gap, ms, floor=FLOOR, temper=TEMPER):
    """The intent posterior after a sighting at C2, C1 the last sighting GAP turns before: p(i) ∝ p(i) · (L(i) + floor)^temper.
    No previous sighting (C1 None): p unchanged."""
    if c1 is None or gap <= 0:
        return dict(p)
    post = {i: p.get(i, 0.0) * (likelihood(ms[i], c1, c2, gap) + floor) ** temper for i in INTENTS}
    z = sum(post.values())
    return {i: v / z for i, v in post.items()} if z > 0 else dict(p)


def mixture(p, ms):
    """The position model under the intent belief: Σ p(i) · model(i)(belief, dt), renormalized."""
    def model(bel, dt):
        out = {}
        for i in INTENTS:
            w = p.get(i, 0.0)
            if w <= 0:
                continue
            for c, m in ms[i](dict(bel), dt).items():
                out[c] = out.get(c, 0.0) + w * m
        z = sum(out.values())
        return {c: m / z for c, m in sorted(out.items())} if z > 0 else bel
    return model


def level(p, sure=HOSTILE_SURE, maybe=HOSTILE_MAYBE):
    """The hostile intent's level: hostile_sure at p ≥ SURE, hostile_maybe at p ≥ MAYBE, else None."""
    h = p.get("hostile", 0.0)
    return "hostile_sure" if h >= sure else ("hostile_maybe" if h >= maybe else None)
