"""demo.py — the exploitation demo's agent side in TEXT mode (alf-demo step 2, docs/DEMO.md §4–§5).

    ALFWORLD_DATA=… .worlds/alf/bin/python experiments/demo.py setup GAME_DIR ROOT [--port P] [--view]
    ALFWORLD_DATA=… .worlds/alf/bin/python experiments/demo.py check [--game GAME_DIR] [--out DIR] [--port P]
    ALFWORLD_DATA=… .worlds/alf/bin/python experiments/demo.py games [--n 10] [--split train] [--out DIR]

setup: ROOT becomes the agent's catalog (cwd-root): the game's hierarchy installed for a person
(gen_hier.install, person=True: the director, the task, the specialists, one commands log), the task
card's generated grammar and prompts, the map in text mode (world/semantic_map.py → ROOT/world-map.json),
and ROOT/config.yaml for metis-agent's
service: the director (v3.director), the turn serving the active cards (v3.serve: active), the map
(v3.world_map: /world/map.json, named on every hello as world/map). demo.sh runs it with the page
(web/world.html?live=1).

check: the five-turn script of §5 through the service, with no browser — the person's words by say_text
(E2B types the FETCH into the task card), the director's chain, the world's world/delta per command,
the result lines said, the end; then a person's goal the task refuses (the tomato into the fridge: a
wrong destination), the ask through the band and the cornered place. Asserts each turn's frames, and
writes them as the page's replay (OUT/<name>.run.jsonl: the same frames world.html?replay= plays).

games: N train games by say_text (the step's acceptance): won, the director's beats, every command a
world/delta."""
import argparse
import json
import os
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
import hier_director_agent as hda  # noqa: E402
from wire import Wire  # noqa: E402

WEB = WORLD.parent / "web"
GAME = "train/pick_and_place_simple-Tomato-None-Microwave-13"        # the fixtures' kitchen (web/fixtures)


def setup(game, root, port=8398, view=False, tree=False):
    """ROOT as the demo's catalog; → (config path, the map, the task's fetch). view: the semantic map sees
    only what the robot sees (semantic-map step 3)."""
    root = Path(root)
    if root.exists():
        shutil.rmtree(root)
    out = gen_hier.install(str(game), str(root), person=True, view=view, tree=tree)
    for spec in hda.NAMES[1:]:                 # metis-agent loads a host from <name>_host.py, or the manifest's host: file
        shutil.copy(Path(out[spec]) / "alf_host.py", Path(out[spec]) / ("%s_host.py" % spec))
    hda.card_files(root, out["task"])
    from semantic_map import text_map
    m = text_map(str(game))
    if view:                                   # the page draws what the robot knows: every place dimmed until seen into
        m["view"] = True
        for p in m["places"]:
            p["unseen"] = True
    (root / "world-map.json").write_text(json.dumps(m, indent=1))
    names = list(hda.NAMES)
    run = root / ".run"
    run.mkdir()
    c = hda.config_dict(run, port)
    c["v3"]["world_map"] = str(root / "world-map.json")
    c["v3"]["catalog"] = names
    c["v3"]["loaded"] = ["director", "task"]
    c["domains"]["names"] = names
    c["domains"]["clocks"] = [{"domain": n, "n": 1} for n in names]
    c["ws"]["ui"] = str(WEB)
    if tree:                                   # the tick (specialist-tree s-404d001f step 2): the tree director, domains.tick
        c["domains"]["tick"] = True
    import yaml
    (run / "config.yaml").write_text(yaml.safe_dump(c, sort_keys=False))
    return run / "config.yaml", m, hda.fetch_of(out["_flat"]), out


