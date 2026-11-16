#!/usr/bin/env python3
"""road_runner.py — the road's HEADLESS SCENARIO RUNNER (metis-plugin s-df4ff191; the user: scenario running is the
domain's, separate from the runtime): one or more catalog cards (or scenarios) played by the road family with no page,
each run a RUNTIME the Metis plugin attaches to by name (/metis-runtime road: metis-agent's RuntimeClient follows the
name from run to run). The run loop, the feed and the wire are metis-agent's (metis_agent.runtime: run.Run, feed.RuntimeFeed);
this file only turns a card into a run (cards.py) and hands road's host (host.py) to the loop.

    (cwd metis-worlds; the Live's venv; metis_agent with its runtime package on the path)
    python road/runner/road_runner.py --card FollowLeadingVehicle [--card ID ...] [--seed 1] [--host sumo|exerciser]
                                      [--site I] [--ticks N] [--scenario NAME] [--workspace road] [--name road] [--linger 5]

- the workspace: metis-worlds/road by default (its .metis/: traces, surprises), or --workspace W
- ONE runtime (feed) named NAME for the invocation, serving while its runs go: .metis/runtimes/<name>.json; every run's
  trace in .metis/traces/<run>, its findings (collisions, RSS violations, broken road rules, a failed end) written as
  surprises and signalled (surprise.new) as their segment closes; run.started / run.ended per run; LINGER seconds after
  the last run for an attached client to drain, then the discovery file removed
- its own environment: SUMO found as road/demo.sh finds it (sumo_env), the semantic world and road/world on its path;
  the session's PYTHONPATH (metis-agent's runtime, metispy's SDK) and METIS_HOME are kept
- SIGTERM / SIGINT (the plugin's runner_stop, its session's end): the run on stops at its next tick ('stopped': the
  world shut, its findings written), the cards after it are not started, the feed stops at once (its file removed)
- stdout: one JSON line per run {run, trace, reason, summary, error}, then {done: true, runs}; exit 1 when a run errs
- the workspace's runner.yaml names this command (the agent adds --card ...)."""
import argparse
import json
import signal
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROAD = HERE.parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(ROAD / "world"))
sys.path.insert(0, str(ROAD.parent / "libs" / "semantic-world"))     # metis-worlds' own library (the road world's)


def stem_of(scenario, seed):
    return "%s-%d" % (scenario.replace(":", "_").replace("@", "_").replace("#", "_"), int(seed))


def specs(a):
    base = {"seed": a.seed, "host": a.host, "ticks": a.ticks, "site": a.site}
    out = [dict(base, card=c) for cs in a.card or [] for c in cs.split(",") if c]
    out += [dict(base, scenario=s) for s in a.scenario or []]
    return [{k: v for k, v in s.items() if v is not None} for s in out]


def sumo_env():
    """SUMO for the run, found as road/demo.sh finds it, so the runner needs no environment of its own (runner.yaml
    names none): $SUMO_VENV, else <metis-worlds>/../.worlds/road, else ~/repo/perotheia-packages/.worlds/road (the
    host's install); its bin first on PATH, SUMO_HOME from its sumo package. A sumo already on PATH with SUMO_HOME set
    is kept as it is. -> the venv used, or None."""
    import os
    import shutil
    import subprocess
    if shutil.which("sumo") and os.environ.get("SUMO_HOME"):
        return None
    for v in [os.environ.get("SUMO_VENV"), ROAD.parent.parent / ".worlds" / "road",
              Path.home() / "repo" / "perotheia-packages" / ".worlds" / "road"]:
        if v and (Path(v) / "bin" / "sumo").exists():
            v = Path(v)
            os.environ["PATH"] = str(v / "bin") + os.pathsep + os.environ.get("PATH", "")
            if not os.environ.get("SUMO_HOME"):
                py = v / "bin" / "python"
                home = subprocess.run([str(py), "-c", "import sumo; print(sumo.SUMO_HOME)"], capture_output=True,
                                      text=True).stdout.strip() if py.exists() else ""
                if home:
                    os.environ["SUMO_HOME"] = home
            return str(v)
    return None


def _quiet_stdout():
    """Our JSON lines on the real stdout; whatever else prints (SUMO's TraCI: 'Retrying in 1 seconds') to stderr."""
    out = sys.stdout
    sys.stdout = sys.stderr
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--card", action="append", help="a catalog card id (repeat, or a,b,c)")
    ap.add_argument("--scenario", action="append", help="a road world scenario name (road_tree's) instead of a card")
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--host", default="sumo", choices=["sumo", "exerciser"])
    ap.add_argument("--site", type=int, default=None)
    ap.add_argument("--ticks", type=int, default=None)
    ap.add_argument("--workspace", default=str(ROAD))
    ap.add_argument("--name", default="road")
    ap.add_argument("--port", type=int, default=0)
    ap.add_argument("--linger", type=float, default=5.0)
    a = ap.parse_args(argv)
    out_fh = _quiet_stdout()
    venv = sumo_env()
    if venv:
        sys.stderr.write("road runner: SUMO from %s\n" % venv)
    todo = specs(a)
    if not todo:
        ap.error("give --card ID (or --scenario NAME)")
    import cards
    import host as H
    from metis_agent.runtime.feed import RuntimeFeed
    from metis_agent.runtime.run import Run
    feed = RuntimeFeed(a.workspace, a.name, H.RoadHost())
    state = {"stop": False, "run": None}

    def term(*_):                                   # SIGTERM / SIGINT (runner_stop, the session's end): the run on stops
        state["stop"] = True                        # at its next tick, the world shut, the feed stopped, the file removed
        if state["run"] is not None:
            state["run"].stop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        signal.signal(sig, term)
    info = feed.start(port=a.port)
    sys.stderr.write("road runner: runtime %s at %s (%s)\n" % (a.name, info.get("url"), info.get("discovery")))
    results, bad = [], False
    try:
        for spec in todo:
            if state["stop"]:
                break
            try:
                scenario, world_kind, ticks, stop_after, env, card, kind = cards.plan(spec)
            except (SystemExit, ValueError, KeyError) as e:
                out = {"spec": spec, "reason": "error", "error": "the spec cannot be run: %s" % e}
                print(json.dumps(out), file=out_fh, flush=True)
                results.append(out)
                bad = True
                continue
            host = H.RoadHost(scenario, spec.get("seed", 1), world_kind=world_kind if world_kind == "sumo" else None,
                              card=card, kind=kind, stop_after=stop_after)
            state["run"] = Run(a.workspace, host, feed)
            out = state["run"].go(H.road_config(spec.get("seed", 1)), ticks, stem_of(scenario, spec.get("seed", 1)),
                                  spec=spec, env=env)
            state["run"] = None
            out["spec"] = spec
            print(json.dumps(out, default=str), file=out_fh, flush=True)
            results.append(out)
            bad = bad or out["reason"] == "error"
    finally:
        feed.stop(linger=0 if state["stop"] else a.linger)
    print(json.dumps({"done": True, "runs": [r.get("run") for r in results]}), file=out_fh, flush=True)
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
