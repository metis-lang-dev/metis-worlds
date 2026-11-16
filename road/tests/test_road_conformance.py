"""The road UI service's EMBEDDED runtime passes the runtime CONFORMANCE check (metis-agent py/tests/runtime_conformance.py,
RUNTIME-INTERFACE v1.5 §7): the same check as the Run loop's. The adapter drives road_host's embedding as its service does: its frames
(run_started at a scenario start, tick, segment_closed), the kernel watch hook for a host finding, a page mark, the scenario's end.
The service's ONE trace is a recorded RoadDomain run (bond003's road3_parked_in_lane, k 0..399, checkpoints every 200)."""
import os
import shutil
import sys
import time
from pathlib import Path
from types import SimpleNamespace

import pytest

ROAD = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROAD / "world"))
TRACE = "/bigdata/work/bond003/runs/road3_parked_in_lane/road_trace"
AGENT_TESTS = ROAD.parents[1] / "metis-agent" / "py" / "tests"


class RoadAdapter:
    """road_host's embedding over a stub host (its run and shared, as RoadHost.metis_frames reads them)."""
    every = 200

    def __init__(self, H, root):
        self.H, self.root = H, Path(root)
        self.host = SimpleNamespace(run={"trace": str(self.root / ".metis" / "traces" / "svc"), "scenario": "conf", "seed": 1},
                                    shared={})
        self.k = 0
        self.live = SimpleNamespace(on_finding=None)        # the service's Live (its watch hook), a stand-in
        import metis_agent.service as S
        S.Live.current = self.live
        self.feed = H.runtime_feed()

    def frame(self):
        self.H.RoadHost.metis_frames(self.host)

    def start(self, stem):
        self.host.shared["scenario_start"] = {"scenario": stem, "seed": 1, "at": time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())}
        self.frame()
        return self.H.FEED["run"]

    def advance(self, ticks):
        for _ in range(int(ticks)):
            self.k += 1
            self.host.shared["k"] = self.k
            self.frame()

    def plant(self, kind, k, words):
        self.live.on_finding({"kind": kind, "k": k, "words": words, "member": "planner"})

    def mark(self, k0, k1, words):
        self.H.page_mark({"run": "svc", "window": [k0, k1], "n": 1, "words": words, "member": "planner"})

    def end(self):
        self.H.end_run(self.host.shared, "done")


@pytest.fixture
def H(tmp_path, monkeypatch):
    try:
        import metis_agent.runtime.feed  # noqa: F401
        from metis.catalog import workspace as W
        assert hasattr(W.Workspace, "drop_window")
    except (ImportError, AssertionError):
        pytest.skip("metis-agent's runtime package and metispy's drop_window are needed")
    if not os.path.isdir(TRACE) or not (AGENT_TESTS / "runtime_conformance.py").is_file():
        pytest.skip("the recorded trace and metis-agent's conformance check are needed")
    root = tmp_path / "road"
    (root / "domains").mkdir(parents=True)
    shutil.copytree(TRACE, root / ".metis" / "traces" / "svc")
    monkeypatch.setenv("METIS_CATALOG", str(root))
    monkeypatch.setenv("METIS_RUNTIME_NAME", "road-ui-conf")
    sys.path.insert(0, str(AGENT_TESTS))
    import road_host
    road_host.RUNTIME_NAME = "road-ui-conf"
    for d in (road_host.FEED, road_host.IDE):
        d.clear()
    yield road_host, root
    road_host.stop_runtime()
    if road_host.IDE.get("client"):
        road_host.IDE["client"].stop()
    for d in (road_host.FEED, road_host.IDE):
        d.clear()


def test_the_road_ui_embedding_conforms(H):
    road_host, root = H
    from runtime_conformance import check
    a = RoadAdapter(road_host, root)
    out = check(a, root)
    assert len(out["runs"]) == 2 and out["runs"][0] != out["runs"][1]
