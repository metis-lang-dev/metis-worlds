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

## The query API (map-queries s-396939dc step 1)

The only faces a program's host and the dialog read the map through (`core.SemanticMap`):

| entry | side | what |
|---|---|---|
| `bind(kind, constraints)` → `[entries]` | dialog | the map's entries a person's word can mean: the entry itself, else the places and things of that kind (`tomato` → `tomato1`, `tomato2`; a thing only once seen, in view mode), else a wanted entry; `{"in": place}` keeps those seen or believed there |
| `level(pred, args)` → level | tick | a standing level port, from the adapter's `LEVELS`; the room's `presence(thing)`: the existence belief quantised at 0.3 / 0.7 (improbable, doubtful, likely) |
| `weight(pred, args)` → p | tick | a standing categorical port: `look` / `where` over (object role, place role) read the place belief; the room's search feeds `look` as 1 on `next()`'s place and 0 elsewhere (the port stays spec 16's categorical port, degenerate), so it visits places most likely first |
| `next(kind, excluded)` → place / None | tick | the argmax of the kind's place belief, ties by the place's id: a function of the map's state |
| `observe(atoms)` | tick | the update (the cycle above) |

**The prior.** An adapter's `prior(thing)` gives the belief before a sighting. The core's own is uniform over the map's places, and logged (`prior-fallback`): a kind with no prior is never a silent `{}`. An empty belief is reserved for a search that has looked everywhere (`lost`).

The room's prior for a kind not seen yet is the per-place rate
`rate(kind, type(place)) = starts(kind, type) / receptacles(type)`. Here starts is the number of ALFWorld games
whose initial state puts the kind in or on that receptacle type, and receptacles is the number of receptacles of
that type across the scenes (`alfworld/world/starts.json`, made by `world/gen_tables.py`). The rate is taken over
the room's places that can hold the kind (cancontain), and normalised over them: `P(place) = rate(place) /
Σ rate`. A compatible type with no starts gets half the smallest rate. A kind the compatibility never names gets
the uniform fallback, logged. Each look updates the belief by Bayes, unchanged.

A cost-aware order (belief per unit of effort: opening a cabinet costs more than a glance at a countertop) is the
next refinement, noted and not built.

| module | what |
|---|---|
| `store` | the map file: JSON beside the world's run, one writer, an mtime cache, and a journal beside it |
| `core` | the cycle every adapter shares (`cycle`, `observe`, `sync`, `role_reading`, the binding's faces) and the hooks an adapter fills in |
| `bayes` | predict (dt a float), walk (a fractional speed or dt mixes in the next step), seen, missed (weighed by the mass taken), exists, normalized; `reachable` (the reachable-set model: the mass spread evenly over the places inside the mover's kinematic interval for dt, speed range × time with braking and acceleration bounds, RSS's worst case; `interval`, `mass_within` for a P(hazard) reading); `associate` (the gate: a sighting of a kind is the instance whose predicted mass is near it, else a new one, kind_2, …) |
| `project` | stable slots and location roles, freeze |
| `ports` | translate, sync_diff, in_room, say_in_roles, names |
| `room` | the adapter for a household of receptacles (ALFWorld): THOR's names, the world card, the receptacle kinds, the projection's ranking (target, dest, p0, p1..pk, the locations), view mode (the cancontain prior, believed / absent / lost) |
| `grid` | the adapter for a level of cells (NetHack, MiniHack): the segment graph (areas, lanes, junctions, gates, dead ends, frontier), sight, a route with gate costs, the movers' models (a hostile chases the ego along the map at its known speed, a peaceful holds; with the cells known, a beast not seen in view is not there), the stable projection (goal, p1..pk, b1 b2, target), the facts between bound cells (`next`, `toward`, `step`, `door`, `stairs_down`, the segment kinds), `describe(thing)` (where a beast is believed, in the world's words) |
| `situation` | the RSS layer, world-independent: a pair per (ego, object) with its constellation (same_dir, opp_dir, xing_*, unstructured, not_relevant), positions and gaps; the host-evaluated `safe_long` / `safe_lat` (Lemmas 2–4), `able_to_stop`, `no_time_overlap` (Def 17); the memory of the axis safe before (Def 10/18: rewritten while safe, frozen while dangerous); the response per pair and the fold (the most severe response, the restrictions intersected); `facts` over the bound roles. The numbers never reach the rules |
| `lane` | the road's adapter skeleton: lanes with neighbours and directions, (lane, s) positions, routes, conflict zones with priority, and the situation pairs they make (no road runtime); speed limits and shapes, routes through internal lanes, the nearest zone, objects' ways merged per junction, a light's phase as priority, the per-vClass `dynamics_for` with the lane's vcap |
| `net` | a SUMO `.net.xml` → the lane map: lanes (length, speed, width, shape, allow), connections with their internal chains, junction link rows (foes, response), traffic-light programs, and the conflict zones from the internal lanes' overlaps with their priority |
| `dungeon` | an exerciser, not a world: cave and rooms-and-corridors levels (from the published algorithm, never NetHack's NGPL source), monsters (a float speed: a newt at 0.5), sight, NLE's perception; `corner()` (a lit room, a dark corridor round a corner); `Level.des()` makes the same level a MiniHack des, `Level.cells()` the grid's known cells |

`examples/bayes_cases.py OUT` runs design §4's cases 6 and 8 on the exerciser (a newt lost behind a corner,
re-found by the walk; its belief spread by the model and cut by the empty view) and writes the turns, the lines
(`GridMap.describe`) and the map's journal.

The library never knows a world's names or a rule program. Adapters do.

Design: semantic-world s-227b8e1b `brief/semantic-world-design.md`. The first consumer is
`alfworld/world/semantic_map.py`, which re-exports `room` and keeps the parts that need the game. The second
consumer is minihack (`grid`). On the grid the situation layer runs with reach for braking distance (`GridMap.pairs`,
`GridMap.hazard`; the route's refuge and avoid modes give the passing place and the way round), and the association
gate names beasts that look alike.

`examples/situation_cases.py OUT` runs design §4's cases 4 and 5 on the exerciser's `dungeon.lanes()` with a rule
program over roles (metispy's REPL): an oncoming hostile in a one-wide lane (stop at the gap of both reaches, fall
back to the last area, fight it there) and a peaceful standing in the lane (yield at the safe gap, wait three turns,
back off to the junction, take the other way).

## The mixed adapter: one map (wc-world s-db2f8e59, the wheelchair DESIGN v5 §12 position 1)

`mixed.MixedMap` is ONE `core.SemanticMap` over two geometries: lane SEGMENTS (road.RoadMap's lane bins over a
`lane.LaneMap`: the roads and the crosswalks) and free-space CELLS (sidewalks, paths, plazas, walking areas). Its places
belong to ZONES (`sidewalk | crossing | lane | path | plaza`), and zones connect only through declared LINKS (`open`,
`ramp` passable at `slow`, `curb` impassable): one place set, one belief store, one role binding (core's). Built from
data (`MixedMap.build(path, lanemap, cells, zones, links)`) or from a SUMO net read with crossings and walking areas
kept (`net.load_net(path, walking=True)`, then `MixedMap.from_net`).

One map is one INSTANCE at runtime: in the wheelchair composition every domain that runs (responder, planner, nav, wc)
reads the one MixedMap. `LaneMap.roles` stays the lane ROLE BINDER: a binder over this map's places that writes into
the one binding, never a second binding. When the road members run on the MixedMap (the wc-member subject), road's
`road_facts` reads its lane roles from the map's binding; that change lands there, with the test that asks for it.
Today the road world (`road_world`, the SUMO host) still runs on `LaneMap` and `RoadMap` directly, unchanged.

## Install

It lives in metis-worlds (`libs/semantic-world`) until the road returns, and is then cut out to its own repo.
Each world's `setup.sh` installs it editable into the world's venv
(`pip install -e libs/semantic-world`), and metis-agent's venv does the same (`py/README.md`), since the worlds'
hosts run in the agent's process.

## Test

`python -m pytest -q tests` in a python that has this library installed (`pip install -e libs/semantic-world`: a branch's own, for a branch; the cases test runs where metispy is importable)
