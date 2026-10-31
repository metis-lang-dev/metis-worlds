// world.js — the road's page (road-agent s-357becc7 step 1): the agent's wire to the 3D client's frame (client.html) and the run's numbers beside it. The
// controls go to the responder's host as world lines (road_host.py): run:SCENARIO:SEED then a new game, play, pause, speed:X.
import { Dash } from './dash.js';

const $ = s => document.querySelector(s);
const dash = new Dash($('#dash'));
const rows = (el, pairs) => { el.replaceChildren(...pairs.flatMap(([k, v]) => { const dt = document.createElement('dt'), dd = document.createElement('dd'); dt.textContent = k; dd.textContent = v; return [dt, dd]; })); };
let picked = null, lastCmd = null, said = 0, sock = null, view = null, viewReady = false, paused = false, following = false, ego = 'ego', queued = null;
const send = o => { if (sock && sock.readyState === WebSocket.OPEN) sock.send(JSON.stringify(o)); };
const line = l => send({ ev: 'world', domain: 'responder', atoms: [l] });
const post = o => { if (view && viewReady) view.contentWindow.postMessage(o, location.origin); };

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
  rows($('#roles'), known.length ? known.map(([r, id]) => [r, id]) : [['nobody', '']]);
}
function talk(text, who) {
  const row = document.createElement('div');
  row.textContent = text;
  if (who) row.className = who;
  const log = $('#log');
  log.append(row);
  log.scrollTop = log.scrollHeight;
}
// the journal's rows the person can read: what each member fired that is a command or the task's, not the wire's every beat
const COMMANDS = /^(brake|change|accel|keep|yield|drive_away|stop_lat|pace|lane|pass|follow|resume|around)/;
function journal(rec) {
  if (rec.kind !== 'dlg-trace' || !['responder', 'planner', 'task'].includes(rec.domain)) return;
  for (const row of rec.fired || []) {
    if (row.kind !== 'clause' || !COMMANDS.test(row.event)) continue;
    if (row.event === lastCmd) continue;           // a command held tick after tick is one row
    lastCmd = row.event;
    const el = document.createElement('div');
    el.textContent = `${rec.domain}: ${row.line || row.event}`;
    const box = $('#journal');
    box.prepend(el);
    while (box.children.length > 40) box.lastChild.remove();
  }
}
async function card() {
  try {
    const c = (await (await fetch('world/map.json')).json()).card;
    $('#card').innerHTML = `<p><b>${c.title}</b></p>${c.about.map(a => `<p>${a}</p>`).join('')}<ul>${c.asks.map(a => `<li><b>${a.say}</b>: ${a.what}</li>`).join('')}</ul><p>It cannot ${c.cannot.join('; ')}.</p>`;
  } catch { /* the card is no reason to stop */ }
}
// the car clicked in the view: the scene's numbers for it, and its role as the ego believes
function showPicked(f) {
  const m = picked && f.movers.find(o => o.id === picked);
  $('#picked-tools').hidden = !m;
  if (!m) { rows($('#picked'), [[picked ? 'gone' : 'click a car', '']]); return; }
  const role = Object.entries(f.roles).find(([, id]) => id === m.id);
  rows($('#picked'), [['id', m.id], ['type', m.type], ['lane', m.lane], ['s', `${m.s.toFixed(1)} m`], ['speed', `${m.speed.toFixed(1)} m/s`], ['role', m.id === f.ego ? 'the ego' : role ? role[0] : 'none']]);
}
function frame(f) {
  if (f.ev === 'world/message') { talk(f.text); return; }
  if (f.ev === 'intent') { talk(f.voice || 'I have asked the planner.'); return; }
  if (f.ev === 'error') { talk(`I could not take that: ${f.error}`); return; }
  if (f.ev === 'journal' && f.rec) { journal(f.rec); return; }
  if (f.ev === 'world/summary') { dash.summary(f); return; }
  if (f.ev === 'world/net') { dash.net(f); if (!view) openView(f.net); else post({ net: f.net }); return; }
  if (f.ev === 'world/scene') scene(f);
}
function connect() {
  sock = new WebSocket(`${location.protocol === 'https:' ? 'wss' : 'ws'}://${location.host}/ws`);
  sock.onopen = () => { $('#conn').textContent = 'connected'; send({ ev: 'hello', since: Number.MAX_SAFE_INTEGER }); line('watching'); };
  sock.onclose = () => { $('#conn').textContent = 'disconnected'; setTimeout(connect, 2000); };
  sock.onmessage = e => frame(JSON.parse(e.data));
}
$('#run').onclick = () => { line(`run:${$('#scenario').value}:${Math.max(1, Number($('#seed').value) || 1)}`); setPaused(false, false); };
$('#play').onclick = () => setPaused(!paused);
$('#speed').onchange = e => line(`speed:${e.target.value}`);
$('#follow').onclick = e => { following = !following; e.target.setAttribute('aria-pressed', following); post(following ? { follow: ego } : { unfollow: true }); };
$('#center').onclick = () => post({ center: ego });
$('#follow-picked').onclick = () => { if (picked) { following = true; $('#follow').setAttribute('aria-pressed', true); post({ unfollow: true }); post({ follow: picked }); } };
$('#center-picked').onclick = () => { if (picked) post({ center: picked }); };
setInterval(() => line('watching'), 2000);                 // the scene comes every step while a page says so, else every second
addEventListener('message', e => {
  if (e.origin !== location.origin) return;
  if ('clicked' in e.data) picked = e.data.clicked;
  if (e.data.followed === false) { following = false; $('#follow').setAttribute('aria-pressed', false); }
  if (e.data.client === 'pause') setPaused(true);
  if (e.data.client === 'resume') setPaused(false);
  if (e.data.client === 'delay' && e.data.ms > 0) line(`speed:${Math.min(4, 100 / e.data.ms)}`);
});
$('#say').addEventListener('keydown', e => {
  const text = e.target.value.trim();
  if (e.key !== 'Enter' || !text) return;
  talk(text, 'me');
  send({ ev: 'say_text', text, id: `p${++said}` });
  e.target.value = '';
});
card();
connect();
