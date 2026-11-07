// scenarios.js — the SCENARIOS card of the road page's TOOLS (loop-road-ui, the user's word 2026-11-07): the scenario catalog as a tree for
// the tester, grouped by where the scenario comes from (the towns and plain roads, OpenSCENARIO's CARLA ScenarioRunner cards, CommonRoad,
// ours), then by the situation it exercises; CommonRoad as its own tree has it, recorded or interactive, then its provenance. One click shows a scenario's card in the WORLD CARD dock (a town: the world's own card);
// a double click runs it (a card at its first site; its other sites are on the card). The host serves the rows (world/catalog: the
// `catalog` line) and a card whole (world/scard: `scard:NAME`), road_host.catalog_tree / scenario_card.

const esc = s => String(s ?? '').replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' })[c]);
const SOURCES = [
  ['scenario-runner', 'OpenSCENARIO', 'CARLA ScenarioRunner scenarios, played on the towns'],
  ['commonroad', 'CommonRoad', 'recorded and hand-made scenarios from the CommonRoad benchmark, on their own roads'],
  ['ours', 'Ours', 'our scenarios on the intersection world (not run on this page)'],
];
const words = t => String(t).replace(/-/g, ' ');
const KINDS = { recorded: 'recorded: the others as they drove', interactive: 'interactive: the others react (SUMO)' };
const PROV = { 'scenario-factory': 'scenario factory', 'hand-crafted': 'hand-crafted', SUMO: 'SUMO', NGSIM: 'NGSIM (US highways)', 'THI-Bicycle': 'THI bicycle', cooperative: 'cooperative' };

export class Scenarios {
  constructor(box, { line, onCard, onTown, run }) {
    Object.assign(this, { box, line, onCard, onTown, run, rows: [], towns: [], current: null, sel: null, q: '' });
    this.box.innerHTML = `<input type="search" class="sc-find" placeholder="find: a name, a town, a situation (junction, cut in, cyclist…)" aria-label="find a scenario" spellcheck="false">
      <div class="sc-tree" role="tree" aria-label="the scenarios"><p class="empty">loading the scenarios…</p></div>
      <p class="sc-help">click: its card in WORLD CARD · double click: run it</p>`;
    this.tree = box.querySelector('.sc-tree');
    let t = null;
    box.querySelector('.sc-find').oninput = e => { clearTimeout(t); t = setTimeout(() => { this.q = e.target.value.trim().toLowerCase(); this.draw(); }, 150); };
    this.tree.addEventListener('click', e => this.click(e, false));
    this.tree.addEventListener('dblclick', e => this.click(e, true));
    this.tree.addEventListener('keydown', e => { if (e.key === 'Enter') this.click(e, true); });
  }

  ask() { this.line('catalog'); }
  catalog(f) { this.rows = f.rows || []; this.towns = f.towns || []; this.draw(); }
  running(name) { this.current = name; this.box.querySelectorAll('.sc-leaf').forEach(li => li.classList.toggle('run', this.isRunning(li.dataset))); }
  isRunning(d) { return !!this.current && (d.town ? d.town === this.current : this.current.startsWith('card:' + d.id + '@') || this.current === 'cr:' + d.id); }

  match(r) {
    if (!this.q) return true;
    return [r.id, r.title, r.situation, r.kind, r.provenance, ...(r.tags || []), ...(r.runs || []).map(x => x.label)].some(s => String(s).toLowerCase().includes(this.q)
      || words(s).toLowerCase().includes(this.q));
  }

  draw() {
    const open = new Set([...this.tree.querySelectorAll('details[open]')].map(d => d.dataset.key));
    const det = (key, label, n, body, hint) => `<details data-key="${esc(key)}" ${open.has(key) || (this.q && n) ? 'open' : ''}>
      <summary title="${esc(hint || '')}">${esc(label)} <span class="sc-n">${n}</span></summary>${body}</details>`;
    const leaf = r => `<li class="sc-leaf${r.id === this.sel ? ' sel' : ''}${this.isRunning(r) ? ' run' : ''}${r.runs?.length ? '' : ' elsewhere'}" data-id="${esc(r.id)}" tabindex="0" role="treeitem" title="${esc(r.title)}">
      <span class="sc-name">${esc(r.id)}</span>${r.source === 'commonroad' ? `<span class="sc-sit">${esc(words(r.situation))}</span>` : ''}${r.verdict ? `<span class="sc-v sc-${esc(r.verdict)}">${esc(r.verdict)}</span>` : ''}${r.set === 'regression' ? '<span class="sc-set" title="the regression set: proven">✓</span>' : ''}</li>`;
    const towns = this.towns.filter(t => !this.q || t.toLowerCase().includes(this.q));
    const town = t => `<li class="sc-leaf${t === this.sel ? ' sel' : ''}${t === this.current ? ' run' : ''}" data-town="${esc(t)}" tabindex="0" role="treeitem"><span class="sc-name">${esc(t)}</span></li>`;
    let html = det('towns', 'Towns', towns.length, `<ul>${towns.filter(t => /^Town/.test(t)).map(town).join('')}</ul>`
      + (towns.some(t => !/^Town/.test(t)) ? det('towns/plain', 'plain roads', towns.filter(t => !/^Town/.test(t)).length, `<ul>${towns.filter(t => !/^Town/.test(t)).map(town).join('')}</ul>`) : ''),
      'CARLA\'s towns on SUMO: free driving, the traffic yours (the TRAFFIC card)');
    const group = (key, rows, by, label, inner) => [...new Set(rows.map(by))].sort().map(g => {   // a level of the tree: rows grouped BY
      const in_ = rows.filter(r => by(r) === g);
      return det(`${key}/${g}`, label(g), in_.length, inner ? inner(`${key}/${g}`, in_) : `<ul>${in_.sort((a, b) => a.id.localeCompare(b.id)).map(leaf).join('')}</ul>`);
    }).join('');
    for (const [src, label, hint] of SOURCES) {
      const rows = this.rows.filter(r => r.source === src && this.match(r));
      if (!rows.length && this.q) continue;
      html += det(src, label, rows.length, src === 'commonroad'
        // CommonRoad as its own tree has it (the user): recorded or interactive, then where it comes from
        ? group(src, rows, r => r.kind || 'other', k => KINDS[k] || k, (key, in_) => group(key, in_, r => r.provenance || 'other', p => PROV[p] || p))
        : group(src, rows, r => r.situation, words), hint);
    }
    this.tree.innerHTML = html || '<p class="empty">nothing found</p>';
  }

