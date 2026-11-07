// dash.js — the run's dashboard under the 3D view (road-agent s-357becc7 step 2): four small charts on one time axis, each its own scale, from the world/scene
// frames, drawn twice a second on plain canvases (no chart library: minimal overhead). The run's numbers above them; the summary when it arrives.
// loop-road-ui (the user, 2026-11-07): a rolling window of the last WINDOW ticks (the trace's ring); the run's EVENTS drawn as bands on every
// chart (a mark a window, a surprise a red line), the selected one bright; an ended event's edges dragged to move it (opts.onMove); a click in
// a band selects it (opts.onSelect); the column of small glyphs at the right acts on the selected event (opts.act: narrate, explain).
const css = v => getComputedStyle(document.documentElement).getPropertyValue(v).trim();   // the shell's tokens
const INK = { get mute() { return css('--dim'); }, get grid() { return css('--line'); } };
const CMD = { accel: '#3987e5', brake: '#d95926', keep: '#199e70', change: '#9085e9' };     // validated for the dark surface, in that order
const OTHER = '#8a939e';
const STRIP_ROWS = { restricted: '#c98500', violation: '#e66767', collision: '#e66767' };
const EV = { mark: 'rgba(80, 200, 220, 0.16)', markSel: 'rgba(80, 200, 220, 0.32)', edge: '#50c8dc', surprise: '#e66767' };
const DRAW_MS = 500;
export const WINDOW = 6000;                                    // ticks kept: 10 min at 0.1 s, the trace's ring (the user: enough for an event's analysis)
const GRAB = 5;                                                // px from an edge that takes it

export class Dash {
  constructor(el, opts = {}) {
    this.el = el;
    this.o = opts;
    el.innerHTML = `<div class="dmain"><div class="stats"></div><div class="charts">
      ${figure('speed', 'Speed, m/s')}${figure('accel', 'Acceleration applied, m/s²')}
      ${figure('cmd', `Command ${Object.entries(CMD).map(([k, c]) => `<span><i style="background:${c}"></i>${k}</span>`).join('')}`)}
      ${figure('events', `Shield and safety <span><i style="background:${STRIP_ROWS.restricted}"></i>restricted</span><span><i style="background:${STRIP_ROWS.violation}"></i>violation or collision</span><span><i style="background:${EV.edge}"></i>event</span>`)}
    </div></div><div class="dglyphs" role="toolbar" aria-orientation="vertical" aria-label="the selected event">
      <button type="button" class="glyph" data-act="narrate" title="narrate the selected event: the rules' own words (free)">¶</button>
      <button type="button" class="glyph" data-act="explain" title="explain the selected event: ask pi why the car acted so (paid)">?</button>
      <span class="dsel" title="the selected event"></span>
    </div><div id="tip"></div>`;
    this.stats = el.querySelector('.stats');
    this.tip = el.querySelector('#tip');
    this.sel = el.querySelector('.dsel');
    this.canvases = [...el.querySelectorAll('canvas')];
    for (const b of el.querySelectorAll('.dglyphs [data-act]')) b.onclick = () => this.o.act?.(b.dataset.act);
    this.reset();
    this.canvases.forEach(c => {
      c.addEventListener('mousemove', e => this.hover(e, c));
      c.addEventListener('mouseenter', () => { this.frozen = this.span(); });       // the axis holds still under the pointer: an edge stays where you aim
      c.addEventListener('mouseleave', () => { if (!this.drag) { this.frozen = null; this.at = null; this.tip.style.display = 'none'; this.draw(); } });
      c.addEventListener('mousedown', e => this.down(e, c));
    });
    addEventListener('mousemove', e => this.dragging(e));
    addEventListener('mouseup', () => this.up());
    setInterval(() => this.dirty && this.draw(), DRAW_MS);
  }

  reset() { this.rows = []; this.limit = null; this.last = null; this.sum = null; this.at = null; this.drag = null; this.frozen = null; this.dirty = true; }

  net(f) { this.limit = Math.max(...f.lanes.map(l => l.speed)); }

  scene(f) {
    if (this.last && f.tick < this.last.tick) { const limit = this.limit; this.reset(); this.limit = limit; }
    const me = f.movers.find(m => m.id === f.ego);
    const was = this.last || { restricted: 0, violations: 0, collisions: 0 };
    if (me) {
      this.rows.push({ t: f.t, k: f.k ?? f.tick, tick: f.tick, v: me.speed, a: f.a, cmd: f.cmd && f.cmd[0], restricted: f.restricted > was.restricted, bad: f.violations > was.violations || f.collisions > was.collisions });
      const from = this.rows[this.rows.length - 1].k - WINDOW;
      if (this.rows[0].k < from) this.rows.splice(0, this.rows.findIndex(o => o.k >= from));   // the rolling window
    }
    this.last = f;
    this.dirty = true;
  }

  summary(f) { this.sum = f; this.dirty = true; }
  changed() { this.dirty = true; }

