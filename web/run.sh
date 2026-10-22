#!/usr/bin/env bash
# The world page's live stack (alf-demo step 3b, the L2 harness as console-nav's synth): metis-agent's
# py service serving the `world_ui` domain (web/ is the catalog: METIS_CATALOG) on Gemma E2B, local,
# and the page at http://ADDR/world.html?live=1 (web/ served, vendor/ the copies). Everything it
# writes goes to web/.metis/ (git-ignored).
#
#   METIS_AGENT=<metis-agent checkout> METISPY=<metispy checkout> METIS_LOOP=<metis-loop checkout> web/run.sh
#
# ADDR (default 127.0.0.1:8397), MODEL (default the checkout's go/models/gemma4 E2B Q4_K_M),
# PY (default the checkout's py/.venv python). The world's own frames (world/map, world/delta,
# world/hierarchy) are not served here: they are the world plugin's (opus's step 2); the page loads
# its map from ?map= (default the ALFWorld fixture) so a pick has things to name.
set -euo pipefail
HERE=$(cd "$(dirname "$0")" && pwd)
: "${METIS_AGENT:?the metis-agent checkout (its py/ is run)}"
: "${METISPY:?the metispy checkout}"
: "${METIS_LOOP:?the metis-loop checkout (its sdk/)}"
ADDR=${ADDR:-127.0.0.1:8397}
MODEL=${MODEL:-$METIS_AGENT/go/models/gemma4/gemma-4-E2B-it-Q4_K_M.gguf}
PY=${PY:-$METIS_AGENT/py/.venv/bin/python}
STATE=$HERE/.metis
mkdir -p "$STATE"
[ -f "$STATE/.gitignore" ] || echo '*' > "$STATE/.gitignore"
cat > "$STATE/config.world_ui.yaml" <<YAML
# written by web/run.sh
model: $MODEL
template: gemma4
stop_words: [stop, halt, freeze, quiet]
v3:
    prompt: [../go/grammar/v3-orchestrator.txt]
    catalog: [world_ui]
    loaded: [world_ui]
    n_ctx: 16384
    tick_ms: ${TICK_MS:-1000}
    journal: $STATE/journal.jsonl
domains:
    names: [world_ui]
    case: live
    seed: 1
    clocks: [{domain: world_ui, n: 1}]
    trace: true
    records: $STATE/records
    narrator_n_ctx: 8192
    seat_n_ctx: 8192
ws:
    addr: $ADDR
YAML
cd "$METIS_AGENT/py"
export METIS_CATALOG=$HERE
export PYTHONPATH=$METIS_AGENT/py:$METIS_LOOP/sdk:$METISPY${PYTHONPATH:+:$PYTHONPATH}
# (the page's copies are vendor/, not lib/: the service mounts /lib/ from an installed fsttm_web)
exec "$PY" -m metis_agent.service --config "$STATE/config.world_ui.yaml" --ui-dir "$HERE" \
  --lib-dir "$HERE/vendor" --addr "$ADDR" "$@"
