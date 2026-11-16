// pagegrammar.js — the road page's own lines (metis-plugin s-df4ff191 step 4: the pi loop's dock is gone, and its lines with it): a heard
// or typed line that is the page's EVENTS' (mark, end mark, narrate, explain, send to Metis, continue) or a scenario's name is routed here,
// deterministically and at 0 USD; anything else stays the road's (drive, stop, follow, add a car, the questions to the agent). No model:
// a keyword table, the words' remainder as WORDS.
//
//   route(text, ctx) → null (the road's) | {to: 'page', action, n?, words?, name?}
//                      actions: mark, endmark, narrate, explain, send, continue (a paused run), scenario (run one)
//   ctx: {paused: the run waits on a surprise, scenarios: the SCENARIOS tree's names}

const norm = t => String(t ?? '').toLowerCase().replace(/[’']/g, "'").replace(/[.!?]+$/, '').replace(/\s+/g, ' ').trim();
const rest = (raw, re) => raw.replace(re, '').replace(/[.!?]+$/, '').trim();   // the person's own words, as said
const num = s => (s == null ? undefined : Number(s));
const TO = '(?:metis|claude|the catalog|the loop|pi)';                  // "send it to Metis" (the loop's words still understood)

// [pattern, (match, ctx, raw) → route | null]; the first that answers wins
export const TABLE = [
  [/^\/?(narrate|explain)(?: event)? (\d+)$/, m => ({ to: 'page', action: m[1], n: num(m[2]) })],
  [new RegExp(`^\\/?send (?:event )?(\\d+) to ${TO}$`), m => ({ to: 'page', action: 'send', n: num(m[1]) })],
  [/^(?:end|stop|close) (?:the )?(?:mark|event)(?:[,:]?\s+(.*))?$/, (m, c, raw) => ({ to: 'page', action: 'endmark', words: rest(raw, /^\s*\S+\s+(?:the\s+)?(?:mark|event)[,:.]?\s*/i) })],
  [/^mark(?: (?:it|here|this|now|an event|the event|event))?$/, () => ({ to: 'page', action: 'mark' })],
  [/^narrate(?: (?:it|this|that|the event|event (\d+)))?$/, m => ({ to: 'page', action: 'narrate', n: num(m[1]) })],
  [/^explain(?: (?:it|this|that|the event|event (\d+)))?$/, m => ({ to: 'page', action: 'explain', n: num(m[1]) })],
  [new RegExp(`^send (?:it|this|that|the event|event (\\d+)) to ${TO}$`), m => ({ to: 'page', action: 'send', n: num(m[1]) })],
  [/^(?:continue|go on|resume)(?: the run)?$/, (m, c) => (c.paused ? { to: 'page', action: 'continue' } : null)],
  // a scenario by its name (the user typed "load DynamicObjectCrossing", 2026-11-07): one the SCENARIOS tree has, else the road's
  [/^(?:load|run|play|start|open)(?: the)?(?: scenario)? ([a-z0-9][\w.-]*)$/, (m, c) => {
    const name = (c.scenarios || []).find(s => String(s).toLowerCase() === m[1]);
    return name ? { to: 'page', action: 'scenario', name } : null;
  }],
];

export function route(text, ctx = {}) {
  const raw = String(text ?? '').trim(), t = norm(raw);
  if (!t) return null;
  for (const [re, f] of TABLE) {
    const m = t.match(re);
    if (m) { const r = f(m, ctx, raw); if (r) return r; }
  }
  return null;
}
