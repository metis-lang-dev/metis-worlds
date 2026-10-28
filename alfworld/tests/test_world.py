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
    shutil.copy(os.path.join(ROOT, "domains", "hier", "capacity.llp"), os.path.join(wd, "hier", "capacity.llp"))
    shutil.copytree(os.path.join(ROOT, "domains", "hier", "iface"), os.path.join(wd, "hier", "iface"), dirs_exist_ok=True)
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
        smap = gen_hier.build_map(str(tmp_path / "map.json"), info, h)
    finally:
        h.gym.close()
    flat_init = sum(1 for l in open(path) if l.startswith("#init"))
    seed = [smap.intent_atom(gen_hier.seed(info)[0])]
    for spec in gen_hier.SPECS:
        p = gen_hier.generate(game_dir(), str(tmp_path / "pk"), spec, 0, info, smap, reading, seed, [])
        init = sum(1 for l in open(p) if l.startswith("#init"))
        assert init < flat_init, (spec, init, flat_init)
        assert gen_hier.vector(spec)["rules"] <= 23          # the task domain: 14 with `already` and `held` (alf-demo step 3b, F8/F12),
                                                             # 21 with view mode's look (semantic-map step 3: not_here, not_in,
                                                             # lost_it, nowhere; verify, open_look, verified), 23 with
                                                             # stuck_take / stuck_put (specialist-tree step 3b: refused split)


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
        smap = gen_hier.build_map(str(tmp_path / "map.json"), info, h)
    finally:
        h.gym.close()
    kinds = info["handles"]["kind"]
    pick = {a[len("pickupable("):-1] for a in info["static"] if a.startswith("pickupable(")}
    plain = os.path.dirname(gen_hier.generate(game_dir(), str(tmp_path / "plain"), "nav", 0, info, smap, reading, [], []))
    assert sorted(os.listdir(plain)) == ["alf_host.py", "domain.yaml", "game.json", "nav.llp"]
    for spec in gen_hier.SPECS:
        pkg = os.path.dirname(gen_hier.generate(game_dir(), str(tmp_path / "pk"), spec, 0, info, smap, reading, [], [],
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
    shutil.copy(os.path.join(ROOT, "domains", "hier", "capacity.llp"), os.path.join(wd, "hier", "capacity.llp"))
    shutil.copytree(os.path.join(ROOT, "domains", "hier", "iface"), os.path.join(wd, "hier", "iface"), dirs_exist_ok=True)
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
    import semantic_map
    smap = semantic_map.SemanticMap(os.path.join(wd, gen_instance.instance_id(game_dir()), ".map.json"))
    far = smap.role_of(far)                            # the activations speak roles: far is bound for the person's goal
    assert far and far.startswith("p")
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
        reading = mirror.reading()
        smap = gen_hier.build_map(os.path.join(wd, "map.json"), info, mirror)
    finally:
        mirror.gym.close()
    smap.project(*gen_hier.args_of(gen_hier.seed(info)[0]))
    rec = "dest"                                                          # a role: the nav specialist speaks roles
    for continues in (False, True):
        out_dir = os.path.join(wd, "c%d" % continues)
        path = gen_hier.generate(game_dir(), out_dir, "nav", 0, info, smap, reading, ["goto(%s)" % rec], [],
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
    for d in ("task", "nav", "access", "grasp", "place"):      # each is its committed instance, byte for byte (semantic-map step 2)
        assert open(os.path.join(pk[d], d + ".llp")).read() == open(os.path.join(ROOT, "domains", "hier", d, d + ".llp")).read(), d
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
    before = open(os.path.join(pk["nav"], "nav.llp")).read()
    assert h.instance("nav", None, []) is True                      # a reload's start: the map re-projected, the program untouched
    assert open(os.path.join(pk["nav"], "nav.llp")).read() == before
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


def test_a_delivery_is_the_activations_start(tmp_path):
    """alf-demo 3b timing, semantic-map step 2: deliver(D, goal, tokens) brings ANY hierarchy domain's
    live session to its next activation — its put-out atoms and stale world facts gone, its own tokens
    one each, the goal in, the world's facts in roles through the map's binding — so the agent takes
    them as one row and never reloads; the live planner's host follows the shared world when refreshed."""
    import collections
    from director_host import DirectorHost
    from alf_host import AlfHost
    root = str(tmp_path)
    pk = gen_hier.install(game_dir(), root)
    h = DirectorHost(pk["director"])
    th = AlfHost(pk["task"])
    try:
        world = th.reading()                                              # the task's world in roles
    finally:
        th.gym.close()
    rec = next(a for a in world if a.startswith("inrecep(target,"))[len("inrecep(target,"):-1]
    assert rec == "p1"                                                    # p1: where the map believes the target is
    tokens = {"want(target)": 1, "to(dest)": 2, "goto(%s)" % rec: 1, "done": 1,  # a put-out sub-goal, an out, a count of 2
              "holds(target)": 1,                                         # a stale world fact (the map says it is in p1)
              "inrecep(target,%s)" % rec: 1}
    goal = "reached(%s)" % rec
    lines = h.deliver("task", goal, tokens)
    got = collections.Counter(tokens)
    for l in lines:
        atom, n = l[1:].split()
        got[atom] += int(n) if l[0] == "+" else -int(n)
    got = {a: n for a, n in got.items() if n > 0}
    want = dict(collections.Counter([a for a in world if a.split("(")[0] in gen_hier.SPECS["task"]["dyn"]]
                                    + ["want(target)", "to(dest)", goal]))
    assert got == want, sorted(set(got.items()) ^ set(want.items()))[:10]
    assert "-goto(%s) 1" % rec in lines and "-holds(target) 1" in lines and "+%s 1" % goal in lines
    nav = h.deliver("nav", "goto(%s)" % rec, {"reached(dest)": 1, "at(lhere)": 1})   # a specialist too: its last result retracted
    assert "+goto(%s) 1" % rec in nav and "-reached(dest) 1" in nav and "+recat(%s,l1) 1" % rec in nav
    assert not any(a.startswith(("+inrecep", "+holds")) for a in nav)      # only what nav observes
    assert h.deliver("director", None, {}) is None
    th, nh = AlfHost(pk["task"]), AlfHost(pk["nav"])
    try:
        loc = nh.smap.handle("l1")
        nh.on_event("go[R=%s,L2=l1]" % rec, ())
        assert nh.t == 1 and th.t == 0 and nh.commands[-1][2] == "go to " + nh.name(nh.smap.handle(rec))
        th.refresh()
        assert th.t == 1 and th.dyn == nh.dyn and "at(%s)" % loc in th.dyn
    finally:
        nh.gym.close()
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
        smap = gen_hier.build_map(os.path.join(wd, name + ".map.json"), info, m)
    finally:
        m.gym.close()
    dom = os.path.relpath(os.path.join(ROOT, "domains", "hier", "task_domain.llp"), os.path.join(wd, name, "task-0"))
    start = [smap.intent_atom(a) for a in init(info)]          # the goal in the room's terms, projected onto the roles
    rd = {a: 1 for a in reading(info, world)}
    path = gen_hier.generate(game_dir(), os.path.join(wd, name), "task", 0, info, smap, rd, start, [], domain_rel=dom)
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
        dests = gen_hier.task_goal(info)[1]
        nd = sorted(r for r in (a[6:-1].split(",")[0] for a in info["static"] if a.startswith("recat(")) if r not in dests)[0]
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


# ── semantic-map s-d4270bed step 2: the room as data — roles in the program, the map in the host ──
ROLES_HIER = os.path.join(ROOT, "domains", "hier")


def _kitchen_handles():
    """Every handle the demo-style test game has (objects, receptacles, locations)."""
    path, _, _ = gen_instance.generate(game_dir(), os.path.join(__import__("tempfile").mkdtemp(), "h"))
    return set(json.load(open(os.path.join(os.path.dirname(path), "game.json")))["handles"]["kind"])


def test_no_room_in_any_specialists_source(tmp_path):
    """The five committed instances and the capacity name no thing of any room; they are what
    gen_hier writes (committed(), capacity()); an install writes no specialist source but them."""
    import re
    handles = _kitchen_handles()
    for f in ["capacity.llp"] + ["%s/%s.llp" % (s, s) for s in gen_hier.SPECS]:
        text = open(os.path.join(ROLES_HIER, f)).read()
        words = set(re.findall(r"\b[a-z]+\d+\b", re.sub(r"%.*", "", text)))
        assert not words & handles, (f, sorted(words & handles)[:5])
    assert open(os.path.join(ROLES_HIER, "capacity.llp")).read() == gen_hier.capacity()
    for s in gen_hier.SPECS:
        assert open(os.path.join(ROLES_HIER, s, s + ".llp")).read() == gen_hier.committed(s), s
    pk = gen_hier.install(game_dir(), str(tmp_path))
    for s in gen_hier.SPECS:
        llps = [f for f in os.listdir(pk[s]) if f.endswith(".llp")]
        assert llps == [s + ".llp"] and open(os.path.join(pk[s], llps[0])).read() == gen_hier.committed(s), s


def test_no_role_is_a_word_of_a_doc_line():
    """A role is said as its thing in every line (AlfHost.speak replaces the bound roles' words): no
    rule's %% line may use a role's name as a plain word, or the voice would rename it too."""
    import re
    import semantic_map
    roles = set(semantic_map.OBJECT_ROLES) | set(semantic_map.place_roles(16)) | set(semantic_map.location_roles(16))
    for f in [os.path.join(ROLES_HIER, s + "_domain.llp") for s in gen_hier.SPECS] + [os.path.join(ROOT, "domains", "director_domain.llp")]:
        for line in open(f):
            if line.strip().startswith("%%"):
                plain = re.sub(r"\{\w+\}", "", line)
                assert not set(re.findall(r"\b\w+\b", plain)) & roles, (f, line.strip())


@pytest.mark.parametrize("k", [8, 16])
def test_the_capacity_grounds_small(tmp_path, k):
    """The committed role bases ground small at k = 8 (the committed capacity) and k = 16 (capacity(16)):
    with the place facts dynamic (the projection asserts recat/openable) a rule ranges over every
    location × receptacle role, so grasp/place grow as places³ — 2.4k events at 8, 13k at 16, against
    the room's 160k and today's ~3k per activation, paid once at load (step 2's report has the table)."""
    import shutil, time
    from metis.lang.compiler import load_llp
    d = tmp_path / "hier"
    shutil.copytree(ROLES_HIER, d, ignore=shutil.ignore_patterns("*.tsv", "intent.yaml"))
    (d / "capacity.llp").write_text(gen_hier.capacity(k))
    bound = {8: 3000, 16: 15000}[k]
    for s in gen_hier.SPECS:
        if k != 8:
            (d / s / (s + ".llp")).write_text(gen_hier.instance_text(s, "../%s_domain.llp" % s, "../capacity.llp", k=k))
        t0 = time.perf_counter()
        prog = load_llp(d / s / (s + ".llp")).catalog.ground({})
        dt = time.perf_counter() - t0
        events = sum(len(v) for v in prog.stages.values()) + len(prog.links)
        assert 0 < events <= bound and dt < 2.0, (s, k, events, dt)


def _role_install(tmp_path):
    from alf_host import AlfHost
    pk = gen_hier.install(game_dir(), str(tmp_path))
    return pk, AlfHost(pk["task"])


def test_the_projection_binds_the_goals_working_set(tmp_path):
    """project(): target the task's object, dest its receptacle, p1 where the map believes the target
    is, p0 where the robot stands; a location shared by two receptacles is one role; a fetch of an
    object the task does not want binds `other`, of a receptacle it does not want a p slot."""
    pk, th = _role_install(tmp_path)
    try:
        m = th.smap
        d = m.load()
        b = m.binding()
        tgt, dst = d["task"]["targets"][0], d["task"]["dests"][0]
        assert b["target"] == tgt and b["dest"] == dst and b["p1"] == d["things"][tgt]["in"]
        assert b["lhere"] == d["agent"]["at"] and b["ldest"] == d["places"][dst]["loc"]
        locs = {}
        for r, p in d["places"].items():
            locs.setdefault(p["loc"], []).append(r)
        shared = next(rs for l, rs in sorted(locs.items()) if len(rs) > 1 and dst not in rs)
        b = m.project(None, shared[0])                          # a named non-dest receptacle: p1; its neighbour too
        b = m.project(None, shared[0])
        m.data["belief"][tgt] = {shared[0]: 0.5, shared[1]: 0.5}   # an uncertain belief: two places
        b = m.project(tgt, None)
        assert {b["p1"], b["p2"]} == set(shared) and b["l1"] == d["places"][shared[0]]["loc"] and "l2" not in b
        rd = m.role_reading({})
        assert rd["recat(p1,l1)"] == rd["recat(p2,l1)"] == 1          # one location role for both
        other = sorted(o for o, t in d["things"].items() if t["pickupable"] and o not in d["task"]["targets"])[0]
        assert m.intent_atom("fetch(%s,%s)" % (other, dst)) == "fetch(other,dest)" and m.binding()["other"] == other
        nd = sorted(r for r in d["places"] if r not in d["task"]["dests"])[0]
        assert m.intent_atom("fetch(%s,%s)" % (tgt, nd)) == "fetch(target,p1)" and m.binding()["p1"] == nd
        assert m.intent_atom("fetch(target,dest)") == "fetch(target,dest)"     # already roles
    finally:
        th.gym.close()


def test_a_rebinding_is_a_sync_on_the_live_session(tmp_path):
    """Moved/new is the host's: a second goal re-projects the map, and the SAME host's next tick
    retracts the old role atoms and asserts the new ones — the counts then are a fresh reading's,
    no reload, no recompile."""
    pk, th = _role_install(tmp_path)
    try:
        counts = dict(th.reading())
        # at the world's state: nothing to sync but the level port's atom, the host's at its tick (spec16 step 4:
        # no fetch engaged, so its risk is high)
        assert th.tick(counts) == ["+fetch_risk(high) 1"]
        counts["fetch_risk(high)"] = 1
        # the level is the host's world line: in the reading the session syncs, never in the watch's observe (a
        # surprise difference) — not even when it moved while the member was stopped (the session still says high)
        assert "fetch_risk(high)" in th.reading() and not any(a.startswith("fetch_risk(") for a in th.observe(counts))
        th.level_atoms = {"fetch_risk(low)": 1}
        assert not any(a.startswith("fetch_risk(") for a in th.observe(counts))
        th.level_atoms = {"fetch_risk(high)": 1}
        d = th.smap.load()
        nd = sorted(r for r in d["places"] if r not in d["task"]["dests"] and r != th.smap.handle("p1"))[0]
        held = th.smap.handle("p1")
        assert th.intent_atom("fetch(%s,%s)" % (d["task"]["targets"][0], nd)) == "fetch(target,p1)"
        assert th.smap.handle("p1") == nd and th.smap.handle("p2") == held     # the target's place moved to p2
        dos = th.tick(counts)
        assert "-inrecep(target,p1) 1" in dos and "+inrecep(target,p2) 1" in dos, dos
        for l in dos:
            a, n = l[1:].split()
            counts[a] = counts.get(a, 0) + (int(n) if l[0] == "+" else -int(n))
        assert {a: n for a, n in counts.items() if n} == th.reading()
    finally:
        th.gym.close()


def test_the_host_says_the_roles_as_the_rooms_things(tmp_path):
    """name(role, thing) as data: the commands, the voice, the goal text and the page's chain say
    the room's things; the rules say roles."""
    from alf_host import AlfHost
    pk, th = _role_install(tmp_path)
    gh = AlfHost(pk["grasp"])
    try:
        b = th.smap.binding()
        names = dict(th.ports()["names"])
        assert names["target"] == b["target"] and names["dest"] == b["dest"] and "lhere" not in names
        assert gh.command_of("take_plain[O=target,L=l1,R=p1]", ()) == "take %s from %s" % (gh.name(b["target"]), gh.name(b["p1"]))
        from semantic_map import spoken
        assert th.speak("I take target from p1.") == "I take %s from %s." % (spoken(b["target"]), spoken(b["p1"]))
        assert th.goal_text("goto(p1)") == "going to " + spoken(b["p1"])
        assert th.in_room("reached(p1)") == "reached(%s)" % b["p1"] and th.in_room("done") == "done"
    finally:
        gh.gym.close()
        th.gym.close()


def test_the_belief_port_reads_the_map(tmp_path):
    """The task's `look(O, R)` weight: the map's belief that O is in R, normalized over the bound
    places — 1.0 where it is seen, 0 elsewhere, flat when the map knows nothing; the host binds it."""
    pk, th = _role_install(tmp_path)

    class Reg:
        def __init__(self):
            self.w = {}

        def weight(self, name, fn):
            self.w[name] = fn
    try:
        reg = Reg()
        th.bind(reg)
        look = reg.w["look"]
        assert look(("target", "p1"), {}) == 1.0 and look(("target", "dest"), {}) == 0.0
        assert look(("other", "p1"), {}) == 1.0                  # unbound: the map has no belief, flat
        m = th.smap
        m.data["belief"][m.handle("target")] = {m.handle("p1"): 0.3, m.handle("dest"): 0.1}
        assert abs(look(("target", "p1"), {}) - 0.75) < 1e-9
    finally:
        th.gym.close()


@pytest.mark.skipif(not os.environ.get("METISC"), reason="METISC is not set")
def test_a_fetch_of_another_thing_is_refused_by_roles(tmp_path):
    """F1 over roles: a person's fetch of an object the task does not want binds it to `other`;
    not_target refuses it and asks with the task's own target."""
    def other(info):
        targets = gen_hier.task_goal(info)[0]
        pick = sorted(a[len("pickupable("):-1] for a in info["static"] if a.startswith("pickupable("))
        return ["fetch(%s,%s)" % (next(o for o in pick if o not in targets), gen_hier.task_goal(info)[1][0])]
    fired, final = _task_instance(str(tmp_path), "other", lambda info, world: world, other)
    assert fired == ["not_target"] and "wrong_object(other)" in final, (fired, final)


def test_no_world_frame_of_the_recordings_carries_a_role():
    """The compiled vocabulary never reaches the page (the architect's rule, semantic-map step 2): no role
    token anywhere in a world/* frame of the recorded turns, not even in a side field; the journal's
    dlg-trace is the program's record and stays in roles."""
    import re
    import semantic_map
    roles = set(semantic_map.OBJECT_ROLES) | set(semantic_map.place_roles()) | set(semantic_map.location_roles())
    pat = re.compile(r"\b(%s)\b" % "|".join(sorted(roles, key=len, reverse=True)))
    ref = os.path.join(ROOT, "..", "web", "fixtures")
    for name in ("alfworld_tomato_microwave_13.run.jsonl", "alfworld_tomato_microwave_13_fridge.run.jsonl"):
        frames = [json.loads(x) for x in open(os.path.join(ref, name))]
        assert any(f["ev"] == "journal" and f["rec"].get("kind") == "dlg-trace" and pat.search(json.dumps(f)) for f in frames)
        for f in frames:
            if f["ev"].startswith("world/"):
                shown = json.dumps(f)
                assert not pat.search(shown), (name, shown[:200])


# ── semantic-map step 3: the map sees only what the robot sees (view mode, the architect's RULING 1) ──
def _view_install(tmp_path):
    from alf_host import AlfHost
    pk = gen_hier.install(game_dir(), str(tmp_path), view=True)
    return pk, AlfHost(pk["task"])


def _loc(m, place):
    return m.load()["places"][place]["loc"]


def test_view_mode_knows_only_what_the_robot_sees(tmp_path):
    """The robot starts where it sees into no receptacle: the map knows the places, no thing; the task's
    kind is an entry of its own ("tomato"), believed flat over the places ALFWorld's cancontain lets hold
    it, the dests left out; the task reads that belief (an inrecep per candidate place), never the game's
    truth, and the card offers the kind."""
    import semantic_map
    import yaml
    pk, th = _view_install(tmp_path)
    try:
        d = th.smap.load()
        kind = semantic_map.want_handle(d["task"]["targets"][0])
        assert d["view"] and d["prior"] == "cancontain" and set(d["things"]) == {kind}
        bel = d["belief"][kind]
        st = set(th.static)
        ok = {a[len("cancontain("):-1].split(",")[0] for a in st if a.startswith("cancontain(") and a.endswith(",%s)" % d["types"][d["task"]["targets"][0]])}
        want = {r for r in d["places"] if d["types"][r] in ok and r not in d["task"]["dests"]}
        assert set(bel) == want and abs(sum(bel.values()) - 1) < 1e-9 and len(set(bel.values())) == 1
        b = th.smap.binding()
        assert b["target"] == kind
        believed = {"inrecep(target,%s)" % r for r, h in b.items() if h in bel}
        assert {a for a in th.reading() if a.startswith("inrecep(")} == believed      # the belief, not the truth
        card = yaml.safe_load(open(os.path.join(pk["task"], "intent.yaml")))
        assert card["slots"]["object"]["enum"] == [kind.upper()]
    finally:
        th.gym.close()


def test_view_a_look_updates_the_belief_and_the_binding_stays(tmp_path):
    """A place looked into without the thing: its belief goes to 0, the rest renormalizes, the task reads
    absent there and its role stays bound (the task holds reached(p) for it); a place seen into with the
    thing: the kind resolves to the instance, the map and the card grow (the host's card_changed), the
    place keeps its role and the target is bound to the instance."""
    import yaml
    pk, th = _view_install(tmp_path)
    m = th.smap
    try:
        d = m.load()
        kind = next(iter(d["things"]))
        truth = {a[len("inrecep("):-1].split(",")[0]: a[len("inrecep("):-1].split(",")[1] for a in th.dyn if a.startswith("inrecep(")}
        tgt = next(t for t in d["task"]["targets"] if t in truth)
        home = truth[tgt]
        empty = next(r for r in sorted(d["belief"][kind]) if not d["places"][r]["openable"] and r != home
                     and not any(v == r for o, v in truth.items() if o in d["task"]["targets"]))
        role = m.role_of(empty)
        n = len(d["belief"][kind])
        m.observe({"at(%s)" % _loc(m, empty)})
        d = m.load()
        assert empty not in d["belief"][kind] and abs(sum(d["belief"][kind].values()) - 1) < 1e-9 and len(d["belief"][kind]) == n - 1
        assert d["looked"][kind] == [empty] and m.role_of(empty) == role
        assert th.reading().get("absent(target,%s)" % role) == 1 and "inrecep(target,%s)" % role not in th.reading()
        lit = [e for f in th.frames() for e in f.get("entities", [])]          # the page lights the place seen into
        assert {"id": empty, "unseen": False, "items": []} in lit and not th.frames()
        hrole = m.role_of(home)
        seen = {"at(%s)" % _loc(m, home)} | ({"opened(%s)" % home} if d["places"][home]["openable"] else set()) | \
               {"inrecep(%s,%s)" % (o, r) for o, r in truth.items() if r == home}
        m.observe(seen)
        d = m.load()
        assert d["resolved"][kind] in d["task"]["targets"] and kind not in d["belief"]
        inst = d["resolved"][kind]
        assert m.binding()["target"] == inst and d["belief"][inst] == {home: 1.0} and m.role_of(home) == hrole
        assert th.reading().get("inrecep(target,%s)" % hrole) == 1
        assert th.card_changed() and not th.card_changed()                 # once, after the growth
        enum = yaml.safe_load(open(os.path.join(pk["task"], "intent.yaml")))["slots"]["object"]["enum"]
        assert inst.upper() in enum and kind.upper() in enum               # the instance, and still the kind
    finally:
        th.gym.close()


def test_view_the_dest_is_looked_into_before_already(tmp_path):
    """A target the map left in its dest (a run before: not seen there now) is believed(target, dest),
    never inrecep — the task's `already` waits for a look (verify); looked into without it: absent there,
    and the belief starts again from the prior less the places looked into; nothing left: lost."""
    pk, th = _view_install(tmp_path)
    m = th.smap
    try:
        d = m.load()
        inst, dst = d["task"]["targets"][0], m.binding()["dest"]
        d["things"][inst] = {"in": dst, "pickupable": True}
        d["belief"][inst] = {dst: 1.0}
        m.save()
        assert m.project(inst, dst)["target"] == inst
        r = th.reading()
        assert r.get("believed(target,dest)") == 1 and "inrecep(target,dest)" not in r
        m.observe({"at(%s)" % _loc(m, dst)} | ({"opened(%s)" % dst} if m.load()["places"][dst]["openable"] else set()))
        d = m.load()
        assert th.reading().get("absent(target,dest)") == 1 and d["belief"][inst] and dst not in d["belief"][inst]
        d["looked"][inst] = sorted(set(d["looked"][inst]) | set(d["belief"][inst]))
        d["belief"][inst] = {}
        m.save()
        assert th.reading().get("lost(target)") == 1
    finally:
        th.gym.close()


def test_a_specialist_reads_its_activation_binding(tmp_path):
    """View mode re-projects while the robot looks: a specialist reads the binding it was woken with
    (frozen at its activation: refresh, as the agent's take calls it) — no place fact moves under its
    goal, which its watch would take for a surprise — and the planner reads the map's own."""
    from alf_host import AlfHost
    pk, th = _view_install(tmp_path)
    ah = AlfHost(pk["access"])
    m = th.smap
    try:
        before = dict(ah.frozen)
        assert ah.frozen == m.binding() and th.frozen is None
        bel = m.load()["belief"][next(iter(m.load()["things"]))]
        empty = next(r for r in sorted(bel) if not m.load()["places"][r]["openable"])
        role = m.role_of(empty)
        m.observe({"at(%s)" % _loc(m, empty)})                        # a look elsewhere: the map's binding may move
        m.load()["binding"].pop(role)                                  # … say this slot was freed
        m.save()
        lrole = next(r for r, h in before.items() if h == _loc(m, empty))
        assert ah.frozen == before and "recat(%s,%s)" % (role, lrole) in ah.reading()
        ah.refresh()
        assert ah.frozen == m.binding() and not any(a.startswith("recat(%s," % role) for a in ah.reading())
    finally:
        ah.gym.close()
        th.gym.close()


def test_the_demo_names_its_games_and_loads_one_by_name(tmp_path):
    """The world page's game picker (demo.sh): demo.py's game list (pick_and_place_simple, one per task directory,
    by room), a game resolved from its name in any of its forms, and setup's games.json (this game current) and the
    service's v3.games / v3.game_request (the page's next game, beside the catalog)."""
    import yaml
    sys.path.insert(0, os.path.join(ROOT, "experiments"))
    import demo
    gs = demo.game_list()
    ids = [g["id"] for g in gs]
    assert len(ids) == len(set(ids)) and all(i.split("/")[1].startswith("pick_and_place_simple-") for i in ids)
    bowl = next(g for g in gs if g["id"] == "train/pick_and_place_simple-Bowl-None-Fridge-6")
    assert bowl["label"] == "bowl → fridge · kitchen 6" and bowl["room"] == "kitchen"
    trial = demo.resolve("Bowl-None-Fridge-6")
    for name in ("pick_and_place_simple-Bowl-None-Fridge-6", bowl["id"], str(trial.parent), str(trial)):
        assert demo.resolve(name) == trial
    with pytest.raises(SystemExit):
        demo.resolve("Bowl-None-Fridge-999")
    cfg, m, fetch, _ = demo.setup(trial, tmp_path / "root")
    g = json.loads((tmp_path / "root" / "games.json").read_text())
    assert g["current"] == bowl["id"] and len(g["games"]) == len(gs)
    v3 = yaml.safe_load(cfg.read_text())["v3"]
    assert v3["games"] == str(tmp_path / "root" / "games.json") and v3["game_request"] == str(tmp_path / "root.next.json")
    assert list(fetch) == ["bowl1", "fridge1"]


def test_a_room_steps_on_after_the_episodes_own_goal(tmp_path):
    """alf-tasks s-e9cc8fae step 1: the game is the room's state only. TextWorld's gym env freezes once the
    episode's goal holds (every later step repeats the last observation); a room is played on the PDDL env
    underneath, which steps on — the tomato into the microwave (the episode's goal: `won` reported, `done` never),
    then out again and into the fridge. A room install has no task in its map and its packages say `room`."""
    import re
    import gen_hier
    sys.path.insert(0, os.path.join(ROOT, "experiments"))
    import demo
    from alf_gym import Game
    trial = demo.resolve("Tomato-None-Microwave-13")
    plays = {}
    for room in (False, True):
        g = Game()
        o = g.open(str(trial / "game.tw-pddl"), max_steps=100, room=room)
        n = o["handles"]["to_name"]
        h = lambda s: re.sub(r"\b([a-z]+\d+)\b", lambda m: n.get(m.group(1), m.group(1)), s)
        rs = [g.step(h(c)) for c in ("go to countertop3", "take tomato1 from countertop3", "go to microwave1", "open microwave1",
                                     "move tomato1 to microwave1", "take tomato1 from microwave1", "go to fridge1", "open fridge1",
                                     "move tomato1 to fridge1")]
        plays[room] = rs
    assert plays[False][4]["won"] and plays[False][4]["done"] and not any(r["changed"] for r in plays[False][5:])   # the gym env: frozen
    r = plays[True]
    assert r[4]["won"] and not any(x["done"] for x in r) and all(x["changed"] for x in r)                             # the room: steps on
    assert "inrecep(tomato1,fridge1)" in r[-1]["dynamic"] and not r[-1]["won"]
    out = gen_hier.install(str(trial), str(tmp_path / "root"), person=True, room=True)
    m = json.load(open(tmp_path / "root" / "domains" / "hier" / ".map.json"))
    assert m["task"] == {"targets": [], "dests": []}
    assert all(json.load(open(os.path.join(out[s], "game.json"))).get("room") for s in ("task", "nav", "access", "grasp", "place"))
    from semantic_map import text_map
    tm = text_map(str(trial), room=True)
    assert tm["task"]["text"] == "" and tm["task"]["episode"] == "Put a tomato in the microwave."
    assert "give the agent a task, then another" in tm["card"]["about"][0] and not any("new game\" first" in c for c in tm["card"]["cannot"])
    rooms = demo.room_list()
    assert len({(x["room"], x["scene"]) for x in rooms}) == len(rooms) and demo.resolve("kitchen 13").parent.name.endswith("-13")
