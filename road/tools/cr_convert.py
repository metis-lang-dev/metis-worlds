"""cr_convert.py — a CommonRoad scenario into the road world's cache (commonroad-world s-9b7591fb step 1; road/docs/commonroad.md).

Runs in the CONVERSION venv (road/.venv-cr, made by road/setup-commonroad.sh: commonroad-io + commonroad-sumo at their pins),
never in the Live's: the Live reads only what this writes.

    road/.venv-cr/bin/python road/tools/cr_convert.py ID|PATH [--root COMMONROAD_ROOT] [--cache DIR] [--force]
    road/.venv-cr/bin/python road/tools/cr_convert.py --index [--root …] [--cache …]

ID: a scenario id (ZAM_Tjunction-1_100_T-1), found under $COMMONROAD_ROOT (default /bigdata/datasets/commonroad): a recorded
scenario's file (scenarios/scenarios/recorded/**/ID.xml) or an interactive scenario's folder (…/interactive/**/ID/ID.cr.xml).
Writes CACHE/ID/ (CACHE default ../.worlds/cr-cache, outside every repo):
- ID.net.xml, ID.sumo.cfg: commonroad-sumo's cr2sumo map converter over the lanelet network, through the system's netconvert
  (the speed limits the scenario's own: overwrite_speed_limit None);
- cr.json (CR_JSON_VERSION): the interface the Live reads, CommonRoad's facts only, in the scenario's frame (the net's
  netOffset is written too: 0,0 when netconvert kept the frame) — see road/docs/commonroad.md for the fields.
Kept while the scenario file's sha256 and CR_JSON_VERSION match (--force converts again). Prints the cache dir.
--index: CACHE/index.json, a row per scenario of the checkout (id, set, path, country, map, tags, obstacles, duration,
interactive), for the page's picker (step 3) and the counts."""
import argparse
import hashlib
import json
import math
import os
import sys
from pathlib import Path

CR_JSON_VERSION = 3
ROAD = Path(__file__).resolve().parents[1]
ROOT = Path(os.environ.get("COMMONROAD_ROOT", "/bigdata/datasets/commonroad"))
# outside road/ (the workspace's .worlds/cr-cache): the Live walks its catalog root, road/, about 10 times a tick, and a cache of
# the whole catalog under it made a tick 1.6 s (cr-harvest s-f4e297da)
CACHE = Path(os.environ.get("COMMONROAD_CACHE", str(ROAD.parents[1] / ".worlds" / "cr-cache")))
SKIP = (".net.xml", ".rou.xml", ".add.xml", ".cr.xml", ".sumo.cfg", ".nod.xml", ".edg.xml", ".con.xml", ".tll.xml", ".typ.xml")


def find(sid, root=ROOT):
    """ID → its file in the checkout (a recorded scenario's ID.xml, else an interactive one's ID/ID.cr.xml), or a path as given."""
    p = Path(sid)
    if p.suffix == ".xml" and p.is_file():
        return p
    base = root / "scenarios" / "scenarios"
    for f in (base / "recorded").rglob(sid + ".xml"):
        return f
    for f in root.rglob(sid + ".cr.xml"):
        return f
    raise SystemExit("cr_convert: no scenario %s under %s (road/setup-commonroad.sh makes the checkout)" % (sid, root))


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def _f(x):
    return None if x is None else round(float(x), 4)


def _interval(v):
    """A CommonRoad value or Interval → [lo, hi] (a value: [v, v]); None when absent."""
    if v is None:
        return None
    if hasattr(v, "start") and hasattr(v, "end"):
        return [_f(v.start), _f(v.end)]
    return [_f(v), _f(v)]


