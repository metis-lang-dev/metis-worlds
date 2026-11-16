"""The road page's events, the Metis bridge and one voice (loop-road-ui s-0314a8ee; metis-plugin s-df4ff191 step 4: the pi LOOP dock out):
the grammar that routes a line to the page's events (run under node: $NODE, else `node` on PATH; none, those tests skip,
METIS_ROAD_REQUIRE_NODE=1 fails instead), and the page's shape: one TOOLS dock of cards, EVENTS whose explain and send go to the Metis
bridge, narrate by the road's own host, the 'catalog changed: reload' notice, the dashboard's rolling window and glyphs."""
import json
import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest

WEB = Path(__file__).resolve().parents[1] / "web"
HTML = (WEB / "world.html").read_text()
WORLD = (WEB / "world.js").read_text()

# (the person says, the context, the route) — brief §1.3's table, and what stays the road's
CASES = [
    ("go right", {}, None),
    ("stop", {}, None),                                               # the car's word
    ("what's around us", {}, None),
    ("mark", {}, {"to": "page", "action": "mark"}),
    ("mark here", {}, {"to": "page", "action": "mark"}),
    ("End mark, the car braked for nothing.", {}, {"to": "page", "action": "endmark", "words": "the car braked for nothing"}),
    ("end the event", {}, {"to": "page", "action": "endmark", "words": ""}),
    ("narrate", {}, {"to": "page", "action": "narrate"}),
    ("narrate event 4", {}, {"to": "page", "action": "narrate", "n": 4}),
    ("explain it", {}, {"to": "page", "action": "explain"}),
    ("send event 2 to metis", {}, {"to": "page", "action": "send", "n": 2}),
    ("send it to Claude", {}, {"to": "page", "action": "send"}),
    ("send event 2 to the loop", {}, {"to": "page", "action": "send", "n": 2}),   # the old words still understood: they go to Metis now
    ("continue", {"paused": True}, {"to": "page", "action": "continue"}),
    ("continue", {}, None),                                           # not waiting on a surprise: the road's
    ("/narrate event 4", {}, {"to": "page", "action": "narrate", "n": 4}),
    ("/explain 4", {}, {"to": "page", "action": "explain", "n": 4}),
    ("load DynamicObjectCrossing", {"scenarios": ["Town03", "DynamicObjectCrossing"]}, {"to": "page", "action": "scenario", "name": "DynamicObjectCrossing"}),
    ("run the scenario town03", {"scenarios": ["Town03"]}, {"to": "page", "action": "scenario", "name": "Town03"}),
    ("load NoSuchThing", {"scenarios": ["Town03"]}, None),           # not in the tree: the road's (it says it does not know)
    # the pi loop's lines are gone with its dock: the road agent's now (or nothing)
    ("agree", {"loopMark": 3}, None),
    ("take the next surprise", {}, None),
    ("/status", {}, None),
    ("confirm", {"gate": True}, None),
    ("why did it brake", {}, None),
]


def node():
    n = os.environ.get("NODE") or shutil.which("node")
    if not n:
        if os.environ.get("METIS_ROAD_REQUIRE_NODE") == "1":
            pytest.fail("no node for the page's grammar (NODE or PATH)")
        pytest.skip("no node for the page's grammar")
    return n


def test_the_grammar_routes_the_events_lines_and_leaves_the_roads(tmp_path):
    js = tmp_path / "run.mjs"
    js.write_text(f"""import {{ route }} from {json.dumps((WEB / "pagegrammar.js").as_uri())};
const cases = JSON.parse(process.argv[2]);
process.stdout.write(JSON.stringify(cases.map(([t, ctx]) => route(t, ctx))));""")
    p = subprocess.run([node(), str(js), json.dumps([[t, c] for t, c, _ in CASES])], capture_output=True, text=True, timeout=60)
    assert p.returncode == 0, p.stderr
    for (t, c, want), got in zip(CASES, json.loads(p.stdout)):
        if want and "n" not in want and got and got.get("n") is None:
            got.pop("n", None)
        assert got == want, (t, c)


