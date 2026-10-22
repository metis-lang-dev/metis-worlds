// ui-port.js — the page as the ui domain's host (console-nav s-b923ebfe; domains/ui/README.md,
// "The input port" and "The effects"): the browser's own focus events become the port's
// world lines, the host's effects become what the page does. No widget names here: a widget
// is an element with data-w="<id>", its role in data-role; the instance's tree is the DOM's.
//
//   const port = new UiPort({ send: lines => …, root: document.getElementById('root') });
//   port.effect({ ui: 'focus', widget: 'panel' })      // one effect of the host (the trace's)
//   port.openDialog(dlg)  /  dlg.close()                // the page's own dialog
//
// The port (page → model): one +enter(W) per focus change (focusin, mouse and keyboard
// alike; the widget is the focused element's nearest [data-w]); +blur when the focus left
// every widget (the viewport); +opened(D) when a dialog rises, the entry's focusin folded
// in (one input: no +enter for it); +closed(D) when it falls (the browser's focus back to
// the invoker is a focusin: +enter); -hidden/+shown, -shown/+hidden for a dock the page
// shows or hides itself (not for an effect); +picked / +nothing_picked / +ambiguous as a
// pick's answer, +page_refused when the one entry it names is disabled (aria-disabled). Elements outside `root` (the page's own controls, the text line) are not
// widgets: a focus there is neither an enter nor a blur.
//
// The console's copy (metis-loop console/lib; tests/synth/page/ui-port.js is the synthetic
// page's, b65401a): an element inside [data-port-off] is the page's own control, never a
// widget (the dialog panel's text line and mic sit inside the `talk` dock); onDock(w, shown),
// when the page gives it, shows or hides a dock for an effect (the shell's docks keep their
// own state), docked(w, shown) reports a dock the page's shell showed or hid by itself, and
// onPick(w, text, entry) has the picked entry too.
//
// The sample (page → observe): `?focus(W)` / `?blur`, the page's real focus whenever it
// differs from what the port last said — a focus change no event reported (an element
// removed under the focus: the standards' silent case) reaches observe() this way.

export class UiPort {
  // syncDocks: the takeover report restates every dock (off until the base folds a doubled
  // shown/hidden token: console-nav P2 — a dock already in that state would be held twice)
  constructor({ send, root, log = () => {}, sampleMs = 500, syncDocks = false, onDock = null }) {
    Object.assign(this, { send, root, log, syncDocks, onDock });
    this.said = null;            // the widget the port last reported (the model's view of the page); null: nothing yet
    this.sampled = null;         // the last sample sent
    this.folding = null;         // a dialog rising: its entry's focusin is +opened's
    this.mute = false;           // a test hook: the next focus change goes unreported
    this.numbered = null;        // {widget, items}: the entries the page shows numbers on
    this.choice = null;          // the candidates of an ambiguous pick, numbered
    this.mode = 'command';
    this.queue = [];
    document.addEventListener('focusin', e => this.focusin(e.target), true);
    document.addEventListener('focusout', e => { if (!e.relatedTarget) setTimeout(() => this.maybeBlur(), 0); }, true);
    setInterval(() => this.sample(), sampleMs);
  }

  // -- the port ----------------------------------------------------------------

