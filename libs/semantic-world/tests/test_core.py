"""semantic_world's core and its room adapter on a synthetic household (no world, no game): the store, the belief
steps, the stable projection, the port contract, the room's text and view modes."""
import json

import pytest

from semantic_world import bayes, ports, project
from semantic_world.room import SemanticMap, spoken, thor_id, want_handle
from semantic_world.store import Store
from semantic_world.world import World, open_map

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


def test_a_kind_wanted_in_sight_of_places_has_looked_into_them(tmp_path):
    """map-queries step 3 (the harness's kettle, then the apple): a kind wanted while the robot stands at places that
    could hold it has looked into them already (a sighting would have resolved it): they are looked, out of its
    belief, absent at once in the reading; the existence prior keeps the mass the look took."""
    st = STATIC + ["cancontain(countertop_t,kettle_t)", "cancontain(fridge_t,kettle_t)"]
    m = SemanticMap.build(str(tmp_path / "map.json"), st, DYN, [], [], view=True, room=True)
    m.observe(["at(loc1)", "inrecep(apple1,countertop1)"])            # standing at the countertops: no kettle there
    assert m.want_kind(m.load(), "kettle") == "kettle"
    d = m.load()
    assert set(d["looked"]["kettle"]) == {"countertop1", "countertop2"} and d["belief"]["kettle"] == {"fridge1": 1.0}
    assert set(d["belief0"]["kettle"]) == {"countertop1", "countertop2", "fridge1"}
    m.project("kettle", "microwave1")
    assert not any(a.startswith("inrecep(target,") and m.binding()[a[15:-1]] != "fridge1"
                   for a in m.role_reading({}))


def test_a_search_that_gave_up_does_not_keep_the_target(tmp_path):
    """The user's session: the apple moved, a kettle search given up, then the apple again: its fetch was bound to the kettle
    still wanted ("Apple 1 is not what this task fetches"). In a room the thing named is the target; the kind stays
    wanted with what was learnt, so asking for it again answers from its belief."""
    st = STATIC + ["cancontain(countertop_t,kettle_t)", "cancontain(fridge_t,kettle_t)"]
    m = SemanticMap.build(str(tmp_path / "map.json"), st, DYN, [], [], view=True, room=True)
    m.observe(["at(loc1)", "inrecep(apple1,countertop1)"])
    m.intent_atom("fetch(kettle,fridge1)")
    assert m.binding()["target"] == "kettle"
    assert m.intent_atom("fetch(apple1,fridge1)") == "fetch(target,dest)" and m.binding()["target"] == "apple1"
    assert m.load()["things"]["kettle"]["wanted"]
    assert m.intent_atom("fetch(kettle,fridge1)") == "fetch(target,dest)" and m.binding()["target"] == "kettle"


def test_the_room_names():
    assert thor_id("countertop_bar__minus_01_dot_87_bar__plus_00_dot_96_bar__plus_01_dot_80") == ("countertop", -1.87, 0.96, 1.8)
    assert spoken("cabinet12") == "cabinet 12" and want_handle("tomato2") == "tomato"


def test_the_query_api(tmp_path):
    """map-queries s-396939dc step 1: one query API — bind (the dialog side), level (standing level ports), weight
    (standing categorical ports), next (the argmax of a place belief, ties by place id), observe — and a room's search
    prior: where the kind usually starts per receptacle of each type, times compatibility, normalized over the room's
    places; a kind the compatibility never names is a logged uniform fallback, never a silent {}."""
    st = STATIC + ["cancontain(countertop_t,kettle_t)", "cancontain(fridge_t,kettle_t)", "cancontain(microwave_t,kettle_t)"]
    m = SemanticMap.build(str(tmp_path / "map.json"), st, DYN, [], [], view=True, room=True)
    d = m.load()
    d["place_rate"] = {"kettle_t": {"countertop_t": 4.0, "fridge_t": 1.0}}         # none starts in the microwave
    d["presence_prior"] = {"kettle_t": 0.5}
    m.save()
    assert m.want_kind(m.load(), "kettle") == "kettle"
    bel = m.load()["belief"]["kettle"]
    z = 4.0 + 4.0 + 1.0 + 0.5                                                          # two countertops, the fridge, the microwave (half the smallest rate)
    assert abs(bel["countertop1"] - 4.0 / z) < 1e-9 and abs(bel["microwave1"] - 0.5 / z) < 1e-9 and abs(sum(bel.values()) - 1) < 1e-9
    assert m.next("kettle") == "countertop1" and m.next("kettle", excluded=["countertop1"]) == "countertop2"
    assert m.level("presence", ("kettle",)) == "doubtful"
    # bind: the places are known at once, a thing once seen (view mode): the tomatoes are not seen yet; the wanted kettle is
    assert m.bind("countertop") == ["countertop1", "countertop2"] and m.bind("kettle") == ["kettle"]
    assert m.bind("tomato") == [] and m.bind("banana") == []
    with pytest.raises(KeyError):
        m.level("fetch_risk", ())
    d = m.load()                                                                       # ties: by the place's id
    d["belief"]["kettle"] = {"fridge1": 0.5, "countertop1": 0.5}
    m.save()
    assert m.next("kettle") == "countertop1"
    d = m.load()                                                                       # nothing known of the kind: uniform, logged
    d["compat"], d["place_rate"] = {"apple_t": ["fridge_t"]}, {}
    m.save()
    p = m._prior("kettle")
    assert p and len(set(round(x, 9) for x in p.values())) == 1
    assert any(json.loads(l).get("kind") == "prior-fallback" for l in open(m.journal))


