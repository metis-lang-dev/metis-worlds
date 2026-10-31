// viewport_test.mjs — the map's view without a browser: a fake box and world (tests/test_nh_tty.py runs it under node).
import assert from 'node:assert/strict';
import { Viewport } from '../web/viewport.js';

const box = { clientWidth: 400, clientHeight: 300 }, world = { style: {} };
let hero = [10, 5];
const v = new Viewport(box, world, { focus: () => hero, seen: () => [8, 3, 14, 8], cols: () => 79, rows: () => 21 });
const cellAt = (bx, by) => [(bx - v.x) / v.px, (by - v.y) / v.px];

v.px = 32; v.center();
assert.equal(v.follow, true);
assert.deepEqual(cellAt(200, 150), [10.5, 5.5]);       // the hero's middle in the box's middle

// the wheel's zoom keeps the cell under the pointer, and leaves whole pixels per cell
v.follow = false;
const under = cellAt(300, 100);
v.zoomAt(1, 300, 100);
assert.equal(v.px, 40);
assert.ok(Math.abs(cellAt(300, 100)[0] - under[0]) < 0.05 && Math.abs(cellAt(300, 100)[1] - under[1]) < 0.05);
assert.ok(Number.isInteger(v.px));
for (let i = 0; i < 40; i++) v.zoomAt(1, 0, 0);
assert.equal(v.px, 96);                                // the steps end
for (let i = 0; i < 40; i++) v.zoomAt(-1, 0, 0);
assert.equal(v.px, 8);

// a drag moves the view, turns following off, and cannot lose the world past its edges
v.px = 32; v.center();
const x0 = v.x;
v.drag(-30, 0);
assert.equal(v.follow, false); assert.equal(v.x, x0 - 30);
v.drag(100000, 100000);
assert.equal(v.x, 200); assert.equal(v.y, 150);
v.drag(-100000, -100000);
assert.equal(v.x, 200 - 79 * 32); assert.equal(v.y, 150 - 21 * 32);

// a world smaller than the box still moves, and the hero can be put in its middle
v.set(8); v.center();
assert.deepEqual(cellAt(200, 150), [10.5, 5.5]);

// 1:1 is the tile's own size; centring follows again, and a followed hero walking near the edge brings the view with him
v.one(); assert.equal(v.px, 16);
v.px = 32; v.center();
hero = [11, 5]; const x1 = v.x; v.keep(); assert.equal(v.x, x1);   // well inside: the view stays still
hero = [30, 5]; v.keep(); assert.deepEqual(cellAt(200, 150)[0], 30.5);
// not followed, he may walk out of view
v.drag(-10, 0); const x2 = v.x; hero = [31, 5]; v.keep(); assert.equal(v.x, x2);

// fit: all that was seen, in the largest step that holds it
v.fit();
assert.equal(v.follow, true);
assert.equal(v.px, 24);                                // 11 × 10 cells with their margin in 400 × 300: 30 px at most
console.log('viewport ok');
