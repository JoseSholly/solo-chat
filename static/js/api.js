/* Shared API layer — included on every page */

const _ACCESS_KEY  = 'cr_access';
const _REFRESH_KEY = 'cr_refresh';
const _USER_KEY    = 'cr_user';

function getAccessToken()  { return localStorage.getItem(_ACCESS_KEY); }
function getRefreshToken() { return localStorage.getItem(_REFRESH_KEY); }

function getUser() {
  try { return JSON.parse(localStorage.getItem(_USER_KEY)); } catch { return null; }
}

function storeSession({ access, refresh, user }) {
  localStorage.setItem(_ACCESS_KEY,  access);
  localStorage.setItem(_REFRESH_KEY, refresh);
  localStorage.setItem(_USER_KEY,    JSON.stringify(user));
}

function clearSession() {
  localStorage.removeItem(_ACCESS_KEY);
  localStorage.removeItem(_REFRESH_KEY);
  localStorage.removeItem(_USER_KEY);
}

async function _tryRefresh() {
  const refresh = getRefreshToken();
  if (!refresh) return false;
  try {
    const res = await fetch('/api/auth/token/refresh/', {
      method:  'POST',
      headers: { 'Content-Type': 'application/json' },
      body:    JSON.stringify({ refresh }),
    });
    if (!res.ok) { clearSession(); return false; }
    const data = await res.json();
    localStorage.setItem(_ACCESS_KEY, data.access);
    if (data.refresh) localStorage.setItem(_REFRESH_KEY, data.refresh);
    return true;
  } catch {
    return false;
  }
}

async function apiFetch(url, options = {}, _retry = true) {
  const token   = getAccessToken();
  const headers = { ...options.headers };

  if (!(options.body instanceof FormData)) {
    headers['Content-Type'] = 'application/json';
  }
  if (token) headers['Authorization'] = `Bearer ${token}`;

  const res = await fetch(url, { ...options, headers });

  if (res.status === 401 && _retry) {
    const ok = await _tryRefresh();
    if (ok) return apiFetch(url, options, false);
    clearSession();
    window.location.href = `/login/?next=${encodeURIComponent(window.location.pathname)}`;
    return res;
  }

  return res;
}

// Multipart upload with real progress. fetch() can't report upload progress,
// so this uses XHR but mirrors apiFetch's refresh-and-retry on 401.
// Resolves (never rejects) with { ok, status, data, aborted }.
function apiUpload(url, formData, { method = 'POST', onProgress, signal } = {}) {
  const send = (retry) => new Promise((resolve) => {
    const xhr = new XMLHttpRequest();
    xhr.open(method, url);
    const token = getAccessToken();
    if (token) xhr.setRequestHeader('Authorization', `Bearer ${token}`);

    if (onProgress) {
      xhr.upload.onprogress = (e) => { if (e.lengthComputable) onProgress(e.loaded / e.total); };
    }

    xhr.onload = async () => {
      if (xhr.status === 401 && retry) {
        if (await _tryRefresh()) { resolve(send(false)); return; }
        clearSession();
        window.location.href = `/login/?next=${encodeURIComponent(window.location.pathname)}`;
      }
      let data = null;
      try { data = JSON.parse(xhr.responseText); } catch { /* empty or non-JSON body */ }
      resolve({ ok: xhr.status >= 200 && xhr.status < 300, status: xhr.status, data, aborted: false });
    };
    xhr.onerror = () => resolve({ ok: false, status: 0, data: null, aborted: false });
    xhr.onabort = () => resolve({ ok: false, status: 0, data: null, aborted: true });

    if (signal) {
      if (signal.aborted) { xhr.abort(); return; }
      signal.addEventListener('abort', () => xhr.abort(), { once: true });
    }
    xhr.send(formData);
  });
  return send(true);
}

// ── Pure utilities (no DOM) ──────────────────────────────────────────────────

function escHtml(s) {
  return String(s ?? '')
    .replace(/&/g, '&amp;').replace(/</g, '&lt;')
    .replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}

function relativeTime(iso) {
  if (!iso) return '';
  const s = Math.floor((Date.now() - new Date(iso)) / 1000);
  if (s < 60)     return 'just now';
  if (s < 3600)   return Math.floor(s / 60) + 'm ago';
  if (s < 86400)  return Math.floor(s / 3600) + 'h ago';
  if (s < 172800) return 'yesterday';
  return new Date(iso).toLocaleDateString();
}

function showToast(msg, type = 'success') {
  const container = document.getElementById('toast-container');
  if (!container) return;
  const el = document.createElement('div');
  el.className   = 'toast ' + type;
  el.setAttribute('role', type === 'error' ? 'alert' : 'status');
  el.textContent = msg;
  container.appendChild(el);
  // Keep at most three on screen
  while (container.children.length > 3) container.firstElementChild.remove();
  setTimeout(() => {
    el.classList.add('is-leaving');
    setTimeout(() => el.remove(), 220);
  }, type === 'error' ? 4500 : 3000);
}
