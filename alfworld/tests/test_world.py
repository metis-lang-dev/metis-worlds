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


def _metis_cli():
    sys.path.insert(0, os.path.join(ROOT, "experiments"))
    from baseline import metis_py  # noqa: E402
    try:
        return metis_py()
    except SystemExit:
        return None


def test_hierarchy_wins_by_manual_switch(tmp_path):
    """The task domain emits sub-goals, the driver activates the specialist that handles each,
    the game is won; every activation ends in a result atom; no command refused."""
    if not _metis_cli():
        pytest.skip("no metispy `metis` beside the worlds repo (set METIS_PY)")
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
        assert gen_hier.vector(spec)["rules"] <= 14          # the task domain: 14 with `already` and `held` (alf-demo step 3b, F8/F12)


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
    if not _metis_cli():
        pytest.skip("no metispy `metis` beside the worlds repo (set METIS_PY)")
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
    if not _metis_cli():
        pytest.skip("no metispy `metis` beside the worlds repo (set METIS_PY)")
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


def test_semantic_map_text_mode():
    """alf-demo step 3a: a game's semantic map in text mode (DEMO.md §3): every receptacle a place
    at the position its THOR id carries, every thing in a place, the agent at traj_data's start,
    the task's words and its goal; web/fixtures/ holds the reference game's, as written by it."""
    import semantic_map
    assert semantic_map.thor_id("countertop_bar__minus_01_dot_87_bar__plus_00_dot_96_bar__plus_01_dot_80") == (
        "countertop", -1.87, 0.96, 1.8)
    assert semantic_map.thor_id("loc_bar_3") is None and semantic_map.spoken("cabinet10") == "cabinet 10"
    m = semantic_map.text_map(game_dir(), "idx.json")
    ids = {p["id"] for p in m["places"]}
    assert m["places"] and all(p["pos"] and len(p["pos"]) == 2 for p in m["places"])
    assert m["things"] and all(t["at"] in ids for t in m["things"])
    assert m["task"]["text"] and m["task"]["goal"].startswith("fetch(") and m["tileset"] == {"index": ["idx.json"]}
    assert len(m["edges"]) == len(ids) * (len(ids) - 1) // 2
    card = m["card"]                                   # the world card (3b): generated from the game's facts
    assert card["title"].startswith("ALFWorld kitchen") and len(card["about"]) == 3 and card["room"] and card["things"]
    assert [a["say"] for a in card["asks"]][:1] == [m["task"]["text"].rstrip(".").lower()] and card["asks"][-2:][0]["say"] == "stop"
    assert sum(t["n"] for t in card["things"]) == sum(1 for t in m["things"] if t["pickupable"]) and card["cannot"]
    ref = os.path.join(ROOT, "..", "web", "fixtures", "alfworld_tomato_microwave_13.json")
    fix = json.load(open(ref))
    trial = os.path.join(families.data_root(), fix["game"])
    if os.path.isdir(trial):
        assert semantic_map.text_map(trial, fix["tileset"]["index"][0]) == fix, "web/fixtures/ is stale: rerun semantic_map.py"


