// world.js — the road's page (road-agent s-357becc7 step 1): the agent's wire to the 3D client's frame (client.html) and the run's numbers beside it. The
// controls go to the responder's host as world lines (road_host.py): run:SCENARIO:SEED then a new game, play, pause, speed:X.
const $ = s => document.querySelector(s);
const rows = (el, pairs) => { el.replaceChildren(...pairs.flatMap(([k, v]) => { const dt = document.createElement('dt'), dd = document.createElement('dd'); dt.textContent = k; dd.textContent = v; return [dt, dd]; })); };
let sock = null, view = null, viewReady = false, paused = false, following = false, ego = 'ego', queued = null;
const send = o => { if (sock && sock.readyState === WebSocket.OPEN) sock.send(JSON.stringify(o)); };
const line = l => send({ ev: 'world', domain: 'responder', atoms: [l] });
const post = o => { if (view && viewReady) view.contentWindow.postMessage(o, location.origin); };

function openView(net) {
  view = document.createElement('iframe');
  view.id = 'view';
  view.src = 'client.html';
  view.addEventListener('load', () => { viewReady = true; post({ net }); });
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
  const me = f.movers.find(m => m.id === f.ego);
  rows($('#run-info'), [['time', `${f.t.toFixed(1)} s`], ['tick', f.tick], ['movers', f.movers.length], ['the sensor sees', f.seen ?? '-'], ['tracks', f.tracks ?? '-'],
    ['restricted ticks', f.restricted], ['collisions', f.collisions], ['arrived', f.arrived ? 'yes' : 'no']]);
  rows($('#ego'), [['lane', me?.lane ?? '-'], ['s', me ? `${me.s.toFixed(1)} m` : '-'], ['speed', me ? `${me.speed.toFixed(1)} m/s` : '-'], ['applied', f.a == null ? '-' : `${f.a} m/s²`],
    ['command', (f.cmd || []).filter(x => x != null).join(' ') || '-'], ['response, long', f.fold.resp_lon], ['response, lat', f.fold.resp_lat]]);
  const known = Object.entries(f.roles);
  rows($('#roles'), known.length ? known.map(([r, id]) => [r, id]) : [['nobody', '']]);
}
function frame(f) {
  if (f.ev === 'world/net') { if (!view) openView(f.net); else post({ net: f.net }); return; }
  if (f.ev === 'world/scene') scene(f);
}
function connect() {
  sock = new WebSocket(`${location.protocol === 'https:' ? 'wss' : 'ws'}://${location.host}/ws`);
  sock.onopen = () => { $('#conn').textContent = 'connected'; send({ ev: 'hello', since: Number.MAX_SAFE_INTEGER }); line('watching'); };
  sock.onclose = () => { $('#conn').textContent = 'disconnected'; setTimeout(connect, 2000); };
  sock.onmessage = e => frame(JSON.parse(e.data));
}
$('#run').onclick = () => { line(`run:${$('#scenario').value}:${Math.max(1, Number($('#seed').value) || 1)}`); send({ ev: 'new_game' }); setPaused(false, false); };
$('#play').onclick = () => setPaused(!paused);
$('#speed').onchange = e => line(`speed:${e.target.value}`);
$('#follow').onclick = e => { following = !following; e.target.setAttribute('aria-pressed', following); post(following ? { follow: ego } : { unfollow: true }); };
setInterval(() => line('watching'), 2000);                 // the scene comes every step while a page says so, else every second
addEventListener('message', e => {
  if (e.origin !== location.origin) return;
  if (e.data.client === 'pause') setPaused(true);
  if (e.data.client === 'resume') setPaused(false);
  if (e.data.client === 'delay' && e.data.ms > 0) line(`speed:${Math.min(4, 100 / e.data.ms)}`);
});
connect();
