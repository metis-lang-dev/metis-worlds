"""gen_level.py — a level variant as a PACKAGE (world-minihack step 1):
`python -m world.gen_level small apple newt none none [--seed N] [--out DIR]` writes
`domains/<name>/{<name>.llp, domain.yaml, intent.yaml, level.json, mh_host.py}`: the level's
cells and names as types, the perceived start as `#init`, the card, the host shim. The
program holds the declarations only — no rules: the domain is what the agent's runs extract
(LEARNING.md: agent first, domain after).

With `domain_rel` the package is an INSTANCE over a lifted base instead (the policy driver's: metis-loop
pi/policy/minihack.py): `base_source(name)` is the base — the perception's, the commands' and the
outcomes' predicates over the level's types, no rule — and the instance declares the level's types
(cell, thing, beast), the grid's geometry as static facts (`next(C, D, C2)`: the cell one step in
direction D; the cells are the level's own, named by their coordinates) and the perceived start.
"""
import argparse, json, os, shutil, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import levels  # noqa: E402
from mh_gym import World  # noqa: E402

CARD = open(os.path.join(HERE, "card.yaml")).read()


# the room family's task (the actor's task line: the model is told it, never the des). The world wins on ARRIVAL:
# stepping onto the stairs ends the episode won, so the line names the step, not a descent (opus's 2a review R1:
# "go down them" made DOWN 82% of all intents, and DOWN can never win here). Not "the stairs" either: the card
# maps any stairs to DOWN ("go down the stairs", and "down" means south "unless the stairs are meant"), so a
# rerun with "walk onto the stairs" typed DOWN 92%; the host's describe() names the stairs down "the goal"
TASK = "walk onto the goal: standing on it wins"


# the eight directions as the host's cmd_move(D) names them, and their steps on the grid (x east, y south)
STEPS = {"n": (0, -1), "e": (1, 0), "s": (0, 1), "w": (-1, 0), "ne": (1, -1), "se": (1, 1), "sw": (-1, 1), "nw": (-1, -1)}


def _declarations():
    """The predicates every level shares (the types cell, thing and beast are the level's)."""
    return ["layers (dyn).", "stages (act).",
            "type dir {n e s w ne se sw nw}.",
            "type doorstate {open closed}.",
            "type hungerstate {satiated normal hungry weak fainting fainted starved}.",
            "type said_kind {%s}." % " ".join(sorted({k for _, k in __import__("perceive").MESSAGES} | {"other"})),
            "type num {n0 .. n40}.",
            "namespace mh produce (dyn).",
            "% the grid (static: the instance's facts)", "bwd next(cell, dir, cell).",
            "% the perception", "pred agent_at(cell) : mh.", "pred floor(cell) : mh.", "pred wall(cell) : mh.", "pred corridor(cell) : mh.",
            "pred door(cell, doorstate) : mh.", "pred stairs_down(cell) : mh.", "pred stairs_up(cell) : mh.", "pred obj(thing, cell) : mh.",
            "pred monster(beast, cell) : mh.", "pred trap(said_kind, cell) : mh.", "pred unknown(cell) : mh.",
            "pred hp(num) : mh.", "pred hpmax(num) : mh.", "pred hunger(hungerstate) : mh.", "pred turn(num) : mh.", "pred holds(thing) : mh.",
            "pred said(said_kind) : mh.",
            "% the commands, one per intent", "pred cmd_move(dir) : mh.", "pred cmd_pickup : mh.", "pred cmd_eat : mh.", "pred cmd_down : mh.",
            "pred cmd_wait : mh.", "pred cmd_open(dir) : mh.", "pred cmd_kick(dir) : mh.", "pred cmd_search : mh.", "pred cmd_apply : mh.", "pred cmd_unknown : mh.",
            "% the outcomes (the extracted rules will produce them)", "type act {move pickup eat down wait open kick search apply unknown}.",
            "pred done(act) : mh.", "pred refused(act) : mh.", "pred progress(act) : mh."]


