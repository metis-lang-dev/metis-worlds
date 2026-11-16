"""road/runtime (metis-plugin s-df4ff191 v3: the headless road runtime, SURPRISE-INTERFACE.md v1.1).

- the observer on a fake world: collisions merged as the Leaderboard does, violations, the windows clamped at the flush,
  the end's event always and its surprise only when the card's checks fail;
- the runtime over the exerciser (no SUMO): discovery + token + exclusivity (409 naming the holder), run.request
  refusals in words, a run's signals in order (run.started answers the request, run.ended reason done), run.stop;
- one SUMO card end to end (RUNTIME_SUMO=1 and sumo on PATH): its finding written into the workspace before its
  surprise.new, the key de-duplicating a second drop.
Needs the Live's venv (metis_agent, aiohttp) and METIS_HOME for the runtime tests; skipped otherwise."""
import asyncio
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

import pytest

ROAD = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROAD / "runtime"))
import observer as O  # noqa: E402


class FakeWorld:
    def __init__(self):
        self.collisions, self.violations, self.tick = [], [], 0


class FakeLoop:                                   # sumo_host.Loop's shape: .world.collisions, .violations, .tick
    def __init__(self):
        self.world, self.violations, self.tick = FakeWorld(), [], 0


class Sink:
    def __init__(self):
        self.s, self.e = [], []

    def surprise(self, b):
        self.s.append(b)
        return b

    def event(self, b):
        self.e.append(b)


def test_observer_collisions_merged_and_violations():
    lp, sink = FakeLoop(), Sink()
    ob = O.Observer(None, sink, "r", "card:X", 1)
    for k in range(1, 200):
        lp.tick = k
        if k in (50, 51, 52):                         # SUMO reports a contact every step it lasts: one event
            lp.world.collisions.append({"t": k * 0.1, "collider": "ego", "victim": "car7", "type": "collision"})
        if k == 120:                                  # the same other again, 7 s later: a second event
            lp.world.collisions.append({"t": k * 0.1, "collider": "car7", "victim": "ego"})
        if k == 60:
            lp.world.collisions.append({"t": 6.0, "collider": "car1", "victim": "car2"})    # not the ego's
        if k == 90:
            lp.violations.append({"tick": 90, "what": "a lane change into it", "pair": "car3:same_dir"})
        ob.tick(lp)
    assert sink.s == []                               # nothing posted before the flush (the trace not closed yet)
    assert ob.counts() == {"collision": 2, "violation": 1}
    out = ob.flush(199)
    assert [b["kind"] for b in out] == ["collision", "violation", "collision"]
    assert out[0]["tick"] == 500 // 10 and out[0]["window"] == [10, 60] and out[0]["other"] == "car7"
    assert out[1]["window"] == [50, 100] and "lane change" in out[1]["words"]
    assert all(0 <= b["window"][0] <= b["window"][1] <= 199 for b in out)


def test_observer_exerciser_rows_and_end():
    class Ex:                                         # the exerciser's RoadWorld: its own collisions, `with`
        collisions = [{"t": 2.0, "with": "a1", "how": "lane", "xy": (10.0, 0.0)}]
        violations = []
        tick = 30
    sink = Sink()
    ob = O.Observer(None, sink, "r", "cruise", 1)
    ob.tick(Ex())
    ob.end({"arrived": True, "collisions": 1, "violations": 0}, {"standing": "pass", "fails": []})
    ob.end({"arrived": False}, {"standing": "fail", "fails": ["not arrived"]})
    out = ob.flush(25)                                # the window clamped to the run
    assert len(sink.e) == 2 and sink.e[0]["edge"] == "end"
    assert [b["kind"] for b in out] == ["collision", "end"] and out[0]["other"] == "a1"
    assert out[1]["standing"] == "fail" and out[1]["window"][1] == 25


# ── the runtime ──
LIVE = shutil.which("python") and os.environ.get("METIS_HOME")


def _need_live():
    try:
        import aiohttp  # noqa: F401
        import metis_agent  # noqa: F401
        from metis.catalog import workspace  # noqa: F401
    except ImportError as e:
        pytest.skip("the Live's venv: %s" % e)
    if not os.environ.get("METIS_HOME"):
        pytest.skip("METIS_HOME: the road family")


class Runtime:
    def __init__(self, ws):
        self.ws = ws
        self.p = subprocess.Popen([sys.executable, str(ROAD / "runtime" / "road_runtime.py"), "--workspace", str(ws)],
                                  stdout=subprocess.PIPE, text=True)
        ready = json.loads(self.p.stdout.readline())
        self.disc = Path(ready["discovery"])
        self.info = json.loads(self.disc.read_text())

    def close(self):
        self.p.terminate()
        self.p.wait(15)


@pytest.fixture
def runtime(tmp_path):
    _need_live()
    r = Runtime(tmp_path / "ws")
    yield r
    r.close()
    assert not r.disc.exists()                        # removed at its exit