def _two_rooms(tmp_path):
    a = SemanticMap.build(str(tmp_path / "a.json"), STATIC, DYN, ["tomato1", "tomato2"], ["microwave1"], view=True)
    st = ["recat(sink1,loc1)", "recat(shelf1,loc2)", "notopenable(sink1)", "notopenable(shelf1)", "otype(soap1,soap_t)",
          "rtype(sink1,sink_t)", "rtype(shelf1,shelf_t)", "cancontain(sink_t,soap_t)", "cancontain(shelf_t,soap_t)", "pickupable(soap1)"]
    b = SemanticMap.build(str(tmp_path / "b.json"), st, ["at(loc0)", "inrecep(soap1,shelf1)"], ["soap1"], ["sink1"], view=True)
    return a, b


def test_a_world_keeps_each_maps_state_across_enter_and_leave(tmp_path):
    """rooms s-b51a2e80 step 1: named maps, one active; the query API answers on the active map; a map's state is its own
    and survives leaving it; an unknown name is refused and leaves the active map as it was."""
    a, b = _two_rooms(tmp_path)
    w = World({"kitchen": a, "bathroom": b}, active="kitchen")
    assert w.map_names() == ["bathroom", "kitchen"] and w.active == "kitchen" and "bathroom" in w
    assert w.bind("countertop") == ["countertop1", "countertop2"] and w.bind("sink") == []
    w.observe(["at(loc1)", "inrecep(apple1,countertop1)"])                  # the kitchen: both countertops looked into
    assert set(w.load()["looked"]["tomato"]) == {"countertop1", "countertop2"}
    assert w.enter("bathroom") is b and w.active == "bathroom"
    assert w.bind("sink") == ["sink1"] and w.bind("countertop") == [] and not w.load().get("looked")
    w.observe(["at(loc2)", "inrecep(soap1,shelf1)"])
    w.enter("kitchen")
    assert set(w.load()["looked"]["tomato"]) == {"countertop1", "countertop2"} and w.next("tomato") == "fridge1"
    with pytest.raises(KeyError):
        w.enter("attic")
    assert w.active == "kitchen"
    with pytest.raises(AttributeError):
        World({"kitchen": a}).bind("tomato")                                 # none active: said, not a None


def test_a_world_on_disk_is_followed_by_every_host_open_on_it(tmp_path):
    """A host per domain, each with its own World on the one file: an enter through one is what every other reads next, and
    each map's state stays on disk across it."""
    a, b = _two_rooms(tmp_path)
    p = str(tmp_path / "x.world.json")
    host1 = World(path=p, make=SemanticMap)
    host1.add_map("kitchen", a.path)
    host1.add_map("bathroom", b.path)
    host1.enter("kitchen")
    host2 = open_map(p, SemanticMap)
    assert isinstance(host2, World) and host2.active == "kitchen" and host2.bind("countertop")
    host2.observe(["at(loc1)", "inrecep(apple1,countertop1)"])
    assert host1.load()["agent"]["at"] == "loc1"                              # one document: the other host reads the write
    host1.enter("bathroom")
    assert host2.active == "bathroom" and host2.bind("sink") == ["sink1"] and host2.path == b.path
    host2.enter("kitchen")
    assert host1.load()["agent"]["at"] == "loc1" and set(host1.load()["looked"]["tomato"]) == {"countertop1", "countertop2"}
    assert any(json.loads(l).get("kind") == "enter" for l in open(a.journal))
    assert isinstance(open_map(a.path, SemanticMap), SemanticMap)             # a single map's file: the map itself


def test_a_worlds_own_faces_shadow_nothing_a_map_has():
    """A host reads the active map through the World as through the map: a World attribute named like a map's would answer
    instead of it (World.names over SemanticMap.names: the lines said roles, not things)."""
    from semantic_world.grid import GridMap
    from semantic_world.mixed import MixedMap
    own = {a for a in vars(World) if not a.startswith("__")}
    for cls in (SemanticMap, GridMap, MixedMap):
        assert not own & {a for a in dir(cls) if not a.startswith("__")}, cls
