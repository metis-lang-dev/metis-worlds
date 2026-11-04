"""The bundle (alf-bundle s-b53cc7ab): domains/hier/ as the workspace's one composition, in the road's shape. No game data:
its sources are the generator's, its tree bases are committed (the one copy of the rules, the one that runs: A3 ruling
B) with the protocol's cancels as one marked block, the plain bases derive from them and back, the workspace face reads
it, and metisc links it to image.golden."""
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


def test_the_tree_bases_are_committed_and_are_the_room_trees():
    """The committed tree bases are what a tree install runs: the room tree's snapshot, byte for byte."""
    from metis.catalog import protocol_stub
    snap = os.path.join(ROOT, "tests", ".room_tree", "domains", "hier")
    for spec in gen_hier.SPECS:
        text = open(os.path.join(HIER, spec + "_domain.llp")).read()
        assert not text.startswith("% DERIVED"), spec
        assert text.count(protocol_stub.BEGIN) == 1 and text.count(protocol_stub.END) == 1, spec
        assert text == open(os.path.join(snap, spec + "_domain.llp")).read(), spec
    ign = open(os.path.join(ROOT, ".gitignore")).read().split()
    assert "domains/hier/plain/" in ign and "domains/hier/tree/" not in ign
    assert not os.path.exists(os.path.join(HIER, "tree"))


def test_the_marked_blocks_are_as_the_stub_writes_them():
    """The cancels are generated in place (gen_hier.py stub), never edited: each block equals its rules' stub."""
    for spec in gen_hier.SPECS:
        text = open(os.path.join(HIER, spec + "_domain.llp")).read()
        assert gen_hier.stub(spec, text) == text, spec


def test_a_hand_edit_of_the_block_is_written_back_by_the_stub():
    spec = "nav"
    text = open(os.path.join(HIER, spec + "_domain.llp")).read()
    bad = text.replace("cancel_goto [dyn] : tick__cancel(nav) * busy * goto(V0) -o idle.",
                       "cancel_goto [dyn] : tick__cancel(nav) * goto(V0) -o idle.")
    assert bad != text and gen_hier.stub(spec, bad) == text


def test_the_plain_bases_round_trip():
    """tree_base(plain(T)) == T for every committed tree base T (ruling B, condition 3): the plain hierarchy is derived
    from the one copy and gives it back."""
    for spec in gen_hier.SPECS:
        t = open(os.path.join(HIER, spec + "_domain.llp")).read()
        p = gen_hier.plain(spec, t)
        assert gen_hier.tree_base(spec, p) == t, spec
        assert "tick__" not in p and "begin [dyn]" not in p and "cancel_" not in p, spec


def test_the_round_trip_names_a_rule_that_breaks_the_protocol():
    """A goal-consuming rule written without busy/idle is not what tree_base would make of its plain form."""
    t = open(os.path.join(HIER, "nav_domain.llp")).read()
    bad = t.replace(" * busy * $tick__grant(nav, motion) -o at(L2) * reached(R) * idle * tick__done(nav).",
                    " * $tick__grant(nav, motion) -o at(L2) * reached(R) * tick__done(nav).")
    assert bad != t and gen_hier.tree_base("nav", gen_hier.plain("nav", bad)) != bad


def test_the_plain_instances_include_the_derived_plain_bases():
    for spec in gen_hier.SPECS:
        t = open(os.path.join(HIER, spec, spec + "_plain.llp")).read()
        assert 'include "../plain/%s_domain.llp".' % spec in t, spec
        assert open(os.path.join(HIER, spec, spec + ".llp")).read().count('include "../%s_domain.llp".' % spec) == 1, spec


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
    """A copy of the bundle (the bases it includes beside it) derives its plain bases and links to image.golden."""
    dom = tmp_path / "domains"
    shutil.copytree(os.path.join(ROOT, "domains"), dom, ignore=shutil.ignore_patterns("build", "plain", "__pycache__"))
    shutil.copytree(os.path.join(ROOT, "world"), tmp_path / "world", ignore=shutil.ignore_patterns("__pycache__"))
    env = dict(os.environ, METIS_HOME=os.path.join(PKGS, "metispy", "metis", "catalog"))
    r = subprocess.run(["make", "-s", "METISC=" + METISC, "PYTHON=" + sys.executable], cwd=dom / "hier", env=env,
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr
    assert "image alfworld v-%s" % open(os.path.join(HIER, "image.golden")).read().strip() in r.stdout
