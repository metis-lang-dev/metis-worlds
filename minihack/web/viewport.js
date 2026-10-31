// viewport.js — the map's window: a world of cells seen through a box whose size is the layout's. The wheel zooms round the
// pointer, a drag moves the view, the buttons zoom in and out, go back to 1:1, show all that has been seen and centre on the
// hero. Centring turns following on (the hero stays in view as it walks); a drag or the wheel leaves it off until asked again.
//
//   const v = new Viewport(box, world, { cell: 16, focus: () => [x, y], seen: () => [x0, y0, x1, y1] | null });
//   v.one() · v.zoomBy(±1) · v.zoomAt(±1, px, py) · v.drag(dx, dy) · v.center() · v.fit() · v.follow · v.keep()
//
// A zoom is whole screen pixels per cell, so neighbouring tiles never show a seam between them.

const STEPS = [8, 12, 16, 20, 24, 32, 40, 48, 64, 80, 96];   // screen pixels per cell
const KEEP = 0.2;                                            // the hero stays this far (of the box) from its edges
const DRAG_FROM = 4;                                         // pixels: less is a click
const FIT_MOST = 32;                                         // a level hardly seen yet is not blown up to fill the box

export class Viewport {
  constructor(box, world, { cell = 16, focus = () => null, seen = () => null, cols = () => 0, rows = () => 0 } = {}) {
    Object.assign(this, { box, world, cell, focus, seen, cols, rows });
    this.px = cell; this.x = 0; this.y = 0; this.follow = true;
    this.controls();
    if (box.addEventListener) this.pointer();
  }

  get z() { return this.px / this.cell; }

  draw() {
    this.world.style.transform = `translate(${this.x}px, ${this.y}px) scale(${this.z})`;
    if (this.zoomLabel) this.zoomLabel.textContent = `${Math.round(this.z * 100)}%`;
    this.followButton?.setAttribute('aria-pressed', String(this.follow));
  }

  // the box's middle always lies on the world: it can be moved anywhere to look at, and never lost
  clamp() {
    const axis = (at, size, box) => Math.round(Math.min(box / 2, Math.max(box / 2 - size, at)));
    this.x = axis(this.x, this.cols() * this.px, this.box.clientWidth);
    this.y = axis(this.y, this.rows() * this.px, this.box.clientHeight);
  }

  set(px, x = this.x, y = this.y) { this.px = px; this.x = x; this.y = y; this.clamp(); this.draw(); }

  // the step `dir` away from this zoom; the cell under (bx, by) in the box stays under it
  zoomAt(dir, bx, by) {
    const next = (dir > 0 ? STEPS.find(s => s > this.px) : [...STEPS].reverse().find(s => s < this.px)) ?? this.px;
    if (next === this.px) return;
    const r = next / this.px;
    this.set(next, bx - (bx - this.x) * r, by - (by - this.y) * r);
  }

  // the buttons: round the hero when he is followed, else round the box's middle
  zoomBy(dir) {
    this.zoomAt(dir, this.box.clientWidth / 2, this.box.clientHeight / 2);
    if (this.follow) this.center();
  }

  drag(dx, dy) { this.follow = false; this.set(this.px, this.x + dx, this.y + dy); }

  // the cell's middle in the box's middle
  look(cx, cy) { this.set(this.px, this.box.clientWidth / 2 - (cx + 0.5) * this.px, this.box.clientHeight / 2 - (cy + 0.5) * this.px); }

  center() {
    this.follow = true;
    const f = this.focus();
    if (f) this.look(f[0], f[1]); else this.draw();
  }

  one() {
    const f = this.follow ? null : [(this.box.clientWidth / 2 - this.x) / this.px - 0.5, (this.box.clientHeight / 2 - this.y) / this.px - 0.5];
    this.px = this.cell;
    if (f) this.look(f[0], f[1]); else this.center();
  }

