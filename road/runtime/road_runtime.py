#!/usr/bin/env python3
"""road_runtime.py — the ROAD WORLD RUNTIME (metis-plugin s-df4ff191 v3): the road world run headless, served to the
Metis plugin by the surprise interface (metis-agent plugin/docs/SURPRISE-INTERFACE.md v1.1): what /connect-runtime
attaches to. Independent of road/web (the road UI's backend is a client of the PLUGIN under /ide, not of this).

    road/runtime/road_runtime.py --workspace ROOT [--port 0] [--name road]
    (the workspace's runner.yaml starts it so: {python} runtime/road_runtime.py --workspace {workspace} --port {port})

- Serves on loopback with a random token: GET /feed (WebSocket: the signals as they come, ?since=SEQ resumes; plain GET:
  the backlog as JSON lines), POST /signal (one envelope in: 200 {ok} | 4xx {error: words}), GET /status.
  Discovery: .metis/runtimes/<name>.json {name, url, token, pid, domain, workspace, protocol, started} while it serves.
- EXCLUSIVE: one plugin at a time (the first that says hello holds it until its feed closes); another is refused with
  409 naming the holder.
- Signals out: hello {name, domain, workspace, protocol, capabilities, spec_keys}; status {state, run?, tick?, counts?}
  (on change and every STATUS_S); run.started / run.ended {run, request, trace, spec, summary?, reason, error?};
  surprise.new {id, ref, key, kind, member} once the record and its window are in the workspace (the run's child
  writes them through the SDK: run_card.py); event.new {run, k0, k1, words} (a run's end).
- Signals in: hello; run.request {id, spec} (the spec is the road runtime's: card | scenario, seed, host, ticks, site;
  one run at a time, a request while running is 409); run.stop {id, run?}; surprise.taken / ruled / applied,
  catalog.changed, world.changed: noted in the status (a catalog change needs nothing more: every run is a fresh Live,
  the next one loads the catalog afresh; a world change: the next run's child imports the world's code afresh too).
- A run = one child process (run_card.py) in the runtime's own interpreter and environment (METIS_HOME etc. from the
  runner's env); its JSON lines become the signals above."""
import argparse
import asyncio
import json
import os
import secrets
import signal
import subprocess
import sys
import threading
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROAD = HERE.parent
PROTOCOL = 1
STATUS_S = 5.0
SPEC_KEYS = ["card", "scenario", "seed", "host", "ticks", "site"]
KEEP_SUMMARY = ("arrived", "collisions", "collision_events", "violations", "ticks", "t", "rc", "s", "wall_s", "stopped",
                "planner_kinds", "responder_kinds")


def now_iso():
    t = time.time()
    return time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(t)) + ".%03d" % int((t % 1) * 1000) + time.strftime("%z")


