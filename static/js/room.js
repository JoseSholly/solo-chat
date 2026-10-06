/* Room panel — header, connection, presence, details drawer, and the room's
   WebSocket. Depends on api.js, auth.js, ui.js, dashboard.js, messages.js,
   composer.js. */

let _activePanel = null;

function destroyActivePanel() {
  if (_activePanel) { _activePanel.destroy(); _activePanel = null; }
}

function loadRoomPanel(room) {
  destroyActivePanel();
  _activePanel = new RoomPanel(room, document.getElementById('main-panel'));
}

const MAX_RECONNECTS = 6;

class RoomPanel {
  constructor(room, container) {
    this.room      = room;
    this.container = container;
    this.me        = getUser() || {};

    this.ws             = null;
    this.wsReady        = false;
    this.reconnectCount = 0;
    this._reconnectTimer = null;
    this._authRetried   = false;
    this._everConnected = false;
    this._destroyed     = false;
    this._markSeenTimer = null;
    this._lastRollCall  = 0;
    this._historyReady  = false;
    this._pending       = [];   // live messages that arrive before history renders

    this.online  = new Map();   // username → { display_name } — people connected right now
    this.members = new Map();   // username → member, as loaded for the drawer

    this._membersOffset   = 0;
    this._membersHasMore  = true;
    this._membersLoading  = false;
    this._membersObserver = null;
    this._drawer = null;
    this._profileLayer = null;

    this._render();

    this.messages = new MessageList(this._el.timeline, this._el.jump, {
      onOpenProfile: (u) => this._showProfile(u),
      onSeen:        () => this._markSeen(),
    });

    this.composer = new Composer(this._el.composer, {
      roomSlug:   room.slug,
      roomName:   room.name,
      dropTarget: this._el.root,
      onSendText: (content) => this._sendText(content),
      onUploaded: (msg) => this._onChatMessage(msg),
    });

    this._bind();
    this._loadHistory();
    this._connectWS();
    this._loadMembers();
    this.composer.focus();
  }

  // ── Render ──────────────────────────────────────────────────────────────

