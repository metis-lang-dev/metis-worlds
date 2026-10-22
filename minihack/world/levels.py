"""levels.py — the level families and their splits (world-minihack step 1), built with
MiniHack's LevelGenerator: a lit room of a size, a down stairs, and zero or more of an
item (apple, key), a monster (newt, rat, jackal), a closed door, a trap (pit). The
DISCOVERY split is a set of combinations; the HELD-OUT split is the combinations never
seen in discovery (the compositional test: a monster AND a trap, a door AND a key, …).

    families()                    every family name
    level(name, variant, seed)    {"name", "des", "actions", "seed", "features"}
    split(family, which)          the variants of a family in "discovery" or "held_out"
"""
import itertools
import random

SIZES = {"small": (5, 5), "medium": (7, 5), "large": (9, 7)}
ITEMS = ["none", "apple", "key"]
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


def des_of(variant, seed=1):
    from minihack import LevelGenerator
    size, item, monster, door, trap = variant
    w, h = SIZES[size]
    rng = random.Random(seed)
    lvl = LevelGenerator(w=w, h=h, lit=True)
    cells = [(x, y) for x in range(w) for y in range(h)]
    rng.shuffle(cells)
    take = lambda: cells.pop()
    lvl.add_stair_down(place=take())
    if item != "none":
        lvl.add_object(item, "%" if item == "apple" else "(", place=take())
    if monster != "none":
        lvl.add_monster(monster, place=take())
    if trap != "none":
        lvl.add_trap(trap, place=take())
    if door != "none":
        x = rng.randrange(1, w - 1)
        lvl.add_door("closed", place=(x, 0))
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
