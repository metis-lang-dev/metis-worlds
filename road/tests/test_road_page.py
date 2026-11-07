"""The road page's loop dock, events and one voice (loop-road-ui s-0314a8ee step 2; the user's word 2026-11-07): the grammar that routes
a line to the pi loop or to the page's events (run under node: $NODE, else `node` on PATH; none, those tests skip, METIS_ROAD_REQUIRE_NODE=1
fails instead), and the page's shape: one TOOLS dock of cards, EVENTS, the LOOP dock as an iframe of the loop console (never its code), the
dashboard's rolling window and glyphs."""
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
    ("stop", {}, None),                                               # the car's word, never the loop's
    ("what's around us", {}, None),
    ("mark", {}, {"to": "page", "action": "mark"}),
    ("mark here", {}, {"to": "page", "action": "mark"}),
    ("End mark, the car braked for nothing.", {}, {"to": "page", "action": "endmark", "words": "the car braked for nothing"}),
    ("end the event", {}, {"to": "page", "action": "endmark", "words": ""}),
    ("agree", {"loopMark": 3}, {"to": "loop", "line": "/agree 3"}),
    ("agree", {}, None),                                              # nothing narrated yet: not the loop's
    ("yes, that is what I saw", {"loopMark": 2}, {"to": "loop", "line": "/agree 2"}),
    ("disagree, it should have kept going", {"loopMark": 3}, {"to": "loop", "line": "/disagree 3 it should have kept going"}),
    ("take it", {}, {"to": "loop", "line": "/take"}),
    ("take the next surprise", {}, {"to": "loop", "line": "/take"}),
    ("why lead_ok", {}, {"to": "loop", "line": "/why lead_ok"}),
    ("why did it brake", {}, {"to": "loop", "line": "why did it brake"}),
    ("what did you change", {}, {"to": "loop", "line": "/diff"}),
    ("show the ruling", {}, {"to": "loop", "line": "/ruling"}),
    ("apply", {}, {"to": "loop", "line": "/apply"}),
    ("confirm", {"gate": True}, {"to": "gate", "answer": "confirm"}),
    ("refuse", {"gate": True}, {"to": "gate", "answer": "refuse"}),
    ("confirm", {}, None),                                            # no gate open: the road's
    ("rebuild", {}, {"to": "loop", "line": "/rebuild"}),
    ("reload", {}, {"to": "loop", "line": "/reload"}),
    ("stop the loop", {}, {"to": "loop", "line": "/stop"}),
    ("loop, why did the planner change lanes?", {}, {"to": "loop", "line": "why did the planner change lanes?"}),
    ("/status", {}, {"to": "loop", "line": "/status"}),
    ("narrate", {}, {"to": "page", "action": "narrate"}),
    ("narrate event 4", {}, {"to": "page", "action": "narrate", "n": 4}),
    ("explain it", {}, {"to": "page", "action": "explain"}),
    ("send event 2 to the loop", {}, {"to": "page", "action": "send", "n": 2}),
    ("continue", {"paused": True}, {"to": "page", "action": "continue"}),
    ("continue", {}, None),                                           # not waiting on a surprise: the road's
    ("/narrate event 4", {}, {"to": "page", "action": "narrate", "n": 4}),   # typed as a command: the page's event, never the loop's /narrate
    ("/explain 4", {}, {"to": "page", "action": "explain", "n": 4}),
    ("/narrate 3", {}, {"to": "page", "action": "narrate", "n": 3}),
    ("send 2 to pi", {}, {"to": "page", "action": "send", "n": 2}),
    ("/narrate Town03-1-x 10..20 ctx", {}, {"to": "loop", "line": "/narrate Town03-1-x 10..20 ctx"}),
    ("load DynamicObjectCrossing", {"scenarios": ["Town03", "DynamicObjectCrossing"]}, {"to": "page", "action": "scenario", "name": "DynamicObjectCrossing"}),
    ("run the scenario town03", {"scenarios": ["Town03"]}, {"to": "page", "action": "scenario", "name": "Town03"}),
    ("load NoSuchThing", {"scenarios": ["Town03"]}, None),           # not in the tree: the road's (it says it does not know)
]


def node():
    n = os.environ.get("NODE") or shutil.which("node")
    if not n:
        if os.environ.get("METIS_ROAD_REQUIRE_NODE") == "1":
            pytest.fail("no node for the page's grammar (NODE or PATH)")
        pytest.skip("no node for the page's grammar")
    return n


def test_the_grammar_routes_the_loops_lines_and_leaves_the_roads(tmp_path):
    js = tmp_path / "run.mjs"
    js.write_text(f"""import {{ route }} from {json.dumps((WEB / "loopgrammar.js").as_uri())};
const cases = JSON.parse(process.argv[2]);
process.stdout.write(JSON.stringify(cases.map(([t, ctx]) => route(t, ctx))));""")
    p = subprocess.run([node(), str(js), json.dumps([[t, c] for t, c, _ in CASES])], capture_output=True, text=True, timeout=60)
    assert p.returncode == 0, p.stderr
    for (t, c, want), got in zip(CASES, json.loads(p.stdout)):
        if want and "n" not in want and got and got.get("n") is None:
            got.pop("n", None)
        assert got == want, (t, c)


