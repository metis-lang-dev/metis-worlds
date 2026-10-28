"""room — the `room` adapter: a household of receptacles and objects (ALFWorld's TextWorld games), over the core
(store, bayes, project, ports). Everything ALFWorld-specific is here: THOR's coordinate names, the world card,
the receptacle kinds (`on` / `in`), the projection's ranking (target, dest, p0, p1..pk, the location roles), the
view mode's prior (ALFWorld's cancontain), the believed / absent / lost facts its task program reads.

The specialists are compiled once over a role vocabulary (the world's capacity.llp); the map lives here, in the
host. Per goal the projection binds roles to the map's entries — target ↦ the object the goal wants, dest ↦ where
it goes, p0 ↦ the receptacle where the robot stands, p1..pk ↦ the places most likely to hold the target (by
belief), the location roles ↦ their places' locations — and the hosts read the world through that binding
(role_reading), so a rebinding is a sync's retract + assert on the live session, never a recompile. One file per
hierarchy, beside the commands log (.map.json): the agent's hosts share a process, the driver runs one per
activation; one writer at a time."""
import re

from . import core, ports
from .project import stable_locations, stable_slots

_WORD = {"_bar_": "|", "_minus_": "-", "_plus_": "+", "_dot_": "."}
CELL = 0.25                                        # metres per grid cell, for the map's readers (web/map.js)


def thor_id(name):
    """A PDDL name → (type, x, y, z): `countertop_bar__minus_01_dot_87_bar__plus_00_dot_96_bar__plus_01_dot_80`
    → ("countertop", -1.87, 0.96, 1.8); None for a name without coordinates."""
    s = name
    for k, v in _WORD.items():
        s = s.replace(k, v)
    parts = s.split("|")
    if len(parts) < 4:
        return None
    try:
        x, y, z = (float(p.replace("_", "")) for p in parts[1:4])
    except ValueError:
        return None
    return parts[0].strip("_"), x, y, z


def spoken(handle):
    """countertop3 → "countertop 3"."""
    m = re.match(r"^(.*?)(\d+)$", handle)
    return "%s %s" % (m.group(1), m.group(2)) if m else handle


def _args(atom):
    return atom[atom.index("(") + 1:-1].split(",")



def _kinds(items, key="type"):
    out = {}
    for it in items:
        out.setdefault(it[key], []).append(it["id"])
    return [{"type": k, "n": len(v), "ids": v} for k, v in sorted(out.items())]


ON = ("countertop", "diningtable", "stoveburner", "shelf", "sidetable", "coffeetable", "sofa", "bed", "desk", "dresser", "toilet", "plate", "ottoman")


def prep(place_type):
    return "on" if place_type in ON else "in"


