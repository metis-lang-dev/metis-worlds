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

## Layout

| path | what |
|---|---|
| `setup.sh` | the world's venv (`.venv/`, Python 3.12): `alfworld[full]` 0.4.2 pinned, its game data (2.3 GB) under `data/` (`ALFWORLD_DATA`) |
| `world/ground.py` | the PDDL facts as atoms: a per-game handle table (`spoon1`, `countertop2`, `loc3`, `cabinet_t`), the predicate map, STATIC vs DYNAMIC |
| `world/alf_gym.py` | one game as a child process (JSON lines): open / reset / step(command) → the dynamic facts, the admissible commands, won |
| `world/alf_host.py` | the host: tick (the program's facts synced to the game's) / on_event (a fired rule → the game's command) / observe / snapshot / restore; over a semantic map it reads the world in roles through the map's binding and says commands, lines and goals in the room's things; `$METIS_ALF_LOG` records every command |
| `world/gen_instance.py` | a game as a flat PACKAGE over `domains/alfred_domain.llp` (types, static facts as Horn facts, the task resolved to `target/1`, `dest/1`, the start): the policy runs' base (metis-loop pi/policy) and the hierarchy's mirror |
| `world/package_host.py` | the host shim every generated package carries as its `alf_host.py` |
| `world/families.py` | the seven task families and ALFWorld's splits (train = discovery; valid_seen / valid_unseen = held-out) |
| `domains/alfred_domain.llp` | the flat LIFTED base: ALFRED's actions as the agent's beliefs, and the greedy rule policy for pick-and-place |
| `domains/hier/` | the HIERARCHY (`docs/HIERARCHY.md`): five lifted specialists — `nav` (goto→reached), `access` (open→accessible), `grasp` (take→taken), `place` (put→placed), `task` (the planner); `capacity.llp`, the role vocabulary, and `<spec>/<spec>.llp`, each specialist's committed instance (compiled once: no room in any source); `<spec>/intent.yaml` the card templates, `*.tsv` their corpora |
| `domains/director_domain.llp` | the director (activation from context; a copy of metis-catalog's) |
| `world/semantic_map.py` | the room as data: `SemanticMap` (places, things, the agent, the task, beliefs, and the roles' binding; `domains/hier/.map.json`), the projection of a goal onto the roles, `role_reading`; and the page's text-mode map (`text_map`, `world_card`; `web/fixtures/` holds the reference game's). `tiles/index.json`: this world's tiles for `web/map.js` |
| `world/gen_hier.py` | the capacity and the committed instances, `install()` (a game for the agent: the flat mirror, the director, the map, the specialists, one commands log), the cards from the map, the driver's packages |
| `world/director_host.py` | the director's host in the agent: the arrivals in, its out atoms retracted, `deliver(D, goal, tokens)` — a domain's next activation as one row on its live session |
| `experiments/demo.py`, `demo.sh` | the demo (`docs/DEMO.md`): `setup` installs a game as the agent's catalog, `check` runs the five-turn script through metis-agent's service (E2B); `demo.sh` serves it with the page (`web/world.html?live=1`) |
| `experiments/hier.py` | the hierarchy in kernel runs: the MANUAL switch (`{goto: nav, open: access, take: grasp, put: place}`) or `--director`; `hier_vector.py` the complexity vector per domain; `complexity.py` the flat one |
| `experiments/hier_director_agent.py` | the hierarchy through metis-agent, games by the person's words (step 3's measure; demo.py takes its helpers); `hier_cards.py` the cards on E2B (F3); `wire.py` the stdlib websocket client |
| `experiments/record_run.py` | one turn of the hierarchy recorded as the world page's frames (`web/fixtures/*.run.jsonl`) |
| `experiments/baseline.py`, `REPORT.md` | the flat program's own rules on a sample of games, and the measured record of each step |
| `tests/` | the grounding, the host on the real game, the hierarchy (manual switch, director, detour), the roles (no room in source, the projection, rebinding on the live session, the host's words, the belief port), the recorded turns, the demo's map |

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
