#!/usr/bin/env bash
# demo.sh — the real game on its own page (web/, experiments/nh_demo.py): NetHack 3.6.6 with the tile hints (nethack/build.sh),
# the map, the talk, the world card, the journal and the dialog. ADDR (default 127.0.0.1:8399). No agent yet: the
# chat and the keyboard are the game's commands, until the agentic loop makes the NetHack domain.
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
[ -x "$HERE/.nethack/install/games/nethack" ] || "$HERE/nethack/build.sh"
exec "$HERE/.venv/bin/python" "$HERE/experiments/nh_demo.py" --addr "${ADDR:-127.0.0.1:8399}"
