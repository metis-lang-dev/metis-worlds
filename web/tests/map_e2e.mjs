// map_e2e.mjs — web/map.html end to end (alf-demo step 3a): headless Chrome over the DevTools
// protocol with real mouse and key events, the repo served by this script. No network, no model.
//
//   node web/tests/map_e2e.mjs            (node >= 22, for its WebSocket: metis-loop's pi/node after pi/setup.sh;
//                                          CHROME=… else google-chrome; exit 1 on a failure)
//
// The checks: both fixtures render (the MiniHack level from its glyphs, the ALFWorld scene from
// its text-mode semantic map); the agent moves on a delta and leaves floor behind; hover shows a
// thing in the attention slot; a click (and Enter) opens the task card with the original words; a
// world's own index entry draws (an icon, and a glyph-only entry); an unknown tile name draws as
// its glyph character; the arrow keys move between things.
if (typeof WebSocket === 'undefined') { console.log('FAIL node >= 22 is needed (its WebSocket): metis-loop pi/node after pi/setup.sh'); process.exit(1); }
import { spawn } from 'node:child_process';
import { createReadStream, existsSync, mkdtempSync, rmSync, statSync } from 'node:fs';
import { createServer } from 'node:http';
import { tmpdir } from 'node:os';
import { extname, join, normalize, resolve } from 'node:path';

const ROOT = resolve(new URL('../..', import.meta.url).pathname);
const TYPES = { '.html': 'text/html', '.js': 'text/javascript', '.css': 'text/css', '.json': 'application/json', '.png': 'image/png' };
const server = createServer((req, res) => {
  const p = normalize(join(ROOT, decodeURIComponent(new URL(req.url, 'http://x').pathname)));
  if (!p.startsWith(ROOT) || !existsSync(p) || !statSync(p).isFile()) { res.writeHead(404); res.end(); return; }
  res.writeHead(200, { 'content-type': TYPES[extname(p)] || 'application/octet-stream' });
  createReadStream(p).pipe(res);
});
await new Promise(r => server.listen(0, '127.0.0.1', r));
const url = `http://127.0.0.1:${server.address().port}/web/map.html`;

const PORT = 9000 + Math.floor(Math.random() * 900);
const prof = mkdtempSync(join(tmpdir(), 'wm-chrome-'));
const chrome = spawn(process.env.CHROME || 'google-chrome', ['--headless=new', `--remote-debugging-port=${PORT}`,
  `--user-data-dir=${prof}`, '--window-size=1200,900', '--no-first-run', 'about:blank'], { stdio: 'ignore' });
const sleep = ms => new Promise(r => setTimeout(r, ms));
let ws, seq = 0;
const pending = new Map();
const cmd = (method, params = {}) => new Promise(r => { const id = ++seq; pending.set(id, r); ws.send(JSON.stringify({ id, method, params })); });
const ev = async expr => {
  const r = await cmd('Runtime.evaluate', { expression: expr, awaitPromise: true, returnByValue: true });
  if (r.result?.exceptionDetails) throw new Error(JSON.stringify(r.result.exceptionDetails).slice(0, 300));
  return r.result?.result?.value;
};
const center = sel => ev(`(() => { const r = document.querySelector(${JSON.stringify(sel)}).getBoundingClientRect(); return [r.x + r.width / 2, r.y + r.height / 2]; })()`);
async function mouse(sel, click = true) {
  const [x, y] = await center(sel);
  await cmd('Input.dispatchMouseEvent', { type: 'mouseMoved', x, y });
  if (click) for (const type of ['mousePressed', 'mouseReleased']) await cmd('Input.dispatchMouseEvent', { type, x, y, button: 'left', clickCount: 1 });
  await sleep(150);
}
const CODES = { Enter: 13, Escape: 27, ArrowRight: 39, ArrowLeft: 37, ArrowUp: 38, ArrowDown: 40 };
async function key(k) {
  for (const type of ['keyDown', 'keyUp']) await cmd('Input.dispatchKeyEvent', { type, key: k, code: k, windowsVirtualKeyCode: CODES[k], ...(k === 'Enter' && type === 'keyDown' ? { text: '\r' } : {}) });
  await sleep(150);
}