def test_the_recorded_turns():
    """alf-demo step 3b: web/fixtures/*.run.jsonl, the world page's recorded turns. The fridge
    (a disengagement, short) is what record_run.py writes now; the win's frames hold the turn:
    every director beat with one attention, the specialists in their order, the end."""
    import tempfile
    ref = os.path.join(ROOT, "..", "web", "fixtures")
    win = [json.loads(x) for x in open(os.path.join(ref, "alfworld_tomato_microwave_13.run.jsonl"))]
    beats = [f for f in win if f["ev"] == "world/hierarchy"]
    assert beats and all(sum(a.startswith("attention(") for a in f["state"]) == 1 for f in beats)
    woke = [f["rec"]["domain"] for f in win if f["ev"] == "journal" and f["rec"]["kind"] == "dlg-domain" and f["rec"]["verb"] == "activate"]
    assert woke == ["nav", "access", "grasp", "nav", "access", "place"]
    assert beats[-1]["effects"] == ["ended(done)"] and win[1]["rec"]["person"] == "put a tomato in the microwave"   # a success ends without an ask (66e96fc)
    fix = os.path.join(ref, "alfworld_tomato_microwave_13_fridge.run.jsonl")
    sem = os.path.join(ref, "alfworld_tomato_microwave_13.json")
    trial = os.path.join(families.data_root(), json.load(open(sem))["game"])
    if os.path.isdir(trial):
        out = os.path.join(tempfile.mkdtemp(), "fridge.run.jsonl")
        r = subprocess.run([sys.executable, os.path.join(ROOT, "experiments", "record_run.py"), trial, sem, out,
                            "put the tomato in the fridge", "fetch(tomato1,fridge1)"], capture_output=True, text=True, timeout=900)
        assert r.returncode == 0, r.stderr[-400:]
        got = [json.loads(x) for x in open(out)]
        got[0]["url"] = json.loads(open(fix).readline())["url"]          # relative to where it was written
        assert got == [json.loads(x) for x in open(fix)], "web/fixtures/ is stale: rerun record_run.py"


def test_hierarchy_continues_after_a_result(tmp_path):
    """alf-hierarchy step 3 (the agent's director): a specialist package generated with
    continues=True reports its result atom once and keeps stepping (tick returns do-lines, not
    None); without it the run ends on the result, as the manual-switch driver expects."""
    from alf_host import AlfHost
    wd = str(tmp_path)
    flat, _, _ = gen_instance.generate(game_dir(), wd)
    flat_pkg = os.path.dirname(flat)
    import json
    info = json.load(open(os.path.join(flat_pkg, "game.json")))
    mirror = AlfHost(flat_pkg)
    try:
        info = dict(info, static=sorted(mirror.static), task_type=mirror.task, params=mirror.params)
        rec = next(a for a in mirror.static if a.startswith("recat("))[6:-1].split(",")[0]
        reading = mirror.reading()
    finally:
        mirror.gym.close()
    for continues in (False, True):
        out_dir = os.path.join(wd, "c%d" % continues)
        path = gen_hier.generate(game_dir(), out_dir, "nav", 0, info, reading, gen_hier.seed(info) + ["goto(%s)" % rec], [],
                                 domain_rel=os.path.join(ROOT, "domains", "hier", "nav_domain.llp"), continues=continues)
        h = AlfHost(os.path.dirname(path))
        try:
            counts = {a: 1 for a in h.reading()}
            counts["reached(%s)" % rec] = 1                               # the nav specialist's result atom
            out = h.tick(counts)
            if continues:
                assert out is not None and not h.done, "continues: the run goes on after the result"
                assert h.tick(counts) is not None and "reached(%s)" % rec in h.reported, "the result is reported once, the world keeps stepping"
            else:
                assert out is None and h.done, "the manual switch: the run ends on the result"
        finally:
            h.gym.close()


