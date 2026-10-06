/* Shared UI primitives — icons, avatars, time, layers (modal/drawer/lightbox).
   Depends on api.js. */

// ── Icons ────────────────────────────────────────────────────────────────────
// One stroke weight, drawn on a 24px grid. Filled glyphs set their own fill.

const _ICON_PATHS = {
  plus:       '<path d="M12 5v14M5 12h14"/>',
  menu:       '<path d="M4 8h16M4 16h11"/>',
  chevronL:   '<path d="M15 18l-6-6 6-6"/>',
  chevronUD:  '<path d="M8.5 9.5L12 6l3.5 3.5M8.5 14.5L12 18l3.5-3.5"/>',
  link:       '<path d="M10 13.5a4.5 4.5 0 0 0 6.4.4l3-3a4.5 4.5 0 0 0-6.4-6.4l-1.4 1.4"/><path d="M14 10.5a4.5 4.5 0 0 0-6.4-.4l-3 3a4.5 4.5 0 0 0 6.4 6.4l1.4-1.4"/>',
  check:      '<path d="M5 12.5l4.5 4.5L19 7.5"/>',
  panel:      '<rect x="3.5" y="4.5" width="17" height="15" rx="3"/><path d="M14.5 4.5v15"/>',
  close:      '<path d="M6.5 6.5l11 11M17.5 6.5l-11 11"/>',
  clip:       '<path d="M20 11.5l-8 8a5 5 0 0 1-7.1-7.1l8.5-8.5a3.3 3.3 0 0 1 4.7 4.7l-8.4 8.4a1.7 1.7 0 0 1-2.4-2.4l7.7-7.7"/>',
  mic:        '<rect x="9" y="3" width="6" height="11.5" rx="3"/><path d="M5.5 11a6.5 6.5 0 0 0 13 0M12 17.5V21"/>',
  arrowUp:    '<path d="M12 19V5.5M6.5 11L12 5.5 17.5 11"/>',
  arrowDown:  '<path d="M12 5v13.5M6.5 13l5.5 5.5 5.5-5.5"/>',
  arrowRight: '<path d="M5 12h13.5M13 6.5l5.5 5.5-5.5 5.5"/>',
  trash:      '<path d="M4.5 7h15M10 11v5.5M14 11v5.5M6.5 7l.8 11.2a2 2 0 0 0 2 1.8h5.4a2 2 0 0 0 2-1.8L17.5 7M9.5 7V4.5h5V7"/>',
  edit:       '<path d="M4.5 19.5h4l10.3-10.3a2.1 2.1 0 0 0-4-4L4.5 15.5v4z"/>',
  leave:      '<path d="M9.5 19.5H6.5a2 2 0 0 1-2-2v-11a2 2 0 0 1 2-2h3M15.5 16l4-4-4-4M19.5 12H10"/>',
  user:       '<circle cx="12" cy="8.5" r="3.75"/><path d="M5 19.5c1.4-3 4-4.5 7-4.5s5.6 1.5 7 4.5"/>',
  image:      '<rect x="3.5" y="4.5" width="17" height="15" rx="3"/><circle cx="9" cy="10" r="1.5"/><path d="M20.5 15.5l-4.5-4.5-8.5 8.5"/>',
  camera:     '<path d="M4 8.5a2 2 0 0 1 2-2h1.6l1.4-2h6l1.4 2H18a2 2 0 0 1 2 2V17a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2z"/><circle cx="12" cy="12.5" r="3.25"/>',
  eye:        '<path d="M2.5 12S6 5.5 12 5.5 21.5 12 21.5 12 18 18.5 12 18.5 2.5 12 2.5 12z"/><circle cx="12" cy="12" r="2.75"/>',
  eyeOff:     '<path d="M10 5.7A9.6 9.6 0 0 1 12 5.5c6 0 9.5 6.5 9.5 6.5a16 16 0 0 1-2.4 3.2M6.6 6.6C4 8.3 2.5 12 2.5 12s3.5 6.5 9.5 6.5c1.9 0 3.5-.6 4.9-1.5M4 4l16 16"/><path d="M10 10.1a2.75 2.75 0 0 0 3.9 3.9"/>',
  play:       '<path d="M8 5.6v12.8a.6.6 0 0 0 .9.5l10.3-6.4a.6.6 0 0 0 0-1L8.9 5.1a.6.6 0 0 0-.9.5z" fill="currentColor" stroke="none"/>',
  pause:      '<rect x="6.5" y="5" width="3.75" height="14" rx="1" fill="currentColor" stroke="none"/><rect x="13.75" y="5" width="3.75" height="14" rx="1" fill="currentColor" stroke="none"/>',
  wave:       '<path d="M4 10v4M8 7v10M12 4v16M16 8v8M20 10.5v3"/>',
};

