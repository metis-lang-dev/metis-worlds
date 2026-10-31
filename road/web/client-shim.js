// client-shim.js — sumo-web3d's built client on the road's frames, loaded before its bundle in client.html (road-agent s-357becc7, steps/step0-report.md):
// its websocket and its fetches are answered here, from what world.js posts (world/net, world/scene); its backend and its SUMO are never started.
const json = o => new Response(JSON.stringify(o), { status: 200, headers: { 'Content-Type': 'application/json' } });
let gotNet;
const net = new Promise(r => { gotNet = r; });
const realFetch = window.fetch.bind(window);
window.fetch = (u, opt) => {
  const p = String(u);
  if (p.endsWith('/state')) return Promise.resolve(json({ scenario: 'road', simulationStatus: 'running', delayMs: 100 }));
  if (p.endsWith('/scenarios')) return Promise.resolve(json([{ displayName: 'the road', kebabCase: 'road' }]));
  if (p.endsWith('network')) return net.then(json);
  if (p.endsWith('water')) return Promise.resolve(json({ type: 'FeatureCollection', features: [] }));
  if (p.endsWith('additional') || p.endsWith('settings')) return Promise.resolve(new Response('', { status: 404 }));
  if (p.includes('/vehicle_route')) return Promise.resolve(json([]));
  return realFetch(u, opt);
};
// the bundle names its assets from the server's root; they stay in the fetched copy
const HOME = '/vendor/sumo-web3d';
const asset = u => (typeof u === 'string' && /^\/(vehicles|arrows|sky)\/|^\/(zebra\.jpg|sidewalk256\.jpg|rail64\.png|asphalt256\.jpg)$/.test(u) ? HOME + u : u);
const xhrOpen = XMLHttpRequest.prototype.open;
XMLHttpRequest.prototype.open = function (m, u, ...more) { return xhrOpen.call(this, m, asset(u), ...more); };
const imgSrc = Object.getOwnPropertyDescriptor(HTMLImageElement.prototype, 'src');
Object.defineProperty(HTMLImageElement.prototype, 'src', { get() { return imgSrc.get.call(this); }, set(u) { imgSrc.set.call(this, asset(u)); } });

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

// the truth's x, y are the centre and its heading radians from +x; the client's are the front bumper and SUMO's degrees from north
const info = m => ({ x: m.x + m.length / 2 * Math.cos(m.heading), y: m.y + m.length / 2 * Math.sin(m.heading), z: 0, speed: m.speed,
  angle: 90 - m.heading * 180 / Math.PI, type: 'passenger', length: m.length, width: m.width, signals: m.signals, vehicle: null, vClass: m.class });
let last = {};
function snapshot(scene) {
  const creations = {}, updates = {}, now = {};
  for (const m of scene.movers) { now[m.id] = info(m); (last[m.id] ? updates : creations)[m.id] = now[m.id]; }
  const removals = Object.keys(last).filter(k => !now[k]);
  last = now;
  return { type: 'snapshot', time: scene.t * 1000, vehicles: { creations, updates, removals }, lights: { creations: {}, updates: {}, removals: [] },
    vehicle_counts: { passenger: scene.movers.length }, simulate_secs: 0, snapshot_secs: 0 };
}

addEventListener('message', e => {
  if (e.origin !== location.origin) return;
  if (e.data.net) gotNet(e.data.net);
  if (e.data.scene && socket) socket.deliver(snapshot(e.data.scene));
  if (e.data.follow) window.sumoFollow(e.data.follow);
  if (e.data.unfollow) window.sumoUnfollow();
});

// the bundle, as fetched and unmodified on disk, run with its follow functions in reach (the bundle keeps them to its sidebar's buttons, and the ego has no look of its own to click)
realFetch(`${HOME}/index.bundle.js`).then(r => r.text()).then(code => {
  const script = document.createElement('script');
  script.text = code.replace('function followObjectPOV(vehicleId) {', 'window.sumoFollow = followObjectPOV; window.sumoUnfollow = unfollowObjectPOV;\nfunction followObjectPOV(vehicleId) {');
  document.body.appendChild(script);
});
