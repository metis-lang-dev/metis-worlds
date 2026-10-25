"""The RSS situation cases on the exerciser (semantic-world s-227b8e1b step 3a, design §4 cases 4 and 5):

    python examples/situation_cases.py OUT_DIR     → per case the turns as JSON lines, the lines said, the map's journal

The level is dungeon.lanes(): two lit rooms joined by a one-wide dark lane, a junction on it opening a longer way
round. The ego walks from room A to the stairs in room B.

- case 4, an oncoming hostile in the lane: a newt comes down the lane at the ego. RSS's opposite direction: the
  pair is safe while the gap along the lane exceeds both reaches (the ego's step and the newt's in the response
  time, plus a cell); when it does not, the pair is dangerous, the lane gives no lateral room, the axis safe
  before was the longitudinal one, so the response is to brake along the lane (brake_min_correct: the ego is in
  its correct lane): the ego stops, then falls back to the last area (the passing place), where it has room and
  meets the newt beside it.
- case 5, a peaceful in the lane: a peaceful beast stands in the lane ahead (same direction, its speed 0). The ego
  yields at the safe gap (brake_min), waits three turns, then backs off to the junction, and takes the other way
  round (the route avoids the beast's cells).

The decision is a rule program over roles (RULES, compiled once, run in metispy's REPL): the host gives it the
map's facts between bound cells (next, toward, step, area/lane/junction), the situation layer's facts
(type, dangerous, safe_before, resp_lon), and a beat a turn; its outputs go(D), fight(D), seek(R), resume, avoid(B)
are the host's to carry out. The numbers (gaps, reaches, safe distances) stay in the host."""
import contextlib
import io
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from semantic_world import dungeon, ports  # noqa: E402
from semantic_world.grid import GridMap, capacity, name  # noqa: E402
from semantic_world.situation import Dynamics, Situation  # noqa: E402

RULES = """catalog rss_nav 1.
provenance text "the RSS cases' navigator over the grid roles (semantic-world step 3a, examples/situation_cases.py)" "2026-10-25".
layers (dyn).
stages (act).
types (cell beast).
type dir {n e s w ne se sw nw}.
type ctype {same_dir opp_dir xing_ego_prio xing_obj_prio xing_same_prio unstructured not_relevant}.
type resp {none brake_min_correct brake_min}.
type axis {none long lat both}.
type count {w0 w1 w2 w3}.
type refuge {area junction}.
namespace nav produce (dyn).
bwd succ(count, count).
succ(w0, w1). succ(w1, w2). succ(w2, w3).
% the host's, every turn: the map between bound cells, the situation layer's verdicts, one beat
pred beat : nav.
pred agent_at(cell) : nav.
pred next(cell, dir, cell) : nav.
pred toward(cell) : nav.
pred step(cell) : nav.
pred monster(beast, cell) : nav.
pred area(cell) : nav.
pred lane(cell) : nav.
pred junction(cell) : nav.
pred resp_lon(resp) : nav.
pred resp_lat(resp) : nav.
pred type(beast, ctype) : nav.
pred dangerous(beast) : nav.
pred safe_before(beast, axis) : nav.
pred refuged : nav.                     % the host's: the ego stands on its passing place
pred way_clear : nav.                   % the host's: no pair dangerous, nothing on the route to the goal in reach
% the program's own
pred free : nav.
pred waited(count) : nav.
pred refuging(refuge) : nav.
% the outputs, the host's to carry out
pred go(dir) : nav.
pred fight(dir) : nav.
pred hold : nav.
pred seek(refuge) : nav.
pred resume : nav.
pred avoid(beast) : nav.
stage act {
  %% I step {D}.
  advance [dyn] : beat * free * $resp_lon(none) * $agent_at(C) * $next(C, D, P) * $toward(P) * $step(P) -o free * go(D).
  %% {B} is coming down the lane at me: I stop and fall back to the open.
  fall_back [dyn] : beat * free * $resp_lon(brake_min_correct) * $dangerous(B) * $type(B, opp_dir) * $safe_before(B, long) * $agent_at(C) * $lane(C) -o refuging(area) * seek(area).
  %% {B} is on me in the lane already: I fall back to the open.
  fall_back_late [dyn] : beat * free * $resp_lon(brake_min_correct) * $dangerous(B) * $type(B, opp_dir) * $safe_before(B, none) * $agent_at(C) * $lane(C) -o refuging(area) * seek(area).
  %% {B} is beside me in the open: I fight it.
  fight_it [dyn] : beat * $dangerous(B) * $type(B, opp_dir) * $agent_at(C) * $area(C) * $next(C, D, P) * $monster(B, P) -o fight(D).
  %% {B} stands in my way: I wait.
  give_way [dyn] : beat * free * $resp_lon(brake_min) * $dangerous(B) * $type(B, same_dir) * waited(W) * $succ(W, W2) -o free * waited(W2) * hold.
  %% {B} stays in my way: I back off to the junction and go round.
  back_off [dyn] : beat * free * $resp_lon(brake_min) * $dangerous(B) * $type(B, same_dir) * waited(w3) -o waited(w0) * refuging(junction) * seek(junction) * avoid(B).
  %% I fall back, {D}.
  retreat [dyn] : beat * $refuging(R) * $agent_at(C) * $next(C, D, P) * $toward(P) * $step(P) -o go(D).
  %% The way is clear: I go on.
  go_on [dyn] : beat * refuging(R) * $refuged * $way_clear -o free * resume.
}
"""
OWNED = ("beat", "agent_at", "next", "toward", "step", "monster", "area", "lane", "junction", "resp_lon", "resp_lat", "type",
         "dangerous", "safe_before", "refuged", "way_clear", "go", "fight", "hold", "seek", "resume", "avoid")
