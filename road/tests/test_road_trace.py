"""The road's trace (metis.trace; trace-replay s-c111ff41): a run of the tree under py Live, each member replayed alone from what it
applied, with no world and no SUMO: 0 divergences. The exerciser here; straight on SUMO with METIS_ROAD_SUMO=1 (one SUMO at a time)."""
import importlib.util
import os
from pathlib import Path

import pytest

ROAD = Path(__file__).resolve().parents[1]
pytest.importorskip("metis.trace")
pytest.importorskip("metis_agent.trace")              # the reader: road's CI runs the siblings at their heads, whichever merged first
pytestmark = pytest.mark.skipif(importlib.util.find_spec("metis_agent") is None, reason="no metis_agent (its venv)")


def road_tree():
    spec = importlib.util.spec_from_file_location("road_tree", ROAD / "experiments" / "road_tree.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def replayed(d):
    from metis import trace
    head = trace.read(d)[0].header
    assert set(head["members"]) == {"responder", "planner", "road_director"}
    assert "brake_lon" in head["commands"]
    out = {}
    for m in head["members"]:
        out[m] = trace.replay(d, m, ROAD / "domains" / m / ("%s.llp" % m))
        assert out[m].ok, (m, out[m].divergence)
    return out


@pytest.fixture
def env(monkeypatch):
    for k in ("METIS_CATALOG", "METIS_ROAD_RUN", "METIS_ROAD_WORLD"):      # road_tree sets them: undone with the test
        monkeypatch.setenv(k, os.environ.get(k, ""))


def test_a_run_on_the_exerciser_replays_with_no_world(tmp_path, env):
    road_tree().run("cruise", 1, tmp_path, ticks=250, trace=tmp_path / "t")
    r = replayed(tmp_path / "t" / "cruise-1")
    assert r["planner"].rules and r["road_director"].rules and r["planner"].out


def test_a_command_in_the_trace_is_the_restrictors_kind_and_args(tmp_path, env):
    from metis import trace
    road_tree().run("cruise", 1, tmp_path, ticks=250, trace=tmp_path / "t")
    out = [o for s in trace.read(tmp_path / "t" / "cruise-1") for t in s.ticks for o in t["members"].get("planner", {}).get("out", ())]
    cmds = [o for o in out if isinstance(o, dict)]
    assert {c["kind"] for c in cmds} >= {"accel", "keep"} and all(not c["args"] for c in cmds if c["kind"] in ("accel", "keep"))
    assert any(isinstance(o, str) and o.startswith("tick__want(planner") for o in out), "every out port, not the commands alone"


def test_a_checkpoint_says_the_runs_time(tmp_path, env):
    from metis import trace
    road_tree().run("cruise", 1, tmp_path, ticks=250, trace=tmp_path / "t")
    segs = trace.read(tmp_path / "t" / "cruise-1")
    assert len(segs) == 2 and segs[1].k0 == 200
    assert segs[1].checkpoint["world"]["scenario"] == "cruise" and segs[1].checkpoint["world"]["t"] > 0


@pytest.mark.skipif(not os.environ.get("METIS_ROAD_SUMO"), reason="METIS_ROAD_SUMO=1: straight on SUMO")
def test_straight_on_sumo_replays_with_no_sumo(tmp_path, env):
    road_tree().run("straight", 1, tmp_path, ticks=400, world_kind="sumo", vehicles=10, trace=tmp_path / "t")
    replayed(tmp_path / "t" / "straight-1")
