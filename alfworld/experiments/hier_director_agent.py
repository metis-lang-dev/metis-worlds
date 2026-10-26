"""hier_director_agent.py — alf-hierarchy step 3 through metis-agent: the DIRECTOR makes the switch inside the agent.
Per game, the hierarchy is installed for the agent (gen_hier.install: the director, the task's person-mode
instance, an empty instance per specialist, one shared commands log), metis-agent's service serves it
with `v3.director` and `v3.serve: active` (the turn holds the active cards only), and the person's words
go in as say_text. From there no hand touches it: the task's sub-goals arrive at the director, which
wakes, forwards (the director host re-instances the specialist; the agent reloads it), sleeps, and ends.

    ALFWORLD_DATA=… .worlds/alf/bin/python experiments/hier_director_agent.py [--split train] [--n 20] [--seed 1]
        [--port 8398] [--out DIR] [--timeout 300]

Runs under the world's venv (gen_hier, the mirror); the service under metis-agent's: the sibling
checkout's py/.venv and models, its code from $METIS_AGENT_DIR (a worktree) when set. The record: OUT/director-agent-<split>-<seed>.json — per
game the words, the J the model typed, the director's beats (dlg-director), the activations, the
turn's size after each restart (dlg-restart n_ctx), the commands, won."""
import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
WORLD = HERE.parent
sys.path.insert(0, str(WORLD / "world"))
sys.path.insert(0, str(HERE))
import families  # noqa: E402
import gen_hier  # noqa: E402
from alf_host import AlfHost  # noqa: E402
from wire import Wire  # noqa: E402

NAMES = ["director", "task", "nav", "access", "grasp", "place"]


def sibling(name):
    d = WORLD
    for _ in range(4):
        d = d.parent
        if (d / name).is_dir():
            return d / name
    return d / name


AGENT_HOME = sibling("metis-agent")                                         # its venv and its models
AGENT_PY = Path(os.environ.get("METIS_AGENT_DIR") or AGENT_HOME) / "py"     # its code: the service runs `-m` there (a worktree's)


def words_of(h):
    """candle1 → candle 1, the way a person names it (the card's guidance: kind and number)."""
    m = re.match(r"^([a-z]+?)(\d+)$", h)
    return "%s %s" % (m.group(1), m.group(2)) if m else h


def fetch_of(flat):
    """The game's own fetch (the driver's seed, gen_hier.seed): → (object, receptacle) the person names."""
    mirror = AlfHost(flat)
    try:
        info = dict(json.load(open(os.path.join(flat, "game.json"))), static=sorted(mirror.static), task_type=mirror.task, params=mirror.params)
    finally:
        mirror.gym.close()
    return gen_hier.args_of(gen_hier.seed(info)[0])


def card_files(root, task_dir):
    """The task card's generated grammar and prompts (metis.intents over this root)."""
    from metis import intents
    intents.ROOT = Path(root)
    spec, name = intents.load_from(task_dir), Path(task_dir).name      # intents.files(name) reads ROOT/domains/<name>: the install nests it under hier/
    d = Path(task_dir) / "intent"
    d.mkdir(exist_ok=True)
    for fn, text in [("%s.gbnf" % name, intents.grammar(spec)), ("%s-prompt.txt" % name, intents.prompt(spec)),
                     ("%s-spoken.txt" % name, intents.spoken(spec))]:
        (d / fn).write_text(text)


def config_dict(run, port):
    """The service's config for the installed hierarchy (the director, serve: active)."""
    return {"model": str(AGENT_HOME / "go/models/gemma4/gemma-4-E2B-it-Q4_K_M.gguf"), "template": "gemma4",
         "stop_words": ["stop", "halt", "freeze", "quiet"],
         "v3": {"prompt": ["../go/grammar/v3-orchestrator.txt"], "catalog": list(NAMES), "loaded": ["director", "task"],
                "serve": "active", "director": "director", "n_ctx": 16384, "tick_ms": 300,
                "journal": str(run / "journal.jsonl")},
         "domains": {"names": list(NAMES), "case": "live", "seed": 1, "clocks": [{"domain": n, "n": 1} for n in NAMES],
                     "trace": True, "records": str(run / "records"), "narrator_n_ctx": 8192, "seat_n_ctx": 8192},
         "ws": {"addr": "127.0.0.1:%d" % port}}


def config(run, port):
    c = config_dict(run, port)
    import yaml
    (run / "config.yaml").write_text(yaml.safe_dump(c, sort_keys=False))
    return run / "config.yaml"