def test_install_director_for_the_agent(tmp_path):
    """alf-hierarchy step 3: a game installed under a root — the director package, the task's
    person-mode instance, an empty instance per specialist, the shared commands log; the director
    host queues arrivals, retracts its out atoms, and re-instances a specialist for a goal over
    the world as the log says."""
    from director_host import DirectorHost
    root = str(tmp_path)
    pk = gen_hier.install(game_dir(), root)
    assert set(pk) == {"_flat", "director", "task", "nav", "access", "grasp", "place"}
    assert os.path.exists(os.path.join(pk["director"], "director.llp")) and os.path.exists(os.path.join(pk["director"], "domain.yaml"))
    for d in ("task", "nav", "access", "grasp", "place"):
        meta = json.load(open(os.path.join(pk[d], "game.json")))
        assert meta["continues"] and meta["commands_log"].endswith(".commands.jsonl"), d
    assert "#init fetch(" not in open(os.path.join(pk["task"], "task.llp")).read()      # person=True: the FETCH is typed, not seeded (W6)
    h = DirectorHost(pk["director"])
    h.world(["+seen(goto) 1"])
    assert h.tick({}) == ["+seen(goto) 1"]
    assert h.tick({"wake(nav)": 1, "forward(nav,goto)": 1, "active(nav)": 1}) == ["-forward(nav,goto) 1", "-wake(nav) 1"]
    assert h.tick({}) == [] and h.reported[-1]["out"] == ["forward(nav,goto)", "wake(nav)"]
    from alf_host import AlfHost
    m = AlfHost(pk["_flat"])
    try:
        rec = next(a for a in sorted(m.static) if a.startswith("recat("))[6:-1].split(",")[0]
    finally:
        m.gym.close()
    assert h.instance("nav", "goto(%s)" % rec, []) is True
    llp = open(os.path.join(pk["nav"], "nav.llp")).read()
    assert "#init goto(%s) 1" % rec in llp
    # the log is the world's state: a nav host made now replays it (empty: t == 0); after a step the
    # log has one line and the next host made over the flat package starts one step in
    nav = AlfHost(pk["nav"])
    try:
        assert nav.t == 0
        nav.on_event("go[R=%s,L2=%s]" % (rec.replace(" ", "_"), "x"), ())
        stepped = nav.t
    finally:
        nav.gym.close()
    log = [json.loads(l) for l in open(os.path.join(root, "domains", "hier", ".commands.jsonl")) if l.strip()]
    assert len(log) == stepped
    if stepped:
        again = AlfHost(pk["_flat"]) if False else None
    if os.environ.get("METISC"):
        for d in ("director", "task", "nav"):
            llp = next(f for f in os.listdir(pk[d]) if f.endswith(".llp"))
            out = subprocess.run([os.environ["METISC"], "--diagnostics-json", os.path.join(pk[d], llp)], capture_output=True, text=True, timeout=120)
            assert out.returncode == 0 and "error" not in out.stdout.lower(), (d, out.stdout[-400:] + out.stderr[-200:])


def test_a_planners_delivery_is_its_new_instance(tmp_path):
    """alf-demo 3b timing: deliver(task, goal, tokens) brings the live planner's counts to exactly
    what instance(task, goal, tokens) would start it at — its put-out sub-goals and stale world facts
    gone, its own tokens one each, the goal in, the world's facts as the log says — so the agent
    takes them as one row instead of a reload; a specialist is not delivered."""
    import collections
    from director_host import DirectorHost
    root = str(tmp_path)
    pk = gen_hier.install(game_dir(), root)
    h = DirectorHost(pk["director"])
    task = open(os.path.join(pk["task"], "task.llp")).read()
    obj = next(a for a in task.splitlines() if a.startswith("#init inrecep("))[len("#init inrecep("):].split(",")[0]
    rec = next(a for a in task.splitlines() if a.startswith("#init inrecep(%s," % obj)).split(",")[1].split(")")[0]
    tokens = {"want(%s)" % obj: 1, "to(%s)" % rec: 2, "goto(%s)" % rec: 1, "done": 1,     # a put-out sub-goal, an out, a count of 2
              "holds(%s)" % obj: 1,                                                    # a stale world fact (the log says it is in rec)
              "inrecep(%s,%s)" % (obj, rec): 1}
    goal = "reached(%s)" % rec
    lines = h.deliver("task", goal, tokens)
    got = collections.Counter(tokens)
    for l in lines:
        atom, n = l[1:].split()
        got[atom] += int(n) if l[0] == "+" else -int(n)
    got = {a: n for a, n in got.items() if n > 0}
    assert h.instance("task", goal, tokens) is True
    want = collections.Counter(l.split()[1] for l in open(os.path.join(pk["task"], "task.llp")).read().splitlines() if l.startswith("#init "))
    assert got == dict(want), (sorted(set(got.items()) ^ set(want.items())))[:10]
    assert "-goto(%s) 1" % rec in lines and "-holds(%s) 1" % obj in lines and "+%s 1" % goal in lines
    assert h.deliver("nav", "goto(%s)" % rec, {}) is None
    # the live planner's own host follows the shared world when refreshed: a specialist's command on the
    # same log moves the world, and the task's host reads it after refresh() (no reset, no replay)
    from alf_host import AlfHost
    th, nav = AlfHost(pk["task"]), AlfHost(pk["nav"])
    try:
        loc = next(a for a in sorted(nav.static) if a.startswith("recat(%s," % rec))[6:-1].split(",")[1]
        nav.on_event("go[R=%s,L2=%s]" % (rec, loc), ())
        assert nav.t == 1 and th.t == 0
        th.refresh()
        assert th.t == 1 and th.dyn == nav.dyn            # each reading is its package's predicates: the world view is dyn
    finally:
        nav.gym.close()
        th.gym.close()


