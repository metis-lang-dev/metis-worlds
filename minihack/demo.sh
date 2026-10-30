#!/usr/bin/env bash
# demo.sh — the real game with the agent on its own page: NetHack 3.6.6 with the tile hints (nethack/build.sh) under
# metis-agent's service, the hierarchy's rules (world/nh_hier.py), Gemma E2B reading the person's words; the map, the talk,
# the hierarchy, the world card, the journal and the dialog. ADDR (default 127.0.0.1:8399), METIS_AGENT (default the sibling
# checkout: its py/.venv and models), CUDA_LIB (the libcudart the agent's llama was built with, where it is not on the path).
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
ADDR="${ADDR:-127.0.0.1:8399}"
AGENT="${METIS_AGENT:-$(cd "$HERE/../.." && pwd)/metis-agent}"
ROOT="${ROOT:-$HERE/.metis/nh}"
[ -x "$HERE/.nethack/install/games/nethack" ] || "$HERE/nethack/build.sh"
CUDA_LIB="${CUDA_LIB:-$HOME/.local/cuda-12.9/lib64}"
[ -d "$CUDA_LIB" ] && export LD_LIBRARY_PATH="$CUDA_LIB${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
mkdir -p "$HERE/.metis"
"$HERE/.venv/bin/python" "$HERE/world/nh_hier.py" "$ROOT" --port "${ADDR##*:}"
export METIS_CATALOG="$ROOT" METIS_MH_PY="$HERE/.venv/bin/python"
echo "the page: http://$ADDR/world.html"
cd "$AGENT/py"
exec "$AGENT/py/.venv/bin/python" -m metis_agent.service --config "$ROOT/.run/config.yaml" --ui-dir "$HERE/web" --lib-dir "$HERE/web/vendor" --addr "$ADDR"
