// world.js — the road's own page (road-agent s-357becc7), the same shell as NetHack's and ALFWorld's: started from minihack/web/world.js, it changes here alone. The left pane is the
// road's: the 3D client's frame (client.html), its tools over it and the dashboard under it (dash.js). The docks talk, world card, journal and dialog are as on the other worlds: the
// agent (metis-agent's /ws) and the dialog (fsttm-web, vendor/). The controls go to the responder's host as world lines (road_host.py): run:SCENARIO:SEED, play, pause, speed:X, watching.
import { Dash } from './dash.js';
import { Panel } from './vendor/panel.js';
import { connect } from './vendor/ws.js';
import { Journal } from './vendor/journal.js';
import { Narrator, attachSelection, attachKey } from './vendor/narrator.js';
import { voiceWidget } from './vendor/switch.js';

const $ = s => document.querySelector(s);
const esc = s => String(s ?? '').replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' })[c]);
const world = window.world = {};
const rows = (el, pairs) => { el.replaceChildren(...pairs.flatMap(([k, v]) => { const dt = document.createElement('dt'), dd = document.createElement('dd'); dt.textContent = k; dd.textContent = v; return [dt, dd]; })); };
const dash = new Dash($('#dash'));
let panel = null, send = () => {};
let view = null, viewReady = false, paused = false, following = false, ego = 'ego', picked = null, lastCmd = null, say = 0;
const line = l => send({ ev: 'world', domain: 'responder', atoms: [l] });
const post = o => { if (view && viewReady) view.contentWindow.postMessage(o, location.origin); };

// ── the 3D view and its tools ──
function openView(net) {
  view = document.createElement('iframe');
  view.id = 'view';
  view.src = 'client.html';
  view.addEventListener('load', () => { viewReady = true; post({ net }); if (following) post({ follow: ego }); });
  $('#wait').replaceWith(view);
}
function setPaused(p, tell = true) {
  paused = p;
  $('#play').textContent = p ? 'play' : 'pause';
  if (tell) line(p ? 'pause' : 'play');
}
function showPicked(f) {                             // the car clicked in the view: the scene's numbers for it, and its role as the ego believes
  const m = picked && f.movers.find(o => o.id === picked);
  $('#picked-tools').hidden = !m;
  if (!m) { rows($('#picked'), [[picked ? 'gone' : 'click a car', '']]); return; }
  const role = Object.entries(f.roles).find(([, id]) => id === m.id);
  rows($('#picked'), [['id', m.id], ['type', m.type], ['lane', m.lane], ['s', `${m.s.toFixed(1)} m`], ['speed', `${m.speed.toFixed(1)} m/s`], ['role', m.id === f.ego ? 'the ego' : role ? role[0] : 'none']]);
}
function scene(f) {
  ego = f.ego;
  post({ scene: f });
  dash.scene(f);
  const me = f.movers.find(m => m.id === f.ego);
  rows($('#run-info'), [['time', `${f.t.toFixed(1)} s`], ['tick', f.tick], ['movers', f.movers.length], ['the sensor sees', f.seen ?? '-'], ['tracks', f.tracks ?? '-'],
    ['restricted ticks', f.restricted], ['collisions', f.collisions], ['arrived', f.arrived ? 'yes' : 'no']]);
  rows($('#ego'), [['lane', me?.lane ?? '-'], ['s', me ? `${me.s.toFixed(1)} m` : '-'], ['speed', me ? `${me.speed.toFixed(1)} m/s` : '-'], ['applied', f.a == null ? '-' : `${f.a} m/s²`],
    ['command', (f.cmd || []).filter(x => x != null).join(' ') || '-'], ['response, long', f.fold.resp_lon], ['response, lat', f.fold.resp_lat]]);
  showPicked(f);
  const known = Object.entries(f.roles);
  rows($('#roles'), known.length ? known : [['nobody', '']]);
}
$('#run').onclick = () => { line(`run:${$('#scenario').value}:${Math.max(1, Number($('#seed').value) || 1)}`); setPaused(false, false); };
$('#play').onclick = () => setPaused(!paused);
$('#speed').onchange = e => line(`speed:${e.target.value}`);
$('#follow').onclick = e => { following = !following; e.target.setAttribute('aria-pressed', following); post(following ? { follow: ego } : { unfollow: true }); };
$('#center').onclick = () => post({ center: ego });
$('#follow-picked').onclick = () => { if (picked) { following = true; $('#follow').setAttribute('aria-pressed', true); post({ unfollow: true }); post({ follow: picked }); } };
$('#center-picked').onclick = () => { if (picked) post({ center: picked }); };
addEventListener('message', e => {
  if (e.origin !== location.origin) return;
  if ('clicked' in e.data) picked = e.data.clicked;
  if (e.data.followed === false) { following = false; $('#follow').setAttribute('aria-pressed', false); }
  if (e.data.client === 'pause') setPaused(true);
  if (e.data.client === 'resume') setPaused(false);
  if (e.data.client === 'delay' && e.data.ms > 0) line(`speed:${Math.min(4, 100 / e.data.ms)}`);
});

