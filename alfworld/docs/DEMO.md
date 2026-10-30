# The exploitation demo: a discovered ALFWorld with a web UI and a voice dialog (architect design, 2026-10-22)

The user (2026-10-22): "Rules or an LLM for activation — wrong dichotomy. Definitely rules, but
if task agency comes from the user we need an agent to make the world interactive: the user
gives a task and the orchestrator chooses a tool. So the first step is world discovery,
autonomous or guided; the second is exploitation, guided by the user's request. The second
part deserves a demo on ALFWorld: a world semantic map with images, a Metis agent with the
domain hierarchy, a web UI with a voice interface. Pay attention to reusable parts from the
Metis stack and UI; we will refactor for reuse on other worlds' demos. Eventually we form a
framework complementary to the agentic loop that gives a discovered world a user interface on
the web UI and the dialog system."

Companions: HIERARCHY.md (the specialists, the manual switch, the director as built),
metis-agent docs/DIRECTOR.md (activation as a domain), metis-agentic-loop docs/POLICY.md (the
loop's phases; discovery is its exploration phase), metis-agent docs/FRAMEWORK.md (the dialog
wire, domains as plugins), the console-nav brief (the lifted voice navigation of widgets).

**Superseded (2026-10-24, voice-nav-removal s-90621b2c):** the voice navigation of the page is
gone. The user dropped it as a mix of two paradigms: the web UI of the last 30 years, and the voice
UX of a small LLM augmented with the metis runtime. One voice paradigm remains, the dialog. The
page's affordances turn INTO the chat (the world card's ask chips, the status line's chips), never
the other way round. `web/domains/world_ui`, `vendor/ui-port.js`, `web/run.sh` and `demo.sh --nav`
are removed; the page runs on the game alone. Below, the voice-nav rows are the history.

## 0. Running it today: a room, and the person's tasks (alf-tasks s-e9cc8fae, 2026-10-29)

The user (2026-10-28): "we reload games and i cant give agent any tasks besides one hardcoded into game episode".
Now the picker loads a ROOM: the game file carries the room's state only, and the person gives the tasks, one after
another, through the intent interface.

    cd metis-worlds/alfworld
    ./demo.sh --tw                      # kitchen 13 as a room; the page: http://127.0.0.1:8398/world.html?live=1
    ./demo.sh --tw "bathroom 401"       # another room by its label (./demo.sh --list names the 107)
    ./demo.sh --tw --view "kitchen 13"  # the robot sees only what stands before it: unseen things are searched for
    ./demo.sh --tw --episode Bowl-None-Fridge-6   # the old way: the game as one task, its own goal wins and ends it

**The room.**
- **Why the episode no longer ends anything.** TextWorld's gym env freezes once the episode's own goal holds: every
  later command repeats the last observation. A room is played on the PDDL env underneath (`alf_gym` `room`), which
  steps on. The episode's goal is still read (`episode_won`, reported) and never ends the session.
- **No task in the map.** The map has no task of its own: the person's goal binds the roles.
- **The picker.** The top bar's picker lists one room per ALFRED scene (24 kitchens, 28 living rooms, 27 bedrooms,
  28 bathrooms). The picker shows the house: the room started in and the first of each other type, the rest behind "choose another
  room…" (a room chosen there joins the house). A pick moves the agent to that room with nothing restarted (rooms
  s-b51a2e80), and a room it comes back to stands as it left it: things where they were put, the places looked into, on the
  page too. Measured (kitchens, GPU): a full restart 13–18 s; a room's first entry 5–15 s; a return 2–5 s. Each room keeps a
  world process (92 MB), at most 4 (METIS_ALF_WORLDS), the longest idle closed; a room returned to after that replays
  its commands log (1.9 s at 10 commands, 10 s at 200).

**The tasks.** The task card (`domains/hier/task/intent.yaml`) maps the words; the program says the lines; the
agent only renders them.