def base_source(name="mh"):
    """The lifted base the policy driver builds (its empty start): every level's predicates, no rule."""
    return "\n".join(["% " + name + " — the loop's base over MiniHack's room family (world/gen_level.py base_source): the",
                      "% perception's, the commands' and the outcomes' predicates; the level's types and the grid are the",
                      "% instance's. No rule: the loop writes them.",
                      "catalog %s 1." % name,
                      'provenance text "the loop\'s base: the empty domain over MiniHack\'s facts (loop-policy)" "2026-10-22".',
                      "types (cell thing beast).   % the level's (spec 12: the base compiles alone)"]
                     + _declarations() + ["stage act {", "}", ""])


def num_atom(a):
    """hp(16) → hp(n16): the perception's numbers as the `num` type's values (clamped to n40)."""
    pred = a.split("(")[0]
    if pred in ("hp", "hpmax", "turn"):
        return "%s(n%d)" % (pred, min(int(a[a.index("(") + 1:-1]), 40))
    return a


def geometry(cells):
    """`next(C, D, C2).` for every cell of the level and every direction whose step stays on a cell."""
    have = set(cells)
    out = []
    for c in cells:
        x, y = (int(v) for v in c[1:].split("_"))
        for d, (dx, dy) in STEPS.items():
            c2 = "c%d_%d" % (x + dx, y + dy)
            if c2 in have:
                out.append("next(%s, %s, %s)." % (c, d, c2))
    return out


def generate(variant, seed, out_dir, max_steps=40, domain_rel=None, name=None):
    lv = levels.level(variant, seed)
    w = World()
    try:
        info = w.open(des=lv["des"], actions=lv["actions"], max_steps=100, seed=seed)
    finally:
        if w.env is not None:                       # in-process NetHack: the policy driver generates many levels
            w.env.close()
    per = info["init"]
    names = per["names"]
    held = {a[6:-1] for a in per["atoms"] if a.startswith("holds(")}          # the starting kit is perceived too (flint_stone, rock)
    objs = sorted(set(names["objects"]) | held | {"apple", "key", "club", "sling", "flint_stones", "rocks", "leather_armor"})
    mons = sorted(set(names["monsters"]) | {"newt", "rat", "jackal"})
    name = name or lv["name"]
    types = ["type cell {%s}." % " ".join(info["cells"]), "type thing {%s}." % " ".join(objs), "type beast {%s}." % " ".join(mons)]
    if domain_rel:                                  # an INSTANCE over the lifted base (the policy driver's)
        lines = ["% " + name + " — MiniHack level " + lv["name"] + " seed %d, generated by world/gen_level.py: the level's types," % seed,
                 "% the grid as static facts and the perceived start, over the lifted base.",
                 "catalog " + name + " 1.",
                 'provenance text "generated MiniHack level %s seed %d" "2026-10-22".' % (lv["name"], seed),
                 'include "%s".' % domain_rel] + types + ["", "% the grid"] + geometry(info["cells"]) + ["", "% the start"]
    else:
        lines = ["% " + name + " — a MiniHack level as a package (generated by world/gen_level.py): its cells and names",
                 "% as types, the perceived start as #init; declarations only — the rules are what the agent's runs extract.",
                 "catalog " + name + " 1.",
                 'provenance text "generated MiniHack level %s seed %d" "2026-10-21".' % (name, seed)]
        decl = _declarations()
        lines += decl[:2] + types + [l for l in decl[2:] if not l.startswith(("bwd next", "% the grid"))] + [
            "stage act {", "  %% I can't do that here.", "  unknown [dyn] : cmd_unknown -o refused(unknown).", "}", ""]
    for a in per["atoms"]:
        lines.append("#init %s 1" % num_atom(a))
    lines += ["#steps 20", "#seeds 1"]
    pkg = os.path.join(out_dir, name)
    os.makedirs(pkg, exist_ok=True)
    open(os.path.join(pkg, name + ".llp"), "w").write("\n".join(lines) + "\n")
    json.dump({"des": lv["des"], "actions": lv["actions"], "seed": seed, "features": lv["features"], "cells": info["cells"],
               "size": info["size"]}, open(os.path.join(pkg, "level.json"), "w"), indent=1)
    open(os.path.join(pkg, "intent.yaml"), "w").write(CARD)
    open(os.path.join(pkg, "domain.yaml"), "w").write(
        "# %s — a MiniHack level as a package (generated by world/gen_level.py); the small LLM agent acts from the card.\n"
        "program: %s.llp\nhost: mh_host.py:make\nintent: {spec: intent.yaml}\nclock: {beats: 1}\nrecords: records/\n"
        "display: MiniHack %s\nline: %s\nvoice: own\n"
        # act without a rule (world-minihack step 2a): the small agent types its next intent from the card
        "actor: {max_steps: %d, task: %s}\n" % (name, name, name, json.dumps("a lit room: " + json.dumps(lv["features"])),
                                                 max_steps, json.dumps(TASK)))
    shim = open(os.path.join(HERE, "package_host.py")).read().replace("__WORLD__", HERE)
    open(os.path.join(pkg, "mh_host.py"), "w").write(shim)
    return pkg, len(per["atoms"])


