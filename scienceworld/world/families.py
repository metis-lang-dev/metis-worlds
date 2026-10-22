"""families.py — ScienceWorld task families with the environment's own splits (world-scienceworld
step 1). A family is a list of task types; a variation is (task, n). The discovery split is the
environment's TRAIN variations, the held-out one its TEST variations (dev kept for tuning)."""
FAMILIES = {
    "conductivity": ["test-conductivity", "test-conductivity-of-unknown-substances"],
    "melting": ["measure-melting-point-known-substance", "measure-melting-point-unknown-substance"],
}


def splits(task):
    """{train, dev, test}: the variation numbers the environment assigns to TASK (one process)."""
    from sw_gym import World
    w = World()
    try:
        return w.open(task, 0)["splits"]
    finally:
        w.close()


def variations(family, which="train", per_task=None):
    out = []
    for task in FAMILIES[family]:
        vs = splits(task)[which]
        out += [(task, v) for v in (vs[:per_task] if per_task else vs)]
    return out


def package_name(task, variation):
    return "%s_%d" % (task.replace("-", "_"), variation)


SPLITS = {"discovery": "train", "gate": "dev", "heldout": "test"}     # the loop's names for the environment's splits


def sample(split, family, n, seed=1):
    """N variations of FAMILY from SPLIT (the loop's name or the environment's), spread over the
    family's task types, as (task, variation) pairs — the policy driver's listing."""
    which = SPLITS.get(split, split)
    import random
    out = []
    per = max(1, -(-n // len(FAMILIES[family])))
    for task in FAMILIES[family]:
        vs = list(splits(task)[which])
        random.Random(seed).shuffle(vs)
        out += [(task, v) for v in vs[:per]]
    return out[:n]
