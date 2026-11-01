#!/usr/bin/env bash
# demo.sh — the road on SUMO on its own page, under metis-agent's service: the tree of road/domains (world/road_hier.py) drives, the page shows it.
# ADDR (default 127.0.0.1:8400), METIS_AGENT (default the sibling checkout: its py/.venv and models), SUMO_VENV (a venv with eclipse-sumo 1.18: sumo,
# netconvert, the tools; road/setup-sumo.sh makes it), CUDA_LIB (the libcudart the agent's llama was built with, where it is not on the path). One SUMO at a time.
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
WORLDS="$(dirname "$HERE")"
ADDR="${ADDR:-127.0.0.1:8400}"
AGENT="${METIS_AGENT:-$(cd "$WORLDS/.." && pwd)/metis-agent}"
ROOT="${ROOT:-$HERE/.metis/road}"
SUMO_VENV="${SUMO_VENV:-$(cd "$WORLDS/.." && pwd)/.worlds/road}"
CUDA_LIB="${CUDA_LIB:-$HOME/.local/cuda-12.9/lib64}"
[ -d "$CUDA_LIB" ] && export LD_LIBRARY_PATH="$CUDA_LIB${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
export PATH="$SUMO_VENV/bin:$PATH" SUMO_HOME="$("$SUMO_VENV/bin/python" -c 'import sumo; print(sumo.SUMO_HOME)')"
export PYTHONPATH="$WORLDS/libs/semantic-world:$HERE/world${PYTHONPATH:+:$PYTHONPATH}"
mkdir -p "$HERE/.metis"
"$AGENT/py/.venv/bin/python" "$HERE/world/road_hier.py" "$ROOT" --agent "$AGENT/py" --port "${ADDR##*:}"
export METIS_CATALOG="$HERE" METIS_ROAD_WORLD="$HERE/world" METIS_ROAD_RUN="$ROOT/run.json"
# the road FAMILY (road-family s-f62c0ed8): the units by name through METIS_HOME = metis-catalog domains/road (domains/catalog.pin); the sibling checkout by default
export METIS_HOME="${METIS_HOME:-$(cd "$WORLDS/.." && pwd)/metis-catalog/domains/road}"
[ -f "$METIS_HOME/responder_domain.llp" ] || { echo "no road family at $METIS_HOME: check out metis-catalog beside (road/domains/catalog.pin) or set METIS_HOME" >&2; exit 2; }
echo "the page: http://$ADDR/world.html"
cd "$AGENT/py"
exec "$AGENT/py/.venv/bin/python" -m metis_agent.service --config "$ROOT/.run/config.yaml" --ui-dir "$HERE/web" --lib-dir "$HERE/web/vendor" --addr "$ADDR"