function icon(name, size = 18, cls = '') {
  return `<svg class="${cls}" width="${size}" height="${size}" viewBox="0 0 24 24" fill="none" stroke="currentColor"
    stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" focusable="false">${_ICON_PATHS[name] || ''}</svg>`;
}

// ── Avatars & monograms ──────────────────────────────────────────────────────
// Low-chroma tones derived from the name: people stay distinguishable without
// turning the sidebar into a rainbow.

function _hash(s) {
  let h = 0;
  for (const c of String(s || '')) h = ((h << 5) - h + c.charCodeAt(0)) | 0;
  return Math.abs(h);
}

function toneFor(seed) {
  const h = _hash(seed) % 360;
  return `--tone:hsl(${h} 11% 19%);--tone-ink:hsl(${h} 22% 78%)`;
}

function initialOf(name) {
  const s = String(name || '').trim();
  return s ? [...s][0].toUpperCase() : '?';
}

function avatarHtml({ name, url, size = 'md', cls = '' } = {}) {
  const inner = url
    ? `<img src="${escHtml(url)}" alt="" loading="lazy" decoding="async">`
    : escHtml(initialOf(name));
  return `<span class="avatar avatar--${size} ${cls}" style="${toneFor(name)}" data-initial="${escHtml(initialOf(name))}" aria-hidden="true">${inner}</span>`;
}

function monogramHtml(name, size = '') {
  return `<span class="monogram ${size ? 'monogram--' + size : ''}" style="${toneFor(name)}" aria-hidden="true">${escHtml(initialOf(name))}</span>`;
}

// A broken avatar image falls back to the initial instead of a broken-image icon.
document.addEventListener('error', (e) => {
  const img = e.target;
  if (img.tagName !== 'IMG') return;
  const av = img.parentElement;
  if (av && av.classList.contains('avatar')) av.textContent = av.dataset.initial || '?';
}, true);

// ── Time ─────────────────────────────────────────────────────────────────────

function clockTime(iso) {
  return new Date(iso).toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' });
}

function fullTime(iso) {
  return new Date(iso).toLocaleString([], { dateStyle: 'medium', timeStyle: 'short' });
}

function dayKey(iso) {
  const d = new Date(iso);
  return `${d.getFullYear()}-${d.getMonth()}-${d.getDate()}`;
}

function _startOfDay(d) { const x = new Date(d); x.setHours(0, 0, 0, 0); return x; }

function dayLabel(iso) {
  const d = new Date(iso);
  const days = Math.round((_startOfDay(new Date()) - _startOfDay(d)) / 86400000);
  if (days === 0) return 'Today';
  if (days === 1) return 'Yesterday';
  if (days < 7)   return d.toLocaleDateString([], { weekday: 'long' });
  const sameYear = d.getFullYear() === new Date().getFullYear();
  return d.toLocaleDateString([], { weekday: 'short', month: 'short', day: 'numeric', ...(sameYear ? {} : { year: 'numeric' }) });
}

// Compact stamp for the room list: now · 4m · 14:02 · Yesterday · Mon · Oct 4
function compactTime(iso) {
  if (!iso) return '';
  const d = new Date(iso);
  const s = (Date.now() - d) / 1000;
  if (s < 60)   return 'now';
  if (s < 3600) return Math.floor(s / 60) + 'm';
  const days = Math.round((_startOfDay(new Date()) - _startOfDay(d)) / 86400000);
  if (days === 0) return clockTime(iso);
  if (days === 1) return 'Yesterday';
  if (days < 7)   return d.toLocaleDateString([], { weekday: 'short' });
  return d.toLocaleDateString([], { month: 'short', day: 'numeric' });
}

