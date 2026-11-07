// loopgrammar.js — the road page's one voice, redirected (loop-road-ui s-0314a8ee, brief §1.3): a heard or typed line that is the
// LOOP's (or the events' on this page) is routed here, deterministically and at 0 USD; anything else stays the road's (drive, stop, follow,
// add a car, the questions to the agent). No model: a keyword table, the words' remainder as WORDS.
//
//   route(text, ctx) → null (the road's) | {to: 'loop', line} (a line for the pi CHAT: "/…" at 0 USD, else pi's, paid)
//                      | {to: 'page', action, n?, words?} (the page's events: mark, endmark, narrate, explain, send, continue; scenario: run one)
//                      | {to: 'gate', answer} (the loop's open gate answered)
//   ctx: {loopMark: the last narrated loop mark number | null, gate: a gate is open, paused: the run waits on a surprise,
//         scenarios: the SCENARIOS tree's names (towns and cards): "load NAME" → {to: 'page', action: 'scenario', name}}

const norm = t => String(t ?? '').toLowerCase().replace(/[’']/g, "'").replace(/[.!?]+$/, '').replace(/\s+/g, ' ').trim();
const rest = (raw, re) => raw.replace(re, '').replace(/[.!?]+$/, '').trim();   // the person's own words, as said
const num = s => (s == null ? undefined : Number(s));

// [pattern, (match, ctx, raw) → route | null]; the first that answers wins
export const TABLE = [
  [/^\/(.+)$/, (m, c, raw) => ({ to: 'loop', line: raw.trim() })],                                      // typed: a command, as it is
  [/^(?:loop|pi)[,:]?\s+(.+)$/, (m, c, raw) => ({ to: 'loop', line: raw.trim().replace(/^(?:loop|pi)[,:]?\s+/i, '') })],   // addressed to the loop
  [/^(?:end|stop|close) (?:the )?(?:mark|event)(?:[,:]?\s+(.*))?$/, (m, c, raw) => ({ to: 'page', action: 'endmark', words: rest(raw, /^\s*\S+\s+(?:the\s+)?(?:mark|event)[,:.]?\s*/i) })],
  [/^mark(?: (?:it|here|this|now|an event|the event|event))?$/, () => ({ to: 'page', action: 'mark' })],
  [/^narrate(?: (?:it|this|that|the event|event (\d+)))?$/, m => ({ to: 'page', action: 'narrate', n: num(m[1]) })],
  [/^explain(?: (?:it|this|that|the event|event (\d+)))?$/, m => ({ to: 'page', action: 'explain', n: num(m[1]) })],
  [/^send (?:it|this|that|the event|event (\d+)) to (?:pi|the loop|the pi loop)$/, m => ({ to: 'page', action: 'send', n: num(m[1]) })],
  [/^(?:agree|i agree|yes,? that(?:'s| is) what i saw)$/, (m, c) => (c.loopMark ? { to: 'loop', line: `/agree ${c.loopMark}` } : null)],
  [/^disagree(?:[,:]?\s+(.*))?$/, (m, c, raw) => (c.loopMark ? { to: 'loop', line: `/disagree ${c.loopMark} ${(raw.replace(/^\s*disagree[,:]?\s*/i, '') || 'not what I saw').trim()}` } : null)],
  [/^take (?:it|the next surprise|the surprise)$/, () => ({ to: 'loop', line: '/take' })],
  [/^why ([a-z_][a-z0-9_]*(?:\([^)]*\))?)$/, m => (/[_(]/.test(m[1]) ? { to: 'loop', line: `/why ${m[1]}` } : null)],   // an atom named: 0 USD
  [/^why (?:did|does|is|was|do) (?:it|the car|the ego|you|we)\b.*$/, (m, c, raw) => ({ to: 'loop', line: raw.trim() })],   // the question in words: pi's, paid
  [/^what did you change$/, () => ({ to: 'loop', line: '/diff' })],
  [/^show (?:me )?the ruling$/, () => ({ to: 'loop', line: '/ruling' })],
  [/^apply(?: (?:it|the ruling|the fix|the correction))?$/, () => ({ to: 'loop', line: '/apply' })],
  [/^(confirm|refuse)$/, (m, c) => (c.gate ? { to: 'gate', answer: m[1] } : null)],
  [/^(rebuild|reload)$/, m => ({ to: 'loop', line: `/${m[1]}` })],
  [/^(?:loop status|status of the loop)$/, () => ({ to: 'loop', line: '/status' })],
  [/^stop the loop$/, () => ({ to: 'loop', line: '/stop' })],
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