  // the time axis: the window's k, read as the run's seconds
  span() {
    if (this.frozen) return this.frozen;
    const r = this.rows;
    if (!r.length) return { k0: 0, k1: 100, t0: 0 };
    const k0 = r[0].k, k1 = Math.max(k0 + 100, r[r.length - 1].k);
    return { k0, k1, t0: r[0].t - (r[0].k - k0) * 0.1 };
  }
  xOf(c) { const s = this.span(), w = c.clientWidth; return k => LEFT + (w - LEFT - 4) * (k - s.k0) / (s.k1 - s.k0); }
  kAt(c, px) { const s = this.span(); return s.k0 + (px - LEFT) / (c.clientWidth - LEFT - 4) * (s.k1 - s.k0); }
  rowAt(k) { return this.rows.length ? this.rows.reduce((a, b) => (Math.abs(b.k - k) < Math.abs(a.k - k) ? b : a)) : null; }

  events() {                                                    // the events with a window in this run's rows
    const r = this.rows;
    if (!r.length) return [];
    const lo = r[0].k, hi = r[r.length - 1].k;
    return (this.o.events?.() || []).filter(e => e.k0 != null && (e.k1 ?? hi) >= lo && e.k0 <= hi)
      .map(e => (this.drag && this.drag.n === e.n ? { ...e, k0: this.drag.k0, k1: this.drag.k1 } : e));
  }

  draw() {
    this.dirty = false;
    const f = this.last, r = this.rows;
    if (f) {
      const pairs = [['time', `${f.t.toFixed(1)} s`], ['restricted', f.restricted], ['optimistic', f.optimistic], ['violations', f.violations], ['unseen, the other\'s duty', f.unseen_other_duty], ['collisions', f.collisions], ['tick', f.ms == null ? '-' : `${f.ms} ms`]];
      if (f.cr) {                                       // a CommonRoad run's measures (cr_world): the goal by its region and its window apart
        const w = (f.cr.window_s || []).map(([a, b]) => a === b ? `${a} s` : `${a}–${b} s`).join(', ');
        pairs.push(['goal', f.cr.goal_t != null ? `reached at ${f.cr.goal_t} s` : f.cr.goal_position_t != null ? `region at ${f.cr.goal_position_t} s, out of its window` : 'not yet'],
          ['goal window', w || 'none'], ['contacts', f.cr.contacts], ['off the lanelets', `${f.cr.off_lanelet_m} m`]);
      }
      if (this.sum) pairs.push(['the run', `${this.sum.arrived ? 'arrived' : 'did not arrive'}, ${this.sum.ticks} ticks`]);
      if (this.sum?.cr) pairs.push(['CommonRoad', this.sum.cr.goal_reached ? 'goal reached in its window' : 'goal not reached in its window']);
      this.stats.innerHTML = pairs.map(([k, v]) => `<span>${k}<b>${v}</b></span>`).join('');
    }
    const s = this.span(), evs = this.events(), selN = this.o.selected?.();
    for (const c of this.canvases) {
      const g = fit(c), w = c.clientWidth, h = c.clientHeight;
      g.clearRect(0, 0, w, h);
      const x = this.xOf(c);
      bands(g, evs, x, h, selN, c.dataset.k === 'speed');
      if (c.dataset.k === 'speed') line(g, r, 'v', x, w, h, 0, Math.max(this.limit || 0, ...r.map(o => o.v), 1), this.limit, 'limit');
      if (c.dataset.k === 'accel') { const m = Math.max(1, ...r.map(o => Math.abs(o.a || 0))); line(g, r, 'a', x, w, h, -m, m, 0, ''); }
      if (c.dataset.k === 'cmd') strip(g, r, x, w, h, o => (o.cmd ? CMD[o.cmd] || OTHER : null));
      if (c.dataset.k === 'events') strip(g, r, x, w, h, o => (o.bad ? STRIP_ROWS.violation : o.restricted ? STRIP_ROWS.restricted : null));
      axis(g, s, x, h);
      if (this.at != null) { g.strokeStyle = INK.mute; g.beginPath(); g.moveTo(x(this.at) + 0.5, 0); g.lineTo(x(this.at) + 0.5, h - BOTTOM); g.stroke(); }
    }
    const e = selN != null && (this.o.events?.() || []).find(x => x.n === selN);
    this.sel.textContent = e ? `#${e.n}` : '';
    for (const b of this.el.querySelectorAll('.dglyphs .glyph')) b.disabled = !e || e.open;
  }

  // ── the pointer: an edge grabbed and moved, a band clicked ──
  hit(e, c) {
    const x = this.xOf(c);
    let best = null;
    for (const ev of this.events()) {
      if (ev.open) continue;
      for (const side of ['k0', 'k1']) {
        const d = Math.abs(x(ev[side]) - e.offsetX);
        if (d <= GRAB && (!best || d < best.d)) best = { ev, side, d };
      }
    }
    if (best) return best;
    const k = this.kAt(c, e.offsetX), inside = this.events().find(ev => ev.k0 <= k + 1 && k - 1 <= (ev.k1 ?? ev.k0));
    return inside ? { ev: inside, side: null } : null;
  }

