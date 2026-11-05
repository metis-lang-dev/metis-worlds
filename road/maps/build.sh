#!/usr/bin/env bash
# road/maps/build.sh [TOWN...] — CARLA's towns as SUMO nets: netconvert over the OpenDRIVE files of an installed CARLA (CARLA_ROOT, default /bigdata/simulators/carla, CARLA 0.9.16 on taycann). The small
# towns' nets are tracked here; the three big ones (Town11, 12, 13: 18 to 25 MB) are not, this script makes them. With TOWN names (Town03 …) only those.
# After netconvert, lane_speeds.py gives the parking and bidirectional lanes their edge's driving speed (the OpenDRIVE states none for them, and
# netconvert's default 1.39 m/s is no limit of CARLA's; road-scenarios s-e23be780, 2026-11-05).
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"; C="${CARLA_ROOT:-/bigdata/simulators/carla}/CarlaUE4/Content/Carla/Maps"
for f in "$C"/OpenDrive/Town0[1-7].xodr "$C"/OpenDrive/Town10HD.xodr "$C"/Town1[1235]/OpenDrive/*.xodr; do
  t="$(basename "$f" .xodr)"
  if [ "$#" -gt 0 ] && [[ " $* " != *" $t "* ]]; then continue; fi
  netconvert --opendrive "$f" -o "$HERE/$t.net.xml" --no-warnings
  python3 "$HERE/lane_speeds.py" "$HERE/$t.net.xml"
done