function formatDuration(sec) {
  if (!isFinite(sec) || sec < 0) return '–:––';
  const s = Math.floor(sec);
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, '0')}`;
}

// ── Environment ──────────────────────────────────────────────────────────────

const _reducedMotionMQ = window.matchMedia('(prefers-reduced-motion: reduce)');
function reducedMotion() { return _reducedMotionMQ.matches; }

const _mobileMQ = window.matchMedia('(max-width: 768px), (hover: none) and (pointer: coarse) and (max-width: 1200px)');
function isMobile() { return _mobileMQ.matches; }

function isTouch() { return window.matchMedia('(pointer: coarse)').matches; }

// ── Screen-reader announcements ──────────────────────────────────────────────

let _announcer = null;
function announce(msg) {
  if (!_announcer) {
    _announcer = document.createElement('div');
    _announcer.className = 'sr-only';
    _announcer.setAttribute('aria-live', 'polite');
    document.body.appendChild(_announcer);
  }
  _announcer.textContent = '';
  requestAnimationFrame(() => { _announcer.textContent = msg; });
}

// ── Clipboard ────────────────────────────────────────────────────────────────

async function copyText(text) {
  try {
    await navigator.clipboard.writeText(text);
    return true;
  } catch {
    // Non-secure contexts have no async clipboard; fall back to a selection copy.
    const ta = document.createElement('textarea');
    ta.value = text;
    ta.setAttribute('readonly', '');
    ta.style.cssText = 'position:fixed;opacity:0;pointer-events:none';
    document.body.appendChild(ta);
    ta.select();
    let ok = false;
    try { ok = document.execCommand('copy'); } catch { ok = false; }
    ta.remove();
    return ok;
  }
}

// Briefly swap a button into a confirmed state ("Copied").
function flashButton(btn, html, ms = 1600) {
  if (btn._flashTimer) clearTimeout(btn._flashTimer);
  else btn._flashOriginal = btn.innerHTML;
  btn.innerHTML = html;
  btn.classList.add('is-done');
  btn._flashTimer = setTimeout(() => {
    btn.innerHTML = btn._flashOriginal;
    btn.classList.remove('is-done');
    btn._flashTimer = null;
  }, ms);
}

// ── Layers: modals, drawers, lightbox ────────────────────────────────────────
// One stack so Escape and focus-trapping always apply to the top-most layer.

const _layers = [];
const _FOCUSABLE = 'a[href], button:not([disabled]), input:not([disabled]):not([type="hidden"]), textarea:not([disabled]), select:not([disabled]), [tabindex]:not([tabindex="-1"])';

function _focusables(root) {
  return [...root.querySelectorAll(_FOCUSABLE)].filter(el => el.getClientRects().length > 0);
}

document.addEventListener('keydown', (e) => {
  const top = _layers[_layers.length - 1];
  if (!top) return;
  if (e.key === 'Escape') {
    if (top.opts.onEscape && top.opts.onEscape(e) === false) return;
    e.preventDefault();
    top.close();
  } else if (e.key === 'Tab') {
    const items = _focusables(top.el);
    if (!items.length) { e.preventDefault(); return; }
    const first = items[0];
    const last  = items[items.length - 1];
    if (!top.el.contains(document.activeElement)) { e.preventDefault(); first.focus(); }
    else if (e.shiftKey && document.activeElement === first) { e.preventDefault(); last.focus(); }
    else if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first.focus(); }
  }
});

/**
 * Show an overlay element and manage it as a layer.
 *   el            — element that gets .is-open / .is-closing
 *   backdrop      — optional separate scrim (drawers); clicking it closes
 *   initialFocus  — selector or element to focus first
 *   removeOnClose — remove el from the DOM after the exit animation
 *   onClose(result)
 * Returns { close(result) }.
 */
function openLayer(el, opts = {}) {
  const prevFocus = document.activeElement;
  const backdrop  = opts.backdrop || null;
  let closed = false;

  const layer = { el, opts, close };
  _layers.push(layer);

  el.classList.remove('is-closing');
  el.classList.add('is-open');
  backdrop?.classList.remove('is-closing');
  backdrop?.classList.add('is-open');

  // Only a press that both starts and ends on the backdrop dismisses, so a
  // text-selection drag that ends outside the dialog doesn't close it.
  const dismissTarget = backdrop || (opts.dismissOnBackdrop !== false ? el : null);
  let downOnBackdrop = false;
  const onBackdropDown  = (e) => { downOnBackdrop = e.target === e.currentTarget; };
  const onBackdropClick = (e) => { if (e.target === e.currentTarget && downOnBackdrop) close(); };
  dismissTarget?.addEventListener('pointerdown', onBackdropDown);
  dismissTarget?.addEventListener('click', onBackdropClick);

  requestAnimationFrame(() => {
    let target = opts.initialFocus;
    if (typeof target === 'string') target = el.querySelector(target);
    (target || _focusables(el)[0] || el).focus({ preventScroll: true });
  });

  function close(result) {
    if (closed) return;
    closed = true;
    _layers.splice(_layers.indexOf(layer), 1);
    dismissTarget?.removeEventListener('pointerdown', onBackdropDown);
    dismissTarget?.removeEventListener('click', onBackdropClick);

    el.classList.add('is-closing');
    backdrop?.classList.add('is-closing');
    const done = () => {
      el.classList.remove('is-open', 'is-closing');
      backdrop?.classList.remove('is-open', 'is-closing');
      if (opts.removeOnClose) el.remove();
    };
    if (reducedMotion()) done(); else setTimeout(done, opts.closeMs ?? 240);

    if (prevFocus && document.contains(prevFocus) && !opts.keepFocus) prevFocus.focus({ preventScroll: true });
    opts.onClose?.(result);
  }

  return layer;
}

/** Build a modal from HTML. Returns { overlay, modal, layer }. */
function createModal({ html, size = '', labelledBy, role = 'dialog', cls = '', ...layerOpts }) {
  const overlay = document.createElement('div');
  overlay.className = 'modal-overlay';
  overlay.innerHTML = `
    <div class="modal ${size ? 'modal--' + size : ''} ${cls}" role="${role}" aria-modal="true"
         ${labelledBy ? `aria-labelledby="${labelledBy}"` : ''}>${html}</div>`;
  document.body.appendChild(overlay);
  const layer = openLayer(overlay, { removeOnClose: true, ...layerOpts });
  return { overlay, modal: overlay.firstElementChild, layer };
}

/** Promise-based confirmation, replaces window.confirm(). */
function confirmDialog({ title, body = '', confirmLabel = 'Confirm', cancelLabel = 'Cancel', danger = false }) {
  return new Promise((resolve) => {
    const id = 'cd-' + Math.random().toString(36).slice(2, 8);
    const { overlay, layer } = createModal({
      size: 'sm',
      role: 'alertdialog',
      labelledBy: id,
      initialFocus: danger ? '[data-act="cancel"]' : '[data-act="ok"]',
      onClose: (r) => resolve(r === true),
      html: `
        <h2 class="modal-title" id="${id}">${escHtml(title)}</h2>
        ${body ? `<p class="modal-desc">${escHtml(body)}</p>` : ''}
        <div class="modal-foot">
          <button type="button" class="btn btn-ghost" data-act="cancel">${escHtml(cancelLabel)}</button>
          <button type="button" class="btn ${danger ? 'btn-danger' : 'btn-primary'}" data-act="ok">${escHtml(confirmLabel)}</button>
        </div>`,
    });
    overlay.addEventListener('click', (e) => {
      const b = e.target.closest('[data-act]');
      if (b) layer.close(b.dataset.act === 'ok');
    });
  });
}

/** Full-screen image viewer. */
function openLightbox(src, alt = 'Image') {
  const el = document.createElement('div');
  el.className = 'lightbox';
  el.setAttribute('role', 'dialog');
  el.setAttribute('aria-modal', 'true');
  el.setAttribute('aria-label', alt);
  el.innerHTML = `
    <div class="lightbox-bar">
      <a class="icon-btn" href="${escHtml(src)}" target="_blank" rel="noopener noreferrer" aria-label="Open original">${icon('arrowRight', 18)}</a>
      <button type="button" class="icon-btn" data-close aria-label="Close">${icon('close', 18)}</button>
    </div>
    <img src="${escHtml(src)}" alt="${escHtml(alt)}">`;
  document.body.appendChild(el);
  const layer = openLayer(el, { removeOnClose: true, initialFocus: '[data-close]' });
  el.querySelector('[data-close]').addEventListener('click', () => layer.close());
  return layer;
}

// ── Popover menus ────────────────────────────────────────────────────────────

/** Wire a trigger button to a .menu element: click, outside-click, Escape, arrow keys. */
function bindMenu(trigger, menu) {
  const items = () => [...menu.querySelectorAll('.menu-item')];
  const isOpen = () => menu.classList.contains('is-open');

  const open = () => {
    menu.classList.add('is-open');
    trigger.setAttribute('aria-expanded', 'true');
    requestAnimationFrame(() => items()[0]?.focus());
  };
  const close = (refocus = false) => {
    if (!isOpen()) return;
    menu.classList.remove('is-open');
    trigger.setAttribute('aria-expanded', 'false');
    if (refocus) trigger.focus();
  };

  trigger.setAttribute('aria-haspopup', 'menu');
  trigger.setAttribute('aria-expanded', 'false');
  trigger.addEventListener('click', (e) => { e.stopPropagation(); isOpen() ? close() : open(); });
  document.addEventListener('click', (e) => { if (!menu.contains(e.target)) close(); });
  menu.addEventListener('keydown', (e) => {
    const list = items();
    const i = list.indexOf(document.activeElement);
    if (e.key === 'Escape')    { e.preventDefault(); e.stopPropagation(); close(true); }
    if (e.key === 'ArrowDown') { e.preventDefault(); list[(i + 1) % list.length]?.focus(); }
    if (e.key === 'ArrowUp')   { e.preventDefault(); list[(i - 1 + list.length) % list.length]?.focus(); }
    if (e.key === 'Tab')       close();
  });
  menu.addEventListener('click', (e) => { if (e.target.closest('.menu-item')) close(); });
  return { open, close };
}
