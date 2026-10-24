// map.js — the world map (alf-demo step 3a, alfworld/docs/DEMO.md §8): one grid renderer for
// every world, over one schema; the tileset is the only world-specific part.
//
//   import { WorldMap, toGrid } from './map.js';
//   const map = new WorldMap(el, { base: { sheet, glyphs, index: [url…] }, onTask, onAttend });
//   await map.load(url)              // the grid schema, or a semantic map (DEMO.md §3: places/things)
//   map.delta({ agent: {pos | at, yaw, holding}, entities: [{id, pos?, tile?, items?, closed?, unseen?, gone?}],
//               cells: [{pos, tile}], hot: [id…], cornered: id | null, task: {chain, results} })   // world/delta
//
// The grid: {cols, rows, cells: [[tile|null]], entities: [{id, name, pos: [x, y], tile, ch?, kind?,
// frame?, items?, hot?}], agent: {pos, yaw?, tile?, ch?}, task: {text, goal, chain?, results?},
// tileset: {index: [url…]}}. A tile is a GLYPH id (a number: the glyph sheet), a NAME (a string:
// the merged index, a name's trailing digits dropped: cabinet3 → cabinet), or {t, ch}. The index
// is the page's base (the editor's named icons) with the world's own entries merged over it, each
// URL resolved against the file that names it; an entry with no image draws its glyph character,
// and a name with no entry its `ch`, else its first letter: a tile never fails.
//
// Each entity and the agent is a focusable button named for its thing (ui_domain's JUMP labels
// them: entries()). Hover or focus shows it in the attention slot (its picture, its frame, what is
// in it); a click, Enter or Space opens the TASK CARD: the words the task was given in, the goal
// atom formalization made of them, the specialist chain so far, the result lines. Arrow keys move
// between the entities, nearest first in that direction; Escape closes the card.

const esc = s => String(s ?? '').replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' })[c]);
const json = async u => { const r = await fetch(u); if (!r.ok) throw new Error(`${u}: ${r.status}`); return r.json(); };
const nameOf = t => String(t).toLowerCase().replace(/[^a-z0-9]+/g, '_').replace(/^_|_$/g, '');

// a semantic map (places with metric positions, things at places) as the grid: x and z quantized to
// `cell` metres (the map's own `cell`, else 0.5), a place that lands on a taken cell moved to the nearest free one, things listed in
// their place (the ones the task names make it hot); the agent quantized the same way
export function toGrid(sem, { cell = sem.cell ?? 0.5, margin = 1 } = {}) {
  const ps = sem.places || [], xs = ps.map(p => p.pos[0]), zs = ps.map(p => p.pos[1]);
  const x0 = Math.min(...xs), z0 = Math.min(...zs);
  const q = ([x, z]) => [Math.round((x - x0) / cell) + margin, Math.round((z - z0) / cell) + margin];
  const cols = Math.round((Math.max(...xs) - x0) / cell) + 2 * margin + 1;
  const rows = Math.round((Math.max(...zs) - z0) / cell) + 2 * margin + 1;
  const n = Math.ceil(Math.sqrt(ps.length * 2.2));
  const C = Math.max(cols, n), R = Math.max(rows, n), taken = new Set();
  const free = ([x, y]) => {
    for (let d = 0; d < C + R; d++)
      for (let dy = -d; dy <= d; dy++) for (let dx = -d; dx <= d; dx++) {
        const p = [x + dx, y + dy];
        if (Math.max(Math.abs(dx), Math.abs(dy)) === d && p[0] >= 0 && p[1] >= 0 && p[0] < C && p[1] < R && !taken.has(p + '')) return p;
      }
    return [x, y];
  };
  const task = sem.task || {}, targets = new Set(task.targets || []), dests = new Set(task.dests || []);
  const entities = ps.map(p => {
    const pos = free(q(p.pos)); taken.add(pos + '');
    const items = p.unseen ? [] : (sem.things || []).filter(t => t.at === p.id);   // view mode: what is in it, once seen
    return { id: p.id, name: p.name || p.id, pos, tile: p.type || p.id, kind: 'place', frame: p.frame || null,
      items: items.map(t => t.name || t.id), closed: !!p.closed, unseen: !!p.unseen,
      hot: dests.has(p.id) || items.some(t => targets.has(t.id)) };
  });
  const a = sem.agent || {};
  return { cols: C, rows: R, cells: Array.from({ length: R }, () => Array(C).fill('floor')), entities,   // the room, all seen
    agent: { pos: a.pos ? q(a.pos) : [0, 0], yaw: a.yaw ?? null, ch: '@', name: 'the agent' },
    task: task, tileset: sem.tileset || { index: [] }, world: sem.world, scene: sem.scene, card: sem.card || null };   // the world card (web/README)
}

