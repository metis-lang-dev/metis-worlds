"""The bundle (alf-bundle s-b53cc7ab): domains/hier/ as the workspace's one composition, in the road's shape. No game data:
its sources are the generator's, its tree bases are the plain ones through tree_base (the one copy of the rules), the
workspace face reads it, and metisc links it to image.golden."""
import os
import shutil
import subprocess
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "world"))
import gen_hier  # noqa: E402

HIER = os.path.join(ROOT, "domains", "hier")
PKGS = os.path.dirname(os.path.dirname(ROOT))
METISC = os.environ.get("METISC") or os.path.join(PKGS, "metis-lang", "src", "metisc")


def test_the_bundle_is_what_the_generator_writes():
    assert gen_hier.write(gen_hier.bundle_files(), HIER, check=True) == []


def test_the_tree_bases_are_the_room_trees_from_the_one_copy_of_the_rules():
    """Derived, never committed: the plain base through tree_base is the tree base a tree install writes (the room tree)."""
    snap = os.path.join(ROOT, "tests", ".room_tree", "domains", "hier")
    for name, text in gen_hier.tree_bases().items():
        body = text.split("\n", 1)[1].replace('include "../iface/alfworld.llp".', 'include "iface/alfworld.llp".')
        assert body == open(os.path.join(snap, name)).read(), name
    assert "domains/hier/tree/" in open(os.path.join(ROOT, ".gitignore")).read().split()


def test_every_member_is_a_package_with_the_lint_lines():
    import yaml
    comp = yaml.safe_load(open(os.path.join(HIER, "composition.yaml")))
    assert comp["name"] == "alfworld" and comp["direct"] == "director" and comp["response"] == 2
    assert comp["specialists"] == ["task", "nav", "access", "grasp", "place"]
    for m in [comp["direct"]] + comp["specialists"]:
        y = yaml.safe_load(open(os.path.join(HIER, m, "domain.yaml")))
        assert os.path.isfile(os.path.join(HIER, m, y["program"])), m
        assert y["safety"] == [] and y["belief"] == [], m
        assert ("commands" in y) == (m not in ("task", "director")), m


def test_the_workspace_face_reads_the_bundle():
    ws = pytest.importorskip("metis.catalog.workspace")
    b = ws.Workspace(ROOT).bundle()
    assert b["name"] == "alfworld" and b["composition"] == "domains/hier/composition.yaml"
    assert b["members"] == ["director", "task", "nav", "access", "grasp", "place"]
    assert b["golden"] == open(os.path.join(HIER, "image.golden")).read().strip()


@pytest.mark.skipif(not os.path.exists(METISC), reason="no metisc")
def test_make_links_the_bundle_to_its_golden(tmp_path):
    """A copy of the bundle (the bases it includes beside it) derives its tree and links to image.golden."""
    dom = tmp_path / "domains"
    shutil.copytree(os.path.join(ROOT, "domains"), dom, ignore=shutil.ignore_patterns("build", "tree", "__pycache__"))
    shutil.copytree(os.path.join(ROOT, "world"), tmp_path / "world", ignore=shutil.ignore_patterns("__pycache__"))
    env = dict(os.environ, METIS_HOME=os.path.join(PKGS, "metispy", "metis", "catalog"))
    r = subprocess.run(["make", "-s", "METISC=" + METISC, "PYTHON=" + sys.executable], cwd=dom / "hier", env=env,
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr
    assert "image alfworld v-%s" % open(os.path.join(HIER, "image.golden")).read().strip() in r.stdout
