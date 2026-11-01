#!/usr/bin/env bash
# setup-sumo.sh — the venv road/demo.sh and road_tree read (SUMO_VENV, default ../.worlds/road): sumo, netconvert and the tools at 1.18, and `import sumo` for SUMO_HOME.
# With SUMO 1.18 already on the host (apt: sumo, sumo-tools) nothing is downloaded: the venv sees the system's traci and sumolib, a small `sumo` module names SUMO_HOME, and
# its bin links the system's binaries. Without it, it installs eclipse-sumo, traci and sumolib 1.18.0 from PyPI; --wheel asks for that anyway.
#   road/setup-sumo.sh [--wheel] [VENV]
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
WHEEL=""
[ "${1:-}" = "--wheel" ] && { WHEEL=1; shift; }
VENV="${1:-$(cd "$HERE/../.." && pwd)/.worlds/road}"
HOME_SYS="${SUMO_HOME:-/usr/share/sumo}"
have_system() { command -v sumo >/dev/null && sumo --version 2>/dev/null | head -1 | grep -q 'Version 1\.18\.' && [ -d "$HOME_SYS/tools/traci" ]; }
if [ -z "$WHEEL" ] && have_system; then
  python3 -m venv --system-site-packages "$VENV"
  SITE="$("$VENV/bin/python" -c 'import site; print(site.getsitepackages()[0])')"
  mkdir -p "$SITE/sumo"
  printf 'SUMO_HOME = %s\n' "'$HOME_SYS'" > "$SITE/sumo/__init__.py"
  for b in sumo netconvert duarouter netedit od2trips polyconvert; do
    command -v "$b" >/dev/null && ln -sf "$(command -v "$b")" "$VENV/bin/$b"
  done
  echo "system SUMO: $(sumo --version | head -1)"
else
  python3 -m venv "$VENV"
  "$VENV/bin/pip" install -q eclipse-sumo==1.18.0 traci==1.18.0 sumolib==1.18.0
  echo "wheel SUMO: $("$VENV/bin/sumo" --version | head -1)"
fi
"$VENV/bin/python" -c 'import sumo, os; assert os.path.isdir(os.path.join(sumo.SUMO_HOME, "tools")), sumo.SUMO_HOME; print("SUMO_HOME", sumo.SUMO_HOME)'
"$VENV/bin/python" -c 'import traci, sumolib; print("traci", traci.__file__)'
