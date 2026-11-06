# The scenario card, v2: the one format every scenario source converts into (scenario-catalog s-92e0b650, the architect, 2026-11-06)

**Status: SPEC, step 1 of scenario-catalog.** The user's word (2026-11-06): one stable format for our scenario runner; sources are converted, adapted and plugged; the catalog runs in CI for regressions as the road domain evolves; SUMO is where the sources converge, CARLA later, no third simulator; the only stable part on the perception side is the semantic world, filled from observation. A card describes a SCENE and what we expect of the family in it. It never describes the family, and nothing in the family reads a card: the host reads it, builds the world, and the semantic world is observed as on any road.

The ten cards in `road/scenarios/*.yaml` are v1 (road-scenarios s-e23be780). v2 keeps every v1 key with its meaning and adds the keys below. A v1 card is a valid v2 card with `card: 1` implied; the migration (step 4) sets `card: 2`, `tags`, `verdict` and `map` on each.

## 1. The card's shape

```yaml
card: 2
scenario: StaticCutIn                     # the id: letters, digits, '-', '_' ; unique in the catalog; a run name is <scenario>-<seed>
title: one line a person reads
source:                                   # PROVENANCE, required: where the scene comes from and under what terms
  suite: lb2 | commonroad | openscenario | ours
  type: StaticCutIn                       # the source's own name for it
  code: srunner/scenarios/cut_in_with_static_vehicle.py:36    # or the scenario file's path in its checkout
  pin: scenario_runner v0.9.16 94ff3b8af752                  # the source's release or commit
  license: "CARLA scenario_runner, MIT License, Copyright (c) 2018 CARLA"   # the notice, verbatim, as the license asks
patches: []                               # every hand change to the source, see §4; [] when none
tags: [cut-in, following, lane-keeping]   # the regulation groups the card exercises, from the vocabulary of §5
exercises: "responder brake_lon; planner brake_follow"       # free text: which rules the author expects to fire
map:                                      # §2
  town: Town03                            # one of road/maps/*.net.xml, or
  net: catalog/commonroad/DEU_Gar-1_2_I-1-1/DEU_Gar-1_2_I-1-1.net.xml   # a stored converted net (with its notice beside)
  data: catalog/commonroad/DEU_Gar-1_2_I-1-1/cr.json                      # the converter's data the host reads (lanelet maps, signs, lights, foe gaps)
sites: {lb1: Scenario1, towns: {Town03: [42, 49, 127, 135]}}   # v1: where on a town the scene is placed (a card on its own net has none)
dt: 0.1
ticks: 1200                               # the outer bound; the run ends earlier by §3's rules
ego:
  v: 11.1                                 # start speed; on a stored net also `at: {lane: ..., s: ...}` and `route: [edges]` or `goal: {...}` (§3)
exerciser: {dest: 400.0}                  # the exerciser's placement, or {skip: "why"} when the exerciser cannot play it
params:                                   # the logical scenario: parameters with ranges, variants are drawn from them
  tta: {value: 2.7, range: [2.7, 2.7], default: 2.7, drives: actors.cutin.trigger.tta, threshold: 1.85, safe: above}
actors:
  - id: cutin
    kind: car | truck | bicycle | pedestrian | emergency | static
    mode: scripted | recorded | model      # §3: who drives it
    at: {ahead: 100, lane: -1}             # relative to the ego (v1), or {lane: ..., s: ...} on a stored net
    v: 0.0
    trigger: {beside: true, tta: 2.7, dist: 15.0}
    script: [{when: trigger, v: 11.1}, {when: trigger, after: 1.5, lane: 1}]
    trajectory: catalog/commonroad/.../obstacles/cr318.jsonl             # mode recorded: the body's poses per step
infractions: {scenario: []}
expect: {arrived: true, collisions: 0, violations: 0}     # what the family is EXPECTED to achieve (the author's bar)
verdict:                                  # the card's CURRENT standing against `expect` (§6): CI fails when it moves EITHER way
  status: pass | soft | fail | world
  since: {worlds: 13b7dac, catalog: ef793dc}
  record: 20261105T051440-668e45          # the surprise record when fail; the world fault's name when world
  note: "the time window is missed by 3.1 s"
```

