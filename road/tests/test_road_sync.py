"""The road host under the tick's latch (nina's finding, wc-member s-4fe6cfd6): Live.latch replaces a host's `reading` with a
copy taking no argument, so a host that called `self.reading(counts)` read its counts back, found no difference, and its
member fell silent after its first command. The Live half runs where metis_agent is installed (metis-agent's venv)."""
import importlib.util
import json
import os
import sys
from pathlib import Path

import pytest

ROAD = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROAD / "world"))


@pytest.fixture
def host(tmp_path, monkeypatch):
    road_host = pytest.importorskip("road_host")
    spec = tmp_path / "run.json"
    spec.write_text(json.dumps({"scenario": "cruise", "seed": 1, "key": str(spec)}))
    monkeypatch.setenv("METIS_ROAD_RUN", str(spec))
    yield road_host.RoadHost(str(ROAD / "domains" / "responder"))
    road_host.SHARED.pop(str(spec), None)


def latch(h):
    snap = h.reading()                      # as Live.latch does
    h.reading = lambda _s=snap: dict(_s)
    return snap


def test_a_latched_host_syncs_the_snapshot_not_the_counts(host):
    snap = latch(host)
    lines = host.sync({})
    assert snap and lines and all(x.startswith("+") for x in lines)     # the counts are empty, the world is not
    assert host.observe({}) == snap


def test_a_latched_host_given_its_own_counts_has_nothing_to_do(host):
    snap = latch(host)
    assert host.sync(dict(snap)) == []


@pytest.mark.skipif(importlib.util.find_spec("metis_agent") is None, reason="no metis_agent (its venv)")
def test_the_tree_goes_on_commanding_after_the_first(tmp_path, monkeypatch):
    for k in ("METIS_CATALOG", "METIS_ROAD_RUN", "METIS_ROAD_WORLD"):      # road_tree sets them: undone with the test
        monkeypatch.setenv(k, os.environ.get(k, ""))
    spec = importlib.util.spec_from_file_location("road_tree", ROAD / "experiments" / "road_tree.py")
    road_tree = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(road_tree)
    out = road_tree.run("cruise", 1, tmp_path, ticks=100)
    assert out["planner_cmds"] >= 5                   # one a clock period (10 ticks), not one a run