EGO = Dynamics(vmin=0.0, vmax=1.0, rho=1.0, min_dist=1.0)


def program(out):
    """The rules over the grid's capacity, written once (the level is the host's map)."""
    p = Path(out) / "rss_nav.llp"
    p.write_text(RULES + "\n" + "\n".join(l for l in capacity().split("\n") if l.startswith("type ")) + "\n")
    return p


def way_clear(m, states, horizon):
    """No pair dangerous and no beast believed on the route to the goal within HORIZON steps (the route as the task
    has it: no refuge)."""
    if any(s.dangerous for s in states):
        return False
    d = m.load()
    refuge = d["task"].pop("refuge", None)
    m.save()
    path = m.route()
    d = m.load()
    if refuge:
        d["task"]["refuge"] = refuge
        m.save()
    beasts = {c for n, t in d["things"].items() if t.get("kind") == "beast" for c, p in (d["belief"].get(n) or {}).items() if p >= 0.5}
    return not any(c in beasts for c in path[1:horizon + 1])


def run(out_dir, case, seed=1, turns=80, horizon=6):
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    lv = dungeon.lanes()
    if case == 4:
        beasts = [dungeon.Monster("newt", (18, 3), hostile=True, speed=1)]
        sim = dungeon.Sim(lv, beasts, seed=seed)
        sim.ego = (6, 3)                                   # at room A's doorway, about to walk the lane
        peaceful = ()
    else:
        beasts = [dungeon.Monster("pony", (15, 3), hostile=False, speed=1)]
        sim = dungeon.Sim(lv, beasts, seed=seed)
        sim.ego = (8, 3)                                   # in the lane, the junction behind it
        peaceful = ("pony",)
    for b in beasts:                                       # a peaceful pony that stands its ground (the case's)
        if not b.hostile:
            b.speed = 0
    path = out / ("case%d.map.json" % case)
    for f in (path, Path(str(path) + ".journal.jsonl")):
        if f.exists():
            f.unlink()
    m = GridMap.build(str(path), (lv.w, lv.h), cells=lv.cells(), peaceful=peaceful,
                      speeds={b.name: b.speed for b in beasts})
    d = m.load()                                           # the beast spotted down the lane as the ego sets off
    for bst in beasts:                                     # (the lane is dark: from here the motion model carries it)
        d["things"][bst.name] = {"in": None, "kind": "beast", "of": bst.name}
        d["belief"][bst.name] = {name(*bst.pos): 1.0}
        d.setdefault("last_seen", {})[bst.name] = [name(*bst.pos), 0.0]
    m.save()
    from metis.lang.repl import Repl
    with contextlib.redirect_stdout(io.StringIO()):
        repl = Repl(str(program(out)), seed=seed)
        repl.onecmd("+free 1")
        repl.onecmd("+waited(w0) 1")
    sit = Situation()
    rows, said = [], []
    for t in range(turns):
        atoms = sim.perceive()
        m.cycle(atoms, models=m.models())
        b = m.project()
        d = m.load()
        states = sit.check(m.pairs(horizon=horizon))
        fold = Situation.fold(states, EGO)
        reading = {a: 1 for a in atoms}
        facts = m.role_reading(reading)
        facts.update(Situation.facts(states, fold))
        facts["beat"] = 1
        if m.route() == [d["agent"]["at"]] and d["task"].get("refuge"):
            facts["refuged"] = 1
        if way_clear(m, states, horizon):
            facts["way_clear"] = 1
        with contextlib.redirect_stdout(io.StringIO()):
            for line in ports.sync_diff(facts, repl.counts, OWNED):
                repl.onecmd(line)
            fired = []
            while len(fired) < 20 and repl._candidates():
                fired.append(repl._sample())
        outs = [a for a, n in repl.counts.items() if n > 0 and a.split("(")[0] in ("go", "fight", "hold", "seek", "resume", "avoid")]
        act, how = "wait", None
        for a in sorted(outs):
            p, xs = a.split("(")[0], ports.args(a)
            if p in ("go", "fight"):
                act, how = "move", xs[0]
            elif p == "seek":
                d = m.load()
                d["task"]["refuge"] = xs[0]
                m.save()
            elif p == "resume":
                d = m.load()
                d["task"].pop("refuge", None)
                m.save()
            elif p == "avoid":
                d = m.load()
                inst = b.get(xs[0], xs[0])
                d["task"].setdefault("avoid", [])
                if inst not in d["task"]["avoid"]:
                    d["task"]["avoid"].append(inst)
                m.save()
        rule_lines = [m.say(_line(f), b) for f in fired]
        said += rule_lines
        rows.append({"t": t, "ego": name(*sim.ego), "beasts": {x.name: name(*x.pos) for x in sim.monsters},
                     "pairs": [{"id": s.id, "role": s.role, "type": s.type, "d_lon": s.d_lon, "d_safe": s.d_safe,
                                "safe_long": s.safe_long, "safe_lat": s.safe_lat, "dangerous": s.dangerous,
                                "before": s.before, "resp_lon": s.resp_lon, "resp_lat": s.resp_lat} for s in states],
                     "fold": fold["resp_lon"], "fired": fired, "said": rule_lines, "act": [act, how],
                     "refuge": m.load()["task"].get("refuge"), "hazard": {n: m.hazard(n) for n in sorted(m.load()["belief"])
                                                                          if m.load()["things"][n].get("kind") == "beast"}})
        if sim.won:
            break
        said_kind = sim.act(act, how) if act != "wait" else sim.act("wait")
        if said_kind == "killed":                          # the world's message: the beast struck is dead
            x, y = sim.ego
            dx, dy = dungeon.STEPS[how]
            hit = name(x + dx, y + dy)
            inst = m.load().get("_beasts_seen", {})
            for n, c in inst.items():
                if c == hit:
                    m.gone(n, "killed")
    with open(out / ("case%d.turns.jsonl" % case), "w") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")
    return {"won": sim.won, "turns": len(rows), "rows": rows, "said": said, "journal": str(path) + ".journal.jsonl"}


