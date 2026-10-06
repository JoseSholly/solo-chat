/* Dashboard shell — sidebar, room list, unread notifications, navigation.
   Depends on api.js, auth.js, ui.js. room.js provides loadRoomPanel(). */

let _activeSlug = null;
const _rooms = new Map();   // slug → room, in the shape /api/dashboard/ returns

const _app = () => document.getElementById('app');

function _restartClass(el, cls) {
  el.classList.remove(cls);
  void el.offsetWidth;   // reflow so the animation replays
  el.classList.add(cls);
}

function updateTitle() {
  const unread = [..._rooms.values()]
    .filter(r => r.slug !== _activeSlug)
    .reduce((n, r) => n + (r.unread_count || 0), 0);
  const active = _activeSlug && _rooms.get(_activeSlug);
  const base   = active ? `${active.name} — Solo-Chat` : 'Solo-Chat';
  document.title = unread ? `(${unread}) ${base}` : base;
}

// ── Mobile: the room list becomes a drawer while a room is open ─────────────

const Nav = {
  _layer: null,

  init() {
    _mobileMQ.addEventListener('change', () => this.close());
  },

  open() {
    if (this._layer || !isMobile()) return;
    _app().classList.add('nav-open');
    this._layer = openLayer(document.getElementById('sidebar'), {
      backdrop:     document.getElementById('nav-scrim'),
      initialFocus: '.room-item.is-active',
      onClose:      () => { _app().classList.remove('nav-open'); this._layer = null; },
    });
  },

  close() { this._layer?.close(); },
};

// ── Signed-in user ───────────────────────────────────────────────────────────

function initUserMenu() {
  const user = getUser();
  if (!user) return;
  const name = user.display_name || user.username;
  document.getElementById('nav-user-avatar').innerHTML = avatarHtml({ name, url: user.avatar_url, size: 'md' });
  document.getElementById('nav-user-name').textContent   = name;
  document.getElementById('nav-user-handle').textContent = '@' + user.username;
  document.getElementById('user-menu-trigger').setAttribute('aria-label', `Account: ${name}`);

  bindMenu(document.getElementById('user-menu-trigger'), document.getElementById('user-dropdown'));
  document.getElementById('btn-logout').addEventListener('click', () => authLogout());
}

// ── Room list ────────────────────────────────────────────────────────────────

function _badgeHtml(n) {
  return `<span class="badge" aria-label="${n} unread">${n > 99 ? '99+' : n}</span>`;
}

function _previewHtml(last) {
  if (!last) return '<em>No messages yet</em>';
  const me   = getUser();
  const mine = me && last.display_name && last.display_name === (me.display_name || me.username);
  // First names keep the preview about the message, not the sender
  const who  = mine ? 'You' : String(last.display_name || '').trim().split(/\s+/)[0];
  const body = last.message_type === 'image' ? '<em>Photo</em>'
             : last.message_type === 'voice' ? '<em>Voice note</em>'
             : escHtml(String(last.content || '').replace(/\s+/g, ' '));
  return who ? `${escHtml(who)}: ${body}` : body;
}

