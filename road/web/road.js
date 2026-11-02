// road.js — the road where the other worlds have map.js: the 3D client's frame (client.html), the dashboard under it (dash.js), and what the docks run and cars show. It keeps the
// map's face for the page (load, delta, showTask, view, map); the road has no cells to draw. The controls go to the responder's host as world lines (road_host.py).
import { Dash } from './dash.js';

const $ = s => document.querySelector(s);
const rows = (el, pairs) => el.replaceChildren(...pairs.flatMap(([k, v]) => {
  const dt = document.createElement('dt'), dd = document.createElement('dd');
  dt.textContent = k; dd.textContent = v;
  return [dt, dd];
}));

export class RoadMap {
  constructor(box, { line }) {
    Object.assign(this, { box, line, map: null, frame: null, ready: false, paused: false, following: false, ego: 'ego', picked: null });
    this.dash = new Dash($('#dash'));
    this.view = { fit() {}, keep() {}, center() {} };
    this.marks = { n: 0, open: false };
    $('#mark').onclick = () => this.markEdge();
    $('#run').onclick = () => { if (this.marks.open) this.markEdge(); line(`run:${$('#scenario').value}:${Math.max(1, Number($('#seed').value) || 1)}`); this.hold(false, false); };
    $('#hold').onclick = () => this.hold(!this.paused);
    $('#speed').onchange = e => line(`speed:${e.target.value}`);
    $('#follow').onclick = () => { this.follows(!this.following); this.post(this.following ? { follow: this.ego } : { unfollow: true }); };
    $('#center').onclick = () => this.post({ center: this.ego });
    $('#follow-picked').onclick = () => { this.follows(true); this.post({ unfollow: true }); this.post({ follow: this.picked }); };
    $('#center-picked').onclick = () => this.post({ center: this.picked });
    for (const b of document.querySelectorAll('[data-drive]')) b.onclick = () => line(`drive:${b.dataset.drive}`);
    const n = () => Math.max(1, Math.min(50, Number($('#t-n').value) || 1));
    $('#t-add').onclick = () => line(`traffic:add:${$('#t-kind').value}:${n()}`);
    $('#t-ahead').onclick = () => line(`traffic:ahead:${$('#t-kind').value}:${n()}`);
    $('#t-clear').onclick = () => line('traffic:clear');
    $('#t-scale').oninput = e => { $('#t-scale-v').textContent = e.target.value; };
    $('#t-scale').onchange = e => line(`traffic:scale:${e.target.value}`);
    $('#t-stop').onclick = () => line(`car:stop:${this.picked}`);
    $('#t-go').onclick = () => line(`car:go:${this.picked}`);
    $('#t-remove').onclick = () => line(`car:remove:${this.picked}`);
    $('#t-close').onclick = () => line(`lane:close:${this.lane}`);
    $('#t-open').onclick = () => line('lane:open');
    $('#t-lights-off').onclick = () => line('lights:off');
    $('#t-lights-on').onclick = () => line('lights:on');
    addEventListener('message', e => {
      if (e.origin !== location.origin) return;
      if ('clicked' in e.data) { this.picked = e.data.clicked; this.lane = e.data.lane; this.selection(); }
      if (e.data.followed === false) this.follows(false);
      if (e.data.client === 'pause') this.hold(true);
      if (e.data.client === 'resume') this.hold(false);
    });
  }

  // the map's face
  async load(url) { this.map = await (await fetch(url)).json(); return this.map; }
  delta() {}
  showTask() {}
  entries() { return []; }

  selection() {
    const car = this.picked, other = car && car !== this.ego;
    $('#t-car').textContent = car ? (other ? car : 'the ego: the stack drives it') : 'click a car in the view';
    for (const b of ['#t-stop', '#t-go', '#t-remove']) $(b).disabled = !other;
    $('#t-lane').textContent = this.lane || 'click a lane in the view';
    $('#t-close').disabled = !this.lane;
  }

  post(o) { if (this.ready) this.frame.contentWindow.postMessage(o, location.origin); }
  follows(on) { this.following = on; $('#follow').setAttribute('aria-pressed', String(on)); }
  markEdge() {                        // the host numbers them (world/mark): this is the next edge as the page last heard it
    const m = this.marks, n = m.open ? m.n : m.n + 1;
    this.line(`mark:${n}:${m.open ? 'stop' : 'start'}:${this.tick ?? ''}`);
    this.mark({ n, open: !m.open });
  }

  mark({ n, open }) {
    this.marks = { n, open };
    const b = $('#mark');
    b.textContent = open ? `end event ${n}` : `mark event ${n + 1}`;
    b.classList.toggle('open', open);
  }

  hold(on, tell = true) {
    this.paused = on;
    $('#hold').textContent = on ? 'play' : 'pause';
    if (tell) this.line(on ? 'pause' : 'play');
  }

  net(f) {
    this.dash.net(f);
    if (f.scenarios && $('#scenario').options.length !== f.scenarios.length) $('#scenario').replaceChildren(...f.scenarios.map(s => Object.assign(document.createElement('option'), { textContent: s })));
    if (document.activeElement !== $('#scenario') && document.activeElement !== $('#seed')) { $('#scenario').value = f.scenario; $('#seed').value = f.seed; }   // what runs, also when a page opens on it
    const key = f.lanes.map(l => l.id).join();          // the client reads its road once: another road, another frame
    if (this.frame && key === this.netKey) return;
    this.netKey = key; this.ready = false;
    this.frame = Object.assign(document.createElement('iframe'), { id: 'view', src: 'client.html' });
    this.frame.addEventListener('load', () => { this.ready = true; this.post({ net: f.net }); if (this.following) this.post({ follow: this.ego }); });
    this.box.replaceChildren(this.frame);
  }

  summary(f) { this.dash.summary(f); }

  scene(f) {
    this.tick = f.tick;
    this.ego = f.ego;
    this.post({ scene: f });
    this.dash.scene(f);
    const me = f.movers.find(m => m.id === f.ego);
    rows($('#run-info'), [['time', `${f.t.toFixed(1)} s`], ['tick', f.tick], ['movers', f.movers.length], ['the sensor sees', f.seen ?? '-'], ['tracks', f.tracks ?? '-'],
      ['restricted ticks', f.restricted], ['collisions', f.collisions], ['arrived', f.arrived ? 'yes' : 'no']]);
    rows($('#ego'), [['lane', me?.lane ?? '-'], ['s', me ? `${me.s.toFixed(1)} m` : '-'], ['speed', me ? `${me.speed.toFixed(1)} m/s` : '-'], ['applied', f.a == null ? '-' : `${f.a} m/s²`],
      ['command', (f.cmd || []).filter(x => x != null).join(' ') || '-'], ['response, long', f.fold.resp_lon], ['response, lat', f.fold.resp_lat]]);
    const roles = Object.entries(f.roles);
    rows($('#roles'), roles.length ? roles : [['nobody', '']]);
    const m = this.picked && f.movers.find(o => o.id === this.picked);
    $('#picked-tools').hidden = !m;
    if (!m) { rows($('#picked'), [[this.picked ? 'it has left the road' : 'click a car in the view', '']]); return; }
    const role = roles.find(([, id]) => id === m.id);
    rows($('#picked'), [['id', m.id], ['type', m.type], ['lane', m.lane], ['s', `${m.s.toFixed(1)} m`], ['speed', `${m.speed.toFixed(1)} m/s`], ['role', m.id === f.ego ? 'the ego' : role ? role[0] : 'none']]);
  }
}