  click(e, run) {
    const li = e.target.closest('.sc-leaf');
    if (!li) return;
    if (li.dataset.town) {
      this.sel = li.dataset.town;
      if (run) this.run(li.dataset.town); else this.onTown(li.dataset.town);
    } else {
      const r = this.rows.find(x => x.id === li.dataset.id);
      if (!r) return;
      this.sel = r.id;
      if (run) { if (r.runs?.length) this.run(r.runs[0].run); else this.onCard(r, 'it plays on another world, not on this page'); }
      else { this.onCard(r); this.line(`scard:${r.id}`); }
    }
    this.box.querySelectorAll('.sc-leaf.sel').forEach(x => x.classList.remove('sel'));
    li.classList.add('sel');
  }
}

// the card as the WORLD CARD shows it: for a road tester, what the scenario is, what it checks and how it stands, then its sites to run
export function cardHtml(f) {
  const c = f.card || {}, src = c.source || {}, v = c.verdict || {};
  const kv = pairs => `<dl class="kv">${pairs.filter(([, x]) => x != null && x !== '').map(([k, x]) => `<dt>${esc(k)}</dt><dd>${esc(x)}</dd>`).join('')}</dl>`;
  const stand = ['sumo', 'exerciser'].filter(h => v[h]).map(h => [`on ${h === 'sumo' ? 'SUMO' : 'the exerciser'}`, `${v[h].status}${v[h].note ? ': ' + v[h].note : ''}`]);
  const actors = (c.actors || []).map(a => `${a.id} (${[a.kind, a.mode, a.level].filter(Boolean).join(', ')})`).join(' · ');
  const expect = c.expect ? Object.entries(c.expect).map(([k, x]) => `${words(k)} ${x}`).join(', ') : '';
  return `<p class="wc-title">${esc(c.title || f.id)}</p>
    <p class="wc-about">${esc(f.id)} · ${esc(src.suite === 'lb2' || f.source === 'scenario-runner' ? 'OpenSCENARIO (CARLA ScenarioRunner)' : src.suite === 'commonroad' ? 'CommonRoad' : src.suite || f.source)}${c.set ? ` · the ${esc(c.set)} set` : ''}</p>
    ${c.exercises ? `<div class="wc-h">what it checks</div><p class="wc-about">${esc(c.exercises)}</p>` : ''}
    ${(c.tags || []).length ? `<div class="wc-h">situations</div><p class="wc-about">${(c.tags || []).map(words).map(esc).join(', ')}</p>` : ''}
    ${f.runs?.length ? `<div class="wc-h">run it</div><div class="wc-kinds">${f.runs.map(r => `<button type="button" class="chip" data-run="${esc(r.run)}">${esc(r.label)}</button>`).join('')}</div>`
      : `<div class="wc-h">run it</div><p class="wc-about">${esc(f.note || 'it plays on another world, not on this page')}</p>`}
    <div class="wc-h">how it stands</div>${kv([...stand, ['expected', expect]])}
    <div class="wc-h">the scene</div>${kv([['the ego', c.ego ? `${c.ego.v ?? '?'} m/s${c.ego.path ? ', path ' + c.ego.path : ''}` : ''], ['the others', actors], ['map', (c.map || {}).town || (c.map || {}).world || ((c.map || {}).net ? 'its own road (CommonRoad)' : '')], ['length', c.ticks ? `${(c.ticks * (c.dt || 0.1)).toFixed(0)} s` : '']])}
    <p class="wc-src">${esc([src.type, src.license].filter(Boolean).join(' · '))}</p>
    <p><button type="button" class="chip" data-town-card="1">the town's card</button></p>`;
}