def test_rule_names_map_by_their_first_token(package):
    """loop-policy step 2 F2: a rule the loop names `verb_why` maps to the game's verb by its first
    token with the variable convention (go: R [L2], open: R, take: O R, put: O R); the table's own
    keys keep their meaning."""
    from alf_host import AlfHost
    pkg, _ = package
    h = AlfHost(pkg)
    try:
        assert h.command_of("go_for[R=x]", ()) is None            # without the opt-in a hand domain's go_for is bookkeeping, not a command (opus)
    finally:
        h.gym.close()
    meta = json.load(open(os.path.join(pkg, "game.json"))); meta["verbs"] = True
    json.dump(meta, open(os.path.join(pkg, "game.json"), "w"))
    h = AlfHost(pkg)
    try:
        o, r = next(a for a in sorted(h.dyn) if a.startswith("inrecep("))[8:-1].split(",")     # a real object in a real receptacle
        loc = next(a for a in h.static if a.startswith("recat(%s," % r))[6:-1].split(",")[1]
        assert h.command_of("go_anywhere[R=%s]" % r, ()) == "go to " + h.name(r)                 # L2 from recat
        assert h.command_of("go_there[L2=%s,R=%s]" % (loc, r), ()) == "go to " + h.name(r)
        assert h.command_of("open_it_up[R=%s]" % r, ()) == "open " + h.name(r)
        assert h.command_of("take_now[O=%s,R=%s]" % (o, r), ()) == "take %s from %s" % (h.name(o), h.name(r))
        assert h.command_of("put_back[O=%s,R=%s]" % (o, r), ()) == "move %s to %s" % (h.name(o), h.name(r))
        assert h.command_of("dance[O=%s]" % o, ()) is None
    finally:
        h.gym.close()


def test_a_taken_command_is_the_maps_delta(package):
    """alf-demo step 2: the host hands the world page one world/delta per command the game took
    (frames(), drained by metis-agent's service): the agent's place after a go; nothing for a
    command the game refused."""
    from alf_host import AlfHost
    pkg, _ = package
    h = AlfHost(pkg)
    try:
        r = sorted(h.loc_of if hasattr(h, "loc_of") else {x for rs in h.recat.values() for x in rs})[0]
        loc = next(l for l, rs in h.recat.items() if r in rs)
        h.on_event("go[L2=%s,R=%s]" % (loc, r), ())
        fs = h.frames()
        assert fs == [{"agent": {"at": r}, "ev": "world/delta"}] and h.frames() == []
        h.on_event("put_plain[O=%s,R=%s]" % (next(iter(h.to_name)), r), ())        # nothing held: the game refuses
        assert h.frames() == []
        assert h.speak("I go to %s, not to loc99." % r) == "I go to %s %s, not to loc99." % (r.rstrip("0123456789"), r[len(r.rstrip("0123456789")):])
    finally:
        h.gym.close()


def test_a_goal_is_said_as_the_person_reads_it():
    """nina's alf-demo 3b wire note: the working status says a domain's goal in words (goal_text)."""
    from alf_host import AlfHost
    h = AlfHost.__new__(AlfHost)
    h.to_name = {"countertop3": "countertop 3", "tomato1": "tomato 1", "microwave1": "microwave 1"}
    assert h.goal_text("goto(countertop3)") == "going to countertop 3"
    assert h.goal_text("put(tomato1,microwave1)") == "moving tomato 1 to microwave 1"
    assert h.goal_text("dance(tomato1)") is None and h.goal_text("put(tomato1)") is None


