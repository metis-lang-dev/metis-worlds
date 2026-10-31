// dash.js — the run's dashboard under the 3D view (road-agent s-357becc7 step 2): four small charts on one time axis, each its own scale, from the world/scene
// frames, drawn twice a second on plain canvases (no chart library: minimal overhead). The run's numbers above them; the summary when it arrives.
const INK = { text: '#d8dde3', mute: '#8a939e', grid: '#2c323a' };
const CMD = { accel: '#3987e5', brake: '#d95926', keep: '#199e70', change: '#9085e9' };     // validated for the dark surface, in that order
const OTHER = '#8a939e';
const STRIP_ROWS = { restricted: '#c98500', violation: '#e66767', collision: '#e66767' };
const DRAW_MS = 500;

export class Dash {
  constructor(el) {
    this.el = el;
    el.innerHTML = `<div class="stats"></div><div class="charts">
      ${figure('speed', 'Speed, m/s')}${figure('accel', 'Acceleration applied, m/s²')}
      ${figure('cmd', `Command ${Object.entries(CMD).map(([k, c]) => `<span><i style="background:${c}"></i>${k}</span>`).join('')}`)}
      ${figure('events', `Shield and safety <span><i style="background:${STRIP_ROWS.restricted}"></i>restricted</span><span><i style="background:${STRIP_ROWS.violation}"></i>violation or collision</span>`)}
    </div><div id="tip"></div>`;
    this.stats = el.querySelector('.stats');
    this.tip = el.querySelector('#tip');
    this.canvases = [...el.querySelectorAll('canvas')];
    this.reset();
    this.canvases.forEach(c => {
      c.addEventListener('mousemove', e => this.hover(e, c));
      c.addEventListener('mouseleave', () => { this.at = null; this.tip.style.display = 'none'; this.draw(); });
    });
    setInterval(() => this.dirty && this.draw(), DRAW_MS);
  }

  reset() { this.rows = []; this.limit = null; this.last = null; this.sum = null; this.at = null; this.dirty = true; }

  net(f) { this.limit = Math.max(...f.lanes.map(l => l.speed)); }

  scene(f) {
    if (this.last && f.tick < this.last.tick) { const limit = this.limit; this.reset(); this.limit = limit; }
    const me = f.movers.find(m => m.id === f.ego);
    const was = this.last || { restricted: 0, violations: 0, collisions: 0 };
    if (me) {
      this.rows.push({ t: f.t, v: me.speed, a: f.a, cmd: f.cmd && f.cmd[0], restricted: f.restricted > was.restricted, bad: f.violations > was.violations || f.collisions > was.collisions });
    }
    this.last = f;
    this.dirty = true;
  }

  summary(f) { this.sum = f; this.dirty = true; }

  draw() {
    this.dirty = false;
    const f = this.last, r = this.rows;
    if (f) {
      const pairs = [['time', `${f.t.toFixed(1)} s`], ['restricted', f.restricted], ['optimistic', f.optimistic], ['violations', f.violations], ['collisions', f.collisions], ['tick', f.ms == null ? '-' : `${f.ms} ms`]];
      if (this.sum) pairs.push(['the run', `${this.sum.arrived ? 'arrived' : 'did not arrive'}, ${this.sum.ticks} ticks`]);
      this.stats.innerHTML = pairs.map(([k, v]) => `<span>${k}<b>${v}</b></span>`).join('');
    }
    const span = Math.max(10, r.length ? r[r.length - 1].t : 10);
    for (const c of this.canvases) {
      const g = fit(c), w = c.clientWidth, h = c.clientHeight;
      g.clearRect(0, 0, w, h);
      const x = t => LEFT + (w - LEFT - 4) * t / span;
      if (c.dataset.k === 'speed') line(g, r, 'v', x, w, h, 0, Math.max(this.limit || 0, ...r.map(o => o.v), 1), this.limit, 'limit');
      if (c.dataset.k === 'accel') { const m = Math.max(1, ...r.map(o => Math.abs(o.a || 0))); line(g, r, 'a', x, w, h, -m, m, 0, ''); }
      if (c.dataset.k === 'cmd') strip(g, r, x, w, h, o => (o.cmd ? CMD[o.cmd] || OTHER : null));
      if (c.dataset.k === 'events') strip(g, r, x, w, h, o => (o.bad ? STRIP_ROWS.violation : o.restricted ? STRIP_ROWS.restricted : null));
      axis(g, span, x, h);
      if (this.at != null) { g.strokeStyle = INK.mute; g.beginPath(); g.moveTo(x(this.at) + 0.5, 0); g.lineTo(x(this.at) + 0.5, h - BOTTOM); g.stroke(); }
    }
  }

