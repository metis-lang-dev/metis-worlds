"""The world under test (world-alfworld step 1): the grounding, the host, the generated
package, the program. Runs under the world's venv with ALFWORLD_DATA set; the program
checks need METISC (metis-lang's compiler) and are skipped without it."""
import json, os, subprocess, sys
import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "world"))
from alf_gym import Game  # noqa: E402
from alf_host import AlfHost, bindings  # noqa: E402
from ground import Handles, STATIC, DYNAMIC  # noqa: E402
import families  # noqa: E402
import gen_instance  # noqa: E402

pytestmark = pytest.mark.skipif(not os.environ.get("ALFWORLD_DATA"), reason="ALFWORLD_DATA is not set")
GAME = "pick_and_place_simple-Tomato-None-DiningTable-26/trial_T20190908_010907_122466"


def game_dir():
    return os.path.join(families.data_root(), "train", GAME)


def test_grounding_is_deterministic_across_opens():
    a = Game().open(os.path.join(game_dir(), "game.tw-pddl"))
    b = Game().open(os.path.join(game_dir(), "game.tw-pddl"))
    assert a["handles"] == b["handles"] and a["static"] == b["static"] and a["init"] == b["init"]
    assert a["task_type"] == "pick_and_place_simple"
    kinds = {k for k in a["handles"]["kind"].values()}
    assert kinds == {"location", "receptacle", "object", "otype", "rtype"}
    assert all(a_.split("(")[0] in STATIC for a_ in a["static"]) and all(a_.split("(")[0] in DYNAMIC for a_ in a["init"])


def test_handles_round_trip():
    a = Game().open(os.path.join(game_dir(), "game.tw-pddl"))
    h = Handles.from_json(a["handles"])
    assert h.to_name == a["handles"]["to_name"]
    assert all(h.to_handle[n] == k for k, n in h.to_name.items())


def test_bindings():
    assert bindings("go_obj[O=tomato2,L=loc1,L2=loc4]") == ("go_obj", {"O": "tomato2", "L": "loc1", "L2": "loc4"})
    assert bindings("choose") == ("choose", {})


def test_splits_and_families():
    c = families.counts()
    # each task directory holds its trials (two per task in train): 790 games of the first family
    assert c["train"]["pick_and_place_simple"] == 790 and c["valid_unseen"]["pick_and_place_simple"] == 24
    assert len(families.sample("valid_seen", "pick_and_place_simple", 3, seed=7)) == 3


@pytest.fixture
def package(tmp_path):
    path, nd, ns = gen_instance.generate(game_dir(), str(tmp_path))
    pkg = os.path.dirname(path)
    assert os.path.exists(os.path.join(pkg, "domain.yaml")) and os.path.exists(os.path.join(pkg, "game.json"))
    # the package includes the lifted domain by a relative path: copy it beside, as the real tree has it
    import shutil
    shutil.copy(os.path.join(ROOT, "domains", "alfred_domain.llp"), os.path.join(str(tmp_path), "alfred_domain.llp"))
    return pkg, path


def plan(h):
    """A plan from the game's own facts: the first target object, its receptacle, the first destination."""
    ot, rt = h.params["object_target"].lower() + "_t", h.params["parent_target"].lower() + "_t"
    targets = sorted(a[6:-1].split(",")[0] for a in h.static if a.startswith("otype(") and a.endswith("," + ot + ")")
                     and "pickupable(" + a[6:-1].split(",")[0] + ")" in h.static)
    dests = sorted(a[6:-1].split(",")[0] for a in h.static if a.startswith("rtype(") and a.endswith("," + rt + ")"))
    r = h.reading()
    at = next(a for a in r if a.startswith("at("))[3:-1]
    o = targets[0]
    rec = next(a for a in r if a.startswith("inrecep(%s," % o))[8:-1].split(",")[1]
    loc = next(a for a in h.static if a.startswith("recat(%s," % rec))[6:-1].split(",")[1]
    d = dests[0]
    dloc = next(a for a in h.static if a.startswith("recat(%s," % d))[6:-1].split(",")[1]
    ev = [("choose[O=%s]" % o, ()), ("go_obj[O=%s,L=%s,L2=%s]" % (o, at, loc), ())]
    if rec in h.openable:
        ev += [("open_obj[O=%s,L=%s,R=%s]" % (o, loc, rec), ()), ("take_open[O=%s,L=%s,R=%s]" % (o, loc, rec), ())]
    else:
        ev += [("take_plain[O=%s,L=%s,R=%s]" % (o, loc, rec), ())]
    ev += [("go_target[L=%s,R=%s,L2=%s]" % (loc, d, dloc), ())]
    ev += [("open_target[L=%s,R=%s]" % (dloc, d), ())] if d in h.openable else []
    ev += [("put_%s[O=%s,L=%s,R=%s]" % ("open" if d in h.openable else "plain", o, dloc, d), ())]
    return ev


