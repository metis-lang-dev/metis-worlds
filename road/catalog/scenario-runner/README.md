# road/catalog/scenario-runner — the CARLA challenge scenarios (ScenarioRunner / Leaderboard) as scene cards, v2 (road-scenarios s-e23be780; scenario-catalog s-92e0b650)

The user (2026-11-05): "extract scenarios for scenario runner from Carla road challenge … with small adaptations it
should work on SUMO. We will introduce new road feature together with scenario to test and we reuse road challenge
scenarios to test for surprises." nina triaged all 38 Leaderboard 2.0 types and Scenario1–10 (step 1, on the subject);
these cards are the port (step 2, opus). The code is metis-worlds' own (`world/scenario_cards.py`, the exerciser's
triggers in `world/road_world.py`); nothing of CARLA's code is here. CARLA's trigger poses are copied as data with
their MIT notice (`sites/`, `sites/LICENSE`).

## A card

One file per scenario TYPE, `NAME.yaml`, in the scenario card's v2 format (road/docs/SCENARIO-CARD.md: `card: 2`, `map`,
`tags` from its §5 vocabulary, `actors[].mode`, `verdict` the family's standing, `patches`). The v1 keys below keep their meaning:

| key | what |
|---|---|
| `scenario`, `title` | the type and what happens, in one line |
| `source` | `suite` (lb2: Leaderboard 2.0; lb1: Scenario1–10), `type`, `code` (file:line in scenario_runner), `pin`, `license` |
| `exercises` | the road family's laws the scenario tests: the hypothesis a surprise falsifies |
| `source.portable` | nina's triage verdict on the SOURCE (v1's `verdict: PORTABLE`; `portable_as: PORTABLE-WALKER`) |
| `sites` | `lb1`: the Leaderboard 1.0 trigger set of the card's shape, `towns`: {Town01/02/03: [indexes] or all} into `sites/` |
| `ego` | its speed; `exerciser` its start, destination and the side road's priority on the exerciser (`skip`: SUMO only) |
| `params` | the source's parameters: `value`, `range` over the route files, `default`, `drives` (the card path it sets), `threshold` and `safe` (above or below) for the research note's §4b variants |
| `actors` | `id`, `kind` (car, static, emergency, bicycle, walker, truck), `at` {`ahead`/`behind` m, `lane` +1 left / −1 right} relative to the ego (the trigger on SUMO) or {`road: side`, `s`}, `v`, `moving`, `breaks_rules`, `trigger` (the source's condition: `gap`, `tta` + `at` + `dist`, `traveled`, `t`), `script` steps {`t` or `when` (a condition, or `trigger`), `v`, `brake`, `lane`, `go`} |
| `infractions` | the Leaderboard criteria of the card itself (e.g. `scenario_timeout: 240`); the route's always apply |
| `expect` | `arrived`, `collisions`, `violations`: what the family must hold |

Variants (`scenario_cards.variants`): for each parameter with a `threshold`, two CLEAR values far on its safe side
(×2.5, ×3.5, within the source's range) and three BORDERLINE (×0.9, ×1.0, ×1.1): `NAME:distance-border-lo`.

## Where a card plays

- **The exerciser** (`card:NAME` as the scenario of `road_tree.py` / `RoadWorld`): one 600 m road with three lanes,
  no lights. The actors are placed relative to the ego and the triggers are armed on its movers. Its lane cut is instant
  (a cut-in jumps lanes). Kinematic cards only.
- **SUMO** (step 2's second half): the card's sites in Town01/02/03, placed by CARLA's co-simulation transform
  (`carla_to_sumo`: x + ox, −y + oy, yaw + 90 with the net's netOffset; nina verified it on all 834 poses).

## Running them

    cd metis-agent/py && METIS_HOME=…/metis-catalog/domains/road .venv/bin/python …/road/experiments/scenarios.py OUT

writes `OUT/scenarios.jsonl` and `OUT/scenarios.md`: arrived, collisions, violations, the planner's commands, the
card's expectation, and the Leaderboard 2.0's infractions and Driving Score per run. CI replays every card on the
exerciser (`tests/test_scenario_cards.py`); SUMO stays out of CI.
