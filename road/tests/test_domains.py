"""The road domains (road/domains: the car's responder and planner over the road FAMILY's units, road_director, task,
the composition, the instrument's eval; road-family s-f62c0ed8): the family lives in metis-catalog domains/road
(road/domains/catalog.pin) and is found through METIS_HOME (road_host.family_home); the family's members' own cases pass
through the interface stub from there, the car members' generated cancels are current against the family's bases, the
traces and the lane-change risk are their goldens (metisc)."""
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROAD = Path(__file__).resolve().parents[1]            # the road's catalog root (METIS_CATALOG for the tree demo)
DOMAINS = ROAD / "domains"
METISC = Path(os.environ.get("METISC") or ROAD.parents[1] / "metis-lang" / "src" / "metisc")
sys.path.insert(0, str(ROAD / "world"))
import road_host  # noqa: E402

FAMILY = Path(road_host.family_home())                # metis-catalog domains/road (catalog.pin)


def env():
    """metisc's environment: METIS_HOME = the family (the units by name); metisc still finds its own standard units
    (iface/: the protocol and the tree director; metis-lang spec/17 amendment 5) beside it."""
    return {**os.environ, "METIS_HOME": str(FAMILY)}


needs_metisc = pytest.mark.skipif(not METISC.is_file(), reason="no metisc (METISC, else metis-lang/src/metisc beside)")


def packages():
    from metis.catalog import manifests as mc
    return mc.domains(ROAD)


def family_packages():
    from metis.catalog import manifests as mc
    return mc.domains(FAMILY.parents[1])   # the catalog root above domains/road


def test_the_road_packages_load():
    assert {d.name for d in packages()} == {"responder", "signals", "planner", "road_director", "task"}


@pytest.mark.parametrize("name", ["responder", "signals", "planner"])
def test_the_family_members_own_cases_pass_through_the_interface_stub(name):
    # the family's cases live with the family (metis-catalog domains/road/<member>/cases); the car's packages here hold
    # the host and the manifest
    from metis.catalog import stub
    d = next(d for d in family_packages() if d.name == name and d.dir.resolve().is_relative_to(FAMILY.resolve()))
    rs = stub.run_package(d)
    assert rs, "%s: cases/ holds no case" % name
    assert all(r.passed for r in rs), stub.render(rs)


@pytest.mark.parametrize("member", ["responder", "signals", "planner"])
def test_the_road_members_cancels_are_as_their_generator_writes_them(member):
    # each member base's stop stub, from metispy's protocol_stub
    from metis.catalog import protocol_stub
    text = (FAMILY / ("%s_domain.llp" % member)).read_text()
    assert protocol_stub.BEGIN in text
    assert protocol_stub.refresh(text, member, idle="idle", namespace=member,
                                 world=protocol_stub.world_private(DOMAINS / member / "domain.yaml")) == text


@needs_metisc
@pytest.mark.parametrize("name", ["responder", "planner", "road_director"])
def test_the_packages_trace_is_its_golden(name):
    # the package's `metisc --run` (metis-catalog ci/packages.py's gate, for the road's packages)
    d = next(d for d in packages() if d.name == name)
    path = d.program or d.serves()[0]
    r = subprocess.run([str(METISC), "--run", str(path)], stdin=subprocess.DEVNULL, capture_output=True, text=True,
                       env=env())
    assert r.returncode == 0, r.stderr
    golden = (DOMAINS / "goldens" if name == "road_director" else FAMILY.parents[1] / "goldens") / "traces" / ("%s.txt" % name)
    assert r.stdout == golden.read_text()   # the family's traces are the catalog's goldens, the director's this world's


@needs_metisc
@pytest.mark.parametrize("case", ["gap", "tight"])
def test_the_road_lane_change_risk_is_its_golden(case):
    # the instrument's lane-change query over the road's world model (spec/16 §10.1, tick: ego): needs a metisc of
    # metis-lang master >= 97b8749 (rows by tick)
    ev = DOMAINS / "eval"
    r = subprocess.run([str(METISC), "--evaluate", "cases/%s.yaml" % case], cwd=ev, capture_output=True, text=True, env=env())
    assert r.stdout + r.stderr + "rc %d\n" % r.returncode == (ev / "goldens" / ("%s.txt" % case)).read_text()
