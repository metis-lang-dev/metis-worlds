"""sw2_roles.py — MiniHack's room over ONE role program (semantic-map s-d4270bed step 4's cases, on the library's
grid map in semantic-world s-227b8e1b step 2: the room's win turn on roles against the flat instance), on CPU,
through metis-agent's own DomainAgent (the session the service runs; no model: the program's rules act).

    .worlds/mh/bin/python experiments/sw2_roles.py setup OUT
    cd metis-agent/py && .venv/bin/python …/experiments/sw2_roles.py run OUT [CASE …] [--out OUT.json]

setup writes the packages under OUT (world/gen_level.generate_roles):
- medium:     room_medium_apple_newt_closed_none over the role program (the des's map): a door, a newt;
- medium-flat the same level, the same stand-in rules over its own cells, the geometry a static table (today's form);
- large:      a 76 × 21 level (MiniHack's largest MAP) over the SAME role program: a wall across it, a closed door,
              a newt on the way, the stairs at the far corner;
- large-view: the large level in view mode: the stairs unseen at the start (the frontier first);
- beast:      a level whose only way runs through a newt (fight, then on).
run: each case on its own DomainAgent; the record — the program's loads (1: no reload), the grounding at load,
the steps and the time from the first beat to the win, the lines in the world's words (the host's speak), the
map's belief and binding before and after."""
import json
import os
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
WORLD = HERE.parent / "world"
VARIANT = ("medium", "apple", "newt", "closed", "none")


def big_des(w=76, h=21, beast=(20, 5), wall=True):
    sys.path.insert(0, str(WORLD))
    from minihack import LevelGenerator
    wx, dy = w // 2, h // 2
    rows = ["." * wx + (("+" if y == dy else "|") if wall else ".") + "." * (w - wx - 1) for y in range(h)]
    lvl = LevelGenerator(map="\n".join(rows) + "\n", lit=True)
    if wall:
        lvl.add_door("closed", place=(wx, dy))
    lvl.set_start_rect((0, 0), (2, 2))
    lvl.add_stair_down(place=(w - 2, h - 2))
    if beast:
        lvl.add_monster("newt", place=beast)
    return lvl.get_des()


def corridor_des():
    """A corridor one cell wide, a newt in it: the only way to the stairs runs through it."""
    from minihack import LevelGenerator
    rows = ["|||||||||||", "|.........|", "|||||||||||"]
    lvl = LevelGenerator(map="\n".join(rows) + "\n", lit=True)
    lvl.set_start_rect((1, 1), (1, 1))
    lvl.add_stair_down(place=(9, 1))
    lvl.add_monster("newt", place=(5, 1))
    return lvl.get_des()


def setup(out):
    sys.path.insert(0, str(WORLD))
    import gen_level
    out = Path(out)
    dom = out / "domains"                              # a catalog root: metis-agent loads OUT/domains/<name> (METIS_CATALOG=OUT)
    dom.mkdir(parents=True, exist_ok=True)
    pk = {"medium": gen_level.generate_roles(VARIANT, 1, str(dom)),
          "medium-flat": gen_level.generate_roles(VARIANT, 1, str(dom), flat=True),
          "large": gen_level.generate_roles(None, 1, str(dom), des=big_des(), name="large_76x21_roles", max_steps=400),
          "large-view": gen_level.generate_roles(None, 1, str(dom), des=big_des(), name="large_76x21_view", view=True, max_steps=600),
          "beast": gen_level.generate_roles(None, 1, str(dom), des=corridor_des(), name="corridor_newt_roles", max_steps=200),
          "medium-k16": gen_level.generate_roles(VARIANT, 1, str(out / "k16" / "domains"), k=16, name="room_medium_apple_newt_closed_none_k16"),
          "large-k16": gen_level.generate_roles(None, 1, str(out / "k16" / "domains"), des=big_des(), name="large_76x21_k16", k=16, max_steps=400)}
    (out / "pk.json").write_text(json.dumps(pk, indent=1))
    for k, v in pk.items():
        print(k, v)


