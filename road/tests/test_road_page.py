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
    assert "if (panel.core.voice) panel.core.tts.speak([text]);" in WORLD and "speak: hear," in WORLD   # the loop's rows heard, not written in TALK


def test_the_dashboard_rolls_6000_ticks_and_moves_events():
    dash = (WEB / "dash.js").read_text()
    assert "export const WINDOW = 6000;" in dash
    assert "this.o.onMove?.(d.n, k0, k1" in dash and "if (d.moved && (k0 !== d.was[0] || k1 !== d.was[1]))" in dash   # a press is no move and 'data-act="narrate"' in dash and 'data-act="explain"' in dash
    ev = (WEB / "events.js").read_text()
    assert "this.line(`mark:${n}:move:${k0}:${k1}${i0 != null && i1 != null ? `:${i0}:${i1}` : ''}`)" in ev   # the k, and the run's ticks
    assert "this.loop.say(`/narrate ${e.trace} ${w0}..${w1} ${this.said(e)}`)" in ev   # one line, every member, the context
    assert "window(e) { return e.kind === 'mark' ? [e.k0, Math.max(e.k0, e.k1)] : [Math.max(0, e.k0 - LEAD), e.k0]; }" in ev   # a surprise with its lead-up
    road = (WEB / "road.js").read_text()
    assert "this.line(`mark:${n}:once:${kind}`)" in road and "if (stop && !this.paused) this.hold(true);" in road
    assert "const RING = 6000;" in ev and "if (e && !this.usable(e)) return;" in ev and ev.count("if (e && !this.usable(e)) return;") == 3   # a window the ring dropped: no loop action
