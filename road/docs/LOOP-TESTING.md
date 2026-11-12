# LOOP-TESTING: the pi loop on the road page, for a tester in Chrome (loop-road-ui s-0314a8ee step 3) — WIP

**Status: WIP, paused by the user's order of 2026-11-13 (attention to the CARLA stack).** Written by bond. Not yet driven
in Chrome: the browser extension was not connected in that session. What was checked, and what was not, is listed at the end.

## Start (two terminals, one SUMO at a time)
1. The road page: `cd metis-worlds/road && ./demo.sh` → http://127.0.0.1:8400/world.html
   - For CommonRoad on pascal: `COMMONROAD_ROOT=/bigdata/dataset/commonroad ./demo.sh`. demo.sh defaults to `/bigdata/datasets/commonroad`, a path that does not exist on pascal.
   - From a git worktree that is not beside `.worlds/`: set `SUMO_VENV=<packages>/.worlds/road`.
2. The loop console over the same workspace: `cd metis-worlds/road && METIS_HOME=../../metis-catalog/domains/road ../../metis-loop/run.sh`
   (:8770). The road page's LOOP dock frames it (`?panels=chat&embed=…`).
3. The budget: in the LOOP chat, `/budget 1` (USD, a session) before the first words to pi. The spend is in the chat's header and in `.metis/cost.jsonl`.

## Flow A: see a problem, mark it, agree or disagree (0 USD)
Run a card (SCENARIOS tree, double click). When the car does something wrong, say **"mark"**, and when it is over, **"end mark, WORDS"**.
The loop narrates the window in the rules' own words. Then:
- **"agree"** closes the mark as a pass: nothing is recorded.
- **"disagree, WORDS"** keeps a confusion record and runs the triage.

Typed in the LOOP chat instead: `/mark RUN:planner K0..K1 WORDS`, `/agree`, `/disagree WORDS`.

## Flow B: the loop rules it (paid)
**"take it"** (`/take`): pi takes the surprise, writes a pack and judges it. The ruling card appears in the dock and its first lines are spoken.
Then:
- **"why …"** (`/why planner at K`) and **"show the ruling"** (`/ruling`).
- **"apply"**, then answer the gate by voice with **"confirm"** or **"refuse"**.
  An apply onto the family's units (METIS_HOME) is refused today (loop-chat s-f6c32d0c step 4, open).
- **"rebuild"**, **"reload"**, then a new run, and `/replay` in the dock.

**"status"** and **"stop the loop"** work at any time.

## Checked by bond (protocol level, no browser, 0 USD)
- demo.sh starts the road page on :8400. run.sh starts the console on :8770 over the same workspace.
- The run is held until a page says `watching`. `tools/loop-drive/page_keeper.py` is a headless page (hello, watching, play).
  With it, the run steps, and the trace is written under `.metis/traces/<run>/` (seg-0, seg-200, truth.jsonl).
- The console's /commands and the stub pi, on the road workspace (loop-test s-6a97bfca step 2): trace list/open/tick, drop at k, /why, /status, /surprises, start/stop.
  The scripts are `tools/loop-drive/drive.py` and `drive_road.py`.

## Not done
- **Flows A and B on the live run.** The drive (`drive_road.py`) was written; it was stopped by the pause before it ran on the live trace.
- **Voice and the page's look** (step 4, the user's).
- **The one paid take**, capped at 0.25 USD.
