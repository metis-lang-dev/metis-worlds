# Coverage: the scenario catalog per regulation group (the live page)

Baseline: the scenario-catalog freeze at metis-worlds d10b929 (regression 85, working 126); its table stays in git at that commit and in the bench report /bigdata/work/bench/d10b929/report.md.

This page is LIVE: regenerated at every set change with `road/tools/scenario_run.py coverage road/catalog` from the cards' verdicts on file (SCENARIO-CARD §6, §6c). Now: 211 cards (commonroad 192, ours 3, scenario-runner 16): regression 87, working 124, the road family at catalog pin 915eae9 (last change: ix-left-turn and ix-crossing-gap promoted at 365188d, the two-phase waiver).

- **regression (proven)**: the cards CI relies on, every played host at pass.
- **working (exercised)**: the rest, measured fail / soft / world on some host, the agents' queue.
- The second table is each host's standings; a card that a host cannot play counts as skip there (the CommonRoad cards on the exerciser, the ours cards on SUMO).

| tag | regression (proven) | working (exercised) |
|---|---|---|
| cut-in | 1 | 1 |
| cyclist | 33 | 32 |
| emergency-vehicle | 1 | 0 |
| following | 2 | 29 |
| highway-ramp | 1 | 2 |
| junction-priority | 61 | 90 |
| lane-change | 9 | 14 |
| lane-keeping | 0 | 2 |
| merge-zipper | 3 | 6 |
| obstacle-static | 6 | 2 |
| oncoming-pass | 10 | 42 |
| overtaking | 1 | 1 |
| parking | 1 | 1 |
| pedestrian-crossing | 1 | 2 |
| right-before-left | 59 | 68 |
| route-following | 73 | 119 |
| speed-limit | 65 | 108 |
| traffic-light | 1 | 3 |
| turning-left | 7 | 34 |
| visibility | 0 | 1 |
| yield-sign | 3 | 5 |

| tag | host | pass | soft | fail | world | skip |
|---|---|---|---|---|---|---|
| cut-in | exerciser | 2 | 0 | 0 | 0 | 0 |
| cut-in | sumo | 1 | 0 | 1 | 0 | 0 |
| cyclist | exerciser | 0 | 0 | 0 | 0 | 65 |
| cyclist | sumo | 33 | 3 | 4 | 25 | 0 |
| emergency-vehicle | exerciser | 0 | 0 | 0 | 0 | 1 |
| emergency-vehicle | sumo | 1 | 0 | 0 | 0 | 0 |
| following | exerciser | 3 | 0 | 0 | 0 | 28 |
| following | sumo | 2 | 1 | 3 | 25 | 0 |
| highway-ramp | exerciser | 0 | 0 | 0 | 0 | 3 |
| highway-ramp | sumo | 1 | 2 | 0 | 0 | 0 |
| junction-priority | exerciser | 5 | 0 | 0 | 0 | 146 |
| junction-priority | sumo | 58 | 40 | 5 | 45 | 3 |
| lane-change | exerciser | 3 | 0 | 0 | 0 | 20 |
| lane-change | sumo | 9 | 11 | 2 | 1 | 0 |
| lane-keeping | exerciser | 0 | 0 | 0 | 0 | 2 |
| lane-keeping | sumo | 0 | 0 | 2 | 0 | 0 |
| merge-zipper | exerciser | 0 | 0 | 0 | 0 | 9 |
| merge-zipper | sumo | 3 | 5 | 1 | 0 | 0 |
| obstacle-static | exerciser | 3 | 0 | 0 | 0 | 5 |
| obstacle-static | sumo | 6 | 0 | 2 | 0 | 0 |
| oncoming-pass | exerciser | 0 | 0 | 0 | 0 | 52 |
| oncoming-pass | sumo | 10 | 38 | 4 | 0 | 0 |
| overtaking | exerciser | 1 | 0 | 0 | 0 | 1 |
| overtaking | sumo | 1 | 0 | 1 | 0 | 0 |
| parking | exerciser | 1 | 0 | 0 | 0 | 1 |
| parking | sumo | 1 | 0 | 1 | 0 | 0 |
| pedestrian-crossing | exerciser | 1 | 0 | 0 | 0 | 2 |
| pedestrian-crossing | sumo | 1 | 0 | 2 | 0 | 0 |
| right-before-left | exerciser | 2 | 0 | 0 | 0 | 125 |
| right-before-left | sumo | 57 | 17 | 7 | 44 | 2 |
| route-following | exerciser | 0 | 0 | 0 | 0 | 192 |
| route-following | sumo | 73 | 57 | 15 | 47 | 0 |
| speed-limit | exerciser | 0 | 0 | 0 | 0 | 173 |
| speed-limit | sumo | 65 | 52 | 12 | 44 | 0 |
| traffic-light | exerciser | 0 | 0 | 0 | 0 | 4 |
| traffic-light | sumo | 1 | 2 | 1 | 0 | 0 |
| turning-left | exerciser | 1 | 0 | 0 | 0 | 40 |
| turning-left | sumo | 6 | 34 | 0 | 0 | 1 |
| visibility | exerciser | 0 | 0 | 0 | 0 | 1 |
| visibility | sumo | 0 | 0 | 1 | 0 | 0 |
| yield-sign | exerciser | 0 | 0 | 0 | 0 | 8 |
| yield-sign | sumo | 3 | 1 | 3 | 1 | 0 |
