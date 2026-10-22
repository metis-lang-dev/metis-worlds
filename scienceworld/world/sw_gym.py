"""sw_gym.py — one ScienceWorld task variation as a child process (world-scienceworld step 1): JSON
lines on stdin/stdout, so the host steps the simulator (a Java jar over py4j) from the domain
agent's process without ScienceWorld in that process's environment. Run under the world's venv.

  {"op": "open", "task": NAME, "variation": N, "simplification": "easy", "max_steps": N}
      -> {"desc", "task_atoms", "init": perception, "valid": [...], "names": [every object referent the simulator knows: the VOCABULARY, no properties],
          "splits": {"train": [...], "dev": [...], "test": [...]}}
  {"op": "reset"}                 -> perception + {"reward", "score", "done", "won"}
  {"op": "step", "command": TEXT} -> the same after the step; an ambiguous referent is answered with its first reading
  {"op": "gold"}                  -> {"gold": [actions]}      (the simulator's own solution: the baseline, never the agent's input)
  {"op": "oracle"}                -> {"tree": …}             (the object tree with the hidden properties: tests and measurements only)
  {"op": "close"}
"""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from perceive import perceive, task_atoms  # noqa: E402


class World:
    def __init__(self):
        self.env = None

    def open(self, task, variation=0, simplification="easy", max_steps=100):
        from scienceworld import ScienceWorldEnv
        self.env = ScienceWorldEnv("", envStepLimit=int(max_steps))
        self.task, self.variation, self.simplification = task, int(variation), simplification
        self.env.load(task, int(variation), simplificationStr=simplification, generateGoldPath=True)
        out = self.reset()
        desc = self.env.get_task_description()
        self.desc = desc
        names = self._names()
        return {"desc": desc, "task_atoms": task_atoms(desc), "init": out, "valid": out["valid"], "names": names,
                "splits": {"train": self.env.get_variations_train(), "dev": self.env.get_variations_dev(), "test": self.env.get_variations_test()}}

    def _names(self):
        """Every referent the simulator knows, as the perceiver would name it: the vocabulary for a
        package's `thing` type (names only — nothing of the tree's properties leaves this process), one
        name per thing (perceive.vocabulary: no qualified spellings, a part owner-first)."""
        from perceive import vocabulary
        try:
            lut = self.env.get_all_object_ids_types_referents_LUTJSON()
            if isinstance(lut, (str, bytes)):
                lut = json.loads(lut)
            return vocabulary(r for v in lut.values() for r in (v.get("referents") or []))
        except Exception:
            return []

    def _out(self, obs, info, reward=0.0, done=False):
        p = perceive(info.get("look", ""), info.get("inv", ""), obs)
        score = float(info.get("score", 0.0))
        won = score >= 100.0 or (done and score >= 100.0)
        p.update({"reward": float(reward), "score": score, "done": bool(done or won), "won": won,
                  "valid": list(info.get("valid") or []), "moves": int(info.get("moves", 0))})
        return p

    def reset(self):
        obs, info = self.env.reset()
        return self._out(obs, info)

    def step(self, command):
        obs, reward, done, info = self.env.step(command)
        if obs.startswith("Ambiguous request"):            # the first reading (the world's own order)
            obs, reward, done, info = self.env.step("0")
        return self._out(obs, info, reward, done)

    def gold(self):
        return {"gold": list(self.env.get_gold_action_sequence())}

    def oracle(self):
        return {"tree": self.env.getObjectTree()}

    def close(self):
        try:
            self.env.close()
        except Exception:
            pass


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
                w.close()
                print(json.dumps({"ok": True}), flush=True)
                return 0
            if op == "open":
                out = w.open(req["task"], req.get("variation", 0), req.get("simplification", "easy"), req.get("max_steps", 100))
            elif op == "reset":
                out = w.reset()
            elif op == "step":
                out = w.step(req["command"])
            elif op == "gold":
                out = w.gold()
            elif op == "oracle":
                out = w.oracle()
            else:
                raise ValueError("unknown op %r" % op)
            out["ok"] = True
            print(json.dumps(out), flush=True)
        except Exception as e:  # noqa: BLE001
            print(json.dumps({"ok": False, "error": "%s: %s" % (type(e).__name__, e)}), flush=True)
    w.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
