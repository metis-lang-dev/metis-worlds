"""semantic_map.py — a game's semantic map (alf-demo, DEMO.md §3): places with a pose, things at
places, the agent, the task. TEXT mode here (no THOR, no frames: CI and the page's fixtures);
the THOR half (the oracle's exploration tables and frames) is step 1's.

    ALFWORLD_DATA=… .worlds/alf/bin/python world/semantic_map.py GAME_DIR OUT.json [INDEX_URL]

INDEX_URL: the world's tile index as the map's reader finds it from the map file (relative to
it), written as the map's `tileset.index`; the page merges it over its base (DEMO.md §8).

Text mode reads the game's PDDL facts through the host (the generated package's game.json and
alf_host.py, as the driver does) and traj_data.json:
- places = the receptacles (`recat(R, L)`), each at the position its THOR object id carries:
  ALFWorld names a thing by its id (`countertop_bar__minus_01_dot_87_bar__plus_00_dot_96_…` =
  `CounterTop|-01.87|+00.96|+01.80`), so x and z are read from the name, in metres;
  `openable` / `closed` from the facts;
- things = the objects in a receptacle (`inrecep(O, R)`), `pickupable` from the facts; their
  own coordinates too (traj_data's `object_poses` name objects by THOR's instance names,
  `Pan_94f6c891`, so they do not join the PDDL ids; the id's coordinates are the same pose);
- agent = traj_data's `init_action` (TeleportFull x, z, rotation), at nowhere yet, empty-handed;
- edges = every pair (ALFWorld's `go to` reaches any place);
- cell = 0.25: the grid a reader puts the places on, in metres (a kitchen's drawers sit 0.3 m
  apart: at 0.5 they share cells; the architect's ruling);
- task = the annotators' words (`turk_annotations`, the first `task_desc`) and the goal the
  generator resolves (`target(O)` / `dest(R)`): fetch(O, R).
Ids are the program's handles (`countertop3`), names the game's spoken form ("countertop 3").
"""
import json
import os
import re
import shutil
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

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


def text_map(game_dir, index=None):
    import gen_instance
    from alf_host import AlfHost
    tmp = tempfile.mkdtemp(prefix="alf-map-")
    try:
        path, _, _ = gen_instance.generate(game_dir, tmp)
        meta = json.load(open(os.path.join(os.path.dirname(path), "game.json")))
        facts = open(path).read()
        h = AlfHost(os.path.dirname(path))
        try:
            static, dyn, params, to_name = set(h.static), set(h.dyn), h.params, h.to_name
        finally:
            h.gym.close()
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    traj = json.load(open(os.path.join(game_dir, "traj_data.json")))
    kind = meta["handles"]["kind"]

    def pos(handle):
        t = thor_id(to_name.get(handle, ""))
        return [round(t[1], 2), round(t[3], 2)] if t else None

    places = []
    for a in sorted(a for a in static if a.startswith("recat(")):
        r, _ = _args(a)
        places.append({"id": r, "name": spoken(r), "type": re.sub(r"\d+$", "", r), "pos": pos(r),
                       "openable": "openable(%s)" % r in static,
                       "closed": "openable(%s)" % r in static and "opened(%s)" % r not in dyn, "frame": None})
    things = []
    for a in sorted(a for a in dyn if a.startswith("inrecep(")):
        o, r = _args(a)
        if kind.get(o) != "object":
            continue
        things.append({"id": o, "name": spoken(o), "type": re.sub(r"\d+$", "", o), "at": r, "pos": pos(o),
                       "pickupable": "pickupable(%s)" % o in static})
    ia = traj["scene"].get("init_action") or {}
    ann = traj.get("turk_annotations", {}).get("anns", [])
    words = [a["task_desc"].strip() for a in ann if a.get("task_desc")]
    targets = re.findall(r"^target\((\w+)\)\.", facts, re.M)
    dests = re.findall(r"^dest\((\w+)\)\.", facts, re.M)
    ids = [p["id"] for p in places]
    task = {"text": words[0] if words else "", "goal": "fetch(%s, %s)" % (targets[0], dests[0]) if targets and dests else "",
            "targets": targets, "dests": dests, "params": params,
            "source": "ALFWorld traj_data.json: turk_annotations (the annotators' words)"}
    return {"world": "alfworld", "scene": traj["scene"]["floor_plan"], "units": "m", "mode": "text", "cell": CELL,
            "game": os.path.relpath(game_dir, os.path.dirname(os.path.dirname(os.path.dirname(game_dir)))),
            "places": places, "things": things,
            "agent": {"pos": [round(ia.get("x", 0.0), 2), round(ia.get("z", 0.0), 2)], "yaw": ia.get("rotation", 0),
                      "at": None, "holding": None},
            "edges": [[a, b] for i, a in enumerate(ids) for b in ids[i + 1:]],
            "task": task, "card": world_card(traj["scene"]["floor_plan"], places, things, task),
            "overview": None, "tileset": {"index": [index] if index else []}}


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
    asks += [{"say": "stop", "what": "the agent stops what it is doing and waits"},
             {"say": "new game", "what": "the same room from its start, the task again"}]
    return {"title": "ALFWorld kitchen %s" % scene,
            "about": ["ALFWorld: a household scene from ALFRED, in text mode (TextWorld): one game is one room and one task.",
                      "The agent moves between places, opens what is closed, takes one thing at a time and puts it in or on a place.",
                      "%d places of %d kinds, %d things you can ask for (%d kinds)." % (len(places), len(rooms), len(pick), len(tk))],
            "room": rooms, "things": tk, "asks": asks,
            "cannot": ["a single step on its own (just go, just open, just pick up): the agent takes whole errands",
                       "a thing that is not in this room, or a place that is not",
                       "another task after the game is won: say \"new game\" first"],
            "source": "generated from the game's facts by world/semantic_map.py"}


