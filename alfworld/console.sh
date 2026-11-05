#!/usr/bin/env bash
# console.sh — the loop console beside the demo (loop-ui s-bb07923c step 2.5): metis-loop's gateway over THIS
# world's workspace (alfworld/, the bundle in place, as demo.sh runs it), so a tester assesses and interrogates the
# world the demo plays: the world page's LOOP dock frames the console's CHAT (?loop=URL), the two terminals'
# flow through a page (WORKSPACE.md §10: the REPL's verbs in its REPL pane, pi's commands and words in its CHAT).
#
#   alfworld/console.sh            the console on LOOP_ADDR (default 127.0.0.1:8397), in the foreground
#   then: http://<demo ADDR>/world.html?live=1&loop=http://127.0.0.1:8397/
#
# The pi loop it starts takes its model from the dot file's [llm] loop (the REPL's `llm loop ollama qwen3:4b`; a
# local model is 0 USD; WORKSPACE.md §10 says what one needs of the Ollama server). Its /rebuild runs the bundle's
# make with demo.sh's python and the sibling metisc, so an /apply + /rebuild changes what the next load runs.
#   LOOP_ADDR (default 127.0.0.1:8397), METIS_LOOP (default the sibling metis-loop checkout), VENV (default the
#   workspace's .venv: metispy, metis-loop[console]), METIS_AGENT_WS (the band's AGENT field; default off: the world
#   page shows the agent itself)
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
PKGS="$HERE"
while [ "$PKGS" != / ] && [ ! -d "$PKGS/.worlds" ]; do PKGS="$(dirname "$PKGS")"; done
[ -d "$PKGS/.worlds" ] || PKGS="$(cd "$HERE/../.." && pwd)"
LOOP="${METIS_LOOP:-$PKGS/metis-loop}"
VENV="${VENV:-$PKGS/.venv}"
ADDR="${LOOP_ADDR:-127.0.0.1:8397}"
[ -f "$LOOP/loop/cli.py" ] || { echo "console.sh: no metis-loop at $LOOP (METIS_LOOP)" >&2; exit 1; }
[ -x "$VENV/bin/python" ] || { echo "console.sh: no python at $VENV/bin/python (VENV: metispy and metis-loop[console])" >&2; exit 1; }
# the bundle's make (the console's /rebuild, pi's bundle_build) as demo.sh runs it: the world's python, the sibling metisc
export PYTHON="${PYTHON:-${METIS_ALF_PY:-$PKGS/.worlds/alf/bin/python}}"
[ -n "${METISC:-}" ] || [ ! -x "$PKGS/metis-lang/src/metisc" ] || export METISC="$PKGS/metis-lang/src/metisc"
make -s -C "$HERE/domains/hier" -q PYTHON="$PYTHON" 2>/dev/null || make -s -C "$HERE/domains/hier" PYTHON="$PYTHON" >&2
export METIS_CATALOG="$HERE"
cd "$HERE"
echo "the loop console over $HERE: http://$ADDR/"
echo "beside the world page: http://${ADDR%:*}:8398/world.html?live=1&loop=http://$ADDR/   (demo.sh's ADDR, if not 8398)"
CAP=()
command -v systemd-run >/dev/null && CAP=(systemd-run --user --scope -q -p MemoryMax=6G)
exec "${CAP[@]}" nice env PYTHONPATH="$LOOP${PYTHONPATH:+:$PYTHONPATH}" "$VENV/bin/python" -m loop.cli \
  --port "${ADDR##*:}" --bind "${ADDR%:*}" --mode personal ${METIS_AGENT_WS:+--metis-agent "$METIS_AGENT_WS"}
