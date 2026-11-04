#!/usr/bin/env bash
# road/maps/build.sh — CARLA's towns as SUMO nets: netconvert over the OpenDRIVE files of an installed CARLA (CARLA_ROOT, default /bigdata/simulators/carla, CARLA 0.9.16 on taycann). The small
# towns' nets are tracked here; the three big ones (Town11, 12, 13: 18 to 25 MB) are not, this script makes them.
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"; C="${CARLA_ROOT:-/bigdata/simulators/carla}/CarlaUE4/Content/Carla/Maps"
for f in "$C"/OpenDrive/Town0[1-7].xodr "$C"/OpenDrive/Town10HD.xodr "$C"/Town1[1235]/OpenDrive/*.xodr; do
  netconvert --opendrive "$f" -o "$HERE/$(basename "$f" .xodr).net.xml" --no-warnings
done
