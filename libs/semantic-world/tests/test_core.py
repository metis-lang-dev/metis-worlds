"""semantic_world's core and its room adapter on a synthetic household (no world, no game): the store, the belief
steps, the stable projection, the port contract, the room's text and view modes."""
import json

from semantic_world import bayes, ports, project
from semantic_world.room import SemanticMap, spoken, thor_id, want_handle
from semantic_world.store import Store

# a kitchen of four receptacles at three locations, two tomatoes, an apple; the robot at loc0 (no receptacle)
STATIC = ["recat(countertop1,loc1)", "recat(countertop2,loc1)", "recat(fridge1,loc2)", "recat(microwave1,loc3)",
          "openable(fridge1)", "openable(microwave1)", "pickupable(tomato1)", "pickupable(tomato2)", "pickupable(apple1)",
          "otype(tomato1,tomato_t)", "otype(tomato2,tomato_t)", "otype(apple1,apple_t)",
          "rtype(countertop1,countertop_t)", "rtype(countertop2,countertop_t)", "rtype(fridge1,fridge_t)",
          "rtype(microwave1,microwave_t)", "cancontain(countertop_t,tomato_t)", "cancontain(fridge_t,tomato_t)",
          "cancontain(microwave_t,tomato_t)", "cancontain(countertop_t,apple_t)"]
DYN = ["at(loc0)", "inrecep(tomato1,countertop2)", "inrecep(tomato2,fridge1)", "inrecep(apple1,countertop1)"]


def test_the_store_reads_again_what_another_writer_wrote(tmp_path):
    a, b = Store(str(tmp_path / "m.json"), journal=str(tmp_path / "j.jsonl")), Store(str(tmp_path / "m.json"))
    a.data = {"belief": {}, "n": 1}
    a.save()
    assert b.load() == {"belief": {}, "n": 1}
    b.data["n"] = 2
    b.save()
    assert a.load()["n"] == 2                               # the mtime cache saw the other writer
    a.log("project", binding={"p1": "x"})
    assert json.loads(open(tmp_path / "j.jsonl").read())["kind"] == "project"


def test_bayes_seen_missed_predict_and_exists():
    d = {"things": {"t": {"in": None}}, "belief": {"t": {"a": 0.5, "b": 0.25, "c": 0.25}}}
    assert bayes.missed(d, "a", {}, lambda t: {}) == ["t"]
    assert d["belief"]["t"] == {"b": 0.5, "c": 0.5} and d["looked"]["t"] == ["a"] and d["exists"]["t"] < 0
    assert bayes.missed(d, "a", {}, lambda t: {}) == []     # nothing believed there: unchanged (occluded is the same)
    assert bayes.seen(d, "t", "c") and d["belief"]["t"] == {"c": 1.0} and d["things"]["t"]["in"] == "c"
    assert not bayes.seen(d, "t", "c")                       # the same sighting: no change, exists still rises
    assert bayes.seen(d, "t", None) and "t" not in d["belief"]   # in hand
    for _ in range(20):
        bayes.seen(d, "t", "c")
    assert d["exists"]["t"] == bayes.L_MAX
    d["belief"]["t"] = {"c": 1.0}
    assert not bayes.predict(d, 1)                           # identity without models
    assert bayes.predict(d, 1, {"t": lambda bel, dt: {"c": 0.5, "b": 0.5}}) and d["belief"]["t"] == {"c": 0.5, "b": 0.5}
    d["belief"]["t"] = {"b": 0.5}
    d["looked"] = {}
    assert bayes.missed(d, "b", {}, lambda t: {"z": 1.0}) == ["t"] and d["belief"]["t"] == {"z": 1.0}   # none left: the prior
    n = bayes.normalized({"a": 0.2, "b": 0.6, "x": 0.2}, ["a", "b"])
    assert set(n) == {"a", "b"} and abs(n["a"] - 0.25) < 1e-9 and abs(n["b"] - 0.75) < 1e-9


def test_the_projection_is_stable():
    b = {"p1": "x", "p2": "y", "p3": "z", "dest": "d"}
    s = project.stable_slots(b, lambda h: h in ("x", "z"), ["w", "x", "v"], 4, bound={"d"})
    assert s == {"p1": "x", "p3": "z", "p2": "w", "p4": "v"}        # x and z keep their roles, the free take the rest
    locs = project.stable_locations({"lhere": "L0", "l2": "L2", "l5": "L9"}, {"L0", "L2", "L3"}, 8)
    assert locs == {"L0": "lhere", "L2": "l2", "L3": "l1"}
    f = project.freeze(b)
    b["p1"] = "q"
    assert f["p1"] == "x"


