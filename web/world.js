// world.js — the world page (alf-demo step 3b, alfworld/docs/DEMO.md §4–§5): the map
// (map.js), the dialog band (fsttm-web's panel, copied in vendor/), the hierarchy of the domains at
// work (the director's atoms), the journal (metis-agent's journal model, copied). One voice
// paradigm, the dialog (voice-nav-removal s-90621b2c): the page's own affordances turn INTO the
// chat (the world card's ask chips, the status line's answers), never a voice navigation of it.
//
//   world.html?replay=fixtures/x.run.jsonl[&speed=4]  a recorded turn, frame by frame (play / step)
//   world.html?agent=ws://127.0.0.1:8395/ws            live: metis-agent's /ws (the person's words,
//   world.html?live=1[&map=fixtures/x.json]            the journal, world/* frames);
//                                                     live=1: this host's /ws (alfworld/demo.sh serves the page)
// Live with a runner that loads games (the service's /world/games.json: alfworld/demo.sh), the top bar's picker
// names another room: load_game, the agent goes there and keeps running (world/loading, then world/map, a status and
// world/room; the talk and journal panes go on). Under the map, the game: its name and its task.
//
// The frames (the same in both): {ev: 'world/map', url} · {ev: 'world/delta', …} (map.js's delta)
// · {ev: 'world/hierarchy', beat, arrival, effects, state} (the director's atoms) · {ev:
// 'journal', rec} (metis-agent's dlg-* records: the words, the dispatch, activate/deactivate,
// the domains' traces, the spoken lines)
// · {ev: 'world/status', state: waiting|working|asking|stuck|done|over, text, domain?, goal?,
// options?} (what the agent does and wants: the band's status line) · {ev: 'world/ask', question,
// options: [{label, say}], by, cornered?} (the director's question: its answers as chips; a chip
// says its answer, as typing it would).
// The shell is the consoles' (vendor/shell.css + shell.js): the docks talk, hierarchy, world card, journal,
// dialog — tools the strip shows and hides, not folded themselves (the architect's ruling, 2026-10-24).
// The test hooks: window.world = {map, panel, frames, step(), stepAll(), log, docks, status}.
import { WorldMap } from './map.js';
import { Panel } from './vendor/panel.js';
import { connect } from './vendor/ws.js';
import { Journal } from './vendor/journal.js';
import { Narrator, attachSelection, attachKey } from './vendor/narrator.js';
import { voiceWidget } from './vendor/switch.js';
import { keywordStop } from './vendor/dialog.js';

