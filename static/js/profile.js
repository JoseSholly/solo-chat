/* Profile page — depends on api.js, auth.js */

let _profileData = null;

// ── Navbar ────────────────────────────────────────────────────────────────────

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
  const trigger = document.getElementById('user-menu-trigger');
  const menu    = document.getElementById('user-dropdown');
  trigger.addEventListener('click', (e) => { e.stopPropagation(); menu.classList.toggle('open'); });
  document.addEventListener('click', () => menu.classList.remove('open'));
  document.getElementById('btn-logout').addEventListener('click', () => authLogout());
}

// ── Load & render ─────────────────────────────────────────────────────────────

async function loadProfile() {
  // Show cached data instantly while fetch is in-flight
  const cached = getUser();
  if (cached) applyView(cached);

  const res = await apiFetch('/api/auth/me/');
  if (!res.ok) return;
  const user = await res.json();

  // Keep localStorage in sync
  storeSession({
    access:  getAccessToken(),
    refresh: getRefreshToken(),
    user:    { ...(getUser() || {}), ...user },
  });
  applyView(user);
}

function applyView(user) {
  _profileData = user;

  const av = document.getElementById('profile-avatar');
  if (user.avatar_url) {
    av.innerHTML = `<img src="${escHtml(user.avatar_url)}" alt="">`;
  } else {
    av.textContent = (user.display_name || user.username || '?')[0].toUpperCase();
  }

  document.getElementById('view-display-name').textContent = user.display_name || '';
  document.getElementById('view-username').textContent     = '@' + (user.username || '');
  document.getElementById('view-bio').textContent          = user.bio || 'No bio set.';
  document.getElementById('view-email').textContent        = user.email || '';
  document.getElementById('view-joined').textContent       = user.date_joined
    ? new Date(user.date_joined).toLocaleDateString(undefined, { year: 'numeric', month: 'long', day: 'numeric' })
    : '';
}

// ── Edit mode ────────────────────────────────────────────────────────────────

function startEdit() {
  const user = _profileData || getUser();
  document.getElementById('edit-display-name').value = user.display_name || '';
  document.getElementById('edit-bio').value          = user.bio || '';
  document.getElementById('profile-error').classList.remove('visible');
  document.getElementById('view-mode').classList.add('hidden');
  document.getElementById('edit-mode').classList.remove('hidden');
  document.getElementById('edit-display-name').focus();
}

function cancelEdit() {
  document.getElementById('edit-mode').classList.add('hidden');
  document.getElementById('view-mode').classList.remove('hidden');
}

async function saveProfile() {
  const displayName = document.getElementById('edit-display-name').value.trim();
  const bio         = document.getElementById('edit-bio').value.trim();
  const errorEl     = document.getElementById('profile-error');
  errorEl.classList.remove('visible');

  const btn      = document.getElementById('btn-save');
  btn.disabled   = true;
  btn.textContent = 'Saving…';

  const res  = await apiFetch('/api/auth/me/', {
    method: 'PATCH',
    body:   JSON.stringify({ display_name: displayName, bio }),
  });
  const data = await res.json();

  btn.disabled   = false;
  btn.textContent = 'Save';

  if (!res.ok) {
    const msg = data.error?.display_name?.[0] || data.error || 'Failed to save.';
    errorEl.textContent = typeof msg === 'string' ? msg : JSON.stringify(msg);
    errorEl.classList.add('visible');
    return;
  }

  storeSession({
    access:  getAccessToken(),
    refresh: getRefreshToken(),
    user:    { ...(getUser() || {}), ...data },
  });
  applyView(data);
  cancelEdit();
  showToast('Profile updated!');

  // Refresh navbar display name
  document.getElementById('nav-user-name').textContent = data.display_name || data.username;
}

// ── Avatar upload ─────────────────────────────────────────────────────────────

async function uploadAvatar(file) {
  const form = new FormData();
  form.append('avatar', file);

  const res  = await apiFetch('/api/auth/me/', { method: 'PATCH', body: form });
  if (!res.ok) { showToast('Avatar upload failed.', 'error'); return; }

  const data = await res.json();
  storeSession({
    access:  getAccessToken(),
    refresh: getRefreshToken(),
    user:    { ...(getUser() || {}), ...data },
  });
  applyView(data);
  showToast('Avatar updated!');
}

// ── Boot ──────────────────────────────────────────────────────────────────────

document.addEventListener('DOMContentLoaded', () => {
  initNavbar();
  loadProfile();

  document.getElementById('btn-edit').addEventListener('click', startEdit);
  document.getElementById('btn-cancel').addEventListener('click', cancelEdit);
  document.getElementById('btn-save').addEventListener('click', saveProfile);

  document.getElementById('edit-display-name').addEventListener('keydown', (e) => {
    if (e.key === 'Enter') { e.preventDefault(); saveProfile(); }
  });

  document.getElementById('profile-avatar-wrap').addEventListener('click', () => {
    document.getElementById('avatar-file-input').click();
  });
  document.getElementById('avatar-file-input').addEventListener('change', () => {
    const f = document.getElementById('avatar-file-input').files[0];
    if (f) uploadAvatar(f);
    document.getElementById('avatar-file-input').value = '';
  });
});
