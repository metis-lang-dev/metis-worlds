"""The road's trace (metis.trace; trace-replay s-c111ff41): a run of the tree under py Live, each member replayed alone from what it
applied, with no world and no SUMO: 0 divergences. The exerciser here; straight on SUMO with METIS_ROAD_SUMO=1 (one SUMO at a time)."""
import importlib.util
import os
from pathlib import Path

import pytest

ROAD = Path(__file__).resolve().parents[1]
pytest.importorskip("metis.trace")
pytest.importorskip("metis_agent.trace")              # the reader: road's CI runs the siblings at their heads, whichever merged first
pytestmark = pytest.mark.skipif(importlib.util.find_spec("metis_agent") is None, reason="no metis_agent (its venv)")


composition = pytest.mark.skipif(not hasattr(__import__("metis_agent.trace", fromlist=["replay_composition"]), "replay_composition"),
                                 reason="metis-agent before the composition's replay: this CI's sibling at its head, until it merges")


def road_tree():
    spec = importlib.util.spec_from_file_location("road_tree", ROAD / "experiments" / "road_tree.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def replayed(d):
    from metis import trace
    head = trace.read(d)[0].header
    assert set(head["members"]) == {"responder", "signals", "planner", "road_director"}
    assert "brake_lon" in head["commands"]
    out = {}
    for m in head["members"]:
        out[m] = trace.replay(d, m, ROAD / "domains" / m / ("%s.llp" % m))
        assert out[m].ok, (m, out[m].divergence)
    return out


@pytest.fixture
def env(monkeypatch):
    for k in ("METIS_CATALOG", "METIS_ROAD_RUN", "METIS_ROAD_WORLD"):      # road_tree sets them: undone with the test
        monkeypatch.setenv(k, os.environ.get(k, ""))


def test_asking_a_trace_of_an_agent_without_the_reader_is_refused(tmp_path, env, monkeypatch):
    tree = road_tree()
    monkeypatch.setattr(tree, "has_reader", lambda: False)
    with pytest.raises(SystemExit) as e:
        tree.run("cruise", 1, tmp_path, ticks=5, trace=tmp_path / "t")
    assert "no trace would be written" in str(e.value) and "metis-agent " in str(e.value) and e.value.code
    assert not (tmp_path / "t").exists() and not list(tmp_path.glob("j-*")), "refused before anything ran"
    tree.run("cruise", 1, tmp_path / "plain", ticks=5)    # no trace asked: nothing to refuse


def test_a_live_that_ignores_the_trace_key_is_refused(tmp_path, env, monkeypatch):
    from metis_agent import service as S
    tree, init = road_tree(), S.Live.__init__

    def older(self, cfg, llm, emit=None):
        init(self, dict((k, v) for k, v in cfg.items() if k != "trace"), llm, emit)
        del self.tracer
    monkeypatch.setattr(S.Live, "__init__", older)
    with pytest.raises(SystemExit, match="this Live ignored the config's trace:"):
        tree.run("cruise", 1, tmp_path, ticks=5, trace=tmp_path / "t")


def test_the_page_refuses_an_agent_without_the_reader(tmp_path):
    spec = importlib.util.spec_from_file_location("road_hier", ROAD / "world" / "road_hier.py")
    hier = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(hier)
    with pytest.raises(SystemExit, match="no metis_agent/trace.py"):
        hier.install(str(tmp_path / "root"), str(tmp_path))
    assert not (tmp_path / "root").exists()


def test_a_run_on_the_exerciser_replays_with_no_world(tmp_path, env):
    road_tree().run("cruise", 1, tmp_path, ticks=250, trace=tmp_path / "t")
    r = replayed(tmp_path / "t" / "cruise-1")
    assert r["planner"].rules and r["road_director"].rules and r["planner"].out


def test_a_command_in_the_trace_is_the_restrictors_kind_and_args(tmp_path, env):
    from metis import trace
    road_tree().run("cruise", 1, tmp_path, ticks=250, trace=tmp_path / "t")
    out = [o for s in trace.read(tmp_path / "t" / "cruise-1") for t in s.ticks for o in t["members"].get("planner", {}).get("out", ())]
    cmds = [o for o in out if isinstance(o, dict)]
    assert {c["kind"] for c in cmds} >= {"accel", "keep"} and all(not c["args"] for c in cmds if c["kind"] in ("accel", "keep"))
    assert any(isinstance(o, str) and o.startswith("tick__want(planner") for o in out), "every out port, not the commands alone"


@pytest.mark.skipif(not hasattr(__import__("metis.trace", fromlist=["case"]), "case"), reason="metispy before metis.trace's case: this CI's sibling at its head, until it merges")
def test_a_case_may_ask_the_command_kind_a_norm_requires(tmp_path, env):
    """On an empty road the oracle is a norm: a yield and an accel leave the same tokens, so a case asserts the command's kind."""
    from metis import trace
    from metis.catalog import manifests as mc, stub
    road_tree().run("cruise", 1, tmp_path, ticks=120, trace=tmp_path / "t")
    rows = [t for s in trace.read(tmp_path / "t" / "cruise-1") for t in s.ticks]
    k = next(t["k"] for t in rows for c in t["members"].get("planner", {}).get("out", ()) if isinstance(c, dict) and c["kind"] == "accel")
    d = next(x for x in mc.domains(ROAD) if x.name == "planner")
    f = tmp_path / "c.yaml"
    f.write_text(trace.case(tmp_path / "t" / "cruise-1", "planner", k, out=[{"kind": "accel*"}]))
    r = stub.run_case(d, f)
    assert r.passed, stub.render([r])
    f.write_text(trace.case(tmp_path / "t" / "cruise-1", "planner", k, out=[{"kind": "yield_*"}, {"not": "accel*"}]))
    fails = " ".join(x for b in stub.run_case(d, f).boundaries for x in b.failures)
    assert "no command of kind yield_*" in fails and "the norm forbids" in fails


def test_a_checkpoint_says_the_runs_time(tmp_path, env):
    from metis import trace
    road_tree().run("cruise", 1, tmp_path, ticks=250, trace=tmp_path / "t")
    segs = trace.read(tmp_path / "t" / "cruise-1")
    assert len(segs) == 2 and segs[1].k0 == 200
    assert segs[1].checkpoint["world"]["scenario"] == "cruise" and segs[1].checkpoint["world"]["t"] > 0


@composition
def test_the_composition_replays_with_no_candidate_to_the_record(tmp_path, env):
    """The whole tree on the real Live, the hosts feeding the record, the agent's own relays."""
    from metis_agent.trace import replay_composition
    tree = road_tree()
    tree.run("cruise", 1, tmp_path, ticks=250, trace=tmp_path / "t")
    r = replay_composition(tmp_path / "t" / "cruise-1", tree.config(None, 1))
    assert r.ok, r.divergence
    assert r.ticks == 250 and r.checkpoints == 1


judged = pytest.mark.skipif(not hasattr(__import__("metis_agent.trace", fromlist=["judge"]), "judge"), reason="metis-agent before the judgement: this CI's sibling at its head, until it merges")
AGAIN = """
stage safety {
  %% The same reading, another name.
  yield_again [dyn] : $busy * $tick__grant(planner, controls) * $zone_at(nextzone, C) * $closing_in(C) * $zprio(nextzone, P) * $yields_to(P) * $conflict(nextzone) * $zbusy(nextzone) * now -o ().
}
"""
BESIDE = """
pred went_on : planner.
stage progress {
  %% I go on, by a rule beside the ones that say how.
  go_on [dyn] : go -o went_on.
}
"""


def judged_on_road(tmp_path, pack):
    from metis_agent.trace import judge
    tree = road_tree()
    tree.run("cruise", 1, tmp_path, ticks=120, trace=tmp_path / "t")
    return judge(tmp_path / "t" / "cruise-1", "planner", pack, ROAD, lambda root: tree.config(None, 1), composition="domains")


LATE = """
stage safety {
  %% The zone ahead comes too late to stop for at my pace: I ease off, {R}.
  brake_late [dyn] : $busy * $tick__grant(planner, controls) * $late(nextzone) * $soft(R) * now -o ().
}
"""


family_units = pytest.mark.skipif("consumers" not in __import__("inspect").signature(getattr(__import__("metis_agent.trace", fromlist=["judge"]), "judge", lambda: None)).parameters,
                                  reason="metis-agent before a family's unit: this CI's sibling at its head, until it merges")


@judged
@family_units
def test_a_new_rule_of_a_commands_kind_shows_as_an_output(tmp_path, env):
    from metis_agent.trace import judge
    tree = road_tree()
    tree.run("cruise", 1, tmp_path, ticks=200, trace=tmp_path / "t")
    e = judge(tmp_path / "t" / "cruise-1", "planner", LATE, ROAD, lambda root: tree.config(None, 1), composition="domains", unit=Path(os.environ["METIS_HOME"]) / "planner_domain.llp")
    assert e["verdict"] == "accepted" and e["unit"] == "METIS_HOME/planner_domain.llp", e["reasons"]
    assert any(x.startswith("brake_late") for x in e["first_out_diff"]["candidate"]), e["first_out_diff"]
    assert e["first_enabled"]["rule"].startswith("brake_late") and e["open_loop_after"] == e["first_enabled"]["k"]


@judged
def test_a_pack_repeating_a_family_rule_is_refused_naming_it(tmp_path, env):
    e = judged_on_road(tmp_path, AGAIN)
    assert e["verdict"] == "refused" and "yield_again repeats yield_zone in planner_domain.llp" in " ".join(e["reasons"]), e["reasons"]


@judged
def test_a_pack_breaking_the_familys_goldens_is_refused_naming_them(tmp_path, env):
    e = judged_on_road(tmp_path, BESIDE)
    assert e["verdict"] == "refused" and "golden drive.yaml of planner" in " ".join(e["reasons"]), e["reasons"]
    assert e["goldens"]["ran"]["planner"] >= 5 and e["receipt"]["moved"] == ["planner"] and e["receipt"]["ei_holds"]
    assert e["first_enabled"]["rule"] == "go_on" and e["first_fired_diff"]["member"] == "planner" and e["open_loop_after"] == e["first_out_diff"]["k"]


@composition
@pytest.mark.skipif(not os.environ.get("METIS_ROAD_SUMO"), reason="METIS_ROAD_SUMO=1: straight on SUMO")
def test_straight_on_sumo_replays_with_no_sumo(tmp_path, env):
    from metis_agent.trace import replay_composition
    tree = road_tree()
    tree.run("straight", 1, tmp_path, ticks=400, world_kind="sumo", vehicles=10, trace=tmp_path / "t")
    replayed(tmp_path / "t" / "straight-1")
    r = replay_composition(tmp_path / "t" / "straight-1", tree.config(None, 1))
    assert r.ok, r.divergence