const $ = s => document.querySelector(s);
const esc = s => String(s ?? '').replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' })[c]);
const q = new URLSearchParams(location.search);
const ORDER = ['task', 'nav', 'access', 'grasp', 'place'];    // the hierarchy's rows, the planner first; others as they appear

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
const jrecs = [];                                    // the records this page has seen (a recording's: live, the service keeps them all)
$('#jsave').onclick = async () => {                  // live: the service's whole journal, from before this page loaded too
  let text = null;
  try { const r = await fetch(new URL('world/journal.jsonl', world.base)); if (r.ok) text = await r.text(); } catch { /* a recording: no service */ }
  const a = document.createElement('a');
  a.href = URL.createObjectURL(new Blob([text ?? jrecs.map(r => JSON.stringify(r)).join('\n') + '\n'], { type: 'application/jsonl' }));
  a.download = `world-journal-${Date.now()}.jsonl`;
  a.click();
  URL.revokeObjectURL(a.href);
};
function journalRow(row) {
  if (!row) return;
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
  if (o.card) showCard();                            // "what can I ask?": the card shown, and the question said (the agent's card line)
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
// the world card (the map's `card`: what this world is, its room and things by kind, what you can ask it and what it
// cannot do; web/README "The schema"): the WORLD CARD dock, its asks as chips that say them; a map without one
// (an older recording) says so
const spokenId = id => String(id).replace(/([a-z])(\d+)$/, '$1 $2');
function kindRows(rows, opens) {
  return `<div class="wc-kinds">${(rows || []).map(r => `<details class="wc-kind" title="${esc((r.ids || []).map(spokenId).join(', '))}">
    <summary><b>${esc(r.type)}</b> <span class="wc-n">× ${esc(r.n)}</span>${opens && r.openable ? '<span class="wc-opens">opens</span>' : ''}</summary>
    <div class="wc-ids">${esc((r.ids || []).map(spokenId).join(', '))}</div></details>`).join('')}</div>`;
}
function worldCard() {
  const c = world.map.map?.card, box = $('#wcard');
  world.card = c || null;
  if (!c) { box.innerHTML = '<p class="empty">This world has no card (an older map or recording): ask for its task, or say "stop".</p>'; return; }
  box.innerHTML = `<p class="wc-title">${esc(c.title || 'this world')}</p>
    ${(c.about || []).map(a => `<p class="wc-about">${esc(a)}</p>`).join('')}
    ${c.asks?.length ? `<div class="wc-h">what you can ask</div><div id="wcasks">${c.asks.map((a, i) => `<div class="wc-ask"><button type="button" class="chip" data-ask="${i}">${esc(a.say)}</button><span class="what">${esc(a.what || '')}</span></div>`).join('')}</div>` : ''}
    ${c.room?.length ? `<div class="wc-h">the room</div>${kindRows(c.room, true)}` : ''}
    ${c.looked?.length ? `<div class="wc-h">looked into already</div><p class="wc-looked">${esc(c.looked.join(', '))}</p>` : ''}
    ${c.things?.length ? `<div class="wc-h">the things you can ask for</div>${kindRows(c.things, false)}` : ''}
    ${c.cannot?.length ? `<div class="wc-h">it cannot</div><ul class="wc-cannot">${c.cannot.map(x => `<li>${esc(x)}</li>`).join('')}</ul>` : ''}
    ${c.source ? `<p class="wc-src">${esc(c.source)}</p>` : ''}`;
  for (const b of box.querySelectorAll('[data-ask]')) b.onclick = () => answer({ say: c.asks[Number(b.dataset.ask)].say });
}
// ── the game: the picker in the top bar (live, when the runner loads games), the game under the map ──
const ROOMS = ['kitchen', 'living room', 'bedroom', 'bathroom'];
world.games = null;
async function gamePicker() {
  let g = null;
  try { const r = await fetch(new URL('world/games.json', world.base)); if (r.ok) g = await r.json(); } catch { /* no runner: no picker */ }
  if (!g?.games?.length) return;
  world.games = g;
  // grouped by room type, every game; with a house (rooms step 2) the house first, the rest behind "choose another"
  const sel = $('#game'), all = $('#gameall'), rooms = [...new Set([...ROOMS, ...g.games.map(x => x.room)])];
  const opt = x => Object.assign(document.createElement('option'),
    { value: x.id, textContent: x.label + (x.split === 'train' ? '' : ` (${x.split.replace('_', ' ')})`), selected: x.id === g.current });
  const groups = () => rooms.filter(r => g.games.some(x => x.room === r)).map(r => {
    const og = document.createElement('optgroup');
    og.label = r;
    og.append(...g.games.filter(x => x.room === r).map(opt));
    return og;
  });
  const go = id => { all.hidden = true; rec('load_game', { game: id }); send({ ev: 'load_game', game: id }); loading(id); };
  if (g.house?.length) {
    sel.replaceChildren(...g.house.map(id => g.games.find(x => x.id === id)).filter(Boolean).map(opt),
      Object.assign(document.createElement('option'), { value: '', textContent: 'choose another room…' }));
    all.replaceChildren(...groups());
    all.onchange = () => go(all.value);
  } else sel.replaceChildren(...groups());
  sel.hidden = false;
  sel.onchange = () => {
    if (sel.value) { go(sel.value); return; }
    sel.value = g.current; all.value = g.current; all.hidden = false; all.focus();
  };
  gameInfo();
}
function loading(game) {                             // another game on its way (null: refused, the current one stays)
  world.loading = game;
  const sel = $('#game');
  sel.disabled = !!game;
  if (!game) {                                       // refused, or arrived: the status line is the agent's again, not "moving"
    sel.value = world.games?.current ?? sel.value; $('#gameall').hidden = true;
    if (world.status) status(world.status);
    return;
  }
  const x = world.games?.games.find(g => g.id === game);
  $('#sstate').textContent = 'moving'; $('#stext').textContent = `the agent goes to ${x?.label ?? game}…`;
  $('#sopts').replaceChildren();
}
function gameInfo() {                                // under the map: the game (the picker's name for it) and its task
  const m = world.map?.map, el = $('#gameinfo');
  if (!el || !m) return;
  const x = world.games?.games.find(g => g.id === world.games.current);
  const task = m.task?.text || m.task?.goal;
  const room = !!m.task?.room;                      // a room (alf-tasks): no task of its own, the person gives them
  el.hidden = !(x || task || room);
  el.innerHTML = `<div class="gi-name">${esc(x ? x.label : m.card?.title || 'this game')}</div>
    ${task ? `<div class="gi-task">this game's task: ${esc(task)}</div>` : ''}
    ${room ? '<div class="gi-task">a room: tell the agent a task, then another</div>' : ''}
    ${x ? `<div class="gi-dim">${esc(x.id)}${room && x.episode ? ` · the room's game: ${esc(x.episode)}` : ''}</div>` : ''}
    ${m.intro ? `<div class="gi-intro">${esc(m.intro)}</div>` : ''}`;
}
function showCard() { docks.set('world', { shown: true, open: true }); $('#dock-world')?.scrollIntoView?.({ block: 'nearest' }); }
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
// the left pane's own size: the splitter, a dock hidden or shown, a window moved to another monitor
new ResizeObserver(() => fitMap()).observe($('#left'));
function status(f) {
  const was = world.status?.state;
  world.status = f;
  $('#status').dataset.state = f.state || '';
  $('#sstate').textContent = f.state || '';
  $('#stext').textContent = f.text || '';
  // the ask's answers are in the ask box; waiting offers the world card ("what can I ask?")
  chips($('#sopts'), f.state === 'asking' ? [] : [...(f.options || []), ...(f.state === 'waiting' && world.card ? [{ label: 'what can I ask?', card: true }] : [])]);
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
    const slots = Object.entries(o).filter(([k]) => k !== 'intent' && k !== 'domain')
      .map(([k, v]) => `${k.replace(/_/g, ' ')} ${spoken(v)}`);
    return slots.length ? `${verb}: ${slots.join(', ')}` : verb;
  } catch { return text; }
}
world.intentWords = t => intentWords(t);
world.frame = f => frame(f);                         // a test hook: one frame in, as the wire or a recording gives it
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
let say = 0, panel = null, send = () => {};
async function frame(f) {
  rec('frame', { ev: f.ev });
  if (f.ev === 'world/map') { world.mapUrl = new URL(f.url, world.base).href; await world.map.load(world.mapUrl); fitMap(); legend(); worldCard(); gameInfo(); drawHierarchy(); return; }   // the task row names this map's task
  if (f.ev === 'world/loading') { loading(f.game); return; }
  if (f.ev === 'world/room') { await gamePicker(); loading(null); gameInfo(); return; }   // the agent is there: no reload, the panes go on
  if (f.ev === 'load_game_ack') { if (f.error) { loading(null); panel.note(f.error); } return; }
  if (f.ev === 'world/delta') { world.map.delta(f); if (f.task) { chainTo(world.map.map.task); } return; }
  if (f.ev === 'world/hierarchy') { hierarchy(f); return; }
  if (f.ev === 'world/status') { status(f); return; }
  if (f.ev === 'world/ask') { ask(f); return; }
  if (f.ev === 'new_game_ack') { if (f.text) panel.note(f.text); return; }
  if (f.ev === 'page') return;                     // the hello's answer: this page owns no domain
  if (f.ev !== 'journal' || !f.rec) return;
  const r = f.rec;
  jrecs.push(r);
  if (r.kind === 'dlg-wake' && r.what === 'person' && world.replay) panel.core.row({ who: 'person', text: r.person, channel: 'main' });
  if (r.kind === 'dlg-say' && world.replay) {
    const [line, ...answers] = asked(r.text);
    panel.core.frame({ ev: 'narration', id: `s${++say}`, sentence: line, kind: r.what === 'ask' ? 'v3-ask' : 'v3-line' });
    if (r.what === 'ask' && answers.length && !world.asked) ask({ question: line, options: answers.map(a => ({ label: a, say: a })) });
  }
  const out = journal.add(r);
  journalRow(out.chat);
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
  $('#ctrl').hidden = true;                          // play / step are the replay's: live has nothing to step
  await frame({ ev: 'world/map', url: q.get('map') || 'fixtures/alfworld_tomato_microwave_13.json' });
  // the socket back after another game's restart: the page starts again on it (the map, the card, the docks' contents)
  const backend = await connect(url, { timeoutMs: 5000, reconnect: 2000, onReopen: b => world.loading ? location.reload() : hello(b) });
  if (!backend) { $('#conn').textContent = `no agent at ${url}`; return null; }
  send = m => { if (backend.isOpen) backend.send(m); };
  $('#conn').textContent = 'live';
  await gamePicker();
  return backend;          // the hello once the panel listens (start)
}

// ── start ──
world.map = new WorldMap($('#map'), {
  base: { sheet: 'tiles/nethack/glyphs.png', glyphs: 'tiles/nethack/glyphs.json', index: ['tiles/index.json'] },
  onTask: () => rec('task', {}),
});
const agentUrl = q.get('agent') || (q.get('live') ? `${location.protocol === 'https:' ? 'wss' : 'ws'}://${location.host}/ws` : null);
const hello = b => b.send({ ev: 'hello', since: 1e15 });
const backend = agentUrl ? await live(agentUrl) : null;
// the shell's docks (the consoles' look): tools the strip shows and hides, each open while shown (fold: false — "go to
// Talk" lands at once; the DIALOG tool's own FLOOR / STATE / EVENTS sections fold inside it)
const docks = world.docks = MetisShell.docks({
  // v3: the DIALOG drawer (fsttm-web's panel, its own part: the floor, barge-in, attention, the numbers), hidden until asked for
  // v4: the cards are tools, not folded (the world card and the journal shown by default as before; the dialog hidden)
  names: ['talk', 'hierarchy', 'world', 'journal', 'dialog'], key: 'worldpage.docks.v4', fold: false,
  defaults: { talk: { shown: true, open: true }, hierarchy: { shown: true, open: true }, world: { shown: true, open: true }, journal: { shown: true, open: true },
    dialog: { shown: false, open: true } },
  onChange: st => panel?.showDialog(!!st.dialog?.shown),              // hidden: the panel draws nothing there
});
docks.apply();
MetisShell.splitter();
panel = world.panel = new Panel($('#talkpanel'), {
  backend: backend || { turn: async function* () { yield 'This is a replay: nobody is listening.'; }, onFrame: null },
  table: await (await fetch('vendor/fsttm.json')).json(), title: '', voice: q.get('voice') === '1',
  // fsttm-web's one panel (dialog-panel s-277c33e3): the chat here (the reply line, the log, the text line); its own
  // part — the floor, barge-in, attention, the floor / state / events cards — in the DIALOG drawer (dialogIn), the
  // mic in the band's voice widget; the world's own frames kept as events only for world/* (the journal frames have
  // their dock); ?host: the backchannel to the host on the socket; ?fw_host: the fsttm-chat tool's
  sections: ['floor', 'state', 'events'], dialogIn: $('#dialogpart'), micButton: false,
  frames: f => String(f.ev ?? '').startsWith('world/'), host: q.has('host') || null,
  onFrame: f => frame(f), onRow: r => rowLook(r), onState: s => floorLook(s),
});
floorLook(panel.core.state());
panel.showDialog(!!docks.state.dialog?.shown);
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
attachSelection(narrator, document); attachKey(narrator, document, { key: 'F8' });
// the band's voice card (fsttm-web switch.js): [● mic ⟦switch⟧ narrator], the narrator always on
$('#voice').replaceWith(Object.assign(voiceWidget(panel, { narrator, key: 'F8' }).el, { id: 'voice' }));
$('#hlist').addEventListener('click', e => { const li = e.target.closest('li'); if (li?.dataset.domain === 'task') world.map.showTask('@agent'); });
$('#hlist').addEventListener('keydown', e => { const li = e.target.closest('li'); if (e.key === 'Enter' && li?.dataset.domain === 'task') world.map.showTask('@agent'); });
if (!agentUrl) await replay(q.get('replay') || 'fixtures/alfworld_tomato_microwave_13.run.jsonl');
document.body.dataset.ready = '1';
