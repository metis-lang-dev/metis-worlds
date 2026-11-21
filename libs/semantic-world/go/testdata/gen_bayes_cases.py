"""Write bayes_cases.json: scripted runs of semantic_world.bayes (the reference) that the Go port
replays step by step (semworld/parity_test.go). Run from libs/semantic-world:

    python3 go/testdata/gen_bayes_cases.py
"""
import copy
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", ".."))
from semantic_world import bayes  # noqa: E402

GRAPH = {"a": ["b"], "b": ["a", "c"], "c": ["b", "d"], "d": ["c"], "e": []}   # a line, and an island


def doc(places, things):
    return {"places": {p: {} for p in places}, "things": {t: {"in": None} for t in things},
            "belief": {}, "exists": {}, "looked": {}}


def model(spec):
    if spec == "still":
        return bayes.still
    w = spec["walk"]
    toward = None
    if w.get("target"):
        dist = bayes.distances(lambda p: GRAPH[p], w["target"], 1e9)
        toward = lambda n: dist.get(n, 1e9)  # noqa: E731
    return bayes.walk(lambda p: GRAPH[p], toward=toward, stay=w["stay"], bias=w["bias"], speed=w["speed"])


def run(name, places, things, ops):
    d = doc(places, things)
    uniform = lambda t: {p: 1.0 / len(places) for p in places}  # noqa: E731
    steps = []
    for op in ops:
        if op["op"] == "seen":
            ret = bayes.seen(d, op["thing"], op["place"])
        elif op["op"] == "missed":
            ret = bayes.missed(d, op["place"], op["seen_at"], uniform)
        elif op["op"] == "predict":
            ms = {t: model(s) for t, s in op["models"].items()}
            ret = bayes.predict(d, op["dt"], ms, tuple(op["alive"]) if op.get("alive") else None)
        elif op["op"] == "set":
            d["belief"][op["thing"]] = dict(op["belief"])
            ret = True
        steps.append({"op": op, "ret": ret, "doc": {k: copy.deepcopy(d.get(k)) for k in
                                                     ("belief", "exists", "looked", "gone")}})
    return {"name": name, "places": places, "things": things, "steps": steps}


walk = {"walk": {"stay": 0.25, "bias": 1.0, "speed": 1, "target": None}}
hunt = {"walk": {"stay": 0.1, "bias": 1.5, "speed": 1.5, "target": "d"}}
CASES = [
    run("seen-and-in-hand", list("abcd"), ["key"], [
        {"op": "seen", "thing": "key", "place": "b"},
        {"op": "seen", "thing": "key", "place": "b"},
        {"op": "seen", "thing": "key", "place": None},
        {"op": "seen", "thing": "key", "place": "c"}]),
    run("missed-renormalises", list("abcd"), ["cup", "pen"], [
        {"op": "set", "thing": "cup", "belief": {"a": 0.5, "b": 0.3, "c": 0.2}},
        {"op": "set", "thing": "pen", "belief": {"b": 1.0}},
        {"op": "missed", "place": "a", "seen_at": {}},
        {"op": "missed", "place": "b", "seen_at": {"pen": "b"}},
        {"op": "missed", "place": "c", "seen_at": {}},
        {"op": "missed", "place": "b", "seen_at": {}}]),
    run("walk-wander-and-fraction", list("abcde"), ["cat"], [
        {"op": "seen", "thing": "cat", "place": "b"},
        {"op": "predict", "dt": 1, "models": {"cat": walk}},
        {"op": "predict", "dt": 0.3, "models": {"cat": walk}},
        {"op": "predict", "dt": 2.5, "models": {"cat": walk}},
        {"op": "predict", "dt": 0, "models": {"cat": walk}}]),
    run("walk-toward-and-alive", list("abcde"), ["newt", "rock"], [
        {"op": "seen", "thing": "newt", "place": "a"},
        {"op": "seen", "thing": "rock", "place": "e"},
        {"op": "predict", "dt": 1, "models": {"newt": hunt, "rock": "still"}, "alive": [0.5, -0.5]},
        {"op": "predict", "dt": 1.4, "models": {"newt": hunt, "rock": "still"}, "alive": [0.5, -0.5]},
        {"op": "predict", "dt": 1, "models": {"newt": hunt, "rock": "still"}, "alive": [0.5, -0.5]},
        {"op": "predict", "dt": 1, "models": {"newt": hunt, "rock": "still"}, "alive": [0.5, -0.5]}]),
]

if __name__ == "__main__":
    with open(os.path.join(HERE, "bayes_cases.json"), "w") as f:
        json.dump(CASES, f, indent=1, sort_keys=True)
    print("wrote %d cases" % len(CASES))
