"""loop-test step 2's dry drive at the protocol level (no browser): the frames the console page sends, over the live gateway."""
import json, sys, time
from websockets.sync.client import connect

URL = sys.argv[1] if len(sys.argv) > 1 else "ws://127.0.0.1:8770/ws"
LLP = sys.argv[2] if len(sys.argv) > 2 else "domains/dog/dog"
LINES = sys.argv[3].split("|") if len(sys.argv) > 3 else ["run 3"]
log = []

def frames(ws, until, timeout=60):
    out, end = [], time.time() + timeout
    while time.time() < end:
        f = json.loads(ws.recv(timeout=max(0.1, end - time.time())))
        out.append(f)
        if until(f):
            return out
    raise AssertionError("timed out; last %s" % out[-3:])

def ask(ws, ch, typ, timeout=60, **kw):
    req = "q%d" % time.monotonic_ns()
    ws.send(json.dumps({"ch": ch, "type": typ, "req": req, **kw}))
    f = frames(ws, lambda f: f.get("req") == req, timeout)[-1]
    log.append((ch, typ, kw, {k: f[k] for k in f if k not in ("req",)}))
    return f

def say(step, ok, what):
    print("%-4s %-28s %s" % ("OK" if ok else "FAIL", step, what), flush=True)

with connect(URL, open_timeout=5, max_size=None) as ws:
    cats = frames(ws, lambda f: f.get("type") == "catalogs")[-1]
    say("catalogs", True, "%d entries" % len(cats.get("catalogs") or cats.get("entries") or []))
    ws.send(json.dumps({"ch": "repl", "type": "open", "llp": LLP, "trace": True, "req": "o1"}))
    s = frames(ws, lambda f: f.get("type") in ("session", "error"))[-1]
    say("open " + LLP, s["type"] == "session", s.get("session") or s.get("error") or s.get("message"))
    sid = s.get("session")
    for i, line in enumerate(LINES):
        ws.send(json.dumps({"ch": "repl", "type": "intent", "session": sid, "id": "i%d" % i, "cmd": line, "actor": "viewer"}))
        got = frames(ws, lambda f: f.get("type") == "posting" and f.get("id") == "i%d" % i)
        say("repl: " + line, True, str(got[-1].get("text") or got[-1].get("lines") or "")[:100])
    d = ask(ws, "surprise", "drop", session=sid, reading={"saw": "dry drive"}, words="loop-test dry drive: it should not have")
    say("surprise drop (session)", d["type"] != "error", d.get("id") or d)
    lst = ask(ws, "surprise", "list")
    say("surprise list", any(x["id"] == d.get("id") for x in lst.get("surprises", [])), "%d surprise(s)" % len(lst.get("surprises", [])))
    st = ask(ws, "loop", "start", mode="rpc", model="stub/script", timeout=120)
    say("loop start (stub pi)", st["type"] == "start" and (st.get("child") or {}).get("state") == "running", (st.get("child") or {}).get("state") or st)
    ask(ws, "loop", "say", text="please apply the pack")
    gate = frames(ws, lambda f: f.get("ch") == "loop" and f.get("type") == "gate")[-1]
    say("gate", bool(gate.get("token")), (gate.get("plan") or {}).get("title"))
    ask(ws, "loop", "confirm", token=gate["token"])
    got = frames(ws, lambda f: f.get("ch") == "loop" and f.get("type") == "pi" and f["event"]["kind"] == "turn_end")
    res = [f["event"] for f in got if f.get("type") == "pi" and f["event"]["kind"] == "tool_result"]
    say("confirm -> tool result", bool(res) and res[-1].get("ok"), (res[-1].get("text") if res else "")[:100])
    for c in ("/status", "/surprises", "/help"):
        r = ask(ws, "loop", "say", text=c)
        rows = frames(ws, lambda f: f.get("ch") == "loop" and f.get("type") in ("cmd", "row", "say") or f.get("kind") == "cmd", timeout=10) if False else []
        say("chat " + c, r.get("type") != "error", str(r.get("text") or r.get("reply") or r)[:110])
    b = ask(ws, "bundle", "state")
    say("bundle state", b.get("type") != "error", json.dumps({k: (b.get("bundle") or {}).get(k) for k in ("name", "image", "stale")}))
    ask(ws, "loop", "stop")
    end = time.time() + 20
    while time.time() < end:
        c = ask(ws, "loop", "state").get("child")
        if c is None or c.get("state") == "exited":
            break
        time.sleep(0.3)
    say("loop stop", c is None or c.get("state") == "exited", (c or {}).get("state"))
json.dump(log, open(sys.argv[4] if len(sys.argv) > 4 else "/bigdata/work/bond/loop-test/frames-A.json", "w"), indent=1, default=str)