def test_one_tools_dock_of_cards_and_events_no_loop():
    """Drive, Cars and Traffic: one TOOLS dock of collapsible cards (the DIALOG's fw-sec look); EVENTS; no LOOP dock (metis-plugin step 4)."""
    tools = HTML[HTML.index('id="dock-tools"'):HTML.index('id="dock-events"')]
    assert [m for m in re.findall(r'<details class="fw-sec tool" id="tool-(\w+)"', tools)] == ["scenarios", "drive", "run", "cars", "traffic"]
    bar = HTML[HTML.index('<span id="runbar">'):HTML.index('</span>', HTML.index('<span id="runbar">'))]
    assert 'id="scenario"' not in bar and 'id="seed"' not in bar                      # the top bar: run controls only (the user)
    card = HTML[HTML.index('id="tool-scenarios"'):HTML.index('id="tool-drive"')]
    assert 'id="seed"' in card and 'id="sc-running"' in card and '<select id="scenario" hidden' in card
    sc = (WEB / "scenarios.js").read_text()
    assert "this.tree.addEventListener('click', e => this.click(e, false));" in sc and "this.tree.addEventListener('dblclick', e => this.click(e, true));" in sc
    assert "this.line(`scard:${r.id}`)" in sc and "this.run(r.runs[0].run)" in sc        # click: the card; double click: its first run
    for gone in ('id="dock-drive"', 'id="dock-run"', 'id="dock-cars"', 'id="dock-traffic"', 'data-strip="drive"', 'data-strip="run"',
                 'data-strip="cars"', 'data-strip="traffic"'):
        assert gone not in HTML, gone
    for el in ('id="t-add"', 'id="t-cr-run"', 'data-drive="turn:left"', 'id="picked"', 'id="run-info"', 'id="follow"', 'id="dock-events"',
               'id="metisstate"', 'id="catchg"', 'id="catchg-reload"'):
        assert el in HTML, el
    for gone in ('id="dock-loop"', 'id="loopbox"', 'data-strip="loop"', '#loopframe'):
        assert gone not in HTML, gone
    assert "names: ['talk', 'tools', 'events', 'hierarchy', 'world', 'journal', 'dialog'], key: 'roadpage.docks.v7'" in WORLD


def test_no_pi_loop_the_page_talks_only_to_its_backend():
    """metis-plugin s-df4ff191 (spec v1.1): the pi LOOP dock is gone; the page talks only to its own backend (the road service, the /ide
    client of an attached Claude Code): send and explain are metis:send|explain lines, answered by world/metis_ack; the plugin's signals
    come relayed as world/metis frames; the page never holds the plugin's URL or token."""
    assert not (WEB / "loopdock.js").exists() and not (WEB / "loopgrammar.js").exists() and not (WEB / "metisbridge.js").exists()
    for f in WEB.glob("*.js"):
        t = f.read_text()
        assert "MetisLoop" not in t and "LoopDock" not in t, f
        assert "token=" not in t and "X-Metis-Token" not in t and "Authorization" not in t and "Bearer" not in t, f   # no credential
    assert "world.map.line(`metis:${op}:${JSON.stringify(b)}`);" in WORLD
    assert "if (f.ev === 'world/metis_ack') { metis.ack(f); return; }" in WORLD and "if (f.ev === 'world/metis') { metisSignal(f.msg || {}); return; }" in WORLD
    ev = (WEB / "events.js").read_text()
    assert "const r = await this.metis.surprise(this.body(e));" in ev and "const r = await this.metis.explain(this.body(e));" in ev
    assert "return { run: e.trace, window: [w0, w1], n: e.n, kind: e.kind," in ev
    host = (WEB.parent / "world" / "road_host.py").read_text()
    assert 'elif line.startswith("metis:"):' in host and "out += self.metis_frames()" in host


def test_narrate_is_the_road_hosts_and_the_catalog_change_is_offered():
    """narrate goes to the road's own host (narrate:N:RUN:K0:K1 -> world/narration), never to a loop; the host's catalog watch says
    world/catalog_changed, the page shows 'catalog changed' and its reload asks the service to reload every member, then says catalog:seen."""
    ev = (WEB / "events.js").read_text()
    assert "this.line(`narrate:${e.n}:${e.trace}:${w0}:${w1}`);" in ev
    assert "if (f.ev === 'world/narration') { events?.narrated(f); return; }" in WORLD
    assert "if (f.ev === 'world/catalog_changed') { catalogChanged(f); return; }" in WORLD and "|| f.ev === 'reload_ack'," in WORLD
    assert "for (const d of MEMBERS) send({ ev: 'reload', domain: d });" in WORLD and "world.map.line('catalog:seen');" in WORLD
    host = (WEB.parent / "world" / "road_host.py").read_text()
    assert 'elif line.startswith("narrate:"):' in host and 'elif line == "catalog:seen":' in host
    assert "for fr in (self.catalog_watch(), self.host_watch()):" in host