  hover(e, c) {
    if (!this.rows.length) return;
    const span = Math.max(10, this.rows[this.rows.length - 1].t);
    const t = (e.offsetX - LEFT) / (c.clientWidth - LEFT - 4) * span;
    const o = this.rows.reduce((a, b) => (Math.abs(b.t - t) < Math.abs(a.t - t) ? b : a));
    this.at = o.t;
    const box = this.el.getBoundingClientRect(), at = c.getBoundingClientRect();
    this.tip.textContent = `t ${o.t.toFixed(1)} s\nspeed ${o.v.toFixed(1)} m/s\napplied ${o.a == null ? '-' : o.a} m/s²\ncommand ${o.cmd || '-'}${o.restricted ? '\nrestricted' : ''}${o.bad ? '\nviolation or collision' : ''}`;
    this.tip.style.display = 'block';
    this.tip.style.left = `${Math.min(at.left - box.left + e.offsetX + 10, box.width - 130)}px`;
    this.tip.style.top = `${at.top - box.top + 2}px`;
    this.draw();
  }
}

const LEFT = 26, BOTTOM = 13;
const figure = (k, title) => `<figure><figcaption>${title}</figcaption><canvas data-k="${k}"></canvas></figure>`;

function fit(c) {
  const w = c.clientWidth, h = c.clientHeight;
  if (c.width !== w || c.height !== h) { c.width = w; c.height = h; }
  const g = c.getContext('2d');
  g.font = '10px system-ui, sans-serif';
  return g;
}

function line(g, rows, key, x, w, h, lo, hi, ref, label) {
  const y = v => 2 + (h - BOTTOM - 4) * (1 - (v - lo) / (hi - lo));
  g.fillStyle = INK.mute;
  g.textAlign = 'right';
  g.fillText(String(Math.round(hi)), LEFT - 4, 10);
  g.fillText(String(Math.round(lo)), LEFT - 4, h - BOTTOM);
  if (ref != null) {
    g.strokeStyle = INK.grid;
    g.beginPath(); g.moveTo(LEFT, y(ref)); g.lineTo(w - 4, y(ref)); g.stroke();
    g.textAlign = 'left';
    if (label) g.fillText(label, LEFT + 2, y(ref) + 10);
  }
  g.strokeStyle = CMD.accel;
  g.lineWidth = 2;
  g.lineJoin = 'round';
  g.beginPath();
  let on = false;
  for (const o of rows) {
    if (o[key] == null) continue;
    if (on) g.lineTo(x(o.t), y(o[key])); else g.moveTo(x(o.t), y(o[key]));
    on = true;
  }
  g.stroke();
  g.lineWidth = 1;
}

function strip(g, rows, x, w, h, color) {
  const top = 4, height = h - BOTTOM - 8;
  for (let i = 0; i < rows.length; i++) {
    const c = color(rows[i]);
    if (!c) continue;
    const a = x(rows[i].t), b = i + 1 < rows.length ? x(rows[i + 1].t) : a + 1;
    g.fillStyle = c;
    g.fillRect(a, top, Math.max(1, b - a), height);
  }
}

function axis(g, span, x, h) {
  g.fillStyle = INK.mute;
  g.strokeStyle = INK.grid;
  g.beginPath(); g.moveTo(LEFT, h - BOTTOM + 0.5); g.lineTo(x(span), h - BOTTOM + 0.5); g.stroke();
  const step = [10, 20, 50, 100, 200, 500].find(s => span / s <= 5) || 1000;
  g.textAlign = 'center';
  for (let t = 0; t <= span; t += step) g.fillText(`${t}`, x(t), h - 2);
}
