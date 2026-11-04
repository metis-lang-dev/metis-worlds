#!/usr/bin/env bash
# demo.sh — the exploitation demo (alf-demo, docs/DEMO.md): one ALFWorld game installed as the agent's
# hierarchy (the director, the task card, the specialists), metis-agent's service on Gemma E2B (local),
# and the world page at http://ADDR/world.html?live=1 — the map, the dialog band, the hierarchy pane,
# the journal. TEXT mode (`--tw`, the only mode until THOR's step 1): the map from the game's facts.
#
#   ALFWORLD_DATA=… alfworld/demo.sh [--tw] [--view] [--episode] [ROOM|GAME]   (default: the fixtures' kitchen 13)
#   alfworld/demo.sh --list [--episode]                          (the rooms it can load, or the games: "split/task  label")
#
#   A room (alf-tasks s-e9cc8fae): the game carries the room's state only; the person gives the tasks, one after
#   another, and the game's own task never ends the session. ROOM: a room's label ("kitchen 13"), or any game of it.
#   --episode: the game as one task (its own goal wins and ends it; the picker lists games). GAME: a game's name
#   ("Bowl-None-Fridge-6", "pick_and_place_simple-Bowl-None-Fridge-6", "train/…"), its task directory or a trial
#   directory. The page's top bar picks another room: the agent goes there and keeps running (rooms s-b51a2e80).
#
#   --view: the semantic map sees only what the robot sees (semantic-map step 3): it knows the places, a
#   thing once seen; "a tomato" is looked for place by place, the belief choosing where first.
#
#   The demo runs the workspace's BUNDLE in place (alf-bundle s-b53cc7ab step 2, the user's ruling 2026-11-03): the members'
#   programs are domains/hier/<spec>/ (METIS_CATALOG = alfworld), `make` rebuilds the image first when it is stale, and
#   ROOT holds the run's state only (the map, the commands log, a game.json per member). The run's trace goes to
#   alfworld/.metis/traces/<game>-<started>/ (config.yaml and run.json beside it), where TRACE and the pi loop find it;
#   an apply by the loop + make changes what the next load runs.
#   --plain: the plain hierarchy (no tick tree), installed into ROOT as before: a comparison run only.
#
#   ADDR (default 127.0.0.1:8398), METIS_AGENT (default the sibling checkout: its py/.venv and models; METIS_AGENT_DIR: its code, a worktree's),
#   ROOT (default alfworld/.metis/demo: the run's state, rebuilt each start; with --plain, the catalog the service runs on)
# Say "put the tomato in the microwave"; "put the tomato in the fridge" is the disengagement (the band asks).
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
PKGS="$HERE"
while [ "$PKGS" != / ] && [ ! -d "$PKGS/.worlds" ]; do PKGS="$(dirname "$PKGS")"; done
PY="${METIS_ALF_PY:-$PKGS/.worlds/alf/bin/python}"
export ALFWORLD_DATA="${ALFWORLD_DATA:-$PKGS/.worlds/alfworld-data}"
AGENT="${METIS_AGENT:-$PKGS/metis-agent}"
ADDR="${ADDR:-127.0.0.1:8398}"
ROOT="${ROOT:-$HERE/.metis/demo}"
GAME="train/pick_and_place_simple-Tomato-None-Microwave-13"
VIEW=()
ROOM=(--room)
LIST=""
PLAIN=()
for a in "$@"; do
  case "$a" in
    --tw) ;;                                   # text mode: the only one until THOR (DEMO.md step 1)
    --view) VIEW=(--view) ;;
    --episode) ROOM=() ;;
    --list) LIST=1 ;;
    --plain) PLAIN=(--plain) ;;
    *) GAME="$a" ;;
  esac
done
if [ -n "$LIST" ]; then
  exec "$PY" "$HERE/experiments/demo.py" list ${ROOM[@]+--rooms}
fi
GAME="$("$PY" "$HERE/experiments/demo.py" resolve "$GAME")"
mkdir -p "$(dirname "$ROOT")"
[ -f "$HERE/.metis/.gitignore" ] || { mkdir -p "$HERE/.metis"; echo '*' > "$HERE/.metis/.gitignore"; }
if [ ${#PLAIN[@]} -gt 0 ]; then
  echo "demo.sh: --plain: the plain hierarchy installed into $ROOT, a comparison run only (the bundle is the demo)" >&2
  export METIS_CATALOG="$ROOT" METIS_ALF_PY="$PY"
else                                           # the bundle in place: its image current first (make: the plain bases, metisc build)
  make -s -C "$HERE/domains/hier" -q PYTHON="$PY" 2>/dev/null || make -s -C "$HERE/domains/hier" PYTHON="$PY" >&2
  export METIS_CATALOG="$HERE" METIS_ALF_RUN="$ROOT" METIS_ALF_PY="$PY"
fi
for p in "$AGENT/py/.venv/bin/python" "$PY"; do      # metis_agent installed in both: the service's venv and the world's (setup.sh)
  "$p" -c "import metis_agent" 2>/dev/null || { echo "demo.sh: $p lacks metis_agent: $p -m pip install --no-deps -e $AGENT/py" >&2; exit 1; }
done
CAP=()
command -v systemd-run >/dev/null && CAP=(systemd-run --user --scope -q -p MemoryMax=6G)
(cd "$HERE" && "$PY" experiments/demo.py setup "$GAME" "$ROOT" --port "${ADDR##*:}" ${VIEW[@]+"${VIEW[@]}"} ${ROOM[@]+"${ROOM[@]}"} ${PLAIN[@]+"${PLAIN[@]}"})
echo "the world page: http://$ADDR/world.html?live=1"
cd "${METIS_AGENT_DIR:-$AGENT}/py"
exec "${CAP[@]}" nice "$AGENT/py/.venv/bin/python" -m metis_agent.service \
  --config "$ROOT/.run/config.yaml" --ui-dir "$HERE/../web" --lib-dir "$HERE/../web/vendor" --addr "$ADDR"