  down(e, c) {
    const h = this.hit(e, c);
    if (!h) return;
    this.o.onSelect?.(h.ev.n);
    if (h.side) { this.drag = { n: h.ev.n, side: h.side, k0: h.ev.k0, k1: h.ev.k1, was: [h.ev.k0, h.ev.k1], c, x: e.clientX, moved: false }; e.preventDefault(); }
    this.draw();
  }

  dragging(e) {
    const d = this.drag;
    if (!d) return;
    if (!d.moved && Math.abs(e.clientX - d.x) < 3) return;      // a press is a selection; a move is a drag of 3 px or more
    d.moved = true;
    const box = d.c.getBoundingClientRect(), r = this.rowAt(this.kAt(d.c, e.clientX - box.left));
    if (!r) return;
    d[d.side] = r.k;
    this.dirty = true;
  }

  up() {
    const d = this.drag;
    if (!d) return;
    this.drag = null;
    if (!d.c.matches(':hover')) this.frozen = null;
    const [k0, k1] = [d.k0, d.k1].sort((a, b) => a - b), r0 = this.rowAt(k0), r1 = this.rowAt(k1);
    if (d.moved && (k0 !== d.was[0] || k1 !== d.was[1]))                      // the window changed: the host hears it, once
      this.o.onMove?.(d.n, k0, k1, r0 ? r0.t : null, r1 ? r1.t : null, r0 ? r0.tick : null, r1 ? r1.tick : null);
    this.draw();
  }

  hover(e, c) {
    if (!this.rows.length) return;
    const h = this.drag ? null : this.hit(e, c);
    c.style.cursor = this.drag || h?.side ? 'ew-resize' : h ? 'pointer' : 'default';
    const o = this.rowAt(this.kAt(c, e.offsetX));
    this.at = o.k;
    const box = this.el.getBoundingClientRect(), at = c.getBoundingClientRect();
    this.tip.textContent = `t ${o.t.toFixed(1)} s\nspeed ${o.v.toFixed(1)} m/s\napplied ${o.a == null ? '-' : o.a} m/s²\ncommand ${o.cmd || '-'}${o.restricted ? '\nrestricted' : ''}${o.bad ? '\nviolation or collision' : ''}${h ? `\nevent ${h.ev.n}${h.side ? ': drag to move this edge' : ''}` : ''}`;
    this.tip.style.display = 'block';
    this.tip.style.left = `${Math.min(at.left - box.left + e.offsetX + 10, box.width - 160)}px`;
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
  g.font = `10px ${css('--mono')}`;
  return g;
}

function bands(g, evs, x, h, selN, label) {
  for (const e of evs) {
    const a = x(e.k0), b = x(e.k1 ?? e.k0), sel = e.n === selN;
    if (e.kind !== 'mark') {                                   // a surprise: one line at its tick
      g.fillStyle = EV.surprise; g.fillRect(a - (sel ? 1.5 : 1), 0, sel ? 3 : 2, h - BOTTOM);
    } else {
      g.fillStyle = sel ? EV.markSel : EV.mark; g.fillRect(a, 0, Math.max(2, b - a), h - BOTTOM);
      if (!e.open) { g.fillStyle = EV.edge; g.fillRect(a - (sel ? 1 : 0.5), 0, sel ? 2 : 1, h - BOTTOM); g.fillRect(b - (sel ? 1 : 0.5), 0, sel ? 2 : 1, h - BOTTOM); }
    }
    if (label) { g.fillStyle = e.kind === 'mark' ? EV.edge : EV.surprise; g.textAlign = 'left'; g.fillText(`#${e.n}`, a + 3, 10); }
  }
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
    if (on) g.lineTo(x(o.k), y(o[key])); else g.moveTo(x(o.k), y(o[key]));
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
    const a = x(rows[i].k), b = i + 1 < rows.length ? x(rows[i + 1].k) : a + 1;
    g.fillStyle = c;
    g.fillRect(a, top, Math.max(1, b - a), height);
  }
}

function axis(g, s, x, h) {                                    // the window's k, labelled in the run's seconds
  g.fillStyle = INK.mute;
  g.strokeStyle = INK.grid;
  g.beginPath(); g.moveTo(LEFT, h - BOTTOM + 0.5); g.lineTo(x(s.k1), h - BOTTOM + 0.5); g.stroke();
  const secs = (s.k1 - s.k0) / 10, step = [10, 20, 50, 100, 200, 500].find(v => secs / v <= 5) || 1000;
  g.textAlign = 'center';
  const first = Math.ceil(s.t0 / step) * step;
  for (let t = first; t <= s.t0 + secs; t += step) g.fillText(`${t}`, x(s.k0 + (t - s.t0) * 10), h - 2);
}
