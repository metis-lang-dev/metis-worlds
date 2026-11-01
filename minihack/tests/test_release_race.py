"""The stale release on NLE (release-race s-c88bf623, spec/15 amendment 10): after a fight, act's grant for the door stands.
experiments/release_case.py: a newt in the lane, then a locked door. Before: the release of the fight, relayed after the way
moved, revoked the door's grant one beat after open_door, and the robot stood to the end. Needs NLE (METIS_MH_PY) and the agent."""
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent.parent
CASE = HERE / "experiments" / "release_case.py"
MH = os.environ.get("METIS_MH_PY")
pytestmark = pytest.mark.skipif(not MH or not Path(MH).exists(), reason="no NLE: METIS_MH_PY")
pytest.importorskip("metis_agent")


def run(tmp_path, **env):
    e = dict(os.environ, RACE_TIMEOUT="30", **env)
    subprocess.run([MH, str(CASE), "setup", str(tmp_path), "1"], check=True, env=e, capture_output=True)
    subprocess.run([sys.executable, str(CASE), "run", str(tmp_path), "1"], check=True, env=e, capture_output=True, timeout=120)
    res = json.loads((tmp_path / "seed1.json").read_text())
    rules = {}
    tick = 1
    for r in res["recs"]:
        if r.get("kind") == "dlg-status":
            tick = r["beat"] + 1
        elif r.get("kind") == "dlg-trace" and r.get("domain") == "director":
            for row in r.get("fired") or []:
                if row.get("kind") != "exo":
                    rules.setdefault(row["event"].split("[")[0], []).append(tick)
    return res, rules


def test_a_fight_then_a_locked_door(tmp_path):
    res, rules = run(tmp_path, RACE_NEWT_X="8")
    assert res["won"]
    assert "release_report_late" not in rules and "release_late" not in rules      # nothing revokes the door's grant
    assert rules.get("release_old")                                                # the fight's release: consumed as stale
    assert any(r.get("kind") == "dlg-relay" and r.get("what") == "stale" for r in res["recs"])
    assert any(s.get("rule", "").startswith("kick") for s in res["steps"])          # it kicks


def test_the_late_path_the_second_door(tmp_path):
    res, rules = run(tmp_path, RACE_NEWT_X="6", RACE_DOOR="closed", RACE_DOOR2_X="17", RACE_DOOR2="locked")
    assert res["won"] and any(s.get("rule", "").startswith("kick") for s in res["steps"])
    assert not [a for a in res["trace"][-1]["sessions"]["director"] if a.startswith(("late(", "late_release(", "tick__released("))]


def test_a_door_with_no_fight_before_it(tmp_path):
    res, rules = run(tmp_path, RACE_NEWT="none")
    assert res["won"] and "release_old" not in rules
