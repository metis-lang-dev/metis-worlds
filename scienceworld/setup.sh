#!/usr/bin/env bash
# metis-worlds/scienceworld — the world's venv: ScienceWorld pinned (its jar runs on the system Java).
#   ./setup.sh            install the venv (.venv/; or use ../../.worlds/sw: the hosts walk up to it)
#   ./setup.sh --check    say what is installed
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"; V="${SW_VENV:-$HERE/.venv}"
command -v java >/dev/null || { echo "setup.sh: no java on PATH (ScienceWorld's simulator is a jar; Java 8+)" >&2; exit 1; }
if [ "${1:-}" = --check ]; then java -version 2>&1 | head -1; "$V/bin/python" -c "import scienceworld; print('scienceworld', scienceworld.__version__ if hasattr(scienceworld, '__version__') else 'ok')"; exit; fi
[ -x "$V/bin/python" ] || python3 -m venv "$V"
"$V/bin/pip" install -q --upgrade pip
"$V/bin/pip" install -q 'scienceworld==1.2.3' 'metispy>=0.1.3'
"$V/bin/pip" install -q -e "$HERE/../libs/semantic-world"   # semantic_world: the library every world's venv has (libs/)
"$V/bin/pip" install -q -e "$HERE"      # the world's own modules (world/: pyproject.toml), as the policy driver imports them
"$V/bin/python" -c "from scienceworld import ScienceWorldEnv; e = ScienceWorldEnv('', envStepLimit=10); print('scienceworld ok,', len(e.get_task_names()), 'task types'); e.close()"