if __name__ == "__main__":
    game, out = sys.argv[1:3]                  # read first: the game's loader rewrites sys.argv
    index = sys.argv[3] if len(sys.argv) > 3 else None
    m = text_map(game, index)
    with open(out, "w") as f:          # closed now: the game's child can end the process hard at exit
        json.dump(m, f, indent=1)
    print("%s: %d places, %d things; task %r → %s" % (m["scene"], len(m["places"]), len(m["things"]),
                                                     m["task"]["text"], m["task"]["goal"]))


# ── the store (semantic-map s-d4270bed step 2): the room as data; the hierarchy's roles bound to it ──
# The specialists are compiled once over a role vocabulary (domains/hier/capacity.llp, gen_hier.capacity);
# the map lives here, in the host. Per goal the projection binds roles to the map's entries — target ↦ the
# object the goal wants, dest ↦ where it goes, p0 ↦ the receptacle where the robot stands, p1..pk ↦ the
# places most likely to hold the target (by belief), the location roles ↦ their places' locations — and the
# hosts read the world through that binding (role_reading), so a rebinding is a sync's retract + assert on
# the live session, never a recompile. One file per hierarchy, beside the commands log (.map.json): the
# agent's hosts share a process, the driver runs one per activation; one writer at a time.
K = 8                                              # the places a projection binds besides dest and p0 (step 1's measure)
OBJECT_ROLES = ("target", "other")


def want_handle(obj):
    """The wanted entry for a target's kind before one is seen (view mode): tomato1 → "tomato"."""
    return re.sub(r"\d+$", "", obj)


def place_roles(k=K):
    return ("dest", "p0") + tuple("p%d" % i for i in range(1, k + 1))


def location_roles(k=K):
    return ("lhere", "ldest") + tuple("l%d" % i for i in range(1, k + 1))


