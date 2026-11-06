# CommonRoad scenarios in the road world: terms and pins (commonroad-world s-9b7591fb, step 1)

The road world runs CommonRoad scenarios FROM A CHECKOUT, outside every repo (`$COMMONROAD_ROOT`), as CARLA's big towns
are built and kept untracked. Nothing of CommonRoad's (a scenario file, a converted net, a route, a picture) is
committed to any repo here, ever: the checkout is outside, the conversion cache is `../.worlds/cr-cache/` (COMMONROAD_CACHE, outside every repo), and
only the pins (below, in `road/setup-commonroad.sh`) and this note are tracked.

## The repositories and their pins

| what | where | pin | license |
|---|---|---|---|
| the scenarios | https://gitlab.lrz.de/tum-cps/commonroad-scenarios, branch `2020a_scenarios` | commit `2416dc27faf3ee36b6799f42712da72a34a2c8fd` (2021-11-26, "move recorded scenarios to one folder"; the repository's last tag is `Release_2018a`, 2019-04-24, so the pin is a commit) | BSD 3-Clause, `LICENSE.txt` |
| the interactive scenarios | https://gitlab.lrz.de/tum-cps/commonroad-interactive-scenarios, branch `master` | commit `749e342013cc069980039fa91ba587f62993aaaf` (2026-09-03; no tags) | BSD 3-Clause, `LICENSE` |

The scenario repository's README: its scenarios are "either obtained from real traffic data (NGSIM dataset) or
hand-crafted (mostly based on real road networks)", and it asks a user of CommonRoad to cite M. Althoff, M. Koschi
and S. Manzinger, "CommonRoad: Composable Benchmarks for Motion Planning on Roads", IEEE Intelligent Vehicles
Symposium 2017, pp. 719-726.

## Run one

Once: `road/setup-commonroad.sh` (the checkouts at their pins, the conversion venv). Then, headless, from metis-worlds (the Live's venv
is metis-agent's; METIS_HOME the road family at road/domains/catalog.pin):

    road/.venv-cr/bin/python road/tools/cr_convert.py ZAM_Tjunction-1_100_T-1      # into ../.worlds/cr-cache/ (optional: a run converts on demand)
    METIS_HOME=<metis-catalog>/domains/road ../metis-agent/py/.venv/bin/python road/experiments/road_tree.py cr:ZAM_Tjunction-1_100_T-1 1 --world sumo --ticks 1200 --out /tmp/cr --trace /tmp/cr/t

The run's summary is the last line (`director.cr`: the measures below). On the page (road/demo.sh), the Traffic dock's COMMONROAD SCENARIO
field takes an id and runs it on SUMO (`run:cr:ID:SEED`); a first run of an id converts it (a few seconds), an id that cannot be had is said.
Below it a search (`crfind:WORDS`: every word in the id, country, map, set, source or tags of index.json, the first 60 rows; a row marked `·` is
not converted yet) runs a scenario by a click. The goal regions show in the 3D view as flat slabs on the road; the dashboard shows the goal
(reached in its window, or the region's time out of it), the window, the contacts and the metres off the lanelets, live and at the end.

## The terms, as they read for this use

`commonroad-scenarios/LICENSE.txt` (read 2026-11-05 at the pin): Copyright 2019 Technical University of Munich,
Professorship of Cyber-Physical Systems. "Redistribution and use in source and binary forms, with or without
modification, are permitted provided that" (1) a redistribution of source keeps the copyright notice, the list of
conditions and the disclaimer; (2) a redistribution in binary form reproduces them in its documentation or other
materials; (3) neither the holder's name nor its contributors' may endorse or promote derived products without
prior written permission. Provided "as is", with no warranty and no liability. `commonroad-interactive-scenarios/
LICENSE` is the same BSD 3-Clause text, Copyright (c) 2023, the same professorship.

What that means here:
- **Use, conversion and a cached derived net are permitted.** Running a scenario, converting it to a SUMO net and
  routes, and keeping the result in the untracked cache is use and modification for ourselves, not a redistribution.
- **Nothing is redistributed, so no notice is owed in a repo.** Should a derived file ever be shipped (a fixture in a
  repo, an image in a release), it must carry the copyright notice, the conditions and the disclaimer above. This
  subject ships none.
- **No endorsement:** the TUM / CommonRoad names are not used to promote anything built here.
- **CI:** a test may fetch the two fixture scenarios from the pinned commit at run time (use, not redistribution);
  they are never committed.
- **The NGSIM-derived scenarios:** NGSIM is a public U.S. DOT (FHWA) dataset; the repository's BSD terms cover the
  files as distributed.

## The Python packages: the CONVERSION venv (the architect's ruling, 2026-11-05)

`road/setup-commonroad.sh` makes `road/.venv-cr` (git-ignored), the road world's only home of CommonRoad's packages, never the
Live's venv: their pins clash with it (sumocr 2024.1 asks libsumo/traci >= 1.19, the 2023.x pair numpy < 2 and Pillow < 9, which has
no Python 3.12 wheel). The venv converts; the Live reads only the cache's files. SUMO stays 1.18.0 (the system's netconvert makes the net).

