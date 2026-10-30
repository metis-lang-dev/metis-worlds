#!/usr/bin/env bash
# metis-worlds/minihack — the world's venv: NLE + MiniHack, pinned. ./setup.sh [--check]
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"; V="$HERE/.venv"
if [ "${1:-}" = --check ]; then "$V/bin/python" -c "import pkg_resources, minihack, nle; print('minihack', minihack.__version__, 'nle', nle.__version__)"; exit; fi
[ -x "$V/bin/python" ] || python3 -m venv "$V"
"$V/bin/pip" install -q --upgrade pip
"$V/bin/pip" install -q 'setuptools<81' 'nle==1.3.0' 'minihack==1.0.2' 'gymnasium>=1.0'
"$V/bin/pip" install -q 'metispy>=0.1.3'      # metis.host: the world's host (metis-packages)
"$V/bin/pip" install -q -e "$HERE/../libs/semantic-world"   # semantic_world: the map, its belief, the ports (libs/)
"$V/bin/pip" install -q 'pyte==0.8.2'   # the real game's tty (world/nh_tty.py)
AGENT="${METIS_AGENT:-$(cd "$HERE/../.." && pwd)/metis-agent}"   # metis_agent (its py/): the experiments that drive the service, as alfworld/setup.sh
if [ -f "$AGENT/py/pyproject.toml" ]; then "$V/bin/pip" install -q --no-deps -e "$AGENT/py"
else echo "setup.sh: no metis-agent at $AGENT (METIS_AGENT): pip install --no-deps -e <metis-agent>/py into $V" >&2; fi
[ -x "$HERE/.nethack/install/games/nethack" ] || "$HERE/nethack/build.sh"   # the real game with the tile hints, under .nethack/
"$V/bin/python" -c "import pkg_resources, minihack, nle; print('minihack', minihack.__version__, 'nle', nle.__version__, 'ok')"