def world_card(scene, places, things, task):
    """The world card (alf-demo step 3b, the user's ask: a model-card-like page of what this world is
    and what can be asked of it, a dock beside TALK / HIERARCHY / JOURNAL): world-neutral keys —
    title, about (lines), room (place kinds with counts), things (thing kinds with counts), asks
    (say, what), cannot (lines), source — generated from the game's own facts, never typed."""
    pick = [t for t in things if t.get("pickupable")]
    rooms = _kinds(places)
    for r in rooms:
        r["openable"] = any(p["openable"] for p in places if p["type"] == r["type"])
    tk = _kinds(pick)
    target = next((t for t in things if t["id"] in task.get("targets", [])), None)
    dest = next((p for p in places if p["id"] in task.get("dests", [])), None)
    other = next((t for t in pick if t["type"] != (target or {}).get("type")), None)
    elsewhere = next((p for p in places if p["id"] != (dest or {}).get("id") and p["type"] in ("fridge", "countertop", "sinkbasin", "diningtable")), None) or (places[0] if places else None)
    asks = []
    if task.get("text"):
        asks.append({"say": task["text"].rstrip(".").lower() if task["text"] else "", "what": "this game's task: the one that wins the game"})
    if target and dest:
        asks.append({"say": "put the %s %s the %s" % (target["type"], prep(dest["type"]), dest["type"]), "what": "the same task in your words: things by kind, a number when the room has several (\"tomato 2\")"})
    if other and elsewhere:
        asks.append({"say": "put the %s %s the %s" % (other["type"], prep(elsewhere["type"]), elsewhere["type"]), "what": "any thing of the room to any place: the agent does it, or asks first when the task wants something else"})
    room = bool(task.get("room"))                     # alf-tasks: a room, no task of its own — the person gives them, one after another
    if room and other and elsewhere:                  # … a second errand for the card's line: another kind to another place
        second = next((t for t in pick if t["type"] != other["type"]), None)
        there = next((p for p in places if p["type"] not in (elsewhere["type"], second and second.get("at", "").rstrip("0123456789"))
                      and p["type"] in ON + ("fridge", "sinkbasin", "sink", "cabinet", "drawer", "microwave", "garbagecan")), None)
        if second and there:                          # [an errand, it in other words, another]: the card's line says the first and the last
            asks[1:1] = [{"say": "bring the %s to the %s" % (other["type"], elsewhere["type"]), "what": "the same errand in other words"},
                         {"say": "move the %s to the %s" % (second["type"], there["type"]), "what": "another errand: in a room the tasks follow one another"}]
    asks += [{"say": "stop", "what": "the agent stops what it is doing and waits"},
             {"say": "new game", "what": "the same room from its start" + ("" if room else ", the task again")}]
    return {"title": "ALFWorld kitchen %s" % scene,
            "about": ["ALFWorld: a household scene from ALFRED, in text mode (TextWorld): " +
                      ("one room; give the agent a task, then another." if room else "one game is one room and one task."),
                      "The agent moves between places, opens what is closed, takes one thing at a time and puts it in or on a place.",
                      "%d places of %d kinds, %d things you can ask for (%d kinds)." % (len(places), len(rooms), len(pick), len(tk))],
            "room": rooms, "things": tk, "asks": asks,
            "cannot": ["a single step on its own (just go, just open, just pick up): the agent takes whole errands",
                       "a thing that is not in this room, or a place that is not"] +
                      ([] if room else ["another task after the game is won: say \"new game\" first"]),
            "source": "generated from the game's facts by world/semantic_map.py"}


K = 8                                              # the places a projection binds besides dest and p0 (step 1's measure)
OBJECT_ROLES = ("target", "other")


def want_handle(obj):
    """The wanted entry for a target's kind before one is seen (view mode): tomato1 → "tomato"."""
    return re.sub(r"\d+$", "", obj)


def place_roles(k=K):
    return ("dest", "p0") + tuple("p%d" % i for i in range(1, k + 1))


def location_roles(k=K):
    return ("lhere", "ldest") + tuple("l%d" % i for i in range(1, k + 1))


