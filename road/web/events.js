// events.js — the run's EVENTS (loop-road-ui s-0314a8ee, the user's word 2026-11-07): the person's marks and the run's surprises, one list.
// A mark is a window the person opened and closed (the top bar's button, or "mark" … "end mark, WORDS" by voice); a surprise is a one-off
// event the page makes itself when the run's collisions or violations rise, and the run stops on it until the person continues. Each
// event has its window in the trace's k (the host's marks.jsonl row, at_k), so it can be:
//   narrated   /mark TRACE:MEMBER K0..K1 WORDS for each member, in the pi CHAT (the rules' own words + one-fact-short, 0 USD)
//   explained  the question to pi in words (paid, the loop's budget)
//   sent       /disagree M WORDS (a confusion record, the triage) then /take: pi processes it; the person applies or refuses at the gate
// The dashboard draws them and moves their edges (mark:N:move:K0:K1). The list is kept in the browser per trace (localStorage).

const MEMBERS = ['planner', 'responder'];                      // the members narrated: who decides the plan, who answers every tick
const KEY = trace => `roadpage.events.v1:${trace}`;
const QUIET_TICKS = 20;                                        // a rise within 2 s of the last is the same surprise going on
const $ = s => document.querySelector(s);
const esc = s => String(s ?? '').replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' })[c]);
const secs = t => (t == null ? '…' : `${t.toFixed(1)}`);

export class Events {
  constructor(box, { line, loop, hold, speak, onChange }) {
    Object.assign(this, { box, line, loop, hold, speak, onChange: onChange || (() => {}) });
    this.list = []; this.sel = null; this.trace = null; this.last = null; this.stopOn = true; this.waiting = null;
    this.rise = { c: 0, v: 0, tick: -1e9 };
    this.pending = [];                                          // narrations asked, their loop marks to come: [{n, member}]
    this.draw();
  }

  // ── the frames ──
  scene(f) {
    if (f.trace && f.trace !== this.trace) this.load(f.trace);
    const was = this.last;
    if (!was || f.tick < was.tick) this.rise = { c: f.collisions || 0, v: f.violations || 0, tick: -1e9 };
    this.last = f;
  }

  // the run's counters rose: a new surprise (→ its kind) unless it is the last one going on
  surprised(f) {
    const r = this.rise, c = f.collisions || 0, v = f.violations || 0;
    const kind = c > r.c ? 'collision' : v > r.v ? 'violation' : null;
    r.c = c; r.v = v;
    if (!kind) return null;
    const fresh = f.tick - r.tick > QUIET_TICKS;
    r.tick = f.tick;
    return fresh ? kind : null;
  }

  at() { const f = this.last || {}; return { k: f.k ?? f.tick ?? null, t: f.t ?? null, tick: f.tick ?? null }; }

  edge(n, edge, words) {
    const a = this.at();
    let e = this.get(n);
    if (edge === 'start' || !e) {
      e = { n, kind: 'mark', open: true, trace: this.trace, k0: a.k, t0: a.t, k1: null, t1: null, words: '', note: '', loop: [] };
      this.list = this.list.filter(x => x.n !== n).concat(e);
    }
    if (edge === 'stop') { Object.assign(e, { open: false, k1: a.k, t1: a.t }); if (words) e.words = words; }
    this.sel = n;
    this.save(); this.draw();
  }

  once(n, kind, stops = true) {
    const a = this.at();
    this.list = this.list.filter(x => x.n !== n).concat({ n, kind, open: false, trace: this.trace, k0: a.k, t0: a.t, k1: a.k, t1: a.t, words: `a ${kind}`, note: '', loop: [] });
    this.sel = n; if (stops) this.waiting = n;
    this.save(); this.draw();
  }

  moved(n, k0, k1, t0, t1, i0, i1) {                             // the dashboard's drag, ended: the host hears it (the k, and the run's ticks there), the list keeps it
    const e = this.get(n);
    if (!e || e.open) return;
    Object.assign(e, { k0, k1, t0, t1, loop: [] });             // a moved window is narrated again
    this.line(`mark:${n}:move:${k0}:${k1}${i0 != null && i1 != null ? `:${i0}:${i1}` : ''}`);
    this.save(); this.draw();
  }

  resumed() { this.waiting = null; this.draw(); }

  // ── the loop ──
  narrate(n) {
    const e = this.get(n ?? this.sel);
    if (!e || e.open || !e.trace || e.k0 == null) { this.speak(e?.open ? `Event ${e.n} is still open: end it first.` : 'Mark an event first.'); return; }
    this.sel = e.n;
    const words = (e.note || e.words || `event ${e.n}`).replace(/\s+/g, ' ');
    for (const m of MEMBERS) {
      this.pending.push({ n: e.n, member: m });
      this.loop.say(`/mark ${e.trace}:${m} ${e.k0}..${Math.max(e.k0, e.k1)} ${words}`);
    }
    e.state = 'narrated'; this.save(); this.draw();
  }

