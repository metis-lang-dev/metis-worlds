// client-shim.js — sumo-web3d's built client on the road's frames, loaded before its bundle in client.html (road-agent s-357becc7, steps/step0-report.md):
// its websocket and its fetches are answered here, from what world.js posts (world/net, world/scene); its backend and its SUMO are never started.
const json = o => new Response(JSON.stringify(o), { status: 200, headers: { 'Content-Type': 'application/json' } });
let gotNet, gotAdd;
const net = new Promise(r => { gotNet = r; });
const add = new Promise(r => { gotAdd = r; });          // the additional shapes: a CommonRoad run's goal regions (world.js posts them with the net)
const realFetch = window.fetch.bind(window);
window.fetch = (u, opt) => {
  const p = String(u);
  if (p.endsWith('/state')) return Promise.resolve(json({ scenario: 'road', simulationStatus: 'running', delayMs: 100 }));
  if (p.endsWith('/scenarios')) return Promise.resolve(json([{ displayName: 'the road', kebabCase: 'road' }]));
  if (p.endsWith('network')) return net.then(json);
  if (p.endsWith('water')) return Promise.resolve(json({ type: 'FeatureCollection', features: [] }));
  if (p.endsWith('additional')) return add.then(a => a ? json(a) : new Response('', { status: 404 }));
  if (p.endsWith('settings')) return Promise.resolve(new Response('', { status: 404 }));
  if (p.includes('/vehicle_route')) return Promise.resolve(json([]));
  return realFetch(u, opt);
};
let socket = null;
class Socket {
  constructor() { socket = this; setTimeout(() => this.onopen && this.onopen({}), 0); }
  // the client's own buttons are the page's play and pause; its delay slider the page's speed
  send(s) {
    const m = JSON.parse(s);
    const state = { start: 'running', resume: 'running', pause: 'paused' }[m.action];
    if (state) { this.deliver({ type: 'state', scenario: 'road', simulationStatus: state, delayMs: 100 }); parent.postMessage({ client: m.action }, location.origin); }
    if (m.action === 'changeDelay') parent.postMessage({ client: 'delay', ms: m.delayLengthMs }, location.origin);
  }
  deliver(o) { if (this.onmessage) this.onmessage({ data: JSON.stringify(o) }); }
  close() {}
}
window.WebSocket = Socket;

// a map far from 0,0 (CommonRoad's own roads keep their UTM metres, x ~ 476000, y ~ 5556000): the client draws in float32,
// where such a map vanishes (the user, 2026-11-07: maps not loaded). The view's map moved to a local origin, its cars with it;
// the page and the road keep their own coordinates, only what is drawn here is shifted.
const FAR = 1e4;
let origin = [0, 0];
const shiftPts = (shape, [ox, oy]) => String(shape || '').trim().split(/\s+/).filter(Boolean)
  .map(p => { const c = p.split(','); c[0] = (Number(c[0]) - ox).toFixed(2); c[1] = (Number(c[1]) - oy).toFixed(2); return c.join(','); }).join(' ');
function localNet(doc) {
  const n = doc?.net, b = String(n?.location?.convBoundary || '').split(',').map(Number);
  if (b.length !== 4 || b.some(x => !Number.isFinite(x)) || Math.max(Math.abs(b[0]), Math.abs(b[1]), Math.abs(b[2]), Math.abs(b[3])) < FAR) { origin = [0, 0]; return doc; }
  const o = origin = [Math.floor(b[0]), Math.floor(b[1])];
  const sh = x => x == null ? x : shiftPts(x, o);
  return { ...doc, net: { ...n,
    location: { ...n.location, convBoundary: [b[0] - o[0], b[1] - o[1], b[2] - o[0], b[3] - o[1]].map(x => x.toFixed(2)).join(',') },
    edge: (n.edge || []).map(e => ({ ...e, ...(e.shape != null ? { shape: sh(e.shape) } : {}), lane: (e.lane || []).map(l => ({ ...l, shape: sh(l.shape) })) })),
    junction: (n.junction || []).map(j => ({ ...j, shape: sh(j.shape), x: (Number(j.x) - o[0]).toFixed(2), y: (Number(j.y) - o[1]).toFixed(2) })) } };
}
const localGoal = goal => (goal || []).map(p => p.map(([x, y]) => [x - origin[0], y - origin[1]]));

// the truth's x, y are the centre and its heading radians from +x; the client's are the front bumper and SUMO's degrees from north
const info = m => ({ x: m.x - origin[0] + m.length / 2 * Math.cos(m.heading), y: m.y - origin[1] + m.length / 2 * Math.sin(m.heading), z: m.z || 0, speed: m.speed,
  angle: 90 - m.heading * 180 / Math.PI, type: 'passenger', length: m.length, width: m.width, signals: m.signals, vehicle: null, vClass: m.class });
let last = {}, wanted = null;
const lastLights = {};
function snapshot(scene) {
  const creations = {}, updates = {}, now = {};
  for (const m of scene.movers) { now[m.id] = info(m); (last[m.id] ? updates : creations)[m.id] = now[m.id]; }
  const removals = Object.keys(last).filter(k => !now[k]);
  last = now;
  const lights = { creations: {}, updates: {}, removals: [] };
  for (const id in scene.lights || {}) {                // read only every so many ticks; the client's own creations hold the first
    const l = scene.lights[id], was = lastLights[id];
    if (!was) lights.creations[id] = l; else if (was.phase !== l.phase || was.programID !== l.programID) lights.updates[id] = l;
    lastLights[id] = l;
  }
  return { type: 'snapshot', time: scene.t * 1000, vehicles: { creations, updates, removals }, lights,
    vehicle_counts: { passenger: scene.movers.length }, simulate_secs: 0, snapshot_secs: 0 };
}

addEventListener('message', e => {
  if (e.origin !== location.origin) return;
  if (e.data.net) {
    gotNet(localNet(e.data.net));
    // the goal as a flat slab on the road: the client draws an additional polygon as a building, (levels + 0.5) x 3 m tall
    gotAdd(e.data.goal?.length ? { poly: localGoal(e.data.goal).map((p, i) => ({ id: `goal-${i}`, type: 'building', shape: p.map(([x, y]) => `${x},${y}`).join(' '),
      param: [{ key: 'building:levels', value: '-0.45' }] })) } : null);
  }
  if (e.data.scene && socket && socket.onmessage) socket.deliver(snapshot(e.data.scene));   // none before the client listens: it would miss a car's entry
  if (e.data.follow) wanted = e.data.follow;
  if (e.data.center && window.sumoCenter) window.sumoCenter(e.data.center);
  if (e.data.unfollow) { wanted = null; window.sumoUnfollow(); }
  if (wanted && last[wanted] && window.sumoFollow) { window.sumoFollow(wanted); wanted = null; }   // asked before the car is on the road: as soon as it is
});