const fails = [];
const check = (ok, what, got) => { console.log(`${ok ? 'ok  ' : 'FAIL'} ${what}${ok ? '' : ': ' + JSON.stringify(got)}`); if (!ok) fails.push(what); };
try {
  for (let i = 0; i < 50; i++) { try { await fetch(`http://127.0.0.1:${PORT}/json/version`); break; } catch { await sleep(200); } }
  const tab = await (await fetch(`http://127.0.0.1:${PORT}/json/new?${url}`, { method: 'PUT' })).json();
  ws = new WebSocket(tab.webSocketDebuggerUrl);
  ws.addEventListener('message', e => { const m = JSON.parse(e.data); if (m.id && pending.has(m.id)) { pending.get(m.id)(m); pending.delete(m.id); } });
  await new Promise(r => ws.addEventListener('open', r));
  for (let i = 0; i < 100 && (await ev('document.body?.dataset.ready').catch(() => null)) !== '1'; i++) await sleep(100);
  const MH = '#minihack', ALF = '#alfworld';

  // 1. both fixtures render
  const r = await ev(`({ mh: document.querySelectorAll('${MH} .wm-cell').length, mhEnts: [...document.querySelectorAll('${MH} .wm-ent')].map(b => b.dataset.name),
    mhSprites: document.querySelectorAll('${MH} .wm-sp').length, alfEnts: document.querySelectorAll('${ALF} .wm-ent').length })`);
  check(r.mh === 40 && r.mhSprites > 20, 'the MiniHack level draws from its glyphs (8x5 cells, sprites)', r);
  check(['door (closed)', 'newt', 'apple', 'the agent'].every(n => r.mhEnts.includes(n)), 'the level\'s things are named buttons', r.mhEnts);
  check(r.alfEnts === 52, 'the ALFWorld scene draws its 51 places and the agent', r.alfEnts);

  // 2. the agent moves on a delta and leaves floor behind
  const before = await center(`${MH} .wm-agent`);
  await ev(`maps.minihack.delta({ agent: { pos: [1, 3] } })`);
  await sleep(400);                                    // the move's transition
  const after = await center(`${MH} .wm-agent`);
  const t = await ev(`getComputedStyle(document.querySelector('${MH} .wm-view')).getPropertyValue('--wm-t') || '24px'`);
  check(Math.abs(after[0] - before[0] - 24) < 2 && after[1] === before[1], 'the agent moved one cell right on world/delta', { before, after, t });
  const under = await ev(`document.querySelector('${MH} .wm-grid').children[3 * 8 + 0].querySelector('[data-tile]')?.dataset.tile`);
  const floor = await ev(`document.querySelector('${MH} .wm-grid').children[3 * 8 + 2].querySelector('[data-tile]')?.dataset.tile`);
  check(under && under === floor, 'the cell it left draws floor, not a second agent', { under, floor });

  // 3. hover shows a thing in the attention slot
  await mouse(`${MH} .wm-ent[data-name="newt"]`, false);
  check((await ev(`document.querySelector('${MH} .wm-attn').textContent`)).includes('newt'), 'hover shows the newt in the attention slot', null);

  // 4. a click opens the task card with the original words; Escape closes it; Enter opens it again
  await mouse(`${ALF} .wm-ent[data-id="microwave1"]`);
  const card = await ev(`({ open: document.querySelector('${ALF} .wm-task').open, text: document.querySelector('${ALF} .wm-card').textContent })`);
  check(card.open && card.text.includes('Put a tomato in the microwave.') && card.text.includes('fetch(tomato1, microwave1)')
    && card.text.includes('microwave 1 is part of this task'), 'a click on the microwave opens the task card: the words, the goal, its part', card);
  await key('Escape');
  check(!(await ev(`document.querySelector('${ALF} .wm-task').open`)), 'Escape closes the task card', null);
  await ev(`document.querySelector('${MH} .wm-agent').focus()`);
  await key('Enter');
  check((await ev(`document.querySelector('${MH} .wm-task').open && document.querySelector('${MH} .wm-card').textContent.includes('Find the stairs down')`)),
    'Enter on the agent opens the level\'s task card', null);
  await key('Escape');

  // 5. a world's own index entries draw: an icon (fridge → the ice box) and a glyph-only entry (countertop → _)
  const w = await ev(`({ fridge: document.querySelector('${ALF} .wm-ent[data-id="fridge1"] img')?.src || null,
    counter: document.querySelector('${ALF} .wm-ent[data-id="countertop1"] .wm-ch')?.textContent || null,
    cabinet: document.querySelector('${ALF} .wm-ent[data-id="cabinet1"] img')?.src || null })`);
  check(/ice%20box\.png$/.test(w.fridge || ''), 'the world\'s index draws the fridge as its own icon (not in the base)', w);
  check(w.counter === '_' && /chest\.png$/.test(w.cabinet || ''), 'a glyph-only entry draws its glyph; cabinet3 → cabinet by its type', w);

  // 6. an unknown tile name draws as its glyph character (its ch, else its first letter)
  await ev(`maps.minihack.delta({ entities: [{ id: 'gold', name: 'a zorkmid', pos: [2, 1], tile: 'zorkmid_pile', ch: '$', kind: 'object' },
                                             { id: 'thing', name: 'a thing', pos: [2, 0], tile: 'quux', kind: 'object' }] })`);
  const u = await ev(`[document.querySelector('${MH} [data-id="gold"] .wm-ch')?.textContent, document.querySelector('${MH} [data-id="thing"] .wm-ch')?.textContent]`);
  check(u[0] === '$' && u[1] === 'q', 'an unknown tile name draws as its glyph character', u);

  // 7. the arrow keys move between things, nearest first in that direction
  await ev(`document.querySelector('${MH} .wm-agent').focus()`);
  await key('ArrowRight');
  check((await ev(`document.activeElement?.dataset.name`)) === 'newt', 'ArrowRight from the agent focuses the newt', await ev(`document.activeElement?.dataset.name`));
  await key('ArrowUp');
  check((await ev(`document.activeElement?.dataset.name`)) === 'a zorkmid', 'ArrowUp from the newt focuses what is above it', await ev(`document.activeElement?.dataset.name`));
} catch (e) {
  fails.push(String(e)); console.log('FAIL', e);
} finally {
  // Chrome's exit first: removing its profile while it still writes there races it
  await new Promise(r => { if (chrome.exitCode !== null) return r(); chrome.once('exit', r); chrome.kill(); setTimeout(r, 5000); });
  server.close(); rmSync(prof, { recursive: true, force: true });
}
console.log(fails.length ? `${fails.length} failed` : 'all passed');
process.exit(fails.length ? 1 : 0);