class SemanticMap(core.SemanticMap):
    """places {receptacle: {loc, openable, opened}}, things {object: {in, pickupable}}, belief {object:
    {receptacle: p}}, exists {object: log-odds}, agent {at, holding}, task {targets, dests}, binding {role: handle},
    k — as JSON at `path`, read again when the file changed (another host wrote it); journal: the store's
    (path + ".journal.jsonl" by default; False: none)."""

    OBJECT_ROLES = OBJECT_ROLES
    LOCATED = ("inrecep", "objat")                     # where a thing is: view mode reads the belief instead

    def place_roles(self, k):
        return place_roles(k)

    def location_roles(self, k):
        return location_roles(k)

    @classmethod
    def build(cls, path, static, dyn, targets, dests, k=K, view=False, room=False):
        """The map from the game's facts as the mirror reads them (static and dynamic atoms) and the task's
        resolved targets and dests; no binding yet. view: the robot sees only what stands before it
        (step 3, the architect's RULING 1): the places are known (the room's first look lists them), a
        thing only once seen; the task's wanted type is an entry of its own, believed flat over the places
        that can hold it (ALFWorld's cancontain), until a target is seen. room (alf-tasks): no task of its own — the
        person's goal binds the roles, and in view mode a kind named before it is seen becomes a wanted entry then."""
        m = cls(path)
        st = set(static)
        places = {}
        for a in sorted(st):
            if a.startswith("recat("):
                r, l = _args(a)
                places[r] = {"loc": l, "openable": "openable(%s)" % r in st, "opened": False}
        pick = {_args(a)[0] for a in st if a.startswith("pickupable(")}
        things = {o: {"in": None, "pickupable": True} for o in sorted(pick)}
        # the room's kinds (its objects' and receptacles' types, and its things' names): what a person may name here
        kinds = {_args(a)[1][:-2] if _args(a)[1].endswith("_t") else _args(a)[1] for a in st if a.startswith(("otype(", "rtype("))}
        kinds |= {re.sub(r"\d+$", "", h) for h in list(places) + list(things)}
        m.data = {"places": places, "things": things, "belief": {}, "agent": {"at": None, "holding": None},
                  "task": dict({"targets": sorted(targets), "dests": sorted(dests)}, **({"room": True} if room else {})),
                  "binding": {}, "k": k, "kinds": sorted(kinds)}
        if view:
            types = {}
            for a in st:
                if a.startswith(("otype(", "rtype(")):
                    h, t = _args(a)
                    types[h] = t
            compat = {}
            for a in sorted(st):
                if a.startswith("cancontain("):
                    rt, ot = _args(a)
                    compat.setdefault(ot, []).append(rt)
            m.data.update(view=True, things={}, types=types, compat=compat, pickable=sorted(pick), looked={}, look=None,
                          prior="cancontain" if compat else "flat")
            for o in sorted(targets):                  # the wanted type: one entry per kind the task names
                w = want_handle(o)
                if w not in m.data["things"]:
                    m.data["things"][w] = {"in": None, "pickupable": True, "wanted": types.get(o)}
                    m.data["belief"][w] = m._prior(w)
        m.observe(dyn, save=False)
        m.save()
        return m

    # ── view mode (step 3): what the robot sees, the belief over the rest ──
    def _prior(self, thing):
        """Flat over the places that can hold THING's type (cancontain), less the dests (a target already
        in its dest is seen there, never believed: the task's `already` must not fire on a guess) and the
        places looked into without it; flat over all such places when the game gives no compatibility."""
        d = self.data
        t = d["things"].get(thing, {}).get("wanted") or d["types"].get(thing)
        ok = set(d["compat"].get(t, ())) if d["compat"] else None
        gone = set(d["looked"].get(thing, ()))
        cand = [r for r in sorted(d["places"]) if r not in d["task"]["dests"] and r not in gone
                and (ok is None or d["types"].get(r) in ok)]
        return {r: 1.0 / len(cand) for r in cand} if cand else {}

    def _visible(self, d, at):
        """The receptacles the robot sees into: at its location, open or not openable."""
        return [r for r, p in sorted(d["places"].items()) if p["loc"] == at and (p["opened"] or not p["openable"])]

    # ── the core's hooks: what the room's facts say, and what it does with a sighting ──
    def evidence(self, d, atoms):
        """The ego's location (`at`) and hand (`holds`), the places opened (a room's own: no change for the core),
        and every thing the facts place (`inrecep`)."""
        changed = False
        opened = {_args(a)[0] for a in atoms if a.startswith("opened(")}
        for r, p in d["places"].items():
            if p["opened"] != (r in opened):
                p["opened"], changed = r in opened, True
        at = next((_args(a)[0] for a in atoms if a.startswith("at(")), d["agent"]["at"])
        held = next((_args(a)[0] for a in sorted(atoms) if a.startswith("holds(")), None)
        named = {}
        for a in atoms:
            if a.startswith("inrecep("):
                o, r = _args(a)
                named[o] = r
        return at, held, named, changed

    def visible(self, d):
        return self._visible(d, d["agent"]["at"])

    def prior(self, thing):
        return self._prior(thing)

    def grow(self, d, thing):
        return {"in": None, "pickupable": thing in d["pickable"]} if d.get("view") else {"in": None, "pickupable": False}

    def resolve(self, d, o):
        """A target seen resolves its wanted type (view mode)."""
        changed = False
        for w, wt in list(d["things"].items()):
            if wt.get("wanted") and (o in d["task"]["targets"] or d["task"].get("room")) and d["types"].get(o) == wt["wanted"]:
                del d["things"][w]
                d["belief"].pop(w, None)
                d["looked"].pop(w, None)
                d.setdefault("resolved", {})[w] = o
                changed = True
        return changed

    def looked_at(self, d, r, seen):
        """A place seen into with a target in it is the one just looked into (its role stays bound)."""
        changed = False
        for o, x in seen.items():
            if x == r and d["look"] != r and (o in d["task"]["targets"] or o in d.get("resolved", {}).values()
                                              or (d["task"].get("room") and o == d["binding"].get("target"))):
                d["look"], changed = r, True
        return changed

    def reproject(self, d):
        self._reproject(d)

    def believed(self, d, inv):
        return self._believed(d, inv)

    def place_facts(self, d, inv):
        """Each bound receptacle's place facts: recat(R, L) when its location is bound, openable(R) or notopenable(R)."""
        out = {}
        for role in OBJECT_ROLES:                      # the goal's things: seen, or a kind looked for (view mode, not seen yet)
            h = d["binding"].get(role)
            if h:
                out[("unseen(%s)" if d["things"].get(h, {}).get("wanted") else "seen(%s)") % role] = 1
        for role, h in d["binding"].items():
            p = d["places"].get(h)
            if p is None or role not in place_roles(d["k"]):
                continue
            if p["loc"] in inv:
                out["recat(%s,%s)" % (role, inv[p["loc"]])] = 1
            out[("openable(%s)" if p["openable"] else "notopenable(%s)") % role] = 1
        return out

    # ── the binding ──
    def project(self, obj=None, rec=None, k=None):
        """Bind the roles for a goal naming OBJ (an object) and REC (a receptacle), either may be None:
        target the goal's object when the task wants it (else the task's first target; a held target
        first), other a named object the task does not want (else a held one), dest the goal's receptacle
        when it is a dest (else the task's first dest), p0 the receptacle where the robot stands, p1..pk a
        named non-dest receptacle, then the places by belief of holding the target, then of holding
        `other`; the location roles follow their places (lhere where the robot stands, a location shared
        with a place bound before reuses its role). Saved; → the binding."""
        d = self.load()
        k = k or d["k"]
        targets, dests = d["task"]["targets"], d["task"]["dests"]
        held = d["agent"]["holding"]
        if d.get("view"):
            tgt = self._view_target(d, obj, held)
            # the person named the kind ("a tomato"): any target of it the robot sees will do (_reproject)
            d["task"]["by_kind"] = bool(obj) and (obj in d.get("resolved", {}) or bool(d["things"].get(obj, {}).get("wanted")))
            same = obj and (obj == tgt or d.get("resolved", {}).get(obj) == tgt or want_handle(obj) == want_handle(tgt or ""))
            other = obj if obj and not same else (held if held and held != tgt else None)
        elif obj in targets:
            tgt = obj
            other = obj if obj and obj != tgt else (held if held and held != tgt else None)
        else:
            tgt = held if held in targets else (targets[0] if targets else obj)
            other = obj if obj and obj != tgt else (held if held and held != tgt else None)
        dst = rec if rec in dests else (dests[0] if dests else rec)
        at = d["agent"]["at"]
        here = [r for r, p in sorted(d["places"].items()) if p["loc"] == at]
        p0 = next((r for r in here if r != dst), None)
        ranked = [rec] if rec and rec != dst else []
        for o in (tgt, other):
            bel = d["belief"].get(o) or {}
            ranked += [r for r, p in sorted(bel.items(), key=lambda x: (-x[1], x[0])) if p > 0]
        ranked += here
        slots = []
        for r in ranked:
            if r in d["places"] and r not in (dst, p0) and r not in slots:
                slots.append(r)
        slots = slots[:k]
        b = {"target": tgt, "other": other, "dest": dst, "p0": p0}
        b.update(("p%d" % i, r) for i, r in enumerate(slots, 1))
        locs = {}
        if at:
            locs[at] = "lhere"
        for role, r in [("dest", dst)] + [("p%d" % i, r) for i, r in enumerate(slots, 1)]:
            loc = d["places"].get(r, {}).get("loc") if r else None
            if loc and loc not in locs:
                locs[loc] = "ldest" if role == "dest" else "l" + role[1:]
        b.update((role, loc) for loc, role in locs.items())
        d["binding"] = {r: h for r, h in sorted(b.items()) if h}
        d["k"] = k
        self.save()
        self.log("project", goal=[obj, rec], binding=d["binding"])
        return dict(d["binding"])

    def _view_target(self, d, obj, held):
        """The target in view mode: the instance the person or the goal names once it is seen, its wanted
        type until then (resolved at the first sighting), a held target first."""
        targets, res = d["task"]["targets"], d.get("resolved", {})
        if obj in res:
            return res[obj]
        if obj in targets and obj in d["things"]:
            return obj
        if obj in d["things"] and d["things"][obj].get("wanted"):
            return obj
        if held in targets:
            return held
        seen = [t for t in targets if t in d["things"]]
        if seen:
            return seen[0]
        wanted = [w for w, t in sorted(d["things"].items()) if t.get("wanted")]
        return wanted[0] if wanted else obj

    def _reproject(self, d):
        """The binding after a look (view mode), STABLE: a place bound stays bound to its role (a role is
        in tokens on the live sessions: reached(p1), goto(p2)) while the target may be there or it is
        the place just looked into (its absent fact must reach the task); the places looked into empty
        free their slots, and the belief's next places fill the free slots, the most likely first; the
        target bound to its wanted type becomes the instance seen. Not saved here."""
        b, k = dict(d["binding"]), d["k"]
        tgt = b.get("target")
        if tgt in d.get("resolved", {}):
            b["target"] = tgt = d["resolved"][tgt]
        vis = set(self._visible(d, d["agent"]["at"]))
        if d["task"].get("by_kind") and tgt and not any(r in vis for r in d["belief"].get(tgt) or {}) \
                and d["agent"]["holding"] != tgt:      # a target of the kind asked for, in sight: that one
            kin = [o for o in d["task"]["targets"] if want_handle(o) == want_handle(tgt) and o != tgt
                   and any(r in vis for r, p in (d["belief"].get(o) or {}).items() if p >= 1.0)]
            if kin:
                b["target"] = tgt = kin[0]
                d.setdefault("resolved", {})[want_handle(tgt)] = tgt
        bel = d["belief"].get(tgt) or {}
        obel = d["belief"].get(b.get("other")) or {} if b.get("other") else {}
        slot = lambda r: re.fullmatch(r"p[1-9]\d*", r)
        cand = [r for r, p in sorted(bel.items(), key=lambda x: (-x[1], x[0])) if p > 0 and r in d["places"]]
        slots = stable_slots(b, lambda h: bel.get(h, 0) > 0 or obel.get(h, 0) > 0 or h == d.get("look"), cand, k,
                             bound={b.get("dest"), b.get("p0")})
        need = {d["places"][h]["loc"] for h in slots.values()}
        loc_role = stable_locations(b, need, k)
        b = {r: h for r, h in b.items() if not slot(r) and not re.fullmatch(r"l[1-9]\d*", r)}
        b.update(slots)
        b.update((r, h) for h, r in loc_role.items() if re.fullmatch(r"l[1-9]\d*", r))
        d["binding"] = {r: h for r, h in sorted(b.items()) if h}

    def _believed(self, d, inv):
        """View mode's place facts for the bound things: inrecep(role, p) and objat(role, l) at every bound
        place the belief holds it may be in (a dest only once seen there), absent(role, p) at a bound place
        looked into without it, lost(role) when no place is left to look."""
        out = {}
        vis = set(self._visible(d, d["agent"]["at"]))
        for orole in OBJECT_ROLES:
            h = d["binding"].get(orole)
            if not h or d["agent"]["holding"] == h:
                continue
            bel = d["belief"].get(h) or {}
            gone = set(d["looked"].get(h, ()))
            for prole in place_roles(d["k"]):
                ph = d["binding"].get(prole)
                if not ph:
                    continue
                p = bel.get(ph, 0)
                if p > 0 and prole == "dest" and ph not in vis:
                    out["believed(%s,%s)" % (orole, prole)] = 1    # left there once: `already` waits for a look
                elif p > 0:
                    out["inrecep(%s,%s)" % (orole, prole)] = 1
                    loc = inv.get(d["places"][ph]["loc"])
                    if loc:
                        out["objat(%s,%s)" % (orole, loc)] = 1
                elif ph in gone:
                    out["absent(%s,%s)" % (orole, prole)] = 1
            if orole == "target" and h in d["things"] and not bel:
                out["lost(%s)" % orole] = 1
        return out

    def want_kind(self, d, word):
        """A room in view mode (alf-tasks step 2): WORD, a kind with no number ("apple"), named before one is seen →
        its wanted entry, believed over the places that can hold it (the cancontain prior); None for a thing seen (an
        instance of the kind seen already is resolved to: the person's "the apple" is the one in sight)."""
        if not word or re.search(r"\d$", word) or word in d["places"]:
            return None
        wt = word + "_t"
        seen = sorted(o for o, t in d["things"].items() if not t.get("wanted") and d["types"].get(o) == wt)
        if seen:
            d.setdefault("resolved", {})[word] = seen[0]
            return None
        if word not in d["things"]:
            d["things"][word] = {"in": None, "pickupable": True, "wanted": wt}
            self.data = d
            d["belief"][word] = self._prior(word)
            self.save()
            self.log("want", wanted=word, belief=d["belief"][word])
        return word

    def intent_atom(self, atom):
        """An atom in the room's terms (the mapper's: fetch(tomato1,microwave1)) said in roles: a fetch
        re-projects for its object and receptacle (the person's goal is the projection's goal), any other
        atom naming an unbound thing too; one already in roles is itself."""
        d = self.load()
        name, args = atom.split("(")[0], (_args(atom) if "(" in atom else [])
        if all(a in self.roles() for a in args):
            return atom
        kind = None
        if d.get("view"):                              # a target not seen yet is its wanted type; one resolved is the instance
            res = d.get("resolved", {})
            kind = next((a for a in args if a in res or d["things"].get(a, {}).get("wanted")), None)   # "a tomato": the kind
            args = [res.get(a, a) if a in res else (want_handle(a) if a not in d["things"] and want_handle(a) in d["things"] else a)
                    for a in args]
        if d.get("view") and d["task"].get("room") and name == "fetch" and kind is None:
            kind = self.want_kind(d, args[0])
            args = [d.get("resolved", {}).get(args[0], args[0])] + list(args[1:]) if kind is None else args
        inv = {h: r for r, h in d["binding"].items()}
        if name == "fetch" or any(a not in inv for a in args):
            obj = kind or next((a for a in args if a in d["things"]), None)
            rec = next((a for a in args if a in d["places"]), None)
            inv = {h: r for r, h in self.project(obj, rec).items()}
            if kind:                                   # the kind's instance as the projection bound it
                args = [d["binding"].get("target") if a in (kind, d.get("resolved", {}).get(kind)) else a for a in args]
        return ports.say_in_roles(name, args, inv)