def test_a_world_model_change_is_a_restart():
    """pascal (step 6): a fix can be the HOST's (road/world/road_facts.py): the page says 'the world model changed: restart, the run
    starts again' and its button restarts the service (os.execv of its own argv); the catalog's reload path stays as it is."""
    assert "if (f.ev === 'world/host_changed') { hostChanged(f); return; }" in WORLD
    assert "the world model changed (${n} file${n === 1 ? '' : 's'}): restart, the run starts again" in WORLD
    assert "world.map.line('restart')" in WORLD
    host = (WEB.parent / "world" / "road_host.py").read_text()
    assert 'elif line == "restart":' in host and "os.execv(sys.executable, list(sys.orig_argv))" in host
    assert "base = HOST_LOADED if HOST_LOADED is not None else snap" in host
    assert 'self.shared.pop("host_said", None)' in host and 'self.shared.pop("cat_said", None)' in host   # a page that opens later is told


def test_the_dashboard_rolls_6000_ticks_and_moves_events():
    dash = (WEB / "dash.js").read_text()
    assert "export const WINDOW = 6000;" in dash
    assert "this.o.onMove?.(d.n, k0, k1" in dash and "if (d.moved && (k0 !== d.was[0] || k1 !== d.was[1]))" in dash   # a press is no move and 'data-act="narrate"' in dash and 'data-act="explain"' in dash
    ev = (WEB / "events.js").read_text()
    assert "this.line(`mark:${n}:move:${k0}:${k1}${i0 != null && i1 != null ? `:${i0}:${i1}` : ''}`)" in ev   # the k, and the run's ticks
    assert "window(e) { return e.kind === 'mark' ? [e.k0, Math.max(e.k0, e.k1)] : [Math.max(0, e.k0 - LEAD), e.k0]; }" in ev   # a surprise with its lead-up
    road = (WEB / "road.js").read_text()
    assert "this.line(`mark:${n}:once:${kind}`)" in road and "if (stop && !this.paused) this.hold(true);" in road
    assert "const RING = 6000;" in ev and "if (e && !this.usable(e)) return null;" in ev and ev.count("const e = this.ready(n);") == 3   # a window the ring dropped: no action


def test_a_run_that_does_not_start_and_a_service_gone_are_said_on_the_page():
    """2026-11-07 (the user: maps not loaded without a message): why a run did not start, in the SCENARIOS card; the road service gone, in the status."""
    assert '<p id="sc-msg" class="sc-msg" hidden></p>' in HTML
    assert "if (f.ev === 'world/runfail') { world.map.runFailed(f); return; }" in WORLD
    road = (WEB / "road.js").read_text()
    assert "this.runMsg(`could not run ${f.scenario}: ${f.why}`, true);" in road and "has not started after 90 s" in road
    assert "const gone = !backend || !backend.isOpen;" in WORLD and "$('#status').dataset.state = gone ? 'down' : '';" in WORLD


def test_a_map_far_from_the_origin_is_drawn_about_a_local_one(tmp_path):
    """CommonRoad's roads keep their UTM metres (x ~ 476000, y ~ 5556000): the 3D client draws in float32, where such a map vanished
    (the user, 2026-11-07). The shim moves the view's map, its cars and the goal to a local origin; a town near 0,0 is left as it is."""
    js = tmp_path / "shim.cjs"
    js.write_text("""const vm = require('vm'), fs = require('fs');
const ctx = {window: {fetch: () => {}}, addEventListener: () => {}, location: {origin: 'x'}, parent: {}, Response: class {}, Promise, JSON, Math, Number, String, Object, setTimeout};
vm.createContext(ctx);
vm.runInContext(fs.readFileSync(process.argv[2], 'utf8') + ';this.localNet = localNet; this.localGoal = localGoal; this.info = info; this.o = () => origin;', ctx);
const far = {net: {location: {convBoundary: '476338.75,5555928.70,479009.65,5556815.71'}, edge: [{id: 'e', lane: [{id: 'e_0', shape: '476400.00,5556000.50,1.0 476410.00,5556001.50'}]}],
  junction: [{id: 'j', x: '476340.00', y: '5555930.00', shape: '476340,5555930 476341,5555931'}]}};
const r = ctx.localNet(far), out = [ctx.o(), r.net.location.convBoundary, r.net.edge[0].lane[0].shape, r.net.junction[0], ctx.localGoal([[[476338, 5555928]]]),
  ctx.info({x: 476340, y: 5555930, heading: 0, length: 4, width: 2, speed: 1, class: 'p'}).x];
const near = {net: {location: {convBoundary: '-10,-10,300,300'}, edge: [], junction: []}};
out.push(ctx.localNet(near) === near, ctx.o());
process.stdout.write(JSON.stringify(out));""")
    p = subprocess.run([node(), str(js), str(WEB / "client-shim.js")], capture_output=True, text=True, timeout=60)
    assert p.returncode == 0, p.stderr
    o, bound, lane, junction, goal, x, same, o2 = json.loads(p.stdout)
    assert o == [476338, 5555928] and bound == "0.75,0.70,2671.65,887.71" and lane == "62.00,72.50,1.0 72.00,73.50"
    assert junction == {"id": "j", "x": "2.00", "y": "2.00", "shape": "2.00,2.00 3.00,3.00"} and goal == [[[0, 0]]] and x == 4
    assert same is True and o2 == [0, 0]