def test_the_port_contract():
    binding = {"target": "tomato1", "p1": "fridge1", "l1": "loc2"}
    reading = {"inrecep(tomato1,fridge1)": 1, "inrecep(apple1,fridge1)": 1, "at(loc2)": 1, "handsfree": 1}
    assert ports.translate(reading, binding) == {"inrecep(target,p1)": 1, "at(l1)": 1, "handsfree": 1}
    counts = {"inrecep(target,p2)": 1, "want(target)": 1, "at(l1)": 1}
    assert ports.sync_diff({"inrecep(target,p1)": 1, "at(l1)": 1}, counts, {"inrecep", "at"}) == \
        ["+inrecep(target,p1) 1", "-inrecep(target,p2) 1"]           # the program's own token stays
    assert ports.in_room("goto(p1)", binding.get) == "goto(fridge1)" and ports.in_room("done", binding.get) == "done"
    assert ports.say_in_roles("fetch", ["tomato1", "fridge1"], {"tomato1": "target", "fridge1": "p1"}) == "fetch(target,p1)"
    assert ports.names(binding, {"target", "p1"}) == [["p1", "fridge1"], ["target", "tomato1"]]


def test_the_room_in_text_mode(tmp_path):
    m = SemanticMap.build(str(tmp_path / "map.json"), STATIC, DYN, ["tomato1"], ["microwave1"])
    d = m.load()
    assert d["belief"]["tomato1"] == {"countertop2": 1.0} and set(d["things"]) == {"tomato1", "tomato2", "apple1"}
    b = m.project("tomato1", "microwave1")
    assert b["target"] == "tomato1" and b["dest"] == "microwave1" and b["p1"] == "countertop2" and b["lhere"] == "loc0"
    r = m.role_reading({"inrecep(tomato1,countertop2)": 1, "at(loc0)": 1})
    assert r["inrecep(target,p1)"] == 1 and r["at(lhere)"] == 1 and r["recat(p1,l1)"] == 1 and r["notopenable(p1)"] == 1
    assert m.intent_atom("fetch(tomato1,microwave1)") == "fetch(target,dest)"
    assert m.belief("target", "p1") == 1.0 and m.names()[0][0] == "dest"
    assert m.observe(["at(loc1)", "holds(tomato1)", "inrecep(tomato2,fridge1)", "inrecep(apple1,countertop1)"])
    assert "tomato1" not in m.load()["belief"] and m.load()["agent"]["holding"] == "tomato1"


def test_the_room_in_view_mode(tmp_path):
    m = SemanticMap.build(str(tmp_path / "map.json"), STATIC, DYN, ["tomato1", "tomato2"], ["microwave1"], view=True)
    d = m.load()
    assert set(d["things"]) == {"tomato"} and d["prior"] == "cancontain"
    assert d["belief"]["tomato"] == {"countertop1": 1 / 3, "countertop2": 1 / 3, "fridge1": 1 / 3}
    m.project("tomato", "microwave1")
    assert m.binding()["target"] == "tomato"
    m.observe(["at(loc1)", "inrecep(apple1,countertop1)"])            # countertop 1 and 2 seen: no tomato on either
    d = m.load()
    assert d["belief"]["tomato"] == {"fridge1": 1.0} and set(d["looked"]["tomato"]) == {"countertop1", "countertop2"}
    assert "apple1" in d["things"]                                   # the map grows by what it sees
    assert m.role_reading({}).get("absent(target,%s)" % m.role_of(d["look"])) == 1
    m.observe(["at(loc2)", "opened(fridge1)", "inrecep(tomato2,fridge1)"])
    d = m.load()
    assert d["resolved"] == {"tomato": "tomato2"} and m.binding()["target"] == "tomato2"
    assert m.role_reading({})["inrecep(target,%s)" % m.role_of("fridge1")] == 1


def test_the_room_names():
    assert thor_id("countertop_bar__minus_01_dot_87_bar__plus_00_dot_96_bar__plus_01_dot_80") == ("countertop", -1.87, 0.96, 1.8)
    assert spoken("cabinet12") == "cabinet 12" and want_handle("tomato2") == "tomato"
