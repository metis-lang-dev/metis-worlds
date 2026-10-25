"""The Bayesian cases on the exerciser (semantic-world s-227b8e1b step 3b, design §4):

    python examples/bayes_cases.py OUT_DIR      → the turns as JSON lines, the lines said, the map's journal

- case 6: a beast seen, lost behind a corner, its belief predicted along the lane, re-found. The corner level
  (dungeon.corner): the robot leaves the lit room by the doorway, walks the dark corridor round the corner and
  waits; a hostile newt follows it. Out of the room the robot sees only the eight cells around it, so the newt is
  lost at the doorway; the walk model (toward the robot, over the passable cells) carries its belief along the
  corridor; the newt is re-found when it comes round the corner beside the robot.
- case 8: the belief of a beast last seen turns ago, spread by the motion model and cut by the empty visible
  cells: every turn the newt is lost, the prediction spreads the mass, and the cells the robot sees empty take
  theirs (negative evidence; the rest renormalized).

Each turn records: the newt's true cell, whether it is seen, the predicted belief (before the sighting: the
model's), the mass the empty visible cells cut, the belief after, and the map's line (GridMap.describe)."""
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from semantic_world import dungeon  # noqa: E402
from semantic_world.grid import GridMap, name  # noqa: E402

ALIVE = (0.05, -2.0)                          # unseen, the newt fades in ~70 turns; each empty look at it costs 0.4 (bayes.L_MISS)
CONFIGS = ((1.0, None, "corner"),               # case 6: the model right
           (0.5, 0.5, "corner-slow-known"),     # case 6: a newt at half speed, the map told so (walk's float speed)
           (0.5, None, "corner-slow"))          # case 8: the model overshoots; the empty view cuts it
ROUTE = ["e", "e"] + ["e"] * 7 + ["s"] * 3          # out of the room, along the corridor, round the corner


def run(out_dir, dt=1.0, waits=20, speed=1.0, model_speed=None, tag="corner"):
    """Case 6 and case 8 in one run (SPEED: the newt's, cells a turn; MODEL_SPEED: what the map is told, else one). → {"turns": [...], "lost_at", "refound_at", "journal"}."""
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    lv = dungeon.corner()
    sim = dungeon.Sim(lv, [dungeon.Monster("newt", (1, 5), hostile=True, speed=speed)], seed=1)
    path = out / ("%s.map.json" % tag)
    for f in (path, Path(str(path) + ".journal.jsonl")):
        if f.exists():
            f.unlink()
    m = GridMap.build(str(path), (lv.w, lv.h), cells=lv.cells(), k=8, speeds={"newt": model_speed} if model_speed else None)
    turns, lost_at, refound_at = [], None, None
    plan = list(ROUTE) + ["wait"] * waits
    for t in range(len(plan) + 1):
        atoms = sim.perceive()
        newt = next((mo for mo in sim.monsters if mo.name == "newt"), None)
        true = name(*newt.pos) if newt else None
        seen = any(a.startswith("monster(newt,") for a in atoms)
        d = m.load()
        prev = dict(d["belief"].get("newt") or {})
        models = m.models()
        pred = models["newt"](dict(prev), dt) if prev and "newt" in models else {}
        m.cycle(atoms, dt, models, ALIVE)
        d = m.load()
        vis = set(m.visible(d))
        post = dict(d["belief"].get("newt") or {})
        rec = {"t": t, "ego": name(*sim.ego), "newt": true, "seen": seen,
               "pred_support": len(pred), "pred_at_true": round(pred.get(true, 0.0), 3) if true else None,
               "pred_rank_true": (sorted(pred, key=lambda c: (-pred[c], c)).index(true) + 1) if true in pred else None,
               "cut": round(sum(p for c, p in pred.items() if c in vis and not seen), 3),
               "post_support": len(post), "post_in_view": round(sum(p for c, p in post.items() if c in vis and not seen), 6),
               "line": m.describe("newt")}
        if not seen and lost_at is None and t > 0:
            lost_at = t
        if seen and lost_at is not None and refound_at is None:
            refound_at = t
        turns.append(rec)
        if refound_at is not None or t == len(plan):
            break
        a = plan[t]
        sim.act("wait") if a == "wait" else sim.act("move", a)
    with open(out / ("%s.turns.jsonl" % tag), "w") as f:
        for r in turns:
            f.write(json.dumps(r) + "\n")
    return {"turns": turns, "lost_at": lost_at, "refound_at": refound_at, "journal": str(path) + ".journal.jsonl",
            "passable": sum(1 for p in lv.tiles if lv.passable(p))}


if __name__ == "__main__":
    for speed, model, tag in CONFIGS:
        r = run(sys.argv[1] if len(sys.argv) > 1 else "out", speed=speed, model_speed=model, tag=tag)
        print("== %s: the newt at %g cells a turn, the model told %s" % (tag, speed, model or "nothing (one)"))
        for x in r["turns"]:
            print("%2d  robot %-7s newt %-7s %s  pred(newt's cell) %-5s rank %-4s cut %-5s  %s" % (
                x["t"], x["ego"], x["newt"], "seen" if x["seen"] else "lost", x["pred_at_true"], x["pred_rank_true"], x["cut"], x["line"]))
        print("lost at turn", r["lost_at"], "re-found at turn", r["refound_at"], "of", r["passable"], "passable cells; journal", r["journal"])