def test_one_tools_dock_of_cards_events_and_the_loop():
    """Drive, Cars and Traffic: one TOOLS dock of collapsible cards (the DIALOG's fw-sec look); EVENTS and LOOP docks; the strip names them."""
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
    for el in ('id="t-add"', 'id="t-cr-run"', 'data-drive="turn:left"', 'id="picked"', 'id="run-info"', 'id="follow"', 'id="dock-events"', 'id="dock-loop"', 'id="loopbox"'):
        assert el in HTML, el
    assert "names: ['talk', 'tools', 'events', 'loop', 'hierarchy', 'world', 'journal', 'dialog'], key: 'roadpage.docks.v6'" in WORLD
    assert "#loopframe { flex: 1 1 auto; min-height: 0;" in HTML                     # the loop's chat scrolls in its dock, the page holds


def test_the_loop_is_an_iframe_of_the_console_never_its_code():
    dock = (WEB / "loopdock.js").read_text()
    assert "src: `${url}/?panels=chat&embed=${encodeURIComponent(location.origin)}`" in dock
    assert "if (e.origin !== this.origin || e.source !== this.frame.contentWindow) return;" in dock     # the console in our dock only
    assert "postMessage(m, this.origin)" in dock and "'*'" not in dock
    for f in WEB.glob("*.js"):
        assert "MetisLoop" not in f.read_text(), f                        # no loop code copied into road/web
    assert "if (chat.voice && chat.active === 'loop') panel.core.tts.speak([text]);" in WORLD and "speak: hear," in WORLD   # the loop's rows heard, not written in TALK


def test_the_dashboard_rolls_6000_ticks_and_moves_events():
    dash = (WEB / "dash.js").read_text()
    assert "export const WINDOW = 6000;" in dash
    assert "this.o.onMove?.(d.n, k0, k1" in dash and "if (d.moved && (k0 !== d.was[0] || k1 !== d.was[1]))" in dash   # a press is no move and 'data-act="narrate"' in dash and 'data-act="explain"' in dash
    ev = (WEB / "events.js").read_text()
    assert "this.line(`mark:${n}:move:${k0}:${k1}${i0 != null && i1 != null ? `:${i0}:${i1}` : ''}`)" in ev   # the k, and the run's ticks
    assert "this.loop.say(`/narrate ${e.trace} ${w0}..${w1} ${this.said(e)}`, undefined, `/narrate event ${e.n}`)" in ev   # one line, every member, the context
    assert "window(e) { return e.kind === 'mark' ? [e.k0, Math.max(e.k0, e.k1)] : [Math.max(0, e.k0 - LEAD), e.k0]; }" in ev   # a surprise with its lead-up
    road = (WEB / "road.js").read_text()
    assert "this.line(`mark:${n}:once:${kind}`)" in road and "if (stop && !this.paused) this.hold(true);" in road
    assert "const RING = 6000;" in ev and "if (e && !this.usable(e)) return;" in ev and ev.count("if (e && !this.usable(e)) return;") == 3   # a window the ring dropped: no loop action


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


def test_the_voice_goes_to_the_last_active_chat():
    """The user, 2026-11-07: voice for two chats. TALK or LOOP, the last one active (clicked, focused, the loop's frame entered) takes
    the mic and is spoken; its header's dot is green. The voice switch is the band's (Shift+8), over both; no tick in TALK, no say button."""
    for dock in ('id="dock-talk"', 'id="dock-loop"'):
        head = HTML[HTML.index(dock):HTML.index('</header>', HTML.index(dock))]
        assert '<span class="chatdot" aria-hidden="true">●</span>' in head, dock
    assert ".chat-active .chatdot { visibility: visible; color: var(--green" in HTML
    assert "$('#dock-talk').addEventListener('pointerdown', () => setChat('talk'));" in WORLD and "$('#dock-loop').addEventListener('pointerdown', () => setChat('loop'));" in WORLD
    assert "if (document.activeElement?.id === 'loopframe') setChat('loop');" in WORLD
    assert "if (t && opts.via === 'voice' && chat.active === 'loop') {" in WORLD and "loop.say(r?.line ?? t, 'heard')" in WORLD   # heard: to the active chat
    assert "panel.core.setVoice(chat.voice && chat.active === 'talk');" in WORLD                                                     # TALK spoken only while active
    assert "vw.voice = voiceSwitch(voiced, { store: 'roadpage.voice'" in WORLD and "voiceWidget(panel, { narrator, key: 'F8', voice: false })" in WORLD
    panel = (WEB / "vendor" / "panel.js").read_text()
    assert "voiceBox = false" in panel and "voiceBox ? el('label', { class: 'fw-voice' }" in panel                                   # no voice tick in TALK
    assert "speakKey = 'Shift+8'" in (WEB / "vendor" / "switch.js").read_text()


def test_a_paused_run_stands_still_on_the_dashboard_and_the_loop_chat_hands_the_page_its_events():
    """The user, 2026-11-07: paused, the dashboard kept ticking (the trace's k counts on, the world's tick stands); "narrate event 4"
    typed in the loop's chat reached the loop's /narrate (a trace and a window) and failed: the console's face hands it to the page."""
    assert "if (this.last && f.tick === this.last.tick) return;" in (WEB / "dash.js").read_text()
    dock = (WEB / "loopdock.js").read_text()
    assert "if (d.metis === 'page' && typeof d.text === 'string') { this.onPage(d.text); return; }" in dock
    assert "onPage: t => { if (!redirect(t, 'text')) loop.say(t); }," in WORLD
