"""levels.py — the level families and their splits (world-minihack step 1), built with
MiniHack's LevelGenerator: a lit room of a size, a down stairs, and zero or more of an
item (apple, key), a monster (newt, rat, jackal), a closed door, a trap (pit). The
DISCOVERY split is a set of combinations; the HELD-OUT split is the combinations never
seen in discovery (the compositional test: a monster AND a trap, a door AND a key, …).

    families()                    every family name
    level(name, variant, seed)    {"name", "des", "actions", "seed", "features"}
    split(family, which)          the variants of a family in "discovery" or "held_out"
    sample(split, family, n, seed)  n GAMES (variant, seed) of a split, seeded: the policy driver's
"""
import itertools
import random

SIZES = {"small": (5, 5), "medium": (7, 5), "large": (9, 7)}
ITEMS = ["none", "apple", "key"]
ITEM_NAMES = {"apple": "apple", "key": "skeleton key"}          # the variant word -> NetHack's object name (M1: no "key")
MONSTER_NAMES = {"newt": "newt", "rat": "sewer rat", "jackal": "jackal"}   # … and monster name (no "rat" either)
MONSTERS = ["none", "newt", "rat", "jackal"]
DOORS = ["none", "closed"]
TRAPS = ["none", "pit"]


def features(variant):
    size, item, monster, door, trap = variant
    return {"size": size, "item": item, "monster": monster, "door": door, "trap": trap}


def all_variants():
    return list(itertools.product(SIZES, ITEMS, MONSTERS, DOORS, TRAPS))


def is_held_out(v):
    """Held out: every combination with BOTH a monster and a trap, or BOTH a door and a key —
    the compositions discovery never shows; everything else is discovery."""
    _, item, monster, door, trap = v
    return (monster != "none" and trap != "none") or (door != "none" and item == "key")


def split(family="room", which="discovery"):
    return [v for v in all_variants() if is_held_out(v) == (which == "held_out")]


# the policy driver's splits (metis-loop pi/policy/minihack.py): discovery's variants at their first layout seeds;
# the GATE's are discovery's variants at other seeds (seen kinds, unseen layouts: ALFWorld's valid_seen); held_out
# the compositions discovery never shows (valid_unseen). A family narrows them: room_quiet has no monster
# (a monster moves on its own, so a record of it is not the command's alone)
GATE_SEED = 1000


def sample(which="discovery", family="room", n=10, seed=1):
    """n games [(variant, level seed)] of the split WHICH (discovery | gate | held_out) of FAMILY (room |
    room_quiet), in a seeded order; the level seeds of discovery and held_out are SEED, the gate's
    GATE_SEED + SEED (and its own order, so its first games are not discovery's first variants)."""
    if family not in ("room", "room_quiet"):
        raise ValueError("family: room | room_quiet, not %r" % family)
    if which not in ("discovery", "gate", "held_out"):
        raise ValueError("split: discovery | gate | held_out, not %r" % which)
    vs = [v for v in split("room", "held_out" if which == "held_out" else "discovery") if family == "room" or v[2] == "none"]
    s = GATE_SEED + seed if which == "gate" else seed
    random.Random(s).shuffle(vs)
    return [(v, s) for v in vs[:n]]


def des_of(variant, seed=1):
    """The room, w×h floor. With a door (M2): a wall column splits it, the door sits in the
    wall, the stairs are BEHIND the wall and the agent starts in front of it — `locked` when
    the variant has the key (the key opens it; KICK breaks it), `closed` otherwise (OPEN).
    The key is NetHack's "skeleton key" (M1: there is no object called "key")."""
    from minihack import LevelGenerator
    size, item, monster, door, trap = variant
    w, h = SIZES[size]
    rng = random.Random(seed)
    if door == "none":
        lvl = LevelGenerator(w=w, h=h, lit=True)
        front = [(x, y) for x in range(w) for y in range(h)]
        back = front
    else:
        wx, dy = w // 2, rng.randrange(h)
        rows = []
        for y in range(h):
            rows.append("." * wx + ("+" if y == dy else "|") + "." * (w - wx))
        lvl = LevelGenerator(map="\n".join(rows) + "\n", lit=True)
        front = [(x, y) for x in range(wx) for y in range(h)]
        back = [(x, y) for x in range(wx + 1, w + 1) for y in range(h)]
        lvl.add_door("locked" if item == "key" else "closed", place=(wx, dy))
        lvl.set_start_rect((0, 0), (wx - 1, h - 1))
    rng.shuffle(front)
    rng.shuffle(back)
    take = front.pop
    lvl.add_stair_down(place=back.pop())
    if item != "none":
        lvl.add_object(ITEM_NAMES[item], "%" if item == "apple" else "(", place=take())
    if monster != "none":
        lvl.add_monster(MONSTER_NAMES[monster], place=take())
    if trap != "none":
        lvl.add_trap(trap, place=take())
    return lvl.get_des()


def level(variant, seed=1):
    name = "room_%s_%s_%s_%s_%s" % variant
    from mh_host import ACTIONS
    return {"name": name, "des": des_of(variant, seed), "actions": ACTIONS, "seed": seed, "features": features(variant)}


def families():
    return ["room"]


if __name__ == "__main__":
    d, h = split("room", "discovery"), split("room", "held_out")
    print("room: %d variants, %d discovery, %d held out" % (len(all_variants()), len(d), len(h)))
