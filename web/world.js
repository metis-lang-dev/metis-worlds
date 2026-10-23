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
// the domains' traces, the spoken lines; a dlg-trace of world_ui carries the page's effects)
// · {ev: 'world/status', state: waiting|working|asking|stuck|done|over, text, domain?, goal?,
// options?} (what the agent does and wants: the band's status line) · {ev: 'world/ask', question,
// options: [{label, say}], by, cornered?} (the director's question: its answers as chips; a chip
// says its answer, as typing it would).
// The shell is the consoles' (vendor/shell.css + shell.js): the docks talk, hierarchy, journal.
// The test hooks: window.world = {map, port, panel, frames, step(), stepAll(), log, docks, status}.
import { WorldMap } from './map.js';
import { Panel } from './vendor/panel.js';
import { connect } from './vendor/ws.js';
import { UiPort } from './vendor/ui-port.js';
import { Journal } from './vendor/journal.js';
import { Narrator, attachSelection, attachKey, narratorView } from './vendor/narrator.js';
import { keywordStop } from './vendor/dialog.js';

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
const hier = { rows: new Map(), attention: null, goal: null };
function resetHierarchy() {                          // a new task: the last task's chain, goals and end are over
  for (const r of hier.rows.values()) { r.last = null; r.sent = null; r.pending = null; }
  hier.ended = null; hier.goal = null;
  drawHierarchy();
}
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
    ${hier.goal && hier.goal.domain === r.name ? `<span class="goal">goal: ${esc(hier.goal.text)}</span>` : ''}
    ${r.last ? `<span class="g">${esc(r.last.goal)} → ${esc(r.last.result || '…')}</span>` : ''}
    ${r.name === 'task' && (world.map?.map?.task?.text || world.map?.map?.task?.goal) ? `<span class="g">this game's task: ${esc(world.map.map.task.text || world.map.map.task.goal)}</span>` : ''}</li>`).join('');
  $('#hstate').textContent = hier.ended ? `ended: ${hier.ended.slice(6, -1)}` : hier.attention ? `attention: ${hier.attention}` : '';
}

// ── the journal pane: metis-agent's model, its chat rows ──
const journal = new Journal();
function journalRow(row) {
  if (!row || (row.kind === 'world' && /world world_ui:/.test(row.text))) return;     // the page's own world lines: the port's, not the user's
  const li = document.createElement('li');
  li.className = `j-${row.who}`;
  li.innerHTML = `<span class="who">${esc(row.who === 'you' ? 'you' : row.who === 'note' ? '·' : 'agent')}</span> ${esc(row.text)}`;
  $('#jlog').appendChild(li);
  li.scrollIntoView?.({ block: 'nearest' });
}

// ── the agent's status and its question: what it wants from the person (alf-demo 3b) ──
world.status = null;
const chips = (box, options, pressed) => box.replaceChildren(...(options || []).map(o => {
  const b = document.createElement('button');
  b.type = 'button'; b.className = 'chip'; b.textContent = o.label; b.title = `says: ${o.say ?? o.label}`;
  b.onclick = () => { for (const c of box.children) c.setAttribute('aria-pressed', String(c === b)); answer(o); };
  if (pressed === o.label) b.setAttribute('aria-pressed', 'true');
  return b;
}));
function answer(o) {                                 // a chip is the person saying its answer (the same path as typing it)
  rec('answer', { say: o.say ?? o.label });
  if (o.ev) send({ ev: o.ev }); else panel.say(o.say ?? o.label);
}
let lastStatus = '', lastStatusRow = '';
// the map's letters (text mode: a letter is a kind's first, shared — c is a cabinet, a countertop and a coffee machine):
// a legend under the map, read off the drawn entries (opus's P3); none when the tiles are pictures
function legend() {
  const by = new Map();
  for (const b of document.querySelectorAll('#map .wm-ent')) {
    if (b.classList.contains('wm-agent')) continue;
    const ch = b.querySelector('.wm-ch')?.textContent?.trim(), name = b.querySelector('.wm-name')?.textContent?.replace(/\s*\d+$/, '').trim();
    if (ch && name) by.set(ch, (by.get(ch) || new Set()).add(name));
  }
  const el = $('#legend');
  el.hidden = !by.size;
  el.innerHTML = [...by.entries()].sort(([a], [b]) => a.localeCompare(b))
    .map(([ch, names]) => `<span><b>${esc(ch)}</b> ${[...names].sort().map(esc).join(' · ')}</span>`).join('') + '<span><b>@</b> the agent</span>';
}
// the tiles as large as the left pane allows (the map, its attention slot beside it when there is room)
function fitMap() {
  const v = $('#map .wm-view'), L = $('#left');
  if (!v || !L) return;
  const cols = Number(getComputedStyle(v).getPropertyValue('--cols')) || 1, rows = Number(getComputedStyle(v).getPropertyValue('--rows')) || 1;
  const w = L.clientWidth - 28 - (L.clientWidth > 900 ? 280 : 0), h = L.clientHeight - 40;
  const z = Math.max(1, Math.min(3, w / (cols * 16), h / (rows * 16)));
  $('#map').style.setProperty('--wm-z', z.toFixed(2));
}
addEventListener('resize', () => fitMap());
function status(f) {
  const was = world.status?.state;
  world.status = f;
  $('#status').dataset.state = f.state || '';
  $('#sstate').textContent = f.state || '';
  $('#stext').textContent = f.text || '';
  chips($('#sopts'), f.state === 'asking' ? [] : f.options);        // the ask's answers are in the ask box
  if (f.state !== 'asking') $('#ask').hidden = true;
  if (f.state === 'waiting' || (f.state === 'working' && ['done', 'stuck', 'over', 'asking', 'waiting'].includes(was))) resetHierarchy();
  if (f.state === 'waiting' && was === 'over' && world.mapUrl) world.map.load(world.mapUrl).then(fitMap);   // a new game: the room from its start
  if (f.state !== 'working') { hier.goal = null; if (f.state !== 'asking') hier.attention = null; drawHierarchy(); }
  if ((f.state === 'waiting' || f.state === 'working') && world.map.map?.entities?.some(e => e.cornered)) world.map.delta({ cornered: null });   // the ask is over: no place in red
  if (f.state === 'working' && f.domain) { hier.goal = { domain: f.domain, text: f.text.replace(/^[^:]*:\s*/, '') }; drawHierarchy(); }
  if (f.state !== 'working' && f.state !== 'asking' && f.text && f.text !== lastStatus) {   // waiting, done, stuck, over: one line each
    panel?.core.row({ who: 'note', text: f.text, status: f.state });
    lastStatusRow = f.text;
    journalRow({ who: 'note', text: `${f.state}: ${f.text}` });
  }
  lastStatus = f.text || lastStatus;
  $('#hstate').textContent = f.state === 'working' ? `attention: ${f.domain || hier.attention || ''}` : f.state || $('#hstate').textContent;
}
// the world's ask line carries its answers ("Fridge 1 is not … | put tomato 1 in microwave 1 | stop": task_domain's
// asking lines); a recording without world/ask (record_run.py's) gives them so: the question, then each answer
const asked = text => String(text ?? '').split(/\s+\|\s+/).map(x => x.trim()).filter(Boolean);
function ask(f) {
  if (!f.fromLine) world.asked = true;
  $('#askq').textContent = f.question || '';
  chips($('#askopts'), f.options);
  $('#ask').hidden = false;
  if (f.cornered) world.map.delta({ cornered: f.cornered });
}

// ── the band's rows in the page's words: an ask is an ask, the typed intent as its name and slots, the floor in words ──
const FLOOR = { FREEu: 'free', FREEs: 'free', USER: 'yours', SYSTEM: 'the agent\'s' };
// the typed intent in words: "FETCH object=TOMATO1 receptacle=MICROWAVE1" → "fetch: object tomato 1, receptacle microwave 1"
// (opus's P1); a handle reads as the map names it (TOMATO1 → tomato 1)
const spoken = v => String(v).toLowerCase().replace(/_/g, ' ').replace(/([a-z])(\d+)$/, '$1 $2');
function intentWords(text) {
  try {
    const o = JSON.parse(text);
    const verb = spoken(o.intent ?? '').trim();
    const slots = Object.entries(o).filter(([k]) => k !== 'intent' && k !== 'domain')    // a page widget is "the map" (opus's P6)
      .map(([k, v]) => k === 'widget' ? `the ${spoken(v)}` : `${k.replace(/_/g, ' ')} ${spoken(v)}`);
    return slots.length ? `${verb}: ${slots.join(', ')}` : verb;
  } catch { return text; }
}
world.intentWords = t => intentWords(t);
function rowLook(r) {
  const li = panel?.rowEl.get(r.n);
  if (!li || li.dataset.looked) return;
  li.dataset.looked = '1';
  const box = panel.dom.log;                         // the newest line in view, unless the person scrolled up to read
  requestAnimationFrame(() => { if (box.scrollHeight - box.scrollTop - box.clientHeight < 160) box.scrollTop = box.scrollHeight; });
  const who = li.querySelector('.fw-who'), text = li.querySelector('.fw-text');
  // a line the band already shows (the status line the agent then says, a reply that repeats its narration): once
  const prev = [...panel.dom.log.children].slice(-4, -1).filter(x => !x.hidden).map(x => x.querySelector('.fw-text')?.textContent.trim());
  if ((r.who === 'agent') && (prev.includes(r.text.trim()) || r.text.trim() === lastStatusRow.trim())) { li.hidden = true; return; }
  if (r.who === 'agent' && r.narration) {
    const asks = r.narration === 'v3-ask';
    if (asks) text.textContent = asked(r.text)[0] ?? r.text;            // the answers are the ask box's chips
    who.textContent = asks ? 'asks' : 'agent';
    li.classList.toggle('fw-ask', asks);
  } else if (r.who === 'intent') { text.textContent = intentWords(r.text); who.textContent = 'meant'; }
  else if (r.who === 'note' && r.status) { who.textContent = r.status; li.classList.add('fw-status'); }
}
function floorLook(s) { if (panel) panel.dom.floor.textContent = `floor: ${FLOOR[s.floor] ?? s.floor.toLowerCase()}`; }

// the voice navigation's next step, said when a list takes the focus (F10: the map took it, the band said nothing)
const HINT = { map: 'In the map: say "pick the microwave" (a thing by name), or "numbers" to pick by number.',
  hlist: 'In the hierarchy: say "pick task" (a domain by name), or "numbers".' };
let lastHint = null;
function hint(e) {
  const h = e?.ui === 'focus' && HINT[e.widget];
  if (!h || h === lastHint) return;
  lastHint = h;
  panel.note(h);
}

// ── the frames ──
let say = 0, panel = null, port = null, send = () => {};
async function frame(f) {
  rec('frame', { ev: f.ev });
  if (f.ev === 'world/map') { world.mapUrl = new URL(f.url, world.base).href; await world.map.load(world.mapUrl); fitMap(); legend(); tagCard(); return; }
  if (f.ev === 'world/delta') { world.map.delta(f); if (f.task) { chainTo(world.map.map.task); } return; }
  if (f.ev === 'world/hierarchy') { hierarchy(f); return; }
  if (f.ev === 'world/status') { status(f); return; }
  if (f.ev === 'world/ask') { ask(f); return; }
  if (f.ev === 'new_game_ack') { if (f.text) panel.note(f.text); return; }
  if (f.ev === 'page') { if (f.owns?.includes('world_ui')) port.sync(); return; }     // the claim: the takeover report
  if (f.ev !== 'journal' || !f.rec) return;
  const r = f.rec;
  if (r.kind === 'dlg-trace' && r.domain === 'world_ui' && r.effects) { for (const e of r.effects) effect(e); return; }
  if (r.kind === 'dlg-wake' && r.what === 'person' && world.replay) panel.core.row({ who: 'person', text: r.person, channel: 'main' });
  if (r.kind === 'dlg-say' && world.replay) {
    const [line, ...answers] = asked(r.text);
    panel.core.frame({ ev: 'narration', id: `s${++say}`, sentence: line, kind: r.what === 'ask' ? 'v3-ask' : 'v3-line' });
    if (r.what === 'ask' && answers.length && !world.asked) ask({ question: line, options: answers.map(a => ({ label: a, say: a })) });
  }
  const out = journal.add(r);
  journalRow(out.chat);
}
function effect(e) {
  rec('effect', { effect: e });
  port.effect(e);
  hint(e);
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
// the shell's docks (the consoles' look); a dock the port shows or hides for an effect goes through them, a dock the
// person shows or hides on the strip is reported to the port (docked)
let portDock = false, shown = {};
const docks = world.docks = MetisShell.docks({
  names: ['talk', 'hierarchy', 'journal'], key: 'worldpage.docks.v1',
  defaults: { talk: { shown: true, open: true }, hierarchy: { shown: true, open: true }, journal: { shown: true, open: false } },
  onChange: st => {
    for (const [d, s] of Object.entries(st)) {
      if (port && !portDock && (shown[d] ?? true) !== !!s.shown) port.docked(d, !!s.shown);
      shown[d] = !!s.shown;
    }
  },
});
docks.apply();
MetisShell.splitter();
port = world.port = new WorldPort({
  root: $('#root'), syncDocks: true,
  send: lines => { rec('port', { lines }); send({ ev: 'world', domain: 'world_ui', atoms: lines }); },
  log: (dir, e) => rec(dir, { e }),
  onDock: (w, on) => { portDock = true; try { docks.set(w, on ? { shown: true, open: true } : { shown: false }); } finally { portDock = false; } },
});
// a pick shows: the picked thing takes the focus (the map's attention slot says what it is; the hierarchy's task row
// opens its card), outlined — the port only marks it `.picked` (the Chrome test: "I picked it." and nothing to see)
port.onPick = (w, text, el) => {
  rec('picked', { w, text });
  el?.focus?.({ preventScroll: false });
  if (w === 'hlist' && el?.dataset?.domain === 'task') world.map.showTask('@agent');
};
panel = world.panel = new Panel($('#talkpanel'), {
  backend: backend || { turn: async function* () { yield 'This is a replay: nobody is listening.'; }, onFrame: null },
  table: await (await fetch('vendor/fsttm.json')).json(), title: '', voice: q.get('voice') === '1',
  onFrame: f => frame(f), onRow: r => rowLook(r), onState: s => floorLook(s),
});
floorLook(panel.core.state());
// "stop" (the dialog's stop words) cuts the page's own voice; while the agent works or asks, it is also the
// person's word to the agent (the ask's "stop" answer, F5): a turn of its own, past the floor's stop-word drop
const say0 = panel.core.say.bind(panel.core);
let stops = 0;
panel.core.say = (text, opts = {}) => {
  const t = String(text ?? '').trim();
  if (backend && t && keywordStop(t, panel.core.dialog.stopWords) && ['working', 'asking', 'stuck'].includes(world.status?.state)) {
    panel.core.tts.cancel?.();
    panel.core.via = opts.via ?? 'say';
    try { return panel.core.turn(t, { id: `stop${++stops}` }); } finally { panel.core.via = null; }
  }
  return say0(text, opts);
};
window.say = text => panel.say(text);
if (backend) hello(backend);
// the narrator (fsttm-web 0.6): the page's selected text read aloud on F8 (the task card's words, the journal), never
// taking the floor: it wraps the band's own TTS and yields while the dialog speaks
const narrator = world.narrator = new Narrator({ tts: panel.core.tts });
attachSelection(narrator, document); attachKey(narrator, document, { key: 'F8' }); narratorView($('#narrator'), narrator);
$('#hlist').addEventListener('click', e => { const li = e.target.closest('li'); if (li?.dataset.domain === 'task') world.map.showTask('@agent'); });
$('#hlist').addEventListener('keydown', e => { const li = e.target.closest('li'); if (e.key === 'Enter' && li?.dataset.domain === 'task') world.map.showTask('@agent'); });
if (!agentUrl) await replay(q.get('replay') || 'fixtures/alfworld_tomato_microwave_13.run.jsonl');
document.body.dataset.ready = '1';