# ── the room in roles (semantic_world.grid, libs/semantic-world) ──
# A STAND-IN program (the architect: say so): MiniHack's domain is what the loop extracts (none is on file); these
# six rules are what an extracted one would read over roles — the room family's errand (walk onto the stairs),
# through a closed door, past a beast. The program is compiled once (domains/_roles: committed); a level is its
# map store and its host, never its source.
ROLES_DIR = os.path.join(os.path.dirname(HERE), "domains", "_roles")


def stand_in_base(geometry="pred"):
    """The lifted base over (cell thing beast). geometry "pred": next(p, d, q) is the host's projection's, between
    bound cells; "bwd": a static table, the instance's facts (today's form: the flat comparison)."""
    said = " ".join(sorted({k for _, k in __import__("perceive").MESSAGES} | {"other"}))
    geo = "pred next(cell, dir, cell) : mh.            % the host's projection: between bound cells, on the live session" \
        if geometry == "pred" else "bwd next(cell, dir, cell).                   % a static table: the instance's facts"
    return "\n".join([
        "% mh_base — a STAND-IN for MiniHack's extracted domain (semantic-map s-d4270bed step 4, world/gen_level.py):",
        "% the room family's errand over roles — the cell the robot stands on, the next cells of the host's path,",
        "% the beasts and things in view. The host plans the path; the rules take the next step, open the door on",
        "% it, fight what stands on it, pick up what the task wants.",
        "catalog mh_base 1.",
        'provenance text "a stand-in MiniHack base over roles (the loop extracts the real one)" "2026-10-25".',
        "layers (dyn).", "stages (act).",
        "types (cell thing beast).   % the instance's: the capacity's roles (or a level's own cells: flat)",
        "type dir {n e s w ne se sw nw}.",
        "type doorstate {open closed}.",
        "type said_kind {%s}." % said,
        "namespace mh produce (dyn).",
        "pred agent_at(cell) : mh.", "pred floor(cell) : mh.", "pred door(cell, doorstate) : mh.", "pred stairs_down(cell) : mh.",
        "pred obj(thing, cell) : mh.", "pred monster(beast, cell) : mh.", "pred holds(thing) : mh.", "pred said(said_kind) : mh.",
        geo,
        "pred toward(cell) : mh.                      % the next cell of the host's path",
        "pred fought(beast) : mh.",
        "bwd want(thing).",
        "stage act {",
        "  %% I step {D}, to {P}.",
        "  move [dyn] : agent_at(C) * $next(C, D, P) * $toward(P) * $floor(P) -o agent_at(P).",
        "  %% I step {D}, through the door.",
        "  move_door [dyn] : agent_at(C) * $next(C, D, P) * $toward(P) * $door(P, open) -o agent_at(P).",
        "  %% The door {D} is closed: I open it.",
        "  open_door [dyn] : agent_at(C) * $next(C, D, P) * $toward(P) * door(P, closed) -o agent_at(C) * door(P, open).",
        "  %% The door {D} is locked: I kick it.",
        "  kick_door [dyn] : agent_at(C) * $next(C, D, P) * $toward(P) * door(P, closed) * $said(door_locked) -o agent_at(C) * door(P, open).",
        "  %% {B} is in my way, {D}: I fight it.",
        "  move_fight [dyn] : agent_at(C) * $next(C, D, P) * $toward(P) * $monster(B, P) -o fought(B).",
        "  %% I pick up {T}.",
        "  pickup [dyn] : agent_at(C) * $obj(T, C) * $want(T) -o holds(T).",
        "}", ""])