def test_runtime_discovery_and_refusals(runtime):
    import aiohttp
    info = runtime.info
    assert info["domain"] == "road" and info["protocol"] == 1 and info["pid"] == runtime.p.pid

    async def go():
        H = {"Authorization": "Bearer " + info["token"], "X-Metis-From": "plugin:a"}
        async with aiohttp.ClientSession() as s:
            async with s.post(info["url"] + "/signal", json={"v": 1, "type": "hello"}) as r:
                assert r.status == 401
            ws = await s.ws_connect(info["url"] + "/feed", headers=H)
            hello = await ws.receive_json()
            assert hello["type"] == "hello" and "card" in hello["spec_keys"] and hello["capabilities"] == ["run", "stop"]
            async with s.post(info["url"] + "/signal", headers=dict(H, **{"X-Metis-From": "plugin:b"}),
                              json={"v": 1, "type": "hello"}) as r:
                assert r.status == 409 and "attached to plugin:a" in (await r.json())["error"]
            for spec, words in (({}, "spec.card"), ({"scenario": "cruise", "colour": "red"}, "unknown keys colour")):
                async with s.post(info["url"] + "/signal", headers=H, json={"v": 1, "type": "run.request", "id": "x",
                                                                            "spec": spec}) as r:
                    assert r.status == 400 and words in (await r.json())["error"]
            async with s.post(info["url"] + "/signal", headers=H, json={"v": 2, "type": "hello"}) as r:
                assert r.status == 400 and "protocol" in (await r.json())["error"]
            async with s.post(info["url"] + "/signal", headers=H, json={"v": 1, "type": "some.future"}) as r:
                assert r.status == 200 and (await r.json())["ignored"] == "some.future"
            await ws.close()
            await asyncio.sleep(0.2)                  # released: another plugin may attach now
            async with s.post(info["url"] + "/signal", headers=dict(H, **{"X-Metis-From": "plugin:b"}),
                              json={"v": 1, "type": "hello"}) as r:
                assert r.status == 200
    asyncio.run(go())


def _run(info, spec, stop_after=None, timeout=300):
    import aiohttp

    async def go():
        got, stop_on = [], stop_after
        H = {"Authorization": "Bearer " + info["token"], "X-Metis-From": "plugin:t"}
        async with aiohttp.ClientSession() as s:
            ws = await s.ws_connect(info["url"] + "/feed", headers=H)
            async with s.post(info["url"] + "/signal", headers=H, json={"v": 1, "type": "run.request", "id": "q1",
                                                                        "spec": spec}) as r:
                assert r.status == 200, await r.text()
            async with s.post(info["url"] + "/signal", headers=H, json={"v": 1, "type": "run.request", "id": "q2",
                                                                        "spec": spec}) as r:
                assert r.status == 409 and "one run at a time" in (await r.json())["error"]
            t0 = time.time()
            while time.time() - t0 < timeout:
                m = await ws.receive_json(timeout=timeout)
                got.append(m)
                if stop_on and m["type"] == stop_on:
                    async with s.post(info["url"] + "/signal", headers=H, json={"v": 1, "type": "run.stop", "id": "s1"}) as r:
                        assert r.status == 200
                    stop_on = None
                if m["type"] == "run.ended":
                    break
            await ws.close()
        return got
    return asyncio.run(go())


def test_runtime_runs_a_scenario(runtime):
    got = _run(runtime.info, {"scenario": "cruise", "host": "exerciser", "ticks": 60})
    types = [m["type"] for m in got if m["type"] not in ("status", "hello")]
    assert types[0] == "run.started" and types[-1] == "run.ended" and "event.new" in types
    st, end = got[[m["type"] for m in got].index("run.started")], got[-1]
    assert st["request"] == "q1" and end["request"] == "q1" and end["reason"] == "done"
    run = st["run"]
    assert (runtime.ws / ".metis" / "traces" / run / "config.yaml").is_file()       # the judge's replay config beside it
    seqs = [m["seq"] for m in got if m["seq"]]
    assert seqs == sorted(seqs)


def test_runtime_stop(runtime):
    got = _run(runtime.info, {"scenario": "cruise", "host": "exerciser", "ticks": 3000}, stop_after="run.started")
    assert got[-1]["type"] == "run.ended" and got[-1]["reason"] == "stopped"


@pytest.mark.skipif(not (os.environ.get("RUNTIME_SUMO") and shutil.which("sumo")), reason="RUNTIME_SUMO=1 and sumo")
def test_runtime_sumo_card_writes_then_signals(runtime):
    got = _run(runtime.info, {"card": "FollowLeadingVehicle", "host": "sumo"}, timeout=900)
    news = [m for m in got if m["type"] == "surprise.new"]
    assert got[-1]["reason"] == "done"
    from metis.catalog import workspace as W
    ws = W.workspace(str(runtime.ws))
    for m in news:                                    # written first: the record and its kept window are on disk
        assert (runtime.ws / m["ref"]).is_file() and m["key"].startswith(got[-1]["run"] + ":")
        rec = ws.surprise(m["id"])
        assert rec["member"] and rec["trace"].startswith("traces/")
        assert ws.drop_surprise(dict(rec, id=None), who="world", key=m["key"]) == m["id"]   # one surprise by two paths
