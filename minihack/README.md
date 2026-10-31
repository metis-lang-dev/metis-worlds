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

## Over roles: the level is the host's map (semantic-world s-227b8e1b step 2)

| path | what |
|---|---|
| `world/mh_hier.py` | MiniHack as a hierarchy, ALFWorld's shape: `director` (the lifted `domains/director_domain.llp`, metis-catalog's byte copy), `task` (the person's REACH → `goto(goal)`; `reached(goal)` → done), `nav` (one step a beat along the host's route; a closed door → `closed(p)`, a beast → `guarded(p)`; on the stairs `reached(goal)`), `act` (open a door — told it is locked, kick it until it gives —; fight a beast). Every domain compiled once over the capacity (`goal p1..pk`, `target other`, `b1 b2`): the same bytes for a 4 × 5 room and a 76 × 21 cave (`tests/test_the_hierarchy_is_one_program_for_every_level`). `install(level, root, view, k)` writes the packages, the map store, one shared NLE process and metis-agent's `.run/config.yaml` |
| `world/mh_director_host.py` | the director's host: the arrivals, a domain's activation as the world in roles through the map's binding |
| `world/mh_host.py` | a level with a `map` (level.json) is read through `semantic_world.grid.GridMap` (libs/semantic-world): each step `cycle`s the map (the beasts predicted — a hostile walks toward the robot, a peaceful holds, the unseen fade —, then the sighting), the binding moves at the beat's input (`tick`), the reading is in roles (`next(p, d, q)`, `toward`, `step`, `door`, `stairs_down` between bound cells); a hierarchy's hosts share one NLE process; the level won is not the run's end (`continues`) |
| `world/gen_level.py` `generate_roles` | one role program for the room family (a STAND-IN base: MiniHack's domain is what the loop extracts), or `flat`: the same rules over the level's own cells (the comparison) |
| `world/perceive.py` | a des that pins the start to one cell (`BRANCH:(x,y,x,y)`) places the screen's top-left by the robot (a dark level's first screen is the eight cells around it); `said(whamm)` (a kicked door holds) |
| `experiments/sw2_hier.py` | the hierarchy's cases (design §4: 1 the room, 2 the exerciser's 76 × 21 cave, 3 a closed then a locked door, 7 view mode: the frontier first; a beast in a corridor), one process per case, on CPU, no model: `setup OUT`, then `run OUT` under metis-agent's venv |
| `experiments/sw2_roles.py` | one role program against the flat instance: the room's win turn, the grounding at load |

The exerciser's levels (`semantic_world.dungeon`: caves from the article's algorithm, rooms and corridors) are NLE
levels through `Level.des()` (`tests/test_an_exerciser_level_opens_in_its_own_coordinates`).

## The real game on the page (`./demo.sh`)

`http://127.0.0.1:8399/world.html` (ADDR): real NetHack on its own page (`web/`), independent of ALFWorld. What the two share is external: the agent (metis-agent) and the dialog (fsttm-web).

| path | what |
|---|---|
| `nethack/build.sh` | NetHack 3.6.6 from source into `.nethack/` (gitignored) with `TTY_TILES_ESCCODES` on: the tty names each cell's tile. Apt's build has it off, and a character and colour alone are ambiguous for 55% of the monsters and 93% of the objects |
| `world/nh_tty.py` | the game behind a pty, its screen in pyte, each map cell with its tile (Tilehack's idea, rewritten for 3.6.6's codes) |
| `world/nh_gym.py` | `mh_gym.py`'s protocol over the real game: the screen as the hierarchy's atoms, prompts answered, the page's `world/*` frames |
| `world/nh_host.py`, `world/nh_hier.py` | `MhHost` over that world (view mode: nothing known until seen; a new level starts the map again), the hierarchy installed for metis-agent's service: the person's words through the model: an errand (`reach(goal)`: the director, task, nav and act) or one command (a move, a search, a pick-up, the stairs). The watch's surprises are off here (`observe`) until the loop makes the domain |

**The map's view** (`web/viewport.js`): the box takes what the layout gives it; the wheel zooms round the pointer, a drag moves the view, the buttons zoom, go to 1:1, fit all that has been seen and centre on the hero (following him until the next drag or wheel). **New game** (the top bar, two presses): the game and its save are gone, a new hero in a new dungeon. The hero's inventory is read from the game's own page (it takes no turn) and shown under the status.

**Surprises** (`world/nh_host.py`, `.metis/nh-records/surprises.jsonl`, the journal pane): a command of the rules' own that did not do what it says (`missed`: a step that left the hero elsewhere, a blow not struck, a door with no answer), or a message the perception has no word for (`unread`). Play goes on: the watch's own record would stop the agent until a consult closes it, so `observe()` keeps it closed. **A stall**: an errand with no turn and no move for 20 s stops through the task's own `stuck_on` and the person is asked.

The tile numbers index `web/tiles/nethack/glyphs.png` (this directory's) directly (`raw_tiles`, `tests/test_nh_tty.py` compares all 1082 by pixel). Glyph numbers differ from NLE's: this build has the mail daemon. The keyboard goes straight to the game (world lines on the agent's wire); chat lines are the model's to read, except a single key, a count and a key, or a #command. Stopping the service saves the game and the next start restores it.

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
