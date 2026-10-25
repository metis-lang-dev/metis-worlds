# semantic-world

A host library for rule programs over a role vocabulary: the semantic map, its Bayesian update, the projection
of roles onto the world's names, and the port contract between them and the program. Pure Python, no dependency.

A world's host runs one cycle every turn:

1. **predict** (`bayes.predict`): the movers' motion over dt turns (a float). Identity for a household, whose
   things move only by the robot's hand. A model per mover is the hook (`grid.models`: a hostile beast chases
   the ego along the map at its speed, a peaceful one holds).
2. **observe** (`bayes.seen`, `bayes.missed`): a sighting collapses the belief. A place looked into without the
   thing is negative evidence: 0 there, the rest renormalized, and the prior again when nothing is left. A place
   not looked into is unchanged. `exists` keeps a log-odds per thing: a sighting raises it, a miss lowers it by
   log(1 − p) for the mass p the place held, and the alive decay lowers it per turn unseen.
3. **project** (`project.stable_slots`, `stable_locations`): the roles are bound to the world's names, per goal,
   stably. A name keeps its role while it is in the working set. A domain reads the binding of its activation
   (`freeze`).
4. **sync** (`ports.sync_diff`, `ports.translate`): the facts between bound roles are retracted and asserted
   on the live session, with no recompile. The weight ports read the belief (`bayes.normalized`).
5. **the program's turn** happens outside the library. Its intents come back through `ports.say_in_roles` and
   `ports.in_room`, and `names` gives name(role, thing) for the voice and the page.

| module | what |
|---|---|
| `store` | the map file: JSON beside the world's run, one writer, an mtime cache, and a journal beside it |
| `core` | the cycle every adapter shares (`cycle`, `observe`, `sync`, `role_reading`, the binding's faces) and the hooks an adapter fills in |
| `bayes` | predict (dt a float), walk (a fractional speed or dt mixes in the next step), seen, missed (weighed by the mass taken), exists, normalized |
| `project` | stable slots and location roles, freeze |
| `ports` | translate, sync_diff, in_room, say_in_roles, names |
| `room` | the adapter for a household of receptacles (ALFWorld): THOR's names, the world card, the receptacle kinds, the projection's ranking (target, dest, p0, p1..pk, the locations), view mode (the cancontain prior, believed / absent / lost) |
| `grid` | the adapter for a level of cells (NetHack, MiniHack): the segment graph (areas, lanes, junctions, gates, dead ends, frontier), sight, a route with gate costs, the movers' models (a hostile chases the ego along the map at its known speed, a peaceful holds; with the cells known, a beast not seen in view is not there), the stable projection (goal, p1..pk, b1 b2, target), the facts between bound cells (`next`, `toward`, `step`, `door`, `stairs_down`, the segment kinds), `describe(thing)` (where a beast is believed, in the world's words) |
| `dungeon` | an exerciser, not a world: cave and rooms-and-corridors levels (from the published algorithm, never NetHack's NGPL source), monsters (a float speed: a newt at 0.5), sight, NLE's perception; `corner()` (a lit room, a dark corridor round a corner); `Level.des()` makes the same level a MiniHack des, `Level.cells()` the grid's known cells |

`examples/bayes_cases.py OUT` runs design §4's cases 6 and 8 on the exerciser (a newt lost behind a corner,
re-found by the walk; its belief spread by the model and cut by the empty view) and writes the turns, the lines
(`GridMap.describe`) and the map's journal.

The library never knows a world's names or a rule program. Adapters do.

Design: semantic-world s-227b8e1b `brief/semantic-world-design.md`. The first consumer is
`alfworld/world/semantic_map.py`, which re-exports `room` and keeps the parts that need the game. The second
consumer is minihack (`grid`). The situation layer comes next.

## Install

It lives in metis-worlds (`libs/semantic-world`) until the road returns, and is then cut out to its own repo.
Each world's `setup.sh` installs it editable into the world's venv
(`pip install -e libs/semantic-world`), and metis-agent's venv does the same (`py/README.md`), since the worlds'
hosts run in the agent's process.

## Test

`python -m pytest -q tests`
