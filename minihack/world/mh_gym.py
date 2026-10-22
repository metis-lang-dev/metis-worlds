"""mh_gym.py — one MiniHack level as a child process (world-minihack step 1): JSON lines
on stdin/stdout, so the host steps NLE from the domain agent's process without NLE there.

  {"op": "open", "des": DES_TEXT | "env": ENV_ID, "actions": [names]?, "max_steps": N, "seed": S}
      -> {"cells": [...], "size": [w, h], "actions": [names], "init": perceive}
  {"op": "reset", "seed": S}         -> perceive + {"done": false}
  {"op": "step", "action": NAME}      -> perceive + {"reward", "done", "won"}
  {"op": "close"}

perceive = {"atoms", "events", "message", "names"} (perceive.py). Actions are named by
NLE's Command / CompassDirection members ("N", "E", "PICKUP", "EAT", "APPLY", "DOWN", …);
the skill environment's 85 actions by default.
"""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)


class World:
    def __init__(self):
        self.env, self.p, self.names = None, None, []

    def open(self, des=None, env_id=None, actions=None, max_steps=100, seed=1):
        import gymnasium as gym, minihack  # noqa: F401
        from nle import nethack
        from perceive import Perceiver
        keys = ("glyphs", "chars", "message", "blstats", "inv_strs", "inv_letters")
        kw = {"observation_keys": keys, "max_episode_steps": int(max_steps)}
        if actions:
            table = {m.name: m for m in list(nethack.CompassDirection) + list(nethack.Command) + list(nethack.MiscDirection) + list(nethack.MiscAction)}
            kw["actions"] = tuple(table[a] for a in actions)
        if des:
            self.env = gym.make("MiniHack-Skill-Custom-v0", des_file=des, **kw)
        else:
            self.env = gym.make(env_id, **kw)
        self.names = [getattr(a, "name", str(a)) for a in self.env.unwrapped.actions]
        obs, info = self._reset(seed)
        self.p = Perceiver(obs["chars"])
        per = self.p.perceive(obs)
        return {"cells": self.p.cells(), "size": [self.p.w, self.p.h], "actions": self.names, "init": per}

    def _reset(self, seed):
        """A deterministic episode: NLE's own seeding (core, disp, reseed=False) before the reset —
        gymnasium's reset(seed) alone does not pin NetHack's RNG, so a replay diverged."""
        u = self.env.unwrapped
        if hasattr(u, "seed"):
            try:
                u.seed(int(seed), int(seed), False)
            except TypeError:
                u.seed(core=int(seed), disp=int(seed), reseed=False)
        return self.env.reset()

    def reset(self, seed=1):
        obs, info = self._reset(seed)
        self.p.seen_traps = {}
        out = self.p.perceive(obs)
        out.update({"done": False, "won": False, "reward": 0.0})
        return out

    def step(self, action):
        i = self.names.index(action)
        obs, r, term, trunc, info = self.env.step(i)
        out = self.p.perceive(obs)
        won = bool(term and r > 0)
        out.update({"reward": float(r), "done": bool(term or trunc), "won": won, "end_status": str(info.get("end_status", ""))})
        return out


def main():
    w = World()
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            req = json.loads(line)
            op = req.get("op")
            if op == "close":
                print(json.dumps({"ok": True}), flush=True)
                return 0
            if op == "open":
                out = w.open(req.get("des"), req.get("env"), req.get("actions"), req.get("max_steps", 100), req.get("seed", 1))
            elif op == "reset":
                out = w.reset(req.get("seed", 1))
            elif op == "step":
                out = w.step(req["action"])
            else:
                raise ValueError("unknown op %r" % op)
            out["ok"] = True
        except Exception as e:  # noqa: BLE001
            out = {"ok": False, "error": "%s: %s" % (type(e).__name__, e)}
        print(json.dumps(out), flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
