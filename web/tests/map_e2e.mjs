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
import { open, checks, sleep } from './cdp.mjs';

const c = checks();
const page = await open('web/map.html');
try {
  const MH = '#minihack', ALF = '#alfworld';

  // 1. both fixtures render
  const r = await page.ev(`({ mh: document.querySelectorAll('${MH} .wm-cell').length, mhEnts: [...document.querySelectorAll('${MH} .wm-ent')].map(b => b.dataset.name),
    mhSprites: document.querySelectorAll('${MH} .wm-sp').length, alfEnts: document.querySelectorAll('${ALF} .wm-ent').length })`);
  c.ok(r.mh === 40 && r.mhSprites > 20, 'the MiniHack level draws from its glyphs (8x5 cells, sprites)', r);
  c.ok(['door (closed)', 'newt', 'apple', 'the agent'].every(n => r.mhEnts.includes(n)), 'the level\'s things are named buttons', r.mhEnts);
  c.ok(r.alfEnts === 52, 'the ALFWorld scene draws its 51 places and the agent', r.alfEnts);

  // 2. the agent moves on a delta and leaves floor behind
  const before = await page.center(`${MH} .wm-agent`);
  await page.ev(`maps.minihack.delta({ agent: { pos: [1, 3] } })`);
  await sleep(400);                                    // the move's transition
  const after = await page.center(`${MH} .wm-agent`);
  const t = await page.ev(`getComputedStyle(document.querySelector('${MH} .wm-view')).getPropertyValue('--wm-t') || '24px'`);
  c.ok(Math.abs(after[0] - before[0] - 24) < 2 && after[1] === before[1], 'the agent moved one cell right on world/delta', { before, after, t });
  const under = await page.ev(`document.querySelector('${MH} .wm-grid').children[3 * 8 + 0].querySelector('[data-tile]')?.dataset.tile`);
  const floor = await page.ev(`document.querySelector('${MH} .wm-grid').children[3 * 8 + 2].querySelector('[data-tile]')?.dataset.tile`);
  c.ok(under && under === floor, 'the cell it left draws floor, not a second agent', { under, floor });

  // 3. hover shows a thing in the attention slot
  await page.mouse(`${MH} .wm-ent[data-name="newt"]`, false);
  c.ok((await page.ev(`document.querySelector('${MH} .wm-attn').textContent`)).includes('newt'), 'hover shows the newt in the attention slot', null);

  // 4. a click opens the task card with the original words; Escape closes it; Enter opens it again
  await page.mouse(`${ALF} .wm-ent[data-id="microwave1"]`);
  const card = await page.ev(`({ open: document.querySelector('${ALF} .wm-task').open, text: document.querySelector('${ALF} .wm-card').textContent })`);
  c.ok(card.open && card.text.includes('Put a tomato in the microwave.') && card.text.includes('fetch(tomato1, microwave1)')
    && card.text.includes('microwave 1 is part of this task'), 'a click on the microwave opens the task card: the words, the goal, its part', card);
  await page.key('Escape');
  c.ok(!(await page.ev(`document.querySelector('${ALF} .wm-task').open`)), 'Escape closes the task card', null);
  await page.ev(`document.querySelector('${MH} .wm-agent').focus()`);
  await page.key('Enter');
  c.ok((await page.ev(`document.querySelector('${MH} .wm-task').open && document.querySelector('${MH} .wm-card').textContent.includes('Find the stairs down')`)),
    'Enter on the agent opens the level\'s task card', null);
  await page.key('Escape');

  // 5. a world's own index entries draw: an icon (fridge → the ice box) and a glyph-only entry (countertop → _)
  const w = await page.ev(`({ fridge: document.querySelector('${ALF} .wm-ent[data-id="fridge1"] img')?.src || null,
    counter: document.querySelector('${ALF} .wm-ent[data-id="countertop1"] .wm-ch')?.textContent || null,
    cabinet: document.querySelector('${ALF} .wm-ent[data-id="cabinet1"] img')?.src || null })`);
  c.ok(/ice%20box\.png$/.test(w.fridge || ''), 'the world\'s index draws the fridge as its own icon (not in the base)', w);
  c.ok(w.counter === '_' && /chest\.png$/.test(w.cabinet || ''), 'a glyph-only entry draws its glyph; cabinet3 → cabinet by its type', w);

  // 6. an unknown tile name draws as its glyph character (its ch, else its first letter)
  await page.ev(`maps.minihack.delta({ entities: [{ id: 'gold', name: 'a zorkmid', pos: [2, 1], tile: 'zorkmid_pile', ch: '$', kind: 'object' },
                                             { id: 'thing', name: 'a thing', pos: [2, 0], tile: 'quux', kind: 'object' }] })`);
  const u = await page.ev(`[document.querySelector('${MH} [data-id="gold"] .wm-ch')?.textContent, document.querySelector('${MH} [data-id="thing"] .wm-ch')?.textContent]`);
  c.ok(u[0] === '$' && u[1] === 'q', 'an unknown tile name draws as its glyph character', u);

  // 7. the arrow keys move between things, nearest first in that direction
  await page.ev(`document.querySelector('${MH} .wm-agent').focus()`);
  await page.key('ArrowRight');
  c.ok((await page.ev(`document.activeElement?.dataset.name`)) === 'newt', 'ArrowRight from the agent focuses the newt', await page.ev(`document.activeElement?.dataset.name`));
  await page.key('ArrowUp');
  c.ok((await page.ev(`document.activeElement?.dataset.name`)) === 'a zorkmid', 'ArrowUp from the newt focuses what is above it', await page.ev(`document.activeElement?.dataset.name`));
} catch (e) {
  c.fail(e);
} finally {
  await page.close();
}
c.done();
