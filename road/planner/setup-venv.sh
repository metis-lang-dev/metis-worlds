#!/usr/bin/env bash
# setup-venv.sh — the planner venv (planner-loop s-0dcc5ed1 step 2): Python 3.11 + the CommonRoad reactive planner (BSD) and its stack.
#
#   road/planner/setup-venv.sh          road/.venv-planner (git-ignored) at the pins of road/planner/requirements.txt
#
# Why its own venv: commonroad-reactive-planner 2025.1 requires Python <3.12; the host's python3 is 3.12, so uv downloads a 3.11
# interpreter (the user's word, 2026-11-07). uv itself is bootstrapped into ../.worlds/uv-tool (outside every repo) when not on PATH.
# Nothing of theirs is copied or put on sys.path: pip-installed only. The licenses: road/docs/planner-licenses.md.
# Idempotent: a venv that imports the stack at the pinned versions is kept.
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
ROAD="$(dirname "$HERE")"
VENV="${PLANNER_VENV:-$ROAD/.venv-planner}"
REQ="$HERE/requirements.txt"
TOOL="${UV_TOOL:-$(cd "$ROAD/../.." && pwd)/.worlds/uv-tool}"

UV="$(command -v uv || true)"
if [ -z "$UV" ]; then
  if [ ! -x "$TOOL/bin/uv" ]; then python3 -m venv "$TOOL" && "$TOOL/bin/pip" install -q uv==0.9.5; fi
  UV="$TOOL/bin/uv"
fi
check() { "$VENV/bin/python" - "$REQ" <<'PY' 2>/dev/null
import importlib.metadata as md, sys
want = dict(l.strip().split("==") for l in open(sys.argv[1]) if "==" in l)
bad = [n for n, v in want.items() if md.version(n) != v]
import commonroad_rp, commonroad_route_planner, commonroad_dc, commonroad_clcs, vehiclemodels, casadi
sys.exit(1 if bad else 0)
PY
}
if [ -x "$VENV/bin/python" ] && check; then echo "$VENV: at the pins"; exit 0; fi
"$UV" python install 3.11
"$UV" venv -q --allow-existing "$VENV" --python 3.11
"$UV" pip install -q --python "$VENV/bin/python" -r "$REQ"
check && echo "$VENV: installed at the pins ($("$VENV/bin/python" -V))"
