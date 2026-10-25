"""core — the semantic map's cycle, shared by every adapter (semantic-world step 2, the architect's condition (a)):

    cycle(atoms, dt)   predict (the movers' motion) → observe (the evidence folded into the belief) → re-project
    sync(reading, counts, owned)   the facts between bound roles as do-lines on a live session
    role_reading(reading)          the world's facts in roles, with the adapter's own (place facts, believed facts)

The algorithm is the room's of semantic-map step 3, in its order: the ego's place and hand; in view mode the
places seen into recorded, each thing seen collapsed (a new one grows the map), the adapter's resolution (a wanted
kind becomes the instance seen), then every place seen into is negative evidence for what is believed there and not
seen (the prior again when nothing is left; `look` marks it); a change re-projects the binding, stably. In `all`
mode (the world tells every fact) each thing named is collapsed, with no negative evidence.

An adapter supplies (class attributes and hooks):
    OBJECT_ROLES, LOCATED      the thing role family; the reading's predicates that place a thing (view mode reads the belief)
    place_roles(k), location_roles(k), named_roles()   the place / location role families, the roles said by name
    evidence(d, atoms) -> (at, held, {thing: place}, changed)   the ego and what is seen, from the world's atoms
    visible(d) -> [places]     the places the ego sees into now (view mode)
    prior(thing) -> {place: p} the belief when nothing is left (view mode)
    grow(d, thing) -> entry    a thing never seen
    resolve(d, thing) -> bool  after a sighting (a wanted kind resolved)
    looked_at(d, place, seen) -> bool   after a place is seen into
    reproject(d)               the stable re-projection after a change (view mode)
    believed(d, inv), place_facts(d, inv) -> {atom: n}   the adapter's facts in roles"""
from . import bayes, ports
from .store import Store


def _top(bel, n=3):
    """A belief's N likeliest places, rounded: [[place, p], …]."""
    return [[r, round(p, 3)] for r, p in sorted(bel.items(), key=lambda x: (-x[1], x[0]))[:n]]