class Session:
    """metis-agent's service over ROOT, its frames collected."""

    def __init__(self, root, cfg, port):
        env = dict(os.environ, METIS_CATALOG=str(root), PYTHONPATH=os.pathsep.join([str(hda.AGENT_PY)] + [p for p in [os.environ.get("PYTHONPATH")] if p]), METIS_ALF_PY=os.environ.get("METIS_ALF_PY", sys.executable))
        self.svc = subprocess.Popen(["systemd-run", "--user", "--scope", "-q", "-p", "MemoryMax=6G", "nice",
                                     str(hda.AGENT_HOME / "py" / ".venv" / "bin" / "python"), "-m", "metis_agent.service",
                                     "--config", str(cfg), "--no-wait-viewer", "--ui-dir", str(WEB), "--lib-dir", str(WEB / "vendor")],
                                    cwd=str(hda.AGENT_PY), env=env, stdout=open(Path(cfg).parent / "service.log", "w"), stderr=subprocess.STDOUT)
        self.frames, self.lock, self.w = [], threading.Lock(), None
        for _ in range(400):
            try:
                self.w = Wire("ws://127.0.0.1:%d/ws" % port)
                break
            except OSError:
                if self.svc.poll() is not None:
                    raise RuntimeError("the service exited: see %s" % (Path(cfg).parent / "service.log"))
                time.sleep(0.5)
        threading.Thread(target=self._read, daemon=True).start()
        self.w.send({"ev": "hello", "since": 1e15})

    def _read(self):
        while True:
            m = self.w.recv()
            if m is None:
                return
            with self.lock:
                self.frames.append(dict(m, at=time.time()))

    def mark(self):
        with self.lock:
            return len(self.frames)

    def since(self, k):
        with self.lock:
            return list(self.frames[k:])

    def wait(self, pred, k=0, timeout=240):
        t0 = time.time()
        while time.time() - t0 < timeout:
            for f in self.since(k):
                if pred(f):
                    return f
            if self.svc.poll() is not None:
                raise RuntimeError("the service exited")
            time.sleep(0.3)
        return None

    def say(self, words, tid):
        k = self.mark()
        self.w.send({"ev": "say_text", "id": tid, "text": words})
        return k

    def close(self):
        if self.w:
            self.w.close()
        self.svc.terminate()
        try:
            self.svc.wait(20)
        except subprocess.TimeoutExpired:
            self.svc.kill()


def journal(fs, kind):
    return [f["rec"] for f in fs if f.get("ev") == "journal" and f["rec"].get("kind") == kind]


def ended(f):
    return f.get("ev") == "journal" and f["rec"].get("kind") == "dlg-director" and f["rec"].get("outcome")


def as_replay(fs, path, map_url):
    """The frames as the page's replay (world.html?replay=): the wire's frames whose events it plays,
    the map named relative to the file, dt the ms between them."""
    keep = [f for f in fs if f.get("ev", "").startswith("world/") or (f.get("ev") == "journal" and f["rec"].get("kind") in
            ("dlg-wake", "dlg-dispatch", "dlg-domain", "dlg-trace", "dlg-say", "dlg-director"))]
    out, prev = [{"ev": "world/map", "url": map_url, "dt": 0}], None
    for f in keep:
        if f.get("ev") == "world/map":
            continue
        g = {k: v for k, v in f.items() if k not in ("at", "t")}
        g["dt"] = 0 if prev is None else int((f["at"] - prev) * 1000)
        prev = f["at"]
        out.append(g)
    Path(path).write_text("".join(json.dumps(x) + "\n" for x in out))
    return out


