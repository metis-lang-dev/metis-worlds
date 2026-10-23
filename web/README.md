# web — the world map and the world page (alf-demo steps 3a, 3b)

One renderer for every world's map, over one schema, with a tileset per world
(`alfworld/docs/DEMO.md` §8). World-neutral and framework-free; a page copies it, as the
console copies fsttm-web's lib (copies, not dependencies).

| path | what |
|---|---|
| `map.js` | `WorldMap(el, {base, onTask, onAttend})`: `load(url or map)`, `delta({agent, entities, cells, hot, task})`, `showTask(id)`, `entries()`; `toGrid(semanticMap)` puts a §3 map (places with metric positions) on a grid of the map's `cell` metres (default 0.5; ALFWorld's maps say 0.25) |
| `map.css` | the look; theme tokens (`--wm-*`), light and dark |
| `map.html` | a static page with both fixtures (`?theme=light|dark`, `?mh=` / `?alf=` another map) |
| `fixtures/minihack_room_medium.json` | a MiniHack level's first screen from its `glyphs` observation (`minihack/world/map_export.py`) |
| `fixtures/alfworld_tomato_microwave_13.json` | an ALFWorld scene's semantic map in text mode (`alfworld/world/semantic_map.py`): the task "Put a tomato in the microwave." |
| `tiles/` | the base tileset: NetHack's art, **not Apache** — see `tiles/NOTICE` (not `assets/`: an installed fsttm_web claims `/assets/` and `/lib/` on metis-agent's server) |
| `world.html`, `world.js` | the world page (3b, DEMO.md §4–§5), in the consoles' shell (the band, the docks TALK / HIERARCHY / JOURNAL, the strip; dark): the map, the band's **status line** (`world/status`: waiting with the game's task, working, asking, stuck, done, over, with its chips: "new game"), the **ask** (`world/ask`, or an ask line's `| answers`: the question highlighted, its answers as chips; a chip says its answer as typing it would), the dialog (fsttm-web's panel: an ask row says "asks", the typed intent as its name and slots), the hierarchy of the domains at work (the director's atoms; the goal beside the attending domain; reset under a new task), the journal (metis-agent's model; the page's own world lines left out); `?replay=fixtures/x.run.jsonl` a recorded turn (play / step), `?live=1` metis-agent's `/ws` (`run.sh`) |
| `vendor/` | the page's copies: fsttm-web's `lib/` (panel, dialog, floor, tts, ws), metis-loop's `ui-port.js` and `shell.css` / `shell.js` (the consoles' common style; equal past their header to metis-loop's and metis-agent's: `tests/test_shell_copies.py`), metis-agent's `journal.js` (not `lib/`: an installed fsttm_web claims `/lib/` on metis-agent's server) |
| `domains/world_ui/` | the page's voice navigation: `world_ui.llp` (facts only) over `ui_domain.llp` (a copy of the lifted base v6.5, `COPIES.md`), the card (`intent.yaml`, `intent/`), the host, 14 cases. The map is a list: its things are picked by name or number |
| `fixtures/*.run.jsonl` | recorded turns (`alfworld/experiments/record_run.py`): the win ("put a tomato in the microwave") and a disengagement (the fridge) |
| `run.sh` | the live stack: metis-agent's service serving `world_ui` on Gemma E2B (local), the page at `http://127.0.0.1:8397/world.html?live=1` |
| `tests/` | `map_e2e.mjs`, `world_e2e.mjs`, `live_e2e.mjs` (the live service's recordings: the status line, the ask chips, a new game, the shell's docks; headless Chrome, real mouse and keys, `cdp.mjs` the harness); `test_world_ui.py` (the cases in both toolchains, the card, the host, the copies), `test_shell_copies.py` (the shell equal to the consoles') |

## The schema

```json
{"cols": 8, "rows": 5, "cells": [[{"t": 2359, "ch": "."}, null, …]],
 "entities": [{"id": "newt@c2_3", "name": "newt", "pos": [2, 3], "tile": 318, "ch": ":", "kind": "monster",
               "frame": null, "items": [], "hot": false}],
 "agent": {"pos": [0, 3], "yaw": null, "tile": 329, "ch": "@"},
 "task": {"text": "the words the task was given in", "goal": "fetch(tomato1, microwave1)",
 "card": {"title": "ALFWorld kitchen FloorPlan13", "about": ["what this world is", "…"],
          "room": [{"type": "cabinet", "n": 26, "ids": ["cabinet1", "…"], "openable": true}],
          "things": [{"type": "tomato", "n": 2, "ids": ["tomato1", "tomato2"]}],
          "asks": [{"say": "put a tomato in the microwave", "what": "this game's task: the one that wins the game"}, {"say": "stop", "what": "…"}],
          "cannot": ["a single step on its own …"], "source": "generated from the game's facts by world/semantic_map.py"},
          "chain": [{"domain": "nav", "goal": "goto(countertop3)", "result": "reached(countertop3)"}],
          "results": ["I go to countertop3."], "source": "…"},
 "tileset": {"index": ["the world's own index, relative to this file"]}}
```

A tile is a glyph id (a number: the glyph sheet), a name (a string: the merged index; a name's
trailing digits are dropped, so `cabinet3` draws as `cabinet`), or `{t, ch}`. An index is
`{name: {image?, glyph?, color?, source}}`. The page's base is the editor's 648 named icons and
the glyph sheet. A world adds its own entries (`alfworld/tiles/index.json`) and they win. An
entry with no image draws its glyph character, and a name with no entry draws its `ch`, else its
first letter: a tile never fails to draw.

The page asks for nothing at runtime. Each thing on the map is a focusable button named for what
it is (a voice JUMP labels them). Hover or focus shows it in the attention slot: its picture, its
frame, what is in it. A click, Enter or Space opens the task card: the original words, the goal
atom formalization made of them, the specialist chain so far, and the result lines.

## Regenerating

```sh
.worlds/mh/bin/python tools/tiles_export.py EDITOR_CHECKOUT    # tiles/ (EDITOR_CHECKOUT: minihack-editor.github.io)
cd minihack && ../../.worlds/mh/bin/python world/map_export.py domains/room_medium_apple_newt_closed_none ../web/fixtures/minihack_room_medium.json
cd alfworld && ALFWORLD_DATA=… ../../.worlds/alf/bin/python world/semantic_map.py GAME_DIR ../web/fixtures/alfworld_tomato_microwave_13.json ../../alfworld/tiles/index.json
node web/tests/map_e2e.mjs; node web/tests/world_e2e.mjs; node web/tests/live_e2e.mjs        # node >= 22 (see below), google-chrome (or CHROME=)
METISC=… python -m pytest web/tests -q                          # a python with metispy (the perotheia-packages .venv)
cd web && python -m metis.intents gen world_ui                  # the card's intent/ files
cd alfworld && ALFWORLD_DATA=… METIS_PY=… ../../.worlds/alf/bin/python experiments/record_run.py GAME_DIR ../web/fixtures/alfworld_tomato_microwave_13.json OUT.run.jsonl "the words" [GOAL]
```

The worlds' suites check that the committed fixtures and the sheet are what these write.

**Node:** the e2e test needs node ≥ 22 (its global `WebSocket`); the system's node is older.
Use the pinned one from metis-loop, `pi/node/bin/node` once `pi/setup.sh` has run there
(`NODE=…/metis-loop/pi/node/bin/node $NODE web/tests/map_e2e.mjs`).
