/* Message timeline — grouping, day dividers, media, voice notes, presence lines,
   scroll anchoring. Depends on api.js, ui.js. */

const GROUP_WINDOW_MS = 5 * 60 * 1000;
const HISTORY_PAGE    = 50;   // MessageService.HISTORY_LIMIT
const AT_BOTTOM_PX    = 80;

function _linkify(escaped) {
  return escaped.replace(/https?:\/\/[^\s<]+/g, (url) => {
    const trail = url.match(/(?:&quot;|&#39;|[.,;:!?)\]'])+$/);
    const clean = trail ? url.slice(0, -trail[0].length) : url;
    return `<a href="${clean}" target="_blank" rel="noopener noreferrer">${clean}</a>${trail ? trail[0] : ''}`;
  });
}

function _isOwn(m) {
  const user = getUser();
  return !!user && (String(m.sender_id) === String(user.id) || m.username === user.username);
}

// ── Voice notes ──────────────────────────────────────────────────────────────
// The waveform shape is derived from the message id (stable, no audio decode);
// progress and the "breathing" while playing come from the real <audio> state.

const VOICE_BARS = 36;

const VoiceNotes = {
  current: null,   // the <audio> currently playing
  _raf: 0,

  shape(seed) {
    let h = _hash(seed) || 1;
    const rnd = () => { h = (h * 1103515245 + 12345) & 0x7fffffff; return h / 0x7fffffff; };
    const raw = Array.from({ length: VOICE_BARS }, rnd);
    // Smooth neighbours so it reads as speech, not noise; taper the ends.
    return raw.map((v, i) => {
      const avg  = (v + (raw[i - 1] ?? v) + (raw[i + 1] ?? v)) / 3;
      const edge = Math.min(1, (i + 1) / 4, (VOICE_BARS - i) / 4);
      return Math.max(0.14, Math.min(1, (0.22 + avg * 0.85) * (0.55 + edge * 0.45)));
    });
  },

  html(m) {
    const bars = this.shape(m.id || m.file_url).map((h, i) =>
      `<span style="--h:${h.toFixed(2)};--i:${i}"></span>`).join('');
    const who = _isOwn(m) ? 'your' : `${escHtml(m.display_name || m.username)}'s`;
    return `
      <div class="voice">
        <button type="button" class="voice-play" data-voice-toggle aria-label="Play ${who} voice note">
          ${icon('play', 16, 'i-play')}${icon('pause', 16, 'i-pause')}
        </button>
        <div class="voice-wave" role="slider" tabindex="0" aria-label="Playback position"
             aria-valuemin="0" aria-valuemax="100" aria-valuenow="0" aria-valuetext="0:00">
          <div class="voice-bars">${bars}</div>
          <div class="voice-bars is-fill">${bars}</div>
        </div>
        <span class="voice-time">–:––</span>
        <audio preload="metadata" src="${escHtml(m.file_url || '')}"></audio>
      </div>`;
  },

  toggle(voiceEl) {
    const audio = voiceEl.querySelector('audio');
    if (!audio) return;
    if (audio.paused) {
      if (this.current && this.current !== audio) this.current.pause();
      voiceEl.classList.add('is-buffering');
      audio.play().catch(() => {
        voiceEl.classList.remove('is-buffering');
        showToast('This voice note could not be played.', 'error');
      });
    } else {
      audio.pause();
    }
  },

  seek(voiceEl, ratio) {
    const audio = voiceEl.querySelector('audio');
    if (!audio || !isFinite(audio.duration)) return;
    audio.currentTime = Math.max(0, Math.min(1, ratio)) * audio.duration;
    this.paint(voiceEl, audio);
  },

  paint(voiceEl, audio) {
    const d = audio.duration;
    const t = audio.currentTime;
    const p = isFinite(d) && d > 0 ? t / d : 0;
    voiceEl.querySelector('.voice-bars.is-fill').style.setProperty('--p', (p * 100).toFixed(2) + '%');
    const wave = voiceEl.querySelector('.voice-wave');
    wave.setAttribute('aria-valuenow', String(Math.round(p * 100)));
    wave.setAttribute('aria-valuetext', `${formatDuration(t)} of ${formatDuration(d)}`);
    // Show elapsed while playing or scrubbed, total length otherwise
    voiceEl.querySelector('.voice-time').textContent =
      (!audio.paused || t > 0) ? formatDuration(t) : formatDuration(d);
  },

  // Smooth progress for the one playing note (timeupdate is only ~4 Hz).
  _loop() {
    cancelAnimationFrame(this._raf);
    const tick = () => {
      const a = this.current;
      if (!a || a.paused) return;
      const v = a.closest('.voice');
      if (v) this.paint(v, a);
      this._raf = requestAnimationFrame(tick);
    };
    this._raf = requestAnimationFrame(tick);
  },

  // Captured media events from the timeline (media events don't bubble).
  onMediaEvent(e) {
    const audio = e.target;
    if (audio.tagName !== 'AUDIO') return;
    const v = audio.closest('.voice');
    if (!v) return;
    switch (e.type) {
      case 'playing':
        this.current = audio;
        v.classList.remove('is-buffering');
        v.classList.add('is-playing');
        v.querySelector('[data-voice-toggle]').setAttribute('aria-label', 'Pause voice note');
        this._loop();
        break;
      case 'waiting':
        v.classList.add('is-buffering');
        break;
      case 'pause':
      case 'ended':
        v.classList.remove('is-playing', 'is-buffering');
        v.querySelector('[data-voice-toggle]').setAttribute('aria-label', 'Play voice note');
        if (e.type === 'ended') audio.currentTime = 0;
        if (this.current === audio) this.current = null;
        this.paint(v, audio);
        break;
      case 'loadedmetadata':
      case 'durationchange':
      case 'timeupdate':
        this.paint(v, audio);
        break;
      case 'error':
        v.classList.remove('is-playing', 'is-buffering');
        v.querySelector('.voice-time').textContent = 'Unavailable';
        break;
    }
  },

  stopAll() {
    this.current?.pause();
    this.current = null;
    cancelAnimationFrame(this._raf);
  },
};

const _MEDIA_EVENTS = ['playing', 'waiting', 'pause', 'ended', 'loadedmetadata', 'durationchange', 'timeupdate', 'error'];

// ── Timeline ─────────────────────────────────────────────────────────────────

class MessageList {
  /**
   * scroller — the scrolling .timeline element
   * jump     — the "New messages" pill
   * opts     — { room, onOpenProfile(user), onSeen() }
   */
  constructor(scroller, jump, opts) {
    this.scroller = scroller;
    this.jump     = jump;
    this.opts     = opts;
    this.inner    = document.createElement('div');
    this.inner.className = 'timeline-inner';
    scroller.appendChild(this.inner);

    this.rendered = new Set();
    this._lastDay   = null;
    this._lastGroup = null;   // { el, stack, key, lastTs }
    this._unseen    = 0;
    this.userScrolled = false;

    this._onScroll = this._onScroll.bind(this);
    this._onClick  = this._onClick.bind(this);
    this._onMedia  = (e) => VoiceNotes.onMediaEvent(e);
    this._onLoad   = this._onLoad.bind(this);
    this._onKey    = this._onKey.bind(this);
    this._onPointerDown = this._onPointerDown.bind(this);

    scroller.addEventListener('scroll', this._onScroll, { passive: true });
    scroller.addEventListener('click', this._onClick);
    scroller.addEventListener('keydown', this._onKey);
    scroller.addEventListener('pointerdown', this._onPointerDown);
    scroller.addEventListener('load', this._onLoad, true);
    scroller.addEventListener('error', this._onLoad, true);
    _MEDIA_EVENTS.forEach(t => scroller.addEventListener(t, this._onMedia, true));
    jump.addEventListener('click', () => this.scrollToBottom(true));
  }

  // ── Rendering ──────────────────────────────────────────────────────────

  showLoading() {
    this.inner.innerHTML = `
      <div class="timeline-skeleton" aria-hidden="true">
        <div class="timeline-skeleton-row"><span class="skeleton"></span><span class="timeline-skeleton-lines"><span class="skeleton" style="width:22%"></span><span class="skeleton" style="width:64%"></span></span></div>
        <div class="timeline-skeleton-row is-own"><span class="skeleton"></span></div>
        <div class="timeline-skeleton-row"><span class="skeleton"></span><span class="timeline-skeleton-lines"><span class="skeleton" style="width:18%"></span><span class="skeleton" style="width:48%"></span><span class="skeleton" style="width:36%"></span></span></div>
      </div>`;
    this.scroller.setAttribute('aria-busy', 'true');
  }

  showError(text) {
    this.inner.innerHTML = `<div class="timeline-intro"><p class="timeline-intro-hint">${escHtml(text)}</p></div>`;
    this.scroller.removeAttribute('aria-busy');
  }

  renderHistory(messages, room) {
    this.inner.innerHTML = '';
    this.rendered.clear();
    this._lastDay = null;
    this._lastGroup = null;

    // Only claim "this is where it starts" when we really have the whole history.
    if (messages.length < HISTORY_PAGE) this.inner.appendChild(this._intro(room, messages.length === 0));

    const frag = document.createDocumentFragment();
    const prevInner = this.inner;
    this.inner = frag;
    messages.forEach(m => this._insert(m, false));
    this.inner = prevInner;
    this.inner.appendChild(frag);

    this.inner.classList.remove('is-entering');
    void this.inner.offsetWidth;
    this.inner.classList.add('is-entering');

    this.scroller.removeAttribute('aria-busy');
    this.scrollToBottom(false);
  }

  _intro(room, empty) {
    const el = document.createElement('div');
    el.className = 'timeline-intro';
    const created = room.created_at
      ? new Date(room.created_at).toLocaleDateString([], { year: 'numeric', month: 'long', day: 'numeric' })
      : '';
    el.innerHTML = `
      ${monogramHtml(room.name, 'lg')}
      <h2 class="timeline-intro-title">${escHtml(room.name)}</h2>
      ${room.description ? `<p class="timeline-intro-desc">${escHtml(room.description)}</p>` : ''}
      ${created ? `<p class="timeline-intro-meta">Created ${escHtml(created)}</p>` : ''}
      ${empty ? '<p class="timeline-intro-hint">No messages yet. Say something — everyone here sees it the moment you send it.</p>' : ''}`;
    return el;
  }

  updateIntro(room) {
    const old = this.inner.querySelector('.timeline-intro');
    if (!old) return;
    const hasHint = !!old.querySelector('.timeline-intro-hint') && !this.inner.querySelector('.msg-group');
    old.replaceWith(this._intro(room, hasHint));
  }

  /** Append one message. live=true for WebSocket arrivals and fresh uploads. */
  append(m, { live = true } = {}) {
    if (m.id && this.rendered.has(String(m.id))) return;
    const stick = this.isAtBottom();
    const own   = _isOwn(m);

    this.inner.querySelector('.timeline-intro-hint')?.remove();
    this._insert(m, live);

    if (stick || own) {
      this.scrollToBottom(live);
    } else {
      this._unseen++;
      this._showJump();
    }
  }

  _insert(m, animate) {
    if (m.id) this.rendered.add(String(m.id));
    const ts  = m.timestamp || new Date().toISOString();
    const t   = Date.parse(ts);
    const own = _isOwn(m);
    const key = own ? '__me' : String(m.sender_id || m.username);

    const dk = dayKey(ts);
    if (dk !== this._lastDay) {
      const div = document.createElement('div');
      div.className = 'day-divider';
      div.setAttribute('role', 'separator');
      div.textContent = dayLabel(ts);
      this.inner.appendChild(div);
      this._lastDay = dk;
      this._lastGroup = null;
    }

    let g = this._lastGroup;
    if (!g || g.key !== key || t - g.lastTs > GROUP_WINDOW_MS || this.inner.lastChild !== g.el) {
      g = this._newGroup(m, own, ts, key);
      this.inner.appendChild(g.el);
      this._lastGroup = g;
    }
    g.lastTs = t;

    const el = this._messageEl(m, ts);
    if (animate && !reducedMotion()) el.classList.add('is-new');
    g.stack.appendChild(el);
    return el;
  }

  _newGroup(m, own, ts, key) {
    const el = document.createElement('div');
    el.className = 'msg-group ' + (own ? 'is-own' : 'is-other');
    const name = m.display_name || m.username || 'Someone';
    const profile = `data-profile="${escHtml(m.username || '')}" data-display-name="${escHtml(name)}" data-avatar-url="${escHtml(m.avatar_url || '')}"`;

    el.innerHTML = `
      ${own ? '' : `<button type="button" class="msg-avatar" ${profile} aria-label="View ${escHtml(name)}'s profile">${avatarHtml({ name, url: m.avatar_url, size: 'md' })}</button>`}
      <div class="msg-stack">
        <header class="msg-head">
          ${own ? '<span class="sr-only">You</span>' : `<button type="button" class="msg-author" ${profile}>${escHtml(name)}</button>`}
          <time datetime="${escHtml(ts)}" title="${escHtml(fullTime(ts))}">${escHtml(clockTime(ts))}</time>
        </header>
      </div>`;
    return { el, stack: el.querySelector('.msg-stack'), key, lastTs: Date.parse(ts) };
  }

  _messageEl(m, ts) {
    const el = document.createElement('div');
    el.className = 'msg';
    if (m.id) el.dataset.id = m.id;
    const gutter = `<time class="msg-gutter-time" datetime="${escHtml(ts)}" title="${escHtml(fullTime(ts))}">${escHtml(clockTime(ts))}</time>`;
    const name = _isOwn(m) ? 'you' : (m.display_name || m.username || 'someone');

    if (m.message_type === 'voice') {
      el.innerHTML = gutter + VoiceNotes.html(m);
    } else if (m.message_type === 'image') {
      const src = escHtml(m.file_url || '');
      el.innerHTML = `${gutter}
        <button type="button" class="msg-image is-loading" data-lightbox-src="${src}" aria-label="Open image from ${escHtml(name)}">
          <img src="${src}" alt="Image from ${escHtml(name)}" loading="lazy" decoding="async">
        </button>`;
    } else {
      el.innerHTML = `${gutter}<div class="msg-text">${_linkify(escHtml(m.content || ''))}</div>`;
    }
    return el;
  }

  /** Join/leave as a quiet line in the timeline. Coalesces room-hopping. */
  presence({ event, username, display_name, avatar_url }) {
    const stick = this.isAtBottom();

    // Look through the trailing run of presence lines: one line per person.
    let node = this.inner.lastElementChild;
    let run = 0;
    while (node && node.classList.contains('presence-event')) {
      const prev = node.previousElementSibling;
      if (node.dataset.user === username || run >= 2) node.remove();
      else run++;
      node = prev;
    }

    const name = display_name || username;
    const now  = new Date().toISOString();
    const el = document.createElement('div');
    el.className = `presence-event is-${event === 'join' ? 'join' : 'leave'}`;
    el.dataset.user = username;
    el.innerHTML = `
      ${avatarHtml({ name, url: avatar_url, size: 'xs' })}
      <span><span class="presence-event-who">${escHtml(name)}</span> ${event === 'join' ? 'is here' : 'left'}</span>
      <span class="presence-event-dot" aria-hidden="true"></span>
      <time datetime="${now}">${escHtml(clockTime(now))}</time>`;
    if (!reducedMotion()) el.classList.add('is-new');
    this.inner.appendChild(el);
    this._lastGroup = null;
    if (stick) this.scrollToBottom(true);
  }

  // ── Scrolling ──────────────────────────────────────────────────────────

  isAtBottom() {
    const s = this.scroller;
    return s.scrollHeight - s.scrollTop - s.clientHeight < AT_BOTTOM_PX;
  }

  scrollToBottom(smooth) {
    this.scroller.scrollTo({
      top: this.scroller.scrollHeight,
      behavior: smooth && !reducedMotion() ? 'smooth' : 'auto',
    });
    this._hideJump();
  }

  _onScroll() {
    const atBottom = this.isAtBottom();
    this.userScrolled = !atBottom;
    if (atBottom && this._unseen) {
      this._hideJump();
      this.opts.onSeen?.();
    }
  }

  _showJump() {
    const n = this._unseen;
    this.jump.querySelector('.jump-pill-label').textContent = n === 1 ? '1 new message' : `${n} new messages`;
    this.jump.classList.add('is-visible');
  }

  _hideJump() {
    this._unseen = 0;
    this.jump.classList.remove('is-visible');
  }

  // ── Delegated interaction ──────────────────────────────────────────────

  _onClick(e) {
    const img = e.target.closest('[data-lightbox-src]');
    if (img && !img.classList.contains('is-broken')) {
      openLightbox(img.dataset.lightboxSrc, img.querySelector('img')?.alt);
      return;
    }
    const p = e.target.closest('[data-profile]');
    if (p) {
      this.opts.onOpenProfile?.({
        username:     p.dataset.profile,
        display_name: p.dataset.displayName,
        avatar_url:   p.dataset.avatarUrl || null,
      });
      return;
    }
    const play = e.target.closest('[data-voice-toggle]');
    if (play) VoiceNotes.toggle(play.closest('.voice'));
  }

  _onKey(e) {
    const wave = e.target.closest?.('.voice-wave');
    if (!wave) return;
    const v = wave.closest('.voice');
    const a = v.querySelector('audio');
    if (!isFinite(a.duration)) {
      if (e.key === ' ' || e.key === 'Enter') { e.preventDefault(); VoiceNotes.toggle(v); }
      return;
    }
    const step = 5 / a.duration;
    const cur  = a.currentTime / a.duration;
    const map  = { ArrowRight: cur + step, ArrowUp: cur + step, ArrowLeft: cur - step, ArrowDown: cur - step, Home: 0, End: 0.999 };
    if (e.key in map) { e.preventDefault(); VoiceNotes.seek(v, map[e.key]); }
    else if (e.key === ' ' || e.key === 'Enter') { e.preventDefault(); VoiceNotes.toggle(v); }
  }

  // Click or drag along the waveform to scrub.
  _onPointerDown(e) {
    const wave = e.target.closest('.voice-wave');
    if (!wave || e.button !== 0) return;
    const v = wave.closest('.voice');
    const at = (ev) => {
      const r = wave.getBoundingClientRect();
      VoiceNotes.seek(v, (ev.clientX - r.left) / r.width);
    };
    at(e);
    wave.setPointerCapture(e.pointerId);
    const move = (ev) => at(ev);
    const up = () => {
      wave.removeEventListener('pointermove', move);
      wave.removeEventListener('pointerup', up);
      wave.removeEventListener('pointercancel', up);
    };
    wave.addEventListener('pointermove', move);
    wave.addEventListener('pointerup', up);
    wave.addEventListener('pointercancel', up);
  }

  _onLoad(e) {
    const img = e.target;
    if (img.tagName !== 'IMG') return;
    const box = img.closest('.msg-image');
    if (!box) return;
    box.classList.remove('is-loading');
    if (e.type === 'error') box.classList.add('is-broken');
    // Late-loading images grow the timeline; stay pinned if we were pinned.
    if (!this.userScrolled) this.scrollToBottom(false);
  }

  destroy() {
    VoiceNotes.stopAll();
    this.scroller.removeEventListener('scroll', this._onScroll);
    this.scroller.removeEventListener('click', this._onClick);
    this.scroller.removeEventListener('keydown', this._onKey);
    this.scroller.removeEventListener('pointerdown', this._onPointerDown);
    this.scroller.removeEventListener('load', this._onLoad, true);
    this.scroller.removeEventListener('error', this._onLoad, true);
    _MEDIA_EVENTS.forEach(t => this.scroller.removeEventListener(t, this._onMedia, true));
  }
}
