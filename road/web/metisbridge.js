// metisbridge.js — the road page's link to the Metis bridge (metis-plugin s-df4ff191 step 4): the plugin's MCP server, where Claude Code
// works the workspace, listens on loopback when Claude Code enables it (bridge_enable); the page is opened with ?metis=URL&token=T.
// IN: an event sent to Metis (a surprise: its window of this page's own trace, the tester's words) or asked about (explain: a question
// Claude Code answers). OUT: the feed, pushed: the surprise's life (open -> taken -> ruled VERDICT -> applied), an explain's answer, and
// 'the catalog changed'. No bridge (no ?metis, or not answering): the page says so where it is asked, never silently.
//
//   const metis = new MetisBridge({url, token, onFrame(f), onState(up)})
//   metis.up                          the feed is connected
//   await metis.surprise({run, window, words, member?, kind, n, scenario?, seed?, t0?, t1?})  -> {id, trace, member}
//   await metis.explain({run, window, words, member?, n})                                     -> {ref}
//   metis.event({n, edge, k0?, k1?, run?, words?})   a record only, fire and forget

export function bridgeFrom(q) {                       // ?metis=http://127.0.0.1:8790&token=T (the token as Claude Code's bridge_enable printed it)
  const url = q.get('metis');
  return url ? { url: url.replace(/\/$/, ''), token: q.get('token') || q.get('metis_token') || '' } : null;
}

export class MetisBridge {
  constructor({ url, token, onFrame, onState }) {
    Object.assign(this, { url, token, onFrame: onFrame || (() => {}), onState: onState || (() => {}), up: false, since: 0, ws: null, closed: false });
    if (url) this.open();
  }

  get on() { return !!this.url; }

  open() {
    if (this.closed) return;
    const w = this.url.replace(/^http/, 'ws') + `/feed/ws?token=${encodeURIComponent(this.token)}&since=${this.since}`;
    let ws;
    try { ws = new WebSocket(w); } catch { return this.retry(); }
    this.ws = ws;
    ws.onopen = () => { this.up = true; this.onState(true); };
    ws.onmessage = e => {
      let f;
      try { f = JSON.parse(e.data); } catch { return; }
      if (typeof f.seq === 'number') this.since = Math.max(this.since, f.seq);
      this.onFrame(f);
    };
    ws.onclose = () => { const was = this.up; this.up = false; if (was) this.onState(false); this.retry(); };
  }

  retry() { if (!this.closed) setTimeout(() => this.open(), 3000); }
  close() { this.closed = true; this.ws?.close(); }

  async post(path, body) {
    if (!this.url) throw new Error('the Metis bridge is off: enable it in Claude Code (bridge_enable) and open this page with ?metis=URL&token=T');
    let r;
    try {
      r = await fetch(this.url + path, { method: 'POST', headers: { 'content-type': 'application/json', 'X-Metis-Token': this.token }, body: JSON.stringify(body) });
    } catch {
      throw new Error(`the Metis bridge at ${this.url} is not answering: is Claude Code's bridge enabled?`);
    }
    const j = await r.json().catch(() => ({}));
    if (!r.ok || j.ok === false) throw new Error(j.error || `the Metis bridge said ${r.status}`);
    return j;
  }

  surprise(b) { return this.post('/surprise', b); }
  explain(b) { return this.post('/explain', b); }
  event(b) { if (this.url) this.post('/event', b).catch(() => {}); }
}