def test_host_runs_the_plan_to_a_win(package):
    pkg, _ = package
    h = AlfHost(pkg)
    try:
        counts = {a: 1 for a in h.reading()}
        assert h.tick(counts) == []                     # the program at the game's state: nothing to sync
        for name, args in plan(h):
            h.on_event(name, args)
        assert all(adm for _, _, _, adm, _ in h.commands), [c for c in h.commands if not c[3]]
        assert h.won
        snap = h.snapshot()
        h.restore(snap)
        assert h.won and len(h.commands) == len(snap["commands"])
    finally:
        h.gym.close()


def test_host_refusal_leaves_the_facts(package):
    pkg, _ = package
    h = AlfHost(pkg)
    try:
        before = set(h.dyn)
        r = h.reading()
        o = next(a for a in h.static if a.startswith("target(") or a.startswith("otype("))  # any object
        h.on_event("put_plain[O=%s,L=loc1,R=sink1]" % next(a[6:-1].split(",")[0] for a in h.static if a.startswith("otype(")), ())
        assert h.commands and not h.commands[-1][3] and not h.commands[-1][4]
        assert set(h.dyn) == before
    finally:
        h.gym.close()


@pytest.mark.skipif(not os.environ.get("METISC"), reason="METISC is not set")
def test_program_reaches_placed_alone(package):
    _, path = package
    out = subprocess.run([os.environ["METISC"], "--run", path], capture_output=True, text=True, timeout=600)
    assert "Q placed 1/1" in out.stdout, out.stdout[-500:] + out.stderr[-300:]


# ── the hierarchy (alf-hierarchy step 1): the specialists over the same game, a manual switch ──
import gen_hier  # noqa: E402


def test_hierarchy_wins_by_manual_switch(tmp_path):
    """The task domain emits sub-goals, the driver activates the specialist that handles each,
    the game is won; every activation ends in a result atom; no command refused."""
    if not os.path.exists(os.path.join(os.path.dirname(ROOT), ".venv", "bin", "metis")):
        pytest.skip("no metispy `metis` beside the world repos")
    sys.path.insert(0, os.path.join(ROOT, "experiments"))
    import hier
    wd = str(tmp_path)
    import shutil
    shutil.copy(os.path.join(ROOT, "domains", "alfred_domain.llp"), os.path.join(wd, "alfred_domain.llp"))
    os.makedirs(os.path.join(wd, "hier"))
    for s in gen_hier.SPECS:
        shutil.copy(os.path.join(ROOT, "domains", "hier", s + "_domain.llp"), os.path.join(wd, "hier", s + "_domain.llp"))
    r = hier.run_game(game_dir(), wd)
    assert r["error"] is None, r
    assert r["won"] and r["outcome"] == "done", r
    assert [a["spec"] for a in r["activations"]] == ["nav", "access", "grasp", "nav", "access", "place"]
    assert all(a["result"] for a in r["activations"]) and r["refused"] == 0


def test_hierarchy_instances_see_less(tmp_path):
    """Each specialist's instance declares fewer predicates and starts from fewer facts than the flat one."""
    path, nd, ns = gen_instance.generate(game_dir(), str(tmp_path))
    info = json.load(open(os.path.join(os.path.dirname(path), "game.json")))
    h = AlfHost(os.path.dirname(path))
    try:
        info = dict(info, static=sorted(h.static), task_type=h.task, params=h.params)
        reading = h.reading()
    finally:
        h.gym.close()
    flat_init = sum(1 for l in open(path) if l.startswith("#init"))
    for spec in gen_hier.SPECS:
        p = gen_hier.generate(game_dir(), str(tmp_path / "pk"), spec, 0, info, reading, gen_hier.seed(info), [])
        init = sum(1 for l in open(p) if l.startswith("#init"))
        assert init < flat_init, (spec, init, flat_init)
        assert gen_hier.vector(spec)["rules"] <= 12


