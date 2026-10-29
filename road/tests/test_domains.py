"""The road domains (road/domains: responder, planner, road_director, the composition, the instrument's eval), moved
here from metis-catalog domains/road (road-move): their packages load, their own cases pass through the interface
stub, their generated cancels are current, their traces and the lane-change risk are their goldens (metisc)."""
import os
import subprocess
from pathlib import Path

import pytest

ROAD = Path(__file__).resolve().parents[1]            # the road's catalog root (METIS_CATALOG for the tree demo)
DOMAINS = ROAD / "domains"
METISC = Path(os.environ.get("METISC") or ROAD.parents[1] / "metis-lang" / "src" / "metisc")


def env():
    """metisc's environment: METIS_HOME unset, the proof that nothing need be set (metisc finds its own standard
    units, iface/: the protocol and the tree director the bases include; metis-lang spec/17 amendment 5)."""
    return {k: v for k, v in os.environ.items() if k != "METIS_HOME"}


needs_metisc = pytest.mark.skipif(not METISC.is_file(), reason="no metisc (METISC, else metis-lang/src/metisc beside)")


def packages():
    from metis.catalog import manifests as mc
    return mc.domains(ROAD)


def test_the_road_packages_load():
    assert {d.name for d in packages()} == {"responder", "planner", "road_director"}


@pytest.mark.parametrize("name", ["responder", "planner"])
def test_the_members_own_cases_pass_through_the_interface_stub(name):
    from metis.catalog import stub
    d = next(d for d in packages() if d.name == name)
    rs = stub.run_package(d)
    assert rs, "%s: cases/ holds no case" % name
    assert all(r.passed for r in rs), stub.render(rs)


@pytest.mark.parametrize("member", ["responder", "planner"])
def test_the_road_members_cancels_are_as_their_generator_writes_them(member):
    # each member base's stop stub, from metispy's protocol_stub
    from metis.catalog import protocol_stub
    text = (DOMAINS / ("%s_domain.llp" % member)).read_text()
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
    assert r.stdout == (DOMAINS / "goldens" / "traces" / ("%s.txt" % name)).read_text()


@needs_metisc
@pytest.mark.parametrize("case", ["gap", "tight"])
def test_the_road_lane_change_risk_is_its_golden(case):
    # the instrument's lane-change query over the road's world model (spec/16 §10.1, tick: ego): needs a metisc of
    # metis-lang master >= 97b8749 (rows by tick)
    ev = DOMAINS / "eval"
    r = subprocess.run([str(METISC), "--evaluate", "cases/%s.yaml" % case], cwd=ev, capture_output=True, text=True, env=env())
    assert r.stdout + r.stderr + "rc %d\n" % r.returncode == (ev / "goldens" / ("%s.txt" % case)).read_text()
