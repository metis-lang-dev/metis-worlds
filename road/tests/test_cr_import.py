"""cr_import (scenario-catalog s-92e0b650 step 3): CommonRoad scenarios as scenario cards v2 (road/docs/SCENARIO-CARD.md) and the
selection over a triaged harvest round. The pure parts on hand-built cr.json fragments; the three-id card test runs where the
conversion cache holds them (panzer, taycann after a pull), else skips: CI has no CommonRoad data."""
import json
import os
import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "tools"))
sys.path.insert(0, str(HERE.parent / "world"))
import cr_import as I  # noqa: E402


def doc(**kw):
    d = {"id": "X", "dt": 0.1, "source": "/c/scenarios/scenarios/recorded/hand-crafted/X.xml", "tags": ["intersection", "turn_left"],
         "lights": [], "right_before_left": {}, "signs": [{"elements": [{"id": "MAX_SPEED"}]}],
         "obstacles": [{"id": 3, "type": "bicycle", "role": "dynamic", "trajectory": [{"k": 0, "x": 1, "y": 2, "theta": 0, "v": 4},
                                                                                       {"k": 1, "x": 1.4, "y": 2, "theta": 0, "v": 4}]},
                       {"id": 4, "type": "car", "role": "dynamic", "trajectory": [{"k": 0, "x": 9, "y": 2, "theta": 0, "v": 10}]},
                       {"id": 5, "type": "parkedVehicle", "role": "static", "trajectory": [{"k": 0, "x": 20, "y": 2, "theta": 0, "v": 0}]}],
         "planning": [{"initial": {"k": 10, "x": 0, "y": 0, "theta": 0, "v": 8.0},
                       "goals": [{"polygons": [], "lanelets": [77], "time": [40, 60], "velocity": [0, 5], "orientation": None}]}]}
    d.update(kw)
    return d


def test_the_scenes_tags_are_the_vocabularys():
    tags = I.scene_tags(doc())
    assert {"route-following", "junction-priority", "turning-left", "speed-limit", "cyclist", "obstacle-static"} <= tags
    assert tags <= I.VOCAB and "following" not in tags                         # a car alone is no tag
    assert "traffic-light" in I.scene_tags(doc(lights=[{"id": 1}])) and "right-before-left" in I.scene_tags(doc(right_before_left={"73": [1]}))


def test_the_goal_in_seconds_from_the_start_and_a_time_only_goal():
    g = I.goal_of(doc(), k0=10, dt=0.1)
    assert g == {"region": {"lanelets": [77]}, "time": [3.0, 5.0], "v": [0, 5]}
    t = doc()
    t["planning"][0]["goals"] = [{"polygons": [], "lanelets": [], "time": [33, 33]}]
    assert I.goal_of(t, k0=0, dt=0.1) == {"time": [3.3, 3.3]}                    # no region: time-only (§3)


def test_the_actors_by_mode():
    rec = {a["id"]: a for a in I.actors_of(doc(), interactive=False, rel="catalog/commonroad/X")}
    assert rec["cr3"]["mode"] == "recorded" and rec["cr3"]["trajectory"] == "catalog/commonroad/X/obstacles/cr3.jsonl"
    assert rec["cr5"]["mode"] == "static" and rec["cr5"]["kind"] == "static"
    inter = {a["id"]: a for a in I.actors_of(doc(), interactive=True)}
    assert inter["cr4"]["mode"] == "model" and inter["cr3"]["mode"] == "recorded"    # a one-state obstacle: SUMO's to drive


def test_the_verdict_from_the_harvest_row():
    base = {"id": "X", "worlds": "13b7dac", "pin": "ef793dc", "error": None}
    assert I.verdict_of(dict(base, failed=[]))["status"] == "pass"
    soft = I.verdict_of(dict(base, failed=["goal"], goal={"position_t": 9.0}))
    assert soft["status"] == "soft" and soft["since"] == {"worlds": "13b7dac", "catalog": "ef793dc"}
    fail = I.verdict_of(dict(base, failed=["contact"], record_id="r1"), {"kind": "structural"})
    assert fail["status"] == "fail" and fail["record"] == "r1"
    assert I.verdict_of(dict(base, failed=["contact"], record_id="r1"), {"kind": "world"})["status"] == "world"
    assert I.verdict_of(None) is None


