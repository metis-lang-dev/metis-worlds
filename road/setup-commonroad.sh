#!/usr/bin/env bash
# setup-commonroad.sh — CommonRoad scenarios FROM A CHECKOUT (commonroad-world s-9b7591fb, step 1; road/docs/commonroad.md).
#
#   road/setup-commonroad.sh            the two repositories at their pins into $COMMONROAD_ROOT, the conversion venv, the counts
#
# COMMONROAD_ROOT (default /bigdata/datasets/commonroad): outside every repo, as CARLA's big towns. Nothing of CommonRoad's is
# committed here: the checkouts are there, the conversion cache is road/maps/cr/ (git-ignored), the venv road/.venv-cr
# (git-ignored). The terms (BSD 3-Clause, TUM CPS) and the pins: road/docs/commonroad.md.
# The conversion venv: commonroad-io + commonroad-sumo (its cr2sumo map converter; sumocr 2024.1 has none) at their pins, its own (their pins clash with the Live's venv: numpy, Pillow,
# libsumo); it converts a scenario into the cache and the Live reads only the cache's files (cr_world.py).
# Idempotent: a checkout at its pin is kept; a venv that imports the pair is kept.
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
ROOT="${COMMONROAD_ROOT:-/bigdata/datasets/commonroad}"
PY="${PYTHON:-python3}"
VENV="$HERE/.venv-cr"

# the pins (road/docs/commonroad.md): commits, for the scenario repository has no tag after Release_2018a
SCEN_URL=https://gitlab.lrz.de/tum-cps/commonroad-scenarios.git
SCEN_PIN=2416dc27faf3ee36b6799f42712da72a34a2c8fd            # 2020a_scenarios, 2021-11-26
INTER_URL=https://gitlab.lrz.de/tum-cps/commonroad-interactive-scenarios.git
INTER_PIN=749e342013cc069980039fa91ba587f62993aaaf           # master, 2026-09-03
PIP_PINS=(${COMMONROAD_PIP_PINS:-commonroad-io==2024.3 commonroad-sumo==2025.1.4 rtree==1.4.1})

checkout() {   # DIR URL PIN: DIR at PIN, fetched alone (depth 1), never a branch's moving head
  local dir="$1" url="$2" pin="$3"
  if [ -d "$dir/.git" ] && [ "$(git -C "$dir" rev-parse HEAD 2>/dev/null)" = "$pin" ]; then
    echo "$dir: at $pin"; return
  fi
  mkdir -p "$dir"
  git -C "$dir" init -q
  git -C "$dir" remote remove origin 2>/dev/null || true
  git -C "$dir" remote add origin "$url"
  git -C "$dir" fetch -q --depth 1 origin "$pin"
  git -C "$dir" -c advice.detachedHead=false checkout -q FETCH_HEAD
  echo "$dir: checked out at $pin"
}

mkdir -p "$ROOT"
checkout "$ROOT/scenarios" "$SCEN_URL" "$SCEN_PIN"
checkout "$ROOT/interactive" "$INTER_URL" "$INTER_PIN"

if ! { [ -x "$VENV/bin/python" ] && "$VENV/bin/python" -c "import commonroad, commonroad_sumo, rtree" 2>/dev/null; }; then
  "$PY" -m venv "$VENV"
  "$VENV/bin/pip" install -q --upgrade pip
  "$VENV/bin/pip" install -q "${PIP_PINS[@]}"
fi
"$VENV/bin/python" - "$ROOT" <<'EOF'
import collections, importlib.metadata as md, pathlib, sys
root = pathlib.Path(sys.argv[1])
print("venv:", ", ".join("%s %s" % (p, md.version(p)) for p in ("commonroad-io", "commonroad-sumo")))
for part in ("scenarios", "interactive"):
    files = [p for p in (root / part).rglob("*.xml") if not p.name.endswith((".net.xml", ".rou.xml", ".add.xml", ".sumocfg", ".cr.xml"))
             and "__" not in p.stem]
    by = collections.Counter(p.stem.split("_")[0] for p in files)
    print("%s: %d scenario files; by country: %s" % (part, len(files), ", ".join("%s %d" % kv for kv in by.most_common())))
EOF
"$VENV/bin/python" "$HERE/tools/cr_convert.py" --index --root "$ROOT"     # the page's picker reads road/maps/cr/index.json
