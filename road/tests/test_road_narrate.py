"""road_narrate (metis-plugin s-df4ff191 step 4): the road page's own narration of a window of its trace, every member in its rules'
own %% words (the protocol's wordless rules and the director left out), and the catalog watch by content (the domains and the family,
never .metis/, a build dir, the cases or the intent files)."""
import os
import shutil
import sys
from pathlib import Path

import pytest

ROAD = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROAD / "world"))
import road_narrate as N  # noqa: E402

VTRACE = "/bigdata/work/bond/road/vtrace/red_light"
FAMILY = os.environ.get("METIS_HOME") or str(ROAD.parents[1] / "metis-catalog" / "domains" / "road")


@pytest.fixture
def root(tmp_path, monkeypatch):
    if not os.path.isdir(VTRACE) or not os.path.isdir(FAMILY):
        pytest.skip("a RoadDomain trace and the road family are needed")
    r = tmp_path / "road"
    r.mkdir()
    shutil.copytree(ROAD / "domains", r / "domains", ignore=shutil.ignore_patterns("build", "__pycache__"))   # the catalog follows no symlink
    shutil.copytree(VTRACE, r / ".metis" / "traces" / "run1")
    monkeypatch.setenv("METIS_HOME", FAMILY)
    monkeypatch.setenv("METIS_CATALOG", str(r))
    return r


def test_narrate_a_window_in_the_rules_words(root):
    out = N.narrate(root, "run1", 0, 199)
    assert "signals" in out["members"] and "road_director" not in out["members"]
    said = " ".join(out["members"]["signals"])
    assert "The light ahead is red: I stop before its line." in said
    assert not any("decide" in x or "back" == x for ls in out["members"].values() for x in ls)


def test_narrate_refusals_and_nothing_fired(root):
    with pytest.raises(ValueError):
        N.narrate(root, "../etc", 0, 1)
    with pytest.raises(ValueError):
        N.narrate(root, "nope", 0, 1)
    assert N.narrate(root, "run1", 5000, 5001)["text"].startswith("Nothing my rules have words for fired")


def test_the_catalog_watch_by_content(tmp_path):
    (tmp_path / "domains" / "planner" / "cases").mkdir(parents=True)
    (tmp_path / "domains" / "planner" / "planner.llp").write_text("a\n")
    (tmp_path / "domains" / "planner" / "cases" / "c.yaml").write_text("x: 1\n")
    fam = tmp_path / "fam"
    fam.mkdir()
    (fam / "planner_domain.llp").write_text("f\n")
    s0 = N.snapshot(N.catalog_files(tmp_path, fam))
    assert len(s0) == 2                                              # the case is not the catalog's behaviour
    (fam / "planner_domain.llp").write_text("f\n")                   # rewritten, unchanged: no change
    assert N.changed(s0, N.snapshot(N.catalog_files(tmp_path, fam))) == []
    (fam / "planner_domain.llp").write_text("g\n")
    moved = N.changed(s0, N.snapshot(N.catalog_files(tmp_path, fam)))
    assert N.rel(moved, tmp_path, fam) == ["family:planner_domain.llp"]


def test_the_host_files_are_the_world_models_code():
    fs = N.host_files(ROAD / "world")
    names = {f.name for f in fs}
    assert "road_facts.py" in names and "road_host.py" in names and all(f.suffix == ".py" for f in fs)
