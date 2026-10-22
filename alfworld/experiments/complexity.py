"""complexity.py — the complexity vector of a family (metis-agentic-loop docs/LEARNING.md),
measured on a sample of its games with a random walk:

    ALFWORLD_DATA=data .venv/bin/python experiments/complexity.py --split train --task pick_and_place_simple --n 5 --walk 20

state diversity     distinct dynamic-fact sets seen along the walks (sampled coverage) and facts per state
action branching    admissible commands per state: mean and p95
outcome branching   distinct next states per (state, command): the text game is deterministic (1)
horizon             the greedy policy's plan length (the base's rules: 5–7 for this family)
rule complexity     the lifted base's rule count (the program the loop extends)
uncertainty         conditional outcome entropy: 0 for a deterministic game (the surprises are ours)
distribution        games per split (the held-out variants)
partial observability   facts the text never names: the dynamic facts vs the objects the observation mentions
"""
import argparse, json, os, random, re, statistics, sys
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "world"))
import families  # noqa: E402
from alf_gym import Game  # noqa: E402


def rules_in_base():
    return sum(1 for l in open(os.path.join(ROOT, "domains", "alfred_domain.llp")) if re.match(r"\s+\w+ \[dyn\] :", l))


def walk(game_dir, steps, rng):
    g = Game()
    info = g.open(os.path.join(game_dir, "game.tw-pddl"), max_steps=steps + 5)
    seen, branching, hidden = {frozenset(info["init"])}, [len(info["admissible"])], []
    state = g.reset()
    for _ in range(steps):
        adm = state["admissible"]
        branching.append(len(adm))
        mentioned = set(re.findall(r"[a-z]+_bar_[^\s,.]+", state["obs"]))
        named = {h for h, n in info["handles"]["to_name"].items() if n in mentioned}
        dyn = [a for a in state["dynamic"] if a.startswith(("inrecep(", "objat(", "opened("))]
        unseen = [a for a in dyn if not any(h in a for h in named)]
        hidden.append((len(unseen), len(dyn)))
        cmd = rng.choice(adm)
        state = g.step(cmd)
        seen.add(frozenset(state["dynamic"]))
        if state["done"]:
            break
    g.env.close() if hasattr(g.env, "close") else None
    return {"facts": len(info["init"]) + len(info["static"]), "dynamic": len(info["init"]), "states": len(seen),
            "branching": branching, "hidden": hidden, "objects": sum(1 for k in info["handles"]["kind"].values() if k == "object"),
            "receptacles": sum(1 for k in info["handles"]["kind"].values() if k == "receptacle")}


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--split", default="train")
    ap.add_argument("--task", default="pick_and_place_simple")
    ap.add_argument("--n", type=int, default=5)
    ap.add_argument("--walk", type=int, default=20)
    ap.add_argument("--seed", type=int, default=1)
    a = ap.parse_args(argv)
    rng = random.Random(a.seed)
    rows = [walk(g, a.walk, rng) for g in families.sample(a.split, a.task, a.n, a.seed)]
    br = [b for r in rows for b in r["branching"]]
    hid = [u / d for r in rows for u, d in r["hidden"] if d]
    vec = {
        "family": a.task, "split": a.split, "games_sampled": len(rows), "walk": a.walk,
        "state_diversity": {"facts_per_state_mean": statistics.mean(r["facts"] for r in rows),
                            "dynamic_per_state_mean": statistics.mean(r["dynamic"] for r in rows),
                            "distinct_states_per_walk_mean": statistics.mean(r["states"] for r in rows),
                            "objects_mean": statistics.mean(r["objects"] for r in rows),
                            "receptacles_mean": statistics.mean(r["receptacles"] for r in rows)},
        "action_branching": {"mean": statistics.mean(br), "p95": sorted(br)[int(0.95 * (len(br) - 1))]},
        "outcome_branching": 1,
        "horizon": {"greedy_plan": "5-7 commands (go, [open], take, go, [open], put)"},
        "rule_complexity": {"base_rules": rules_in_base()},
        "uncertainty": {"conditional_outcome_entropy": 0.0, "note": "the text game is deterministic; every surprise is a missing rule"},
        "distribution_diversity": families.counts(),
        "partial_observability": {"hidden_dynamic_fraction_mean": statistics.mean(hid) if hid else None,
                                  "note": "the fraction of placement/open facts the observation text does not mention; the host reads the facts, the person reads the text"},
    }
    os.makedirs(os.path.join(HERE, "records"), exist_ok=True)
    p = os.path.join(HERE, "records", "complexity-%s-%s.json" % (a.split, a.task))
    json.dump(vec, open(p, "w"), indent=1)
    print(json.dumps({k: v for k, v in vec.items() if k != "distribution_diversity"}, indent=1))
    print(p)
    return 0


if __name__ == "__main__":
    sys.exit(main())
