#!/usr/bin/env bash
# metis-worlds/alfworld — the world's venv: ALFWorld (text mode) pinned, its game data.
#   ./setup.sh            install the venv and download the text games into data/
#   ./setup.sh --check    say what is installed
# The planner dependency (fast-downward-textworld) builds with a bare `python` on PATH,
# which Ubuntu has not: the venv's python is shimmed in for the install.
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"; V="$HERE/.venv"
export ALFWORLD_DATA="${ALFWORLD_DATA:-$HERE/data}"
if [ "${1:-}" = --check ]; then "$V/bin/python" -c "import alfworld, textworld; print('alfworld', alfworld.__version__ if hasattr(alfworld,'__version__') else '?', 'textworld', textworld.__version__)"; ls "$ALFWORLD_DATA" 2>/dev/null | head; exit; fi
[ -x "$V/bin/python" ] || python3 -m venv "$V"
mkdir -p "$V/pybin"; ln -sfn "$V/bin/python" "$V/pybin/python"
PATH="$V/pybin:$PATH" "$V/bin/pip" install -q --upgrade pip
PATH="$V/pybin:$PATH" "$V/bin/pip" install -q 'alfworld[full]==0.4.2'
PATH="$V/pybin:$PATH" "$V/bin/pip" install -q 'metispy>=0.1.3'      # metis.host, metis.repl: the world's host and the experiments (metis-packages)
mkdir -p "$ALFWORLD_DATA"
"$V/bin/alfworld-download" --data-dir "$ALFWORLD_DATA" "$@"      # ~2.3 GB: the text games, the PDDL logic, a detector the text mode never loads
"$V/bin/python" -c "import alfworld, textworld; print('alfworld ok, data at', '$ALFWORLD_DATA')"
