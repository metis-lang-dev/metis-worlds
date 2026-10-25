"""semantic_world — a host library for rule programs over a role vocabulary (semantic-world s-227b8e1b).

The cycle a world's host runs every turn: predict (bayes, the movers' motion) → observe (bayes, with negative
evidence) → project (the roles bound to the world's names, stable, frozen per activation) → sync (ports: the facts
between bound roles retracted and asserted on the live session, the weight ports' readings) → the program's turn →
an intent back in the world's terms.

    store    the map file (mtime cache, one writer) and its journal
    core     the cycle every adapter shares: cycle / observe / sync / role_reading, the adapter's hooks
    bayes    predict / seen / missed, exists log-odds
    project  stable slots and location roles, freeze
    ports    translate, sync_diff, in_room, say_in_roles, names
    room     the adapter for a household of receptacles (ALFWorld)
    grid     the adapter for a level of cells (NetHack, MiniHack): the segment graph, the route, sight, the movers
    dungeon  a pure-python exerciser: cave and rooms levels, monsters, sight, NLE's perception

Pure python, no dependency: the library never knows a world's names or a rule program; adapters do."""
from . import bayes, core, ports, project, store  # noqa: F401  (room, grid, dungeon: imported by name)
from .store import Store  # noqa: F401

__version__ = "0.1.0"