def polygons(shape):
    """A CommonRoad shape → its polygons' vertices ([[x, y], …] each): a rectangle's corners, a circle as 24 points, a group's
    every member's."""
    from commonroad.geometry.shape import Circle, Polygon, Rectangle, ShapeGroup
    if shape is None:
        return []
    if isinstance(shape, ShapeGroup):
        return [p for s in shape.shapes for p in polygons(s)]
    if isinstance(shape, Circle):
        cx, cy = shape.center
        return [[[_f(cx + shape.radius * math.cos(2 * math.pi * k / 24)), _f(cy + shape.radius * math.sin(2 * math.pi * k / 24))] for k in range(24)]]
    if isinstance(shape, (Rectangle, Polygon)):
        return [[[_f(x), _f(y)] for x, y in shape.vertices]]
    return []


def state(s):
    """A CommonRoad state → {k, x, y, theta, v} (k its time step)."""
    pos = getattr(s, "position", None)
    xy = [_f(pos[0]), _f(pos[1])] if pos is not None and hasattr(pos, "__len__") and len(pos) == 2 else [None, None]
    return {"k": int(s.time_step) if not hasattr(s.time_step, "start") else int(s.time_step.start), "x": xy[0], "y": xy[1],
            "theta": _f(getattr(s, "orientation", None)), "v": _f(getattr(s, "velocity", None))}


def lanelet_rows(net):
    out = []
    for la in net.lanelets:
        out.append({"id": la.lanelet_id, "types": sorted(t.value for t in la.lanelet_type),
                    "left": [[_f(x), _f(y)] for x, y in la.left_vertices], "right": [[_f(x), _f(y)] for x, y in la.right_vertices],
                    "successors": list(la.successor), "predecessors": list(la.predecessor),
                    "adj_left": la.adj_left, "adj_left_same": la.adj_left_same_direction,
                    "adj_right": la.adj_right, "adj_right_same": la.adj_right_same_direction,
                    "signs": sorted(la.traffic_signs), "lights": sorted(la.traffic_lights),
                    "stop_line": ([[_f(x), _f(y)] for x, y in (la.stop_line.start, la.stop_line.end)] if la.stop_line is not None
                                  and la.stop_line.start is not None else None)})
    return out


def sign_rows(net):
    return [{"id": ts.traffic_sign_id, "position": [_f(ts.position[0]), _f(ts.position[1])] if ts.position is not None else None,
             "elements": [{"id": e.traffic_sign_element_id.name, "values": list(e.additional_values)} for e in ts.traffic_sign_elements]}
            for ts in net.traffic_signs]


def light_rows(net):
    out = []
    for tl in net.traffic_lights:
        cyc = getattr(tl, "traffic_light_cycle", None)
        els = getattr(cyc, "cycle_elements", None) or []
        out.append({"id": tl.traffic_light_id, "position": [_f(tl.position[0]), _f(tl.position[1])] if tl.position is not None else None,
                    "offset": int(getattr(cyc, "time_offset", 0) or 0),
                    "cycle": [{"state": e.state.value, "steps": int(e.duration)} for e in els]})
    return out


def intersection_rows(net):
    return [{"id": i.intersection_id,
             "incomings": [{"id": g.incoming_id, "lanelets": sorted(g.incoming_lanelets), "left": sorted(g.successors_left),
                            "straight": sorted(g.successors_straight), "right": sorted(g.successors_right),
                            "left_of": getattr(g, "left_of", None)} for g in i.incomings]}
            for i in net.intersections]


def obstacle_rows(sc):
    rows = []
    for o in list(sc.dynamic_obstacles) + list(sc.static_obstacles):
        sh = o.obstacle_shape
        length, width = (getattr(sh, "length", None), getattr(sh, "width", None))
        if length is None and hasattr(sh, "radius"):
            length = width = 2 * sh.radius
        traj = [state(o.initial_state)]
        pred = getattr(o, "prediction", None)
        if pred is not None and hasattr(pred, "trajectory"):
            traj += [state(s) for s in pred.trajectory.state_list]
        rows.append({"id": o.obstacle_id, "type": o.obstacle_type.value, "role": o.obstacle_role.value,
                     "length": _f(length), "width": _f(width), "trajectory": traj})
    return rows