  _render() {
    const r = this.room;
    this.container.innerHTML = `
      <section class="room" aria-labelledby="rp-title">
        <header class="room-head">
          <button type="button" class="icon-btn room-nav-btn" id="rp-nav" aria-label="Rooms">${icon('menu', 20)}</button>
          <div class="room-head-title">
            <h1 class="room-title" id="rp-title">${escHtml(r.name)}</h1>
            <div class="room-sub">
              <span class="conn" id="rp-conn" data-state="connecting" role="status">
                <span class="conn-dot" aria-hidden="true"></span><span class="conn-label">Connecting…</span>
              </span>
              <span class="room-sub-sep" aria-hidden="true">·</span>
              <span id="rp-meta" class="truncate">${this._memberCountText()}</span>
            </div>
          </div>
          <button type="button" class="presence is-alone" id="rp-presence" aria-label="See who's here">
            <span class="presence-avatars" id="rp-presence-avatars"></span>
            <span class="presence-label"><span class="live-dot" aria-hidden="true"></span><span class="presence-label-text" id="rp-presence-text">Just you</span></span>
          </button>
          <button type="button" class="btn btn-secondary btn-sm" id="rp-invite" title="Copy invite link">
            ${icon('link', 16)}<span class="btn-label">Invite</span>
          </button>
          <button type="button" class="icon-btn" id="rp-details" aria-label="Room details"
                  aria-expanded="false" aria-controls="rp-drawer" title="Details">${icon('panel', 19)}</button>
        </header>

        <div class="timeline-wrap">
          <div class="timeline" id="rp-timeline" role="log" aria-label="Messages" aria-live="polite" tabindex="-1"></div>
          <button type="button" class="jump-pill" id="rp-jump">
            <span class="live-dot" aria-hidden="true"></span>
            <span class="jump-pill-label">New messages</span>
            ${icon('arrowDown', 15)}
          </button>
        </div>

        <div class="composer-wrap" id="rp-composer"></div>
        <div class="drop-zone" aria-hidden="true">Drop an image or audio file to send it</div>
      </section>

      <div class="drawer-scrim" id="rp-scrim"></div>
      <aside class="drawer" id="rp-drawer" role="dialog" aria-modal="true" aria-labelledby="rp-drawer-title">
        <div class="drawer-head">
          <span id="rp-drawer-title">Room details</span>
          <button type="button" class="icon-btn" data-act="close-drawer" aria-label="Close details">${icon('close', 18)}</button>
        </div>
        <div class="drawer-body" id="rp-drawer-body">
          <section class="drawer-section drawer-room" id="rp-drawer-room"></section>
          <section class="drawer-section">
            <div class="drawer-label"><span>Invite link</span></div>
            <div class="invite-field">
              <code id="rp-invite-url">${escHtml(this._inviteUrl())}</code>
              <button type="button" class="btn btn-ghost btn-sm" data-act="copy-invite">${icon('link', 15)} Copy</button>
            </div>
            <p class="invite-hint">Anyone with this link can join after signing in.</p>
          </section>
          <section class="drawer-section">
            <div class="drawer-label">
              <span>Members <span class="mono" id="rp-members-total"></span></span>
              <span class="mono" id="rp-members-online"></span>
            </div>
            <div class="member-list" id="rp-members-list" role="list">
              <div class="room-skeleton" aria-hidden="true"><span class="skeleton" style="border-radius:50%;width:32px;height:32px"></span><span class="room-skeleton-lines"><span class="skeleton"></span><span class="skeleton"></span></span></div>
            </div>
          </section>
        </div>
        <div class="drawer-foot" id="rp-drawer-foot"></div>
      </aside>`;

    const q = (id) => document.getElementById(id);
    this._el = {
      root:       this.container.querySelector('.room'),
      title:      q('rp-title'),
      conn:       q('rp-conn'),
      meta:       q('rp-meta'),
      presence:   q('rp-presence'),
      avatars:    q('rp-presence-avatars'),
      presenceTx: q('rp-presence-text'),
      invite:     q('rp-invite'),
      details:    q('rp-details'),
      timeline:   q('rp-timeline'),
      jump:       q('rp-jump'),
      composer:   q('rp-composer'),
      drawer:     q('rp-drawer'),
      scrim:      q('rp-scrim'),
      drawerBody: q('rp-drawer-body'),
    };
    this._renderDrawerRoom();
  }

  _inviteUrl() { return `${location.origin}/join/${this.room.slug}/`; }

  _memberCountText() {
    const n = this.room.member_count ?? 0;
    return `${n} member${n !== 1 ? 's' : ''}`;
  }

  _renderDrawerRoom() {
    const r = this.room;
    const created = r.created_at
      ? new Date(r.created_at).toLocaleDateString([], { year: 'numeric', month: 'long', day: 'numeric' })
      : '';
    const by = r.creator_username ? ` by @${r.creator_username}` : '';
    document.getElementById('rp-drawer-room').innerHTML = `
      ${monogramHtml(r.name, 'lg')}
      <h2 class="drawer-room-name">${escHtml(r.name)}</h2>
      ${r.description ? `<p class="drawer-room-desc">${escHtml(r.description)}</p>` : ''}
      ${created ? `<p class="drawer-room-meta">Created ${escHtml(created)}${escHtml(by)}</p>` : ''}`;

    document.getElementById('rp-drawer-foot').innerHTML = r.is_creator ? `
      <button type="button" class="btn btn-ghost" data-act="edit">${icon('edit', 17)} Edit room</button>
      <button type="button" class="btn btn-ghost" data-act="delete" style="color:var(--danger)">${icon('trash', 17)} Delete room</button>` : `
      <button type="button" class="btn btn-ghost" data-act="leave" style="color:var(--danger)">${icon('leave', 17)} Leave room</button>`;
  }

  // ── Events ──────────────────────────────────────────────────────────────

