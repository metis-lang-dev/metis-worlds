# alfworld — a small world for learning (metis-worlds)

[ALFWorld](https://github.com/alfworld/alfworld) (text-mode, TextWorld over ALFRED's
household tasks) under the metis agentic loop: the kernel's program acts through a host,
the domain agent scores every beat and records the surprises, the agentic loop proposes
rules from them, an experimental gate accepts a rule only if held-out configurations get
more predictable, the domain reloads, the agent runs again. No small model in this loop:
the approach is **design the domain first, add the interface later**. The program and its
measures: `metis-agentic-loop/docs/LEARNING.md`.

Grounding: ALFWorld's text environment carries the underlying PDDL facts, so the world's
state is atoms without a perception model — the host is the RDDL host's shape
(`metis-catalog tools/rddl_host.py`): a beat is one step of the environment, the facts
become `+atom` / `-atom` lines, the program's actions become the environment's commands.

## Layout (step 1)

| path | what |
|---|---|
| `setup.sh` | the world's venv (`.venv/`, Python 3.12): `alfworld[full]` 0.4.2 pinned, its game data (2.3 GB) under `data/` (`ALFWORLD_DATA`) |
| `world/ground.py` | the PDDL facts as atoms: a per-game handle table (`spoon1`, `countertop2`, `loc3`, `cabinet_t`), the predicate map, STATIC vs DYNAMIC |
| `world/alf_gym.py` | one game as a child process (JSON lines): open / reset / step(command) → the dynamic facts, the admissible commands, won |
| `world/alf_host.py` | the host: `make(case)` → tick (the sync of the program's facts to the game's) / on_event (a fired rule → the game's command) / observe / snapshot / restore (a replay); `$METIS_ALF_LOG` records every command, whether the game took it, what changed |
| `world/gen_instance.py` | a game as a PACKAGE: `domains/<iid>/{<iid>.llp, domain.yaml, game.json, alf_host.py}` — the instance's types, static facts as Horn facts, the task resolved to the game's things (`target/1`, `dest/1`), the start |
| `domains/alfred_domain.llp` | the LIFTED base: ALFRED's actions as the agent's beliefs, and the greedy rule policy for pick-and-place |
| `world/families.py` | the seven task families and ALFWorld's splits (train = discovery; valid_seen / valid_unseen = held-out) |
| `experiments/baseline.py` | the program's own rules on a sample of games, no loop: won / lost, the commands, the refusals |
| `domains/hier/` | the HIERARCHY (alf-hierarchy, `docs/HIERARCHY.md`): five lifted specialists — `nav` (goto→reached), `access` (open→accessible / refused), `grasp` (take→taken / refused), `place` (put→placed / refused), `task` (the planner: sub-goals out, results in, `done` / `stuck`) |
| `world/gen_hier.py` | one activation of a specialist as a generated instance: its predicates, its facts, the things its goal names (`game.json`: `replay`, `observe`, `out`, `things` for the host) |
| `world/semantic_map.py` | a game's semantic map (`docs/DEMO.md` §3), text mode: places at the positions their THOR ids carry, things in places, the agent's start, the task's words and goal; `web/fixtures/` holds the reference game's. `tiles/index.json`: this world's tiles for `web/map.js` (merged over the base) |
| `experiments/hier.py` | the hierarchy with a MANUAL switch: one kernel run per activation, the driver's table `{goto: nav, open: access, take: grasp, put: place}` is the switch; `hier_vector.py` the complexity vector per domain |
| `tests/` | the grounding is deterministic, the host runs a plan to a win on the real game, a refusal leaves the facts, the package compiles and reaches `placed` alone; the hierarchy wins by the manual switch, its instances see less |

## Findings while building (step 1)

- **Handles must be shared, not recomputed.** TextWorld hands the facts back as a set; a
  per-process first-appearance numbering differed between the generator and the host, so
  the program's `loc2` was the fridge in one and the coffee machine in the other. The
  generator orders the facts and writes the map into `game.json`; the host reuses it.
- **The game's verbs are TextWorld's, not ALFWorld's agent aliases.** `put O in/on R` is
  the agent layer's; the game lists `move O to R`. The host sends the game's verbs and
  records what the game offered when it refuses, so a refusal in the records is the
  world's, never a phrasing slip.
- **The refusal path works as designed.** A rule that fires without its real precondition
  (taking from a closed fridge) sends a command the game answers with "Nothing happens.":
  no fact changes while the rule produced its effect — the surprise the loop learns from.
- **Grounding size.** A rule carrying the task's type variables grounded to millions of
  instances and overflowed the compiler's run; the generator resolves the task to the
  game's things (`target(O)`, `dest(R)`) so no rule carries a type, and the instance runs
  in both toolchains in seconds.

## Not here
The closure (surprise → proposal → gate → reload), the gate policy and the metrics: the
metis side, in metis-agentic-loop / the loop SDK / metis-agent.