def planning_rows(pps):
    out = []
    for pid, pp in sorted(pps.planning_problem_dict.items()):
        goals = []
        for k, st in enumerate(pp.goal.state_list):
            pos = getattr(st, "position", None)
            goals.append({"polygons": polygons(pos), "lanelets": sorted((pp.goal.lanelets_of_goal_position or {}).get(k, [])),
                          "time": _interval(getattr(st, "time_step", None)), "velocity": _interval(getattr(st, "velocity", None)),
                          "orientation": _interval(getattr(st, "orientation", None))})
        out.append({"id": pid, "initial": state(pp.initial_state), "goals": goals})
    return out


def net_edges(net_xml):
    """The net's edge ids: the converter's edge map names some that netconvert merged away (a junction's cluster)."""
    import xml.etree.ElementTree as ET
    return {el.get("id") for _, el in ET.iterparse(net_xml, events=("start",)) if el.tag == "edge" and el.get("function") != "internal"}


RIGHT_OF_WAY_SIGNS = ("YIELD", "STOP", "STOP_4_WAY", "PRIORITY", "RIGHT_OF_WAY", "PRIORITY_OVER_ONCOMING", "PRIORITY_OPPOSITE_DIRECTION")


def unsigned_junctions(net_xml, doc):
    """The SUMO junctions of the scenario's own intersections whose incoming lanelets carry no right-of-way sign (yield, stop,
    priority, right of way) and no light: the scenario states no priority there, so the net must not invent one (the
    architect's ruling, commonroad-world step 2 (4)). → {junction id: [its intersection ids]}; only `priority` junctions."""
    import xml.etree.ElementTree as ET
    to_node, jtype = {}, {}
    for _, el in ET.iterparse(net_xml, events=("start",)):
        if el.tag == "edge" and el.get("function") != "internal":
            to_node[el.get("id")] = el.get("to")
        elif el.tag == "junction":
            jtype[el.get("id")] = el.get("type")
    edge_of = {la: e for e, las in doc["edges"].items() for la in las}
    signs = {s["id"]: {x["id"] for x in s["elements"]} for s in doc["signs"]}
    lanelets = {la["id"]: la for la in doc["lanelets"]}
    out = {}
    for inter in doc["intersections"]:
        incoming = [l for g in inter["incomings"] for l in g["lanelets"]]
        if any(lanelets[l]["lights"] for l in incoming if l in lanelets):
            continue
        if any(signs.get(s, set()) & set(RIGHT_OF_WAY_SIGNS) for l in incoming if l in lanelets for s in lanelets[l]["signs"]):
            continue
        nodes = {to_node.get(str(edge_of.get(l))) for l in incoming} - {None}
        for n in nodes:
            if jtype.get(n) == "priority":
                out.setdefault(n, []).append(inter["id"])
    return out


def right_before_left(out_dir, net, doc):
    """Patch the unsigned junctions to right_before_left in the cached net (netconvert -s NET -n PATCH, the frame kept)."""
    import subprocess
    net_xml = str(out_dir / net)
    js = unsigned_junctions(net_xml, doc)
    if not js:
        return {}
    patch = out_dir / "rbl.nod.xml"
    patch.write_text("<nodes>\n%s</nodes>\n" % "".join('  <node id="%s" type="right_before_left"/>\n' % j for j in sorted(js)))
    tmp = out_dir / ("rbl." + net)
    subprocess.run(["netconvert", "-s", net_xml, "-n", str(patch), "-o", str(tmp), "--no-warnings"], check=True, capture_output=True)
    os.replace(tmp, net_xml)
    patch.unlink()
    return js


def net_offset(net_xml):
    import xml.etree.ElementTree as ET
    for _, el in ET.iterparse(net_xml, events=("start",)):
        if el.tag == "location":
            return [float(v) for v in el.get("netOffset", "0,0").split(",")]
    return [0.0, 0.0]


