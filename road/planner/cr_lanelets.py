#!/usr/bin/env python3
"""cr_lanelets.py — a CommonRoad scenario's lanelets, obstacles and planning problem as JSON, NO SUMO conversion
(planner-loop s-0dcc5ed1: the user's option 1, 2026-11-07: the lanelet adapter; road/world/cr_lanes.py builds the
semantic LaneMap from this file).

    road/.venv-planner/bin/python road/planner/cr_lanelets.py XML [OUT_JSON]     (default: lanes_for(XML))

commonroad-io only (the planner venv). The rows are cr_convert's own (lanelet_rows, sign_rows, light_rows,
intersection_rows, obstacle_rows, planning_rows: the same keys cr.json has), in CommonRoad coordinates (no net offset),
plus per lanelet its centre line and its speed limit (commonroad-io's TrafficSignInterpreter: the lowest MAX_SPEED on it,
None when unsigned). The Live's venv reads only this file."""
import hashlib
import json
import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROAD = HERE.parent
sys.path.insert(0, str(ROAD / "tools"))
import cr_convert  # noqa: E402  (its row functions import commonroad-io only; the SUMO converter only in _convert)

LANES_VERSION = 1
WS = Path(os.environ.get("PLANNER_WS", str(Path.home() / "repo" / "perotheia-packages")))
LANES = Path(os.environ.get("CR_LANES", str(WS / ".worlds" / "cr-lanes")))


def lanes_for(xml):
    """The JSON's path for XML: by its id under a directory keyed by the file's directory (ids repeat across sets)."""
    xml = Path(xml).resolve()
    sid = xml.name[:-len(".cr.xml")] if xml.name.endswith(".cr.xml") else xml.stem
    return LANES / hashlib.sha256(str(xml.parent).encode()).hexdigest()[:12] / (sid + ".json")


def export(xml, out=None):
    from commonroad.common.file_reader import CommonRoadFileReader
    from commonroad.scenario.traffic_sign_interpreter import TrafficSignInterpreter
    xml = Path(xml)
    sc, pps = CommonRoadFileReader(str(xml)).open(lanelet_assignment=True)
    net = sc.lanelet_network
    rows = cr_convert.lanelet_rows(net)
    try:
        tsi = TrafficSignInterpreter(sc.scenario_id.country_id, net)
    except Exception:
        tsi = None
    for r, la in zip(rows, net.lanelets):
        r["center"] = [[cr_convert._f(x), cr_convert._f(y)] for x, y in la.center_vertices]
        v = None
        if tsi is not None:
            try:
                v = tsi.speed_limit(frozenset([la.lanelet_id]))
            except Exception:
                v = None
        r["speed"] = float(v) if v is not None else None
    doc = {"version": LANES_VERSION, "kind": "lanes", "id": str(sc.scenario_id), "source": str(xml.resolve()),
           "sha256": cr_convert.sha256(xml), "dt": sc.dt, "lanelets": rows, "signs": cr_convert.sign_rows(net),
           "lights": cr_convert.light_rows(net), "intersections": cr_convert.intersection_rows(net),
           "obstacles": cr_convert.obstacle_rows(sc), "planning": cr_convert.planning_rows(pps)}
    out = Path(out) if out else lanes_for(xml)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(doc))
    return out


if __name__ == "__main__":
    a = sys.argv[1:]
    if not a:
        sys.exit(__doc__)
    print(export(a[0], a[1] if len(a) > 1 else None))