def _line(fired):
    """The rule's %% line for a fired event, with its bindings (the program's doc lines)."""
    rule, _, binds = fired.partition("[")
    doc = DOCS.get(rule, rule)
    for kv in binds.rstrip("]").split(","):
        if "=" in kv:
            k, v = kv.split("=", 1)
            doc = doc.replace("{%s}" % k, v)
    return doc


DOCS = {}
_prev = None
for _l in RULES.split("\n"):
    _s = _l.strip()
    if _s.startswith("%%"):
        _prev = _s[2:].strip()
    elif _prev and "[dyn]" in _s:
        DOCS[_s.split()[0]] = _prev
        _prev = None


if __name__ == "__main__":
    for case in (4, 5):
        r = run(sys.argv[1] if len(sys.argv) > 1 else "out", case)
        print("== case %d: %s in %d turns" % (case, "won" if r["won"] else "NOT won", r["turns"]))
        for x in r["rows"]:
            ps = "; ".join("%s %s gap %g/%g %s%s" % (p["role"] or p["id"], p["type"], p["d_lon"], p["d_safe"],
                                                    "DANGEROUS" if p["dangerous"] else "safe", (" before " + str(p["before"])) if p["dangerous"] else "")
                           for p in x["pairs"])
            print("%2d ego %-6s %-30s fold %-17s %-10s %s | %s" % (x["t"], x["ego"], json.dumps(x["beasts"]), x["fold"],
                                                                 "/".join(str(v) for v in x["act"] if v), ps, " ".join(x["said"])))