def produced_net(out, sid):
    """The net the map converter wrote: cr2sumo names it after the scenario's benchmark id, which for an interactive scenario
    lacks the trailing -1 (ZAM_Tjunction-1_374_I-1.net.xml for ZAM_Tjunction-1_374_I-1-1): moved to <sid>.net.xml, the
    name cr_world reads. → the file name, or None."""
    want = out / (sid + ".net.xml")
    if want.is_file():
        return want.name
    nets = sorted((p for p in out.glob("*.net.xml") if not p.name.startswith("rbl.")), key=lambda p: p.stat().st_mtime)
    if not nets:
        return None
    os.replace(nets[-1], want)
    return want.name


def read_lenient(src):
    """The scenario and its planning problems; a file whose objects reuse an id (the interactive set's 'ID 0 is already
    used': a lanelet and an obstacle both 0) is read again with the uniqueness check off. → (scenario, problems, lenient)."""
    from commonroad.common.file_reader import CommonRoadFileReader
    from commonroad.scenario import scenario as S
    try:
        sc, pps = CommonRoadFileReader(str(src)).open()
        return sc, pps, False
    except ValueError as e:
        if "already used" not in str(e):
            raise
    keep = S.Scenario._mark_object_id_as_used
    S.Scenario._mark_object_id_as_used = lambda self, object_id: self._id_set.add(object_id)
    try:
        sc, pps = CommonRoadFileReader(str(src)).open()
    finally:
        S.Scenario._mark_object_id_as_used = keep
    return sc, pps, True


class lock:
    """One conversion of an id at a time (workers in parallel ask for the same id): an flock on CACHE/.locks/<sid>."""
    def __init__(self, cache, sid):
        (cache / ".locks").mkdir(parents=True, exist_ok=True)
        self.path = cache / ".locks" / sid

    def __enter__(self):
        import fcntl
        self.f = open(self.path, "w")
        fcntl.flock(self.f, fcntl.LOCK_EX)
        return self

    def __exit__(self, *exc):
        import fcntl
        fcntl.flock(self.f, fcntl.LOCK_UN)
        self.f.close()


def convert(sid, root=ROOT, cache=CACHE, force=False):
    src = find(sid, root)
    sid = src.name[:-len(".cr.xml")] if src.name.endswith(".cr.xml") else src.stem
    with lock(cache, sid):
        return _convert(src, sid, cache, force)


def _convert(src, sid, cache, force):
    out = cache / sid
    meta, h = out / "cr.json", sha256(src)
    if not force and meta.is_file():
        old = json.loads(meta.read_text())
        if old.get("version") == CR_JSON_VERSION and old.get("sha256") == h and (out / old["net"]).is_file():
            return out
    out.mkdir(parents=True, exist_ok=True)
    sc, pps, lenient = read_lenient(src)
    from commonroad_sumo.cr2sumo.map_converter.map_converter import CR2SumoMapConverter, CR2SumoMapConverterConfig
    conf = CR2SumoMapConverterConfig.from_scenario(sc)
    conf.overwrite_speed_limit = None                  # the scenario's own limits, not the converter's 130 km/h everywhere
    conv = CR2SumoMapConverter(sc, conf)
    lights_dropped = False
    try:
        made = conv.create_sumo_files(out.resolve())
    except ValueError as e:
        # cr2sumo's _create_traffic_lights raises a bare ValueError for a light on a lanelet outside an intersection with
        # no or several successors (44 rows, USA_Lanker-1_16_T-1): converted again without its lights, said in cr.json
        if str(e) or "_create_traffic_lights" not in "".join(__import__("traceback").format_tb(e.__traceback__)):
            raise
        conv = CR2SumoMapConverter(sc, conf)
        conv._create_traffic_lights = lambda: None
        made, lights_dropped = conv.create_sumo_files(out.resolve()), True
    if made is None:
        raise SystemExit("cr_convert: %s: the map converter made no SUMO net" % sid)
    net = produced_net(out, sid)
    if net is None:
        raise SystemExit("cr_convert: %s: the map converter wrote no .net.xml in %s" % (sid, out))
    doc = {"version": CR_JSON_VERSION, "id": sid, "source": str(src), "sha256": h, "dt": float(sc.dt),
           "net": net, "net_offset": net_offset(str(out / net)), "converter": {"commonroad-sumo": _ver("commonroad-sumo"),
           "commonroad-io": _ver("commonroad-io"), "highway_mode": conf.highway_mode, "country": conf.country_id.value},
           "tags": sorted(t.value for t in (sc.tags or ())), "edges": {str(k): v for k, v in conv.lanes_dict.items()},
           "edges_missing": sorted(str(k) for k in conv.lanes_dict if str(k) not in net_edges(str(out / net))),
           "lanelets": lanelet_rows(sc.lanelet_network), "signs": sign_rows(sc.lanelet_network),
           "lights": light_rows(sc.lanelet_network), "intersections": intersection_rows(sc.lanelet_network),
           "obstacles": obstacle_rows(sc), "planning": planning_rows(pps), "interactive": src.name.endswith(".cr.xml"),
           "lenient_ids": lenient, "lights_dropped": lights_dropped,
           # the converter's own lanelet -> edge and -> lane maps (it merges lanelets into edges with new ids): cr_world resolves
           # the ego's start and the goal's lanelets through them, geometry the fallback
           "lanelet_edge": {str(k): str(v) for k, v in conv.lanelet_id2edge_id.items()},
           "lanelet_lane": {str(k): str(v) for k, v in conv.lanelet_id2lane_id.items()}}
    doc["right_before_left"] = right_before_left(out, net, doc)       # the scenario's priority, not the converter's
    meta.write_text(json.dumps(doc))
    return out


