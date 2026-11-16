"""road/runner (metis-plugin s-df4ff191; RUNTIME-INTERFACE v1.5): the road's headless scenario runner over metis-agent's
generic runtime.

- the observer on a fake world: collisions merged as the Leaderboard does, violations, the exerciser's own rows, the end
  finding only when the card's checks fail;
- road's host under runtime.run.Run on the exerciser (no SUMO): the world's tick IS the trace's tick (the findings'
  k), the run spec file names the trace dir, the world closed;
- the runner over the exerciser with a RuntimeClient attached by the runtime's NAME before it exists (as the plugin):
  run.started -> run.ended, the trace in the workspace, the discovery file gone after it;
- one SUMO card end to end (RUNNER_SUMO=1 and sumo on PATH): a finding written and signalled (surprise.new) before
  run.ended, its record in the workspace.
Needs the Live's venv with metis_agent's runtime package (metis-agent claude-plugin) and METIS_HOME; skipped otherwise."""
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

import pytest

ROAD = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROAD / "runner"))
import observer as O  # noqa: E402


class FakeWorld:
    def __init__(self):
        self.collisions = []


class FakeLoop:                                   # sumo_host.Loop's shape: .world.collisions, .violations, .tick
    def __init__(self):
        self.world, self.violations, self.tick = FakeWorld(), [], 0


def test_observer_collisions_merged_and_violations():
    lp, ob, out = FakeLoop(), O.Observer(), []
    for k in range(1, 200):
        lp.tick = k
        if k in (50, 51, 52):                     # SUMO reports a contact every step it lasts: one event
            lp.world.collisions.append({"t": k * 0.1, "collider": "ego", "victim": "car7", "type": "collision"})
        if k == 120:                              # the same other again, 7 s later: a second event
            lp.world.collisions.append({"t": k * 0.1, "collider": "car7", "victim": "ego"})
        if k == 60:
            lp.world.collisions.append({"t": 6.0, "collider": "car1", "victim": "car2"})    # not the ego's
        if k == 90:
            lp.violations.append({"tick": 90, "what": "a lane change into it", "pair": "car3:same_dir"})
        out += ob.new(lp)
    assert [(f["kind"], f["k"]) for f in out] == [("collision", 50), ("violation", 90), ("collision", 120)]
    assert out[0]["other"] == "car7" and "lane change" in out[1]["words"] and out[1]["slug"]


def test_observer_exerciser_rows_and_end():
    class Ex:
        collisions = [{"t": 2.0, "with": "a1", "how": "lane", "xy": (10.0, 0.0)}]
        violations = []
        tick = 30
    ob = O.Observer()
    assert [(f["kind"], f["other"], f["k"]) for f in ob.new(Ex())] == [("collision", "a1", 20)]
    assert ob.end({}, {"standing": "pass", "fails": []}) == []
    e = ob.end({}, {"standing": "fail", "fails": ["not arrived"]})
    assert e[0]["kind"] == "end" and "not arrived" in e[0]["words"]


def _need_live():
    try:
        import metis_agent.runtime.run  # noqa: F401
        from metis_agent.runtime.feed import RuntimeFeed  # noqa: F401
    except ImportError as e:
        pytest.skip("the Live's venv with metis_agent.runtime (metis-agent claude-plugin): %s" % e)
    if not os.environ.get("METIS_HOME"):
        pytest.skip("METIS_HOME: the road family")


class StubFeed:
    def __init__(self):
        self.calls = []

    def __getattr__(self, name):
        return lambda *a, **k: self.calls.append((name, a, k))


def test_road_host_under_the_run_loop(tmp_path):
    _need_live()
    import host as H
    from metis_agent.runtime.run import Run
    seen = []

    class Probe(H.RoadHost):
        def findings(self, live, k):
            seen.append((k, self.world.tick, live.tracer.k - 1))
            return super().findings(live, k)
    h = Probe("cruise", 1, world_kind=None)
    feed = StubFeed()
    out = Run(tmp_path / "ws", h, feed).go(H.road_config(1), 30, "cruise-1")
    assert out["reason"] == "done", out
    assert seen and all(k == wt == tk for k, wt, tk in seen), seen[:5]          # the world's tick is the trace's
    tdir = tmp_path / "ws" / ".metis" / "traces" / out["run"]
    assert (tdir / "config.yaml").is_file() and list(tdir.glob("seg-*.jsonl"))
    assert [c[0] for c in feed.calls][0] == "run_started" and feed.calls[-1][0] == "run_ended"
    assert os.environ.get("METIS_ROAD_RUN") != str(h.tmp / "run.json")             # the run's spec file not left behind
    import road_host
    assert h.key not in road_host.SHARED                                       # the world shut, its slot freed