def run_game(game, run, port, timeout):
    run.mkdir(parents=True, exist_ok=True)
    out = gen_hier.install(game, str(run / "root"), person=True)      # the task seeds no fetch: the person's words are its goal
    o, r = fetch_of(out["_flat"])
    for spec in NAMES[1:]:                     # the agent looks for <name>_host.py (the manifest's host: file, metis-agent minihack-acts, not yet)
        shutil.copy(Path(out[spec]) / "alf_host.py", Path(out[spec]) / ("%s_host.py" % spec))
    card_files(run / "root", out["task"])
    words = "bring the %s to the %s" % (words_of(o), words_of(r))
    env = dict(os.environ, METIS_CATALOG=str(run / "root"),
               METIS_ALF_PY=os.environ.get("METIS_ALF_PY", sys.executable))
    svc = subprocess.Popen(["systemd-run", "--user", "--scope", "-q", "-p", "MemoryMax=6G", "nice",
                            str(AGENT_HOME / "py" / ".venv" / "bin" / "python"), "-m", "metis_agent.service",
                            "--config", str(config(run, port)), "--no-wait-viewer"],
                           cwd=str(AGENT_PY), env=env, stdout=open(run / "service.log", "w"), stderr=subprocess.STDOUT)
    frames, lock, w, t0 = [], threading.Lock(), None, time.time()
    rec = {"game": os.path.relpath(game, families.data_root()), "words": words, "fetch": [o, r]}

    def reader():
        while True:
            m = w.recv()
            if m is None:
                return
            with lock:
                frames.append(m)

    def journal(kind):
        with lock:
            return [m["rec"] for m in frames if m.get("ev") == "journal" and m["rec"].get("kind") == kind]
    try:
        for _ in range(400):
            try:
                w = Wire("ws://127.0.0.1:%d/ws" % port)
                break
            except OSError:
                if svc.poll() is not None:
                    raise RuntimeError("the service exited: see %s" % (run / "service.log"))
                time.sleep(0.5)
        threading.Thread(target=reader, daemon=True).start()
        w.send({"ev": "hello", "since": 1e15})
        time.sleep(1.0)
        w.send({"ev": "say_text", "id": "p1", "text": words})
        t1 = time.time()
        while time.time() - t1 < timeout:
            with lock:
                said = next((m for m in frames if m.get("ev") == "intent" and m.get("id") == "p1"), None)
            if said and "j" not in rec:
                rec["j"], rec["voice"] = said.get("intent"), said.get("voice")
            ends = [b for b in journal("dlg-director") if b.get("outcome")]
            if ends:
                rec["outcome"] = ends[-1]["outcome"]
                break
            if svc.poll() is not None:
                raise RuntimeError("the service exited: see %s" % (run / "service.log"))
            time.sleep(0.3)
        else:
            rec["outcome"] = "timeout"
        time.sleep(1.0)
        beats = journal("dlg-director")
        rec["beats"] = [{k: b.get(k) for k in ("arrival", "effects", "goals")} for b in beats]
        rec["activations"] = [g for b in beats for g in (b.get("goals") or [])]
        rec["restarts"] = [{"why": x.get("why"), "n_ctx": x.get("n_ctx"), "intents": x.get("intents")} for x in journal("dlg-restart")]
        rec["turn"] = [{"domain": x.get("domain"), "n_ctx": x.get("n_ctx"), "ms": x.get("ms")} for x in journal("dlg-gen")]
        rec["errors"] = [x for x in journal("dlg-domain") if x.get("error")][:5]
    except Exception as e:  # noqa: BLE001
        rec["outcome"], rec["error"] = "error", "%s: %s" % (type(e).__name__, e)
    finally:
        if w:
            w.close()
        svc.terminate()
        try:
            svc.wait(20)
        except subprocess.TimeoutExpired:
            svc.kill()
    log = run / "root" / "domains" / "hier" / ".commands.jsonl"
    cmds = [json.loads(x) for x in log.read_text().splitlines() if x.strip()] if log.exists() else []
    mirror = AlfHost(out["_flat"])                     # the world as the commands left it: the log stepped into the flat game
    try:
        for c in cmds:
            mirror._take(mirror.gym.call("step", command=c["command"]))
        rec["won"] = bool(mirror.won)
    finally:
        mirror.gym.close()
    rec["commands"] = len(cmds)
    rec["seconds"] = round(time.time() - t0, 1)
    return rec


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--split", default="train")
    ap.add_argument("--task", default="pick_and_place_simple")
    ap.add_argument("--n", type=int, default=20)
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--port", type=int, default=8398)
    ap.add_argument("--timeout", type=float, default=300)
    ap.add_argument("--out", default=str(HERE / "records"))
    a = ap.parse_args(argv)
    games = families.sample(a.split, a.task, a.n, a.seed)
    out = Path(a.out)
    runs = out / ("director-agent-%s-%d" % (a.split, a.seed))
    recs = []
    for i, g in enumerate(games):
        r = run_game(g, runs / ("g%02d" % i), a.port, a.timeout)
        recs.append(r)
        top = max((x["n_ctx"] or 0 for x in (r.get("turn") or []) + (r.get("restarts") or [])), default=None)
        print("%2d %-58s %s %-14s %2d activations, %2d commands, turn ≤ %s tok, %ss  j=%s" % (
            i + 1, r["game"][-58:], "WON " if r.get("won") else "lost", r.get("outcome"), len(r.get("activations") or []),
            r.get("commands", 0), top, r.get("seconds"), json.dumps(r.get("j"))), flush=True)
    summary = {"split": a.split, "task": a.task, "n": len(recs), "seed": a.seed, "won": sum(bool(r.get("won")) for r in recs),
               "games": recs}
    path = out / ("director-agent-%s-%d.json" % (a.split, a.seed))
    path.write_text(json.dumps(summary, indent=1))
    print("won %d/%d; %s" % (summary["won"], len(recs), path), flush=True)


if __name__ == "__main__":
    main()
