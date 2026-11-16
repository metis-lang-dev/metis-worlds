"""alf_runner.py — ALFWorld's HEADLESS SCENARIO RUNNER on the generic Metis runtime (metis-plugin s-df4ff191;
metis-agent plugin/docs/RUNTIME-INTERFACE.md v1.6 §1, §6). Domain code only: how a task becomes a run. The feed, the
findings' writing and the run loop are metis-agent's (runtime.feed.RuntimeFeed, runtime.run.Run).

    python runner/alf_runner.py --workspace ALFWORLD_DIR [--name alfworld] [--game GAME] [--object tomato]
                                [--receptacle microwave1] [--ticks 400] [--linger 5]

One run per invocation, served as the runtime NAME (.metis/runtimes/<name>.json): the room's game installed (the
workspace's bundle in place, demo.setup's bundle mode: the game's install runs in ALFWorld's own venv, which has
textworld), the person's FETCH typed into the Live (no model), the run until the agent's status ends. The kernel
watch's surprises come through the Live's on_finding (metis-agent); ALFWorld's own finding is END: the task did not
end done (refused, stuck, asking), written through the SDK's drop_window, then signalled.

Found by itself (as road/demo.sh, so runner.yaml names no env): ALFWORLD_DATA and METIS_ALF_PY (ALFWorld's venv) from
the environment, else <perotheia-packages>/.worlds/{alfworld-data, alf/bin/python} (walking up from here), else the
host's ~/repo/perotheia-packages/.worlds. stdout: one JSON line, the run's out."""
import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ALF = HERE.parent
END = ("over", "done", "stuck", "asking")


def worlds():
    """The .worlds directory holding ALFWorld's venv and data."""
    p = ALF
    while p != p.parent:
        if (p / ".worlds").is_dir():
            return p / ".worlds"
        p = p.parent
    return Path.home() / "repo" / "perotheia-packages" / ".worlds"


def main(argv=None):
    ap = argparse.ArgumentParser(prog="alf_runner")
    ap.add_argument("--workspace", default=str(ALF))
    ap.add_argument("--name", default="alfworld")
    ap.add_argument("--game", default="train/pick_and_place_simple-Tomato-None-Microwave-13")
    ap.add_argument("--object", default="tomato")
    ap.add_argument("--receptacle", default="microwave1")
    ap.add_argument("--ticks", type=int, default=400)
    ap.add_argument("--linger", type=float, default=5.0)
    ap.add_argument("--plant", default=None, metavar="MEMBER:-ATOM,+ATOM",
                    help="a PLANTED world change, once: after MEMBER's first command, its next reading drops each -ATOM "
                         "and adds each +ATOM (e.g. grasp:-holding,+handsfree: the take the game took, read as not taken), "
                         "so the member's kernel watch finds its own effect missing: a surprise (the watch's path, proven)")
    a = ap.parse_args(argv)
    ws = Path(a.workspace).resolve()
    w = worlds()
    os.environ.setdefault("ALFWORLD_DATA", str(w / "alfworld-data"))
    os.environ.setdefault("METIS_ALF_PY", str(w / "alf" / "bin" / "python"))
    os.environ.setdefault("METIS_CATALOG", str(ws))
    root = ws / ".metis" / "alf-run"
    os.environ["METIS_ALF_RUN"] = str(root)

    from metis_agent.runtime.feed import RuntimeFeed
    from metis_agent.runtime.host import RuntimeHost
    from metis_agent.runtime.run import Run
    import yaml

    class AlfRuntime(RuntimeHost):
        name, domain, window = a.name, "alfworld", (20, 5)
        err = None

        def start(self, live, cfg):
            live.started.set()
            if a.plant:
                self.plant(live, a.plant)
            self.err = live.typed("task", "r1", {"intent": "FETCH", "object": a.object.upper(),
                                                 "receptacle": a.receptacle.upper()})

        def plant(self, live, spec):
            """Wrap the member's host's observe (the reading its watch scores): once, after its first command, the
            reading the planted change makes. Said in the run's summary; never on without --plant."""
            member, _, change = spec.partition(":")
            ag = live.agents.agents.get(member)
            outer = getattr(ag, "host", None)
            inner = getattr(outer, "inner", outer)
            if outer is None or not hasattr(outer, "observe"):
                raise ValueError("--plant: no member %s with a world host that the watch reads" % member)
            drop = [x[1:] for x in change.split(",") if x.startswith("-")]
            add = [x[1:] for x in change.split(",") if x.startswith("+")]
            real, self.planted = outer.observe, None        # the face the watch reads (AgentHost copies the inner one)

            def observe(counts):
                r = real(counts)
                n = len(getattr(inner, "commands", None) or [])
                if n == 1:                      # from its first command until its next: the planted reading
                    r = {x: c for x, c in r.items() if x not in drop}
                    r.update({x: 1 for x in add})
                    if self.planted is None:
                        self.planted = {"member": member, "after": inner.commands[0][2], "dropped": drop, "added": add,
                                        "reads": 0}
                    self.planted["reads"] += 1
                return r
            outer.observe = observe

        def done(self, live, k):
            return bool(self.err) or bool(live.status and live.status.get("state") in END)

        def summary(self, live):
            return {"status": live.status, "typed": self.err, "task": [a.object, a.receptacle], "game": a.game,
                    **({"planted": getattr(self, "planted", None)} if a.plant else {})}

        def end_findings(self, live, summary):
            st = (live.status or {}).get("state")
            if self.err or st not in ("over", "done"):
                why = self.err or "%s: %s" % (st or "no end", (live.status or {}).get("text") or "")
                return [{"kind": "end", "slug": "task", "member": "task",
                         "words": "the task FETCH %s -> %s did not end done: %s" % (a.object, a.receptacle, why)}]
            return []

    # the game's install needs textworld: ALFWorld's own venv (as experiments/sm_cases.py's setup); the run: the Live's
    setup = ("import sys; from pathlib import Path; sys.path[:0] = [%r, %r]; import demo, families; "
             "g = next(Path(families.data_root(), %r).glob('trial_*')); c = demo.setup(g, %r, view=True, bundle=True); "
             "print('CFG', c[0])" % (str(ws / "experiments"), str(ws / "world"), a.game, str(root)))
    got = subprocess.run([os.environ["METIS_ALF_PY"], "-c", setup], capture_output=True, text=True, cwd=str(ws))
    line = [x for x in got.stdout.splitlines() if x.startswith("CFG ")]
    if got.returncode or not line:
        sys.stderr.write(got.stderr[-4000:] or got.stdout[-4000:])
        print(json.dumps({"run": None, "reason": "error", "error": "the game's setup failed (stderr above)"}), flush=True)
        return 2
    cfg = yaml.safe_load(Path(line[-1][4:]).read_text())
    cfg["domains"]["consult"] = False                    # no model in a runtime's run
    cfg["domains"].pop("narrate", None)
    host = AlfRuntime()
    feed = RuntimeFeed(ws, a.name, host)
    feed.start(port=0)
    try:
        out = Run(ws, host, feed).go(cfg, a.ticks, "%s-%s" % (Path(a.game).name, a.object), spec=vars(a))
        print(json.dumps(out, default=str), flush=True)
    finally:
        feed.stop(linger=a.linger)
    return 0 if out.get("reason") != "error" else 1


if __name__ == "__main__":
    sys.exit(main())
