"""record_run.py — one exploitation turn of the hierarchy, recorded as the world page's frames
(alf-demo step 3b, docs/DEMO.md §5), in TEXT mode: the fixture web/world.html replays and its
e2e test drives, until THOR's recorded run (step 1) brings frames.

    ALFWORLD_DATA=… .worlds/alf/bin/python experiments/record_run.py GAME_DIR MAP.json OUT.jsonl "the words" [GOAL]

The run is experiments/hier.py's --director run (the director's rules make the switch); GOAL is
the typed J's atom (default: the map's task goal), so a person's other goal
(`fetch(tomato1,fridge1)`) records a disengagement. One JSON frame per line, `dt` the ms since
the one before:
  {ev: world/map, url}                                the map (relative to this file)
  {ev: journal, rec: {kind: dlg-wake, what: person, person}}       the words
  {ev: journal, rec: {kind: dlg-dispatch, cid, domain: task, j}}    the typed intent (j: its JSON, as the wire has it)
  {ev: world/hierarchy, beat, arrival, effects, state}  the director's beat: its state atoms
                                                        (active/inactive, attention, sent,
                                                        pending) and its effects
  {ev: journal, rec: {kind: dlg-domain, verb, domain, by: director}}   wake / sleep
  {ev: journal, rec: {kind: dlg-trace, domain, beat, fired}}        an activation's rules
  {ev: world/delta, agent?, entities?, hot?, cornered?, task?}      what the world did, and the
                                                        task card's chain and result lines
  {ev: journal, rec: {kind: dlg-say, what: voice | ask, text, src}} the result's own %% line
The journal records are metis-agent's (docs/WIRE.md); world/hierarchy is this fixture's (the
orchestrator's director frame, opus's step 2, will carry the same atoms).
"""
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(ROOT, "world"))
import hier  # noqa: E402
from alf_host import AlfHost  # noqa: E402
import gen_instance  # noqa: E402
from semantic_map import SemanticMap, spoken  # noqa: E402

RUNS, BEATS = [], []
_beat = hier.director_beat


def run_package(path, steps=12):
    """hier.run_package, keeping the run's fired rule instances (the REPL's `run N` prints them
    first): the result's %% line is the line of the rule that made it."""
    pkg = os.path.dirname(path)
    log = os.path.join(pkg, "host.log")
    env = dict(os.environ, METIS_ALF_LOG=log, METIS_ALF_PY=os.environ.get("METIS_ALF_PY", sys.executable))
    p = subprocess.run([hier.metis_py(), "--plugin", os.path.join(pkg, "alf_host.py:make"), path], input="run %d\n" % steps,
                       capture_output=True, text=True, env=env, timeout=600)
    recs = [json.loads(x) for x in open(log)] if os.path.exists(log) else []
    ticks = [r for r in recs if r.get("tick")]
    last = ticks[-1] if ticks else {}
    fired = next(([x for x in ln.split() if "[" in x] for ln in p.stdout.splitlines() if "[" in ln and "stage " not in ln), [])
    err = None
    if p.returncode != 0 or "Traceback" in p.stderr:
        err = (p.stderr.strip().splitlines() or ["rc %d" % p.returncode])[-1]
    out = {"commands": [r for r in recs if "rule" in r], "out": last.get("out", []), "tokens": last.get("tokens", []),
           "error": err, "stderr": p.stderr[-400:], "fired": fired, "spec": os.path.basename(pkg).split("-")[0]}
    RUNS.append(out)
    return out


def director_beat(out_dir, k, state, arrival):
    effects, new = _beat(out_dir, k, state, arrival)
    BEATS.append({"beat": k, "arrival": arrival, "effects": effects, "state": new})
    return effects, new


hier.run_package, hier.director_beat = run_package, director_beat


def lines():
    """rule name → its %% line, from every specialist's base and the task's."""
    out = {}
    for f in os.listdir(os.path.join(ROOT, "domains", "hier")):
        if f.endswith("_domain.llp"):
            prev = None
            for ln in open(os.path.join(ROOT, "domains", "hier", f)):
                s = ln.strip()
                if s.startswith("%%"):
                    prev = s[2:].strip()
                elif "[dyn]" in s and prev:
                    out[s.split()[0]] = prev
                    prev = None
                else:
                    prev = prev if not s else None
    return out


def said(line, fired, names=None):
    """A %% line with its {X} filled from the fired instance's bindings — the roles as the things the
    map binds them to (names: role → handle), the handles spoken."""
    _, _, b = fired.partition("[")
    binds = dict(kv.split("=", 1) for kv in b.rstrip("]").split(",") if "=" in kv)
    names = names or {}
    t = re.sub(r"\{(\w+)\}", lambda m: spoken(names.get(binds.get(m.group(1), m.group(1)), binds.get(m.group(1), m.group(1)))), line)
    return t[:1].upper() + t[1:]


