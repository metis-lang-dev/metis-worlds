"""hier_agent.py — alf-hierarchy step 2's replay: one ALFWorld game through metis-agent's service (the console's
backend: the orchestrator on E2B, a domain agent per specialist package, the wire) with the
person's words typed into the ATTENDED card and the sub-goals activated by hand.

    ALFWORLD_DATA=… .venv/bin/python experiments/hier_agent.py WORLD GAME_DIR RUN_DIR "the person's words" [--port 8397]

Runs under the world's venv; the service under metis-agent's ($METIS_AGENT_DIR, default the
sibling metis-agent; its py/.venv), the card generator metis-catalog's tools/intents.py
($METIS_CATALOG_DIR, default the sibling metis-catalog).

1. The task's package (gen_hier, intents=True, person mode: nothing in #init) is the one domain
   the service serves; the person's words go in as say_text: the orchestrator's turn holds the
   task's card alone, its J lands as fetch(O, R) in the task's program.
2. The task emits a sub-goal (the host's log: the out atom, its tokens) — by hand, as the
   driver's table says (gen_hier.HANDLES): deactivate the task; generate the specialist's package
   over the game as it is now (this driver's mirror of the game, the commands so far to replay);
   activate it (the wire's activate: hot-installed from its manifest); type the sub-goal into its
   card (the wire's intent{domain, id, j}: no model); wait for its result in the log; mirror the
   commands it sent; deactivate it.
3. The task's next package with its tokens and the result in #init; activate it; back to 2,
   until done, stuck or wrong_dest.
The record: RUN_DIR/replay.json (every step: domain, J, the atoms out, the commands, won) and
RUN_DIR/frames.jsonl (every frame the service sent)."""
import json
import os
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path

WORLD, GAME, RUN, WORDS = sys.argv[1:5]
PORT = int(sys.argv[sys.argv.index("--port") + 1]) if "--port" in sys.argv else 8397
def _sibling(name):
    """The first parent of the world that holds a checkout NAME (metis-worlds/alfworld/world → the
    checkouts beside metis-worlds; baseline.metis_py walks the same way)."""
    d = Path(WORLD).resolve()
    for _ in range(4):
        d = d.parent
        if (d / name).is_dir():
            return d / name
    return d / name


AGENT_PY = Path(os.environ.get("METIS_AGENT_DIR") or _sibling("metis-agent")) / "py"
CATALOG_TOOLS = Path(os.environ.get("METIS_CATALOG_DIR") or _sibling("metis-catalog")) / "tools" / "intents.py"
sys.path.insert(0, os.path.join(WORLD, "world"))
import gen_hier  # noqa: E402
import gen_instance  # noqa: E402
from alf_host import AlfHost  # noqa: E402


from wire import Wire  # noqa: E402  (the stdlib client: experiments/wire.py)


import importlib.util  # noqa: E402
_s = importlib.util.spec_from_file_location("catalog_intents", CATALOG_TOOLS)
intents = importlib.util.module_from_spec(_s)
_s.loader.exec_module(intents)

run = Path(RUN)
shutil.rmtree(run, ignore_errors=True)
cat, stage = run / "catalog", run / "stage"
(cat / "domains").mkdir(parents=True)
(cat / "hier").mkdir()
for s_ in gen_hier.SPECS:
    shutil.copy(os.path.join(WORLD, "domains", "hier", s_ + "_domain.llp"), cat / "hier")
LOG = run / "alf.log"

# the driver's mirror of the game (hier.py's): the flat package gives the handles and the game
flat, _, _ = gen_instance.generate(GAME, str(stage))
mirror = AlfHost(os.path.dirname(flat))
info = json.load(open(os.path.join(os.path.dirname(flat), "game.json")))
info = dict(info, static=sorted(mirror.static), task_type=mirror.task, params=mirror.params)
(stage / "hier-out").mkdir(parents=True, exist_ok=True)
smap = gen_hier.build_map(str(stage / "hier-out" / ".map.json"), info, mirror)   # the room as data (semantic-map s-d4270bed)
smap.project(*gen_hier.args_of(gen_hier.seed(info)[0]))
shutil.copy(os.path.join(WORLD, "domains", "hier", "capacity.llp"), cat / "hier")