class SemanticMap(Store):
    OBJECT_ROLES = ()
    LOCATED = ()

    def __init__(self, path, journal=None):
        super().__init__(path, path + ".journal.jsonl" if journal is None else (journal or None))

    # ── the adapter's hooks (the defaults: a world that names every fact, no extra facts) ──
    def place_roles(self, k):
        return ()

    def location_roles(self, k):
        return ()

    def named_roles(self, k):
        return set(self.OBJECT_ROLES) | set(self.place_roles(k))

    def evidence(self, d, atoms):
        raise NotImplementedError

    def visible(self, d):
        return []

    def prior(self, thing):
        return {}

    def grow(self, d, thing):
        return {"in": None}

    def resolve(self, d, thing):
        return False

    def looked_at(self, d, place, seen):
        return False

    def reproject(self, d):
        pass

    def believed(self, d, inv):
        return {}

    def place_facts(self, d, inv):
        return {}

    # ── the cycle ──
    def cycle(self, atoms, dt=1, models=None, alive=None, save=True):
        """One turn's map work: predict(dt) with the movers' models (and the alive decay), then observe(atoms). →
        changed."""
        d = self.load()
        moved = bayes.predict(d, dt, models, alive)
        if moved and save:                             # the movers' predicted beliefs, before the sighting (the journal)
            self.log("predict", dt=dt, belief={t: _top(d["belief"].get(t) or {}) for t in sorted(models or {})},
                     gone=list(d.get("gone", ())))
        return self.observe(atoms, save=save, predicted=moved)

    def observe(self, atoms, save=True, predicted=False):
        """What the ego sees now folded into the map (view mode: through the adapter's visibility, with negative
        evidence; else every fact the world names). → changed."""
        d = self.load()
        atoms = set(atoms)
        at, held, named, changed = self.evidence(d, atoms)
        changed = changed or predicted
        if (at, held) != (d["agent"]["at"], d["agent"]["holding"]):
            d["agent"].update(at=at, holding=held)
            changed = True
        if d.get("view"):
            moved = self._observe_view(d, named, held)
            if moved and d["binding"]:
                self.reproject(d)
            if (changed or moved) and save:
                self.save()
                self.log("observe", at=d["agent"]["at"], holding=d["agent"]["holding"], look=d.get("look"), binding=d["binding"] if moved else None)
            return changed or moved
        for o in sorted(set(named) | ({held} if held else set())):
            if o not in d["things"]:
                d["things"][o] = self.grow(d, o)
            changed = bayes.seen(d, o, named.get(o)) or changed
        if changed and save:
            self.save()
            self.log("observe", at=d["agent"]["at"], holding=d["agent"]["holding"])
        return changed

    def _observe_view(self, d, named, held):
        changed = False
        vis = self.visible(d)
        for r in vis:                                  # the places seen into (the page lights them)
            if r not in d.setdefault("seen", []):
                d["seen"].append(r)
                changed = True
        seen = {o: r for o, r in named.items() if r in vis}
        if held:
            seen[held] = None
        for o, r in sorted(seen.items(), key=lambda x: x[0]):
            if o not in d["things"]:                   # a thing never seen: the map grows
                d["things"][o] = self.grow(d, o)
                changed = True
            changed = bayes.seen(d, o, r) or changed
            d["looked"].pop(o, None)                   # a sighting supersedes the places it was not in
            changed = self.resolve(d, o) or changed
        for r in vis:                                  # looked into: what is not there is not there (negative evidence)
            if bayes.missed(d, r, seen, self.prior):
                d["look"] = r
                changed = True
            changed = self.looked_at(d, r, seen) or changed
        return changed

    def gone(self, thing, why):
        """THING is out of the world, the world says so (a beast killed, an item used up): its belief dropped and
        recorded `gone`, its exists at the floor — no motion model carries it any more. → changed."""
        d = self.load()
        if thing not in d["things"] or thing in d.get("gone", ()):
            return False
        d["belief"].pop(thing, None)
        d.setdefault("gone", []).append(thing)
        bayes._exists(d, thing, -2 * bayes.L_MAX)
        self.save()
        self.log("gone", thing=thing, why=why)
        return True

    def lost(self, thing):
        """No place left to look for THING: the belief is empty and it is not in hand (view mode)."""
        d = self.load()
        return bool(d.get("view")) and thing in d["things"] and not d["belief"].get(thing) \
            and d["agent"]["holding"] != thing

    # ── the binding, through the ports ──
    def binding(self):
        return dict(self.load()["binding"])

    def roles(self):
        k = self.load()["k"]
        return set(self.OBJECT_ROLES) | set(self.place_roles(k)) | set(self.location_roles(k))

    def handle(self, role, binding=None):
        """The world name a role is bound to (None when unbound); a constant that is no role is itself. binding: a
        domain's own (frozen for its activation) over the map's."""
        return (binding if binding is not None else self.binding()).get(role) if role in self.roles() else role

    def role_of(self, handle):
        return {h: r for r, h in self.binding().items()}.get(handle)

    def role_reading(self, reading, binding=None):
        """The world's facts (atom → count, its names) over the bound entries only, in roles, with the adapter's
        facts (view mode: where a bound thing is comes from the belief, not the world). binding: a domain's own."""
        d = self.load()
        if binding is not None:
            d = dict(d, binding=binding)
        inv = {h: r for r, h in d["binding"].items()}
        out = {}
        if d.get("view"):
            objs = {h for r, h in d["binding"].items() if r in self.OBJECT_ROLES}
            reading = {a: n for a, n in reading.items()
                       if not (a.split("(")[0] in self.LOCATED and ports.args(a)[0] in objs)}
            out.update(self.believed(d, inv))
        out.update(ports.translate(reading, d["binding"]))
        out.update(self.place_facts(d, inv))
        return out

    def sync(self, reading, counts, owned, binding=None):
        """The do-lines that bring a live session's facts (COUNTS) to READING in roles (the predicates OWNED only)."""
        return ports.sync_diff(self.role_reading(reading, binding), counts, owned)

    def names(self, binding=None):
        """name(role, thing) as data: the named roles and what they are bound to."""
        k = self.load()["k"]
        return ports.names(binding if binding is not None else self.binding(), self.named_roles(k))

    def belief(self, obj_role, place_role):
        """The belief that the role-bound thing is at the role-bound place, normalized over the bound places (a
        weight port's reading): 1.0 for a single believed place, 1.0 when the map has no belief for it."""
        d = self.load()
        b = d["binding"]
        bel = d["belief"].get(b.get(obj_role), {})
        bound = {b[r] for r in self.place_roles(d["k"]) if b.get(r)}
        z = sum(p for r, p in bel.items() if r in bound)
        return bel.get(b.get(place_role), 0.0) / z if z > 0 else 1.0