def run_case(pkg, beats=800):
    import metis.lang.repl as R
    from metis_agent import domains
    from metis_agent.domain_agent import DomainAgent
    loads = [0]
    orig = R.Repl._load

    def counted(self, *a, **kw):
        loads[0] += 1
        return orig(self, *a, **kw)
    R.Repl._load = counted
    name = Path(pkg).name
    t0 = time.perf_counter()
    os.environ["METIS_CATALOG"] = str(Path(pkg).resolve().parents[1])   # the package's catalog root (OUT, or OUT/k8)
    mod = domains.load(name, fresh=True)
    ag = DomainAgent(mod)
    t_load = time.perf_counter() - t0
    # the watch blind (arm A: the reading applied, no verdict), both forms alike: MiniHack's world brings what no
    # rule predicts — the room behind a door seen as it opens, a beast's own step — and a surprise waits for a
    # consult, which needs the model (none on this CPU step); the surprises are counted, not consulted
    ag.watch.blind = True
    host = ag.host.inner
    mp = json.loads(Path(host.level["map"]).read_text())
    before = {"belief": mp["belief"], "binding": mp["binding"], "known": len(mp["cells"]), "path": len(mp["path"])}
    repl, said, fired, k = ag.repl, [], [], len(ag.repl.fired_rows)
    t1 = time.perf_counter()
    n = 0
    for n in range(1, beats + 1):
        ag.handle({"clock": "beat"})
        under = list(host.fired)                           # the binding each command fired under, in order (the host's record)
        host.fired = []
        for kind, stage, ev in ag.repl.fired_rows[k:]:
            if kind == "exo":
                continue
            fired.append(ev.name)
            line = ag.replier.line(ev)[0]
            if line:
                b = next((under.pop(i)[1] for i, (nm, _) in enumerate(under) if nm == ev.name), None)
                said.append(host.speak(line, binding=b))
        k = len(ag.repl.fired_rows)
        if host.done:
            break
    dt = time.perf_counter() - t1
    to_win = (host.won_at - t1) if getattr(host, "won_at", None) else None
    mp = json.loads(Path(host.level["map"]).read_text())
    after = {"belief": mp["belief"], "binding": mp["binding"], "known": len(mp["cells"]), "seen": len(mp["seen"])}
    R.Repl._load = orig
    rec = {"package": name, "loads": loads[0], "flat": bool(host.cmap.load()["flat"]), "same_session": ag.repl is repl, "load_s": round(t_load, 2),
           "beats": n, "steps": host.t, "won": host.won, "done": host.done, "turn_s": round(dt, 3),
           "to_win_s": round(to_win, 3) if to_win is not None else None,                  # the first beat to the winning step
           "record_s": round(dt - to_win, 3) if to_win is not None else None,             # … then the episode's record
           "rules": {r.split("[")[0]: sum(1 for f in fired if f.split("[")[0] == r.split("[")[0]) for r in set(fired)},
           "said": said, "before": before, "after": after}
    host.gym.close()
    return rec


def ground(pkg):
    """The program's grounding at load, alone (metispy's compiler: events, ms)."""
    from metis.lang.compiler import load_llp
    p = Path(pkg) / (Path(pkg).name + ".llp")
    t0 = time.perf_counter()
    prog = load_llp(p).catalog.ground({})
    return {"events": sum(len(v) for v in prog.stages.values()) + len(prog.links), "ms": round((time.perf_counter() - t0) * 1000, 1)}


def run(out, cases, dest=None):
    os.environ["METIS_CATALOG"] = str(Path(out).resolve())
    pk = json.loads((Path(out) / "pk.json").read_text())
    res = {}
    for c in cases:
        r = run_case(pk[c])
        r["ground"] = ground(pk[c])
        res[c] = r
        print("== %s: won %s in %d steps, %d beats, to the win %s s, then the record %s s (load %.2f s; ground %s); loads %d, same session %s" % (
            c, r["won"], r["steps"], r["beats"], r["to_win_s"], r["record_s"], r["load_s"], r["ground"], r["loads"], r["same_session"]))
        print("   rules", r["rules"])
        print("   said", r["said"][:12], "…" if len(r["said"]) > 12 else "")
        print("   before", json.dumps(r["before"])[:300])
        print("   after ", json.dumps(r["after"])[:300])
    if dest:
        Path(dest).write_text(json.dumps(res, indent=1))
    return res


if __name__ == "__main__":
    if sys.argv[1] == "setup":
        setup(sys.argv[2])
    else:
        dest = sys.argv[sys.argv.index("--out") + 1] if "--out" in sys.argv else None
        cases = [a for a in sys.argv[3:] if not a.startswith("--") and a != dest]
        run(sys.argv[2], cases or ["medium", "medium-flat", "beast", "large", "large-view"], dest)