  _bind() {
    document.getElementById('rp-nav').addEventListener('click', () => Nav.open());
    this._el.details.addEventListener('click', () => this._openDrawer());
    this._el.presence.addEventListener('click', () => this._openDrawer());
    this._el.invite.addEventListener('click', () => this._copyInvite(this._el.invite, `${icon('check', 16)}<span class="btn-label">Copied</span>`));

    this._el.drawer.addEventListener('click', (e) => {
      const act = e.target.closest('[data-act]')?.dataset.act;
      if (act === 'close-drawer') this._drawer?.close();
      if (act === 'copy-invite')  this._copyInvite(e.target.closest('[data-act]'), `${icon('check', 15)} Copied`);
      if (act === 'edit')   this._openEditModal();
      if (act === 'delete') this._deleteRoom();
      if (act === 'leave')  this._leaveRoom();
      const m = e.target.closest('.member');
      if (m) this._showProfile(this.members.get(m.dataset.username) || { username: m.dataset.username });
    });

    // The connection retry link lives inside the status line
    this._el.conn.addEventListener('click', (e) => {
      if (e.target.closest('.conn-retry')) this._retryNow();
    });

    // Come back from a lost connection as soon as the network or tab returns
    this._onOnline     = () => this._retryNow();
    this._onVisibility = () => { if (!document.hidden) this._retryIfGivenUp(); };
    window.addEventListener('online', this._onOnline);
    document.addEventListener('visibilitychange', this._onVisibility);
  }

  async _copyInvite(btn, doneHtml) {
    const ok = await copyText(this._inviteUrl());
    if (ok) {
      flashButton(btn, doneHtml);
      announce('Invite link copied');
    } else {
      showToast('Couldn\'t copy. The link is in Room details.', 'error');
    }
  }

  // ── Drawer ──────────────────────────────────────────────────────────────

  _openDrawer() {
    if (this._drawer) return;
    this._el.details.setAttribute('aria-expanded', 'true');
    this._drawer = openLayer(this._el.drawer, {
      backdrop: this._el.scrim,
      initialFocus: '[data-act="close-drawer"]',
      onClose: () => {
        this._drawer = null;
        this._el.details?.setAttribute('aria-expanded', 'false');
      },
    });
  }

  // ── History ─────────────────────────────────────────────────────────────

  async _loadHistory() {
    this.messages.showLoading();
    const res = await apiFetch(`/api/rooms/${this.room.slug}/`);
    if (this._destroyed) return;
    if (!res.ok) { this.messages.showError('Messages didn\'t load. Check your connection and reopen the room.'); return; }

    const data = await res.json();
    if (this._destroyed) return;
    this.room = { ...this.room, ...data.room, slug: String(data.room.slug) };
    this._el.meta.textContent = this._memberCountText();
    this._renderDrawerRoom();
    this.messages.renderHistory(data.messages, this.room);

    // Anything that arrived over the socket while history was in flight
    this._historyReady = true;
    this._pending.forEach(m => this.messages.append(m, { live: true }));
    this._pending = [];
  }

  // ── WebSocket ───────────────────────────────────────────────────────────

  _connectWS() {
    if (this._destroyed) return;
    clearTimeout(this._reconnectTimer);
    const proto = location.protocol === 'https:' ? 'wss' : 'ws';
    const ws = new WebSocket(`${proto}://${location.host}/ws/chat/${this.room.slug}/?token=${getAccessToken()}`);
    this.ws = ws;
    if (!this._everConnected) this._setConn('connecting');

    ws.onopen = () => {
      const restored = this._everConnected;
      this.wsReady = true;
      this.reconnectCount = 0;
      this._everConnected = true;
      // Presence is rebuilt from scratch on every (re)connect: the roll call
      // triggered by our own join tells us who is here.
      this.online.clear();
      this._renderPresence();
      this._setConn('live', { restored });
      this.composer.setOnline(true);
    };

    ws.onmessage = (e) => {
      let msg;
      try { msg = JSON.parse(e.data); } catch { return; }
      if (msg.type === 'chat_message')   this._onChatMessage(msg);
      if (msg.type === 'presence_event') this._onPresence(msg);
    };

    ws.onclose = async (e) => {
      if (this.ws !== ws) return;
      this.wsReady = false;
      this.composer.setOnline(false);
      if (e.code === 4001 && !this._authRetried) {
        // Access token expired while we were connected: refresh once, retry.
        this._authRetried = true;
        if (await _tryRefresh()) { this._connectWS(); return; }
      }
      if (e.code === 4001 || e.code === 4003 || e.code === 4004) {
        this._setConn('denied');
        return;
      }
      this._scheduleReconnect();
    };
  }

