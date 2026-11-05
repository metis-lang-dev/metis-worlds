# The CommonRoad harvest: the catalog in batch (commonroad-world s-9b7591fb, step 3b)

Every scenario of the index (road/maps/cr/index.json, `cr_convert.py --index`) run once, headless, by the road tree
(`road/experiments/road_tree.py cr:ID SEED --world sumo`) on the family at `road/domains/catalog.pin`; ONE row per
scenario, a surprise record per failure; no agent in the loop per scenario. Hosts share no filesystem: each host
works its own slice under its own `/bigdata/work/harvest/`, and `pull` brings a host's rows and records to taycann.
The tool: `road/tools/cr_batch.py` (george). The triage over the rows and records: `road/tools/cr_triage.py` (nina).

## Commands

    road/tools/cr_batch.py plan   --hosts taycann:12,panzer:28 [--set recorded|interactive] [--source S,S] [--ids ID,ID] [--limit N]
    road/tools/cr_batch.py work   [--host H]                       # one worker loop: claim, run, row, record; exits when queue/ is empty
    road/tools/cr_batch.py launch --workers N [--host H] [--ssh USER@HOST]   # N workers detached (systemd-run --user, MemoryMax=6G, nice 10)
    road/tools/cr_batch.py status [--host H] [--ssh USER@HOST]     # done / failed / running / queued / ETA per host
    road/tools/cr_batch.py pull   --ssh USER@HOST --host H         # rsync that host's rows/ and records/ (and failed runs/) here
    road/tools/cr_batch.py recover [--host H]                      # running/ jobs whose worker pid is gone go back to queue/

`plan` runs on every host with the same arguments and the same index: the split is by a hash of the id (sha256, first
8 hex as an integer) weighted by the hosts' numbers, so each host computes the same split and queues only its own
slice. A row already in `rows/` is not queued again (resumable). `launch` runs `recover` first.

## Layout

    /bigdata/work/harvest/<pin>/<host>/      pin: the first 7 of road/domains/catalog.pin (the law the rows were run under)
        plan.json                            the plan's arguments, the index's row count, this host's job count, when
        queue/<id>.json                      a job: the index's row for the scenario (id, set, source, path, country, map, tags, dt)
        running/<id>.json                    a claimed job: moved here from queue/ by rename (atomic: one worker wins)
        running/<id>.pid                     "<pid> <host>" of the worker that holds it
        done/<id>.json                       the job, after its row is written
        rows/<id>.json                       THE ROW (below)
        records/<record_id>.json             a surprise record per failed scenario (below)
        runs/<id>/                           road_tree's out dir: the run spec, the world log, the journal, the trace
                                             (trace/<run>/, run = cr_<id>-<seed>), stderr.txt; deleted for a pass
        logs/worker-<n>.log                  a worker's lines

`COMMONROAD_HARVEST` overrides `/bigdata/work/harvest`.

## The row (rows/<id>.json, one JSON object)

| field | type | what |
|---|---|---|
| `id` | str | the scenario id |
| `set` | str | `recorded` or `interactive` |
| `source` | str | the index's source (hand-crafted, THI-Bicycle, NGSIM's map, scenario-factory, ...) |
| `country` | str | the id's country code |
| `tags` | [str] | the scenario file's tags |
| `host` | str | where it ran |
| `pin` | str | the catalog pin (7) |
| `worlds` | str | metis-worlds commit (7) the worker ran |
| `seed` | int | SUMO's seed |
| `started`, `ended` | str | ISO-8601 with offset |
| `wall_s` | float | the subprocess's wall time |
| `ticks`, `t` | int, float | the world's ticks and run seconds |
| `arrived` | bool\|null | the world's: the ego done with its route |
| `goal` | object | `position_t` (s or null: the ego's centre first in a goal region), `window_ok` (the goal's time window held when it was there), `reached` (CommonRoad's goal: region, window, speed, heading), `window_s` |
| `contact` | bool | the ego's box against an obstacle's recorded box, CommonRoad's test |
| `contacts` | int | how many contact intervals |
| `sumo_collisions` | int | SUMO's collision events (the Leaderboard's) |
| `off_lanelet` | object | `ticks`, `m` |
| `violations` | int | the world's violation count (the summary carries a count, not a list) |
| `rc` | float\|null | driven metres over the route's, percent |
| `fired` | [str] | the director's triggers that fired (empty for a cr: scenario, which has none) |
| `untriggered` | [str] | armed triggers that never fired |
| `failed` | [str] | the measures that failed, in this order: `contact`, `sumo_collision`, `goal`, `off_lanelet`, `violation` |
| `record_id` | str\|null | the surprise record of this row's failure |
| `error` | object\|null | the run did not finish: `kind` (`convert`, `world`, `timeout`, `crash`), `line` (the exception's line), `trace` (the last 5 stderr lines), `rc` |
| `stopped` | str\|null | `window+30`: the run was stopped 30 s after the goal's time window ended, goal not reached (the ruling of 2026-11-05; `CR_STOP_AFTER_WINDOW`); null: it ran to arrival or the tick cap. Rows before the early stop have no `stopped` key: the first hand-crafted round on panzer |
| `summary` | object | the world's whole summary line, as road_tree prints it |

A row **passes** when `error` is null and `failed` is empty. `goal` fails when `reached` is false.

## The record (records/<record_id>.json)

The workspace's surprise format (metispy `metis.catalog.workspace.drop_surprise`), written by the worker with
`who: "world"`, `status: "open"`, an id of the workspace's shape (`YYYYMMDDTHHMMSS-<6 hex>`):
`member` (`responder` for `contact`/`sumo_collision`, `planner` for `goal`/`off_lanelet`, `road_director` for a
violation alone), `reading` (one sentence: the scenario, the first failed measure and its numbers), `atoms` (the
failed measures), `trace` (`traces/<run>`: the run's trace dir name, the trace itself in `runs/<id>/trace/`),
`trace_path` (`runs/<id>/trace/<run>`, relative to the host dir), `config` (the trace's config.yaml, relative),
`window` ([k0, k1] in trace ticks, inside the trace's ks: a contact's [first contact - 50, first contact]; the goal's
[window end - 300, window end], or the run's end when it ends first or the goal has no window; off-lanelet's [first
off tick - 50, that tick]; a violation alone [run end - 50, run end]), `scenario` (`cr:<id>`), `row` (`rows/<id>.json`). A run that did not finish
(`error`) gets no record: it is a world or conversion fault, not the family's, and the triage reads it from the row.
Importing a representative into `road/.metis/surprises/` (nina's `cr_triage.py import`) copies the record and its
trace there.
