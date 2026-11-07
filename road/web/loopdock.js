// loopdock.js — the pi loop's CHAT as a dock of the road page (loop-road-ui s-0314a8ee, brief §1): an iframe of the loop console's
// served page with ?panels=chat&embed=<this page's origin> (never a copy of its code), its rows spoken through the road's one voice.
// The wire is metis-loop's embed face (console/lib/embed.js, CHAT.md §1): window.postMessage, origin-checked on both sides.
//
//   const loop = new LoopDock(box, {url, speak(text), onGate(g), onRow(row)})
//   loop.say(text, via)          a line into the CHAT as typed ("/…" at 0 USD, else pi's)
//   loop.answerGate(how)         the open gate answered: confirm | refuse
//   loop.up                      the face said ready
//   loop.lastMark                the last loop mark narrated (its number, for /agree and /disagree)
//   loop.gate                    the open gate {id, title} | null

const SPOKEN = new Set(['pi', 'cmd', 'mark', 'ruling', 'stale', 'built', 'err']);   // what the tester hears; their own lines, pi's tool calls and notes are only shown
const SPEAK_MAX = 400;

export function loopUrl(q, loc) {                        // ?loop=URL, else this host's :8770 (metis-loop/run.sh's port)
  const u = q.get('loop');
  if (u) return u.replace(/\/$/, '');
  return `${loc.protocol}//${loc.hostname}:8770`;
}

export function spokenForm(row) {                         // a row as the voice says it: the first lines of an answer, a mark's narration whole
  const text = String(row.text ?? '').trim();
  if (!text) return '';
  if (row.kind === 'mark') return text.split('\n').slice(0, 8).join('. ');
  if (row.kind === 'cmd') return text.split('\n').slice(0, 2).join('. ');
  return text.length > SPEAK_MAX ? text.slice(0, SPEAK_MAX) + '…' : text;
}

export class LoopDock {
  constructor(box, { url, speak, onGate, onRow }) {
    Object.assign(this, { box, url, speak, onGate: onGate || (() => {}), onRow: onRow || (() => {}), up: false, lastMark: null, gate: null, queue: [] });
    this.origin = new URL(url).origin;
    this.msg = Object.assign(document.createElement('p'), { className: 'empty loop-msg', textContent: `connecting to the loop at ${url} …` });
    this.frame = Object.assign(document.createElement('iframe'), {
      id: 'loopframe', title: 'the pi loop', src: `${url}/?panels=chat&embed=${encodeURIComponent(location.origin)}`,
    });
    box.replaceChildren(this.msg, this.frame);
    addEventListener('message', e => this.onMessage(e));
    this.timer = setTimeout(() => { if (!this.up) this.msg.textContent = `the loop is not running at ${url}: start it with metis-loop/run.sh in metis-worlds/road (docs/LOOP-TESTING.md), then reload this page`; }, 8000);
  }

  onMessage(e) {
    if (e.origin !== this.origin || e.source !== this.frame.contentWindow) return;   // the loop's console in our dock, nothing else
    const d = e.data;
    if (!d || typeof d !== 'object') return;
    if (d.metis === 'ready') {
      this.up = true; clearTimeout(this.timer); this.msg.hidden = true;
      for (const [t, v] of this.queue.splice(0)) this.post({ metis: 'chat', text: t, via: v });
      return;
    }
    if (d.metis === 'row') {
      if (d.kind === 'mark' && d.mark) this.lastMark = d.mark;
      this.onRow(d);
      if (SPOKEN.has(d.kind) && (d.kind !== 'cmd' || this.sent)) { const s = spokenForm(d); if (s) this.speak(s); }   // the CHAT's opening /status is not said
      return;
    }
    if (d.metis === 'gate') {
      if (d.open) { this.gate = { id: d.id, title: d.title }; this.speak(`The loop asks: ${d.title}. Say confirm, or refuse.`); }
      else if (this.gate && this.gate.id === d.id) this.gate = null;
      this.onGate(d);
    }
  }

  post(m) { this.frame.contentWindow?.postMessage(m, this.origin); }

  say(text, via) {
    if (!text) return;
    this.sent = (this.sent || 0) + 1;
    if (!this.up) { this.queue.push([text, via]); return; }
    this.post({ metis: 'chat', text, ...(via ? { via } : {}) });
  }

  answerGate(how) {
    if (!this.gate || (how !== 'confirm' && how !== 'refuse')) return false;
    this.post({ metis: 'gate', answer: how, id: this.gate.id });
    return true;
  }
}
