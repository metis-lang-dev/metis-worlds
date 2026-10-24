#!/usr/bin/env bash
# demo.sh — the exploitation demo (alf-demo, docs/DEMO.md): one ALFWorld game installed as the agent's
# hierarchy (the director, the task card, the specialists), metis-agent's service on Gemma E2B (local),
# and the world page at http://ADDR/world.html?live=1 — the map, the dialog band, the hierarchy pane,
# the journal. TEXT mode (`--tw`, the only mode until THOR's step 1): the map from the game's facts.
#
#   ALFWORLD_DATA=… alfworld/demo.sh [--tw] [--view] [GAME_DIR]     (default: the fixtures' kitchen, Tomato-Microwave-13)
#
#   --view: the semantic map sees only what the robot sees (semantic-map step 3): it knows the places, a
#   thing once seen; "a tomato" is looked for place by place, the belief choosing where first.
#
#   ADDR (default 127.0.0.1:8398), METIS_AGENT (default the sibling checkout: its py/.venv and models),
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
GAME=""
VIEW=()
for a in "$@"; do
  case "$a" in
    --tw) ;;                                   # text mode: the only one until THOR (DEMO.md step 1)
    --view) VIEW=(--view) ;;
    *) GAME="$a" ;;
  esac
done
if [ -z "$GAME" ]; then
  K="$ALFWORLD_DATA/json_2.1.1/train/pick_and_place_simple-Tomato-None-Microwave-13"
  GAME="$K/$(ls "$K" | head -1)"
fi
mkdir -p "$(dirname "$ROOT")"
[ -f "$HERE/.metis/.gitignore" ] || { mkdir -p "$HERE/.metis"; echo '*' > "$HERE/.metis/.gitignore"; }
cd "$HERE"
"$PY" experiments/demo.py setup "$GAME" "$ROOT" --port "${ADDR##*:}" ${VIEW[@]+"${VIEW[@]}"}
export METIS_CATALOG="$ROOT" METIS_ALF_PY="$PY"
export PYTHONPATH="${METIS_AGENT_DIR:-$AGENT}/py${PYTHONPATH:+:$PYTHONPATH}"
echo "the world page: http://$ADDR/world.html?live=1"
cd "${METIS_AGENT_DIR:-$AGENT}/py"
CAP=()
command -v systemd-run >/dev/null && CAP=(systemd-run --user --scope -q -p MemoryMax=6G)
exec "${CAP[@]}" nice "$AGENT/py/.venv/bin/python" -m metis_agent.service --config "$ROOT/.run/config.yaml" \
  --ui-dir "$HERE/../web" --lib-dir "$HERE/../web/vendor" --addr "$ADDR"