export class WorldMap {
  constructor(root, { base = {}, onTask = null, onAttend = null } = {}) {
    Object.assign(this, { root, base, onTask, onAttend });
    this.index = {}; this.glyphs = null; this.map = null; this.els = new Map();
    root.classList.add('wm');
    root.innerHTML = `<div class="wm-view"><div class="wm-grid" aria-hidden="true"></div>
      <div class="wm-layer" role="list" aria-label="on the map"></div></div>
      <aside class="wm-attn" aria-live="polite"><span class="wm-empty">point at something on the map</span></aside>
      <dialog class="wm-task" aria-label="the task"><div class="wm-card"></div>
      <form method="dialog"><button class="wm-close">close</button></form></dialog>`;
    [this.grid, this.layer] = root.querySelectorAll('.wm-grid, .wm-layer');
    this.attn = root.querySelector('.wm-attn'); this.card = root.querySelector('.wm-task');
    this.layer.addEventListener('click', e => { const b = e.target.closest('.wm-ent'); if (b) this.showTask(b.dataset.id); });
    this.layer.addEventListener('pointerover', e => { const b = e.target.closest('.wm-ent'); if (b) this.attend(b.dataset.id); });
    this.layer.addEventListener('focusin', e => { const b = e.target.closest('.wm-ent'); if (b) this.attend(b.dataset.id); });
    this.layer.addEventListener('keydown', e => this.key(e));
  }

  async tileset(ts, url) {
    const at = (u, b) => new URL(u, b).href;
    const sheet = ts.sheet ? at(ts.sheet, url) : this.base.sheet && at(this.base.sheet, location.href);
    const glyphs = ts.glyphs ? at(ts.glyphs, url) : this.base.glyphs && at(this.base.glyphs, location.href);
    this.sheet = sheet; this.glyphs = glyphs ? await json(glyphs) : null;
    this.index = {};
    const lists = [...(this.base.index || []).map(u => at(u, location.href)), ...(ts.index || []).map(u => at(u, url))];
    for (const u of lists) {                          // later wins: the world's entries over the base
      let idx;
      try { idx = await json(u); } catch (e) { console.warn(`map: no tile index at ${u} (its names draw as glyphs)`); continue; }
      for (const [k, v] of Object.entries(idx)) this.index[nameOf(k)] = { ...v, image: v.image ? at(v.image, u) : null };
    }
  }

  // a tile as HTML: the sheet's sprite, an index image, a glyph character, never nothing
  tile(t, ch) {
    if (t && typeof t === 'object') return this.tile(t.t, t.ch ?? ch);
    const g = this.glyphs;
    if (typeof t === 'number' && g && this.sheet && t >= 0 && t < g.glyph2tile.length) {
      const i = g.glyph2tile[t], s = g.size;
      return `<i class="wm-sp" data-tile="${t}" style="background-image:url('${this.sheet}');background-position:-${(i % g.cols) * s}px -${Math.floor(i / g.cols) * s}px"></i>`;
    }
    const k = t == null ? '' : nameOf(t), e = this.index[k] || this.index[k.replace(/_?\d+$/, '')];
    if (e?.image) return `<img class="wm-img" src="${esc(e.image)}" alt="" data-tile="${esc(k)}">`;
    const c = e?.glyph || ch || (k ? k[0] : '?');
    return `<b class="wm-ch ${esc(e?.color || '')}" data-tile="${esc(k)}">${esc(c)}</b>`;
  }

