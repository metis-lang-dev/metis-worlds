# road/runner: the road world's headless scenario runner

metis-plugin s-df4ff191. The user's ruling: **scenario running is the domain's, separate from the runtime**. This
directory turns a catalog card into a road run. Everything else is metis-agent's generic runtime
(`metis_agent.runtime`: `run.Run` the loop, `feed.RuntimeFeed` the feed and the wire, specs in metis-agent
`plugin/docs/RUNTIME-INTERFACE.md` and `SURPRISE-INTERFACE.md`).

| file | what |
|---|---|
| `road_runner.py` | the CLI: `--card ID` (repeat, or `a,b,c`) or `--scenario NAME`, `--seed`, `--host sumo\|exerciser`, `--site`, `--ticks`, `--workspace` (default `road/`), `--name road`, `--linger 5` |
| `cards.py` | a card -> road_tree's scenario, host, ticks, window stop; the card's standing; rulecheck's road rules |
| `host.py` | `RoadHost`, road's `RuntimeHost`: the run spec file, blind watches, the world's findings, the run-end rules, the summary, the end findings, the world shut |
| `observer.py` | the road's findings per tick: collisions (merged as the Leaderboard does), RSS violations; a failed end |
| `../runner.yaml` | what the plugin's `runner_start` runs |

One invocation = ONE runtime named `road`, serving while its runs go (`.metis/runtimes/road.json`). Each run:
- its trace in `.metis/traces/<scenario>-<seed>-<UTC stamp>/`, with `config.yaml` beside it (the judge replays on it)
- `run.started`, then each finding as it is found:
  - a collision, an RSS violation
  - at the end, a broken road rule, or the card's checks failing
- each finding written as a surprise (`drop_window`, key `<run>:<kind>[:<slug>]:<k>`), then signalled
  (`surprise.new`) once the trace segment holding its window is closed, then `run.ended`

## From Claude Code with the plugin (the headless mode)

    runner_start '--card FollowLeadingVehicle'        # or Bash: python road/runner/road_runner.py --card ...
    runtime_connect road                              # follows the name across runs (re-attaches by itself)
    wait_signals 'surprise.*'                         # the surprises as they come; surprise_get / take / rule ...

## Environment

- the Live's venv with metis-agent's runtime package: metis-agent `claude-plugin` ≥ 36bfe64
- `METIS_HOME`: the road family, at `road/domains/catalog.pin`'s commit
- SUMO: found by the runner as `road/demo.sh` does (`$SUMO_VENV`, else `../.worlds/road`, else the host's `~/repo/perotheia-packages/.worlds/road`); a `sumo` on `PATH` with `SUMO_HOME` set wins
- the semantic world: metis-worlds' `libs/semantic-world` (road_runner.py puts it on its path itself)

Tests: `road/tests/test_road_runner.py`. The observer, the host under the run loop (the world's tick is the trace's),
the runner by name on the exerciser, a bad card said in words; one SUMO card with `RUNNER_SUMO=1`.
