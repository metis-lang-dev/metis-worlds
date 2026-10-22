// world.js — the world page (alf-demo step 3b, alfworld/docs/DEMO.md §4–§5): the map
// (map.js), the dialog band (fsttm-web's panel, copied in vendor/), the hierarchy of the domains at
// work (the director's atoms), the journal (metis-agent's journal model, copied), and voice
// navigation of the page itself (web/domains/world_ui: the page is that domain's host, through
// the ui port).
//
//   world.html?replay=fixtures/x.run.jsonl[&speed=4]  a recorded turn, frame by frame (play / step)
//   world.html?agent=ws://127.0.0.1:8395/ws            live: metis-agent's /ws (the person's words,
//   world.html?live=1[&map=fixtures/x.json]            the journal, world/* frames, world_ui's effects);
//                                                     live=1: this host's /ws (web/run.sh serves the page)
//
// The frames (the same in both): {ev: 'world/map', url} · {ev: 'world/delta', …} (map.js's delta)
// · {ev: 'world/hierarchy', beat, arrival, effects, state} (the director's atoms) · {ev:
// 'journal', rec} (metis-agent's dlg-* records: the words, the dispatch, activate/deactivate,
// the domains' traces, the spoken lines; a dlg-trace of world_ui carries the page's effects).
// The test hooks: window.world = {map, port, panel, frames, step(), stepAll(), log}.
import { WorldMap } from './map.js';
import { Panel } from './vendor/panel.js';
import { connect } from './vendor/ws.js';
import { UiPort } from './vendor/ui-port.js';
import { Journal } from './vendor/journal.js';

const $ = s => document.querySelector(s);
const esc = s => String(s ?? '').replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' })[c]);
const q = new URLSearchParams(location.search);
const ORDER = ['task', 'nav', 'access', 'grasp', 'place'];    // the hierarchy's rows, the planner first; others as they appear

// ── the page as world_ui's host: the map's things and the hierarchy's domains are list entries ──
class WorldPort extends UiPort {
  entries(w) {
    if (w === 'map') return world.map.entries();
    if (w === 'hlist') return [...document.querySelectorAll('#hlist li')];
    return super.entries(w);
  }
  badges(items) { this.unbadge(); items.forEach((e, i) => { if (i < 9) e.dataset.n = String(i + 1); }); }
  unbadge() { for (const e of document.querySelectorAll('[data-n]')) delete e.dataset.n; }
}

const world = window.world = { log: [], frames: [], at: 0 };
const rec = (dir, f) => world.log.push({ t: Math.round(performance.now()), dir, ...f });

