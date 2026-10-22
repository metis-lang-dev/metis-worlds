#!/usr/bin/env bash
# metis-worlds/minihack — the world's venv: NLE + MiniHack, pinned. ./setup.sh [--check]
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"; V="$HERE/.venv"
if [ "${1:-}" = --check ]; then "$V/bin/python" -c "import pkg_resources, minihack, nle; print('minihack', minihack.__version__, 'nle', nle.__version__)"; exit; fi
[ -x "$V/bin/python" ] || python3 -m venv "$V"
"$V/bin/pip" install -q --upgrade pip
"$V/bin/pip" install -q 'setuptools<81' 'nle==1.3.0' 'minihack==1.0.2' 'gymnasium>=1.0'
"$V/bin/python" -c "import pkg_resources, minihack, nle; print('minihack', minihack.__version__, 'nle', nle.__version__, 'ok')"