// ── the journal pane: metis-agent's model, its chat rows, and the stack's commands ──
const journal = new Journal();
$('#jsave').onclick = async () => {                  // the service's whole journal
  const text = await (await fetch('world/journal.jsonl')).text();
  const a = document.createElement('a');
  a.href = URL.createObjectURL(new Blob([text], { type: 'application/jsonl' }));
  a.download = `road-journal-${Date.now()}.jsonl`;
  a.click();
  URL.revokeObjectURL(a.href);
};
function journalRow(row) {
  if (!row) return;
  const li = document.createElement('li');
  li.className = `j-${row.who}`;
  li.innerHTML = `<span class="who">${esc(row.who === 'you' ? 'you' : row.who === 'note' ? '·' : row.who === 'agent' ? 'agent' : row.who)}</span> ${esc(row.text)}`;
  const box = $('#jlog');
  box.appendChild(li);
  while (box.children.length > 400) box.firstChild.remove();
  li.scrollIntoView?.({ block: 'nearest' });
}
const COMMANDS = /^(brake|change|accel|keep|yield|drive_away|stop_lat|pace|lane|pass|follow|resume|around)/;
function commands(rec) {                             // what each member fired that is a command or the task's; a command held tick after tick is one row
  if (rec.kind !== 'dlg-trace' || !['responder', 'planner', 'task'].includes(rec.domain)) return;
  for (const row of rec.fired || []) {
    if (row.kind !== 'clause' || !COMMANDS.test(row.event) || row.event === lastCmd) continue;
    lastCmd = row.event;
    journalRow({ who: rec.domain, text: row.line || row.event });
  }
}

// ── the agent's status and its question ──
world.status = null;
const chips = (box, options, pressed) => box.replaceChildren(...(options || []).map(o => {
  const b = document.createElement('button');
  b.type = 'button'; b.className = 'chip'; b.textContent = o.label; b.title = `says: ${o.say ?? o.label}`;
  b.onclick = () => { for (const c of box.children) c.setAttribute('aria-pressed', String(c === b)); answer(o); };
  if (pressed === o.label) b.setAttribute('aria-pressed', 'true');
  return b;
}));
function answer(o) {                                 // a chip is the person saying its answer (the same path as typing it)
  if (o.card) docks.set('world', { shown: true, open: true });
  if (o.ev) send({ ev: o.ev }); else panel.say(o.say ?? o.label);
}
let lastStatus = '', lastStatusRow = '';
function status(f) {
  world.status = f;
  $('#status').dataset.state = f.state || '';
  $('#sstate').textContent = f.state || '';
  $('#stext').textContent = f.text || '';
  chips($('#sopts'), f.state === 'asking' ? [] : [...(f.options || []), ...(f.state === 'waiting' && world.card ? [{ label: 'what can I ask?', card: true }] : [])]);
  if (f.state !== 'asking') $('#ask').hidden = true;
  if (f.state !== 'working' && f.state !== 'asking' && f.text && f.text !== lastStatus) {
    panel?.core.row({ who: 'note', text: f.text, status: f.state });
    lastStatusRow = f.text;
    journalRow({ who: 'note', text: `${f.state}: ${f.text}` });
  }
  lastStatus = f.text || lastStatus;
}
function ask(f) {
  $('#askq').textContent = f.question || '';
  chips($('#askopts'), f.options);
  $('#ask').hidden = false;
}
const asked = text => String(text ?? '').split(/\s+\|\s+/).map(x => x.trim()).filter(Boolean);

// ── the world card ──
async function worldCard(url) {
  const c = (await (await fetch(url)).json()).card, box = $('#wcard');
  world.card = c || null;
  if (!c) { box.innerHTML = '<p class="empty">This world has no card.</p>'; return; }
  box.innerHTML = `<p class="wc-title">${esc(c.title)}</p>
    ${(c.about || []).map(a => `<p class="wc-about">${esc(a)}</p>`).join('')}
    ${c.asks?.length ? `<div class="wc-h">what you can ask</div><div id="wcasks">${c.asks.map((a, i) => `<div class="wc-ask"><button type="button" class="chip" data-ask="${i}">${esc(a.say)}</button><span class="what">${esc(a.what)}</span></div>`).join('')}</div>` : ''}
    ${c.cannot?.length ? `<div class="wc-h">it cannot</div><ul class="wc-cannot">${c.cannot.map(x => `<li>${esc(x)}</li>`).join('')}</ul>` : ''}
    ${c.source ? `<p class="wc-src">${esc(c.source)}</p>` : ''}`;
  for (const b of box.querySelectorAll('[data-ask]')) b.onclick = () => answer({ say: c.asks[Number(b.dataset.ask)].say });
}