class Runtime:
    def __init__(self, workspace, name="road", python=None):
        self.ws = Path(workspace).resolve()
        self.name, self.python = name, python or sys.executable
        self.token = secrets.token_urlsafe(24)
        self.seq, self.backlog = 0, []
        self.lock = threading.Lock()
        self.holder, self.holder_since = None, None
        self.child, self.run, self.request, self.spec = None, None, None, None
        self.tick, self.counts, self.notes = None, {}, []
        self.loop, self.waiters = None, set()
        self.port = None

    # ── the feed ──
    def signal(self, type_, **fields):
        with self.lock:
            self.seq += 1
            env = {"v": 1, "seq": self.seq, "ts": now_iso(), "type": type_, "from": "runtime:%s" % self.name}
            env.update({k: v for k, v in fields.items() if v is not None})
            self.backlog.append(env)
        if self.loop is not None:
            self.loop.call_soon_threadsafe(self._wake)
        return env

    def envelope(self, type_, **fields):
        env = {"v": 1, "seq": self.seq, "ts": now_iso(), "type": type_, "from": "runtime:%s" % self.name}
        env.update({k: v for k, v in fields.items() if v is not None})
        return env

    def _wake(self):
        for w in list(self.waiters):
            if not w.done():
                w.set_result(True)

    def hello(self):
        return {"v": 1, "seq": 0, "ts": now_iso(), "type": "hello", "from": "runtime:%s" % self.name, "name": self.name,
                "domain": "road", "workspace": str(self.ws), "protocol": PROTOCOL, "capabilities": ["run", "stop"],
                "spec_keys": SPEC_KEYS}

    def status(self):
        return {"state": "running" if self.child is not None else "idle", "run": self.run, "tick": self.tick,
                "counts": dict(self.counts) or None}

    # ── runs ──
    def start_run(self, req_id, spec):
        if self.child is not None:
            raise Conflict("a run is going (%s, request %s): one run at a time; run.stop it first" % (self.run, self.request))
        if not isinstance(spec, dict) or not (spec.get("card") or spec.get("scenario")):
            raise Refused("run.request needs spec.card (a catalog card id) or spec.scenario (a road world scenario)")
        unknown = sorted(set(spec) - set(SPEC_KEYS))
        if unknown:
            raise Refused("run.request spec: unknown keys %s (this runtime reads %s)" % (", ".join(unknown), ", ".join(SPEC_KEYS)))
        args = dict(spec, workspace=str(self.ws))
        self.child = subprocess.Popen([self.python, str(HERE / "run_card.py"), json.dumps(args)], stdout=subprocess.PIPE,
                                      stderr=open(self.ws / ".metis" / "runtimes" / ("%s.child.log" % self.name), "a"),
                                      text=True, cwd=str(ROAD.parent), start_new_session=True)
        self.request, self.spec, self.run, self.tick, self.counts = req_id, spec, None, None, {}
        threading.Thread(target=self._read_child, args=(self.child,), daemon=True, name="road-run").start()
        self.signal("status", **self.status())

    def stop_run(self):
        c = self.child
        if c is None:
            raise Refused("no run is going")
        try:
            os.killpg(c.pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
        self.stopping = True

    def _read_child(self, child):
        ended = False
        trace = None
        for line in child.stdout:
            try:
                m = json.loads(line)
            except ValueError:
                continue
            t = m.get("type")
            if t == "started":
                self.run, trace = m["run"], m.get("trace")
                self.signal("run.started", run=self.run, request=self.request, trace=trace, spec=self.spec)
            elif t == "status":
                self.tick, self.counts = m.get("tick"), m.get("counts") or {}
                self.signal("status", **self.status())
            elif t == "finding":
                self.counts[m["kind"]] = self.counts.get(m["kind"], 0) + 1
                self.signal("surprise.new", id=m["id"], ref=m.get("ref"), key=m.get("key"), kind=m.get("kind"),
                            member=m.get("member"), run=m.get("run"), window=m.get("window"), words=m.get("words"))
            elif t == "event":
                self.signal("event.new", run=m.get("run"), k0=m.get("k0"), k1=m.get("k1"), words=m.get("words"))
            elif t == "ended":
                ended = True
                summ = {k: m["summary"].get(k) for k in KEEP_SUMMARY if k in (m.get("summary") or {})}
                if m.get("check"):
                    summ["check"] = {k: m["check"].get(k) for k in ("standing", "fails")}
                self.signal("run.ended", run=self.run, request=self.request, trace=trace, spec=self.spec, summary=summ,
                            reason="done")
            elif t == "error":
                ended = True
                self.signal("run.ended", run=self.run or m.get("run"), request=self.request, trace=trace, spec=self.spec,
                            reason="error", error=m.get("error"))
        rc = child.wait()
        if not ended:
            stopped = getattr(self, "stopping", False)
            self.signal("run.ended", run=self.run, request=self.request, trace=trace, spec=self.spec,
                        reason="stopped" if stopped else "error",
                        error=None if stopped else "the run's child exited %s without an end (see %s.child.log)" % (rc, self.name))
        self.child, self.stopping = None, False
        self.signal("status", **self.status())

    # ── signals in ──
    def accept(self, env, peer):
        t = env.get("type")
        if t == "hello":
            return {"ok": True}
        if t == "run.request":
            self.start_run(env.get("id"), env.get("spec"))
            return {"ok": True}
        if t == "run.stop":
            self.stop_run()
            return {"ok": True}
        if t in ("surprise.taken", "surprise.ruled", "surprise.applied", "catalog.changed", "world.changed"):
            self.notes.append({k: env.get(k) for k in ("type", "id", "verdict", "commit", "branch", "paths") if env.get(k)})
            del self.notes[:-50]
            return {"ok": True}
        return {"ok": True, "ignored": t}            # unknown types are ignored (forward compatible)

    # ── the holder (exclusive) ──
    def claim(self, peer):
        with self.lock:
            if self.holder is None or self.holder == peer:
                if self.holder is None:
                    self.holder, self.holder_since = peer, time.strftime("%H:%M")
                return None
            return "runtime %s is attached to %s since %s; disconnect it first" % (self.name, self.holder, self.holder_since)

    def release(self, peer):
        with self.lock:
            if self.holder == peer:
                self.holder, self.holder_since = None, None


class Refused(Exception):
    status = 400


class Conflict(Refused):
    status = 409


def discovery(rt):
    d = rt.ws / ".metis" / "runtimes"
    d.mkdir(parents=True, exist_ok=True)
    return d / ("%s.json" % rt.name)


async def serve(rt, host, port):
    from aiohttp import WSMsgType, web

    def authorized(req):
        h = req.headers.get("Authorization", "")
        tok = h[7:] if h.startswith("Bearer ") else req.query.get("token", "")
        return secrets.compare_digest(tok or "", rt.token)

    def peer_of(req):
        return req.headers.get("X-Metis-From") or req.query.get("from") or "plugin:?"

    async def feed(req):
        if not authorized(req):
            return web.json_response({"error": "a token is needed (Authorization: Bearer <token>)"}, status=401)
        peer = peer_of(req)
        since = int(req.query.get("since") or 0)
        if req.headers.get("Upgrade", "").lower() != "websocket":
            rows = [e for e in rt.backlog if e["seq"] > since]
            return web.Response(text="".join(json.dumps(e) + "\n" for e in [rt.hello()] + rows), content_type="application/x-ndjson")
        why = rt.claim(peer)
        if why:
            return web.json_response({"error": why}, status=409)
        ws = web.WebSocketResponse(heartbeat=20)
        await ws.prepare(req)
        try:
            await ws.send_json(rt.hello())
            await ws.send_json(rt.envelope("status", **rt.status()))
            sent = since

            async def pump():
                nonlocal sent
                while not ws.closed:
                    rows = [e for e in rt.backlog if e["seq"] > sent]
                    for e in rows:
                        await ws.send_json(e)
                        sent = e["seq"]
                    w = rt.loop.create_future()
                    rt.waiters.add(w)
                    try:
                        await asyncio.wait_for(w, STATUS_S)
                    except asyncio.TimeoutError:          # the heartbeat: to this socket only, not the backlog
                        await ws.send_json(rt.envelope("status", **rt.status()))
                    finally:
                        rt.waiters.discard(w)
            task = asyncio.ensure_future(pump())
            async for msg in ws:                             # the plugin may send its signals on the socket too
                if msg.type == WSMsgType.TEXT:
                    try:
                        out = rt.accept(json.loads(msg.data), peer)
                    except Refused as e:
                        out = {"error": str(e), "status": e.status}
                    await ws.send_json(dict(out, type="reply"))
                elif msg.type in (WSMsgType.ERROR, WSMsgType.CLOSE):
                    break
            task.cancel()
        finally:
            rt.release(peer)
        return ws

    async def post_signal(req):
        if not authorized(req):
            return web.json_response({"error": "a token is needed (Authorization: Bearer <token>)"}, status=401)
        peer = peer_of(req)
        why = rt.claim(peer)
        if why:
            return web.json_response({"error": why}, status=409)
        try:
            env = await req.json()
        except ValueError:
            return web.json_response({"error": "one JSON envelope per request"}, status=400)
        if not isinstance(env, dict) or not env.get("type"):
            return web.json_response({"error": "an envelope has a type"}, status=400)
        if int(env.get("v") or 1) > PROTOCOL:
            return web.json_response({"error": "protocol %s: this runtime speaks %d" % (env.get("v"), PROTOCOL)}, status=400)
        try:
            return web.json_response(rt.accept(env, peer))
        except Refused as e:
            return web.json_response({"error": str(e)}, status=e.status)

    async def status(req):
        if not authorized(req):
            return web.json_response({"error": "a token is needed"}, status=401)
        return web.json_response(dict(rt.status(), name=rt.name, holder=rt.holder, seq=rt.seq, notes=rt.notes[-10:]))

    app = web.Application()
    app.router.add_get("/feed", feed)
    app.router.add_post("/signal", post_signal)
    app.router.add_get("/status", status)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, host, port)
    await site.start()
    rt.port = site._server.sockets[0].getsockname()[1]
    return runner


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--workspace", required=True)
    ap.add_argument("--port", type=int, default=0)
    ap.add_argument("--name", default="road")
    a = ap.parse_args(argv)
    rt = Runtime(a.workspace, a.name)
    (rt.ws / ".metis" / "runtimes").mkdir(parents=True, exist_ok=True)
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    rt.loop = loop
    runner = loop.run_until_complete(serve(rt, "127.0.0.1", a.port))
    disc = discovery(rt)
    info = {"name": rt.name, "url": "http://127.0.0.1:%d" % rt.port, "token": rt.token, "pid": os.getpid(), "domain": "road",
            "workspace": str(rt.ws), "protocol": PROTOCOL, "started": now_iso()}
    tmp = disc.with_suffix(".json.part")
    tmp.write_text(json.dumps(info))
    os.replace(tmp, disc)
    print(json.dumps({"ready": True, "url": info["url"], "discovery": str(disc)}), flush=True)

    def bye(*_):
        loop.stop()
    for s in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(s, bye)
    try:
        loop.run_forever()
    finally:
        if rt.child is not None:
            try:
                os.killpg(rt.child.pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
        try:
            if json.loads(disc.read_text()).get("pid") == os.getpid():
                disc.unlink()
        except (OSError, ValueError):
            pass
        loop.run_until_complete(runner.cleanup())


if __name__ == "__main__":
    main()