def test_the_selection_one_per_cluster_then_every_stratum(tmp_path):
    d = tmp_path / "ef793dc" / "panzer" / "rows"
    d.mkdir(parents=True)
    rows = [{"id": "%s_%s-%d" % (c, m, i), "country": c, "tags": [m], "failed": ["contact"] if i == 0 else [], "error": None,
             "started": "%s%s%03d" % (c, m, i)} for c in ("DEU", "USA", "ESP") for m in ("urban", "highway") for i in range(10)]
    for r in rows:
        (d / ("%s.json" % r["id"])).write_text(json.dumps(r))
    clusters = [{"id": "c1", "kind": "structural", "representative": {"id": "DEU_urban-0"}, "scenarios": ["DEU_urban-0"]},
                {"id": "c2", "kind": "world", "representative": {"id": "USA_urban-0"}, "scenarios": ["USA_urban-0"]}]
    (tmp_path / "ef793dc" / "clusters.json").write_text(json.dumps({"clusters": clusters}))
    ids = I.select(tmp_path / "ef793dc", n=20, seed=1)
    assert ids[0] == "DEU_urban-0" and "USA_urban-0" not in ids[:1]               # the law clusters first, world ones not as such
    strata = {(i.split("_")[0], i.split("_")[1].split("-")[0]) for i in ids}
    assert len(strata) == 6 and len(ids) <= 20 and len(set(ids)) == len(ids)      # every (country, map type) at least once
    assert I.select(tmp_path / "ef793dc", n=20, seed=1) == ids                     # deterministic


IDS = ("ARG_Carcarana-10_2_T-1", "DEU_Frankfurt-74_11_I-1", "ESP_Berga-10_3_I-1-1")


def _cache():
    import cr_world
    return Path(os.environ.get("COMMONROAD_CACHE", str(cr_world.CACHE)))


@pytest.mark.skipif(not all((_cache() / i / "cr.json").is_file() for i in IDS), reason="the CommonRoad conversion cache lacks the three ids")
def test_three_cards_from_the_cache(tmp_path):
    pytest.importorskip("sumolib")
    import yaml
    for sid in IDS:
        p = I.card(sid, _cache(), tmp_path)
        c = yaml.safe_load(p.read_text())
        assert c["card"] == 2 and c["source"]["suite"] == "commonroad" and c["patches"] == [] and set(c["tags"]) <= I.VOCAB
        d = tmp_path / sid
        assert (d / "NOTICE").read_text().startswith("CommonRoad") and (d / "cr.json").is_file() and (d / Path(c["map"]["net"]).name).is_file()
        for a in c["actors"]:
            if a["mode"] == "recorded" and a.get("trajectory"):
                assert (d / "obstacles" / Path(a["trajectory"]).name).is_file()


def test_a_card_already_in_the_catalog_is_kept(tmp_path):
    (tmp_path / "X.yaml").write_text("card: 2\nscenario: X\n# hand-made\n")
    assert I.card("X", tmp_path / "nocache", tmp_path).read_text().endswith("# hand-made\n")   # never read the cache, never overwritten


@pytest.mark.skipif(not all((_cache() / i / "cr.json").is_file() for i in IDS[:1]), reason="the CommonRoad conversion cache lacks the id")
def test_the_verdict_is_per_host_sumo_only(tmp_path):
    pytest.importorskip("sumolib")
    import yaml
    row = {"id": IDS[0], "worlds": "13b7dac", "pin": "ef793dc", "error": None, "failed": []}
    c = yaml.safe_load(I.card(IDS[0], _cache(), tmp_path, row=row).read_text())
    assert c["verdict"] == {"sumo": {"status": "pass", "since": {"worlds": "13b7dac", "catalog": "ef793dc"}}}