const RoomList = {
  indicator: null,
  _reconcileTimer: null,

  get el() { return document.getElementById('room-list'); },

  init() {
    this.el.addEventListener('click', (e) => {
      const a = e.target.closest('.room-item');
      if (!a) return;
      if (e.metaKey || e.ctrlKey || e.shiftKey || e.altKey) return;   // let new-tab gestures through
      e.preventDefault();
      const room = _rooms.get(a.dataset.slug);
      if (room) selectRoom(room);
    });

    // Alt+↑ / Alt+↓ moves between rooms from anywhere
    document.addEventListener('keydown', (e) => {
      if (!e.altKey || (e.key !== 'ArrowUp' && e.key !== 'ArrowDown')) return;
      const slugs = [..._rooms.keys()];
      if (!slugs.length) return;
      e.preventDefault();
      const i = slugs.indexOf(_activeSlug);
      const next = e.key === 'ArrowDown' ? (i + 1) % slugs.length : (i - 1 + slugs.length) % slugs.length;
      selectRoom(_rooms.get(slugs[i === -1 ? 0 : next]));
    });

    setInterval(() => this.refreshTimes(), 30000);
  },

  async load() {
    if (!_rooms.size) this._skeleton();
    const res = await apiFetch('/api/dashboard/');
    if (!res.ok) {
      this.el.innerHTML = '<div class="room-list-empty"><strong>Rooms didn\'t load</strong>Check your connection and refresh.</div>';
      return false;
    }
    const rooms = await res.json();
    _rooms.clear();
    rooms.forEach(r => _rooms.set(String(r.slug), { ...r, slug: String(r.slug) }));
    this.render();
    return true;
  },

  _skeleton() {
    this.el.innerHTML = Array.from({ length: 4 }, () => `
      <div class="room-skeleton" aria-hidden="true">
        <span class="skeleton"></span>
        <span class="room-skeleton-lines"><span class="skeleton"></span><span class="skeleton"></span></span>
      </div>`).join('');
  },

  render() {
    const list = this.el;
    list.innerHTML = '<span class="room-indicator" aria-hidden="true"></span>';
    this.indicator = list.firstElementChild;
    document.getElementById('room-count').textContent = _rooms.size || '';

    if (!_rooms.size) {
      list.insertAdjacentHTML('beforeend', `
        <div class="room-list-empty">
          <strong>No rooms yet</strong>
          Create one, or open an invite link someone sent you.
        </div>`);
    } else {
      const frag = document.createDocumentFragment();
      for (const room of _rooms.values()) frag.appendChild(this._item(room));
      list.appendChild(frag);
    }
    this.syncIndicator(false);
    updateTitle();
  },

  _item(room) {
    const a = document.createElement('a');
    a.className = 'room-item';
    a.href = '/dashboard/?room=' + encodeURIComponent(room.slug);
    a.dataset.slug = room.slug;
    if (room.slug === _activeSlug) { a.classList.add('is-active'); a.setAttribute('aria-current', 'page'); }
    if (room.unread_count > 0 && room.slug !== _activeSlug) a.classList.add('has-unread');

    const ts = room.last_message?.timestamp || '';
    a.innerHTML = `
      ${monogramHtml(room.name)}
      <span class="room-item-body">
        <span class="room-item-row">
          <span class="room-name">${escHtml(room.name)}</span>
          <time class="room-time" ${ts ? `datetime="${escHtml(ts)}"` : ''}>${escHtml(compactTime(ts))}</time>
        </span>
        <span class="room-item-row">
          <span class="room-preview">${_previewHtml(room.last_message)}</span>
          ${room.unread_count > 0 && room.slug !== _activeSlug ? _badgeHtml(room.unread_count) : ''}
        </span>
      </span>`;
    return a;
  },

  _find(slug) {
    return this.el.querySelector(`.room-item[data-slug="${CSS.escape(slug)}"]`);
  },

  setActive(slug) {
    this.el.querySelectorAll('.room-item').forEach((el) => {
      const on = el.dataset.slug === slug;
      el.classList.toggle('is-active', on);
      if (on) el.setAttribute('aria-current', 'page'); else el.removeAttribute('aria-current');
    });
    this.syncIndicator(true);
    this._find(slug)?.scrollIntoView({ block: 'nearest' });
  },

  // Slide the selection to the active room instead of teleporting it.
  syncIndicator(animate) {
    const ind = this.indicator;
    if (!ind) return;
    const item = this.el.querySelector('.room-item.is-active');
    if (!item) { ind.classList.remove('is-visible'); return; }
    const jump = !animate || !ind.classList.contains('is-visible');
    if (jump) ind.classList.add('no-anim');
    ind.style.setProperty('--y', item.offsetTop + 'px');
    ind.style.setProperty('--h', item.offsetHeight + 'px');
    ind.classList.add('is-visible');
    if (jump) { void ind.offsetWidth; ind.classList.remove('no-anim'); }
  },

  // A message landed in a background room.
  bump(slug) {
    const room = _rooms.get(slug);
    const item = this._find(slug);
    if (!room || !item) { this.reconcileSoon(0); return; }

    room.unread_count = (room.unread_count || 0) + 1;
    item.classList.add('has-unread');

    const row = item.querySelectorAll('.room-item-row')[1];
    let badge = item.querySelector('.badge');
    if (!badge) {
      row.insertAdjacentHTML('beforeend', _badgeHtml(room.unread_count));
      _restartClass(row.lastElementChild, 'is-entering');
    } else {
      badge.outerHTML = _badgeHtml(room.unread_count);
      _restartClass(row.querySelector('.badge'), 'is-bumped');
    }

    const time = item.querySelector('.room-time');
    time.dateTime = new Date().toISOString();
    time.textContent = 'now';

    _restartClass(item, 'is-bumped');
    updateTitle();
  },

  clearUnread(slug) {
    const room = _rooms.get(slug);
    if (room) room.unread_count = 0;
    const item = this._find(slug);
    if (item) {
      item.classList.remove('has-unread');
      item.querySelector('.badge')?.remove();
    }
    updateTitle();
  },

  // Keep the active room's preview current from messages we already have.
  updatePreview(slug, msg) {
    const room = _rooms.get(slug);
    const item = this._find(slug);
    if (!room || !item) return;
    room.last_message = {
      display_name: msg.display_name || msg.username,
      message_type: msg.message_type,
      content:      msg.message_type === 'text' ? msg.content : null,
      timestamp:    msg.timestamp || new Date().toISOString(),
    };
    item.querySelector('.room-preview').innerHTML = _previewHtml(room.last_message);
    const time = item.querySelector('.room-time');
    time.dateTime = room.last_message.timestamp;
    time.textContent = compactTime(room.last_message.timestamp);
  },

  rename(slug, name) {
    const room = _rooms.get(slug);
    const item = this._find(slug);
    if (!room) return;
    room.name = name;
    if (item) item.replaceWith(this._item(room));
    this.syncIndicator(false);
    updateTitle();
  },

  refreshTimes() {
    this.el.querySelectorAll('.room-time[datetime]').forEach((t) => {
      t.textContent = compactTime(t.getAttribute('datetime'));
    });
  },

  // Unread pushes carry no content, so after a burst of them fetch the real
  // previews and counts once. Event-driven, debounced — not polling.
  reconcileSoon(delay = 1200) {
    clearTimeout(this._reconcileTimer);
    this._reconcileTimer = setTimeout(() => this._reconcile(), delay);
  },

  async _reconcile() {
    const res = await apiFetch('/api/dashboard/');
    if (!res.ok) return;
    const rooms = (await res.json()).map(r => ({ ...r, slug: String(r.slug) }));
    const sameSet = rooms.length === _rooms.size && rooms.every(r => _rooms.has(r.slug));

    rooms.forEach((r) => {
      if (r.slug === _activeSlug) r.unread_count = 0;
      _rooms.set(r.slug, { ..._rooms.get(r.slug), ...r });
    });
    if (!sameSet) {
      const fresh = new Set(rooms.map(r => r.slug));
      [..._rooms.keys()].forEach(s => { if (!fresh.has(s)) _rooms.delete(s); });
      this.render();
      return;
    }

    rooms.forEach((r) => {
      const item = this._find(r.slug);
      if (!item) return;
      item.querySelector('.room-preview').innerHTML = _previewHtml(r.last_message);
      const time = item.querySelector('.room-time');
      if (r.last_message) {
        time.dateTime = r.last_message.timestamp;
        time.textContent = compactTime(r.last_message.timestamp);
      }
      if (r.slug === _activeSlug) return;
      const badge = item.querySelector('.badge');
      item.classList.toggle('has-unread', r.unread_count > 0);
      if (r.unread_count > 0) {
        if (badge) badge.outerHTML = _badgeHtml(r.unread_count);
        else item.querySelectorAll('.room-item-row')[1].insertAdjacentHTML('beforeend', _badgeHtml(r.unread_count));
      } else {
        badge?.remove();
      }
    });
    updateTitle();
  },
};

