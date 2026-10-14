/* LiveSocket — one WebSocket that keeps itself alive. Depends on api.js.

   A WebSocket is never permanent: deploys, proxies recycling idle lines,
   sleeping laptops and Wi-Fi changes all cut it. So instead of hoping the
   line stays up, this class makes drops invisible:

   - Heartbeat: a {"type":"ping"} every 20 s; the server answers "pong". The
     traffic keeps proxies from treating the line as idle, and any message
     counts as proof of life. Silence for 45 s means the line is dead even if
     the browser hasn't noticed ("zombie"), so it's closed and reopened.
   - Quiet reconnects: the UI only hears "reconnecting" if the line isn't back
     within 2.5 s, so a blip never shows.
   - Never gives up: backoff 0.5 s → 30 s with jitter (so tabs don't all
     reconnect at the same instant after a deploy); "offline" after a minute
     of failing, but it keeps trying, and tries at once when the network or
     the tab comes back.
   - Auth: a token about to expire is refreshed before connecting, and a
     4001 close (token refused) refreshes and reopens, every time it happens.
     4003 / 4004 (not allowed / not found) are final.

   new LiveSocket('/ws/chat/<slug>/', {
     onOpen({ restored, noticed }),   // restored: reconnect; noticed: UI saw it drop
     onMessage(msg),                  // parsed JSON; pings/pongs are filtered out
     onState(state),                  // connecting | live | reconnecting | offline | denied
     onDenied(code),
   })                                                                          */

const LS_PING_EVERY    = 20000;
const LS_DEAD_AFTER    = 45000;
const LS_QUIET_FOR     = 2500;
const LS_OFFLINE_AFTER = 60000;
const LS_BACKOFF_MIN   = 500;
const LS_BACKOFF_MAX   = 30000;
const LS_FINAL_CODES   = new Set([4003, 4004]);

class LiveSocket {
  constructor(path, handlers = {}) {
    this.path = path;
    this.h = handlers;
    this.ws = null;
    this.state = null;
    this._attempt = 0;
    this._everOpen = false;
    this._noticed = false;      // did the UI see this outage?
    this._downSince = 0;
    this._closed = false;
    this._timers = {};

    this._onOnline     = () => this.retryNow();
    this._onVisibility = () => { if (!document.hidden) this._checkOnReturn(); };
    window.addEventListener('online', this._onOnline);
    document.addEventListener('visibilitychange', this._onVisibility);

    this._setState('connecting');
    this._open();
  }

  get isOpen() { return this.ws?.readyState === WebSocket.OPEN; }

  send(payload) {
    if (!this.isOpen) return false;
    this.ws.send(JSON.stringify(payload));
    return true;
  }

  /** Reconnect now instead of waiting out the backoff (Retry button, network back). */
  retryNow() {
    if (this._closed || this.isOpen || this.state === 'denied') return;
    if (this.ws?.readyState === WebSocket.CONNECTING) return;   // already on its way
    this._attempt = 0;
    this._clear('retry');
    this._drop();
    this._open();
  }

  /** For good: the panel is going away. */
  close() {
    this._closed = true;
    Object.keys(this._timers).forEach((k) => this._clear(k));
    window.removeEventListener('online', this._onOnline);
    document.removeEventListener('visibilitychange', this._onVisibility);
    this._drop();
  }

  // ── Internals ──────────────────────────────────────────────────────────

  _url() {
    const proto = location.protocol === 'https:' ? 'wss' : 'ws';
    const sep = this.path.includes('?') ? '&' : '?';
    // The current token every time: it may have been refreshed since the last try.
    return `${proto}://${location.host}${this.path}${sep}token=${encodeURIComponent(getAccessToken() || '')}`;
  }

