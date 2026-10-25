#!/bin/sh
# the test nets, from their plain XML (SUMO netconvert 1.18; SUMO_HOME=/usr/share/sumo): a four-way priority
# junction (a 2-lane major road W-E at 13.89 m/s, a 1-lane minor road S-N at 8.33 m/s), and the same under a light
set -e
cd "$(dirname "$0")"
netconvert --node-files cross.nod.xml --edge-files cross.edg.xml -o cross.net.xml --no-turnarounds --no-warnings
netconvert --node-files cross_tls.nod.xml --edge-files cross.edg.xml -o cross_tls.net.xml --no-turnarounds --no-warnings
