/* Room panel — depends on api.js, auth.js, dashboard.js */

const _AVATAR_COLORS = ['#6366f1','#8b5cf6','#ec4899','#f97316','#14b8a6','#0ea5e9','#84cc16'];

function _avatarColor(name) {
  let h = 0;
  for (const c of (name || '')) h = ((h << 5) - h + c.charCodeAt(0)) | 0;
  return _AVATAR_COLORS[Math.abs(h) % _AVATAR_COLORS.length];
}

let _activePanel = null;

function destroyActivePanel() {
  if (_activePanel) { _activePanel.destroy(); _activePanel = null; }
}

function loadRoomPanel(room) {
  destroyActivePanel();
  _activePanel = new RoomPanel(room, document.getElementById('main-panel'));
}

// ─────────────────────────────────────────────────────────────────────────────

const BACK_SVG = `<svg width="18" height="18" viewBox="0 0 24 24" fill="none"
  stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
  <polyline points="15 18 9 12 15 6"/>
</svg>`;

const PEOPLE_SVG = `<svg width="15" height="15" viewBox="0 0 24 24" fill="none"
  stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
  <path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"/>
  <circle cx="9" cy="7" r="4"/>
  <path d="M23 21v-2a4 4 0 0 0-3-3.87"/>
  <path d="M16 3.13a4 4 0 0 1 0 7.75"/>
</svg>`;

const LINK_SVG = `<svg width="14" height="14" viewBox="0 0 24 24" fill="none"
  stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
  <path d="M10 13a5 5 0 0 0 7.54.54l3-3a5 5 0 0 0-7.07-7.07l-1.72 1.71"/>
  <path d="M14 11a5 5 0 0 0-7.54-.54l-3 3a5 5 0 0 0 7.07 7.07l1.71-1.71"/>
</svg>`;

const SEND_SVG = `<svg width="15" height="15" viewBox="0 0 24 24" fill="none"
  stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
  <line x1="22" y1="2" x2="11" y2="13"/>
  <polygon points="22 2 15 22 11 13 2 9 22 2"/>
</svg>`;

const MIC_SVG = `<svg width="15" height="15" viewBox="0 0 24 24" fill="none"
  stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
  <path d="M12 1a3 3 0 0 0-3 3v8a3 3 0 0 0 6 0V4a3 3 0 0 0-3-3z"/>
  <path d="M19 10v2a7 7 0 0 1-14 0v-2"/>
  <line x1="12" y1="19" x2="12" y2="23"/>
  <line x1="8" y1="23" x2="16" y2="23"/>
</svg>`;

const IMAGE_SVG = `<svg width="15" height="15" viewBox="0 0 24 24" fill="none"
  stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
  <rect x="3" y="3" width="18" height="18" rx="2" ry="2"/>
  <circle cx="8.5" cy="8.5" r="1.5"/>
  <polyline points="21 15 16 10 5 21"/>
</svg>`;

const EDIT_SVG = `<svg width="15" height="15" viewBox="0 0 24 24" fill="none"
  stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
  <path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"/>
  <path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"/>
</svg>`;

const LEAVE_SVG = `<svg width="15" height="15" viewBox="0 0 24 24" fill="none"
  stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
  <path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4"/>
  <polyline points="16 17 21 12 16 7"/>
  <line x1="21" y1="12" x2="9" y2="12"/>
</svg>`;

const TRASH_SVG = `<svg width="15" height="15" viewBox="0 0 24 24" fill="none"
  stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
  <polyline points="3 6 5 6 21 6"/>
  <path d="M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6"/>
  <path d="M10 11v6"/><path d="M14 11v6"/>
</svg>`;

// ─────────────────────────────────────────────────────────────────────────────

class RoomPanel {
  constructor(room, container) {
    this.room             = room;
    this.container        = container;
    this.ws               = null;
    this.wsReady          = false;
    this.reconnectCount   = 0;
    this.maxReconnects    = 5;
    this._reconnectTimer  = null;
    this._userScrolled    = false;
    this.onlineUsers      = new Set();

    this._markSeenTimer = null;

    this._membersOffset  = 0;
    this._membersHasMore = true;
    this._membersLoading = false;
    this._membersObserver = null;

    this._render();
    this._bindEvents();
    this._loadHistory();
    this._connectWS();
    this._loadMembers();
  }