def test_the_director_copy_matches_the_catalogs():
    """The lifted director base's canonical home is metis-catalog domains/director (loop-policy 2b G5);
    this world carries a copy (copies, not dependencies). Skipped without the catalog checkout beside."""
    d = ROOT
    cat = None
    for _ in range(5):
        d = os.path.dirname(d)
        c = os.path.join(d, "metis-catalog", "domains", "director", "director_domain.llp")
        if os.path.exists(c):
            cat = c
            break
    if cat is None:
        pytest.skip("no metis-catalog checkout beside the worlds")
    mine = os.path.join(ROOT, "domains", "director_domain.llp")
    assert open(mine).read() == open(cat).read(), "the copy drifted from metis-catalog domains/director/director_domain.llp"


# ── alf-demo step 3b (the architect's world items of opus's findings): F3 answerable asks, F7 a new episode, F8 a done task asked again ──
def _task_instance(wd, name, reading, init):
    """The task's instance over the lifted task domain, run by metisc: the fired rules and the final facts."""
    import json
    flat, _, _ = gen_instance.generate(game_dir(), os.path.join(wd, "flat"))
    fp = os.path.dirname(flat)
    from alf_host import AlfHost
    m = AlfHost(fp)
    try:
        info = dict(json.load(open(os.path.join(fp, "game.json"))), static=sorted(m.static), task_type=m.task, params=m.params)
        world = m.reading()
    finally:
        m.gym.close()
    dom = os.path.relpath(os.path.join(ROOT, "domains", "hier", "task_domain.llp"), os.path.join(wd, name, "task-0"))
    rd = reading(info, world)
    path = gen_hier.generate(game_dir(), os.path.join(wd, name), "task", 0, info, rd, init(info), [], domain_rel=dom)
    out = subprocess.run([os.environ["METISC"], "--run", path], capture_output=True, text=True, timeout=300)
    assert out.returncode == 0, out.stderr[-500:]
    fired = [l.split()[2].split("[")[0] for l in out.stdout.splitlines() if l.startswith("T ")]
    final = next(l for l in out.stdout.splitlines() if l.startswith("F "))
    return fired, final


@pytest.mark.skipif(not os.environ.get("METISC"), reason="METISC is not set")
def test_a_fetch_already_in_place_is_done_at_once(tmp_path):
    """F8: asking for a task that is done must not undo it — the planner sees the target in its
    destination and is done without a sub-goal (no goto, nothing taken out again)."""
    def seed(info):
        return gen_hier.seed(info)
    def already(info, world):
        o, r = seed(info)[0][6:-1].split(",")
        return [a for a in world if not a.startswith("inrecep(%s," % o)] + ["inrecep(%s,%s)" % (o, r)]
    fired, final = _task_instance(str(tmp_path), "already", already, seed)
    assert fired == ["already"] and " done:1" in final and "goto(" not in final, (fired, final)
    fired, final = _task_instance(str(tmp_path), "fresh", lambda info, world: world, seed)
    assert fired[0] == "fetch" and "goto(" in final and " done:" not in final, (fired, final)
    # F12: a stop after the take leaves the agent holding the target — the next fetch carries it
    def held(info, world):
        o = seed(info)[0][6:-1].split(",")[0]
        return [a for a in world if not a.startswith("inrecep(%s," % o)] + ["holds(%s)" % o]
    fired, final = _task_instance(str(tmp_path), "held", held, seed)
    assert fired == ["held"] and "goto(" in final and "carry(" in final, (fired, final)


