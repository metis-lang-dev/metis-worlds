"""The road UI's service EMBEDS the generic runtime (metis-plugin s-df4ff191, RUNTIME-INTERFACE v1.5): a page mark is written at once
through the runtime (finding now=True: the SDK's drop_window under the page mark's key) and said on its feed; the page's explain goes by
the route rule (an /ide pairing, else the feed's clients, else words); a client's feedback reaches the page ONCE."""
import os
import shutil
import sys
from pathlib import Path

import pytest

ROAD = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROAD / "world"))
VTRACE = "/bigdata/work/bond/road/vtrace/red_light"


@pytest.fixture
def H(tmp_path, monkeypatch):
    try:
        import metis_agent.runtime.feed  # noqa: F401
        from metis.catalog import workspace as W
        assert hasattr(W.Workspace, "drop_window")
    except (ImportError, AssertionError):
        pytest.skip("metis-agent's runtime package and metispy's drop_window are needed")
    if not os.path.isdir(VTRACE):
        pytest.skip("a RoadDomain trace is needed")
    root = tmp_path / "road"
    (root / "domains").mkdir(parents=True)
    shutil.copytree(VTRACE, root / ".metis" / "traces" / "run1")
    monkeypatch.setenv("METIS_CATALOG", str(root))
    import road_host
    for d in (road_host.FEED, road_host.IDE):
        d.clear()
    yield road_host
    road_host.stop_runtime()
    if road_host.IDE.get("client"):
        road_host.IDE["client"].stop()
    for d in (road_host.FEED, road_host.IDE):
        d.clear()


def test_a_page_mark_is_written_at_once_and_said_on_the_feed(H):
    r = H.page_mark({"run": "run1", "window": [10, 30], "n": 1, "words": "late for the red light", "member": "signals", "scenario": "red_light"})
    assert r["key"] == "run1:mark:1:10-30" and r["signalled"] is False
    feed = H.runtime_feed()
    new = [s for s in feed.after(0) if s["type"] == "surprise.new"]
    assert [s["id"] for s in new] == [r["id"]] and new[0]["key"] == r["key"]
    assert feed.ws.surprise(r["id"])["page"]["scenario"] == "red_light"
    again = H.page_mark({"run": "run1", "window": [10, 30], "n": 1, "words": "again", "member": "signals"})
    assert again["id"] == r["id"]                                   # one finding, one surprise


def test_explain_by_the_route_rule(H):
    with pytest.raises(ValueError, match="no Claude Code is attached"):
        H.page_request({"run": "run1", "k0": 10, "k1": 30}, "why?")
    feed = H.runtime_feed()
    feed.signal_in({"type": "hello", "from": "plugin:1"})           # a plugin attached by /connect-runtime road-ui
    r = H.page_request({"run": "run1", "k0": 10, "k1": 30}, "why so late?")
    assert r["via"] == "runtime" and any(s["type"] == "explain.request" and s["id"] == r["id"] for s in feed.after(0))


def test_a_clients_feedback_reaches_the_page_once(H):
    feed = H.runtime_feed()
    feed.signal_in({"type": "hello", "from": "plugin:1"})
    feed.signal_in({"type": "surprise.ruled", "from": "plugin:1", "id": "S1", "verdict": "accepted", "seq": 5})
    first = H.feedback()
    assert [m["type"] for m in first] == ["surprise.ruled"] and first[0]["id"] == "S1"
    assert H.feedback() == []                                       # read once
    H.IDE["client"] = type("I", (), {"take": lambda self: [{"type": "surprise.ruled", "id": "S1", "verdict": "accepted"}],
                                     "status": lambda self: {"connected": True}})()
    assert H.feedback() == []                                       # the same signal by the /ide path: not twice
    H.IDE.clear()
    assert H.attached() is True


def test_the_kernel_watch_hook_queues_its_findings_on_the_trace(H, monkeypatch):
    """bond004's hook (service.Live.current.on_finding): the embedding sets it, a watch surprise becomes a finding under the service's
    TRACE (not the scenario run's name), queued, then written when its window is on disk (segment_closed)."""
    import metis_agent.service as S
    live = type("L", (), {"on_finding": None})()
    monkeypatch.setattr(S.Live, "current", live, raising=False)
    feed = H.runtime_feed()
    H.FEED["trace"] = "run1"
    H.watch_hook(feed)
    assert live.on_finding is not None
    live.on_finding({"kind": "watch", "k": 20, "member": "signals", "words": "the light read red where it was amber"})
    assert not [s for s in feed.after(0) if s["type"] == "surprise.new"]          # queued: its window not closed yet
    feed.segment_closed(199)
    new = [s for s in feed.after(0) if s["type"] == "surprise.new"]
    assert new and new[0]["kind"] == "watch" and feed.ws.surprise(new[0]["id"])["trace"].startswith("traces/run1-")