Keys the v1 loader reads keep their names: `scenario`, `source`, `exercises`, `sites`, `dt`, `ticks`, `ego`, `exerciser`, `params`, `actors`, `infractions`, `expect`. `verdict: PORTABLE` of v1 (nina's triage verdict on the SOURCE) moves to `source.portable: true`; v2's `verdict` is the family's standing.

## 2. The map

A card plays on ONE map, named one of two ways:
- `map.town`: a CARLA town converted by `road/maps/build.sh` (OpenDRIVE → SUMO net; the big towns untracked, rebuilt from `$CARLA_ROOT`). `sites` places the scene on it, as v1 does.
- `map.net` + `map.data`: a stored converted net under `road/catalog/<source>/<id>/`, with `NOTICE` beside it carrying the source's license text (BSD-3 asks for it on redistribution). The data file is the converter's (CommonRoad: `cr.json` v4: lanelet→edge/lane maps, signs, lights or `lights_dropped`, foe gaps, the planning problem). Storing is the user's word (2026-11-06): converting every time was the cost; the license permits it.

The host reads the net through `semantic_world.net.load_net` into the LaneMap, as on every road. The card never carries lane geometry of its own.

## 3. The ego, the actors, the run's end

**The ego** starts at `ego.at` (or the site's pose) with `ego.v`, and drives either a `route` (edges) to `exerciser.dest` / the route's end, or to a `goal`: `{region: polygon | lanelets, time: [t0, t1], v: [lo, hi], heading: [lo, hi]}`, any part optional; a goal without a region is TIME-ONLY (CommonRoad's goal state without position): the ego drives on and the goal is the window. The run ends (a) at `ticks`, (b) when the goal is reached, (c) at the goal window's end + 30 s when a region goal is not reached, (d) at arrival ONLY if no goal window is still open (a run never ends on arrival before its window closes; the ego holds at the route's end with a stop wish within 40 m). These are the harvest's rulings written down.

**Actors** by `mode`:
- `scripted`: v1's actors: placed relative to the ego, armed `trigger` (gap / tta / dist / traveled / t / beside), `script` steps with `after` delays (speed, lane, flow); the host drives them by the script.
- `recorded`: a `trajectory` file (jsonl, one pose per step: t, x, y, heading, v, lane) the host plays by moveToXY per tick; inside a junction the body stays on its route's lanes (never remapped per tick); a recorded body does not react.
- `model`: the host's own driver model drives it from its start pose and speed (SUMO's car-following and lane-change model; `breaks_rules` and `kind: emergency` as v1).
`kind: pedestrian` and `bicycle` are host-side bodies with their class (the walker cards' ruling).

**Variants**: `params` as v1: each parameter has `range`, `default`, `drives` (the path it sets), `threshold` and `safe`; the runner plays the card as the source states it and, with `--variants`, two clear values and three borderline ones, as today. A PEGASUS-style logical scenario is a card with several params.

## 4. Patches

Every hand change to what the source states is a `patches` entry: `{what: "the oncoming flow's first gap", from: 20, to: 35, why: "SUMO's insertion refuses the source's 20 m at 50 km/h", by: nina, date: 2026-11-06}`. A card with patches is still the source's scenario, honestly marked; the importer writes `patches: []` and a person adds to it. The triage reads `patches` to tell a source's scene from ours.

## 5. Tags: the regulation groups

`tags` name what the card EXERCISES, from one vocabulary (the coverage table's rows; `road/docs/coverage.md`, step 6): `following`, `lane-keeping`, `lane-change`, `overtaking`, `oncoming-pass`, `cut-in`, `merge-zipper`, `junction-priority`, `right-before-left`, `stop-sign`, `yield-sign`, `traffic-light`, `turning-left`, `turning-right`, `roundabout`, `pedestrian-crossing`, `cyclist`, `emergency-vehicle`, `parking`, `obstacle-static`, `route-following`, `speed-limit`, `visibility`, `highway-ramp`. A source's own tags (CommonRoad's `intersection`, `highway`, `critical`, …) go to `source.tags`, never into `tags`. A tag is added to the vocabulary by the architect, with its row in coverage.md.

## 6. The verdict, and what CI does with it

`verdict.status` is the family's CURRENT standing on this card at `verdict.since` (the worlds commit and the catalog pin), measured by the runner: `pass` (expect met), `soft` (the goal's place reached, its window missed; or expect met with a NOTE row), `fail` (a measure of expect missed: the record id in `verdict.record`), `world` (the world cannot pose it honestly: a converter fault named in `verdict.record`; not the family's). The verdict is written by the runner (`scenario_run.py verdict CARD`), never by hand, and committed with the card.

CI (step 5) runs every card on the exerciser per push, and the SUMO cards nightly on panzer, and compares the measured standing with `verdict.status`: a card that moves in EITHER direction fails the run (a regression, or an unexplained fix that someone must read and then record as the new verdict with its `since`). CI prints coverage: `tags` × status counts, per regulation group.

## 6b. One verdict per host; the index's `run`; one town per card (opus's and george's points, 2026-11-06)

- **The verdict is per host.** A card plays on the exerciser (fast, the CI's per-push check) and on SUMO (the nightly), and the two can stand apart (StaticCutIn: pass on the exerciser, fail on three SUMO sites). So `verdict` is keyed by host: `verdict: {exerciser: {status, since, record, note}, sumo: {status, since, record, note}}`; a host the card cannot play has `{status: skip, note: "why"}` (the v1 `exerciser.skip`). CI compares each host's measured standing with its own entry only. A card's single-host summary, where one word is needed (the picker), is SUMO's when present, else the exerciser's.
- **One town per card.** `map.town` is one town, the card's reference placement; `sites` lists every placement, and the host's standing is measured over all its sites (the worst site decides, as the tables do today). A list of towns is not needed.
- **The catalog's index** (`road/catalog/index.json`, written by `scenario_run.py index`) carries per row: `id`, `source`, `tags`, `verdict` (per host), `map`, and `run`: the run spec the host starts (`card:NAME@TOWN#SITE` for a CARLA card, `cr:ID` for a CommonRoad card), so the page's picker starts a row without deriving it.
- **Layout wins over paths**: the runner reads `road/catalog/<source>/` (§7); `road/scenarios/` is gone once the ten cards move.

## 6a. Answers to the runner's open points (george's design note, steps/runner-design-george.md)

- **The end condition** is §3's four rules, read from the card: `ticks` (outer bound), `ego.goal` (reached; or window end + 30 s for a region goal; a time-only goal ends at its window's end), `exerciser.dest` / the route's end (arrival, only once no window is open). Nothing else ends a run; a crash is an `error` row.
- **`expect` → the standing**: every key of `expect` is a measure the runner computes; `pass` = all met; `soft` = all met except the goal's window (place reached) or met with a NOTE row; `fail` = a hard measure missed (arrived false with no window open, collisions, violations, off_lanelet beyond a seam, a region goal's place never reached); `world` is never derived from `expect`: it comes from the world-fault rules.
- **The world-fault rules live in the runner** (`scenario_run.py check`), not in the triage: no route / no goal edge / ticks ≤ 5 / a frozen or lane-jumping or standing-ego partner / a recorded partner from behind / initial contact / unavoidable start are properties of the ROW and the TRUTH, so the runner writes `world` into the row's standing with the rule's name, and the triage only reads it. cr_triage keeps the clustering and the curve.
- **The stored-net layout**: in the card's own directory `road/catalog/<source>/<id>/` (net, data, trajectories, NOTICE), never a shared hash store: a card is one self-contained thing a person can read, copy and delete; two cards on one map store it twice (the catalog is hundreds of cards, not thousands).
- **The law pin**: a card never pins a law. CI runs every card at main's `road/domains/catalog.pin`; `verdict.since` records the pin the standing was measured at, so a moved verdict names the pin that moved it. The harvest's per-pin directories keep the history.

## 7. Where the cards live

`road/scenarios/` keeps the ten CARLA cards (moving to `road/catalog/carla/` in step 4). `road/catalog/<source>/<id>.yaml` for every imported card, with `road/catalog/<source>/<id>/` beside it for a stored net, data and trajectories, and `NOTICE`. The catalog's `index.json` (id, source, tags, verdict, map) is written by the runner and read by the page's picker (the catalog first, the raw checkout second).

## 8. What a card is not

Not law, not projection, not a surprise record. It carries no rule names except in `exercises` (free text for the author), no atoms, no facts: the family meets the scene through the semantic world, which the host fills from what the body simulator shows within the sensor range. It is not a trace: traces are the runner's output, beside the row.
