"""The task's fetch under the one-tick instrument (spec16 s-b12d90f2 step 3, part 2; metis-lang spec/16): the world model
(domains/hier/task/eval/), the fetch query, the fetch_risk level, in both forms (today's go_for @w look; the certified
decision on a belief level with static weights). Needs metispy's metis.kernel.evaluate; METISC (a metisc beside, or
the env var) adds the parity with metisc --evaluate, listing for listing."""
import io
import os
import subprocess
import sys
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

import pytest

E = pytest.importorskip("metis.kernel.evaluate")

ALF = Path(__file__).resolve().parents[1]
EVAL = ALF / "domains" / "hier" / "task" / "eval"
CASES = sorted(p.stem for p in (EVAL / "cases").glob("*.yaml"))
METISC = Path(os.environ.get("METISC") or ALF.parents[1] / "metis-lang" / "src" / "metisc")


def listing(case, *flags):
    out, err = io.StringIO(), io.StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        rc = E.main(["cases/%s.yaml" % case, *flags])
    return out.getvalue() + err.getvalue() + "rc %d\n" % rc


def test_the_generated_files_are_current():
    r = subprocess.run([sys.executable, "world/gen_eval.py", "--check"], cwd=ALF, capture_output=True, text=True)
    assert r.returncode == 0, r.stderr


@pytest.mark.parametrize("case", CASES)
def test_the_fetch_risk_is_the_golden_and_brute_agrees(case, monkeypatch):
    monkeypatch.chdir(EVAL)
    got = listing(case)
    assert got == (EVAL / "goldens" / ("%s.txt" % case)).read_text()
    exact = [l.split(" worlds ")[0] for l in got.splitlines() if l.startswith("V ") and " = " in l]
    brute = {l.split(" worlds ")[0] for l in listing(case, "--brute").splitlines() if l.startswith("V ")}
    assert len(exact) == 2 and all(v in brute for v in exact)
    assert sum(l.startswith("L fetch_risk(") for l in got.splitlines()) == 1


@pytest.mark.parametrize("case", CASES)
def test_the_decision_never_reads_the_truth(case, monkeypatch):
    # spec/16 §3's honest form: the belief fact (truly) is read by the world's rules only, never by the task's
    monkeypatch.chdir(EVAL)
    notes = [l.split()[2] for l in listing(case).splitlines() if l.startswith("N belief-read")]
    assert notes and all(r.startswith("w_") for r in notes)


@pytest.mark.parametrize("case", [c for c in CASES if c.endswith("_level")])
def test_the_level_forms_place_levels_are_the_instruments(case, monkeypatch):
    # the case's init carries the host's place_level atoms; the instrument's level port gives the same, from the belief
    monkeypatch.chdir(EVAL)
    init = (EVAL / "cases" / ("%s.yaml" % case)).read_text().split("init: [", 1)[1].split("]\n", 1)[0]
    given = {a.replace(" ", "") for a in init.replace("), ", ")|").split("|") if a.startswith("place_level(")}
    derived = {l[2:] for l in listing(case).splitlines() if l.startswith("L place_level(") and ",target," in l}
    assert given and given == derived


@pytest.mark.skipif(not METISC.is_file(), reason="no metisc beside metis-worlds (metis-lang/src/metisc) or METISC")
@pytest.mark.parametrize("case", CASES)
def test_metisc_gives_the_same_listing(case, monkeypatch):
    monkeypatch.chdir(EVAL)
    for flags in ([], ["--brute"]):
        r = subprocess.run([str(METISC), "--evaluate", "cases/%s.yaml" % case, *flags], cwd=EVAL, capture_output=True, text=True)
        assert r.stdout + r.stderr + "rc %d\n" % r.returncode == listing(case, *flags)