def package(spec, k, init, replay):
    """The activation's package, served from the catalog as <spec>_<k> (its manifest, its card,
    the card's generated grammar and prompts, the host shim under the name the agent looks for)."""
    p = Path(gen_hier.generate(GAME, str(stage / "hier-out"), spec, k, info, smap, mirror.reading(), init, replay,
                               intents=True)).parent
    name = "%s_%d" % (spec, k)
    d = cat / "domains" / name
    shutil.copytree(p, d)
    shutil.copy(d / "alf_host.py", d / ("%s_host.py" % name))
    spec_ = intents.load_from(d)
    (d / "intent").mkdir()
    (d / "intent" / ("%s.gbnf" % name)).write_text(intents.grammar(spec_))
    (d / "intent" / ("%s-prompt.txt" % name)).write_text(intents.prompt(spec_))
    (d / "intent" / ("%s-spoken.txt" % name)).write_text(intents.spoken(spec_))
    return name


def config(first):
    c = {"model": "../go/models/gemma4/gemma-4-E2B-it-Q4_K_M.gguf", "template": "gemma4",
         "stop_words": ["stop", "halt", "freeze", "quiet"],
         "v3": {"prompt": ["../go/grammar/v3-orchestrator.txt"], "catalog": [first], "loaded": [first],
                "n_ctx": 16384, "tick_ms": 500, "journal": str(run / "journal.jsonl")},
         "domains": {"names": [first], "case": "live", "seed": 1, "clocks": [{"domain": first, "n": 1}],
                     "trace": True, "records": "catalog", "narrator_n_ctx": 8192, "seat_n_ctx": 8192},
         "ws": {"addr": "127.0.0.1:%d" % PORT, "ui": "../console", "lib": "../../fsttm-web/lib"}}
    import yaml
    (run / "config.yaml").write_text(yaml.safe_dump(c, sort_keys=False))
    return run / "config.yaml"


frames, lock = [], threading.Lock()


def reader(w):
    with open(run / "frames.jsonl", "w") as f:
        while True:
            m = w.recv()
            if m is None:
                return
            f.write(json.dumps(m) + "\n")
            f.flush()
            with lock:
                frames.append(m)


def wait_frame(pred, timeout=120):
    t0, seen = time.time(), 0
    while time.time() - t0 < timeout:
        with lock:
            new = frames[seen:]
            seen = len(frames)
        for m in new:
            if pred(m):
                return m
        time.sleep(0.1)
    raise TimeoutError("no frame matched in %ds" % timeout)


def log_since(off):
    if not LOG.exists():
        return [], off
    with open(LOG) as f:
        f.seek(off)
        data = f.read()
        return [json.loads(l) for l in data.splitlines() if l.strip()], off + len(data.encode())


def traced(domain, preds):
    """The atoms of `preds` the domain's last fired clause produced (its dlg-trace)."""
    with lock:
        recs = [m["rec"] for m in frames if m.get("ev") == "journal" and m["rec"].get("kind") == "dlg-trace"
                and m["rec"].get("domain") == domain]
    for r in reversed(recs):
        for f in reversed(r.get("fired") or []):
            got = [a for a in f.get("produce") or [] if a.split("(")[0] in preds]
            if f.get("kind") == "clause" and got:
                return got
    return []


def wait_out(off, domain=None, spec=None, timeout=120):
    """The host's log from offset `off` until a tick with an out atom: (out, tokens, commands, offset).
    A command the game ends on (won) ends the domain's episode before its next tick: the agent
    beats a world whose episode is over no more, so the result is the trace's."""
    t0, cmds = time.time(), []
    while time.time() - t0 < timeout:
        recs, off = log_since(off)
        for r in recs:
            if "rule" in r:
                cmds.append(r)
            if r.get("tick") and r.get("out"):
                return r["out"], r["tokens"], cmds, off
        if cmds and cmds[-1].get("won") and domain:
            time.sleep(1.0)
            got = traced(domain, set(gen_hier.SPECS[spec]["out"]))
            if got:
                return got, [], cmds, off
        time.sleep(0.2)
    raise TimeoutError("no result in the host's log in %ds" % timeout)


J = {"goto": lambda a: {"intent": "GO", "receptacle": a[0].upper()},
     "open": lambda a: {"intent": "OPEN", "receptacle": a[0].upper()},
     "take": lambda a: {"intent": "TAKE", "object": a[0].upper()},
     "put": lambda a: {"intent": "PUT", "object": a[0].upper(), "receptacle": a[1].upper()}}

steps, commands = [], []
first = package("task", 0, [], [])
env = dict(os.environ, METIS_CATALOG=str(cat), METIS_ALF_LOG=str(LOG), PYTHONPATH=str(AGENT_PY))
svc = subprocess.Popen(["systemd-run", "--user", "--scope", "-q", "-p", "MemoryMax=6G", "nice",
                        str(AGENT_PY / ".venv" / "bin" / "python"), "-m", "metis_agent.service",
                        "--config", str(config(first)), "--no-wait-viewer"],
                       cwd=str(AGENT_PY), env=env, stdout=open(run / "service.log", "w"), stderr=subprocess.STDOUT)