def test_activation_cards(tmp_path):
    """alf-hierarchy step 2: with intents=True an activation's package carries its card — the
    template's slots filled with the activation's things in capitals (the mapper's keys) mapping to
    the handles, only the examples the game has, the things in the guidance, the manifest naming
    it; without it the driver's package stays four files."""
    import yaml
    path, _, _ = gen_instance.generate(game_dir(), str(tmp_path))
    info = json.load(open(os.path.join(os.path.dirname(path), "game.json")))
    h = AlfHost(os.path.dirname(path))
    try:
        info = dict(info, static=sorted(h.static), task_type=h.task, params=h.params)
        reading = h.reading()
    finally:
        h.gym.close()
    kinds = info["handles"]["kind"]
    pick = {a[len("pickupable("):-1] for a in info["static"] if a.startswith("pickupable(")}
    plain = os.path.dirname(gen_hier.generate(game_dir(), str(tmp_path / "plain"), "nav", 0, info, reading, [], []))
    assert sorted(os.listdir(plain)) == ["alf_host.py", "domain.yaml", "game.json", "nav.llp"]
    for spec in gen_hier.SPECS:
        pkg = os.path.dirname(gen_hier.generate(game_dir(), str(tmp_path / "pk"), spec, 0, info, reading, [], [],
                                                intents=True))
        assert "intent: {spec: intent.yaml}" in open(os.path.join(pkg, "domain.yaml")).read()
        c = yaml.safe_load(open(os.path.join(pkg, "intent.yaml")))
        want = {"receptacle": {r for r, k in kinds.items() if k == "receptacle"},
                "object": {o for o, k in kinds.items() if k == "object" and o in pick}}   # the task too: any pickupable may be named (F1)
        for slot, s in c["slots"].items():
            assert {v.lower() for v in s["enum"]} == want[slot], (spec, slot)
            assert c["values"][slot] == {v.upper(): v for v in want[slot]}
            assert all(v.upper() in c["guidance"] for v in want[slot])
        for _, j in c["examples"]:
            assert all(j[k].lower() in want[k] for k in j if k in want), (spec, j)
        assert [r["atom"].split("(")[0] for r in c["map"]] == [{"nav": "goto", "access": "open", "grasp": "take",
                                                                 "place": "put", "task": "fetch"}[spec]]
        assert all(" " not in r["atom"] for r in c["map"])     # a do-line reads a space as its count's


# ── the director (alf-hierarchy step 3): rules make the switch; a detour for a person's goal from elsewhere ──
def _hier_workdir(tmp_path):
    import shutil
    wd = str(tmp_path)
    shutil.copy(os.path.join(ROOT, "domains", "alfred_domain.llp"), os.path.join(wd, "alfred_domain.llp"))
    shutil.copy(os.path.join(ROOT, "domains", "director_domain.llp"), os.path.join(wd, "director_domain.llp"))
    os.makedirs(os.path.join(wd, "hier"))
    for s in gen_hier.SPECS:
        shutil.copy(os.path.join(ROOT, "domains", "hier", s + "_domain.llp"), os.path.join(wd, "hier", s + "_domain.llp"))
    return wd


def test_director_makes_the_switch(tmp_path):
    """The director's rules wake, route and sleep the specialists from the kinds that arrive: the same
    game, the same six activations as the manual switch, won; every specialist slept after its result."""
    if not os.path.exists(os.path.join(os.path.dirname(ROOT), ".venv", "bin", "metis")):
        pytest.skip("no metispy `metis` beside the world repos")
    sys.path.insert(0, os.path.join(ROOT, "experiments"))
    import hier
    r = hier.run_game_director(game_dir(), _hier_workdir(tmp_path))
    assert r["error"] is None and r["won"] and r["outcome"] == "done", r
    assert [a["spec"] for a in r["activations"] if a["spec"] != "task"] == ["nav", "access", "grasp", "nav", "access", "place"]
    effects = [e for b in r["beats"] for e in b["effects"]]
    assert effects.count("wake(nav)") == 2 and effects.count("sleep(nav)") == 2 and "ended(done)" in effects
    assert r["refused"] == 0


def test_director_detours_a_goal_from_elsewhere(tmp_path):
    """A person's open(R) while the agent stands elsewhere: access answers elsewhere(R), the director
    puts the goal aside, sends nav, and on reached(R) gives access its goal back; R ends up open."""
    if not os.path.exists(os.path.join(os.path.dirname(ROOT), ".venv", "bin", "metis")):
        pytest.skip("no metispy `metis` beside the world repos")
    sys.path.insert(0, os.path.join(ROOT, "experiments"))
    import hier
    wd = _hier_workdir(tmp_path)
    path, _, _ = gen_instance.generate(game_dir(), wd)
    h = AlfHost(os.path.dirname(path))
    try:
        at = next(a for a in h.reading() if a.startswith("at("))[3:-1]
        far = sorted(x for x in h.openable if "recat(%s,%s)" % (x, at) not in h.static)[0]
    finally:
        h.gym.close()
    r = hier.run_game_director(game_dir(), wd, first=["open(%s)" % far])
    assert r["error"] is None, r
    assert [(a["spec"], a["result"]) for a in r["activations"]][:3] == [
        ("access", ["elsewhere(%s)" % far]), ("nav", ["reached(%s)" % far]), ("access", ["accessible(%s)" % far])]
    detour = next(b for b in r["beats"] if b["arrival"] == "elsewhere(%s)" % far)
    assert set(detour["effects"]) == {"forward(nav,goto)", "sleep(access)", "wake(nav)"}
    effects = [e for b in r["beats"] for e in b["effects"]]
    assert effects.count("forward(access,open)") == 2