def _runner(ws, args, timeout):
    from metis_agent.runtime.client import RuntimeClient
    got = []
    c = RuntimeClient(ws, "plugin:test", on_signal=got.append, poll=0.1)
    c.connect("road")                                                          # by name, before the runtime exists
    try:
        p = subprocess.run([sys.executable, str(ROAD / "runner" / "road_runner.py"), "--workspace", str(ws), "--linger", "2"]
                           + args, capture_output=True, text=True, timeout=timeout, cwd=str(ROAD.parent))
        end = time.time() + 10
        while time.time() < end and not any(s.get("type") == "run.ended" for s in got):
            time.sleep(0.1)
    finally:
        c.close()
    return p, got


def test_the_runner_on_the_exerciser_by_name(tmp_path):
    _need_live()
    ws = tmp_path / "ws"
    p, got = _runner(ws, ["--scenario", "cruise", "--host", "exerciser", "--ticks", "40"], 300)
    assert p.returncode == 0, p.stderr[-2000:]
    rows = [json.loads(l) for l in p.stdout.splitlines() if l.startswith("{")]
    run = rows[0]["run"]
    assert rows[0]["reason"] == "done" and rows[-1] == {"done": True, "runs": [run]}
    types = [s["type"] for s in got if s.get("type") not in ("status",)]
    assert "runtime.attached" in types and types.index("run.started") < types.index("run.ended")
    assert (ws / ".metis" / "traces" / run / "config.yaml").is_file()
    assert not (ws / ".metis" / "runtimes" / "road.json").exists()             # removed after the linger


def test_a_card_that_cannot_be_run_is_said(tmp_path):
    _need_live()
    p = subprocess.run([sys.executable, str(ROAD / "runner" / "road_runner.py"), "--workspace", str(tmp_path / "ws"),
                        "--linger", "0", "--card", "NoSuchCard"], capture_output=True, text=True, timeout=120, cwd=str(ROAD.parent))
    assert p.returncode == 1
    row = json.loads(p.stdout.splitlines()[0])
    assert row["reason"] == "error" and "no card NoSuchCard" in row["error"]


@pytest.mark.skipif(not (os.environ.get("RUNNER_SUMO") and shutil.which("sumo")), reason="RUNNER_SUMO=1 and sumo")
def test_a_sumo_card_its_findings_signalled(tmp_path):
    _need_live()
    ws = tmp_path / "ws"
    p, got = _runner(ws, ["--card", "FollowLeadingVehicle"], 1200)
    assert p.returncode == 0, p.stderr[-2000:]
    types = [s["type"] for s in got]
    news = [s for s in got if s["type"] == "surprise.new"]
    assert news and types.index("surprise.new") < types.index("run.ended")
    from metis.catalog import workspace as W
    w = W.workspace(str(ws))
    for s in news:
        rec = w.surprise(s["id"])
        assert rec["member"] and rec["trace"].startswith("traces/") and s["key"].startswith(s["run"] + ":")


def test_a_term_stops_the_run_and_cleans_up(tmp_path):
    _need_live()
    import signal as SIG
    ws = tmp_path / "ws"
    p = subprocess.Popen([sys.executable, str(ROAD / "runner" / "road_runner.py"), "--workspace", str(ws), "--linger", "30",
                          "--scenario", "cruise", "--host", "exerciser", "--ticks", "100000"], stdout=subprocess.PIPE,
                         stderr=subprocess.PIPE, text=True, cwd=str(ROAD.parent))
    disc = ws / ".metis" / "runtimes" / "road.json"
    end = time.time() + 120                                                    # until the run is under way
    while time.time() < end and not (disc.is_file() and list(ws.glob(".metis/traces/cruise-1-*/seg-*.jsonl"))):
        time.sleep(0.2)
    assert disc.is_file()
    p.send_signal(SIG.SIGTERM)
    out, err = p.communicate(timeout=60)
    rows = [json.loads(l) for l in out.splitlines() if l.startswith("{")]
    assert rows[0]["reason"] == "stopped", (rows, err[-1500:])
    assert not disc.exists()                                                   # no linger after a stop: the file gone
