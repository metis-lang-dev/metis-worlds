"""store — the map file: one JSON document per world run (beside the world's run directory), one writer at a time,
read again when another process wrote it (an mtime cache), and a journal beside it.

The document's keys are the adapter's (a room's places and things, a grid's cells), with the ones every adapter
shares: `belief` {thing: {place: p}}, `exists` {thing: log-odds}, `binding` {role: world name}, `k` (the capacity),
`agent` (the ego)."""
import json
import os
import time


class Store:
    def __init__(self, path, journal=None):
        """path: the map file; journal: a JSON-lines file the store appends its events to (None: no journal)."""
        self.path, self.data, self._mtime = path, None, None
        self.journal = journal

    def load(self):
        """The document as it is on disk (read again when the file changed), else as held."""
        try:
            t = os.stat(self.path).st_mtime_ns
        except OSError:
            return self.data
        if t != self._mtime:
            with open(self.path) as f:
                self.data = json.load(f)
            self._mtime = t
        return self.data

    def save(self):
        tmp = self.path + ".tmp"
        with open(tmp, "w") as f:
            json.dump(self.data, f, indent=1, sort_keys=True)
        os.replace(tmp, self.path)
        self._mtime = os.stat(self.path).st_mtime_ns

    def log(self, kind, **rec):
        """One journal row: {t, kind, …} (the binding's changes, the evidence folded in)."""
        if not self.journal:
            return
        with open(self.journal, "a") as f:
            f.write(json.dumps(dict({"t": round(time.time(), 3), "kind": kind}, **rec), sort_keys=True) + "\n")