  // ── Render ────────────────────────────────────────────────────────────────

  _render() {
    const r = this.room;
    const editBtn = r.is_creator
      ? `<button class="btn-icon" id="rp-edit" title="Edit room">${EDIT_SVG}</button>`
      : '';
    const actionBtn = r.is_creator
      ? `<button class="btn-icon" id="rp-delete" title="Delete room" style="color:var(--error)">${TRASH_SVG}</button>`
      : `<button class="btn-icon" id="rp-leave"  title="Leave room">${LEAVE_SVG}</button>`;

    this.container.innerHTML = `
      <div class="room-panel">
        <div class="room-header">
          <button class="btn-icon rp-back-btn" id="rp-back" title="Back to rooms" aria-label="Back to rooms">
            ${BACK_SVG}
          </button>
          <div>
            <span class="room-header-name">${escHtml(r.name)}</span>
            <span class="room-header-meta" id="rp-meta">${r.member_count} member${r.member_count !== 1 ? 's' : ''}</span>
          </div>
          <div class="room-header-spacer"></div>
          <button class="btn btn-ghost rp-copy-btn" id="rp-copy-link" style="font-size:13px;height:32px">
            ${LINK_SVG}<span class="rp-copy-label">Copy Invite Link</span>
          </button>
          <button class="btn-icon rp-members-btn" id="rp-members-btn" title="Members" aria-label="Toggle members">
            ${PEOPLE_SVG}
          </button>
          ${editBtn}
          ${actionBtn}
        </div>

        <div class="ws-status hidden" id="rp-status"></div>

        <div class="room-body" id="rp-body">
          <div class="members-backdrop" id="rp-backdrop"></div>

          <div class="chat-column">
            <div class="chat-area" id="rp-chat"></div>
            <div class="chat-input-bar">
              <input type="file" id="rp-img-file"   accept="image/*" style="display:none">
              <input type="file" id="rp-voice-file" accept="audio/*" style="display:none">
              <button class="btn-icon" id="rp-img-btn"   title="Send image"      disabled>${IMAGE_SVG}</button>
              <button class="btn-icon" id="rp-voice-btn" title="Send voice note" disabled>${MIC_SVG}</button>
              <input class="chat-input" type="text" id="rp-input"
                     placeholder="Message…" autocomplete="off" disabled>
              <button class="btn btn-primary" id="rp-send" disabled
                      style="width:38px;height:38px;padding:0;flex-shrink:0">${SEND_SVG}</button>
            </div>
          </div>

          <div class="members-panel" id="rp-members-panel">
            <div class="members-panel-header" id="rp-members-header">MEMBERS</div>
            <div class="members-list" id="rp-members-list">
              <div class="loading-state" style="padding:20px 0"><div class="spinner"></div></div>
            </div>
          </div>
        </div>
      </div>`;

    this._el = {
      chat:      document.getElementById('rp-chat'),
      input:     document.getElementById('rp-input'),
      send:      document.getElementById('rp-send'),
      imgBtn:    document.getElementById('rp-img-btn'),
      imgFile:   document.getElementById('rp-img-file'),
      voiceBtn:  document.getElementById('rp-voice-btn'),
      voiceFile: document.getElementById('rp-voice-file'),
      status:    document.getElementById('rp-status'),
      meta:      document.getElementById('rp-meta'),
    };
  }

  // ── Events ────────────────────────────────────────────────────────────────