  _scheduleReconnect() {
    if (this.reconnectCount >= MAX_RECONNECTS) {
      this._setConn('offline');
      return;
    }
    const delay = Math.min(1000 * 2 ** this.reconnectCount, 12000);
    this.reconnectCount++;
    this._setConn('reconnecting');
    this._reconnectTimer = setTimeout(() => this._connectWS(), delay);
  }

  _retryNow() {
    if (this._destroyed || this.wsReady) return;
    if (this.ws) { this.ws.onclose = null; this.ws.close(); }
    this.reconnectCount = 0;
    this._setConn('reconnecting');
    this._connectWS();
  }

  _retryIfGivenUp() {
    if (this._el.conn.dataset.state === 'offline') this._retryNow();
  }

  _setConn(state, { restored = false } = {}) {
    const el = this._el.conn;
    if (!el) return;
    clearTimeout(this._connFlashTimer);
    el.dataset.state = state;
    el.classList.remove('is-restored');
    const label = el.querySelector('.conn-label');
    const text = {
      connecting:   'Connecting…',
      live:         'Live',
      reconnecting: 'Reconnecting…',
      offline:      'Offline · <button type="button" class="conn-retry">Retry</button>',
      denied:       'Can\'t connect — check your membership',
    }[state];

    if (state === 'live' && restored) {
      void el.offsetWidth;
      el.classList.add('is-restored');
      label.textContent = 'Back online';
      this._connFlashTimer = setTimeout(() => {
        el.classList.remove('is-restored');
        label.textContent = 'Live';
      }, 1800);
    } else {
      label.innerHTML = text;
    }
  }

  // ── Messages ────────────────────────────────────────────────────────────

  _sendText(content) {
    if (!this.wsReady) return false;
    this.ws.send(JSON.stringify({ type: 'text', content }));
    return true;
  }

  _onChatMessage(msg) {
    if (this._historyReady) this.messages.append(msg, { live: true });
    else this._pending.push(msg);
    RoomList.updatePreview(this.room.slug, msg);
    this._markSeen();
  }

  _markSeen() {
    clearTimeout(this._markSeenTimer);
    this._markSeenTimer = setTimeout(() => {
      apiFetch(`/api/rooms/${this.room.slug}/seen/`, { method: 'PATCH' });
    }, 2000);
  }

  // ── Presence ────────────────────────────────────────────────────────────

  _onPresence(msg) {
    const isMe = msg.username === this.me.username;
    const entry = { display_name: msg.display_name || msg.username };

    if (msg.event === 'here') {
      // Roll-call reply from someone already in the room
      if (!isMe) this.online.set(msg.username, entry);
    } else if (msg.event === 'join') {
      this.online.set(msg.username, entry);
      if (!isMe) {
        this._answerRollCall();
        if (this._historyReady) this.messages.presence({ ...msg, avatar_url: this.members.get(msg.username)?.avatar_url });
      }
    } else {
      // 'leave'. With two tabs open, one closing doesn't mean you left.
      if (isMe) return;
      this.online.delete(msg.username);
      if (this._historyReady) this.messages.presence({ ...msg, avatar_url: this.members.get(msg.username)?.avatar_url });
    }
    this._renderPresence();
    this._updateMemberDot(msg.username, this.online.has(msg.username));
  }

  // Someone just arrived: tell them we're here. Throttled so a burst of
  // joins doesn't trigger a burst of replies.
  _answerRollCall() {
    const now = Date.now();
    if (!this.wsReady || now - this._lastRollCall < 1500) return;
    this._lastRollCall = now;
    this.ws.send(JSON.stringify({ type: 'here' }));
  }