  line(l) {
    this.queue.push(l);
    if (this.queue.length === 1) queueMicrotask(() => { const ls = this.queue; this.queue = []; this.send(ls); });
  }
  widgetOf(el) {
    if (!el || el === document.body || !this.root.contains(el) || el.closest('[data-port-off]')) return null;
    return el.closest('[data-w]')?.dataset.w ?? null;
  }
  el(w) { return this.root.querySelector(`[data-w="${w}"]`) ?? (this.root.dataset.w === w ? this.root : null); }
  focusin(target) {
    const w = this.widgetOf(target);
    if (w == null) return;                       // the page's own controls, the text line
    if (this.folding && w === this.folding.entry) { this.said = w; return; }   // the dialog's entry: +opened carries it
    if (this.mute) { this.mute = false; return; }
    if (w === this.said) return;                 // coalesced: one per change
    this.said = w;
    this.line(`+enter(${w})`);
  }
  maybeBlur() {
    const a = document.activeElement;
    if (a && a !== document.body) return;        // the focus went somewhere: its focusin said so
    if (this.mute) { this.mute = false; return; }
    if (this.said === 'root') return;
    this.said = 'root';
    this.line('+blur');
  }
  real() {
    const a = document.activeElement;
    if (!a || a === document.body) return 'root';
    return this.widgetOf(a) ?? null;             // null: outside the widgets (the text line): no reading
  }
  sample() {
    if (this.said === null) return;              // not synced yet: the program's focus is not the page's to read
    const r = this.real();
    if (r == null || r === this.said || r === this.sampled) { if (r === this.said) this.sampled = r; return; }
    this.sampled = r;
    this.line(r === 'root' && !document.activeElement?.closest?.('[data-w="root"]') ? '?blur' : `?focus(${r})`);
  }

  // sync: the page's whole visible state, reported once when the page becomes the
  // domain's host (a takeover: a new page, a reload). The program may hold another page's
  // state: every dialog of the page is +opened(D) when up, else +closed(D) (the rules close a
  // modal the old page left, or drop the stray); every dock its +shown / +hidden; then the
  // real focus (+enter(W), or +blur). The sampler starts after it.
  sync() {
    for (const d of this.root.querySelectorAll('dialog[data-w]')) this.line(d.open ? `+opened(${d.dataset.w})` : `+closed(${d.dataset.w})`);
    if (this.syncDocks) for (const e of this.root.querySelectorAll('[data-role="dock"]')) this.line(e.hidden ? `+hidden(${e.dataset.w})` : `+shown(${e.dataset.w})`);
    const a = document.activeElement, w = this.real() ?? 'root';   // the focus in the text line: the page's widget is the root's
    this.said = this.sampled = w;
    this.line(!a || a === document.body || this.widgetOf(a) == null ? '+blur' : `+enter(${w})`);
  }

  // -- the page's own acts ---------------------------------------------------------

  openDialog(dlg, { modal = true } = {}) {
    const d = dlg.dataset.w, entry = dlg.dataset.entry ?? d;
    this.folding = { dialog: d, entry };
    dlg.addEventListener('close', () => this.line(`+closed(${d})`), { once: true });
    this.line(`+opened(${d})`);
    if (modal) dlg.showModal(); else dlg.show();
    if (!modal) this.el(entry)?.focus();         // show() does not move the focus: the page does, as showModal would
    this.said = entry;
    this.folding = null;                         // the entry's focusin was synchronous: every later one is a move
    this.unjump();                               // a dialog rising drops the labels (the base's open_jump)
  }
  dockItself(w, shown) {
    const e = this.el(w);
    if (!e) return;
    e.hidden = !shown;
    this.docked(w, shown);
  }
  // docked: the page showed or hid the dock itself (it is already so): the port says it
  docked(w, shown) {
    this.line(shown ? `-hidden(${w})` : `-shown(${w})`);
    this.line(shown ? `+shown(${w})` : `+hidden(${w})`);
  }
  // shown: a dock shown or hidden for an effect, by the page's shell when it has one
  shown(el, w, on) {
    if (this.onDock && el.dataset.role === 'dock') this.onDock(w, on);
    else el.hidden = !on;
  }

  // -- the host's effects ------------------------------------------------------------