  async _open() {
    if (this._closed) return;
    // An expired token would only be refused: refresh it first.
    if (accessTokenExpiring() && getRefreshToken()) {
      await _tryRefresh();
      if (this._closed) return;
    }
    let ws;
    try { ws = new WebSocket(this._url()); } catch { this._scheduleRetry(); return; }
    this.ws = ws;

    ws.onopen = () => {
      if (this.ws !== ws) return;
      const restored = this._everOpen;
      const noticed  = this._noticed;
      this._everOpen = true;
      this._attempt = 0;
      this._noticed = false;
      this._downSince = 0;
      this._clear('quiet');
      this._clear('offline');
      this._setState('live');
      this._heard();
      this._timers.ping = setInterval(() => this.send({ type: 'ping' }), LS_PING_EVERY);
      this.h.onOpen?.({ restored, noticed });
    };

    ws.onmessage = (e) => {
      if (this.ws !== ws) return;
      this._heard();
      let msg;
      try { msg = JSON.parse(e.data); } catch { return; }
      if (msg.type === 'pong' || msg.type === 'ping') return;
      this.h.onMessage?.(msg);
    };

    ws.onclose = (e) => {
      if (this.ws !== ws) return;
      this._onClose(e.code, e.reason);
    };
  }

  async _onClose(code, reason) {
    this._clear('ping');
    this._clear('dead');
    this.ws = null;
    if (this._closed) return;
    console.info(`[socket] ${this.path} closed: code ${code}${reason ? ` (${reason})` : ''}`);

    if (code === 4001) {
      // Token expired or invalid: refresh, then reconnect with the new one.
      if (await _tryRefresh()) { this._attempt = 0; this._open(); return; }
      // Refresh token still there means the refresh itself couldn't get
      // through (network); keep trying. Gone means the session really ended.
      if (getRefreshToken()) { this._scheduleRetry(); return; }
      this._deny(code);
      return;
    }
    if (LS_FINAL_CODES.has(code)) { this._deny(code); return; }
    this._scheduleRetry();
  }

  _deny(code) {
    this._clear('quiet');
    this._clear('offline');
    this._setState('denied');
    this.h.onDenied?.(code);
  }

  _scheduleRetry() {
    if (this._closed) return;
    if (!this._downSince) {
      this._downSince = Date.now();
      // Tell the UI only if we're not back quickly.
      this._timers.quiet = setTimeout(() => {
        this._noticed = true;
        this._setState('reconnecting');
      }, LS_QUIET_FOR);
      this._timers.offline = setTimeout(() => {
        this._noticed = true;
        this._setState('offline');
      }, LS_OFFLINE_AFTER);
    }
    const base  = Math.min(LS_BACKOFF_MIN * 2 ** this._attempt, LS_BACKOFF_MAX);
    const delay = base * (0.7 + Math.random() * 0.6);
    this._attempt++;
    this._clear('retry');
    this._timers.retry = setTimeout(() => this._open(), delay);
  }

  // Any frame from the server proves the line is alive; silence means it isn't.
  _heard() {
    this._clear('dead');
    this._timers.dead = setTimeout(() => {
      console.info(`[socket] ${this.path}: no reply for ${LS_DEAD_AFTER / 1000}s, reconnecting`);
      this._drop();
      this._onClose(4000, 'heartbeat timeout');
    }, LS_DEAD_AFTER);
  }

  // After the tab was hidden (timers throttled, laptop asleep), don't trust
  // the line: ask for a pong now and reconnect at once if it's down.
  _checkOnReturn() {
    if (this.isOpen) this.send({ type: 'ping' });
    else this.retryNow();
  }

  _drop() {
    const ws = this.ws;
    this.ws = null;
    if (!ws) return;
    ws.onopen = ws.onmessage = ws.onclose = null;
    try { ws.close(); } catch { /* already closing */ }
  }

  _clear(name) {
    clearTimeout(this._timers[name]);
    clearInterval(this._timers[name]);
    delete this._timers[name];
  }

  _setState(state) {
    if (this.state === state) return;
    this.state = state;
    this.h.onState?.(state);
  }
}