// ── the hierarchy pane: the director's atoms as rows ──
const hier = { rows: new Map(), attention: null };
function hierarchy(f) {
  const st = f.state || [];
  const arg = a => a.slice(a.indexOf('(') + 1, -1).split(',');
  const names = new Set([...ORDER.filter(d => st.some(a => arg(a)[0] === d)), ...st.filter(a => /^(in)?active\(/.test(a)).map(a => arg(a)[0])]);
  for (const d of names) {
    const r = hier.rows.get(d) || { name: d, goals: [] };
    r.active = st.includes(`active(${d})`);
    r.sent = st.find(a => a.startsWith(`sent(${d},`)) ? arg(st.find(a => a.startsWith(`sent(${d},`)))[1] : null;
    r.pending = st.find(a => a.startsWith(`pending(${d},`)) ? arg(st.find(a => a.startsWith(`pending(${d},`)))[1] : null;
    hier.rows.set(d, r);
  }
  hier.attention = (st.find(a => a.startsWith('attention(')) || '').slice(10, -1) || null;
  hier.ended = (f.effects || []).find(e => e.startsWith('ended(')) || hier.ended;
  drawHierarchy();
}
function chainTo(task) {                             // the task's chain gives each specialist its last goal and result
  for (const s of task.chain || []) {
    const r = hier.rows.get(s.domain) || { name: s.domain, goals: [] };
    r.last = s; hier.rows.set(s.domain, r);
  }
  drawHierarchy();
}
function drawHierarchy() {
  const rows = [...hier.rows.values()].sort((a, b) => (ORDER.indexOf(a.name) + 99) % 99 - (ORDER.indexOf(b.name) + 99) % 99);
  $('#hlist').innerHTML = rows.map(r => `<li data-domain="${esc(r.name)}" class="${r.active ? 'on' : 'off'}${hier.attention === r.name ? ' att' : ''}" tabindex="-1">
    <b>${esc(r.name)}</b> <span class="st">${r.active ? (hier.attention === r.name ? 'attending' : 'active') : 'asleep'}</span>
    ${r.sent ? `<span class="k">on ${esc(r.sent)}</span>` : ''}${r.pending ? `<span class="k">· put aside: ${esc(r.pending)}</span>` : ''}
    ${r.last ? `<span class="g">${esc(r.last.goal)} → ${esc(r.last.result || '…')}</span>` : ''}
    ${r.name === 'task' && world.map?.map?.task?.goal ? `<span class="g">${esc(world.map.map.task.goal)}</span>` : ''}</li>`).join('');
  $('#hstate').textContent = hier.ended ? `ended: ${hier.ended.slice(6, -1)}` : hier.attention ? `attention: ${hier.attention}` : '';
}

// ── the journal pane: metis-agent's model, its chat rows ──
const journal = new Journal();
function journalRow(row) {
  if (!row) return;
  const li = document.createElement('li');
  li.className = `j-${row.who}`;
  li.innerHTML = `<span class="who">${esc(row.who === 'you' ? 'you' : row.who === 'note' ? '·' : 'agent')}</span> ${esc(row.text)}`;
  $('#jlog').appendChild(li);
  li.scrollIntoView?.({ block: 'nearest' });
}

// ── the frames ──
let say = 0, panel = null, port = null, send = () => {};
async function frame(f) {
  rec('frame', { ev: f.ev });
  if (f.ev === 'world/map') { await world.map.load(new URL(f.url, world.base).href); tagCard(); return; }
  if (f.ev === 'world/delta') { world.map.delta(f); if (f.task) { chainTo(world.map.map.task); } return; }
  if (f.ev === 'world/hierarchy') { hierarchy(f); return; }
  if (f.ev === 'page') { if (f.owns?.includes('world_ui')) port.sync(); return; }     // the claim: the takeover report
  if (f.ev !== 'journal' || !f.rec) return;
  const r = f.rec;
  if (r.kind === 'dlg-trace' && r.domain === 'world_ui' && r.effects) { for (const e of r.effects) effect(e); return; }
  if (r.kind === 'dlg-wake' && r.what === 'person' && world.replay) panel.core.row({ who: 'person', text: r.person, channel: 'main' });
  if (r.kind === 'dlg-say' && world.replay) panel.core.frame({ ev: 'narration', id: `s${++say}`, sentence: r.text, kind: r.what === 'ask' ? 'v3-ask' : 'v3-template' });
  const out = journal.add(r);
  journalRow(out.chat);
}
function effect(e) {
  rec('effect', { effect: e });
  port.effect(e);
}

// the task card is map.js's dialog: world_ui's `card`, its close button `cardclose`
function tagCard() {
  const d = $('#map .wm-task'), b = d?.querySelector('.wm-close');
  if (!d || d.dataset.w) return;
  Object.assign(d.dataset, { w: 'card', role: 'dialog', entry: 'cardclose' }); d.tabIndex = -1;
  if (b) Object.assign(b.dataset, { w: 'cardclose', role: 'button' });
  const show = d.showModal.bind(d);
  let rising = false;                                // the card rises through the port (+opened), which calls showModal itself
  d.showModal = () => {
    if (rising || !port) return show();
    rising = true;
    try { port.openDialog(d); } finally { rising = false; }
  };
}

// ── replay: the recording, frame by frame ──
async function replay(url) {
  world.replay = true;
  world.base = new URL(url, location.href).href;
  const text = await (await fetch(world.base)).text();
  world.frames = text.split('\n').filter(Boolean).map(l => JSON.parse(l));
  const speed = Number(q.get('speed') || 1);
  let timer = null;
  world.step = async () => { if (world.at < world.frames.length) await frame(world.frames[world.at++]); drawCtrl(); return world.at < world.frames.length; };
  world.stepAll = async () => { while (await world.step()) { /* every frame */ } };
  const play = () => {
    if (timer) { clearTimeout(timer); timer = null; drawCtrl(); return; }
    const next = async () => { if (!(await world.step())) { timer = null; drawCtrl(); return; } timer = setTimeout(next, (world.frames[world.at]?.dt ?? 400) / speed); };
    timer = setTimeout(next, 0); drawCtrl();
  };
  $('#play').onclick = play; $('#step').onclick = () => world.step();
  const drawCtrl = () => {
    $('#play').textContent = timer ? 'pause' : world.at >= world.frames.length ? 'done' : 'play';
    $('#conn').textContent = `replay · ${world.at}/${world.frames.length}`;
  };
  await world.step();                                // the map first
  drawCtrl();
  if (q.get('autoplay')) play();
}

// ── live: metis-agent's /ws ──
async function live(url) {
  world.base = location.href;
  await frame({ ev: 'world/map', url: q.get('map') || 'fixtures/alfworld_tomato_microwave_13.json' });
  const backend = await connect(url, { timeoutMs: 5000, reconnect: 2000, onReopen: hello });
  if (!backend) { $('#conn').textContent = `no agent at ${url}`; return null; }
  send = m => { if (backend.isOpen) backend.send(m); };
  $('#conn').textContent = 'live';
  for (const b of ['#play', '#step']) $(b).disabled = true;
  return backend;          // the hello once the panel listens (start)
}

// ── start ──
world.map = new WorldMap($('#map'), {
  base: { sheet: 'tiles/nethack/glyphs.png', glyphs: 'tiles/nethack/glyphs.json', index: ['tiles/index.json'] },
  onTask: () => rec('task', {}),
});
const agentUrl = q.get('agent') || (q.get('live') ? `${location.protocol === 'https:' ? 'wss' : 'ws'}://${location.host}/ws` : null);
const hello = b => b.send({ ev: 'hello', since: 1e15, claim: ['world_ui'] });
const backend = agentUrl ? await live(agentUrl) : null;
port = world.port = new WorldPort({
  root: $('#root'), syncDocks: true,
  send: lines => { rec('port', { lines }); send({ ev: 'world', domain: 'world_ui', atoms: lines }); },
  log: (dir, e) => rec(dir, { e }),
});
panel = world.panel = new Panel($('#talkpanel'), {
  backend: backend || { turn: async function* () { yield 'This is a replay: nobody is listening.'; }, onFrame: null },
  table: await (await fetch('vendor/fsttm.json')).json(), title: 'talk', voice: q.get('voice') === '1',
  onFrame: f => frame(f),
});
window.say = text => panel.say(text);
if (backend) hello(backend);
$('#hlist').addEventListener('click', e => { const li = e.target.closest('li'); if (li?.dataset.domain === 'task') world.map.showTask('@agent'); });
$('#hlist').addEventListener('keydown', e => { const li = e.target.closest('li'); if (e.key === 'Enter' && li?.dataset.domain === 'task') world.map.showTask('@agent'); });
if (!agentUrl) await replay(q.get('replay') || 'fixtures/alfworld_tomato_microwave_13.run.jsonl');
document.body.dataset.ready = '1';
