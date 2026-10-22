# web — the world map (alf-demo step 3a)

One renderer for every world's map, over one schema, with a tileset per world
(`alfworld/docs/DEMO.md` §8). World-neutral and framework-free; a page copies it, as the
console copies fsttm-web's lib (copies, not dependencies).

| path | what |
|---|---|
| `map.js` | `WorldMap(el, {base, onTask, onAttend})`: `load(url or map)`, `delta({agent, entities, cells, hot, task})`, `showTask(id)`, `entries()`; `toGrid(semanticMap)` puts a §3 map (places with metric positions) on a grid |
| `map.css` | the look; theme tokens (`--wm-*`), light and dark |
| `map.html` | a static page with both fixtures (`?theme=light|dark`, `?mh=` / `?alf=` another map) |
| `fixtures/minihack_room_medium.json` | a MiniHack level's first screen from its `glyphs` observation (`minihack/world/map_export.py`) |
| `fixtures/alfworld_tomato_microwave_13.json` | an ALFWorld scene's semantic map in text mode (`alfworld/world/semantic_map.py`): the task "Put a tomato in the microwave." |
| `assets/` | the base tileset: NetHack's art, **not Apache** — see `assets/NOTICE` |
| `tests/map_e2e.mjs` | the page end to end in headless Chrome (real mouse and keys) |

## The schema

```json
{"cols": 8, "rows": 5, "cells": [[{"t": 2359, "ch": "."}, null, …]],
 "entities": [{"id": "newt@c2_3", "name": "newt", "pos": [2, 3], "tile": 318, "ch": ":", "kind": "monster",
               "frame": null, "items": [], "hot": false}],
 "agent": {"pos": [0, 3], "yaw": null, "tile": 329, "ch": "@"},
 "task": {"text": "the words the task was given in", "goal": "fetch(tomato1, microwave1)",
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
.worlds/mh/bin/python tools/tiles_export.py EDITOR_CHECKOUT    # assets/ (EDITOR_CHECKOUT: minihack-editor.github.io)
cd minihack && ../../.worlds/mh/bin/python world/map_export.py domains/room_medium_apple_newt_closed_none ../web/fixtures/minihack_room_medium.json
cd alfworld && ALFWORLD_DATA=… ../../.worlds/alf/bin/python world/semantic_map.py GAME_DIR ../web/fixtures/alfworld_tomato_microwave_13.json ../../alfworld/tiles/index.json
node web/tests/map_e2e.mjs                                      # node >= 22, google-chrome (or CHROME=)
```

The worlds' suites check that the committed fixtures and the sheet are what these write.