def record(game_dir, map_path, out_path, words, goal):
    """The director's run on the game with the typed goal; its frames (above) to out_path."""
    sem = json.load(open(map_path))
    work = tempfile.mkdtemp(prefix="alf-record-")       # the bases beside the packages, as hier.main sets them
    shutil.copy(os.path.join(ROOT, "domains", "alfred_domain.llp"), work)
    os.makedirs(os.path.join(work, "hier"))
    for s in hier.gen_hier.SPECS:
        shutil.copy(os.path.join(ROOT, "domains", "hier", s + "_domain.llp"), os.path.join(work, "hier"))
    shutil.copy(os.path.join(ROOT, "domains", "hier", "capacity.llp"), os.path.join(work, "hier"))
    shutil.copytree(os.path.join(ROOT, "domains", "hier", "iface"), os.path.join(work, "hier", "iface"))   # the bases' interface package
    shutil.copy(os.path.join(ROOT, "domains", "director_domain.llp"), work)
    r = hier.run_game_director(game_dir, work, first=[goal])
    L = lines()
    smap = SemanticMap(os.path.join(work, gen_instance.instance_id(game_dir), ".map.json"))
    names = {role: h for role, h in smap.binding().items()}      # the run's binding: the frames say the room's things

    def room(atom):
        if "(" not in atom:
            return atom
        n, _, rest = atom.partition("(")
        return "%s(%s)" % (n, ",".join(names.get(a, a) for a in rest.rstrip(")").split(",")))
    o, rr = goal[goal.index("(") + 1:-1].split(",")
    frames = [{"ev": "world/map", "url": os.path.relpath(os.path.abspath(map_path), os.path.dirname(os.path.abspath(out_path)))},
              {"ev": "journal", "rec": {"kind": "dlg-wake", "what": "person", "person": words}},
              {"ev": "journal", "rec": {"kind": "dlg-dispatch", "cid": "c1", "domain": "task",     # the wire's: j a JSON string
                                        "j": json.dumps({"intent": "FETCH", "object": o.upper(), "receptacle": rr.upper()},
                                                        separators=(",", ":"))}}]
    # the world, replayed command by command on a fresh host: the deltas
    flat, _, _ = gen_instance.generate(game_dir, os.path.join(work, "flat"))
    host = AlfHost(os.path.dirname(flat))
    to_handle = {v: k for k, v in host.to_name.items()}
    items = {p["id"]: [t["name"] for t in sem["things"] if t["at"] == p["id"]] for p in sem["places"]}
    chain, results = [], []
    acts = iter(zip(r["activations"], RUNS))           # one run per forward, in the order they ran
    try:
        for b in BEATS:
            frames.append({"ev": "world/hierarchy", **b})
            for e in b["effects"]:
                m = re.match(r"(wake|sleep)\((\w+)\)", e)
                if m:
                    frames.append({"ev": "journal", "rec": {"kind": "dlg-domain", "verb": "activate" if m.group(1) == "wake" else "deactivate",
                                                             "domain": m.group(2), "by": "director"}})
            for e in (e for e in b["effects"] if e.startswith("forward(")):
                act, run = next(acts, (None, None))
                if act is None:
                    break
                spec = act["spec"]
                frames.append({"ev": "journal", "rec": {"kind": "dlg-trace", "domain": spec, "beat": b["beat"], "fired": run["fired"]}})
                for c in run["commands"]:
                    host._take(host.gym.call("step", command=c["command"]))
                    frames.append({"ev": "world/delta", **delta(c["command"], to_handle, items)})
                if spec != "task":
                    chain.append({"domain": spec, "goal": room(act["goal"]), "result": ", ".join(room(a) for a in act["result"])})
                line = next((said(L[f.split("[")[0]], f, names) for f in reversed(run["fired"]) if f.split("[")[0] in L), None)
                if not line:
                    continue
                results.append(line)
                ask = next((x for x in act["result"] if x.split("(")[0] in ("wrong_dest", "wrong_object", "stuck")), None)
                frames.append({"ev": "world/delta", "task": {"chain": list(chain), "results": list(results)},
                               **({"cornered": _arg(room(ask), 0)} if ask else {})})
                frames.append({"ev": "journal", "rec": {"kind": "dlg-say", "what": "ask" if ask else "voice", "text": line,
                                                         "src": {"by": "harness", "domain": spec, "what": "result"}}})
        if r["won"]:
            frames.append({"ev": "journal", "rec": {"kind": "dlg-say", "what": "voice", "text": "The task is done.",
                                                     "src": {"by": "harness", "domain": "director", "what": "ended"}}})
    finally:
        host.gym.close()
        shutil.rmtree(work, ignore_errors=True)
    for i, f in enumerate(frames):
        f["dt"] = 0 if i == 0 else 400
    with open(out_path, "w") as fh:            # closed now (alfworld/world/README.md: the loader's hazards)
        for f in frames:
            fh.write(json.dumps(f) + "\n")
    return r, frames


def _arg(atom, i):
    return atom[atom.index("(") + 1:-1].split(",")[i]


def delta(command, to_handle, items):
    """What one game command changed, as the map's delta."""
    words = command.split(" ")
    if command.startswith("go to "):
        return {"agent": {"at": to_handle.get(command[6:], command[6:])}}
    if command.startswith("open "):
        return {"entities": [{"id": to_handle.get(command[5:], command[5:]), "closed": False}]}
    if command.startswith("take "):
        o, r = command[5:].split(" from ")
        oh, rh = to_handle.get(o, o), to_handle.get(r, r)
        items[rh] = [x for x in items.get(rh, []) if x != spoken(oh)]
        return {"agent": {"holding": spoken(oh)}, "entities": [{"id": rh, "items": items[rh]}]}
    if command.startswith("move "):
        o, r = command[5:].split(" to ")
        oh, rh = to_handle.get(o, o), to_handle.get(r, r)
        items[rh] = items.get(rh, []) + [spoken(oh)]
        return {"agent": {"holding": None}, "entities": [{"id": rh, "items": items[rh]}]}
    return {"note": command}


if __name__ == "__main__":
    game, map_path, out, words = sys.argv[1:5]           # read first: the game's loader rewrites sys.argv
    goal = sys.argv[5] if len(sys.argv) > 5 else json.load(open(map_path))["task"]["goal"].replace(" ", "")
    r, frames = record(game, map_path, out, words, goal)
    print("%s: %s, %d activations, %d commands; %d frames" % (os.path.basename(out), r["outcome"], r["n_activations"],
                                                               r["commands"], len(frames)))
