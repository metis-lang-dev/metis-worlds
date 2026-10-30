// world_e2e.mjs — web/world.html end to end (alf-demo step 3b): DEMO.md §5's turn driven by the
// recorded frames (web/fixtures/*.run.jsonl, a text-mode run of the hierarchy with the director),
// in headless Chrome with real mouse and key events. No network, no model.
//
//   node web/tests/world_e2e.mjs        (node >= 22: metis-loop's pi/node after pi/setup.sh; exit 1 on a failure)
//
// The turn: the person's words in the band; the director's beats in the hierarchy (who attends,
// who sleeps); the world on the map (the agent goes to the countertop, takes the tomato, goes to
// the microwave, opens it, puts the tomato in); every result's own line spoken in the band and
// kept in the journal; the task card with the words, the goal, the chain and the lines; the end.
// A disengagement: the person's goal the task refuses (the fridge), the band asks, the place in
// red. One voice paradigm (voice-nav-removal s-90621b2c): no voice navigation of the page; its
// affordances turn into the chat (the world card's asks). The docks are tools: the strip shows and
// hides them, a header folds nothing.
import { open, checks, sleep } from './cdp.mjs';

const c = checks();
const page = await open('web/world.html');
const ev = page.ev;
const stepTo = pred => ev(`(async () => { for (let i = 0; i < 200; i++) { if (${pred}) return true; if (!(await world.step())) return ${pred}; } return false; })()`);
try {
  c.ok(await ev(`document.querySelectorAll('#map .wm-ent').length === 52 && world.frames.length > 40`), 'the recording and its map load (51 places and the agent)', null);
  c.ok(await ev(`world.narrator.state === 'stopped' && document.getElementById('voice').classList.contains('fw-voicebar')
    && document.querySelectorAll('#voice .fw-switch').length === 1 && document.getElementById('voice').textContent === 'micnarrator'
    && document.querySelector('#voice .fw-narr')?.dataset.state === 'stopped' && !document.querySelector('#band .narrator')`),
    'the band\'s voice card (fsttm-web): [● mic ⟦switch⟧ narrator], the narrator (F8) always on, stopped', null);
  await ev(`(() => { world.panel.core.listening = true; world.panel.core.changed(); world.narrator._set('reading'); })()`);
  const on = await ev(`[getComputedStyle(document.querySelector('#voice .fw-sw-light')).backgroundColor, getComputedStyle(document.querySelector('#voice .fw-narr')).color]`);
  c.ok(on.every(x => x === 'rgb(63, 185, 80)'), 'on: the mic light and the reading narrator green (not the page\'s white accent)', on);

  // the docks resize vertically: the grip on HIERARCHY's top edge moves its border with TALK; kept; a double click: equal
  const hs = () => ev(`['talk', 'hierarchy'].map(d => Math.round(document.getElementById('dock-' + d).getBoundingClientRect().height))`);
  const g = await ev(`(() => { const g = document.querySelector('#dock-hierarchy > .dgrip'), r = g.getBoundingClientRect(); return { hidden: g.hidden, x: r.x + r.width / 2, y: r.y + r.height / 2, talkGrip: document.querySelector('#dock-talk > .dgrip')?.hidden }; })()`);
  c.ok(!g.hidden && g.talkGrip, 'a grip between two open docks (none on the first)', g);
  const h0 = await hs();
  await page.cmd('Input.dispatchMouseEvent', { type: 'mouseMoved', x: g.x, y: g.y });
  await page.cmd('Input.dispatchMouseEvent', { type: 'mousePressed', x: g.x, y: g.y, button: 'left', clickCount: 1 });
  for (let i = 1; i <= 5; i++) await page.cmd('Input.dispatchMouseEvent', { type: 'mouseMoved', x: g.x, y: g.y + 16 * i, button: 'left', buttons: 1 });
  await page.cmd('Input.dispatchMouseEvent', { type: 'mouseReleased', x: g.x, y: g.y + 80, button: 'left', clickCount: 1 });
  const h1 = await hs();
  c.ok(Math.abs(h1[0] - h0[0] - 80) <= 3 && Math.abs(h0[1] - h1[1] - 80) <= 3, 'dragged 80 px down: TALK grows, HIERARCHY shrinks by as much', [h0, h1]);
  c.ok(await ev(`Math.round(world.docks.state.talk.size) === ${h1[0]} && JSON.parse(localStorage.getItem('worldpage.docks.v4')).talk.size > 0`), 'the sizes kept with the layout', await ev(`JSON.stringify(world.docks.state)`));
  await page.goto('web/world.html');
  c.ok(JSON.stringify(await hs()) === JSON.stringify(h1), 'and after a reload', [h1, await hs()]);
  await ev(`document.querySelector('#dock-hierarchy > .dgrip').dispatchEvent(new MouseEvent('dblclick', { bubbles: true }))`);
  c.ok(await ev(`!world.docks.state.talk.size && !world.docks.state.hierarchy.size`), 'a double click on a grip: equal again', await ev(`JSON.stringify(world.docks.state)`));

  // the splitter keeps a share of the row: a smaller window (another monitor) keeps the proportion, the map refits
  const sp = await ev(`(() => { const r = document.getElementById('split').getBoundingClientRect(); return { x: r.x + r.width / 2, y: r.y + 200 }; })()`);
  await page.cmd('Input.dispatchMouseEvent', { type: 'mouseMoved', x: sp.x, y: sp.y });
  await page.cmd('Input.dispatchMouseEvent', { type: 'mousePressed', x: sp.x, y: sp.y, button: 'left', clickCount: 1 });
  await page.cmd('Input.dispatchMouseEvent', { type: 'mouseMoved', x: sp.x - 150, y: sp.y, button: 'left', buttons: 1 });
  await page.cmd('Input.dispatchMouseEvent', { type: 'mouseReleased', x: sp.x - 150, y: sp.y, button: 'left', clickCount: 1 });
  const share = () => ev(`(() => { const L = document.getElementById('left'), m = L.parentElement; return [L.style.flex, L.getBoundingClientRect().width / m.getBoundingClientRect().width, getComputedStyle(document.getElementById('map')).getPropertyValue('--wm-z')]; })()`);
  const s1 = await share();
  c.ok(/%$/.test(s1[0]), 'the splitter sets a share (%), not pixels', s1);
  await page.cmd('Emulation.setDeviceMetricsOverride', { width: 900, height: 700, deviceScaleFactor: 1.5, mobile: false });
  await sleep(400);
  const s2 = await share();
  c.ok(Math.abs(s2[1] - s1[1]) < 0.02 && s2[2] !== s1[2], 'a smaller window, another scale: the same share, the map refitted', [s1, s2]);
  await page.cmd('Emulation.clearDeviceMetricsOverride');
  await ev(`document.getElementById('split').dispatchEvent(new MouseEvent('dblclick', { bubbles: true }))`);
  await ev(`(() => { world.panel.core.listening = false; world.panel.core.changed(); world.narrator._set('stopped'); })()`);
  c.ok(await ev(`!document.querySelector('#talkpanel .fw-mic') && document.querySelector('#voice .fw-switch').getAttribute('role') === 'switch'`),
    'the mic is the band\'s switch, not the text line\'s button', null);

  // 1. the person's words, the typed J
  await stepTo(`[...document.querySelectorAll('#talkpanel .fw-log li')].some(l => l.textContent.includes('put a tomato in the microwave'))`);
  c.ok(await ev(`[...document.querySelectorAll('#jlog li')].some(l => l.textContent.includes('put a tomato in the microwave'))`),
    'the person\'s words are in the band and the journal', null);

  // 2. the director wakes nav: the hierarchy shows it attending, the task active
  await stepTo(`document.querySelector('#hlist li[data-domain="nav"].att')`);
  c.ok(await ev(`document.querySelector('#hlist li[data-domain="task"]').classList.contains('on') && document.querySelector('#hlist li[data-domain="nav"] .st').textContent === 'attending'`),
    'the director woke nav: nav attending, the task active', await ev(`document.getElementById('hlist').textContent.replace(/\\s+/g, ' ')`));

  // 3. nav goes: the agent stands on countertop 3
  await stepTo(`world.map.map.agent.pos + '' === world.map.map.entities.find(e => e.id === 'countertop3').pos + ''`);
  const at = await ev(`(() => { const s = e => document.querySelector(e).style; const a = s('#map .wm-agent'), p = s('#map [data-id="countertop3"]');
    return [a.getPropertyValue('--x') === p.getPropertyValue('--x') && a.getPropertyValue('--y') === p.getPropertyValue('--y'), world.at]; })()`);
  c.ok(at[0], 'world/delta: the agent is drawn on countertop 3', at);

  // 4. grasp takes: the agent holds the tomato, the countertop has one thing less
  const before = await ev(`world.map.map.entities.find(e => e.id === 'countertop3').items.length`);
  await stepTo(`(world.map.map.agent.holding || '') === 'tomato 1'`);
  c.ok(await ev(`document.querySelector('#map .wm-agent').getAttribute('aria-label') === 'the agent, holding tomato 1'`)
    && (await ev(`world.map.map.entities.find(e => e.id === 'countertop3').items.length`)) === before - 1,
    'the agent holds tomato 1 and countertop 3 lost it', null);

  // 5. access opens the microwave; place puts the tomato in; the end
  c.ok(await stepTo(`world.map.map.entities.find(e => e.id === 'microwave1').closed === false`)
    && !(await ev(`document.querySelector('#map [data-id="microwave1"]').getAttribute('aria-label')`)).includes('closed'), 'access opened the microwave', null);
  await ev(`world.stepAll()`);
  const end = await ev(`({ hstate: document.getElementById('hstate').textContent, items: world.map.map.entities.find(e => e.id === 'microwave1').items,
    holding: world.map.map.agent.holding, said: [...document.querySelectorAll('#talkpanel .fw-log li')].map(l => l.textContent),
    journal: document.getElementById('jlog').textContent })`);
  c.ok(end.hstate === 'ended: done' && end.items.includes('tomato 1') && !end.holding, 'the end: done, the tomato in the microwave', end);
  c.ok(end.said.some(s => s.includes('Tomato 1 is in microwave 1: done.')) && end.said.some(s => s.includes('I open microwave 1.')),
    'every result\'s own line spoken in the band', end.said.slice(-4));
  c.ok(end.journal.includes('activate nav') && end.journal.includes('deactivate place'), 'the journal has the activations', null);
  const rows = await ev(`[...document.querySelectorAll('#jlog li')].map(l => l.textContent.replace(/\\s+/g, ' ').trim())`);
  c.ok(rows.includes('· → c1 FETCH object=TOMATO1 receptacle=MICROWAVE1') && !rows.some(r => /undefined|\[object Object\]/.test(r)),
    'the journal shows the typed intent as its name and args, nothing undefined', rows.slice(0, 3));

  // 6. the hierarchy's task row opens the task card: the words, the goal, the chain, the lines
  await page.mouse('#hlist li[data-domain="task"]');
  const card = await ev(`({ open: document.querySelector('#map .wm-task').open, text: document.querySelector('#map .wm-card').textContent,
    chain: document.querySelectorAll('#map .wm-chain li').length })`);
  c.ok(card.open && card.text.includes('Put a tomato in the microwave.') && card.text.includes('fetch(tomato1, microwave1)') && card.chain === 6
    && card.text.includes('Tomato 1 is in microwave 1: done.'), 'the task card: the words, the goal, the six steps, the lines', card);
  await page.key('Escape');
  c.ok(await ev(`!document.querySelector('#map .wm-task').open`), 'Escape closes it', null);

  // 7. no voice navigation: no port, no world_ui claim, no nav markup
  c.ok(await ev(`!('port' in world) && !document.querySelector('[data-w], [data-port-off]') && !world.log.some(r => r.dir === 'port')`),
    'the page is the game\'s alone: no ui port, no nav markup', null);
  // the architect's ruling (b): the cards are tools — a header click folds nothing, "go to Talk" lands at once; ✕ hides
  await page.mouse('#dock-talk > header .tt');
  c.ok(await ev(`document.getElementById('dock-talk').classList.contains('open') && !document.querySelector('#dock-talk .tw').textContent
    && getComputedStyle(document.querySelector('#dock-talk > header')).cursor === 'default'`), 'a dock\'s header folds nothing (no ▾, no pointer)', null);
  await page.mouse('#dock-journal > header .x');
  c.ok(await ev(`document.getElementById('dock-journal').hidden`), '✕ hides it', null);
  await page.mouse('[data-strip="journal"]');
  c.ok(await ev(`document.getElementById('dock-journal').classList.contains('open')`), 'the strip shows it again, open', null);

  // 7b. the world card (the user: "I did not know what to ask"): what this world is, its room and things by kind, what to ask
  const wc = await ev(`({ title: document.querySelector('#wcard .wc-title')?.textContent, room: document.querySelectorAll('#wcard .wc-kinds')[0]?.querySelectorAll('.wc-kind').length,
    things: document.querySelectorAll('#wcard .wc-kinds')[1]?.querySelectorAll('.wc-kind').length,
    cab: [...document.querySelectorAll('#wcard .wc-kind summary')].map(x => x.textContent.replace(/\\s+/g, ' ').trim()).find(t => t.startsWith('cabinet')),
    asks: [...document.querySelectorAll('#wcasks .chip')].map(b => b.textContent), cannot: document.querySelectorAll('#wcard .wc-cannot li').length,
    src: document.querySelector('#wcard .wc-src')?.textContent, strip: !!document.querySelector('[data-strip="world"]') })`);
  c.ok(wc.title === 'ALFWorld kitchen 13' && wc.room === 10 && wc.things === 24 && wc.cab.startsWith('cabinet × 26') && wc.cab.endsWith('opens') && wc.cannot === 3
    && wc.src.startsWith('generated from the game') && wc.strip && wc.asks[0] === 'put a tomato in the microwave' && wc.asks.includes('new game'),
    'the world card: its title, the room and the things by kind × count, the asks, what it cannot, the source', wc);
  c.ok(await ev(`document.getElementById('dock-world').classList.contains('open')`), 'the WORLD CARD dock: shown, so open (a tool, not folded)', null);
  await page.mouse('#wcasks .chip');
  c.ok(await ev(`[...document.querySelectorAll('#talkpanel .fw-person .fw-text')].some(t => t.textContent === 'put a tomato in the microwave')`),
    'an ask\'s chip says it, as typing it would', null);
  // small talk is talk: no "meant" row for a CHITCHAT intent, an errand's intent row stays
  await ev(`(() => { world.panel.core.row({ who: 'intent', text: '{"intent":"CHITCHAT"}' }); world.panel.core.row({ who: 'intent', text: '{"intent":"UNKNOWN"}' }); })()`);
  c.ok(await ev(`(() => { const r = [...document.querySelectorAll('#talkpanel .fw-intent')].slice(-2); return r[0].hidden && !r[1].hidden && r[1].querySelector('.fw-text').textContent === 'unknown'; })()`),
    'small talk: no "meant" row; an unknown errand keeps its row', null);
  await ev(`world.frame({ ev: 'world/status', state: 'waiting', text: 'Tell me a task.' })`);
  c.ok(await ev(`[...document.querySelectorAll('#sopts .chip')].some(b => b.textContent === 'what can I ask?')`), 'waiting offers "what can I ask?"', null);
  await ev(`world.docks.set('world', { shown: false })`);
  await page.mouse('#sopts .chip:last-child');
  c.ok(await ev(`document.getElementById('dock-world').classList.contains('open')`), '…which opens the world card', null);
  c.ok(await ev(`[...document.querySelectorAll('#talkpanel .fw-person .fw-text')].some(t => t.textContent === 'what can I ask?')`),
    '…and says it, as typing it would (the agent answers with the card\'s line)', null);
  c.ok(await ev(`!document.getElementById('ctrl').hidden`), 'a replay shows play / step', null);

  // 8. the disengagement: the fridge is not where this task wants the tomato
  await page.goto('web/world.html?replay=fixtures/alfworld_tomato_microwave_13_fridge.run.jsonl');
  await ev(`world.stepAll()`);
  const d = await ev(`({ said: [...document.querySelectorAll('#talkpanel .fw-log li')].map(l => l.textContent),
    red: document.querySelector('#map [data-id="fridge1"]').classList.contains('wm-cornered'), hstate: document.getElementById('hstate').textContent,
    chips: [...document.querySelectorAll('#askopts .chip')].map(b => b.textContent), asking: !document.getElementById('ask').hidden
      && [...document.querySelectorAll('#talkpanel .fw-ask .fw-who')].some(w => w.textContent === 'asks') })`);
  c.ok(d.said.some(s => s.includes('Fridge 1 is not where this task wants tomato 1.') && !s.includes('|')) && d.red && d.hstate === 'ended: wrong_dest'
    && d.chips.join(' / ') === 'put tomato 1 in microwave 1 / stop' && d.asking,
    'the disengagement: the band asks, the fridge in red, the hierarchy ended on wrong_dest', d);

  // 8b. view mode (semantic-map step 3): the page draws what the robot knows — a place not looked into is
  // marked where it stands (its things hidden), and unmarked as the robot looks into it
  const v = await ev(`(async () => {
    const sem = await (await fetch(world.mapUrl)).json();
    sem.view = true;
    for (const p of sem.places) p.unseen = p.id !== 'countertop3';
    await world.map.load(sem, world.mapUrl);
    const el = id => document.querySelector('#map [data-id="' + id + '"]'), ent = id => world.map.map.entities.find(e => e.id === id);
    const pos = ent('fridge1').pos + '';
    const before = { dim: el('fridge1').classList.contains('wm-unseen'), seen: !el('countertop3').classList.contains('wm-unseen'),
      hidden: ent('fridge1').items.length === 0, shown: ent('countertop3').items.length > 0 };
    world.frame({ ev: 'world/delta', entities: [{ id: 'fridge1', unseen: false, items: ['tomato 1'] }] });
    return { ...before, lit: !el('fridge1').classList.contains('wm-unseen'), items: ent('fridge1').items, still: ent('fridge1').pos + '' === pos };
  })()`);
  c.ok(v.dim && v.seen && v.hidden && v.shown && v.lit && v.items.join() === 'tomato 1' && v.still,
    'view mode: a place not looked into is marked in place, its things hidden; a seen one not; unmarked when looked into', v);
  const u = await ev(`(() => {
    const b = document.querySelector('#map [data-id="fridge1"]');
    const sem = world.map.map, g = document.querySelector('#gameinfo .gi-intro');
    return { opacity: getComputedStyle(b).opacity, intro: g && g.textContent, jsave: document.querySelector('#dock-journal #jsave')?.textContent };
  })()`);
  c.ok(u.opacity === '1', 'view mode: a place the opening text names is not dimmed', u.opacity);
  c.ok(/^You are in the middle of a room\./.test(u.intro || '') && !/_bar_/.test(u.intro), 'the room\'s opening text under its description', u.intro);
  c.ok(u.jsave === 'save (JSONL)', 'the journal saves its records', u.jsave);

  // 8c. the house (rooms step 2): the picker shows the rooms the agent keeps, the rest behind "choose another"; a move
  // needs no reload; the world card names the places looked into
  const h = await ev(`(async () => {
    const real = window.fetch, games = { current: 'k2', rooms: true, house: ['k2', 'b1'], games: [
      { id: 'k2', label: 'kitchen 2', room: 'kitchen', split: 'train' }, { id: 'k3', label: 'kitchen 3', room: 'kitchen', split: 'train' },
      { id: 'b1', label: 'bathroom 1', room: 'bathroom', split: 'train' }] };
    window.fetch = (u, o) => String(u).endsWith('world/games.json') ? Promise.resolve(new Response(JSON.stringify(games))) : real(u, o);
    window.__stayed = true;
    await world.frame({ ev: 'world/room', game: 'k2' });
    const sel = document.querySelector('#game'), all = document.querySelector('#gameall');
    const before = { house: [...sel.options].map(o => o.textContent), value: sel.value, hidden: all.hidden };
    sel.value = ''; sel.dispatchEvent(new Event('change'));
    const after = { hidden: all.hidden, groups: [...all.querySelectorAll('optgroup')].map(g => g.label), every: all.options.length, back: sel.value };
    const sem = await (await real(world.mapUrl)).json();
    sem.card = { ...(sem.card || {}), looked: ['fridge 1', 'countertop 2'] };
    await world.map.load(sem, world.mapUrl);
    world.frame({ ev: 'world/map', url: world.mapUrl }).catch(() => {});
    return { before, after };
  })()`);
  c.ok(h.before.house.join() === 'kitchen 2,bathroom 1,choose another room…' && h.before.value === 'k2' && h.before.hidden,
    'the picker shows the house and "choose another"', h.before);
  c.ok(!h.after.hidden && h.after.every === 3 && h.after.groups.join() === 'kitchen,bathroom' && h.after.back === 'k2',
    '"choose another" opens every room, grouped; the house stays on the current room', h.after);
  c.ok(await ev(`window.__stayed === true`), 'a room change does not reload the page', null);
  // nina's F2: a refused door gives the status line back, not "moving"
  const m = await ev(`(async () => {
    world.frame({ ev: 'world/status', state: 'done', text: 'Done. Tell me another task.' });
    await world.frame({ ev: 'world/loading', game: 'b1' });
    const moving = document.querySelector('#sstate').textContent;
    await world.frame({ ev: 'load_game_ack', game: 'b1', error: 'I am holding candle 1: tell me where to put it down first.' });
    return { moving, after: document.querySelector('#sstate').textContent, text: document.querySelector('#stext').textContent, value: document.querySelector('#game').value };
  })()`);
  c.ok(m.moving === 'moving' && !/moving/i.test(m.after) && /Done/.test(m.text) && m.value === 'k2', 'a refused door: the status is the agent\'s again, the picker back', m);

  // 9. at phone width the page does not scroll sideways
  await page.cmd('Emulation.setDeviceMetricsOverride', { width: 390, height: 844, deviceScaleFactor: 2, mobile: true });
  await sleep(300);
  const w = await ev(`[document.documentElement.scrollWidth, document.documentElement.clientWidth]`);
  c.ok(w[0] <= w[1], 'at 390 px: no horizontal scroll', w);

  // 10. live: play / step are the replay's, hidden (nothing to step); here no agent listens
  await page.goto('web/world.html?agent=ws://127.0.0.1:9/ws');
  await sleep(500);
  c.ok(await ev(`document.getElementById('ctrl').hidden`), 'live: no play / step', null);
} catch (e) {
  c.fail(e);
} finally {
  await page.close();
}
c.done();
