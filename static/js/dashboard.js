/* Dashboard — depends on api.js, auth.js */

const ROOM_COLORS = ['#6366f1','#8b5cf6','#ec4899','#f97316','#14b8a6','#0ea5e9','#84cc16'];

function roomColor(name) {
  let h = 0;
  for (const c of (name || '')) h = ((h << 5) - h + c.charCodeAt(0)) | 0;
  return ROOM_COLORS[Math.abs(h) % ROOM_COLORS.length];
}

// ── Navbar ───────────────────────────────────────────────────────────────────

function initNavbar() {
  const user = getUser();
  if (!user) return;
  document.getElementById('nav-user-name').textContent = user.display_name || user.username;
  const av = document.getElementById('nav-user-avatar');
  if (user.avatar_url) {
    av.innerHTML = `<img src="${escHtml(user.avatar_url)}" alt="">`;
  } else {
    av.textContent = (user.display_name || user.username || '?')[0].toUpperCase();
  }
}

function initDropdown() {
  const trigger = document.getElementById('user-menu-trigger');
  const menu    = document.getElementById('user-dropdown');
  trigger.addEventListener('click', (e) => {
    e.stopPropagation();
    menu.classList.toggle('open');
  });
  document.addEventListener('click', () => menu.classList.remove('open'));
  document.getElementById('btn-logout').addEventListener('click', () => authLogout());
  document.getElementById('btn-profile').addEventListener('click', () => {
    window.location.href = '/profile/';
  });
}

// ── Notification WebSocket ────────────────────────────────────────────────────

let _notifWs             = null;
let _notifReconnectTimer = null;
let _notifReconnectCount = 0;

function connectNotifications() {
  if (_notifWs) { _notifWs.onclose = null; _notifWs.close(); }
  const proto = location.protocol === 'https:' ? 'wss' : 'ws';
  const url   = `${proto}://${location.host}/ws/notifications/?token=${getAccessToken()}`;

  _notifWs = new WebSocket(url);

  _notifWs.onopen = () => { _notifReconnectCount = 0; };

  _notifWs.onmessage = (e) => {
    const msg = JSON.parse(e.data);
    if (msg.type === 'unread_update' && msg.room_slug !== _activeSlug) {
      bumpRoomBadge(msg.room_slug);
    }
  };

  _notifWs.onclose = () => {
    if (_notifReconnectCount >= 5) return;
    const delay = Math.min(1000 * 2 ** _notifReconnectCount, 12000);
    _notifReconnectCount++;
    _notifReconnectTimer = setTimeout(connectNotifications, delay);
  };
}

function bumpRoomBadge(slug) {
  const item = document.querySelector(`.room-item[data-slug="${slug}"]`);
  if (!item) return;
  let badge = item.querySelector('.unread-badge');
  if (!badge) {
    badge = document.createElement('span');
    badge.className = 'unread-badge';
    badge.textContent = '1';
    item.querySelector('.room-meta').appendChild(badge);
  } else {
    badge.textContent = String(parseInt(badge.textContent || '0', 10) + 1);
  }
}

function clearRoomBadge(slug) {
  document.querySelector(`.room-item[data-slug="${slug}"] .unread-badge`)?.remove();
}

// ── Room sidebar ─────────────────────────────────────────────────────────────

let _activeSlug = null;

function renderRoomItem(room) {
  const item = document.createElement('div');
  item.className = 'room-item' + (room.slug === _activeSlug ? ' active' : '');
  item.dataset.slug = room.slug;

  const color   = roomColor(room.name);
  const initial = (room.name || '?')[0].toUpperCase();

  let preview = 'No messages yet';
  if (room.last_message) {
    preview = room.last_message.message_type === 'text'
      ? room.last_message.content || ''
      : '[' + room.last_message.message_type + ']';
  }

  const time  = room.last_message ? relativeTime(room.last_message.timestamp) : '';
  const badge = room.unread_count > 0
    ? `<span class="unread-badge">${room.unread_count}</span>` : '';

  item.innerHTML = `
    <div class="room-icon" style="background:${color}">${initial}</div>
    <div class="room-info">
      <div class="room-name">${escHtml(room.name)}</div>
      <div class="room-preview">${escHtml(preview)}</div>
    </div>
    <div class="room-meta">
      <span class="room-time">${escHtml(time)}</span>
      ${badge}
    </div>`;

  item.addEventListener('click', () => selectRoom(room));
  return item;
}

