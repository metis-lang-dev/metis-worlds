"""alf_gym.py — one ALFWorld text game as a child process (world-alfworld step 1): JSON
lines on stdin/stdout, so the host (alf_host.py) steps the game from the domain agent's
process without ALFWorld in that process's environment. Run under the world's venv.

  {"op": "open", "game": PATH, "max_steps": N, "handles": {to_name, kind}?, "room": bool?}   (the package's map, reused)
      -> {"task_type", "params", "handles": {to_name, kind}, "static": [atoms], "init": [atoms],
          "admissible": [commands], "obs": text}
  {"op": "reset"}                 -> {"dynamic": [atoms], "admissible", "obs", "won", "done"}
  {"op": "step", "command": TEXT} -> {"dynamic", "admissible", "obs", "won", "done", "changed": bool}
  {"op": "close"}

`dynamic` is the full reading of the game's dynamic facts after the step (ground.py's
atoms); `changed` says whether any fact changed — "Nothing happens." leaves them as they
were, which is how the world refuses a command.

`room` (alf-tasks s-e9cc8fae step 1): the game is the carrier of a room's state only. TextWorld's gym env stops
once the episode's own goal holds (its batch wrapper: every later step repeats the last observation, the facts
frozen), so a room is played on the PDDL env underneath (`textworld.start`), which keeps stepping: `won` is still
read (the episode's goal, reported), `done` never ends the session, and the tasks the person gives are checked
by the hierarchy itself.
"""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from ground import Handles, atoms_of  # noqa: E402


class Game:
    def __init__(self):
        self.env, self.handles, self.room = None, None, False

    def open(self, game, max_steps=60, handles=None, room=False):
        import textworld, textworld.gym
        infos = textworld.EnvInfos(facts=True, won=True, admissible_commands=True, extras=["gamefile"])
        self.room = bool(room)
        if self.room:                            # the PDDL env itself: no episode end (the module's `room`)
            self.env = textworld.start(game, infos)
        else:
            env_id = textworld.gym.register_games([game], infos, max_episode_steps=int(max_steps), name="metis")
            self.env = textworld.gym.make(env_id)
        self.handles = Handles.from_json(handles) if handles else Handles()
        traj = json.load(open(os.path.join(os.path.dirname(game), "traj_data.json")))
        obs, info = self._reset()
        static, dynamic = atoms_of(info["facts"], self.handles)
        self.last = set(dynamic)
        return {"task_type": traj.get("task_type"), "params": traj.get("pddl_params", {}),
                "desc": (traj.get("turk_annotations", {}).get("anns") or [{}])[0].get("task_desc"),
                "handles": self.handles.as_json(), "static": static, "init": dynamic,
                "admissible": list(info["admissible_commands"]), "obs": obs}

    def _out(self, obs, info, changed=None):
        _, dynamic = atoms_of(info["facts"], self.handles)
        now = set(dynamic)
        if changed is None:
            changed = now != self.last
        self.last = now
        return {"dynamic": dynamic, "admissible": list(info["admissible_commands"]), "obs": obs,
                "won": bool(info.get("won")), "done": bool(info.get("won")), "changed": bool(changed)}

    def _reset(self):
        if self.room:
            st = self.env.reset()
            return st.feedback, st
        return self.env.reset()

    def reset(self):
        obs, info = self._reset()
        self.last = None
        return self._out(obs, info, changed=True)

    def step(self, command):
        if self.room:                            # `won`: the episode's goal, reported; the room never ends
            st, _, _ = self.env.step(command)
            out = self._out(st.feedback, st)
            out["done"] = False
            return out
        obs, score, done, info = self.env.step(command)
        out = self._out(obs, info)
        out["done"] = bool(done or out["won"])
        return out


def main():
    g = Game()
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
                out = g.open(req["game"], req.get("max_steps", 60), req.get("handles"), bool(req.get("room")))
            elif op == "reset":
                out = g.reset()
            elif op == "step":
                out = g.step(req["command"])
            else:
                raise ValueError("unknown op %r" % op)
            out["ok"] = True
        except Exception as e:  # noqa: BLE001
            out = {"ok": False, "error": "%s: %s" % (type(e).__name__, e)}
        print(json.dumps(out), flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
