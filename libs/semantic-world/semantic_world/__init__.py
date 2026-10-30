"""semantic_world — a host library for rule programs over a role vocabulary (semantic-world s-227b8e1b).

The cycle a world's host runs every turn: predict (bayes, the movers' motion) → observe (bayes, with negative
evidence) → project (the roles bound to the world's names, stable, frozen per activation) → sync (ports: the facts
between bound roles retracted and asserted on the live session, the weight ports' readings) → the program's turn →
an intent back in the world's terms.

    world    named maps, one active: enter(name), the query API on the active map (same agent, next map)
    store    the map file (mtime cache, one writer) and its journal
    core     the cycle every adapter shares: cycle / observe / sync / role_reading, the adapter's hooks
    bayes    predict / seen / missed, exists log-odds; the reachable set (RSS's worst case); the association gate
    project  stable slots and location roles, freeze
    ports    translate, sync_diff, in_room, say_in_roles, names
    room     the adapter for a household of receptacles (ALFWorld)
    grid     the adapter for a level of cells (NetHack, MiniHack): the segment graph, the route, sight, the movers
    dungeon  a pure-python exerciser: cave, rooms and lanes levels, monsters, sight, NLE's perception
    situation the RSS layer: pairs, safe distances, the memory of the axis safe before, the fold, facts over roles
    lane     the road's adapter skeleton: lanes, (lane, s) positions, conflict zones, the pairs
    road     the lane adapter's belief: tracks over lane bins, intents, the association, the danger region
    mixed    the ONE map over lane segments and free-space cells, zones and their links (the wheelchair's world)
    occupancy the mixed map's predict step over a horizon, a time-indexed occupancy; its zones on a grid aligned to its cells

Pure python, no dependency: the library never knows a world's names or a rule program; adapters do."""
from . import bayes, core, ports, project, store  # noqa: F401  (room, grid, dungeon, situation, lane: imported by name)
from .store import Store  # noqa: F401

__version__ = "0.1.0"