// ── Notification socket: unread pushes for rooms you're not looking at ──────

const Notifications = {
  ws: null,
  timer: null,
  attempts: 0,
  dead: false,
  _dropped: false,
  _authRetried: false,

  _setMark(state) {
    const mark = document.getElementById('notif-mark');
    if (!mark) return;
    mark.dataset.state = state;
    mark.title = state === 'live' ? 'Live updates connected' : 'Live updates paused — reconnecting';
  },

  connect() {
    clearTimeout(this.timer);
    if (this.ws) { this.ws.onclose = null; this.ws.close(); }

    const proto = location.protocol === 'https:' ? 'wss' : 'ws';
    const ws = new WebSocket(`${proto}://${location.host}/ws/notifications/?token=${getAccessToken()}`);
    this.ws = ws;

    ws.onopen = () => {
      this.attempts = 0;
      this.dead = false;
      this._setMark('live');
      // Anything that happened while we were away: sync once.
      if (this._dropped) RoomList.reconcileSoon(0);
    };

    ws.onmessage = (e) => {
      let msg;
      try { msg = JSON.parse(e.data); } catch { return; }
      if (msg.type === 'unread_update' && msg.room_slug !== _activeSlug) {
        RoomList.bump(String(msg.room_slug));
        RoomList.reconcileSoon();
      }
    };

    ws.onclose = async (e) => {
      this._setMark('offline');
      this._dropped = true;
      if (e.code === 4001 && !this._authRetried) {
        this._authRetried = true;
        if (await _tryRefresh()) { this.connect(); return; }
      }
      if (this.attempts >= 6) { this.dead = true; return; }
      const delay = Math.min(1000 * 2 ** this.attempts, 15000);
      this.attempts++;
      this.timer = setTimeout(() => this.connect(), delay);
    };
  },

  // Called when the network or tab comes back after we gave up.
  revive() {
    if (!this.dead) return;
    this.attempts = 0;
    this.connect();
  },
};