  _bindEvents() {
    document.getElementById('rp-back')?.addEventListener('click', () => {
      document.querySelector('.app-layout')?.classList.remove('room-open');
    });

    document.getElementById('rp-members-btn')?.addEventListener('click', () => this._toggleMembers());
    document.getElementById('rp-backdrop')?.addEventListener('click', () => this._closeMembersDrawer());

    document.getElementById('rp-copy-link').addEventListener('click', () => {
      const link = `${location.origin}/join/${this.room.slug}/`;
      navigator.clipboard.writeText(link).then(() => showToast('Invite link copied!'));
    });

    const leaveBtn  = document.getElementById('rp-leave');
    const deleteBtn = document.getElementById('rp-delete');
    const editBtn   = document.getElementById('rp-edit');
    if (leaveBtn)  leaveBtn.addEventListener('click',  () => this._leaveRoom());
    if (deleteBtn) deleteBtn.addEventListener('click', () => this._deleteRoom());
    if (editBtn)   editBtn.addEventListener('click',   () => this._openEditModal());

    this._el.send.addEventListener('click', () => this._sendText());
    this._el.input.addEventListener('keydown', (e) => {
      if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); this._sendText(); }
    });

    this._el.imgBtn.addEventListener('click', () => this._el.imgFile.click());
    this._el.imgFile.addEventListener('change', () => {
      const f = this._el.imgFile.files[0];
      if (f) this._uploadImage(f);
      this._el.imgFile.value = '';
    });

    this._el.voiceBtn.addEventListener('click',  () => this._el.voiceFile.click());
    this._el.voiceFile.addEventListener('change', () => {
      const f = this._el.voiceFile.files[0];
      if (f) this._uploadVoice(f);
      this._el.voiceFile.value = '';
    });

    this._el.chat.addEventListener('scroll', () => {
      this._userScrolled = !this._isAtBottom();
    });

    // Image click → lightbox
    this._el.chat.addEventListener('click', (e) => {
      const img = e.target.closest('img[data-lightbox-src]');
      if (img) { this._openLightbox(img.dataset.lightboxSrc); return; }
    });

    // Avatar click → profile modal
    this._el.chat.addEventListener('click', (e) => {
      const av = e.target.closest('.msg-avatar.clickable');
      if (!av) return;
      if (av.dataset.own === 'true') {
        this._openOwnProfileModal();
      } else if (av.dataset.username) {
        this._fetchAndShowProfile({
          username:     av.dataset.username,
          display_name: av.dataset.displayName || av.dataset.username,
          avatar_url:   av.dataset.avatarUrl   || null,
        });
      }
    });
  }

  // ── History ───────────────────────────────────────────────────────────────

  async _loadHistory() {
    this._el.chat.innerHTML = '<div class="loading-state"><div class="spinner"></div></div>';
    const res = await apiFetch(`/api/rooms/${this.room.slug}/`);
    if (!res.ok) { this._el.chat.innerHTML = ''; return; }

    const data = await res.json();
    this.room = { ...this.room, ...data.room };
    this._updateMeta();
    this._syncEditButton();

    this._el.chat.innerHTML = '';
    if (data.messages.length === 0) {
      this._appendSystem('No messages yet. Say hello!');
    } else {
      data.messages.forEach(m => this._appendMessage(m, false));
    }
    this._scrollToBottom(false);
  }

  // ── WebSocket ─────────────────────────────────────────────────────────────

  _connectWS() {
    const proto = location.protocol === 'https:' ? 'wss' : 'ws';
    const url   = `${proto}://${location.host}/ws/chat/${this.room.slug}/?token=${getAccessToken()}`;
    this._setStatus('Connecting…', 'connecting');

    this.ws = new WebSocket(url);

    this.ws.onopen = () => {
      this.wsReady       = true;
      this.reconnectCount = 0;
      this._setStatus('', '');
      this._enableInput(true);
    };

    this.ws.onmessage = (e) => {
      const msg = JSON.parse(e.data);
      if (msg.type === 'chat_message')  this._appendMessage(msg, true);
      if (msg.type === 'presence_event') this._handlePresence(msg);
    };

    this.ws.onclose = (e) => {
      this.wsReady = false;
      this._enableInput(false);
      if (e.code === 4001 || e.code === 4003 || e.code === 4004) {
        this._setStatus('Cannot connect — check your membership.', 'error');
        return;
      }
      this._scheduleReconnect();
    };

    this.ws.onerror = () => { this.wsReady = false; this._enableInput(false); };
  }

  _scheduleReconnect() {
    if (this.reconnectCount >= this.maxReconnects) {
      this._setStatus('Connection lost. Refresh the page to retry.', 'error');
      return;
    }
    const delay = Math.min(1000 * 2 ** this.reconnectCount, 12000);
    this.reconnectCount++;
    this._setStatus('Reconnecting…', 'connecting');
    this._reconnectTimer = setTimeout(() => this._connectWS(), delay);
  }

  // ── Presence ──────────────────────────────────────────────────────────────

  _handlePresence(msg) {
    if (msg.event === 'join') this.onlineUsers.add(msg.username);
    else this.onlineUsers.delete(msg.username);
    this._updateMeta();
    this._updateMemberDot(msg.username, msg.event === 'join');
  }

  _updateMeta() {
    if (!this._el.meta) return;
    const mc = this.room.member_count;
    const oc = this.onlineUsers.size;
    this._el.meta.textContent =
      `${mc} member${mc !== 1 ? 's' : ''}${oc > 0 ? ' · ' + oc + ' online' : ''}`;
  }

  _syncEditButton() {
    const header = this.container.querySelector('.room-header');
    if (!header) return;

    const existing = header.querySelector('#rp-edit');

    if (!this.room.is_creator) {
      existing?.remove();
      return;
    }

    if (existing) return; // already present

    const btn = document.createElement('button');
    btn.className = 'btn-icon';
    btn.id        = 'rp-edit';
    btn.title     = 'Edit room';
    btn.innerHTML = EDIT_SVG;
    btn.addEventListener('click', () => this._openEditModal());

    // Insert before the delete/leave button
    const actionBtn = header.querySelector('#rp-delete') || header.querySelector('#rp-leave');
    if (actionBtn) actionBtn.before(btn);
    else header.appendChild(btn);
  }

  // ── Messaging ─────────────────────────────────────────────────────────────

  _sendText() {
    if (!this.wsReady) return;
    const content = this._el.input.value.trim();
    if (!content) return;
    this.ws.send(JSON.stringify({ type: 'text', content }));
    this._el.input.value = '';
  }

  async _uploadImage(file) {
    this._enableInput(false);
    showToast('Uploading…');

    const form = new FormData();
    form.append('file', file);
    form.append('message_type', 'image');

    const res = await apiFetch(`/api/rooms/${this.room.slug}/upload/`, {
      method: 'POST',
      body:   form,
    });
    this._enableInput(true);

    if (!res.ok) { showToast('Upload failed.', 'error'); return; }
    const msg = await res.json();

    if (this.wsReady) {
      this.ws.send(JSON.stringify({
        type:      'image',
        id:        msg.id,
        file_url:  msg.file_url,
        timestamp: msg.timestamp,
      }));
    }
  }

  async _uploadVoice(file) {
    this._enableInput(false);
    showToast('Uploading…');

    const form = new FormData();
    form.append('file', file);
    form.append('message_type', 'voice');

    const res = await apiFetch(`/api/rooms/${this.room.slug}/upload/`, {
      method: 'POST',
      body:   form,
    });
    this._enableInput(true);

    if (!res.ok) { showToast('Upload failed.', 'error'); return; }
    const msg = await res.json();

    if (this.wsReady) {
      this.ws.send(JSON.stringify({
        type:      'voice',
        id:        msg.id,
        file_url:  msg.file_url,
        timestamp: msg.timestamp,
      }));
    }
  }

  // ── Leave / delete ────────────────────────────────────────────────────────

  async _leaveRoom() {
    if (!confirm(`Leave "${this.room.name}"?`)) return;
    const res = await apiFetch(`/api/rooms/${this.room.slug}/leave/`, { method: 'POST' });
    if (!res.ok) {
      const d = await res.json().catch(() => ({}));
      showToast(d.error || 'Could not leave room.', 'error');
      return;
    }
    this.destroy();
    showToast('You left the room.');
    _activeSlug = null;
    await loadDashboard();
    showEmptyPanel();
    history.pushState({}, '', '/dashboard/');
  }

  async _deleteRoom() {
    if (!confirm(`Delete "${this.room.name}"? This cannot be undone.`)) return;
    const res = await apiFetch(`/api/rooms/${this.room.slug}/delete/`, { method: 'DELETE' });
    if (!res.ok) {
      const d = await res.json().catch(() => ({}));
      showToast(d.error || 'Could not delete room.', 'error');
      return;
    }
    this.destroy();
    showToast(`"${this.room.name}" was deleted.`);
    _activeSlug = null;
    await loadDashboard();
    showEmptyPanel();
    history.pushState({}, '', '/dashboard/');
  }

  // ── Edit room ─────────────────────────────────────────────────────────────

  _openEditModal() {
    const existing = document.getElementById('rp-edit-modal-overlay');
    if (existing) existing.remove();

    const overlay = document.createElement('div');
    overlay.id = 'rp-edit-modal-overlay';
    overlay.className = 'modal-overlay open';
    overlay.innerHTML = `
      <div class="modal" role="dialog" aria-modal="true" aria-labelledby="rp-edit-title">
        <div class="modal-header">
          <span class="modal-title" id="rp-edit-title">Edit Room</span>
          <button class="modal-close" id="rp-edit-close" aria-label="Close">&#x2715;</button>
        </div>
        <form id="rp-edit-form">
          <div class="modal-body">
            <div id="rp-edit-error" class="form-error"></div>
            <div class="form-group">
              <label class="form-label" for="rp-edit-name">Room Name</label>
              <input class="form-input" type="text" id="rp-edit-name"
                     value="${escHtml(this.room.name)}" maxlength="100" required>
            </div>
            <div class="form-group">
              <label class="form-label" for="rp-edit-desc">
                Description <span style="color:var(--text-muted)">(optional)</span>
              </label>
              <textarea class="form-input" id="rp-edit-desc"
                        rows="2">${escHtml(this.room.description || '')}</textarea>
            </div>
          </div>
          <div class="modal-footer">
            <button type="button" class="btn btn-ghost" id="rp-edit-cancel">Cancel</button>
            <button type="submit" class="btn btn-primary" id="rp-edit-submit">Save</button>
          </div>
        </form>
      </div>`;

    document.body.appendChild(overlay);

    const close = () => { overlay.remove(); document.removeEventListener('keydown', onKey); };
    const onKey = (e) => { if (e.key === 'Escape') close(); };
    document.addEventListener('keydown', onKey);

    overlay.addEventListener('click',                    (e) => { if (e.target === overlay) close(); });
    document.getElementById('rp-edit-close').addEventListener('click', close);
    document.getElementById('rp-edit-cancel').addEventListener('click', close);
    document.getElementById('rp-edit-form').addEventListener('submit', (e) => {
      e.preventDefault();
      this._submitEdit(close);
    });

    document.getElementById('rp-edit-name').focus();
  }

  async _submitEdit(closeModal) {
    const nameInput = document.getElementById('rp-edit-name');
    const descInput = document.getElementById('rp-edit-desc');
    const errorEl   = document.getElementById('rp-edit-error');
    const submitBtn = document.getElementById('rp-edit-submit');

    const name        = nameInput.value.trim();
    const description = descInput.value.trim();

    errorEl.textContent = '';
    errorEl.classList.remove('visible');

    if (!name) {
      errorEl.textContent = 'Room name is required.';
      errorEl.classList.add('visible');
      nameInput.focus();
      return;
    }

    submitBtn.disabled = true;
    submitBtn.textContent = 'Saving…';

    const res = await apiFetch(`/api/rooms/${this.room.slug}/update/`, {
      method:  'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body:    JSON.stringify({ name, description }),
    });

    submitBtn.disabled = false;
    submitBtn.textContent = 'Save';

    if (!res.ok) {
      const d = await res.json().catch(() => ({}));
      errorEl.textContent = d.error || 'Could not save changes.';
      errorEl.classList.add('visible');
      return;
    }

    const updated = await res.json();
    this.room.name        = updated.name;
    this.room.description = updated.description;

    // Update header
    const nameEl = this.container.querySelector('.room-header-name');
    if (nameEl) nameEl.textContent = updated.name;

    // Update sidebar
    const sidebarItem = document.querySelector(`.room-item[data-slug="${updated.slug}"] .room-name`);
    if (sidebarItem) sidebarItem.textContent = updated.name;

    closeModal();
    showToast('Room updated.');
  }

  // ── Render messages ───────────────────────────────────────────────────────

  _appendMessage(data, smooth) {
    const user  = getUser();
    const isOwn = user && (String(data.sender_id) === String(user.id) || data.username === user.username);
    const wasAtBottom = this._isAtBottom();

    const row = document.createElement('div');
    row.className = 'message-row ' + (isOwn ? 'own' : 'other');

    // Bubble content
    let bubbleContent = '';
    if (data.message_type === 'voice') {
      bubbleContent = `<audio controls src="${escHtml(data.file_url || '')}"></audio>`;
    } else if (data.message_type === 'image') {
      const src = escHtml(data.file_url || '');
      bubbleContent = `<img src="${src}" alt="image" loading="lazy" data-lightbox-src="${src}">`;
    } else {
      bubbleContent = escHtml(data.content || '');
    }

    // Avatar
    const avatarUrl  = isOwn ? (user.avatar_url || null) : (data.avatar_url || null);
    const avatarName = isOwn ? (user.display_name || user.username) : (data.display_name || data.username);
    const initial    = (avatarName || '?')[0].toUpperCase();
    const color      = _avatarColor(avatarName);
    const inner      = avatarUrl ? `<img src="${escHtml(avatarUrl)}" alt="">` : initial;

    let avatarHtml;
    if (isOwn) {
      avatarHtml = `<span class="msg-avatar clickable"
                         style="background:${color}"
                         data-own="true"
                         role="button" tabindex="0"
                         title="Your profile"
                         aria-label="View your profile">${inner}</span>`;
    } else {
      avatarHtml = `<span class="msg-avatar clickable"
                         style="background:${color}"
                         data-username="${escHtml(data.username || '')}"
                         data-display-name="${escHtml(data.display_name || data.username || '')}"
                         data-avatar-url="${escHtml(avatarUrl || '')}"
                         data-color="${color}"
                         role="button"
                         tabindex="0"
                         aria-label="View ${escHtml(avatarName)} profile">${inner}</span>`;
    }

    row.innerHTML = `
      ${avatarHtml}
      <div class="msg-body">
        ${!isOwn ? `<div class="message-sender">${escHtml(data.display_name || data.username)}</div>` : ''}
        <div class="message-bubble">${bubbleContent}</div>
        <div class="message-time">${relativeTime(data.timestamp)}</div>
      </div>`;

    this._el.chat.appendChild(row);
    if (wasAtBottom || !this._userScrolled) this._scrollToBottom(smooth);
    if (smooth) this._markSeen();
  }

  _appendSystem(text) {
    const el = document.createElement('div');
    el.className = 'system-message';
    el.textContent = text;
    this._el.chat.appendChild(el);
    if (!this._userScrolled) this._scrollToBottom(true);
  }

  _openLightbox(src) {
    const overlay = document.createElement('div');
    overlay.className = 'img-lightbox';
    overlay.innerHTML = `
      <button class="img-lightbox-close" aria-label="Close">
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none"
             stroke="currentColor" stroke-width="2.5" stroke-linecap="round">
          <line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/>
        </svg>
      </button>
      <img src="${escHtml(src)}" alt="image">
    `;
    document.body.appendChild(overlay);

    const close = () => {
      overlay.remove();
      document.removeEventListener('keydown', onKey);
    };
    const onKey = (e) => { if (e.key === 'Escape') close(); };

    overlay.addEventListener('click', (e) => { if (e.target === overlay) close(); });
    overlay.querySelector('.img-lightbox-close').addEventListener('click', close);
    document.addEventListener('keydown', onKey);
  }

  // ── Helpers ───────────────────────────────────────────────────────────────

  _markSeen() {
    clearTimeout(this._markSeenTimer);
    this._markSeenTimer = setTimeout(() => {
      apiFetch(`/api/rooms/${this.room.slug}/seen/`, { method: 'PATCH' });
    }, 2000);
  }

  _enableInput(on) {
    this._el.input.disabled    = !on;
    this._el.send.disabled     = !on;
    this._el.imgBtn.disabled   = !on;
    this._el.voiceBtn.disabled = !on;
  }

  _setStatus(text, type) {
    const el = this._el.status;
    if (!el) return;
    if (!text) { el.className = 'ws-status hidden'; return; }
    el.className   = 'ws-status ' + type;
    el.textContent = text;
  }

  _isAtBottom() {
    const c = this._el.chat;
    return c.scrollHeight - c.scrollTop - c.clientHeight < 80;
  }

  _scrollToBottom(smooth) {
    this._el.chat.scrollTo({
      top:      this._el.chat.scrollHeight,
      behavior: smooth ? 'smooth' : 'instant',
    });
  }

  _openProfileModal(data, isOwn) {
    this._closeProfileModal();

    const color   = _avatarColor(data.display_name || data.username);
    const initial = (data.display_name || data.username || '?')[0].toUpperCase();
    const inner   = data.avatar_url
      ? `<img src="${escHtml(data.avatar_url)}" alt="">`
      : initial;

    const overlay = document.createElement('div');
    overlay.className = 'profile-modal-overlay';

    const CLOSE_SVG = `<svg width="14" height="14" viewBox="0 0 24 24" fill="none"
      stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
      <line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/>
    </svg>`;

    overlay.innerHTML = `
      <div class="profile-modal" role="dialog" aria-modal="true">
        <button class="profile-modal-close" aria-label="Close">${CLOSE_SVG}</button>
        <div class="profile-modal-avatar" style="background:${color}">${inner}</div>
        <div class="profile-modal-name">${escHtml(data.display_name || data.username)}</div>
        <div class="profile-modal-username">@${escHtml(data.username || '')}</div>
        <div id="pm-body"></div>
        ${isOwn ? `
          <div class="profile-modal-actions">
            <a href="/profile/" class="btn btn-ghost btn-full" style="font-size:13px;height:34px">
              Edit Profile
            </a>
          </div>` : ''}
      </div>`;

    document.body.appendChild(overlay);
    this._profileModalEl = overlay;

    overlay.querySelector('.profile-modal-close').addEventListener('click', () => this._closeProfileModal());
    overlay.addEventListener('click', (e) => { if (e.target === overlay) this._closeProfileModal(); });
    this._escHandler = (e) => { if (e.key === 'Escape') this._closeProfileModal(); };
    document.addEventListener('keydown', this._escHandler);
  }

  _fillProfileBody(data) {
    const body = document.getElementById('pm-body');
    if (!body) return;
    const joined = data.date_joined
      ? new Date(data.date_joined).toLocaleDateString(undefined, { year: 'numeric', month: 'long' })
      : null;
    let html = '';
    if (data.bio) {
      html += `<div class="profile-modal-divider"></div>
               <p class="profile-modal-bio">${escHtml(data.bio)}</p>`;
    }
    if (joined) {
      html += `<div class="profile-modal-divider"></div>
               <p class="profile-modal-meta">Member since ${escHtml(joined)}</p>`;
    }
    body.innerHTML = html;
  }

  _closeProfileModal() {
    this._profileModalEl?.remove();
    this._profileModalEl = null;
    if (this._escHandler) {
      document.removeEventListener('keydown', this._escHandler);
      this._escHandler = null;
    }
  }

  // ── Members panel ─────────────────────────────────────────────────────────

  _toggleMembers() {
    document.getElementById('rp-body')?.classList.toggle('members-open');
  }

  _closeMembersDrawer() {
    document.getElementById('rp-body')?.classList.remove('members-open');
  }

  async _loadMembers() {
    if (this._membersLoading || !this._membersHasMore) return;
    this._membersLoading = true;

    const list = document.getElementById('rp-members-list');
    if (!list) { this._membersLoading = false; return; }

    const res = await apiFetch(
      `/api/rooms/${this.room.slug}/members/?limit=20&offset=${this._membersOffset}`
    );
    this._membersLoading = false;
    if (!res.ok) return;

    const data = await res.json();

    // First page: clear the spinner
    if (this._membersOffset === 0) list.innerHTML = '';

    // Remove sentinel before appending so order is preserved
    const oldSentinel = document.getElementById('rp-members-sentinel');
    oldSentinel?.remove();

    data.members.forEach(m => list.appendChild(this._buildMemberItem(m)));

    this._membersOffset += data.members.length;
    this._membersHasMore = data.has_more;

    const header = document.getElementById('rp-members-header');
    if (header) header.textContent = `MEMBERS · ${data.total}`;

    if (this._membersHasMore) {
      const sentinel = document.createElement('div');
      sentinel.id = 'rp-members-sentinel';
      sentinel.style.cssText = 'height:1px;flex-shrink:0';
      list.appendChild(sentinel);

      if (!this._membersObserver) {
        this._membersObserver = new IntersectionObserver(
          (entries) => { if (entries[0].isIntersecting) this._loadMembers(); },
          { root: list, threshold: 0 }
        );
      }
      this._membersObserver.observe(sentinel);
    }
  }

  _buildMemberItem(m) {
    const isOnline = this.onlineUsers.has(m.username);
    const color    = _avatarColor(m.display_name || m.username);
    const initial  = (m.display_name || m.username || '?')[0].toUpperCase();
    const inner    = m.avatar_url ? `<img src="${escHtml(m.avatar_url)}" alt="">` : initial;

    const item = document.createElement('div');
    item.className = `member-item ${isOnline ? 'online' : 'offline'}`;
    item.dataset.username = m.username;
    const isCreator = this.room.creator_username && m.username === this.room.creator_username;
    item.innerHTML = `
      <div class="member-avatar-wrap">
        <div class="member-av" style="background:${color}">${inner}</div>
        <span class="member-status-dot ${isOnline ? 'online' : 'offline'}"></span>
      </div>
      <div class="member-info">
        <div class="member-name">
          <span class="member-name-text">${escHtml(m.display_name || m.username)}</span>
          ${isCreator ? '<span class="creator-tag">Creator</span>' : ''}
        </div>
        <div class="member-username">@${escHtml(m.username)}</div>
      </div>`;

    item.addEventListener('click', () => this._fetchAndShowProfile({
      username:     m.username,
      display_name: m.display_name,
      avatar_url:   m.avatar_url,
    }));
    return item;
  }

  _updateMemberDot(username, isOnline) {
    const item = document.querySelector(`#rp-members-list .member-item[data-username="${CSS.escape(username)}"]`);
    if (!item) return;
    item.classList.toggle('online',  isOnline);
    item.classList.toggle('offline', !isOnline);
    const dot = item.querySelector('.member-status-dot');
    if (dot) dot.className = `member-status-dot ${isOnline ? 'online' : 'offline'}`;
  }

  _openOwnProfileModal() {
    const user = getUser();
    if (!user) return;
    this._openProfileModal(user, true);
    this._fillProfileBody(user);
  }

  async _fetchAndShowProfile(preload) {
    this._openProfileModal(preload, false);
    const body = document.getElementById('pm-body');
    if (body) body.innerHTML = `
      <div class="profile-modal-divider"></div>
      <div class="loading-state" style="flex:none;padding:4px 0">
        <div class="spinner" style="width:18px;height:18px;border-width:2px"></div>
      </div>`;

    const res = await apiFetch(`/api/auth/users/${preload.username}/`);
    if (!this._profileModalEl) return;
    if (!res.ok) {
      if (body) body.innerHTML = '';
      return;
    }
    const profile = await res.json();

    // Update header in case display_name / avatar differ from message data
    const modal = this._profileModalEl.querySelector('.profile-modal');
    if (!modal) return;
    const color   = _avatarColor(profile.display_name || profile.username);
    const initial = (profile.display_name || profile.username || '?')[0].toUpperCase();
    const av = modal.querySelector('.profile-modal-avatar');
    if (av) {
      av.style.background = color;
      av.innerHTML = profile.avatar_url
        ? `<img src="${escHtml(profile.avatar_url)}" alt="">`
        : initial;
    }
    modal.querySelector('.profile-modal-name').textContent    = profile.display_name || profile.username;
    modal.querySelector('.profile-modal-username').textContent = '@' + profile.username;
    this._fillProfileBody(profile);
  }

  destroy() {
    this._closeProfileModal();
    if (this._markSeenTimer) clearTimeout(this._markSeenTimer);
    if (this._reconnectTimer) clearTimeout(this._reconnectTimer);
    if (this._membersObserver) { this._membersObserver.disconnect(); this._membersObserver = null; }
    if (this.ws) {
      this.ws.onclose = null;
      this.ws.close();
      this.ws = null;
    }
  }
}