  _renderPresence() {
    const others = [...this.online.entries()].filter(([u]) => u !== this.me.username);
    const shown  = others.slice(0, 4);
    const box    = this._el.avatars;

    // Diff the stack so arrivals pop in and departures pop out
    const keep = new Set(shown.map(([u]) => u));
    box.querySelectorAll('.avatar[data-user]').forEach((av) => {
      if (keep.has(av.dataset.user) || av.classList.contains('is-leaving')) return;
      av.classList.add('is-leaving');
      setTimeout(() => av.remove(), reducedMotion() ? 0 : 150);
    });
    shown.forEach(([username, p]) => {
      if (box.querySelector(`.avatar[data-user="${CSS.escape(username)}"]:not(.is-leaving)`)) return;
      const m = this.members.get(username);
      box.insertAdjacentHTML('beforeend', avatarHtml({ name: p.display_name, url: m?.avatar_url, size: 'sm', cls: 'is-entering' }));
      box.lastElementChild.dataset.user = username;
    });

    const n = others.length;
    this._el.presence.classList.toggle('is-alone', n === 0);
    this._el.presenceTx.textContent = n === 0 ? 'Just you' : `${n} here`;
    const names = others.map(([, p]) => p.display_name);
    this._el.presence.setAttribute('aria-label', n === 0
      ? 'Only you are here right now. See room details'
      : `${names.join(', ')} ${n === 1 ? 'is' : 'are'} here right now. See room details`);

    const onlineEl = document.getElementById('rp-members-online');
    if (onlineEl) onlineEl.textContent = this.online.size ? `${this.online.size} online` : '';
  }

  // ── Members ─────────────────────────────────────────────────────────────

  async _loadMembers() {
    if (this._membersLoading || !this._membersHasMore) return;
    this._membersLoading = true;

    const res = await apiFetch(`/api/rooms/${this.room.slug}/members/?limit=20&offset=${this._membersOffset}`);
    this._membersLoading = false;
    if (this._destroyed || !res.ok) return;

    const data = await res.json();
    const list = document.getElementById('rp-members-list');
    if (!list) return;
    if (this._membersOffset === 0) list.innerHTML = '';
    document.getElementById('rp-members-sentinel')?.remove();

    data.members.forEach((m) => {
      this.members.set(m.username, m);
      list.appendChild(this._memberItem(m));
    });
    this._membersOffset += data.members.length;
    this._membersHasMore = data.has_more;
    document.getElementById('rp-members-total').textContent = `· ${data.total}`;

    // Members load after presence may have arrived: give avatars their photos.
    this._el.avatars.querySelectorAll('.avatar[data-user]').forEach((av) => {
      const m = this.members.get(av.dataset.user);
      if (m?.avatar_url && !av.querySelector('img')) av.innerHTML = `<img src="${escHtml(m.avatar_url)}" alt="">`;
    });

    if (this._membersHasMore) {
      const sentinel = document.createElement('div');
      sentinel.id = 'rp-members-sentinel';
      sentinel.style.height = '1px';
      list.appendChild(sentinel);
      if (!this._membersObserver) {
        this._membersObserver = new IntersectionObserver(
          (entries) => { if (entries[0].isIntersecting) this._loadMembers(); },
          { root: this._el.drawerBody, rootMargin: '120px' },
        );
      }
      this._membersObserver.observe(sentinel);
    }
  }

  _memberItem(m) {
    const name = m.display_name || m.username;
    const isCreator = this.room.creator_username && m.username === this.room.creator_username;
    const isMe = m.username === this.me.username;
    const btn = document.createElement('button');
    btn.type = 'button';
    btn.className = 'member' + (this.online.has(m.username) ? ' is-online' : '');
    btn.dataset.username = m.username;
    btn.setAttribute('role', 'listitem');
    btn.innerHTML = `
      <span class="member-avatar">${avatarHtml({ name, url: m.avatar_url, size: 'md' })}<span class="member-dot" aria-hidden="true"></span></span>
      <span class="member-text">
        <span class="member-name truncate">${escHtml(name)}${isMe ? ' <span style="color:var(--text-3)">(you)</span>' : ''}</span>
        <span class="member-handle truncate">@${escHtml(m.username)}</span>
      </span>
      ${isCreator ? '<span class="member-role">Creator</span>' : ''}
      <span class="sr-only">${this.online.has(m.username) ? 'online' : 'offline'}</span>`;
    return btn;
  }

