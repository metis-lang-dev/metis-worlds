"""world — same agent, next map (rooms s-b51a2e80): named maps, one active. A room of a house, a level of a dungeon, a
segment of a road, one of a wheelchair's nets: the programs are compiled over roles and do not change, only the map
under them does.

    World(maps, active)            maps in memory: {name: map}
    World(path=FILE, make=Map)     maps on disk: FILE names them and the active one, and every World open on it follows
                                   an enter made through another (a host per domain, each with its own copy)

`enter(name)` makes NAME active. Everything else — the query API (bind / level / weight / next / observe), the cycle, the
map's document, its `names` — is the active map's, reached through this object as through the map itself, so this
class's own attributes must never shadow a map's (a test holds them apart). A map's state (its belief, what was looked
into, where things were left) is the map's own, so it is as it was on return.

The caller decides when: an enter is a world event, applied between ticks, so no host reads two maps in one tick."""
import json
import os
import time


class World:
    def __init__(self, maps=None, active=None, path=None, make=None):
        if path and not make:
            raise ValueError("a World on disk needs make: the class that opens one of its map files")
        self._maps, self._files, self._active = dict(maps or {}), {}, active
        self._path, self._make, self._mtime = path, make, None
        if active is not None and not path and active not in self._maps:
            raise KeyError("no map %r here (it has: %s)" % (active, ", ".join(sorted(self._maps)) or "none"))
        self._read()

    # ── on disk ──
    def _read(self):
        """The file as another World open on it left it (read again when it changed)."""
        if not self._path:
            return
        try:
            t = os.stat(self._path).st_mtime_ns
        except OSError:
            return
        if t != self._mtime:
            with open(self._path) as f:
                d = json.load(f)
            self._files, self._active, self._mtime = d["maps"], d["active"], t

    def _write(self):
        tmp = self._path + ".tmp"
        with open(tmp, "w") as f:
            json.dump({"active": self._active, "maps": self._files}, f, indent=1, sort_keys=True)
        os.replace(tmp, self._path)
        self._mtime = os.stat(self._path).st_mtime_ns

    # ── the maps ──
    def add_map(self, name, m):
        """A map under NAME: the map itself, or on disk the file it lives in. Its state is untouched."""
        self._read()
        if self._path:
            self._files[name] = os.path.abspath(m)
            self._maps.pop(name, None)
            self._write()
        else:
            self._maps[name] = m

    def map_names(self):
        self._read()
        return sorted(self._files if self._path else self._maps)

    @property
    def active(self):
        """The active map's name, or None."""
        self._read()
        return self._active

    def __contains__(self, name):
        return name in self.map_names()

    def map_named(self, name):
        """The map NAME, active or not."""
        self._read()
        if self._path and name in self._files and name not in self._maps:
            self._maps[name] = self._make(self._files[name])
        if name not in self._maps:
            raise KeyError("no map %r here (it has: %s)" % (name, ", ".join(self.map_names()) or "none"))
        return self._maps[name]

    @property
    def map(self):
        """The active map."""
        name = self.active
        if name is None:
            raise LookupError(self._none())
        return self.map_named(name)

    def _none(self):
        return "this World has no active map: enter one (it has: %s)" % (", ".join(self.map_names()) or "none")

    def enter(self, name):
        """NAME becomes the active map, its state as it was left. → the map."""
        m = self.map_named(name)
        was = self.active
        self._active = name
        if self._path:
            self._write()
        log = getattr(m, "log", None)
        if callable(log):
            log("enter", map=name, left=was, t_enter=round(time.time(), 3))
        return m

    def __getattr__(self, attr):
        """What is not the World's is the active map's: the query API, the cycle, the document."""
        if attr.startswith("_"):
            raise AttributeError(attr)
        name = self.active
        if name is None:
            raise AttributeError(self._none())
        return getattr(self.map_named(name), attr)


def open_map(path, make):
    """The map a host reads at PATH: a World when the file is one (`*.world.json`), else the map itself."""
    return World(path=path, make=make) if str(path).endswith(".world.json") else make(path)