window.addEventListener('online', () => Notifications.revive());
document.addEventListener('visibilitychange', () => { if (!document.hidden) Notifications.revive(); });

// ── Navigation ───────────────────────────────────────────────────────────────

function showEmptyPanel() {
  _app().classList.remove('room-open');
  Nav.close();
  const user  = getUser();
  const first = String(user?.display_name || '').trim().split(/\s+/)[0];

  document.getElementById('main-panel').innerHTML = _rooms.size ? `
    <div class="stage-empty">
      <p class="kicker"><span class="live-dot"></span>${_rooms.size} room${_rooms.size !== 1 ? 's' : ''}</p>
      <h1 class="stage-empty-title">Welcome back${first ? ', ' + escHtml(first) : ''}.<br><span>Pick up a conversation.</span></h1>
      <p class="stage-empty-body">Choose a room on the left. Anything new shows up there the moment it's sent.</p>
      <div class="stage-empty-actions">
        <button class="btn btn-secondary" type="button" data-new-room>${icon('plus', 16)} New room</button>
      </div>
    </div>` : `
    <div class="stage-empty">
      <h1 class="stage-empty-title">Start a room.<br><span>Invite your people.</span></h1>
      <p class="stage-empty-body">Rooms are private: only people with the invite link can join. Talk in text, images and voice notes, and everyone sees it as it happens.</p>
      <div class="stage-empty-actions">
        <button class="btn btn-primary" type="button" data-new-room>${icon('plus', 16)} New room</button>
      </div>
    </div>`;
  updateTitle();
}

