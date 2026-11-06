"""scenario_run (scenario-catalog s-92e0b650 step 2): the card's paths, its standing against expect, the verdict written in place,
the catalog's index; no simulator."""
import importlib.util
import json
from pathlib import Path

import yaml

ROAD = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("scenario_run", ROAD / "tools" / "scenario_run.py")
R = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(R)


def net_card(tmp_path, **kw):
    c = {"card": 2, "scenario": "ZAM_X-1_1_T-1", "map": {"net": "x/x.net.xml", "data": "x/cr.json"},
         "ego": {"goal": {"region": "data", "time": [10, 20]}}, "expect": {"goal": True}}
    c.update(kw)
    p = tmp_path / "ZAM_X-1_1_T-1.yaml"
    p.write_text(yaml.safe_dump(c))
    return R.load(p)


def test_paths_from_road_or_the_cards_dir(tmp_path):
    c = net_card(tmp_path)
    assert R.card_file(c, "catalog/commonroad/a/b.net.xml") == ROAD / "catalog/commonroad/a/b.net.xml"
    assert R.card_file(c, "x/x.net.xml") == tmp_path / "x" / "x.net.xml"
    assert R.on_net(c)


def test_the_standing_of_a_net_card(tmp_path):
    c = net_card(tmp_path)
    ok = {"failed": [], "error": None, "summary": {"director": {"cr": {"goal_edge": "e1", "route_note": None}}}, "ticks": 300}
    assert R.standing(c, ok)["status"] == "pass"
    assert R.standing(c, dict(ok, failed=["contact", "goal"]))["status"] == "fail"
    soft = dict(ok, failed=["goal"], goal={"position_t": 12.0})
    assert R.standing(c, soft)["status"] == "soft"
    assert R.standing(c, dict(ok, failed=["goal"], goal={"position_t": None}))["status"] == "fail"
    world = dict(ok, summary={"director": {"cr": {"goal_edge": "e1", "route_note": "no way from a to the goal's edge b"}}})
    assert R.standing(c, world)["status"] == "world"
    assert R.standing(c, dict(ok, error={"kind": "world", "line": "cr: no route"}))["status"] == "world"
    assert R.standing(c, dict(ok, error={"kind": "crash", "line": "x"}))["status"] == "error"


def test_the_standing_of_a_town_card(tmp_path):
    p = tmp_path / "C.yaml"
    p.write_text(yaml.safe_dump({"scenario": "C", "expect": {"arrived": True}}))
    c = R.load(p)
    assert R.standing(c, {"fails": []})["status"] == "pass"
    assert R.standing(c, {"fails": ["collisions 1 > 0"]}) == {"status": "fail", "why": "collisions 1 > 0"}


def test_the_verdict_is_written_in_place_and_read_back(tmp_path, monkeypatch):
    c = net_card(tmp_path, verdict={"status": "pass", "since": {"worlds": "0000000", "catalog": "0000000"}}, title="kept")
    monkeypatch.setattr(R, "since", lambda: {"worlds": "abc1234", "catalog": "def5678"})
    R.write_verdict(c, {"status": "soft", "why": "the window missed"}, "sumo")
    back = R.load(c["_path"])
    assert back["title"] == "kept" and back["verdict"] == {"sumo": {"status": "soft", "since": {"worlds": "abc1234", "catalog": "def5678"},
                                                                   "note": "the window missed"}}
    assert R.expected(back) == "soft" and R.expected(back, "exerciser") is None
    R.write_verdict(back, {"status": "pass"}, "exerciser")              # one host's entry kept beside the other's
    both = R.load(c["_path"])
    assert R.expected(both, "sumo") == "soft" and R.expected(both, "exerciser") == "pass"


def test_a_host_may_be_skipped(tmp_path):
    c = net_card(tmp_path, verdict={"exerciser": "skip", "sumo": {"status": "fail"}})
    assert R.skipped(c, "exerciser") and not R.skipped(c, "sumo") and R.expected(c, "sumo") == "fail"
    c2 = net_card(tmp_path, verdict={"exerciser": {"status": "skip", "note": "why"}, "sumo": {"status": "pass"}})
    assert R.skipped(c2, "exerciser")


def test_coverage_counts_tags_by_host_and_standing(tmp_path):
    net_card(tmp_path, tags=["following", "cut-in"], verdict={"exerciser": "skip", "sumo": {"status": "fail"}})
    md = R.coverage([str(tmp_path)])
    assert "| following | sumo | 0 | 0 | 1 | 0 | 0 |" in md and "| cut-in | exerciser | 0 | 0 | 0 | 0 | 1 |" in md


def test_the_index(tmp_path):
    net_card(tmp_path, tags=["following"], source={"suite": "commonroad"}, verdict={"sumo": {"status": "fail"}})

    class A:
        dir = str(tmp_path)
    R.cmd_index(A)
    rows = json.loads((tmp_path / "index.json").read_text())["cards"]
    assert rows == [{"id": "ZAM_X-1_1_T-1", "scenario": "ZAM_X-1_1_T-1", "source": "commonroad", "tags": ["following"],
                     "verdict": {"sumo": "fail"}, "map": "x/x.net.xml", "run": "cr:x", "runs": ["cr:x"]}]


def test_the_catalogs_cards_carry_their_notice_and_verdict():
    for p in sorted((ROAD / "catalog" / "commonroad").glob("*.yaml")):
        c = R.load(p)
        d = R.card_file(c, c["map"]["net"]).parent
        assert (d / "NOTICE").is_file() and "BSD" in (d / "NOTICE").read_text(), p
        assert R.card_file(c, c["map"]["net"]).is_file() and R.card_file(c, c["map"]["data"]).is_file(), p
        assert R.expected(c, "sumo") in ("pass", "soft", "fail", "world"), p