  async load(src, url = location.href) {
    if (typeof src === 'string') { url = new URL(src, location.href).href; src = await json(url); }
    const m = src.places ? toGrid(src) : src;
    await this.tileset(m.tileset || {}, url);
    this.map = m; this.frameBase = url;
    this.root.style.setProperty('--cols', m.cols); this.root.style.setProperty('--rows', m.rows);
    this.grid.innerHTML = m.cells.map((row, y) => row.map((c, x) =>
      `<span class="wm-cell${c == null ? ' wm-void' : ''}" style="--x:${x};--y:${y}">${c == null ? '' : this.tile(c)}</span>`).join('')).join('');
    this.layer.innerHTML = ''; this.els.clear();
    for (const e of m.entities) this.put(e);
    this.put({ ...m.agent, id: '@agent', name: m.agent.name || 'the agent', kind: 'agent', tile: m.agent.tile ?? null, ch: m.agent.ch || '@' });
    this.rove(this.els.get('@agent'));
    return m;
  }

  entity(id) { return id === '@agent' ? this.agentEnt() : this.map.entities.find(e => e.id === id); }
  agentEnt() { return { ...this.map.agent, id: '@agent', name: this.map.agent.name || 'the agent', kind: 'agent' }; }
  entries() { return [...this.layer.querySelectorAll('.wm-ent')]; }    // the focusable things, for the ui port's JUMP

  put(e) {
    let b = this.els.get(e.id);
    if (!b) {
      b = document.createElement('button');
      b.className = 'wm-ent'; b.type = 'button'; b.tabIndex = -1; b.dataset.id = e.id; b.setAttribute('role', 'listitem');
      this.layer.appendChild(b); this.els.set(e.id, b);
    }
    b.dataset.kind = e.kind || ''; b.dataset.name = e.name || e.id;
    b.setAttribute('aria-label', (e.name || e.id) + (e.unseen ? ' (not seen yet)' : e.items?.length ? ` (${e.items.length} in it)` : ''));
    b.classList.toggle('wm-unseen', !!e.unseen);           // view mode: the robot has not seen into it (dimmed, kept in place)
    b.classList.toggle('wm-hot', !!e.hot); b.classList.toggle('wm-agent', e.id === '@agent'); b.classList.toggle('wm-cornered', !!e.cornered);
    b.style.setProperty('--x', e.pos[0]); b.style.setProperty('--y', e.pos[1]);
    if (e.yaw != null) b.style.setProperty('--yaw', `${e.yaw}deg`);
    b.innerHTML = this.tile(e.tile, e.ch) + (e.items?.length ? `<sup>${e.items.length}</sup>` : '')
      + `<span class="wm-name">${esc(e.name || e.id)}</span>`;     // its name as text: a pick by name reads it (the ui port)
  }

  // the live state: the agent moves, entities move, change or go, cells change, the task's progress
  delta(d) {
    const m = this.map;
    if (d.agent) {                                    // `at` a place: the agent stands on its cell; `holding` what it carries
      Object.assign(m.agent, d.agent);
      const at = d.agent.at && m.entities.find(e => e.id === d.agent.at);
      if (at && !d.agent.pos) m.agent.pos = [...at.pos];
      m.agent.name = 'the agent' + (m.agent.holding ? `, holding ${m.agent.holding}` : '');
      this.put({ ...this.agentEnt(), ch: m.agent.ch || '@' });
    }
    for (const u of d.entities || []) {
      const i = m.entities.findIndex(e => e.id === u.id);
      if (u.gone) { if (i >= 0) m.entities.splice(i, 1); this.els.get(u.id)?.remove(); this.els.delete(u.id); continue; }
      const e = i >= 0 ? Object.assign(m.entities[i], u) : (m.entities.push({ ...u }), m.entities.at(-1));
      this.put(e);
    }
    for (const c of d.cells || []) {
      m.cells[c.pos[1]][c.pos[0]] = c.tile;
      const s = this.grid.children[c.pos[1] * m.cols + c.pos[0]];
      if (s) { s.innerHTML = c.tile == null ? '' : this.tile(c.tile); s.classList.toggle('wm-void', c.tile == null); }
    }
    if (d.hot) for (const e of m.entities) { e.hot = d.hot.includes(e.id); this.els.get(e.id)?.classList.toggle('wm-hot', e.hot); }
    if ('cornered' in d) for (const e of m.entities) {   // where the loop stopped and asks (disengagement): the place in red
      e.cornered = e.id === d.cornered; this.els.get(e.id)?.classList.toggle('wm-cornered', e.cornered);
    }
    if (d.task) Object.assign(m.task, d.task);
    if (this.card.open && this.cardFor) this.showTask(this.cardFor);
    const a = this.attn?.dataset.id;                  // the attention slot follows the world: its thing changed (opened, filled, moved)
    if (a && ((a === '@agent' && d.agent) || (d.entities || []).some(u => u.id === a))) this.attend(a);
  }