outcome, w = "running", None
try:
    for _ in range(240):
        try:
            w = Wire("ws://127.0.0.1:%d/ws" % PORT)
            break
        except OSError:
            if svc.poll() is not None:
                raise SystemExit("the service exited: see %s" % (run / "service.log"))
            time.sleep(0.5)
    threading.Thread(target=reader, args=(w,), daemon=True).start()
    w.send({"ev": "hello"})
    wait_frame(lambda m: m.get("ev") == "catalog" or "domains" in m, 30)
    off = 0
    # 1. the person's words through the attended card (the task's, the one the turn serves)
    w.send({"ev": "say_text", "id": "p1", "text": WORDS})
    said = wait_frame(lambda m: m.get("ev") == "intent" and m.get("id") == "p1", 120)
    out, tokens, cmds, off = wait_out(off)
    steps.append({"k": 0, "domain": first, "by": "person", "words": WORDS, "j": said.get("intent"),
                  "voice": said.get("voice"), "out": out, "tokens": tokens})
    print("task_0  %r → %s → %s" % (WORDS, json.dumps(said.get("intent")), out), flush=True)
    cur, k = first, 0
    while True:
        goal = out[0]
        base = goal.split("(")[0]
        if base in ("done", "stuck", "wrong_dest"):
            outcome = goal
            break
        # 2. by hand: the specialist the table names, activated, the sub-goal typed into its card
        spec = gen_hier.HANDLES[base]
        k += 1
        w.send({"ev": "deactivate", "domain": cur})
        wait_frame(lambda m: m.get("ev") == "domain_ack" and m.get("domain") == cur, 30)
        name = package(spec, k, [], commands)
        w.send({"ev": "activate", "domain": name})
        ack = wait_frame(lambda m: m.get("ev") == "domain_ack" and m.get("domain") == name, 120)
        if ack.get("error"):
            raise SystemExit("activate %s: %s" % (name, ack["error"]))
        j = J[base]([smap.handle(a) or a for a in gen_hier.args_of(goal)])   # the card speaks the room: the goal's roles as things
        w.send({"ev": "intent", "domain": name, "id": "g%d" % k, "j": j})
        iack = wait_frame(lambda m: m.get("ev") == "intent_ack" and m.get("id") == "g%d" % k, 60)
        if iack.get("error"):
            raise SystemExit("intent %s: %s" % (name, iack["error"]))
        res, _, cmds, off = wait_out(off, name, spec)
        for c in cmds:                                  # the driver's mirror does what the specialist did
            mirror._take(mirror.gym.call("step", command=c["command"]))
            commands.append(c["command"])
        steps.append({"k": k, "domain": name, "by": "hand", "goal": goal, "j": j, "out": res,
                      "commands": [c["command"] for c in cmds], "refused": [c["command"] for c in cmds if not c["admissible"]],
                      "won": bool(cmds and cmds[-1].get("won"))})
        print("%-7s %s → %s  %s" % (name, json.dumps(j), res, [c["command"] for c in cmds]), flush=True)
        if mirror.won:                                  # the game is over: no task activation has a beat to run
            outcome = "won (%s)" % res[0]
            break
        w.send({"ev": "deactivate", "domain": name})
        wait_frame(lambda m: m.get("ev") == "domain_ack" and m.get("domain") == name, 30)
        # 3. the task again: its tokens and the result in its start
        k += 1
        cur = package("task", k, tokens + res, commands)
        w.send({"ev": "activate", "domain": cur})
        ack = wait_frame(lambda m: m.get("ev") == "domain_ack" and m.get("domain") == cur, 120)
        if ack.get("error"):
            raise SystemExit("activate %s: %s" % (cur, ack["error"]))
        out, tokens, _, off = wait_out(off)
        steps.append({"k": k, "domain": cur, "by": "hand", "out": out, "tokens": tokens})
        print("%-7s → %s" % (cur, out), flush=True)
        if k > 30:
            outcome = "activations exhausted"
            break
finally:
    won = mirror.won
    json.dump({"game": GAME, "words": WORDS, "outcome": outcome, "won": won, "commands": commands, "steps": steps},
              open(run / "replay.json", "w"), indent=1)
    print("outcome %s, won %s, %d commands; %s" % (outcome, won, len(commands), run / "replay.json"), flush=True)
    if w:
        w.close()
    svc.terminate()
    try:
        svc.wait(20)
    except subprocess.TimeoutExpired:
        svc.kill()
    mirror.gym.close()
