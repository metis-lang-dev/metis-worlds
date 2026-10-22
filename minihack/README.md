# minihack — a small world for learning, with the small model in the loop (metis-worlds)

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
| `world/perceive.py` | NLE's observation as atoms: cells `cX_Y` of the level's own map (`agent_at`, `floor`, `wall`, `door(C, open\|closed)` by glyph (an open door draws as `-`/`|`; a doorway is floor), `stairs_down`, `obj(NAME, C)`, `monster(NAME, C)`, `trap(KIND, C)` once seen), the status (`hp`, `hunger`, `turn`), the inventory (`holds(NAME)`, counted items singular), the message as typed EVENTS (`said(blocked)`, `said(see_here)`, `said(picked)`, `said(killed)`, …) |
| `world/mh_gym.py` | one level as a child process (JSON lines): open (a `.des` text or an env id, the action names, the seed) / reset / step(ACTION) → the perception, reward, done, won |
| `world/mh_host.py` | the host: a fired rule named `X` or `X_<why>` (consuming `cmd_X(...)`) → the NLE action; `act(atom)` / `describe()`, the faces of metis-agent's actor (step 2a); the perception read back; the message's events handed in for one beat; sync; replay; `$METIS_MH_LOG` |
| `world/levels.py` | the `room` family: 144 variants (size × item × monster × door × trap) built with MiniHack's LevelGenerator; 75 discovery, 69 held out (every monster+trap and door+key combination never seen in discovery: the compositional test). NetHack's names: the key is a `skeleton key` (carried: "a key"), the rat a `sewer rat`. With a door, a wall splits the room, the door sits in it, the stairs are BEHIND it and the agent starts in front: `locked` when the variant has the key (APPLY the key, or KICK), `closed` otherwise (OPEN). `tests/test_every_variant_opens_as_its_level` opens all 144 (a bad des makes NLE fall back to a 3×3 room silently). What the two held-out compositions test (nina's N1): monster+trap is a COMPOSITION (both seen alone in discovery); door+key is a NEW SKILL built from known parts (a key is carried in discovery, a closed door is opened, but no door is ever locked there, so APPLY-on-a-door is first needed held out). The report keeps the two apart |
| `world/map_export.py` | a level's first screen as `web/map.js`'s grid (its `glyphs` observation on the glyph sheet, floor under what moves, the things named): `web/fixtures/` holds the room_medium package's |
| `world/gen_level.py` + `world/card.yaml` | a variant as a PACKAGE: `domains/<name>/{<name>.llp, domain.yaml, intent.yaml, level.json, mh_host.py}` — declarations and the perceived start only, NO rules: the domain is what the agent's runs extract; the card: MOVE(dir), PICKUP, EAT, OPEN(dir), KICK(dir), SEARCH, DOWN, WAIT, APPLY(dir) — the key on the door in a direction: the gym's `UNLOCK:DIR` macro answers NetHack's three prompts (the key's inventory letter, the direction, y) —, UNKNOWN |
| `experiments/agent_run.py` | world-minihack step 2a: the small agent in the level, unattended. Every variant of a split once (the discovery split: 75), Gemma E2B acting from the card through metis-agent's domain agent (**act without a rule**: the package's manifest `actor: {max_steps, task}`; the host's `act(atom)` runs a command no rule took, `describe()` says the perception in words, from the atoms only), every step journaled; `report` builds the measures (win rate per feature, steps, refusals, the intents, the named surprises) |
| `tests/` | the splits, the perception of a level, the host walking to the apple and picking it up, the restore, the package compiling |

**The journals** (`agent_run.py run OUT`): one file per episode, `OUT/<variant>.jsonl`, **plain JSON lines**, the shape metis-agent's actor writes (docs/WIRE.md, "Act without a rule"): a `step` row per step (`reading` the perception atoms, `text` what the model was given, `j` the intent it typed, `words`, `command` the mapped atom, `result` the world's answer: `acted`, `events`, `reward`, `done`, `won`), then one `episode` row (`variant`, `seed`, `steps`, `end`, `won`, `refusals`, `intents`, `cost: 0`). They are what step 2b's extraction (the loop's pi driver) reads: keep the shape plain.

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
