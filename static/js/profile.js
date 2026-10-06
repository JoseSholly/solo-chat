/* Profile page — depends on api.js, auth.js, ui.js */

let _profileData = null;

const $ = (id) => document.getElementById(id);

function _syncSession(user) {
  storeSession({
    access:  getAccessToken(),
    refresh: getRefreshToken(),
    user:    { ...(getUser() || {}), ...user },
  });
}

// ── Load & render ─────────────────────────────────────────────────────────────

async function loadProfile() {
  // Cached copy renders instantly while the fresh one loads
  const cached = getUser();
  if (cached) applyView(cached);

  const res = await apiFetch('/api/auth/me/');
  if (!res.ok) return;
  const user = await res.json();
  _syncSession(user);
  applyView(user);
}

function renderAvatar(user, url = user.avatar_url) {
  $('profile-avatar').innerHTML = avatarHtml({ name: user.display_name || user.username, url, size: '2xl' });
}

function applyView(user) {
  _profileData = user;
  renderAvatar(user);
  $('view-display-name').textContent = user.display_name || user.username || '';
  $('view-username').textContent     = '@' + (user.username || '');
  const bio = $('view-bio');
  bio.textContent = user.bio || 'No bio yet.';
  bio.classList.toggle('is-empty', !user.bio);
  $('view-email').textContent  = user.email || '';
  $('view-joined').textContent = user.date_joined
    ? new Date(user.date_joined).toLocaleDateString([], { year: 'numeric', month: 'long', day: 'numeric' })
    : '';
  document.title = `${user.display_name || user.username} — Solo-Chat`;
}

// ── Edit mode ────────────────────────────────────────────────────────────────

function _bioCount() {
  const n = $('edit-bio').value.length;
  $('bio-count').textContent = n ? `${n}` : '';
}

function startEdit() {
  const user = _profileData || getUser();
  $('edit-display-name').value = user.display_name || '';
  $('edit-bio').value          = user.bio || '';
  _bioCount();
  $('profile-error').classList.remove('is-visible');
  $('view-mode').hidden = true;
  $('edit-mode').hidden = false;
  $('edit-display-name').focus();
}

function cancelEdit() {
  $('edit-mode').hidden = true;
  $('view-mode').hidden = false;
  $('btn-edit').focus();
}

async function saveProfile() {
  const displayName = $('edit-display-name').value.trim();
  const bio         = $('edit-bio').value.trim();
  const errorEl     = $('profile-error');
  errorEl.classList.remove('is-visible');

  if (!displayName) {
    errorEl.textContent = 'Your name can\'t be empty.';
    errorEl.classList.add('is-visible');
    $('edit-display-name').setAttribute('aria-invalid', 'true');
    $('edit-display-name').focus();
    return;
  }

  const btn = $('btn-save');
  btn.disabled = true;
  btn.textContent = 'Saving…';

  const res  = await apiFetch('/api/auth/me/', {
    method: 'PATCH',
    body:   JSON.stringify({ display_name: displayName, bio }),
  });
  const data = await res.json().catch(() => ({}));

  btn.disabled = false;
  btn.textContent = 'Save';

  if (!res.ok) {
    const msg = data.error?.display_name?.[0] || data.error?.bio?.[0] || data.error || 'Couldn\'t save your changes.';
    errorEl.textContent = typeof msg === 'string' ? msg : JSON.stringify(msg);
    errorEl.classList.add('is-visible');
    return;
  }

  _syncSession(data);
  applyView(data);
  cancelEdit();
  flashButton($('btn-edit'), `${icon('check', 16)} Saved`);
  announce('Profile saved');
}

// ── Avatar upload ─────────────────────────────────────────────────────────────

async function uploadAvatar(file) {
  if (!file.type.startsWith('image/')) { showToast('Choose an image file.', 'error'); return; }

  const wrap = $('profile-avatar-wrap');
  const ring = wrap.querySelector('.profile-avatar-ring');
  const user = _profileData || getUser();
  const preview = URL.createObjectURL(file);

  // Show the new photo right away; the ring tracks the real upload.
  renderAvatar(user, preview);
  ring.style.setProperty('--p', 0);
  wrap.classList.add('is-uploading');
  wrap.disabled = true;

  const form = new FormData();
  form.append('avatar', file);
  const res = await apiUpload('/api/auth/me/', form, {
    method: 'PATCH',
    onProgress: (p) => ring.style.setProperty('--p', p),
  });

  wrap.classList.remove('is-uploading');
  wrap.disabled = false;
  URL.revokeObjectURL(preview);

  if (!res.ok) {
    renderAvatar(user);
    const msg = res.data?.error?.avatar?.[0] || 'Photo upload failed.';
    showToast(msg, 'error');
    return;
  }

  _syncSession(res.data);
  applyView(res.data);
  wrap.classList.remove('is-updated');
  void wrap.offsetWidth;
  wrap.classList.add('is-updated');
  showToast('Photo updated.');
}

// ── Boot ──────────────────────────────────────────────────────────────────────

document.addEventListener('DOMContentLoaded', () => {
  loadProfile();

  $('btn-logout').addEventListener('click', () => authLogout());
  $('btn-edit').addEventListener('click', startEdit);
  $('btn-cancel').addEventListener('click', cancelEdit);
  $('edit-mode').addEventListener('submit', (e) => { e.preventDefault(); saveProfile(); });
  $('edit-bio').addEventListener('input', _bioCount);
  $('edit-display-name').addEventListener('input', (e) => e.target.removeAttribute('aria-invalid'));
  $('edit-mode').addEventListener('keydown', (e) => { if (e.key === 'Escape') cancelEdit(); });

  $('profile-avatar-wrap').addEventListener('click', () => $('avatar-file-input').click());
  $('avatar-file-input').addEventListener('change', () => {
    const f = $('avatar-file-input').files[0];
    $('avatar-file-input').value = '';
    if (f) uploadAvatar(f);
  });
});
