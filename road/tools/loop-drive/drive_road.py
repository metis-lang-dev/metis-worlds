"""loop-road-ui step 3, flows A and B at the protocol level, over the console beside a live road run (stub pi)."""
import json, sys, time
sys.argv = sys.argv[:1]
exec(open("/bigdata/work/bond/loop-test/drive.py").read().split("with connect(")[0])

def chat(ws, text, timeout=120):
    r = ask(ws, "loop", "say", text=text, timeout=timeout)
    t = str(r.get("text") or r.get("error") or r)
    say("chat " + text[:40], r.get("type") != "error", t[:230].replace("\n", " | "))
    return r

with connect(URL, open_timeout=5, max_size=None) as ws:
    frames(ws, lambda f: f.get("type") == "catalogs")
    tl = ask(ws, "trace", "list")
    live = [t for t in tl.get("traces", []) if t["run"].startswith("Town03")]
    run = live[-1]["run"]
    op = ask(ws, "trace", "open", run=run)["trace"]
    k1 = op["k1"]
    say("live trace", True, "%s k0..k1 %s..%s, members %s" % (run, op["k0"], k1, sorted(op["header"]["members"])))
    a, b = max(1, k1 - 60), max(2, k1 - 40)
    # flow A
    m1 = chat(ws, "/mark %s:planner %d..%d it braked for nothing" % (run, a, b))
    chat(ws, "/agree")
    m2 = chat(ws, "/mark %s:planner %d..%d it should have kept going" % (run, a, b))
    chat(ws, "/disagree it should have kept going: the crossing was clear")
    chat(ws, "/surprises")
    # flow B (stub pi: its words are the stub's)
    st = ask(ws, "loop", "start", mode="rpc", model="stub/script", timeout=120)
    say("loop start (stub)", (st.get("child") or {}).get("state") == "running", (st.get("child") or {}).get("state"))
    chat(ws, "/take")
    chat(ws, "/why planner at %d" % b)
    chat(ws, "/ruling")
    chat(ws, "/status")
    chat(ws, "/stop")
json.dump(log, open("/bigdata/work/bond/loop-test/frames-road.json", "w"), indent=1, default=str)