// ── the band's rows in the page's words ──
const FLOOR = { FREEu: 'free', FREEs: 'free', USER: 'yours', SYSTEM: 'the agent\'s' };
// the typed intent in words: "FETCH object=TOMATO1 receptacle=MICROWAVE1" → "fetch: object tomato 1, receptacle microwave 1"
// (opus's P1); a handle reads as the map names it (TOMATO1 → tomato 1)
const spoken = v => String(v).toLowerCase().replace(/_/g, ' ').replace(/([a-z])(\d+)$/, '$1 $2');
function intentWords(text) {
  try {
    const o = JSON.parse(text);
    const verb = spoken(o.intent ?? '').trim();
    const slots = Object.entries(o).filter(([k]) => k !== 'intent' && k !== 'domain')
      .map(([k, v]) => `${k.replace(/_/g, ' ')} ${spoken(v)}`);
    return slots.length ? `${verb}: ${slots.join(', ')}` : verb;
  } catch { return text; }
}
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
    who.textContent = asks ? 'asks' : r.narration === 'v3-card' ? 'world' : 'agent';   // v3-card: the world card's line (hello, an unknown)
    li.classList.toggle('fw-ask', asks);
  } else if (r.who === 'intent') {
    // small talk is talk, not an errand: the person's line and her reply, no "meant" row (the user, 2026-10-24)
    if (/"intent"\s*:\s*"CHITCHAT"/.test(r.text)) { li.hidden = true; return; }
    text.textContent = intentWords(r.text); who.textContent = 'meant';
  }
  else if (r.who === 'note' && r.status) { who.textContent = r.status; li.classList.add('fw-status'); }
}
function floorLook(s) { if (panel) panel.dom.floor.textContent = `floor: ${FLOOR[s.floor] ?? s.floor.toLowerCase()}`; }


// ── the frames ──
function frame(f) {
  if (f.ev === 'world/scene') { scene(f); return; }
  if (f.ev === 'world/net') { dash.net(f); if (!view) openView(f.net); else post({ net: f.net }); return; }
  if (f.ev === 'world/summary') { dash.summary(f); return; }
  if (f.ev === 'world/map') { worldCard(new URL(f.url, location.href).href); return; }
  if (f.ev === 'world/status') { status(f); return; }
  if (f.ev === 'world/ask') { ask(f); return; }
  if (f.ev === 'world/message') { panel.core.frame({ ev: 'narration', id: `g${++say}`, sentence: f.text, kind: 'v3-card' }); journalRow({ who: 'agent', text: f.text }); return; }
  if (f.ev !== 'journal' || !f.rec) return;
  if (f.rec.kind === 'dlg-world') return;                // the page's own lines: watching, play, speed
  commands(f.rec);
  journalRow(journal.add(f.rec).chat);
}

// ── start ──
const agentUrl = `${location.protocol === 'https:' ? 'wss' : 'ws'}://${location.host}/ws`;
const hello = b => { b.send({ ev: 'hello', since: 1e15 }); line('watching'); };
const backend = await connect(agentUrl, { timeoutMs: 5000, reconnect: 2000, onReopen: b => hello(b) });
if (!backend) $('#conn').textContent = `no agent at ${agentUrl}`;
else { send = m => { if (backend.isOpen) backend.send(m); }; $('#conn').textContent = 'live'; }
setInterval(() => line('watching'), 2000);           // the scene comes every step while a page says so, else every second
const docks = world.docks = MetisShell.docks({
  names: ['talk', 'world', 'journal', 'dialog'], key: 'roadpage.docks.v1', fold: false,
  defaults: { talk: { shown: true, open: true }, world: { shown: true, open: true }, journal: { shown: true, open: true }, dialog: { shown: false, open: true } },
  onChange: st => panel?.showDialog(!!st.dialog?.shown),
});
docks.apply();
MetisShell.splitter();
const NOT_EVENTS = new Set(['world/scene', 'world/net']);   // ten a second: not the dialog's events
panel = world.panel = new Panel($('#talkpanel'), {
  backend, table: await (await fetch('vendor/fsttm.json')).json(), title: '', voice: false,
  sections: ['floor', 'state', 'events'], dialogIn: $('#dialogpart'), micButton: false,
  frames: f => String(f.ev ?? '').startsWith('world/') && !NOT_EVENTS.has(f.ev),
  onFrame: f => frame(f), onRow: r => rowLook(r), onState: s => floorLook(s),
});
floorLook(panel.core.state());
panel.showDialog(!!docks.state.dialog?.shown);
window.say = text => panel.say(text);
if (backend) hello(backend);
const narrator = world.narrator = new Narrator({ tts: panel.core.tts });
attachSelection(narrator, document); attachKey(narrator, document, { key: 'F8' });
$('#voice').replaceWith(Object.assign(voiceWidget(panel, { narrator, key: 'F8' }).el, { id: 'voice' }));
document.body.dataset.ready = '1';
