"""ALFWorld's headless scenario runner on the generic Metis runtime (runner/alf_runner.py; metis-plugin s-df4ff191):
one run served as the named runtime, its trace in the workspace; a task that does not end done is ONE end finding,
written (drop_window) then signalled; a task that ends done raises none. On a temporary copy of the workspace (the
runner writes under .metis/); needs ALFWorld's data and venv (.worlds) and metis-agent with its runtime package."""
import json
import os
import shutil
import subprocess
import sys
import threading
from pathlib import Path

import pytest

ALF = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ALF / "runner"))
import alf_runner  # noqa: E402

W = alf_runner.worlds()
pytest.importorskip("metis_agent.runtime.feed")
pytestmark = pytest.mark.skipif(not (W / "alf" / "bin" / "python").exists() or not (W / "alfworld-data").is_dir(),
                                reason="no ALFWorld venv / data (.worlds)")


@pytest.fixture
def ws(tmp_path):
    root = tmp_path / "alfworld"
    for d in ("domains", "experiments", "world", "runner"):
        shutil.copytree(ALF / d, root / d, ignore=shutil.ignore_patterns("__pycache__", "build"))
    for f in ("README.md",):
        shutil.copy(ALF / f, root / f)
    (root / ".metis" / "traces").mkdir(parents=True)
    return root


def run(ws, *args):
    from metis_agent.runtime.client import RuntimeClient
    got = []
    c = RuntimeClient(ws, "test:alf", on_signal=got.append, poll=0.1)
    c.connect("alfworld")                                   # waits for the name, as the plugin does
    try:
        p = subprocess.run([sys.executable, str(ws / "runner" / "alf_runner.py"), "--workspace", str(ws), "--linger", "1.5",
                            "--ticks", "200", *args], capture_output=True, text=True, timeout=600, env=os.environ)
        assert p.returncode == 0, p.stderr[-3000:]
        out = json.loads(p.stdout.strip().splitlines()[-1])
        import time
        end = time.time() + 10
        while time.time() < end and not any(s.get("type") == "run.ended" for s in got):
            time.sleep(0.1)
        return out, got
    finally:
        c.close()


def test_a_task_that_does_not_end_done_is_one_end_finding(ws):
    out, got = run(ws, "--receptacle", "fridge1")          # the disengagement: the task wants the microwave
    assert out["reason"] == "done" and out["summary"]["status"]["state"] == "asking"
    new = [s for s in got if s["type"] == "surprise.new"]
    assert len(new) == 1 and new[0]["kind"] == "end" and new[0]["key"].startswith(out["run"] + ":end:task:")
    rec = json.loads((ws / new[0]["ref"]).read_text())
    assert rec["member"] == "task" and "did not end done" in rec["words"] and rec["source"] == "runtime:alfworld"
    assert (ws / ".metis" / rec["trace"]).is_dir() and (ws / ".metis" / out["trace"] / "config.yaml").is_file()
    ended = [s for s in got if s["type"] == "run.ended"][0]
    assert ended["surprises"] == [new[0]["id"]] and got.index(new[0]) < got.index(ended)       # written, signalled, then the end


def test_a_task_that_ends_done_raises_none(ws):
    out, got = run(ws)                                     # tomato -> microwave1: the game's own task
    assert out["summary"]["status"]["state"] == "over"
    assert not [s for s in got if s["type"] == "surprise.new"]
    assert any(s["type"] == "run.started" for s in got) and not list((ws / ".metis" / "surprises").glob("*.json"))