| the person says | the agent |
|---|---|
| put the apple on the countertop / take the mug to the sink / move the pepper shaker to the drawer | does it: nav, access, grasp, place, one sub-goal at a time |
| move the pepper shaker to a shelf (kitchen 13 has none) | "There is no shelf in this room." |
| put the tomato in the drawer (ALFWorld's cancontain forbids it) | "Tomato 1 cannot go in or on drawer 3: this world does not allow it." |
| heat the apple / wash the mug / chill the wine | "Sorry, heating is not a task I know: I move things from place to place." |
| bring the teddy bear to the fridge (a kind ALFWorld has, not this room) | "There is no teddybear in this room." |
| bring the toy to the fridge (the model guesses a thing the words never name) | "I didn't hear toiletpaperroll in what you said: say it again with the thing's name?" (metis-agent's slot grounding over the card's `grounded:` slots: never a substitution) |
| bring me the egg (no place) | "I need the receptacle too: say it again with it?" |
| a word outside ALFWorld's vocabulary (banana) | the world card's line: what this world is, what to ask |

**Several tasks in a row.**
- Each starts without a reload, re-binding the roles.
- A thing still in the hand (after a "stop") is put down where the robot stands first: "Tomato 1 is down: now I
  fetch egg 1 to countertop 1."

**The search (`--view`).**
- **The prior.** A kind not seen yet is believed over the places that can hold it: ALFRED's compatibility
  (`world/cancontain.json`, the union over the dataset).
- **The existence belief.** The kind also has an existence belief: its room type's frequency in ALFRED
  (`world/presence.json`), lowered by every place looked into without it, quantised as presence(likely | doubtful |
  improbable).
- **The planner says** "No apple seen yet: I look in microwave 1 first." (the task results on the page; the
  specialists' lines are the ones voiced).
- **The search stops**
  - at "There is probably no kettle in this room: I stop looking." (a kitchen kettle: after about half the places; a
    bathroom kettle: at once), or
  - at "There is no X in this room: I looked everywhere it could be."

**Our own check, and a card per task.**
- **Success is the hierarchy's, never the episode's `won`.** At each task's end, ROOT/records/tasks/task-NN.json
  (ROOT: `alfworld/.metis/demo`) holds:
  - the goal in the room's names, and its roles;
  - the outcome, the ticks, the seconds and the commands;
  - the map's belief records meanwhile;
  - `check`: for done, the goal holds in the world's facts as observed (`goal_holds`), and `agrees` says whether the
    end and the world agree.
- **Refusals and stops.** A refusal, or a task stopped before its end, says the check does not apply.

**The consoles.**
- The world page runs on metis-agent's **py** service (`demo.sh`).
- The Go agent has no director and no world/* frames, so it does not run this demo.

**What to try** (nina's Chrome check):
1. kitchen 13: "put the apple on the countertop", then "move the bowl to the cabinet", then "put a tomato in the
   microwave" (the episode's own goal: "Done. Tell me another task.");
2. one impossible: "move the pepper shaker to a shelf";
3. then `--view` with "bring the kettle to the sink".

## 1. The two phases, and who has the agency

| phase | agency | what runs | what it produces |
|---|---|---|---|
| **discovery** | the loop (autonomous) or the person (guided: "look in the drawers") | the agentic loop's exploration (POLICY.md) over the world's port, or the oracle's scene exploration | the **semantic map** (§3) and the domain hierarchy (HIERARCHY.md): places, things, what can be done to what, as rules |
| **exploitation** | the person: a task in words | the director (rules) + the specialists, the person's words typed by E2B into the attended card | the task done in the world, every step visible on the map and said in the dialog; a cornered loop disengages and asks |

Rules route; the model only types words. This is DIRECTOR.md's division, unchanged: the person's
utterance becomes an intent of the task specialist's card (`fetch(mug, desk)`), the director
wakes the specialists in turn by the result kinds (HIERARCHY.md §director), and nothing in the
hierarchy is chosen by a model. What the demo adds is the person at the top: the *task* is
theirs, so a task card and a dialog are needed, which the measured runs (REPORT.md) did not
have — they seeded `fetch` from the game's own goal.

## 2. What ALFWorld gives (checked on 2026-10-22, alfworld 0.4.2 in `.worlds/alf`)

- There is **no "semantic map" in ALFWorld**. The name is **AI2-THOR**, the 3D household
  simulator behind every game: each text game is a THOR scene (`traj_data.json` →
  `scene.floor_plan` = `FloorPlan301`, `scene.object_poses` = every object's x,y,z,
  `scene.object_toggles`, `dirty_and_empty`). `ai2thor 2.1.0` is installed in the world's venv;
  its Unity build (`thor-201909061227-Linux64.zip`) is still served from S3 (HEAD 200 on
  2026-10-22) and **not yet downloaded** on taycann (`~/.ai2thor` absent). THOR needs an X
  display with OpenGL: taycann has `:0` live and an RTX PRO 2000 (8 GB) — the E2B gguf
  (~3 GB) and THOR's window fit together.
- `AlfredThorEnv` (alfworld/agents/environment) runs **the same text commands** as the
  TextWorld games (`go to desk 1`, `open drawer 2`, `take mug 1 from desk 1`, `move mug 1 to
  shelf 1`): the **oracle controller** teleports to the receptacle's pre-computed point
  (`openable_points`, ALFRED's) and interacts with ground-truth instance masks. So
  `alf_gym.py`'s protocol does not change; a THOR backend is one more `open` option.
- **The oracle's `explore_scene` is the discovery pass**: at reset it teleports to every
  receptacle point, keeps a 300×300 RGB frame per visit (`exploration_frames`), reads the
  instance segmentation, and builds `receptacles[object_id] = {object_type, locs (pose),
  num_pixels, num_id "desk 1", closed}`; each later visit (`print_frame`) adds the visible
  objects with their parent receptacle. That table **is** a semantic map: places with a pose
  and a picture, things at places. We render it, we do not invent it.
- Images of the dataset's trajectories are not in `json_2.1.1` (only frame names); every image
  the demo shows is rendered live by THOR. THOR's event metadata also gives every object's
  position, `parentReceptacles`, `isOpen`, `visible` — the plan view is drawn from it.
- The Mask R-CNN detector (`detectors/mrcnn_alfred_objects_sep13_004.pth`, BUTLER's `mrcnn`
  controller) is the **discovery-from-pixels** option: same text commands, objects found by a
  detector instead of ground-truth masks. Not in the demo; it is the honest later step of the
  discovery phase (the semantic map built from what a detector saw).

## 3. The semantic map (world-neutral schema, ALFWorld instance)

One file per game, `map.json`, plus a `frames/` folder, written by the world's discovery pass
and read by the UI, the agent and the tests:

```json
{"world": "alfworld", "scene": "FloorPlan301", "units": "m",
 "places":  [{"id": "desk 1", "type": "desk", "pos": [1.8, -1.1], "yaw": 90, "openable": false,
              "frame": "frames/desk_1.png"},
             {"id": "drawer 2", "type": "drawer", "pos": [...], "openable": true, "frame": "..."}],
 "things":  [{"id": "mug 1", "type": "mug", "at": "desk 1", "pickupable": true}],
 "agent":   {"pos": [x, z], "yaw": 0, "at": "desk 1", "holding": null},
 "edges":   [["desk 1", "drawer 2"]],
 "overview": "frames/overview.png"}
```

- `places` = the receptacles (HIERARCHY.md's `recat(R, L)` with the pose from the oracle's
  `locs`); `things` = the objects with `inrecep`; `agent` = `at` + `holding`; `edges` =
  reachability (all pairs in ALFWorld: `go to` teleports; a grid world fills them from its
  map); `overview` = a top-down frame if the build supports it, else the plan drawn from
  `pos` alone (to verify in step 0; the plan from positions is enough for the demo).
- In **text mode** (no GPU, CI) the same `map.json` is built from the PDDL facts and
  `traj_data.json`'s `object_poses`, with no frames. Everything downstream works on both;
  pictures are what THOR adds.
- **Updates** are the dynamic facts the host already reads (`at`, `inrecep`, `holding`,
  `closed`): after every command the world emits `pose`/`at`/`holding`/`closed` deltas plus
  the fresh frame; the map file is the discovered state, the deltas are the live state.

## 4. The pieces and what is reused

```
 browser: the WORLD PAGE                               metis-agent (py backend, :8395)
 ┌──────────────────────────────────────────┐   /ws    ┌──────────────────────────────────────┐
 │ map pane ─ plan from map.json, the agent │ ◄──────► │ console backend (wire v1 + world/*)  │
 │   dot, frames on attention, highlights   │          ├──────────────────────────────────────┤
 │ dialog band ─ fsttm-web lib (copied):    │          │ director (rules) + task + specialists│
 │   mic · floor · TTS · panel              │          │   served from metis-worlds/alfworld/  │
 │ hierarchy pane ─ active/attention/pending│          │   domains/ (cwd-root: cd = root)     │
 │ journal ─ journal.js (copied)            │          │ E2B types words → task card          │
 │ (voice nav: removed 2026-10-24)          │          ├──────────────────────────────────────┤
 └──────────────────────────────────────────┘          │ world plugin: alf_host.py ─► alf_gym │
                                                        │   (thor | tw backend) ─► THOR / TW   │
                                                        └──────────────────────────────────────┘
```

| part | reused from | new |
|---|---|---|
| world port (open/reset/step JSON lines) | `world/alf_gym.py`, `alf_host.py` (world-alfworld) | `backend: thor` in `open`; ops `map` (write `map.json` + frames), `frame` (last frame), `pose` |
| semantic map builder | the oracle's `explore_scene`/`print_frame` tables (alfworld) | `world/semantic_map.py`: oracle tables → §3 schema; text-mode fallback from PDDL + `object_poses` |
| specialists + director | `domains/hier/*`, `domains/director_domain.llp`, `gen_hier.py` (HIERARCHY.md) | a **task card** for the person's words (opus's intent cards, step 2, extended with FETCH's two slots and the map's `values`) |
| orchestration | metis-agent py backend: director + attended card (alf-hierarchy step 3, opus), `handles/2` generator (nina, SDK) | the world as a `process` plugin (`plugin: process`, `host: world/alf_host.py:make`) — FRAMEWORK §4, no new plugin kind |
| dialog | fsttm-web `lib/` (fsttm, attention, dialog, tts, panel) copied into the page (copies-not-deps) | nothing in fsttm-web; the page composes it |
| wire | metis-agent WIRE.md v1 (`say_text` → `intent`/`narration`, `activate`/`deactivate`, journal `dlg-*`) | one frame family `world/*`: `world/map` (the file's URL), `world/delta` (pose/at/holding/closed), `world/frame` (png) |
| ~~voice navigation of the page~~ (removed, voice-nav-removal) | console-nav's lifted `ui_domain.llp` base (focus tree, activation ports, JUMP/held modes) | `world_ui.llp`: the instance for the page's widgets (map, places, dialog, hierarchy, journal); the map's places are jumpable by name ("show the drawer") |
| page shell | metis-agent `console/` (index, shell.css/js, journal.js) | `world.html` + `map.js` (SVG plan, ≤ 300 lines) |
| run script | `run.sh` pattern (metis-agent, metis-loop) | `alfworld/demo.sh`: starts THOR + the agent from the world root; `--tw` for text mode |

Nothing of this goes into metis-catalog; the world repo owns its map builder and page; the
Metis stack is used as it is, with two additions it needs anyway (the world frame family on
the wire, the task card's `values` from the map).

## 5. One exploitation turn, end to end

1. The person: "put the mug on the desk" (mic, or typed; fsttm-web's floor as today).
2. E2B, serving the director's card and the attended card (task), types `fetch(mug 1, desk 1)`
   — the slot `values` come from `map.json` (`things`, `places`), so the words resolve to the
   map's ids; an unknown thing is the card's refusal, not a guess.
3. The director: `wake(task)`, `forward(task, fetch)`; task emits `goto(desk 1)` →
   `wake(nav)` … exactly HIERARCHY.md's §director chain: nav → (access) → grasp → nav → place
   → task `done`. Every `wake`/`sleep` is a `world/delta`-free wire event the hierarchy pane
   shows; every world command is a `world/delta` + `world/frame` the map pane shows (the dot
   moves, the drawer opens, the frame changes); every result's `%%` line is said by the
   narrator through the band.
4. **Disengagement** (POLICY.md): a `stuck`/`wrong_dest`/`wrong_object` result ends the task
   with `ask(K)`; the band asks ("the mug is in a closed drawer I cannot open — open it?"),
   the person answers, the director routes the answer as a new intent or stops. The page
   shows the cornered state on the map (the place in red).
5. The journal records the turn as `dlg-*` + the world's records (gitignored), replayable
   without THOR in text mode: the demo's test.

## 6. Steps (one subject, `alf-demo`; depends on alf-hierarchy step 3 and console-nav step 2)

- **Step 0 — THOR bring-up (the architect, with the user for the download).** First run of
  `ai2thor.Controller` downloads the Unity build to `~/.ai2thor` (size shown by the
  downloader; the user approves the download). Acceptance: one train game runs through
  `AlfredThorEnv` with the oracle on `:0` with the four commands of a fetch, the exploration
  frames saved; the measured per-command latency recorded. If THOR 2.1's 2019 build does not
  render on this driver, fallback = Xvfb, then text mode for the demo with the map from
  `object_poses` (no pictures) — reported, not hidden.
- **Step 1 — the world side (the architect).** `semantic_map.py`, the `thor` backend and the
  three ops in `alf_gym.py`/`alf_host.py`, text-mode fallback, tests (`map.json` schema on
  both backends; a fetch on THOR equals the same fetch on TW fact for fact).
- **Step 2 — the agent (opus, after alf-hierarchy step 3).** The world as a process plugin of
  the py backend, the task card with `values` from the map, the `world/*` frames on the wire,
  the director's `ask` reaching the band, `demo.sh`. Acceptance: the five-turn script of §5
  replayed in text mode without a browser (the backend's test), 10 train games by voice-less
  `say_text`.
- **Step 3 — the page (nina, after console-nav step 2).** `world.html` + `map.js`, the dialog
  band and journal copied in, the hierarchy pane; acceptance: the e2e page test drives §5 with
  frames from a recorded THOR run (fixtures). (Its `world_ui.llp` voice navigation was removed by
  voice-nav-removal, 2026-10-24.)
- **Step 4 — the user's session (USER GATE).** Live, on THOR: a task by voice, a detour, a
  disengagement answered by voice.

## 7. Toward the framework (after the demo; not built now)

The parts that are world-neutral by construction and get lifted out when the second world
(MiniHack: the map = the dungeon grid, frames = the tty render) needs them:

1. the **world port** = the PortPlugin contract + three ops (`map`, `frame`, `pose`);
2. the **semantic map schema** (§3) and its **map widget** (`map.js`);
3. the **director** base (already lifted: `director_domain.llp`) with its instance generator, and the
   role vocabulary with the host's semantic map (semantic-map s-d4270bed) — the ui navigation base
   is gone (voice-nav-removal);
4. the **world page** composition (map + band + hierarchy + journal) over metis-agent's wire.

That is the complement of the agentic loop: the loop discovers and formalizes a world into a
hierarchy; this gives the formalized world its face and its ear. Both consume the same catalog
root (cwd-root's rule), so a world repo is a domain root for both.

## 8. Map rendering (the user's pointers, checked 2026-10-22)

- **liujonathan24/NetHack-engine** is an engine, not a renderer: Python over a custom
  NetHack C fork, "one canonical map model behind every encoding" (ASCII, JSON, tiles in a
  harness layer). Its sibling **NetHack-console** draws the map as glyph TEXT into the page
  (tty style, a WASM NetHack). **Neither repo has a license file**, so nothing of their code
  is reusable; only the idea — one map model, several encodings — which §3 already is.
- **minihack-editor/minihack-editor.github.io** (Apache-2.0, a React 17 CRA app) has what we
  want: **664 named PNG icons** (13 dungeon, 273 items, 378 monsters) scraped from
  NetHackWiki with JSON indexes `name → image → glyph char/colour → wiki link`, and a
  des-file compiler in JS (grid → `MAP…ENDMAP` + `MONSTER`/`OBJECT` footer). The icons are
  NOT Apache: NetHackWiki publishes NetHack-derived images under the NetHack General Public
  License (others CC BY-SA 3.0), so they live in their own `assets/` folder with its own
  NOTICE, never inside an Apache source tree. The React canvas itself is not worth lifting.
- **Already in our venv:** MiniHack's `tiles.pkl` = 1082 glyphs × 16×16 RGB, the NetHack 3.6
  tileset keyed by GLYPH ID — exactly what NLE's `glyphs` observation gives. Exported once to
  a sprite sheet PNG + `glyph → index` JSON, the page draws a level from `glyphs` with no
  mapping step. The editor's named icons serve the legend, hover and the places list
  (readable at any size).

**`map.js`, world-neutral by construction:** a grid renderer over one schema —
`{cols, rows, cells: [[tile]], entities: [{id, name, pos, tile, frame?}], agent: {pos, yaw},
tileset: {sheet, size, index}}` — plus a hover/attention frame slot. The tileset is the only
world-specific part: MiniHack = the glyph sheet; ALFWorld = the semantic map's places on a
coarse grid (THOR x,z quantized to 0.5 m), editor icons for the tiles (chest for an openable
receptacle, a generic tile otherwise) and the THOR frame on hover; the agent as `@`. The
ALFWorld → MiniHack export (world-minihack's note: a des-file per scene, `CONTAINER` for the
openable receptacles) reads the same schema, so a scene renders identically before and after
the export. That is the "check reuse for other worlds' maps": one renderer, one schema, a
tileset per world.

**The user (2026-10-22): "reuse tiles and get the mapping; the real task is to add objects from
a new world; clicking an object should show the task description — we see the trace and the
narration, but the original task is consumed by formalization."** So:

- **The tileset is extensible per world, and the mapping is the world's.** A tileset is a JSON
  index `{name: {image, glyph?, source}}` plus images. The base index is the editor's (664
  named icons) and the glyph sheet; a world ADDS entries for its own objects in its map
  folder (`alfworld/tiles/index.json`: `mug`, `desk`, `drawer`, … → an icon where NetHack has
  one — `chest` for an openable receptacle, `apple` — or a crop from the THOR frame of the
  place where the object was first seen, written by `semantic_map.py` at discovery). The
  page merges the world's index over the base; a name with no entry draws as its glyph
  character, never fails. Adding a world = adding an index, no renderer change.
- **The original task travels with the instance and is shown on click.** Formalization turns
  "Pick up the alarm clock and turn on the lamp" into `fetch(alarmclock 1, desklamp 1)` and
  the words are gone from the trace. So `game.json`/`map.json` keep `task: {text, goal,
  source}` (the world's own description: ALFWorld's `task_desc`; for a person's task, their
  utterance as said), and the page shows it: a click on the agent, on a highlighted entity or
  on the hierarchy pane's task row opens the task card — the words, the goal atom, the
  specialist chain so far, the result lines. The journal keeps the person's utterance beside
  the typed intent for the same reason (metis-agent already journals `say_text`).