  entries(w) { return [...(this.el(w)?.querySelectorAll('li') ?? [])]; }
  badges(items) {
    this.unbadge();
    items.forEach((li, i) => { if (i < 9) li.dataset.n = String(i + 1); });
  }
  unbadge() { for (const li of this.root.querySelectorAll('li[data-n]')) delete li.dataset.n; }
  effect(e) {
    this.log('effect', e);
    const w = e.widget, el = w ? this.el(w) : null;
    switch (e.ui) {
      case 'focus': if (el) { if (el.hidden) this.shown(el, w, true); el.focus(); } break;
      case 'show': if (el) this.shown(el, w, true); break;
      case 'hide': if (el) this.shown(el, w, false); break;
      case 'numbers': this.numbered = { widget: w, items: this.entries(w) }; this.badges(this.numbered.items); break;
      case 'unnumber': this.numbered = null; this.choice = null; this.unbadge(); break;
      case 'pick': this.pick(e); break;
      case 'mode': this.mode = e.mode; this.onMode?.(e.mode); break;
      case 'jump': this.jump(e.letter); break;
      case 'jump_pick': this.jumpPick(e.number); break;
      case 'unjump': this.unjump(); break;
      default: this.log('effect?', e);
    }
  }
  // jump (page-wide hint mode, Vimium's f / Emacs avy): every widget the person can reach,
  // labelled 1–9 in the page's order — inside the dialog only while one is up; a hidden dock
  // too (the jump shows it first); with a letter, only the widgets whose name starts with it;
  // more than nine: the first nine, and the bar says how many more
  reachable(letter) {
    const open = [...this.root.querySelectorAll('dialog[data-w]')].find(d => d.open);
    const all = [...(open ?? this.root).querySelectorAll('[data-w]')].filter(e => {
      if (e === this.root || e === open) return false;
      if (!open && e.closest('dialog')) return false;          // a closed dialog's contents are not there
      const hiddenUp = e.parentElement?.closest('[hidden]');
      return !hiddenUp && (!e.hidden || e.dataset.role === 'dock');
    });
    return letter ? all.filter(e => e.dataset.w.startsWith(letter.toLowerCase())) : all;
  }
  jump(letter) {
    this.unjump();
    const all = this.reachable(letter);
    this.labels = all.slice(0, 9);
    this.labels.forEach((e, i) => { e.dataset.j = String(i + 1); });
    this.onJump?.(this.labels.map((e, i) => `${i + 1} ${e.dataset.w}${e.hidden ? ' (hidden)' : ''}`), Math.max(0, all.length - 9));
  }
  jumpPick(n) {
    const e = this.labels?.[n - 1];
    this.unjump();
    this.line(e ? `+jumped(${e.dataset.w})` : '+nothing_picked');
  }
  unjump() {
    for (const e of this.root.querySelectorAll('[data-j]')) delete e.dataset.j;
    this.labels = null;
    this.onJump?.(null, 0);
  }

  pick(e) {
    const all = this.entries(e.widget);
    let hit;
    if (e.choice && this.choice) hit = this.choice.slice(e.number - 1, e.number);
    else if (e.number != null) hit = all.slice(e.number - 1, e.number).filter(() => e.number > 0);
    else {
      const words = (e.name ?? '').toLowerCase().match(/[a-z0-9]+/g)?.filter(x => !['the', 'a', 'an', 'entry', 'item'].includes(x)) ?? [];
      hit = words.length ? all.filter(li => words.every(x => li.textContent.toLowerCase().includes(x))) : [];
    }
    if (hit.length === 1 && hit[0].getAttribute('aria-disabled') === 'true') {
      this.line('+page_refused');                // the page declines it: the entry is not to be picked
    } else if (hit.length === 1) {
      for (const li of all) li.classList.toggle('picked', li === hit[0]);
      if (this.choice) {                         // a choice resolved: its candidates' numbers go (the list's stay, if up)
        this.choice = null;
        if (this.numbered) this.badges(this.numbered.items); else this.unbadge();
      }
      this.onPick?.(e.widget, hit[0].textContent.trim(), hit[0]);
      this.line('+picked');
    } else if (hit.length > 1) {
      this.choice = hit;
      this.badges(hit);                          // the page numbers the candidates: say the number
      this.line('+ambiguous');
    } else {
      this.line('+nothing_picked');
    }
  }
}