class SemanticMap:
    """places {receptacle: {loc, openable, opened}}, things {object: {in, pickupable}}, belief {object:
    {receptacle: p}}, agent {at, holding}, task {targets, dests}, binding {role: handle}, k — as JSON at
    `path`, read again when the file changed (another host wrote it)."""

    def __init__(self, path):
        self.path, self.data, self._mtime = path, None, None

    @classmethod
    def build(cls, path, static, dyn, targets, dests, k=K, view=False):
        """The map from the game's facts as the mirror reads them (static and dynamic atoms) and the task's
        resolved targets and dests; no binding yet. view: the robot sees only what stands before it
        (step 3, the architect's RULING 1): the places are known (the room's first look lists them), a
        thing only once seen; the task's wanted type is an entry of its own, believed flat over the places
        that can hold it (ALFWorld's cancontain), until a target is seen."""
        m = cls(path)
        st = set(static)
        places = {}
        for a in sorted(st):
            if a.startswith("recat("):
                r, l = _args(a)
                places[r] = {"loc": l, "openable": "openable(%s)" % r in st, "opened": False}
        pick = {_args(a)[0] for a in st if a.startswith("pickupable(")}
        things = {o: {"in": None, "pickupable": True} for o in sorted(pick)}
        m.data = {"places": places, "things": things, "belief": {}, "agent": {"at": None, "holding": None},
                  "task": {"targets": sorted(targets), "dests": sorted(dests)}, "binding": {}, "k": k}
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

    def _observe_view(self, d, dyn, held):
        changed = False
        vis = self._visible(d, d["agent"]["at"])
        seen = {}
        for a in dyn:
            if a.startswith("inrecep("):
                o, r = _args(a)
                if r in vis:
                    seen[o] = r
        if held:
            seen[held] = None
        for o, r in sorted(seen.items(), key=lambda x: x[0]):
            if o not in d["things"]:                   # a thing never seen: the map grows
                d["things"][o] = {"in": None, "pickupable": o in d["pickable"]}
                changed = True
            t = d["things"][o]
            post = {r: 1.0} if r else {}
            if t["in"] != r or d["belief"].get(o) != post:
                t["in"], changed = r, True
                if post:
                    d["belief"][o] = post
                else:
                    d["belief"].pop(o, None)
            d["looked"].pop(o, None)                   # a sighting supersedes the places it was not in
            for w, wt in list(d["things"].items()):    # a target seen resolves its wanted type
                if wt.get("wanted") and o in d["task"]["targets"] and d["types"].get(o) == wt["wanted"]:
                    del d["things"][w]
                    d["belief"].pop(w, None)
                    d["looked"].pop(w, None)
                    d.setdefault("resolved", {})[w] = o
                    changed = True
        for r in vis:                                  # looked into: what is not there is not there
            for o in sorted(d["belief"]):
                bel = d["belief"][o]
                if bel.get(r, 0) > 0 and seen.get(o) != r:
                    d["looked"].setdefault(o, []).append(r)
                    del bel[r]
                    z = sum(bel.values())
                    d["belief"][o] = {x: p / z for x, p in bel.items()} if z > 0 else self._prior(o)
                    d["look"] = r
                    changed = True
            for o, x in seen.items():
                if x == r and d["look"] != r and (o in d["task"]["targets"] or o in d.get("resolved", {}).values()):
                    d["look"], changed = r, True
        return changed

    def lost(self, thing):
        """No place left to look for THING: the belief is empty and it is not in hand."""
        d = self.load()
        return bool(d.get("view")) and thing in d["things"] and not d["belief"].get(thing) \
            and d["agent"]["holding"] != thing

    def load(self):
        try:
            t = os.stat(self.path).st_mtime_ns
        except OSError:
            return self.data
        if t != self._mtime:
            with open(self.path) as f:
                self.data = json.load(f)
            self._mtime = t
        return self.data

    def save(self):
        tmp = self.path + ".tmp"
        with open(tmp, "w") as f:
            json.dump(self.data, f, indent=1, sort_keys=True)
        os.replace(tmp, self.path)
        self._mtime = os.stat(self.path).st_mtime_ns

    def observe(self, dyn, save=True):
        """What the robot sees now (text mode: every fact) folded into the map: the places opened, the
        agent's place and hand, and each thing's belief updated by the observation's likelihood (1 at the
        place it is seen in, 0 elsewhere: the posterior collapses; a thing not seen keeps its prior)."""
        d = self.load()
        dyn = set(dyn)
        changed = False
        opened = {_args(a)[0] for a in dyn if a.startswith("opened(")}
        for r, p in d["places"].items():
            if p["opened"] != (r in opened):
                p["opened"], changed = r in opened, True
        at = next((_args(a)[0] for a in dyn if a.startswith("at(")), d["agent"]["at"])
        held = next((_args(a)[0] for a in sorted(dyn) if a.startswith("holds(")), None)
        if (at, held) != (d["agent"]["at"], d["agent"]["holding"]):
            d["agent"].update(at=at, holding=held)
            changed = True
        if d.get("view"):
            moved = self._observe_view(d, dyn, held)
            if moved and d["binding"]:
                self._reproject(d)
            if (changed or moved) and save:
                self.save()
            return changed or moved
        seen = {}
        for a in dyn:
            if a.startswith("inrecep("):
                o, r = _args(a)
                seen[o] = r
        for o in sorted(set(seen) | ({held} if held else set())):
            t = d["things"].setdefault(o, {"in": None, "pickupable": False})
            r = seen.get(o)
            prior = d["belief"].get(o, {})
            post = {r: 1.0} if r else {}
            if t["in"] != r or prior != post:
                t["in"], changed = r, True
                if post:
                    d["belief"][o] = post
                else:
                    d["belief"].pop(o, None)
        if changed and save:
            self.save()
        return changed

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
        keep = {r: h for r, h in b.items() if slot(r) and (bel.get(h, 0) > 0 or obel.get(h, 0) > 0 or h == d.get("look"))}
        free = ["p%d" % i for i in range(1, k + 1) if "p%d" % i not in keep]
        bound = set(keep.values()) | {b.get("dest"), b.get("p0")}
        cand = [r for r, p in sorted(bel.items(), key=lambda x: (-x[1], x[0])) if p > 0 and r in d["places"] and r not in bound]
        slots = dict(keep, **dict(zip(free, cand)))
        loc_role = {h: r for r, h in b.items() if r in ("lhere", "ldest")}
        need = {d["places"][h]["loc"] for h in slots.values()}
        for r, h in sorted(b.items()):
            if re.fullmatch(r"l[1-9]\d*", r) and h in need and h not in loc_role:
                loc_role[h] = r
        used = set(loc_role.values())
        for h in sorted(need):
            if h not in loc_role:
                r = next("l%d" % i for i in range(1, k + 1) if "l%d" % i not in used)
                loc_role[h] = r
                used.add(r)
        b = {r: h for r, h in b.items() if not slot(r) and not re.fullmatch(r"l[1-9]\d*", r)}
        b.update(slots)
        b.update((r, h) for h, r in loc_role.items() if re.fullmatch(r"l[1-9]\d*", r))
        d["binding"] = {r: h for r, h in sorted(b.items()) if h}

    def binding(self):
        return dict(self.load()["binding"])

    def handle(self, role, binding=None):
        """The map entry a role is bound to (None when unbound); a constant that is no role is itself.
        binding: a host's own (a specialist's, frozen for its activation in view mode) over the map's."""
        return (binding if binding is not None else self.binding()).get(role) if role in self.roles() else role

    def roles(self):
        k = self.load()["k"]
        return set(OBJECT_ROLES) | set(place_roles(k)) | set(location_roles(k))

    def role_of(self, handle):
        return {h: r for r, h in self.binding().items()}.get(handle)

    def role_reading(self, reading, binding=None):
        """The world's facts (atom → count, the game's handles) over the bound entries only, said in roles,
        with each bound receptacle's place facts: recat(R, L) when its location is bound, openable(R) or
        notopenable(R). binding: a host's own over the map's (handle)."""
        d = self.load()
        if binding is not None:
            d = dict(d, binding=binding)
        inv = {h: r for r, h in d["binding"].items()}
        out = {}
        if d.get("view"):                          # where a bound thing is: the belief's, not the game's (step 3)
            objs = {h for r, h in d["binding"].items() if r in OBJECT_ROLES}
            reading = {a: n for a, n in reading.items()
                       if not (a.startswith(("inrecep(", "objat(")) and _args(a)[0] in objs)}
            out.update(self._believed(d, inv))
        for a, n in reading.items():
            name = a.split("(")[0]
            args = _args(a) if "(" in a else []
            if all(x in inv for x in args):
                out["%s(%s)" % (name, ",".join(inv[x] for x in args)) if args else name] = n
        for role, h in d["binding"].items():
            p = d["places"].get(h)
            if p is None or role not in place_roles(d["k"]):
                continue
            if p["loc"] in inv:
                out["recat(%s,%s)" % (role, inv[p["loc"]])] = 1
            out[("openable(%s)" if p["openable"] else "notopenable(%s)") % role] = 1
        return out

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

    def names(self, binding=None):
        """name(role, thing) as data: the bound roles and the things they name (locations left out)."""
        k = self.load()["k"]
        keep = set(OBJECT_ROLES) | set(place_roles(k))
        return sorted([r, h] for r, h in (binding if binding is not None else self.binding()).items() if r in keep)

    def belief(self, obj_role, rec_role):
        """The belief that the role-bound object is in the role-bound receptacle, normalized over the bound
        places (the weight port `look`): 1.0 for a single believed place, 1.0 when the map has no belief for it."""
        d = self.load()
        b = d["binding"]
        bel = d["belief"].get(b.get(obj_role), {})
        bound = {b[r] for r in place_roles(d["k"]) if b.get(r)}
        z = sum(p for r, p in bel.items() if r in bound)
        return bel.get(b.get(rec_role), 0.0) / z if z > 0 else 1.0      # the map knows nothing: flat

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
        inv = {h: r for r, h in d["binding"].items()}
        if name == "fetch" or any(a not in inv for a in args):
            obj = kind or next((a for a in args if a in d["things"]), None)
            rec = next((a for a in args if a in d["places"]), None)
            inv = {h: r for r, h in self.project(obj, rec).items()}
            if kind:                                   # the kind's instance as the projection bound it
                args = [d["binding"].get("target") if a in (kind, d.get("resolved", {}).get(kind)) else a for a in args]
        return "%s(%s)" % (name, ",".join(inv.get(a, a) for a in args)) if args else name