def roles_files(k=None):
    """The committed role program: {file: text} (domains/_roles)."""
    from semantic_world import grid
    return {"mh_base.llp": stand_in_base("pred"), "capacity.llp": grid.capacity(k or grid.K)}


def generate_roles(variant, seed, out_dir, view=False, k=None, flat=False, des=None, name=None, max_steps=200):
    """A level over the committed role program: domains/<name>/{<name>.llp (the includes, no room), level.json (its
    `map`: the store), .map.json (the des's, or empty in view mode), mh_host.py, domain.yaml}. flat: the same
    stand-in base over the level's own cells with the geometry a static table (today's form; the comparison).
    des: a level's des of its own (the large one); else the room family's variant. → the package dir."""
    from semantic_world import grid
    lv = levels.level(variant, seed) if des is None else {"name": name, "des": des, "actions": __import__("mh_host").ACTIONS,
                                                          "seed": seed, "features": {"des": "own"}}
    name = name or lv["name"] + ("_flat" if flat else "_roles")
    w = World()
    try:
        info = w.open(des=lv["des"], actions=lv["actions"], max_steps=100, seed=seed)
    finally:
        if w.env is not None:
            w.env.close()
    pkg = os.path.join(out_dir, name)
    os.makedirs(pkg, exist_ok=True)
    head = ["% " + name + " — MiniHack level " + lv["name"] + " seed %d (world/gen_level.py generate_roles)." % seed]
    if flat:
        open(os.path.join(out_dir, "mh_base_flat.llp"), "w").write(stand_in_base("bwd"))
        names = info["init"]["names"]
        things = sorted(set(names["objects"]) | {"apple", "key"})
        beasts = sorted(set(names["monsters"]) | {"newt", "rat"})
        lines = head + ["catalog %s 1." % name, 'provenance text "flat: the level\'s cells, the geometry static" "2026-10-25".',
                        'include "../mh_base_flat.llp".', "type cell {%s}." % " ".join(info["cells"]),
                        "type thing {%s}." % " ".join(things), "type beast {%s}." % " ".join(beasts), ""] + \
            [l for l in geometry(info["cells"])]
    else:
        rd = os.path.join(out_dir, "_roles")
        os.makedirs(rd, exist_ok=True)
        for f, t in roles_files(k).items():
            open(os.path.join(rd, f), "w").write(t)
        lines = head + ["catalog %s 1." % name, 'provenance text "over the committed role program: no room in its source" "2026-10-25".',
                        'include "../_roles/mh_base.llp".', 'include "../_roles/capacity.llp".', "want(target)."]
    open(os.path.join(pkg, name + ".llp"), "w").write("\n".join(lines) + "\n")
    mp = os.path.abspath(os.path.join(pkg, ".map.json"))
    grid.GridMap.build(mp, info["size"], des=lv["des"], view=view, k=k or grid.K, flat=flat)
    json.dump({"des": lv["des"], "actions": lv["actions"], "seed": seed, "features": lv["features"], "cells": info["cells"],
               "size": info["size"], "map": mp, "max_steps": max_steps}, open(os.path.join(pkg, "level.json"), "w"), indent=1)
    open(os.path.join(pkg, "domain.yaml"), "w").write(
        "# %s — a MiniHack level over the role program (generated by world/gen_level.py generate_roles).\n"
        "program: %s.llp\nhost: mh_host.py:make\nclock: {beats: 1}\nrecords: records/\n"
        "display: MiniHack %s\nline: %s\nvoice: own\n" % (name, name, name, json.dumps("the room: walk onto the stairs")))
    shim = open(os.path.join(HERE, "package_host.py")).read().replace("__WORLD__", HERE)
    open(os.path.join(pkg, "mh_host.py"), "w").write(shim)
    return pkg


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("size"); ap.add_argument("item"); ap.add_argument("monster"); ap.add_argument("door"); ap.add_argument("trap")
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--out", default=os.path.join(HERE, "..", "domains"))
    ap.add_argument("--max-steps", type=int, default=40, help="the actor's step cap (the manifest's actor: {max_steps})")
    a = ap.parse_args(argv)
    pkg, n = generate((a.size, a.item, a.monster, a.door, a.trap), a.seed, a.out, max_steps=a.max_steps)
    print("%s: %d perceived atoms" % (pkg, n))
    return 0


if __name__ == "__main__":
    sys.exit(main())