  explain(n) {
    const e = this.get(n ?? this.sel);
    if (!e || e.open || !e.trace) { this.speak('Mark an event first.'); return; }
    this.sel = e.n;
    const what = e.note || e.words;
    this.loop.say(`Explain event ${e.n} for a road tester: run ${e.trace}, trace window k ${e.k0}..${e.k1} (${secs(e.t0)}–${secs(e.t1)} s of the run)`
      + `${what ? `, what the tester saw: "${what}"` : ''}. Why did the car act as it did there? Name the rules that decided and the facts they saw, in plain words, briefly.`);
    e.state = 'explained'; this.save(); this.draw();
  }

  send(n) {
    const e = this.get(n ?? this.sel);
    if (!e || e.open || !e.trace) { this.speak('Mark an event first.'); return; }
    this.sel = e.n;
    if (!e.loop.length) { e.sendAfter = true; this.narrate(e.n); return; }
    const m = e.loop.find(x => x.member === 'planner') || e.loop[0];
    this.loop.say(`/disagree ${m.mark} ${(e.note || e.words || `event ${e.n}`).replace(/\s+/g, ' ')}`);
    this.loop.say('/take');
    e.sendAfter = false; e.state = 'sent to pi'; this.save(); this.draw();
  }

  row(r) {                                                       // a row of the CHAT: a mark narrated belongs to the oldest narration asked
    if (r.kind !== 'mark' || !r.mark || !this.pending.length) return;
    const p = this.pending.shift(), e = this.get(p.n);
    if (!e) return;
    e.loop = e.loop.filter(x => x.member !== p.member).concat({ member: p.member, mark: r.mark });
    if (e.sendAfter && !this.pending.some(x => x.n === e.n)) this.send(e.n);
    this.save(); this.draw();
  }

  // ── the list ──
  get(n) { return this.list.find(e => e.n === n) || null; }
  select(n) { this.sel = this.get(n) ? n : null; this.draw(); }
  load(trace) {
    this.trace = trace;
    try { this.list = JSON.parse(localStorage.getItem(KEY(trace)) || '[]'); } catch { this.list = []; }
    this.draw();
  }
  save() { if (this.trace) try { localStorage.setItem(KEY(this.trace), JSON.stringify(this.list)); } catch { /* full or private */ } }

  draw() {
    const rows = [...this.list].sort((a, b) => b.n - a.n);
    this.box.innerHTML = `<div class="ev-bar"><label title="the run stops when the car collides or breaks a rule; you continue it"><input type="checkbox" id="ev-stop" ${this.stopOn ? 'checked' : ''}> stop on a surprise</label>
      ${this.waiting != null ? `<button type="button" class="chip ev-go" id="ev-go" title="the run waits on event ${this.waiting}: continue it">continue the run</button>` : ''}</div>
      ${rows.length ? '' : '<p class="empty">No events yet. Press "mark event" when you see a problem, and again when it is over; a collision or a broken rule makes one by itself.</p>'}
      <ol class="ev-list">${rows.map(e => `<li class="ev ${e.n === this.sel ? 'sel' : ''} ev-${e.kind === 'mark' ? 'mark' : 'surprise'}" data-n="${e.n}" tabindex="0">
        <div class="ev-h"><b>#${e.n}</b> <span class="ev-kind">${esc(e.kind === 'mark' ? 'mark' : e.kind)}</span>
          <span class="ev-t">${secs(e.t0)}${e.kind === 'mark' ? `–${secs(e.t1)}` : ''} s</span>${e.open ? '<span class="ev-open">open</span>' : ''}${e.state ? `<span class="ev-st">${esc(e.state)}</span>` : ''}
          <span class="ev-acts"><button type="button" class="glyph" data-act="narrate" title="narrate: the rules' own words for this event (free)">¶</button><button type="button" class="glyph" data-act="explain" title="explain: ask pi why the car acted so (paid)">?</button><button type="button" class="glyph" data-act="send" title="send to the pi loop: a record of what you saw, pi proposes a correction, you decide whether to apply it (paid)">⇢</button></span></div>
        ${e.words && e.kind === 'mark' ? `<div class="ev-w">${esc(e.words)}</div>` : ''}
        <input class="ev-note" type="text" placeholder="what you saw (your words go with it)" value="${esc(e.note)}" aria-label="your words for event ${e.n}">
      </li>`).join('')}</ol>`;
    this.box.querySelector('#ev-stop').onchange = ev => { this.stopOn = ev.target.checked; };
    const go = this.box.querySelector('#ev-go');
    if (go) go.onclick = () => this.hold(false);
    for (const li of this.box.querySelectorAll('li.ev')) {
      const n = Number(li.dataset.n);
      li.onclick = ev => { if (ev.target.closest('button,input')) return; this.select(n); };
      li.querySelector('.ev-note').onchange = ev => { const e = this.get(n); if (e) { e.note = ev.target.value.trim(); this.save(); } };
      for (const b of li.querySelectorAll('[data-act]')) b.onclick = () => this[b.dataset.act](n);
    }
    this.onChange();
  }
}