@pytest.mark.skipif(not os.environ.get("METISC"), reason="METISC is not set")
def test_the_asks_carry_their_answers(tmp_path):
    """F3: a question to the person ends its doc line with the answers the card takes, `| put O in D
    | stop`, every placeholder bound by the rule (the destination this task wants, the object it fetches)."""
    import re
    src = open(os.path.join(ROOT, "domains", "hier", "task_domain.llp")).read()
    asks = re.findall(r"%% ([^\n]*\| stop)\n\s*(\w+) \[dyn\] : ([^\n]*)", src)
    assert sorted(n for _, n, _ in asks) == ["not_dest", "not_target"], asks
    for doc, name, rule in asks:
        answers = [a.strip() for a in doc.split("|")[1:]]
        assert len(answers) == 2 and answers[-1] == "stop" and answers[0].startswith("put "), (name, answers)
        for v in re.findall(r"\{(\w+)\}", doc):
            assert re.search(r"\(\s*%s\s*[,)]|,\s*%s\s*[,)]" % (v, v), rule.split("-o")[0]), (name, v, rule)
    def notdest(info):
        o = gen_hier.seed(info)[0][6:-1].split(",")[0]
        nd = sorted(a[8:-1] for a in gen_hier.static_facts("task", info) if a.startswith("notdest("))[0]
        return ["fetch(%s,%s)" % (o, nd)]
    fired, final = _task_instance(str(tmp_path), "notdest", lambda info, world: world, notdest)
    assert fired == ["not_dest"] and "wrong_dest(" in final, (fired, final)


def test_new_episode_restarts_the_won_game(package):
    """F7: after a win the game is over (commands change nothing); new_episode() restarts the same
    game from its start with the shared commands log emptied and nothing reported."""
    from alf_host import AlfHost
    pkg, _ = package
    log = os.path.join(pkg, ".commands.jsonl")
    open(log, "w").close()
    import json
    meta = json.load(open(os.path.join(pkg, "game.json")))
    json.dump(dict(meta, commands_log=log), open(os.path.join(pkg, "game.json"), "w"))
    h = AlfHost(pkg)
    try:
        for name, args in plan(h):
            h.on_event(name, args)
        assert h.won and h.t > 0 and os.path.getsize(log) > 0
        h.new_episode()
        assert not h.won and not h.done and h.t == 0 and os.path.getsize(log) == 0 and not h.reported
        assert any(a.startswith("holds(") for a in h.reading()) is False
    finally:
        h.gym.close()


def test_hosts_on_one_log_share_one_world(package):
    """alf-demo step 3b (the user's time profile: 12 director steps × two ALFWorld spawns = 90 s of a
    93 s task): every host on the same commands log shares one world process; a host opened after
    another stepped the world takes its state without a reset or a replay; new_episode resets it."""
    import time
    from alf_host import AlfHost, _SHARED
    pkg, _ = package
    log = os.path.join(pkg, ".commands.jsonl")
    open(log, "w").close()
    a = AlfHost(pkg, commands_log=log)
    assert a.gym.shared and (a.game, log) in _SHARED
    steps = plan(a)[:2]
    for name, args in steps:
        a.on_event(name, args)
    t = time.time()
    b = AlfHost(pkg, commands_log=log)
    dt = time.time() - t
    assert b.gym is a.gym and b.t == a.t == len(a.gym.history) >= 1 and b.reading() == a.reading(), "the state carried over"
    assert dt < 0.5, "no spawn, no reset, no replay: %.2f s" % dt
    assert b.gym.history == [c for _, _, c, _, _ in a.commands]
    b.new_episode()
    assert b.t == 0 and b.gym.history == [] and os.path.getsize(log) == 0
    c = AlfHost(pkg)                                     # no log: a private world as before
    assert not c.gym.shared and c.gym is not a.gym
    c.gym.close()


@pytest.mark.skipif(not os.environ.get("METISC"), reason="METISC is not set")
def test_every_lifted_base_compiles_alone():
    """spec 12 (abstract-types step 3): the director, the flat base and the hierarchy's specialist
    bases declare the types their instances complete (`types (…)`), so metisc compiles each alone
    — its advisory names them — and refuses only to ground it."""
    hier = os.path.join(ROOT, "domains", "hier")
    bases = [os.path.join(ROOT, "domains", f) for f in ("director_domain.llp", "alfred_domain.llp")] + \
        sorted(os.path.join(hier, f) for f in os.listdir(hier) if f.endswith("_domain.llp"))
    assert len(bases) == 7
    for p in bases:
        out = subprocess.run([os.environ["METISC"], p], capture_output=True, text=True, timeout=120)
        assert out.returncode == 0 and "; abstract " in out.stdout, (p, out.stderr[-600:])
