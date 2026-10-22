# metis-world-minihack — a small world for learning, with the small model in the loop

[MiniHack](https://github.com/samvelyan/minihack) (NLE: NetHack's engine, configurable
levels) under the metis agentic loop with the small LLM agent (Gemma E2B, metis-agent) IN
the loop: the agent acts in the level through the domain's intents, its surprises feed the
agentic loop, and the domain is **extracted after** from what the agent did. The approach
under comparison with ALFWorld's: **agent first, domain after**. The program and its
measures: `metis-agentic-loop/docs/LEARNING.md`.

Grounding: NLE gives glyphs, chars, messages and the bottom-line stats; the world's
perception adapter turns the visible map into atoms (cells, the agent's position, objects,
monsters, terrain) and messages into events. Level families are MiniHack's configurable
`.des` levels; held-out combinations of hazards, items and terrain never appear during
discovery.

## Layout (step 1)

| path | what |
|---|---|
| `setup.sh` | the world's venv (`.venv/`, Python 3.12): `nle` 1.3.0, `minihack` 1.0.2, `setuptools<81` (minihack imports `pkg_resources`) |
| `world/perceive.py` | NLE's observation as atoms: cells `cX_Y` of the level's own map (`agent_at`, `floor`, `wall`, `door(C, open\|closed)`, `stairs_down`, `obj(NAME, C)`, `monster(NAME, C)`, `trap(KIND, C)` once seen), the status (`hp`, `hunger`, `turn`), the inventory (`holds(NAME)`, counted items singular), the message as typed EVENTS (`said(blocked)`, `said(see_here)`, `said(picked)`, `said(killed)`, …) |
| `world/mh_gym.py` | one level as a child process (JSON lines): open (a `.des` text or an env id, the action names, the seed) / reset / step(ACTION) → the perception, reward, done, won |
| `world/mh_host.py` | the host: a fired rule named `X` or `X_<why>` (consuming `cmd_X(...)`) → the NLE action; the perception read back; the message's events handed in for one beat; sync; replay; `$METIS_MH_LOG` |
| `world/levels.py` | the `room` family: 144 variants (size × item × monster × door × trap) built with MiniHack's LevelGenerator; 75 discovery, 69 held out (every monster+trap and door+key combination never seen in discovery: the compositional test) |
| `world/gen_level.py` + `world/card.yaml` | a variant as a PACKAGE: `domains/<name>/{<name>.llp, domain.yaml, intent.yaml, level.json, mh_host.py}` — declarations and the perceived start only, NO rules: the domain is what the agent's runs extract; the card: MOVE(dir), PICKUP, EAT, OPEN, KICK, SEARCH, DOWN, WAIT, APPLY, UNKNOWN |
| `tests/` | the splits, the perception of a level, the host walking to the apple and picking it up, the restore, the package compiling |

## Findings while building (step 1)

- **The map is the level's, not the screen's.** NLE draws the level inside a 21×79
  screen; the perceiver takes the bounding box at reset so cells are level coordinates
  (`c0_0` the top-left), stable across variants of one size.
- **An action set is a choice.** MiniHack's navigation envs expose eight compass moves; the
  skill env exposes 85 commands. The world pins a short list (moves, pickup, eat, open,
  kick, apply, search, down, wait, more, esc) named by NLE's enums, so an intent's action is
  a name, never an index.
- **The message line lingers.** NLE keeps the last message on the line; the host hands a
  message to the program as an event only when it changed, for one beat.
- **The episode ends on the stairs.** Stepping onto `>` ends the level with the reward:
  `won` is the terminal reward, and the host sends nothing after `done`.
- **Rule names are the commands.** The host maps a fired rule by its name (`move`,
  `pickup_here`, …): the extracted domain's rules must keep that convention, which the
  extraction (step 2) enforces.

## Not here
The agent-in-the-loop wiring (metis-agent), the extraction (the agentic loop's `take`),
the gate policy and the metrics: the metis side.
