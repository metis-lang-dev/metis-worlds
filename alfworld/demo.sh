#!/usr/bin/env bash
# demo.sh — the exploitation demo (alf-demo, docs/DEMO.md): one ALFWorld game installed as the agent's
# hierarchy (the director, the task card, the specialists), metis-agent's service on Gemma E2B (local),
# and the world page at http://ADDR/world.html?live=1 — the map, the dialog band, the hierarchy pane,
# the journal. TEXT mode (`--tw`, the only mode until THOR's step 1): the map from the game's facts.
#
#   ALFWORLD_DATA=… alfworld/demo.sh [--tw] [--view] [GAME]     (default: the fixtures' kitchen, Tomato-Microwave-13)
#   alfworld/demo.sh --list                                      (the games it can load: one per line, "split/task  label")
#
#   GAME: a game's name ("Bowl-None-Fridge-6", "pick_and_place_simple-Bowl-None-Fridge-6", "train/…"), its task
#   directory or a trial directory. The page's top bar picks another game: the service stops, this script sets
#   that game up and starts it again, and the page reloads on it.
#
#   --view: the semantic map sees only what the robot sees (semantic-map step 3): it knows the places, a
#   thing once seen; "a tomato" is looked for place by place, the belief choosing where first.
#
#   ADDR (default 127.0.0.1:8398), METIS_AGENT (default the sibling checkout: its py/.venv and models; METIS_AGENT_DIR: its code, a worktree's),
#   ROOT (default alfworld/.metis/demo: the catalog the service runs on, rebuilt each start)
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
for a in "$@"; do
  case "$a" in
    --tw) ;;                                   # text mode: the only one until THOR (DEMO.md step 1)
    --view) VIEW=(--view) ;;
    --list) exec "$PY" "$HERE/experiments/demo.py" list ;;
    *) GAME="$a" ;;
  esac
done
GAME="$("$PY" "$HERE/experiments/demo.py" resolve "$GAME")"
mkdir -p "$(dirname "$ROOT")"
[ -f "$HERE/.metis/.gitignore" ] || { mkdir -p "$HERE/.metis"; echo '*' > "$HERE/.metis/.gitignore"; }
export METIS_CATALOG="$ROOT" METIS_ALF_PY="$PY"
for p in "$AGENT/py/.venv/bin/python" "$PY"; do      # metis_agent installed in both: the service's venv and the world's (setup.sh)
  "$p" -c "import metis_agent" 2>/dev/null || { echo "demo.sh: $p lacks metis_agent: $p -m pip install --no-deps -e $AGENT/py" >&2; exit 1; }
done
CAP=()
command -v systemd-run >/dev/null && CAP=(systemd-run --user --scope -q -p MemoryMax=6G)
NEXT="$ROOT.next.json"                         # the page's next game (the service's v3.game_request), read when it stops
rm -f "$NEXT"
while :; do
  (cd "$HERE" && "$PY" experiments/demo.py setup "$GAME" "$ROOT" --port "${ADDR##*:}" ${VIEW[@]+"${VIEW[@]}"})
  echo "the world page: http://$ADDR/world.html?live=1"
  rc=0
  (cd "${METIS_AGENT_DIR:-$AGENT}/py" && "${CAP[@]}" nice "$AGENT/py/.venv/bin/python" -m metis_agent.service \
    --config "$ROOT/.run/config.yaml" --ui-dir "$HERE/../web" --lib-dir "$HERE/../web/vendor" --addr "$ADDR") || rc=$?
  [ -f "$NEXT" ] || exit "$rc"                 # stopped by hand (^C): the demo ends
  GAME="$("$PY" "$HERE/experiments/demo.py" resolve "$("$PY" -c 'import json, sys; print(json.load(open(sys.argv[1]))["game"])' "$NEXT")")"
  rm -f "$NEXT"
  echo "demo.sh: the next game, $GAME"
done