def check(game, out_dir, port, tree=False):
    """The five-turn script (DEMO.md §5), twice: the win, and the disengagement. → the report."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    report, problems = {}, []
    o, r = None, None
    for name, words_of_fetch in (("win", None), ("fridge", ("tomato 1", "fridge 1"))):
        root = out_dir / ("root-" + name)
        cfg, m, (o, r), inst = setup(game, root, port=port, tree=tree)
        words = "put the %s in the %s" % (words_of_fetch or (hda.words_of(o), hda.words_of(r)))
        s = Session(root, cfg, port)
        try:
            got = s.wait(lambda f: f.get("ev") == "world/map", timeout=60)
            time.sleep(1.0)
            hello_card = next((f.get("sentence") for f in s.since(0) if f.get("ev") == "narration" and f.get("kind") == "v3-card"), None)
            card_voice, card_status = None, None
            if name == "fridge":
                # the user's "put the pencil in microwave" → unknown with nothing to go on: words the agent
                # takes no task from get the world's card — what it is and what to ask — and it still waits
                k0 = s.say("what can you do?", "p0")
                rep0 = s.wait(lambda f: f.get("ev") == "intent" and f.get("id") == "p0", k0, timeout=120)
                time.sleep(1.0)
                card_voice = (rep0 or {}).get("voice")
                card_status = [f.get("state") for f in s.since(k0) if f.get("ev") == "world/status"]
            k = s.say(words, "p1")
            end = s.wait(ended, k)
            time.sleep(2.0)
            turn = s.since(k)
            log0 = root / "domains" / "hier" / ".commands.jsonl"
            after = {"commands_at_end": sum(1 for x in log0.read_text().splitlines() if x.strip()) if log0.exists() else 0}
            if name == "win":
                # step 3b F7: the game is won and over — another task is refused in words, the status says over
                k2 = s.say("put the %s in the fridge" % hda.words_of(o), "p2")
                rep_ = s.wait(lambda f: f.get("ev") == "intent" and f.get("id") == "p2", k2, timeout=120)
                time.sleep(2.0)
                after["over_voice"] = " ".join(f.get("sentence", "") for f in s.since(k2) if f.get("ev") == "narration") or (rep_ or {}).get("voice")
                after["over_status"] = [f.get("state") for f in s.since(k2) if f.get("ev") == "world/status"]
                # the architect's AlfHost.new_episode as the demo's new game: the same room from its start, the task again
                k4 = s.say("new game", "p4")
                s.wait(lambda f: f.get("ev") == "world/status" and f.get("state") == "waiting", k4, timeout=120)
                after["new_game_status"] = [f.get("state") for f in s.since(k4) if f.get("ev") == "world/status"]
                # opus's 3b user test: a stop while a specialist is on its goal, then the task again from where
                # it stopped (the stop that left the director's state awake sent the next goal to a sleeping domain).
                # Said while nav works; where it lands (before the take, or with the object in hand) is the chain's
                # speed against a spoken stop's latency, so the held case (F12) is taken from wherever it lands
                k5 = s.say(words, "p5")
                mid = s.wait(lambda f: f.get("ev") == "world/status" and f.get("state") == "working" and f.get("domain") == "nav", k5, timeout=300)
                k6 = s.say("stop", "p6")
                rep6 = s.wait(lambda f: f.get("ev") == "intent" and f.get("id") == "p6", k6, timeout=60)
                time.sleep(2.0)
                hand = [(f.get("agent") or {}).get("holding") for f in s.since(k5) if f.get("ev") == "world/delta" and "holding" in (f.get("agent") or {})]
                after["mid_stop"] = {"at": (mid or {}).get("goal"), "voice": (rep6 or {}).get("voice"), "holding": hand[-1] if hand else None,
                                     "asleep": [x for x in (next((f.get("state") for f in reversed(s.since(k6)) if f.get("ev") == "world/hierarchy"), None) or [])
                                                if x.startswith("active(")]}
                if hand and hand[-1]:
                    # the stop landed with the object in hand: no wire frame is before the take by a stop's latency
                    # any more (semantic-map step 2: the chain steps every ~90 ms, a spoken stop lands ~260 ms after
                    # the frame it is said on; the take follows nav's status within one beat), so "a stop before the
                    # take" is not reachable from the wire — this stop IS the stop with the object in hand (the
                    # architect's ruling (a)), and the task asked again carries it on (F12)
                    after["held_stop"] = {"at": hand[-1], "voice": (rep6 or {}).get("voice"), "by": "the mid stop: already holding",
                                          "won_before_the_stop": any(f.get("ev") == "world/status" and f.get("state") == "over" for f in s.since(k5))}
                else:
                    # … else a stop with the object in hand, CONDITION-based (the architect's ruling on spec16's demo
                    # check): said once the errand has taken it (the take's world/delta) and nav reports the carry leg
                    # (working on its goto, after the take), and before its done. An errand that ends before the stop
                    # lands is a case not run (the stop's latency against the chain's), not a miss: a new game and
                    # the case again, at most three times, every try recorded
                    tries, held = [], None
                    for attempt in range(3):
                        if attempt:
                            kn = s.say("new game", "p7n%d" % attempt)
                            s.wait(lambda f: f.get("ev") == "world/status" and f.get("state") == "waiting", kn, timeout=120)
                        k7 = s.say(words, "p7_%d" % attempt)
                        carry = s.wait(lambda f: f.get("ev") == "world/delta" and (f.get("agent") or {}).get("holding"), k7, timeout=300)
                        t_take = (carry or {}).get("at", 0)
                        leg = s.wait(lambda f: f.get("ev") == "world/status" and f.get("state") == "working" and f.get("domain") == "nav"
                                     and f.get("at", 0) > t_take, k7, timeout=60) if carry else None
                        if not leg or any(f.get("ev") == "world/status" and f.get("state") == "over" for f in s.since(k7)):
                            tries.append({"try": attempt, "ran": False, "why": "the errand ended before its carry leg was seen"})
                            continue
                        k8 = s.say("stop", "p8_%d" % attempt)
                        rep8 = s.wait(lambda f: f.get("ev") == "intent" and f.get("id") == "p8_%d" % attempt, k8, timeout=60)
                        time.sleep(2.0)
                        holding = [(f.get("agent") or {}).get("holding") for f in s.since(k7)
                                   if f.get("ev") == "world/delta" and "holding" in (f.get("agent") or {})]
                        # the errand ended first: the game over, or the object put down before the stop (the world's
                        # delta: the over status can reach the wire after the stop's own answer)
                        won = any(f.get("ev") == "world/status" and f.get("state") == "over" for f in s.since(k7)) or not (holding and holding[-1])
                        held = {"at": ((carry or {}).get("agent") or {}).get("holding"), "voice": (rep8 or {}).get("voice"),
                                "by": "a stop on the carry leg (try %d)" % attempt, "won_before_the_stop": won}
                        tries.append({"try": attempt, "ran": not won, "why": "the errand ended before the stop landed" if won else "stopped on the carry leg"})
                        if not won:
                            break
                    after["held_stop"] = dict(held or {"at": None, "voice": None, "won_before_the_stop": None}, tries=tries)
                k9 = s.say(words, "p9")
                end9 = s.wait(ended, k9, timeout=300)
                time.sleep(2.0)
                after["again_outcome"] = end9["rec"]["outcome"] if end9 else "timeout"
            else:
                # step 3b F5: stop is answered and waits; then the ask's first answer, said back, is taken
                ask = next((f for f in reversed(turn) if f.get("ev") == "world/ask"), None)
                after["ask"] = ask
                k2 = s.say("stop", "p2")
                rep_ = s.wait(lambda f: f.get("ev") == "intent" and f.get("id") == "p2", k2, timeout=60)
                time.sleep(1.0)
                after["stop_voice"] = (rep_ or {}).get("voice")
                after["stop_status"] = [f.get("state") for f in s.since(k2) if f.get("ev") == "world/status"]
                if ask and ask.get("options"):
                    k3 = s.say(ask["options"][0]["say"], "p3")
                    end3 = s.wait(ended, k3, timeout=300)
                    time.sleep(2.0)
                    after["answer"] = ask["options"][0]["say"]
                    after["answer_j"] = next((f.get("intent") for f in s.since(k3) if f.get("ev") == "intent" and f.get("id") == "p3"), None)
                    after["answer_outcome"] = end3["rec"]["outcome"] if end3 else "timeout"
            fs = s.since(0)
        finally:
            s.close()
        rec = {"words": words, "map": bool(got), "hello_card": hello_card, "card_voice": card_voice, "card_status": card_status}
        rec["j"] = next((f.get("intent") for f in turn if f.get("ev") == "intent" and f.get("id") == "p1"), None)
        rec["outcome"] = end["rec"]["outcome"] if end else "timeout"
        rec["asked"] = bool(end and any(e.startswith("ask(") for e in end["rec"].get("effects") or ()))
        rec["hierarchy"] = sum(1 for f in turn if f.get("ev") == "world/hierarchy")
        deltas = [f for f in turn if f.get("ev") == "world/delta"]
        rec["moves"] = [f["agent"]["at"] for f in deltas if (f.get("agent") or {}).get("at")]
        rec["world_deltas"] = sum(1 for f in deltas if "task" not in f)
        rec["task_views"] = sum(1 for f in deltas if "task" in f)
        rec["cornered"] = next((f["cornered"] for f in deltas if f.get("cornered")), None)
        rec["chain"] = next((f["task"]["chain"] for f in reversed(deltas) if "task" in f), [])
        rec["said"] = [(f.get("kind"), f.get("sentence")) for f in turn if f.get("ev") == "narration"]
        rec["wakes"] = [x["domain"] for x in journal(turn, "dlg-domain") if x.get("by") == "director" and x.get("verb") == "activate"]
        log = root / "domains" / "hier" / ".commands.jsonl"
        rec["commands"] = [json.loads(x)["command"] for x in log.read_text().splitlines() if x.strip()] if log.exists() else []
        rec["replay"] = str(out_dir / ("%s.run.jsonl" % name))
        shutil.copy(root / "world-map.json", out_dir / ("%s.map.json" % name))     # the map beside its recording (nina's N2)
        as_replay(fs, rec["replay"], "%s.map.json" % name)
        rec.update(after)
        rec["statuses"] = [f.get("state") for f in fs if f.get("ev") == "world/status"]
        report[name] = rec
        # the five turns, as DEMO.md §5 says them
        need = [(rec["map"], "1. the world's map named on hello (world/map)"),
                (rec["j"] and rec["j"].get("intent") == "FETCH", "2. E2B typed the person's words into the task card (FETCH)"),
                (rec["hierarchy"] > 0, "3. the director's beats on the wire (world/hierarchy)")]
        if name == "win":
            need += [(rec["wakes"], "3. the director woke the specialists (dlg-domain by director)"),
                     (rec["world_deltas"] >= len(rec["commands"]) > 0, "3. every world command a world/delta (the map's agent moves)"),
                     (any(k == "v3-line" for k, _ in rec["said"]), "3. the results' lines said through the band"),
                     (rec["outcome"] == "ended(done)", "the task ends done")]
        else:
            # the task refuses the destination at once (not_dest → wrong_dest): no specialist, no command
            need.append((rec["commands_at_end"] == 0, "4. nothing is sent to the world for a refused destination"))
            need.append((rec["asked"], "4. a wrong destination disengages: the director asks"))
            need.append((any(k == "v3-ask" for k, _ in rec["said"]), "4. the ask said through the band (v3-ask)"))
            need.append((rec["cornered"] is not None, "4. the map shows the cornered place"))
        need.append((Path(rec["replay"]).stat().st_size > 0, "5. the turn recorded, replayable without THOR (the page's ?replay=)"))
        # step 3b: what the agent wants from the person, always said
        need.append((rec["statuses"][:1] == ["waiting"], "3b. waiting for a task, on hello (world/status)"))
        need.append(("Ask me, for example" in (rec.get("hello_card") or ""), "3b. the world's card said on hello (what it is, what to ask)"))
        if name == "fridge":
            need.append(("Ask me, for example" in (rec.get("card_voice") or "") and not (rec.get("card_status") or []),
                         "3b. words with no task get the card, and the agent still waits"))
        need.append(("working" in rec["statuses"] or name == "fridge", "3b. working, while a domain is on its goal"))
        if name == "win":
            need.append(("over" in rec["statuses"], "3b. over: the won game takes no other task"))
            need.append(("over" in (rec.get("over_status") or []) and "game is over" in (rec.get("over_voice") or "").lower(),
                         "3b. another task after the win is refused in words"))
            need.append(("waiting" in (rec.get("new_game_status") or []), "3b. a new game: the same room, waiting for a task"))
            ms = rec.get("mid_stop") or {}
            need.append((ms.get("at") and ms.get("voice") == "Stopped.", "3b. a stop while a specialist works is answered"))
            need.append((ms.get("asleep") is not None and all(x.startswith("active(task") for x in ms["asleep"]),
                         "3b. … the hierarchy at its start after it (only the planner awake, world/hierarchy)"))
            hs = rec.get("held_stop") or {}
            need.append((hs.get("at") and hs.get("voice") == "Stopped." and not hs.get("won_before_the_stop"),
                         "3b. a stop with the object in hand is answered (before the errand ends)"))
            need.append((rec.get("again_outcome") == "ended(done)", "3b. … and the task, asked again from there, wins"))
        else:
            a = rec.get("ask") or {}
            need.append((bool(a.get("options")), "3b. the ask carries its answers (world/ask options)"))
            need.append(("asking" in rec["statuses"], "3b. asking, while the question is open"))
            need.append((rec.get("stop_voice") == "Stopped." and "waiting" in (rec.get("stop_status") or []), "3b. stop is answered and waits"))
            need.append(((rec.get("answer_j") or {}).get("intent") not in (None, "UNKNOWN"), "3b. the ask's first answer, said back, is taken"))
            need.append((rec.get("answer_outcome") == "ended(done)", "3b. … and it finishes the task"))
        rec["checks"] = [[bool(ok), what] for ok, what in need]
        problems += ["%s: %s" % (name, what) for ok, what in need if not ok]
    report["problems"] = problems
    (out_dir / "check.json").write_text(json.dumps(report, indent=1))
    return report


def games(n, split, out_dir, port, seed=1):
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    recs = []
    for i, g in enumerate(families.sample(split, "pick_and_place_simple", n, seed)):
        root = out_dir / ("g%02d" % i)
        cfg, m, (o, r), inst = setup(g, root, port=port)
        words = "bring the %s to the %s" % (hda.words_of(o), hda.words_of(r))
        s = Session(root, cfg, port)
        t0 = time.time()
        try:
            k = s.say(words, "p1")
            end = s.wait(ended, k, timeout=300)
            time.sleep(1.0)
            turn = s.since(k)
        finally:
            s.close()
        log = root / "domains" / "hier" / ".commands.jsonl"
        cmds = [json.loads(x)["command"] for x in log.read_text().splitlines() if x.strip()] if log.exists() else []
        from alf_host import AlfHost
        mirror = AlfHost(inst["_flat"])
        try:
            for c in cmds:
                mirror._take(mirror.gym.call("step", command=c))
            won = bool(mirror.won)
        finally:
            mirror.gym.close()
        deltas = [f for f in turn if f.get("ev") == "world/delta" and "task" not in f]
        rec = {"game": os.path.relpath(g, families.data_root()), "words": words, "won": won,
               "outcome": end["rec"]["outcome"] if end else "timeout", "commands": len(cmds), "world_deltas": len(deltas),
               "hierarchy": sum(1 for f in turn if f.get("ev") == "world/hierarchy"),
               "lines": sum(1 for f in turn if f.get("ev") == "narration" and f.get("kind") == "v3-line"),
               "seconds": round(time.time() - t0, 1)}
        recs.append(rec)
        print("%2d %-60s %s %-12s %d commands, %d world/delta, %d beats, %d lines, %ss" % (
            i + 1, rec["game"][-60:], "WON " if won else "lost", rec["outcome"], rec["commands"], rec["world_deltas"],
            rec["hierarchy"], rec["lines"], rec["seconds"]), flush=True)
    summary = {"split": split, "n": len(recs), "won": sum(r["won"] for r in recs), "games": recs}
    (out_dir / ("games-%s.json" % split)).write_text(json.dumps(summary, indent=1))
    print("won %d/%d" % (summary["won"], len(recs)))
    return summary


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("setup")
    s.add_argument("game")
    s.add_argument("root")
    s.add_argument("--port", type=int, default=8398)
    s.add_argument("--view", action="store_true", help="the semantic map sees only what the robot sees (semantic-map step 3)")
    c = sub.add_parser("check")
    c.add_argument("--game", default=None)
    c.add_argument("--out", default=str(HERE / "records" / "demo-check"))
    c.add_argument("--port", type=int, default=8398)
    c.add_argument("--tree", action="store_true", help="the tick: the tree director, domains.tick (specialist-tree step 2)")
    g = sub.add_parser("games")
    g.add_argument("--n", type=int, default=10)
    g.add_argument("--split", default="train")
    g.add_argument("--out", default=str(HERE / "records" / "demo-games"))
    g.add_argument("--port", type=int, default=8398)
    a = ap.parse_args(argv)
    if a.cmd == "setup":
        cfg, m, fetch, _ = setup(a.game, a.root, a.port, view=a.view)
        print(json.dumps({"config": str(cfg), "task": m["task"]["text"], "fetch": fetch}))
        return 0
    if a.cmd == "check":
        game = a.game or str(Path(families.data_root()) / GAME / sorted(os.listdir(Path(families.data_root()) / GAME))[0])
        rep = check(game, a.out, a.port, tree=a.tree)
        for name in ("win", "fridge"):
            r = rep[name]
            print("%s: %r → %s; %s; %d world/delta, %d beats; said %d; cornered %s" % (
                name, r["words"], json.dumps(r["j"]), r["outcome"], r["world_deltas"], r["hierarchy"], len(r["said"]), r["cornered"]))
            for ok, what in r["checks"]:
                print("   %s %s" % ("ok " if ok else "NO ", what))
        return 1 if rep["problems"] else 0
    games(a.n, a.split, a.out, a.port)
    return 0


if __name__ == "__main__":
    sys.exit(main())