function selectRoom(room, { push = true } = {}) {
  if (!room) return;
  Nav.close();
  if (room.slug === _activeSlug && _activePanel) return;

  _activeSlug = room.slug;
  RoomList.setActive(room.slug);
  RoomList.clearUnread(room.slug);
  _app().classList.add('room-open');
  if (push) history.pushState({ slug: room.slug }, '', '/dashboard/?room=' + encodeURIComponent(room.slug));
  loadRoomPanel(room);   // room.js
  updateTitle();
}

function closeRoom({ push = true } = {}) {
  destroyActivePanel();
  _activeSlug = null;
  RoomList.setActive(null);
  if (push) history.pushState({}, '', '/dashboard/');
  showEmptyPanel();
}

// Browser back/forward moves between rooms (and back to the list on mobile).
window.addEventListener('popstate', () => {
  const slug = new URLSearchParams(location.search).get('room');
  if (slug && _rooms.has(slug)) selectRoom(_rooms.get(slug), { push: false });
  else closeRoom({ push: false });
});

// ── New room ─────────────────────────────────────────────────────────────────

const NewRoom = {
  layer: null,

  init() {
    document.getElementById('btn-new-room').addEventListener('click', () => this.open());
    document.getElementById('modal-close').addEventListener('click', () => this.close());
    document.getElementById('modal-cancel').addEventListener('click', () => this.close());
    document.getElementById('new-room-form').addEventListener('submit', (e) => { e.preventDefault(); this.submit(); });
    document.getElementById('room-name-input').addEventListener('input', (e) => e.target.removeAttribute('aria-invalid'));
  },

  open() {
    Nav.close();
    document.getElementById('new-room-form').reset();
    document.getElementById('modal-error').classList.remove('is-visible');
    document.getElementById('room-name-input').removeAttribute('aria-invalid');
    this.layer = openLayer(document.getElementById('modal-overlay'), {
      initialFocus: '#room-name-input',
      onClose: () => { this.layer = null; },
    });
  },

  close() { this.layer?.close(); },

  _error(msg) {
    const el = document.getElementById('modal-error');
    el.textContent = msg;
    el.classList.remove('is-visible');
    void el.offsetWidth;
    el.classList.add('is-visible');
  },

  async submit() {
    const nameInput = document.getElementById('room-name-input');
    const name = nameInput.value.trim();
    const description = document.getElementById('room-desc-input').value.trim();
    if (!name) {
      nameInput.setAttribute('aria-invalid', 'true');
      this._error('Give the room a name.');
      nameInput.focus();
      return;
    }

    const btn = document.getElementById('modal-submit');
    btn.disabled = true;
    btn.textContent = 'Creating…';

    const res  = await apiFetch('/api/rooms/', { method: 'POST', body: JSON.stringify({ name, description }) });
    const data = await res.json().catch(() => ({}));

    btn.disabled = false;
    btn.textContent = 'Create room';

    if (!res.ok) {
      const msg = data.error?.name?.[0] || data.error || 'Could not create the room.';
      nameInput.setAttribute('aria-invalid', 'true');
      this._error(typeof msg === 'string' ? msg : JSON.stringify(msg));
      return;
    }

    this.close();
    await RoomList.load();
    selectRoom(_rooms.get(String(data.slug)) || { ...data, slug: String(data.slug) });
    showToast('Room created. Use Invite to bring people in.');
  },
};

// ── Boot ─────────────────────────────────────────────────────────────────────

document.addEventListener('DOMContentLoaded', async () => {
  initUserMenu();
  Nav.init();
  NewRoom.init();
  RoomList.init();

  document.getElementById('main-panel').addEventListener('click', (e) => {
    if (e.target.closest('[data-new-room]')) NewRoom.open();
  });

  await RoomList.load();
  Notifications.connect();

  // Open the room in the URL (e.g. arriving from an invite link)
  const slug = new URLSearchParams(location.search).get('room');
  if (slug && _rooms.has(slug)) {
    history.replaceState({ slug }, '');
    selectRoom(_rooms.get(slug), { push: false });
  } else {
    if (slug) history.replaceState({}, '', '/dashboard/');
    showEmptyPanel();
  }
});
