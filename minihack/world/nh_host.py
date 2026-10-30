"""nh_host.py — the real game under the hierarchy's rules: MhHost with nh_gym.py as its world, and the faces the page and
the person use. The level is unknown until seen (view mode), a new dungeon level or game starts the map again, and the
game is never replayed or reset: it is one game, the person's and the agent's.
"""
import os

from metis.host import GymChild

from mh_host import HERE, SHARED, MhHost, interpreter

EVENTS = ["blocked", "see_here", "door_here", "door_closed", "door_opened", "door_locked", "door_stuck", "whamm", "killed", "hit", "hurt", "fell_pit",
          "trap_door", "ate", "picked", "nothing_here", "cant", "hunger", "died", "welcome", "stopped", "nevermind", "prompt", "asked", "other"]


class NhGym(GymChild):
    def __init__(self, level):
        super().__init__(os.path.join(HERE, "nh_gym.py"), interpreter(), "game", open_args={"map_doc": level.get("map_doc"), "card": level.get("card")})


class NhHost(MhHost):
    def client(self):
        return NhGym(self.level)

    def _take(self, out, fresh=True):
        if fresh and getattr(self, "cmap", None) is not None and self.key in SHARED:
            sh, at = SHARED[self.key], (out.get("dlvl"), out.get("game"))
            if at[0] is not None:
                if sh.get("at") not in (None, at):       # another level or another game: its map is its own
                    self.start_map()
                sh["at"] = at
        super()._take(out, fresh)

    def start_map(self):
        from semantic_world.grid import GridMap
        k = self.cmap.load()["k"]
        GridMap.build(self.level["map"], self.level["size"], view=True, k=k)

    def world(self, lines):
        """The person's keys, on the wire as world lines `key:<keys>`: the game takes them as typed."""
        for line in lines:
            if not line.startswith("key:"):
                raise ValueError("the real game takes keys (key:<keys>), not %r" % line)
            out = self.gym.call("keys", keys=line[4:])
            self.done = False
            self._take(out)
            self.pending_events += self.events

    def frames(self):
        return self.gym.call("frames")["frames"] if self.spec == "task" else []

    def observe(self, counts):
        """The watch's reading: what the session holds. A real game brings what no rule predicts every turn (a room seen as
        a door opens, a beast's own step), and until the loop has made this domain's rules that is no surprise to stop for:
        the world's reading still comes in, at the tick's sync."""
        return dict(counts)

    def reseed(self, seed):
        pass

    def restore(self, snap):
        self.beat, self.pending_events, self.handed = snap["beat"], list(snap["pending"]), list(snap["handed"])

    def ports(self):
        return {"level": {"size": self.gym.info["size"], "step": self.t, "done": self.done, "won": self.won}, "observed": [], "events": EVENTS,
                "actions": self.gym.info["actions"], "commands": []}


def make(case=None, package_dir=None):
    return NhHost(package_dir or os.getcwd(), case)