def _ver(p):
    import importlib.metadata as md
    return md.version(p)


def index(root=ROOT, cache=CACHE):
    """A row per scenario of the checkout, read from the files' headers (no full parse: thousands of files)."""
    import re
    rows = []
    base = root / "scenarios" / "scenarios"
    for f in sorted(base.rglob("*.xml")):
        if f.name.endswith(SKIP) and not f.name.endswith(".cr.xml"):
            continue
        interactive = f.name.endswith(".cr.xml")
        if not interactive and "recorded" not in f.parts:
            continue
        sid = f.name[:-len(".cr.xml")] if interactive else f.stem
        head = f.open(errors="ignore").read(4096)
        tags = re.search(r"<scenarioTags>(.*?)</scenarioTags>", head, re.S) or re.search(r"<tags>(.*?)</tags>", head, re.S)
        rows.append({"id": sid, "set": "interactive" if interactive else "recorded", "source": f.parent.name if not interactive else f.parent.parent.name,
                     "path": str(f.relative_to(root)), "country": sid.split("_")[0], "map": sid.split("_")[1].split("-")[0] if "_" in sid else "",
                     "tags": re.findall(r"<(\w+)\s*/>", tags.group(1)) if tags else [],
                     "dt": float(re.search(r'timeStepSize="([0-9.]+)"', head).group(1)) if re.search(r'timeStepSize="([0-9.]+)"', head) else None})
    cache.mkdir(parents=True, exist_ok=True)
    (cache / "index.json").write_text(json.dumps({"version": CR_JSON_VERSION, "root": str(root), "rows": rows}))
    return rows


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("scenario", nargs="?")
    ap.add_argument("--root", default=str(ROOT))
    ap.add_argument("--cache", default=str(CACHE))
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--index", action="store_true")
    a = ap.parse_args(argv)
    if a.index:
        rows = index(Path(a.root), Path(a.cache))
        print(json.dumps({"scenarios": len(rows), "recorded": sum(r["set"] == "recorded" for r in rows),
                          "interactive": sum(r["set"] == "interactive" for r in rows)}))
        return
    if not a.scenario:
        ap.error("a scenario id or path, or --index")
    print(convert(a.scenario, Path(a.root), Path(a.cache), a.force))


if __name__ == "__main__":
    main()
