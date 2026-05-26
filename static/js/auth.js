/* Auth helpers — depends on api.js */

async function authSignup({ displayName, username, email, password }) {
  const res = await fetch('/api/auth/signup/', {
    method:  'POST',
    headers: { 'Content-Type': 'application/json' },
    body:    JSON.stringify({ display_name: displayName, username, email, password }),
  });
  const data = await res.json();
  if (!res.ok) return { ok: false, errors: data.error };
  storeSession(data);
  return { ok: true };
}

async function authLogin({ email, password }) {
  const res = await fetch('/api/auth/login/', {
    method:  'POST',
    headers: { 'Content-Type': 'application/json' },
    body:    JSON.stringify({ email, password }),
  });
  const data = await res.json();
  if (!res.ok) return { ok: false, errors: data.error };
  storeSession(data);
  return { ok: true };
}

async function authLogout() {
  const refresh = getRefreshToken();
  if (refresh) {
    await apiFetch('/api/auth/logout/', {
      method: 'POST',
      body:   JSON.stringify({ refresh }),
    }).catch(() => {});
  }
  clearSession();
  window.location.href = '/login/';
}