| package | pin | license | note |
|---|---|---|---|
| `commonroad-io` | 2024.3 | BSD | the reader: lanelets, obstacles, planning problems, signs, lights |
| `commonroad-sumo` | 2025.1.4 | BSD 3-Clause (TUM CPS, 2023) | its `cr2sumo` map converter (lanelets → SUMO net through netconvert); it brings libsumo/traci 1.28 into the venv only, unused by the road |

`sumocr` 2024.1 (the brief's) has no map converter: it reads a scenario that ships its SUMO files; the converter moved to
`commonroad-sumo`. `commonroad-scenario-designer` (0.8.5) has one too but is GPL-3.0 and pulls PyQt6: not used.

## The cache and its interface: `../.worlds/cr-cache/<id>/` (COMMONROAD_CACHE; outside road/, whose catalog walk it slowed)

`road/.venv-cr/bin/python road/tools/cr_convert.py <id>` writes `<id>.net.xml`, `<id>.sumo.cfg` and `cr.json`, and keeps them while the
scenario file's sha256 and the version match (`--force` converts again); `--index` writes `../.worlds/cr-cache/index.json` (a row per scenario
of the checkout: id, set, source, path, country, map, tags, dt) for the page's picker. `road/world/cr_world.py` (the `cr:<id>` kind,
under `sumo_world.SumoWorld`) reads them; a scenario not yet in the cache is converted once by running the tool.

`cr.json`, version 4 (CommonRoad's facts only, in the scenario's frame; metres, radians from +x, steps of `dt` s):
- `version`, `id`, `source` (the file in the checkout), `sha256`, `dt`, `net` (the net's file name), `net_offset` (netconvert's; 0,0 seen),
  `converter` (the two versions, highway mode, country), `tags`, `interactive` (an interactive scenario's `.cr.xml`);
- `edges`: SUMO edge id → its lanelet ids (the converter's: an edge of a multi-lane road holds several); `edges_missing`: the ids of
  that map netconvert merged away (a junction's cluster), so a reader places by geometry where an edge is missing;
- `lanelets`: id, types, `left`/`right` bound vertices, successors, predecessors, adjacent left/right with the same-direction flag, sign
  and light ids, stop line;
- `signs`: id, position, elements (CommonRoad's element id, e.g. `MAX_SPEED`, and its values); `lights`: id, position, offset, cycle
  (state, steps); `intersections`: id, incomings (lanelets, successors left/straight/right, `left_of`);
- `obstacles`: id, type (CommonRoad's: car, truck, bus, bicycle, pedestrian, priorityVehicle, parkedVehicle, …), role, length, width,
  `trajectory` (the initial state then the prediction's: `k`, `x`, `y`, `theta`, `v`; a static obstacle has its initial state alone);
- `right_before_left`: {SUMO junction id: its CommonRoad intersection ids}, the junctions the post-pass made right_before_left (version 2,
  commonroad-world step 2 (4)): the converter makes a junction `priority` (a main road) where the scenario states none; a junction of the
  scenario's own intersections whose incoming lanelets carry no right-of-way sign (yield, stop, priority, right of way, 4-way stop) and no
  light is patched in the cached net (`netconvert -s NET -n PATCH`, the frame kept), so the yield law reads the scenario's priority;
- `planning`: per planning problem its id, `initial` (k, x, y, theta, v) and `goals` (each: `polygons` of its position's shapes, a
  circle as 24 points; `lanelets` of the goal position; `time`, `velocity`, `orientation` as [lo, hi] or null).

## The measures (`director.cr` in the run's summary)

`goal_reached` and `goal_t` (the ego's centre in a goal's region, its step in the goal's time window and its speed and heading in the
goal's intervals), `goal_position_t` (the region alone), `goal_window_s` (the window as run seconds); `contact` and `contacts` (the ego's
box against each obstacle's recorded box, CommonRoad's own test; SUMO's collisions are the Leaderboard's beside it);
`off_lanelet_ticks`/`_m` (the centre outside every lanelet's polygon); `cost` null (a scenario file has no cost function: the benchmark
id carries it); `rc` (the driven metres over the route's) as the cards'.

## A run's end and the world's faults (cr-harvest s-f4e297da, 2026-11-06)

- A run does not end on arrival before its goal's time window closes: within 40 m of the route's end the planner gets the
  stop wish (road_wishes) and holds; the run ends when the goal is reached (`stopped: held`), or the window's end + 30 s
  passes (`window+30`). A goal with no time window is never held for.
- A time-only goal (no region): the ego drives on; the goal is its window, speed and heading.
- No route from the start's edge to the goal's (the converted net lost the connection: Flensburg, Lohmar):
  `error: world`, "cr: no route", never the goal measure. So is a route under 5 m to a goal with a region ("cr: no goal edge").
- The violation measure starts at the family's first command (`first_cmd_tick`): before it the accel is the initial state's.
