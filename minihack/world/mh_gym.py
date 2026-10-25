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


def map_size(des):
    """The MAP block's width and height, so the perceiver's grid covers rooms not yet seen."""
    lines = des.split("\n")
    if "MAP" not in lines:
        return None
    rows = lines[lines.index("MAP") + 1:lines.index("ENDMAP")]
    return (max(len(r) for r in rows), len(rows))


def map_start(des):
    """The robot's start cell in the MAP's coordinates when the des pins it to one cell (BRANCH:(x,y,x,y)), else None."""
    import re
    m = re.search(r"^BRANCH:\s*\((\d+),\s*(\d+),\s*(\d+),\s*(\d+)\)", des, re.M)
    if m and m.group(1) == m.group(3) and m.group(2) == m.group(4):
        return int(m.group(1)), int(m.group(2))
    return None


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
            acts = [table[a] for a in actions]
            by_code = {int(a): a for a in nethack.ACTIONS}
            for c in "abcdefghijklmnopqrstuvwxyz":        # inventory letters and y/n answers, sent by key code
                if ord(c) not in {int(a) for a in acts}:
                    acts.append(by_code[ord(c)])
            kw["actions"] = tuple(acts)
        if des:
            self.env = gym.make("MiniHack-Skill-Custom-v0", des_file=des, **kw)
        else:
            self.env = gym.make(env_id, **kw)
        self.names = [getattr(a, "name", str(a)) for a in self.env.unwrapped.actions]
        self.codes = [int(a) for a in self.env.unwrapped.actions]
        obs, info = self._reset(seed)
        self.p = Perceiver(obs["chars"], size=map_size(des) if des else None, start=map_start(des) if des else None)
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

    def _step(self, i):
        obs, r, term, trunc, info = self.env.step(i)
        out = self.p.perceive(obs)
        won = bool(term and r > 0)
        out.update({"reward": float(r), "done": bool(term or trunc), "won": won, "end_status": str(info.get("end_status", ""))})
        return out

    def step(self, action):
        """An action name; `KEY:c` sends the key c (an inventory letter, y/n); `UNLOCK:DIR` is the
        macro NetHack's apply needs (M3): APPLY, the skeleton key's letter, the direction, y."""
        if action.startswith("KEY:"):
            return self._step(self.codes.index(ord(action[4:5])))
        if action.startswith("UNLOCK:"):
            out = self._step(self.names.index("APPLY"))
            letter = self.env.unwrapped.key_in_inventory("key")   # unidentified, the inventory says "key"
            if letter is None or out["done"]:                # "You don't have anything to use or apply."
                return out
            out = self._step(self.codes.index(ord(letter)))   # "In what direction?"
            if out["done"]:
                return out
            out = self._step(self.names.index(action[7:]))    # "Unlock it? [yn]" — or "Lock it?" on an unlocked door
            if out["done"]:
                return out
            if "unlock it" in out.get("message", "").lower():
                return self._step(self.codes.index(ord("y")))
            return self._step(self.codes.index(ord("n")))     # never lock a door the agent could open (N2)
        return self._step(self.names.index(action))


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