  // all that has been seen, as large as the box allows, within the zoom steps
  fit() {
    const s = this.seen() || [0, 0, this.cols() - 1, this.rows() - 1], pad = 2;
    const x0 = Math.max(0, s[0] - pad), y0 = Math.max(0, s[1] - pad), x1 = Math.min(this.cols() - 1, s[2] + pad), y1 = Math.min(this.rows() - 1, s[3] + pad);
    const want = Math.min(this.box.clientWidth / (x1 - x0 + 1), this.box.clientHeight / (y1 - y0 + 1));
    this.px = [...STEPS].reverse().find(p => p <= Math.min(want, FIT_MOST)) ?? STEPS[0];
    this.follow = true;
    this.look((x0 + x1) / 2, (y0 + y1) / 2);
  }

  // the hero walked, or the box changed: a followed hero near an edge brings the view back round him
  keep() {
    if (!this.follow) { this.clamp(); return this.draw(); }
    const f = this.focus();
    if (!f) return;
    const w = this.box.clientWidth, h = this.box.clientHeight, sx = this.x + (f[0] + 0.5) * this.px, sy = this.y + (f[1] + 0.5) * this.px;
    if (sx < w * KEEP || sx > w * (1 - KEEP) || sy < h * KEEP || sy > h * (1 - KEEP)) this.look(f[0], f[1]);
    else { this.clamp(); this.draw(); }
  }

  controls() {
    if (!this.box.ownerDocument) return;
    const bar = this.box.ownerDocument.createElement('div');
    bar.className = 'wm-vp'; bar.setAttribute('role', 'toolbar'); bar.setAttribute('aria-label', 'the map\'s view');
    const button = (text, title, fn) => {
      const b = this.box.ownerDocument.createElement('button');
      b.type = 'button'; b.textContent = text; b.title = title; b.setAttribute('aria-label', title);
      b.onclick = e => { e.stopPropagation(); fn(); };
      bar.appendChild(b);
      return b;
    };
    button('−', 'zoom out', () => this.zoomBy(-1));
    this.zoomLabel = this.box.ownerDocument.createElement('span');
    this.zoomLabel.className = 'wm-vp-z';
    bar.appendChild(this.zoomLabel);
    button('+', 'zoom in', () => this.zoomBy(1));
    button('1:1', 'one tile pixel to one screen pixel', () => this.one());
    button('fit', 'all that has been seen', () => this.fit());
    this.followButton = button('◎', 'centre on the hero and follow', () => this.center());
    bar.addEventListener('pointerdown', e => e.stopPropagation());
    bar.addEventListener('wheel', e => e.stopPropagation(), { passive: true });
    this.box.appendChild(bar);
  }

  pointer() {
    const box = this.box;
    let down = null, moved = false;
    box.addEventListener('wheel', e => {
      e.preventDefault();
      const r = box.getBoundingClientRect();
      this.follow = false;
      this.zoomAt(e.deltaY < 0 ? 1 : -1, e.clientX - r.left - box.clientLeft, e.clientY - r.top - box.clientTop);
    }, { passive: false });
    box.addEventListener('pointerdown', e => {
      if (e.button !== 0) return;
      down = { x: e.clientX, y: e.clientY, id: e.pointerId }; moved = false;
    });
    box.addEventListener('pointermove', e => {
      if (!down || e.pointerId !== down.id) return;
      const dx = e.clientX - down.x, dy = e.clientY - down.y;
      if (!moved && Math.hypot(dx, dy) < DRAG_FROM) return;
      if (!moved) { moved = true; box.setPointerCapture?.(e.pointerId); box.classList.add('wm-dragging'); }
      down.x = e.clientX; down.y = e.clientY;
      this.drag(dx, dy);
    });
    const up = () => { down = null; box.classList.remove('wm-dragging'); };
    box.addEventListener('pointerup', up);
    box.addEventListener('pointercancel', up);
    // the click that ends a drag opens nothing
    box.addEventListener('click', e => { if (moved) { moved = false; e.stopPropagation(); e.preventDefault(); } }, true);
    box.addEventListener('dragstart', e => e.preventDefault());
  }
}