  attend(id) {
    const e = this.entity(id);
    if (!e) return;
    const ix = this.index[nameOf(e.tile ?? '')] || this.index[nameOf(e.tile ?? '').replace(/_?\d+$/, '')];
    const frame = e.frame ? new URL(e.frame, this.frameBase).href : null;
    this.attn.innerHTML = `<div class="wm-big">${this.tile(e.tile, e.ch)}</div><b>${esc(e.name || e.id)}</b>
      <span class="wm-kind">${esc(e.kind || '')}${e.closed ? ' · closed' : ''}${e.unseen ? ' · not seen yet' : ''}${e.hot ? ' · in the task' : ''}${e.cornered ? ' · the loop stopped here' : ''}</span>
      ${frame ? `<img class="wm-frame" src="${esc(frame)}" alt="${esc(e.name)} as the world showed it">` : ''}
      ${e.items?.length ? `<div class="wm-items">in it: ${e.items.map(esc).join(', ')}</div>` : ''}
      ${ix?.source?.startsWith('http') ? `<a href="${esc(ix.source)}" target="_blank" rel="noopener">about the picture</a>` : ''}`;
    this.attn.dataset.id = id;
    this.onAttend?.(e);
  }

  // the task card: the original words, the goal atom, the chain, the results; what this thing is to it
  showTask(id = '@agent') {
    const t = this.map.task || {}, e = this.entity(id) || {}, chain = t.chain || [], res = t.results || [];
    this.cardFor = id;
    this.card.querySelector('.wm-card').innerHTML = `<h3>the task</h3>
      <p class="wm-words">${t.text ? `“${esc(t.text)}”` : '<span class="wm-empty">no words: the task was not given in words</span>'}</p>
      ${t.source ? `<p class="wm-src">${esc(t.source)}</p>` : ''}
      <p>goal <code class="wm-goal">${esc(t.goal || '—')}</code></p>
      ${e.id && e.id !== '@agent' ? `<p class="wm-this">${esc(e.name)}${e.hot ? ' is part of this task' : ' is not named by this task'}</p>` : ''}
      <h4>so far</h4>${chain.length ? `<ol class="wm-chain">${chain.map(s => `<li><b>${esc(s.domain)}</b> ${esc(s.goal || '')}${s.result ? ` → <code>${esc(s.result)}</code>` : ''}</li>`).join('')}</ol>` : '<p class="wm-empty">nothing yet</p>'}
      ${res.length ? `<h4>said</h4><ul class="wm-results">${res.map(r => `<li>${esc(r)}</li>`).join('')}</ul>` : ''}`;
    if (!this.card.open) this.card.showModal();
    this.onTask?.(t, e);
  }

  // the roving focus: one entity is the tab stop; the arrows move to the nearest in their direction
  rove(b) { for (const x of this.entries()) x.tabIndex = x === b ? 0 : -1; }
  key(ev) {
    const b = ev.target.closest('.wm-ent');
    if (!b) return;
    const dir = { ArrowLeft: [-1, 0], ArrowRight: [1, 0], ArrowUp: [0, -1], ArrowDown: [0, 1] }[ev.key];
    if (!dir) return;
    ev.preventDefault();
    const p = e => { const s = this.els.get(e)?.style; return [+s.getPropertyValue('--x'), +s.getPropertyValue('--y')]; };
    const [x, y] = p(b.dataset.id);
    let best = null, bd = Infinity;
    for (const o of this.entries()) {
      if (o === b) continue;
      const [ox, oy] = p(o.dataset.id), dx = ox - x, dy = oy - y;
      if (dx * dir[0] + dy * dir[1] <= 0) continue;           // not ahead
      const d = Math.hypot(dx, dy) + 2 * Math.abs(dx * dir[1] - dy * dir[0]);
      if (d < bd) { bd = d; best = o; }
    }
    if (best) { this.rove(best); best.focus(); }
  }
}
