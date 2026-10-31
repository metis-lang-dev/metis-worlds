"""road_hier.py — the road installed for metis-agent's service on its own page (road-agent s-357becc7): the tree of road/domains (responder, planner, road_director, as
experiments/road_tree.py runs it) over the SUMO host, the task that takes the person's words (domains/task, the local model reads them), the run's spec, the world's card and
the service's config. The planner drives; the person asks.

    python world/road_hier.py ROOT --agent AGENT_PY [--port P] [--scenario S] [--seed N]     ROOT/run.json, ROOT/world-map.json, ROOT/.run/config.yaml
"""
import argparse
import json
import os
import shutil

import yaml

HERE = os.path.dirname(os.path.abspath(__file__))
WEB = os.path.join(os.path.dirname(HERE), "web")
NAMES = ["responder", "planner", "road_director", "task"]
CARD = {"title": "The road, on SUMO", "about": ["An RSS road world: the responder answers every 0.1 s, the planner plans every second, the restrictor is the shield.",
                                                "The stack drives. You may ask; it decides, and it may say not now."],
        "asks": [{"say": "take it easy", "what": "a pace: easy, normal or brisk"}, {"say": "go to the left lane", "what": "the left or the right lane, when it is safe"},
                 {"say": "pass this car", "what": "get past the car ahead, when it is safe"}, {"say": "stay behind him", "what": "no lane changes"},
                 {"say": "carry on as usual", "what": "forget what you asked"}, {"say": "what's around us", "what": "the cars it sees, as it believes them"}],
        "cannot": ["steer, brake or stop for you: the stack holds the controls"], "source": "metis-worlds road/world/road_hier.py"}


def intent_files(task_dir):
    """The task's grammar and prompts from its intent.yaml (metis.intents), beside it: generated, not tracked."""
    from pathlib import Path
    from metis import intents
    intents.ROOT = Path(task_dir).parents[1]
    spec, d = intents.load_from(task_dir), Path(task_dir) / "intent"
    d.mkdir(exist_ok=True)
    for fn, text in (("task.gbnf", intents.grammar(spec)), ("task-prompt.txt", intents.prompt(spec)), ("task-spoken.txt", intents.spoken(spec))):
        (d / fn).write_text(text)


def install(root, agent_py, port=8400, scenario="straight", seed=1):
    intent_files(os.path.join(os.path.dirname(HERE), "domains", "task"))
    if os.path.exists(root):
        shutil.rmtree(root)
    os.makedirs(os.path.join(root, ".run"))
    root = os.path.abspath(root)
    run = {"scenario": scenario, "seed": int(seed), "world": "sumo", "page": True, "key": "page",
           "work": os.path.join(root, "work"), "log": os.path.join(root, "log.jsonl")}
    os.makedirs(run["work"])
    json.dump(run, open(os.path.join(root, "run.json"), "w"), indent=1)
    doc = os.path.join(root, "world-map.json")
    json.dump({"world": "road", "card": CARD}, open(doc, "w"))
    c = yaml.safe_load(open(os.path.join(agent_py, "config.live.yaml")))
    c["model"] = os.path.join(os.path.abspath(agent_py), c["model"])
    c["v3"].update(journal=os.path.join(root, "journal.jsonl"), catalog=[], loaded=NAMES, director="road_director", world_map=doc, tick_ms=1)   # the responder's host holds the pace
    c["domains"].update(names=NAMES, seed=int(seed), narrate=None, consult=False, records=None, quiet=[], pairs=[], clocks=[{"domain": d, "n": 1} for d in NAMES], tick=True)
    c["ws"] = {"addr": "127.0.0.1:%d" % port, "ui": WEB}
    path = os.path.join(root, ".run", "config.yaml")
    yaml.safe_dump(c, open(path, "w"), sort_keys=False)
    return path


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("root")
    ap.add_argument("--agent", required=True)
    ap.add_argument("--port", type=int, default=8400)
    ap.add_argument("--scenario", default="straight")
    ap.add_argument("--seed", type=int, default=1)
    a = ap.parse_args()
    print(install(a.root, a.agent, a.port, a.scenario, a.seed))