def test_the_voice_is_talks():
    """One chat now (the LOOP dock gone): TALK has the mic and, with the band's voice switch (Shift+8) on, the voice."""
    head = HTML[HTML.index('id="dock-talk"'):HTML.index('</header>', HTML.index('id="dock-talk"'))]
    assert '<span class="chatdot" aria-hidden="true">●</span>' in head
    assert "panel.core.setVoice(chat.voice);" in WORLD and "setChat" not in WORLD
    assert "vw.voice = voiceSwitch(voiced, { store: 'roadpage.voice'" in WORLD and "voiceWidget(panel, { narrator, key: 'F8', voice: false })" in WORLD
    panel = (WEB / "vendor" / "panel.js").read_text()
    assert "voiceBox = false" in panel and "voiceBox ? el('label', { class: 'fw-voice' }" in panel                                   # no voice tick in TALK
    assert "speakKey = 'Shift+8'" in (WEB / "vendor" / "switch.js").read_text()


def test_a_paused_run_stands_still_on_the_dashboard():
    """The user, 2026-11-07: paused, the dashboard kept ticking (the trace's k counts on, the world's tick stands)."""
    assert "if (this.last && f.tick === this.last.tick) return;" in (WEB / "dash.js").read_text()


def test_the_events_react_to_the_host_and_the_bridge(tmp_path):
    """events.js under node with a stub DOM: narrate sends the host's line and says the narration; send posts the event's own trace
    window to the bridge; the feed moves the event sent -> taken -> ruled ACCEPTED -> applied; an explain's answer is said and kept;
    a bridge that refuses is said, never silent."""
    js = tmp_path / "ev.mjs"
    js.write_text("""const stubEl = () => ({ innerHTML: '', onchange: null, onclick: null, querySelector: () => stubEl(), querySelectorAll: () => [] });
globalThis.document = { querySelector: () => stubEl() };
globalThis.localStorage = { getItem: () => null, setItem: () => {} };
const { Events } = await import(process.argv[2]);
const lines = [], said = [], posts = [];
const metis = {
  surprise: async b => { posts.push(['surprise', b]); return { id: 'S1', trace: 'traces/run-mark-3', member: 'planner' }; },
  explain: async b => { posts.push(['explain', b]); return { ref: 'X1' }; },
};
const ev = new Events(stubEl(), { line: l => lines.push(l), metis, speak: t => said.push(t), context: () => ({ scenario: 'cut_in', seed: '1' }) });
ev.scene({ trace: 'run', k: 100, t: 10, tick: 100 });
ev.edge(3, 'start'); ev.scene({ trace: 'run', k: 160, t: 16, tick: 160 }); ev.edge(3, 'stop', 'braked late');
ev.narrate(3);
ev.narrated({ n: 3, members: { planner: ['I keep my speed.'] }, text: 'x' });
await ev.send(3);
for (const st of [['taken'], ['ruled', 'accepted: the gate'], ['applied']]) ev.feed({ kind: 'surprise', id: 'S1', n: 3, status: st[0], verdict: st[1], commit: 'abc' });
await ev.explain(3);
ev.feed({ kind: 'answer', ref: 'X1', text: 'The cut-in came inside the brake reach.' });
const bad = new Events(stubEl(), { line: () => {}, metis: { surprise: async () => { throw new Error('the Metis bridge is off'); } }, speak: t => said.push('BAD ' + t) });
bad.scene({ trace: 'r2', k: 5, t: 0.5, tick: 5 }); bad.once(1, 'collision'); await bad.send(1);
const e = ev.get(3);
process.stdout.write(JSON.stringify({ lines, said, posts, state: e.state, answer: e.answer, sid: e.sid, bad_state: bad.get(1).state }));""")
    p = subprocess.run([node(), str(js), (WEB / "events.js").as_uri()], capture_output=True, text=True, timeout=60)
    assert p.returncode == 0, p.stderr
    o = json.loads(p.stdout)
    assert o["lines"] == ["narrate:3:run:100:160"]
    assert any("I keep my speed." in s for s in o["said"])
    kind, body = o["posts"][0]
    assert kind == "surprise" and body["run"] == "run" and body["window"] == [100, 160] and body["n"] == 3 and "braked late" in body["words"]
    assert o["sid"] == "S1" and o["state"] == "answered" and o["answer"] == "The cut-in came inside the brake reach."
    assert any(s == "Event 3: taken." for s in o["said"]) and any(s.startswith("Event 3: ruled accepted") for s in o["said"])
    assert any("Event 3: applied (abc)." == s for s in o["said"])
    assert any(s.startswith("BAD Event 1: send failed: the Metis bridge is off") for s in o["said"])
    assert o["bad_state"].startswith("send failed: the Metis bridge is off")                  # on the row too, not only said


