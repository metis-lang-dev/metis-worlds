// live_e2e.mjs — web/world.html on the live service's recordings (alf-demo step 3b: web/fixtures/live/, opus's
// world/status and world/ask frames): what the agent wants from the person is always on the page. The status
// line (waiting with the game's task, working with the goal beside the attending domain, asking, over with
// its "new game" chip), the ask box with the task's answers as chips (a chip says its answer), the hierarchy
// reset under a new task, the journal without the page's own world lines, and the consoles' shell (the docks,
// the strip; a dock hidden on the strip reported to the port).
//
//   node web/tests/live_e2e.mjs        (node >= 22)
import { open, checks } from './cdp.mjs';

const c = checks();
const page = await open('web/world.html?replay=fixtures/live/win.run.jsonl');
const ev = page.ev;
const stepTo = pred => ev(`(async () => { for (let i = 0; i < 600; i++) { if (${pred}) return true; if (!(await world.step())) return ${pred}; } return false; })()`);
const st = () => ev(`({ state: document.getElementById('status').dataset.state, text: document.getElementById('stext').textContent,
  chips: [...document.querySelectorAll('#sopts .chip')].map(b => b.textContent) })`);
const band = () => ev(`[...document.querySelectorAll('#talkpanel .fw-log li')].map(l => l.querySelector('.fw-who').textContent + ': ' + l.querySelector('.fw-text').textContent)`);
try {
  // the shell: one look with the consoles
  c.ok(await ev(`!!window.MetisShell && document.querySelector('#band .brand').textContent === 'WORLD' && ['talk','hierarchy','journal'].every(d => document.getElementById('dock-' + d))
    && getComputedStyle(document.body).backgroundColor === 'rgb(13, 16, 20)'`), 'the consoles\' shell: the band, the docks, the dark tokens', null);

  // waiting: the page says what it wants first
  c.ok(await stepTo(`document.getElementById('status').dataset.state === 'waiting'`), 'waiting on hello', await st());
  const w = await st();
  c.ok(w.text.includes("This game's task: Put a tomato in the microwave."), 'the status names the game\'s task', w);
  c.ok((await band()).some(r => r.startsWith('waiting: Tell me a task')), 'the band says it once, as a status line', await band());

  // working: the goal beside the attending domain
  c.ok(await stepTo(`document.getElementById('status').dataset.state === 'working' && document.querySelector('#hlist li[data-domain="nav"] .goal')`),
    'working: the goal shows beside nav in the hierarchy', await ev(`document.getElementById('hlist').textContent.replace(/\\s+/g, ' ')`));
  c.ok(await ev(`document.querySelector('#hlist li[data-domain="nav"] .goal').textContent === 'goal: Going to countertop 3'`), 'the goal in the world\'s names', null);

  // done → over: the chip for a new game
  c.ok(await stepTo(`document.getElementById('status').dataset.state === 'over'`), 'over after the win', await st());
  const o = await st();
  c.ok(o.chips.join() === 'new game' && o.text.startsWith('Done.'), 'over: "new game" offered as a chip', o);
  const rows = await band();
  c.ok(rows.some(r => r === 'agent: Done: the task is done.') && !rows.some(r => r.startsWith('unasked')), 'result lines are the agent\'s, never "unasked"', rows.slice(-4));

  // a new game: the hierarchy's last chain is gone
  c.ok(await stepTo(`[...document.querySelectorAll('#talkpanel .fw-person .fw-text')].some(t => t.textContent === 'new game')`), 'the person asks for a new game', null);
  c.ok(await stepTo(`document.getElementById('status').dataset.state === 'waiting'`), 'waiting again', await st());
  c.ok(await ev(`[...document.querySelectorAll('#hlist li:not([data-domain="task"]) .g, #hlist .goal')].length === 0 && document.getElementById('hstate').textContent === 'waiting'`),
    'the hierarchy reset under the new game (no stale chain, no stale end)', await ev(`document.getElementById('hlist').textContent.replace(/\\s+/g, ' ')`));
  await ev(`world.stepAll()`);
  c.ok((await st()).state === 'over', 'the second win ends over too', await st());

  // the journal: the agent's and the person's lines, not the page's own world atoms
  c.ok(!(await ev(`document.getElementById('jlog').textContent`)).includes('world world_ui'), 'the journal keeps the page\'s world lines out', null);

  // a chip says its answer, as typing it would
  await page.mouse('#sopts .chip');
  c.ok(await stepTo(`[...document.querySelectorAll('#talkpanel .fw-person .fw-text')].filter(t => t.textContent === 'new game').length === 2`)
    && (await ev(`world.log.some(r => r.dir === 'answer' && r.say === 'new game')`)), 'the "new game" chip says "new game"', await band());

  // the shell's strip: hiding a dock is reported to the port
  await page.mouse('[data-strip="hierarchy"]');
  c.ok(await ev(`document.getElementById('dock-hierarchy').hidden && world.log.some(r => r.dir === 'port' && r.lines.includes('+hidden(hierarchy)'))`),
    'a dock hidden on the strip: +hidden(hierarchy) to the port', await ev(`world.log.filter(r => r.dir === 'port').slice(-2)`));
  await page.mouse('[data-strip="hierarchy"]');
  c.ok(await ev(`!document.getElementById('dock-hierarchy').hidden && world.log.some(r => r.dir === 'port' && r.lines.includes('+shown(hierarchy)'))`),
    '…and shown again: +shown(hierarchy)', null);

  // the ask: its question highlighted, its answers as chips
  await page.goto('web/world.html?replay=fixtures/live/fridge.run.jsonl');
  c.ok(await stepTo(`!document.getElementById('ask').hidden`), 'fridge: the ask box opens', null);
  const a = await ev(`({ q: document.getElementById('askq').textContent, chips: [...document.querySelectorAll('#askopts .chip')].map(b => b.textContent),
    state: document.getElementById('status').dataset.state })`);
  await stepTo(`document.getElementById('status').dataset.state === 'asking'`);
  c.ok(a.q === 'Fridge 1 is not where this task wants tomato 1.' && a.chips.join(' / ') === 'put tomato 1 in microwave 1 / stop', 'the question and its two answers', a);
  c.ok(await ev(`[...document.querySelectorAll('#talkpanel .fw-ask .fw-who')].some(w => w.textContent === 'asks')
    && document.querySelector('#map [data-id="fridge1"]').classList.contains('wm-cornered')`), 'the band row says "asks" (highlighted), the fridge in red', await band());
  await page.mouse('#askopts .chip:last-child');
  c.ok(await ev(`world.log.some(r => r.dir === 'answer' && r.say === 'stop') && document.querySelector('#askopts .chip:last-child').getAttribute('aria-pressed') === 'true'`),
    'the "stop" chip says "stop"', null);
  c.ok(await stepTo(`document.getElementById('status').dataset.state === 'waiting' && document.getElementById('ask').hidden`), 'after stop: waiting, the ask box gone', await st());
  c.ok(await ev(`!document.querySelector('#map .wm-cornered')`), 'after stop: no place in red', null);
  await ev(`world.stepAll()`);
  c.ok((await st()).state === 'over', 'fridge: the first answer finishes the task (over)', await st());

  // the phone width
  await page.goto('web/world.html?replay=fixtures/live/fridge.run.jsonl&w=390');
  await ev(`(async () => { document.body.style.width = '390px'; await world.stepAll(); })()`);
  c.ok(await ev(`document.documentElement.scrollWidth <= 390 + 1 || document.body.scrollWidth <= 390 + 1`), 'at 390 px: no horizontal scroll', await ev(`document.body.scrollWidth`));
} finally {
  await page.close();
  c.done();
}
