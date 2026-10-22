"""families.py — ALFWorld's task families and splits as the experiments see them
(world-alfworld step 1).

    games(split)                 every game directory of a split, as ALFWorld ships it
    family(split, task_type)     the games of one task type in a split
    sample(split, task_type, n, seed)   n of them, drawn with a seed (a reproducible subset)
    FAMILIES                     the seven task types, with the first the loop learns on

The splits are ALFWorld's: `train` is the discovery split; `valid_seen` (the training
scenes, other tasks) and `valid_unseen` (scenes never seen) are the held-out ones the
closed loop is measured on (metis-agentic-loop docs/LEARNING.md). Nothing is re-split
here: a configuration the loop invented a rule from is never one it is scored on.
"""
import os
import random

FAMILIES = ("pick_and_place_simple", "pick_and_place_with_movable_recep", "pick_clean_then_place_in_recep",
            "pick_heat_then_place_in_recep", "pick_cool_then_place_in_recep", "pick_two_obj_and_place",
            "look_at_obj_in_light")
SPLITS = ("train", "valid_seen", "valid_unseen")


def data_root():
    r = os.environ.get("ALFWORLD_DATA")
    if not r:
        raise SystemExit("ALFWORLD_DATA is not set (setup.sh puts the games under data/)")
    return os.path.join(r, "json_2.1.1")


def games(split):
    root = os.path.join(data_root(), split)
    out = []
    for task in sorted(os.listdir(root)):
        tdir = os.path.join(root, task)
        if not os.path.isdir(tdir):
            continue
        for trial in sorted(os.listdir(tdir)):
            if os.path.exists(os.path.join(tdir, trial, "game.tw-pddl")):
                out.append(os.path.join(tdir, trial))
    return out


def task_of(game_dir):
    return os.path.basename(os.path.dirname(game_dir)).split("-")[0]


def family(split, task_type):
    return [g for g in games(split) if task_of(g) == task_type]


def sample(split, task_type, n, seed=1):
    gs = family(split, task_type)
    rng = random.Random(seed)
    return rng.sample(gs, min(n, len(gs)))


def counts():
    return {s: {t: len(family(s, t)) for t in FAMILIES} for s in SPLITS}


if __name__ == "__main__":
    for s, c in counts().items():
        print(s, c)
