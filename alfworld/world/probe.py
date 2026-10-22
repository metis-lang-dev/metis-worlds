"""probe.py — one ALFWorld text game, registered with its PDDL facts (world-alfworld step 1).

    ALFWORLD_DATA=data .venv/bin/python -m world.probe [--split train|valid_seen|valid_unseen] [--game N]

ALFWorld's own AlfredTWEnv registers games without `facts`; the host registers them
itself with textworld.EnvInfos(facts=True), so every step carries the full state as
Propositions (name, typed arguments) — the atoms of the world, no perception model.
"""
import argparse, os, sys, yaml
import textworld, textworld.gym
import alfworld.agents.environment as E

HERE = os.path.dirname(os.path.abspath(__file__))


def config(split="train"):
    cfg = yaml.safe_load(open(os.path.join(HERE, "..", "configs", "base_config.yaml")))
    ex = lambda s: os.path.expandvars(s) if isinstance(s, str) else s
    for k in ("data_path", "eval_id_data_path", "eval_ood_data_path"):
        cfg["dataset"][k] = ex(cfg["dataset"][k])
    for k in ("domain", "grammar"):
        cfg["logic"][k] = ex(cfg["logic"][k])
    return cfg


def games(split="train"):
    """The split's game files (ALFWorld's own listing)."""
    env = E.get_environment("AlfredTWEnv")(config(split), train_eval={"train": "train", "valid_seen": "eval_in_distribution", "valid_unseen": "eval_out_of_distribution"}[split])
    return env.game_files


def open_game(game_file, max_steps=50):
    infos = textworld.EnvInfos(facts=True, won=True, admissible_commands=True, extras=["gamefile"])
    env_id = textworld.gym.register_games([game_file], infos, max_episode_steps=max_steps, name="metis")
    return textworld.gym.make(env_id)


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--split", default="train")
    ap.add_argument("--game", type=int, default=0)
    a = ap.parse_args(argv)
    gs = games(a.split)
    print(f"{a.split}: {len(gs)} games; #{a.game}: {gs[a.game][-80:]}")
    g = open_game(gs[a.game])
    obs, info = g.reset()
    print("obs:", obs[:200].replace("\n", " | "))
    facts = list(info["facts"])
    print(f"facts: {len(facts)}; e.g. {[str(f) for f in facts[:4]]}")
    print("admissible:", info["admissible_commands"][:5])
    return 0


if __name__ == "__main__":
    sys.exit(main())