  _updateMemberDot(username, isOnline) {
    const item = this._el.drawer.querySelector(`.member[data-username="${CSS.escape(username)}"]`);
    if (!item) return;
    item.classList.toggle('is-online', isOnline);
    const sr = item.querySelector('.sr-only');
    if (sr) sr.textContent = isOnline ? 'online' : 'offline';
  }

  // ── Profiles ────────────────────────────────────────────────────────────

  async _showProfile(preload) {
    this._profileLayer?.close();
    const isOwn = preload.username === this.me.username;
    const base  = isOwn ? { ...this.me } : preload;
    const name  = base.display_name || base.username;
    const id    = 'pc-' + Math.random().toString(36).slice(2, 8);

    const { modal, layer } = createModal({
      size: 'sm',
      cls: 'profile-card',
      labelledBy: id,
      onClose: () => { if (this._profileLayer === layer) this._profileLayer = null; },
      html: `
        <button type="button" class="icon-btn modal-close" data-close aria-label="Close">${icon('close', 18)}</button>
        <div data-avatar>${avatarHtml({ name, url: base.avatar_url, size: 'xl' })}</div>
        <h2 class="profile-card-name" id="${id}">${escHtml(name)}</h2>
        <p class="profile-card-handle">@${escHtml(base.username || '')}</p>
        ${this.online.has(base.username) ? '<p class="profile-card-online"><span class="live-dot"></span>Here now</p>' : ''}
        <div data-body>${isOwn ? '' : '<div class="spinner" style="margin:24px auto 0"></div>'}</div>
        ${isOwn ? '<a href="/profile/" class="btn btn-secondary btn-full">Edit profile</a>' : ''}`,
    });
    this._profileLayer = layer;
    modal.querySelector('[data-close]').addEventListener('click', () => layer.close());

    const fill = (p) => {
      const joined = p.date_joined
        ? new Date(p.date_joined).toLocaleDateString([], { year: 'numeric', month: 'long' })
        : '';
      modal.querySelector('[data-body]').innerHTML = `
        ${p.bio ? `<p class="profile-card-bio">${escHtml(p.bio)}</p>` : ''}
        ${joined ? `<p class="profile-card-meta">Member since ${escHtml(joined)}</p>` : ''}`;
    };

    if (isOwn) { fill(this.me); return; }

    const res = await apiFetch(`/api/auth/users/${encodeURIComponent(preload.username)}/`);
    if (this._profileLayer !== layer) return;
    if (!res.ok) { modal.querySelector('[data-body]').innerHTML = ''; return; }
    const p = await res.json();
    const pname = p.display_name || p.username;
    modal.querySelector('[data-avatar]').innerHTML = avatarHtml({ name: pname, url: p.avatar_url, size: 'xl' });
    modal.querySelector('.profile-card-name').textContent = pname;
    fill(p);
  }

  // ── Edit / leave / delete ───────────────────────────────────────────────

  _openEditModal() {
    const { overlay, modal, layer } = createModal({
      labelledBy: 'rp-edit-title',
      initialFocus: '#rp-edit-name',
      html: `
        <div class="modal-head">
          <h2 class="modal-title" id="rp-edit-title">Edit room</h2>
          <button type="button" class="icon-btn modal-close" data-close aria-label="Close">${icon('close', 18)}</button>
        </div>
        <form id="rp-edit-form" novalidate>
          <div class="modal-body">
            <div class="form-error" id="rp-edit-error" role="alert"></div>
            <div class="field">
              <label class="field-label" for="rp-edit-name">Name</label>
              <input class="input" type="text" id="rp-edit-name" value="${escHtml(this.room.name)}" maxlength="100" autocomplete="off" required>
            </div>
            <div class="field">
              <label class="field-label" for="rp-edit-desc">Description <span class="field-hint">Optional</span></label>
              <textarea class="input" id="rp-edit-desc" rows="3">${escHtml(this.room.description || '')}</textarea>
            </div>
          </div>
          <div class="modal-foot">
            <button type="button" class="btn btn-ghost" data-close>Cancel</button>
            <button type="submit" class="btn btn-primary" id="rp-edit-submit">Save</button>
          </div>
        </form>`,
    });
    overlay.querySelectorAll('[data-close]').forEach(b => b.addEventListener('click', () => layer.close()));
    modal.querySelector('form').addEventListener('submit', (e) => { e.preventDefault(); this._submitEdit(modal, layer); });
  }