async function loadDashboard() {
  const list = document.getElementById('room-list');
  list.innerHTML = '<div class="loading-state"><div class="spinner"></div></div>';

  const res = await apiFetch('/api/dashboard/');
  if (!res.ok) { list.innerHTML = ''; return; }

  const rooms = await res.json();
  list.innerHTML = '';

  if (rooms.length === 0) {
    list.innerHTML = '<div class="room-list-empty">No rooms yet.<br>Create or join one to get started.</div>';
    return;
  }
  rooms.forEach(r => list.appendChild(renderRoomItem(r)));
}

function setActiveItem(slug) {
  document.querySelectorAll('.room-item').forEach(el => {
    el.classList.toggle('active', el.dataset.slug === slug);
  });
}

function showEmptyPanel() {
  document.querySelector('.app-layout')?.classList.remove('room-open');
  document.getElementById('main-panel').innerHTML = `
    <div class="empty-state">
      <div class="empty-state-icon">💬</div>
      <div class="empty-state-title">No room selected</div>
      <div class="empty-state-body">Pick a room from the sidebar or create a new one to start chatting.</div>
      <button class="btn btn-primary" onclick="document.getElementById('btn-new-room').click()">New Room</button>
    </div>`;
}

function selectRoom(room) {
  _activeSlug = room.slug;
  setActiveItem(room.slug);
  clearRoomBadge(room.slug);
  document.querySelector('.app-layout')?.classList.add('room-open');
  history.pushState({ slug: room.slug }, '', '/dashboard/?room=' + room.slug);
  loadRoomPanel(room);  // defined in room.js
}

// ── New-room modal ────────────────────────────────────────────────────────────

function initNewRoomModal() {
  const overlay   = document.getElementById('modal-overlay');
  const openBtn   = document.getElementById('btn-new-room');
  const closeBtn  = document.getElementById('modal-close');
  const cancelBtn = document.getElementById('modal-cancel');
  const form      = document.getElementById('new-room-form');
  const submitBtn = document.getElementById('modal-submit');
  const errorEl   = document.getElementById('modal-error');

  const open = () => {
    form.reset();
    errorEl.classList.remove('visible');
    overlay.classList.add('open');
    document.getElementById('room-name-input').focus();
  };
  const close = () => overlay.classList.remove('open');

  openBtn.addEventListener('click', open);
  closeBtn.addEventListener('click', close);
  cancelBtn.addEventListener('click', close);
  overlay.addEventListener('click', (e) => { if (e.target === overlay) close(); });

  form.addEventListener('submit', async (e) => {
    e.preventDefault();
    const name = document.getElementById('room-name-input').value.trim();
    const desc = document.getElementById('room-desc-input').value.trim();
    if (!name) return;

    submitBtn.disabled    = true;
    submitBtn.textContent = 'Creating…';
    errorEl.classList.remove('visible');

    const res  = await apiFetch('/api/rooms/', { method: 'POST', body: JSON.stringify({ name, description: desc }) });
    const data = await res.json();

    submitBtn.disabled    = false;
    submitBtn.textContent = 'Create Room';

    if (!res.ok) {
      const msg = data.error?.name?.[0] || data.error || 'Failed to create room.';
      errorEl.textContent = typeof msg === 'string' ? msg : JSON.stringify(msg);
      errorEl.classList.add('visible');
      return;
    }

    close();
    showToast(`Room "${data.name}" created!`);
    await loadDashboard();
    selectRoom(data);
  });
}

// ── Boot ──────────────────────────────────────────────────────────────────────

document.addEventListener('DOMContentLoaded', async () => {
  initNavbar();
  initDropdown();
  initNewRoomModal();
  await loadDashboard();
  connectNotifications();

  // Auto-open a room when the URL contains ?room=<slug> (e.g. after joining)
  const slug = new URLSearchParams(window.location.search).get('room');
  if (slug) {
    const item = document.querySelector(`.room-item[data-slug="${slug}"]`);
    if (item) item.click();
  }

  document.getElementById('btn-new-room-empty')?.addEventListener('click', () => {
    document.getElementById('btn-new-room').click();
  });
});