def test_a_rerun_event_never_takes_the_first_runs_surprise(tmp_path):
    """Step 6 live: a re-run on the same trace numbers its events from 1 again; the bridge's feed, replayed after a reconnect, carries
    the first run's #1. The new #1 must keep no sid and no state of it, and its send must post its own window."""
    js = tmp_path / "rerun.mjs"
    js.write_text("""const store = {};
const stubEl = () => ({ innerHTML: '', onchange: null, onclick: null, querySelector: () => stubEl(), querySelectorAll: () => [] });
globalThis.document = { querySelector: () => stubEl() };
globalThis.localStorage = { getItem: k => store[k] ?? null, setItem: (k, v) => { store[k] = v; } };
const { Events } = await import(process.argv[2]);
const posts = [];
const metis = { surprise: async b => { posts.push(b); return { id: 'S' + posts.length, trace: 't', member: 'planner' }; }, explain: async () => ({}) };
let ev = new Events(stubEl(), { line: () => {}, metis, speak: () => {}, context: () => ({}) });
ev.scene({ trace: 'T', k: 300, t: 30, tick: 300 }); ev.edge(1, 'start'); ev.scene({ trace: 'T', k: 330, t: 33, tick: 330 }); ev.edge(1, 'stop');
await ev.send(1); ev.feed({ kind: 'surprise', id: 'S1', n: 1, status: 'applied' });
ev = new Events(stubEl(), { line: () => {}, metis, speak: () => {}, context: () => ({}) });
ev.scene({ trace: 'T', k: 336, t: 33.5, tick: 336 }); ev.edge(1, 'start'); ev.scene({ trace: 'T', k: 469, t: 46.8, tick: 469 }); ev.edge(1, 'stop');
for (const s of ['open', 'taken', 'ruled', 'applied']) ev.feed({ kind: 'surprise', id: 'S1', n: 1, status: s });
const mid = JSON.parse(JSON.stringify(ev.get(1)));
await ev.send(1);
process.stdout.write(JSON.stringify({ mid, after: ev.get(1), last: posts[posts.length - 1] }));""")
    p = subprocess.run([node(), str(js), (WEB / "events.js").as_uri()], capture_output=True, text=True, timeout=60)
    assert p.returncode == 0, p.stderr
    o = json.loads(p.stdout)
    assert "sid" not in o["mid"] and o["mid"].get("state") in (None, "")
    assert o["after"]["sid"] == "S2" and o["after"]["state"] == "sent to Metis" and o["last"]["window"] == [336, 469]


def test_a_restart_starts_a_new_trace_dir(tmp_path):
    """Step 6: the page's restart re-read the same config and rewrote the same trace dir from seg-0, leaving the last start's later
    segments: a trace no replay can read. fresh_trace gives the config and run.json a new stamped dir before the exec."""
    import sys as S
    import yaml
    S.path.insert(0, str(WEB.parent / "world"))
    import road_host as H
    cfg, rj = tmp_path / "config.yaml", tmp_path / "run.json"
    old = str(tmp_path / "traces" / "Town03-1-20261116T133826")
    cfg.write_text(yaml.safe_dump({"trace": {"dir": old, "every": 200}}))
    rj.write_text(json.dumps({"trace": old, "scenario": "Town03"}))
    new = H.fresh_trace(["python", "-m", "metis_agent.service", "--config", str(cfg)], str(rj))
    assert new != old and new.startswith(str(tmp_path / "traces" / "Town03-1-2")) and new.endswith("Z")
    assert yaml.safe_load(cfg.read_text())["trace"]["dir"] == new and json.loads(rj.read_text())["trace"] == new
    assert yaml.safe_load(cfg.read_text())["trace"]["every"] == 200