  async _submitEdit(modal, layer) {
    const nameInput = modal.querySelector('#rp-edit-name');
    const errorEl   = modal.querySelector('#rp-edit-error');
    const submitBtn = modal.querySelector('#rp-edit-submit');
    const name        = nameInput.value.trim();
    const description = modal.querySelector('#rp-edit-desc').value.trim();

    errorEl.classList.remove('is-visible');
    nameInput.removeAttribute('aria-invalid');
    if (!name) {
      errorEl.textContent = 'Room name is required.';
      errorEl.classList.add('is-visible');
      nameInput.setAttribute('aria-invalid', 'true');
      nameInput.focus();
      return;
    }

    submitBtn.disabled = true;
    submitBtn.textContent = 'Saving…';
    const res = await apiFetch(`/api/rooms/${this.room.slug}/update/`, {
      method: 'PATCH',
      body:   JSON.stringify({ name, description }),
    });
    submitBtn.disabled = false;
    submitBtn.textContent = 'Save';

    if (!res.ok) {
      const d = await res.json().catch(() => ({}));
      errorEl.textContent = d.error || 'Could not save changes.';
      errorEl.classList.add('is-visible');
      return;
    }

    const updated = await res.json();
    this.room.name        = updated.name;
    this.room.description = updated.description;
    this._el.title.textContent = updated.name;
    this._renderDrawerRoom();
    this.messages.updateIntro(this.room);
    RoomList.rename(this.room.slug, updated.name);
    layer.close();
    showToast('Room updated.');
  }

  async _leaveRoom() {
    const ok = await confirmDialog({
      title: `Leave ${this.room.name}?`,
      body: 'You\'ll stop receiving its messages. You can rejoin with an invite link.',
      confirmLabel: 'Leave room',
      danger: true,
    });
    if (!ok) return;
    const res = await apiFetch(`/api/rooms/${this.room.slug}/leave/`, { method: 'POST' });
    if (!res.ok) {
      const d = await res.json().catch(() => ({}));
      showToast(d.error || 'Could not leave the room.', 'error');
      return;
    }
    const name = this.room.name;
    this._drawer?.close();
    closeRoom();
    await RoomList.load();
    showEmptyPanel();
    showToast(`You left ${name}.`);
  }

  async _deleteRoom() {
    const ok = await confirmDialog({
      title: `Delete ${this.room.name}?`,
      body: 'The room and all of its messages will be removed for everyone. This can\'t be undone.',
      confirmLabel: 'Delete room',
      danger: true,
    });
    if (!ok) return;
    const res = await apiFetch(`/api/rooms/${this.room.slug}/delete/`, { method: 'DELETE' });
    if (!res.ok) {
      const d = await res.json().catch(() => ({}));
      showToast(d.error || 'Could not delete the room.', 'error');
      return;
    }
    const name = this.room.name;
    this._drawer?.close();
    closeRoom();
    await RoomList.load();
    showEmptyPanel();
    showToast(`${name} was deleted.`);
  }

  // ── Teardown ────────────────────────────────────────────────────────────

  destroy() {
    this._destroyed = true;
    this._profileLayer?.close();
    this._drawer?.close();
    clearTimeout(this._markSeenTimer);
    clearTimeout(this._reconnectTimer);
    clearTimeout(this._connFlashTimer);
    this._membersObserver?.disconnect();
    window.removeEventListener('online', this._onOnline);
    document.removeEventListener('visibilitychange', this._onVisibility);
    this.messages?.destroy();
    this.composer?.destroy();
    if (this.ws) {
      this.ws.onclose = null;
      this.ws.close();
      this.ws = null;
    }
  }
}
