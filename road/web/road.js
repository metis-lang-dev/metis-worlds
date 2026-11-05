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
    const crRun = () => {                                   // a CommonRoad scenario by its id (commonroad-world step 3): run:cr:ID:SEED
      const id = $('#t-cr').value.trim().replace(/^cr:/, '');
      if (!id) return;
      if (this.marks.open) this.markEdge();
      this.crWant = `cr:${id}`;
      $('#t-cr-msg').textContent = `starting cr:${id}: a first run converts it into the cache, a few seconds…`;
      line(`run:cr:${id}:${Math.max(1, Number($('#seed').value) || 1)}`);
      this.hold(false, false);
    };
    $('#t-cr-run').onclick = crRun;
    this.crRun = crRun;
    let q = null;                                           // the picker: the host filters the checkout's index (crfind:QUERY), a frame comes back
    $('#t-crq').oninput = e => { clearTimeout(q); q = setTimeout(() => line(`crfind:${e.target.value}`), 250); };
    $('#t-crq').onfocus = () => { if (!$('#t-crlist').children.length) line(`crfind:${$('#t-crq').value}`); };
    $('#t-cr').onkeydown = e => { if (e.key === 'Enter') crRun(); };
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
    const names = f.scenarios && f.scenario && !f.scenarios.includes(f.scenario) ? [...f.scenarios, f.scenario] : f.scenarios;   // a cr: run is not in the list: its own option
    if (names && $('#scenario').options.length !== names.length) $('#scenario').replaceChildren(...names.map(s => Object.assign(document.createElement('option'), { textContent: s })));
    if (f.scenario && f.scenario === this.crWant) { $('#t-cr-msg').textContent = `running ${f.scenario}`; this.crWant = null; }
    if (document.activeElement !== $('#scenario') && document.activeElement !== $('#seed')) { $('#scenario').value = f.scenario; $('#seed').value = f.seed; }   // what runs, also when a page opens on it
    const key = f.lanes.map(l => l.id).join() + JSON.stringify(f.goal || '');   // the client reads its road once: another road (or goal), another frame
    if (this.frame && key === this.netKey) return;
    this.netKey = key; this.ready = false;
    this.frame = Object.assign(document.createElement('iframe'), { id: 'view', src: 'client.html' });
    this.frame.addEventListener('load', () => { this.ready = true; this.post({ net: f.net, goal: f.goal }); if (this.following) this.post({ follow: this.ego }); });
    this.box.replaceChildren(this.frame);
  }

  summary(f) { this.dash.summary(f); }

  crList(f) {                                               // world/cr_list: the scenarios found, a row each; a click runs one
    if (f.error) { $('#t-crn').textContent = f.error; $('#t-crlist').replaceChildren(); return; }
    $('#t-crn').textContent = f.n > f.rows.length ? `${f.n} found, the first ${f.rows.length} shown` : `${f.n} found`;
    $('#t-crlist').replaceChildren(...f.rows.map(r => {
      const li = document.createElement('li'), b = document.createElement('button'), sm = document.createElement('small');
      b.type = 'button';
      b.textContent = r.id + (r.cached ? '' : ' ·');
      b.title = r.cached ? 'converted: starts at once' : 'not yet converted: the first run takes a few seconds';
      sm.textContent = ` ${r.set} · ${r.source}${r.tags?.length ? ' · ' + r.tags.join(', ') : ''}`;
      b.append(document.createElement('br'), sm);
      b.onclick = () => { $('#t-cr').value = r.id; this.crRun(); };
      li.append(b);
      return li;
    }));
  }

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
