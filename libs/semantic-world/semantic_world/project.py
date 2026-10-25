"""project — the binding of a role vocabulary (fixed capacity k per role family) to the world's names.

A program is compiled once over roles; a projection binds them per goal (an adapter ranks what the goal needs) and
re-binds them as the world is seen. Two rules make a re-projection safe on live sessions, where a role sits in
tokens (`goto(p2)`, a detour's `open(p3)`):
- stable: a world name keeps its role while it stays in the working set; the names that left free their slots, the
  new ones take the first free slots (stable_slots);
- frozen at refresh: a domain woken for a goal reads the binding of its activation until its next one (freeze), so
  nothing moves under a rule; the planner reads the store's own."""
import re


def slot_roles(prefix, k):
    return tuple("%s%d" % (prefix, i) for i in range(1, k + 1))


def is_slot(role, prefix="p"):
    return re.fullmatch(r"%s[1-9]\d*" % re.escape(prefix), role) is not None


def stable_slots(binding, keep, candidates, k, prefix="p", bound=()):
    """The PREFIX1..PREFIXk slots after a re-projection: those of BINDING whose world name KEEP(name) holds stay as
    they are; the free ones take CANDIDATES in order (the most needed first), skipping names already kept or in BOUND.
    → {role: name}."""
    kept = {r: h for r, h in binding.items() if is_slot(r, prefix) and keep(h)}
    free = [r for r in slot_roles(prefix, k) if r not in kept]
    taken = set(kept.values()) | set(bound)
    cand = [c for c in candidates if c not in taken]
    return dict(kept, **dict(zip(free, cand)))


def stable_locations(binding, need, k, fixed=("lhere", "ldest"), prefix="l"):
    """The location roles for the locations NEED: a fixed role (lhere, ldest) keeps its location; a slot role of
    BINDING keeps its location while it is needed; the rest take the first free slot roles. → {location: role}."""
    loc_role = {h: r for r, h in binding.items() if r in fixed}
    for r, h in sorted(binding.items()):
        if is_slot(r, prefix) and h in need and h not in loc_role:
            loc_role[h] = r
    used = set(loc_role.values())
    for h in sorted(need):
        if h not in loc_role:
            r = next(x for x in slot_roles(prefix, k) if x not in used)
            loc_role[h] = r
            used.add(r)
    return loc_role


def freeze(binding):
    """A domain's binding for its activation (a copy: the store's moves on, this one does not)."""
    return dict(binding)


def inverse(binding):
    return {h: r for r, h in binding.items()}
