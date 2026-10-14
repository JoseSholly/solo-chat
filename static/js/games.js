/* Games — lobby, Tic-Tac-Toe board, challenges and Quick match.
   Depends on api.js, ui.js, dashboard.js, room.js (the _activePanel contract:
   one panel in the stage at a time, each with destroy()). */

const BOT_LEVELS = [
  { id: 'easy',   label: 'Easy' },
  { id: 'medium', label: 'Medium' },
  { id: 'hard',   label: 'Hard' },
];
const QUICK_MATCH_BOT_OFFER_MS = 15000;
const QUICK_MATCH_RETRY_MS     = 5000;

// Inline marks, drawn on a 100×100 grid. pathLength=1 lets CSS "draw" them.
const MARK_SVG = {
  X: `<svg class="mark mark--x" viewBox="0 0 100 100" aria-hidden="true" focusable="false">
        <path pathLength="1" d="M28 28L72 72"/><path pathLength="1" d="M72 28L28 72"/></svg>`,
  O: `<svg class="mark mark--o" viewBox="0 0 100 100" aria-hidden="true" focusable="false">
        <circle pathLength="1" cx="50" cy="50" r="23"/></svg>`,
};

const GAME_ICON = '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" aria-hidden="true"><path d="M9.5 4v16M14.5 4v16M4 9.5h16M4 14.5h16"/></svg>';

function _apiError(data, fallback) {
  return (data && typeof data.error === 'string') ? data.error : fallback;
}

function _recordText(s) {
  if (!s) return '';
  return `${s.wins}W · ${s.losses}L · ${s.draws}D`;
}

function _mySymbol(game) {
  const me = getUser();
  if (!me || !game) return null;
  if (game.players.X?.username === me.username) return 'X';
  if (game.players.O?.username === me.username) return 'O';
  return null;
}

function _outcomeFor(game) {
  const mine = _mySymbol(game);
  if (game.status !== 'finished') return null;
  if (game.result === 'draw') return 'draw';
  return game.result === mine.toLowerCase() ? 'win' : 'loss';
}

function _opponentOf(game) {
  const mine = _mySymbol(game);
  return game.players[mine === 'X' ? 'O' : 'X'];
}

// ── Navigation ───────────────────────────────────────────────────────────────

function setGamesNavActive(on) {
  const el = document.getElementById('nav-games');
  if (!el) return;
  el.classList.toggle('is-active', on);
  if (on) el.setAttribute('aria-current', 'page'); else el.removeAttribute('aria-current');
}

function _enterGamesStage(title) {
  Nav.close();
  destroyActivePanel();
  _activeSlug = null;
  RoomList.setActive(null);
  setGamesNavActive(true);
  _app().classList.add('room-open');
  _stageTitle = title;
  updateTitle();
}

function openGames({ push = true } = {}) {
  _enterGamesStage('Games');
  if (push) history.pushState({ games: true }, '', '/dashboard/?games');
  _activePanel = new GamesLobby(document.getElementById('main-panel'));
}

function openGame(id, { push = true } = {}) {
  _enterGamesStage('Tic-Tac-Toe');
  if (push) history.pushState({ game: id }, '', '/dashboard/?game=' + encodeURIComponent(id));
  _activePanel = new GameBoard(id, document.getElementById('main-panel'));
}

// Quick match found someone: a modal shows who's playing and counts down before the board opens.
const MATCH_INTRO_SECONDS = 3;
let _matchIntroId = null;

async function openMatchIntro(gameId, game = null) {
  if (_matchIntroId === gameId) return;
  _matchIntroId = gameId;
  if (!game) {
    const res = await apiFetch(`/api/games/${gameId}/`);
    game = res.ok ? await res.json().catch(() => null) : null;
    if (!game) { _matchIntroId = null; openGame(gameId); return; }   // the board can show what's wrong
  }

  const me = getUser();
  const chip = (sym) => {
    const p = game.players[sym];
    const you = p.username === me?.username;
    const av = p.is_bot
      ? `<span class="avatar avatar--lg bot-avatar" aria-hidden="true">${GAME_ICON}</span>`
      : avatarHtml({ name: p.display_name, url: p.avatar_url, size: 'lg' });
    return `
      <div class="player-chip player-chip--${sym.toLowerCase()}">
        ${av}
        <span class="player-chip-text">
          <span class="player-chip-name truncate">${escHtml(you ? 'You' : (p.display_name || p.username))}</span>
          <span class="player-chip-meta">${p.is_bot ? 'Computer' : '@' + escHtml(p.username)}</span>
        </span>
        <span class="player-chip-mark" aria-label="plays ${sym}">${MARK_SVG[sym]}</span>
      </div>`;
  };

  let timer = null;
  const titleId = 'mi-' + Math.random().toString(36).slice(2, 8);
  const { modal, layer } = createModal({
    size: 'sm',
    labelledBy: titleId,
    cls: 'match-intro',
    // Closing early (Escape, backdrop) just skips the wait.
    onClose: () => {
      clearTimeout(timer);
      _matchIntroId = null;
      openGame(gameId);
    },
    html: `
      <h2 class="modal-title" id="${titleId}">Match found!</h2>
      <div class="match-intro-players">${chip('X')}<span class="game-vs" aria-hidden="true">vs</span>${chip('O')}</div>
      <p class="match-intro-count" role="status" aria-live="polite"></p>`,
  });
  announce('Match found');

  const count = modal.querySelector('.match-intro-count');
  let left = MATCH_INTRO_SECONDS;
  const tick = () => {
    if (left <= 0) { layer.close('start'); return; }
    count.textContent = `Game starts in ${left}…`;
    left--;
    timer = setTimeout(tick, 1000);
  };
  tick();
}

// ── Actions shared by the lobby, the board and room profile cards ───────────

async function challengePlayer(username, btn) {
  if (btn) btn.disabled = true;
  const res  = await apiFetch('/api/games/challenges/', { method: 'POST', body: JSON.stringify({ username }) });
  const data = await res.json().catch(() => ({}));
  if (btn) btn.disabled = false;

  if (res.ok) {
    showToast(`Challenge sent to ${data.players.O.display_name}. It opens when they accept.`);
    Games.refreshLobby();
    return true;
  }
  if (data.code === 'already_playing' && data.game_status === 'active') {
    openGame(data.game_id);
    return false;
  }
  showToast(_apiError(data, 'Couldn\'t send the challenge.'), 'error');
  return false;
}

async function startBotGame(level) {
  const res  = await apiFetch('/api/games/bot/', { method: 'POST', body: JSON.stringify({ level }) });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) { showToast(_apiError(data, 'Couldn\'t start the game.'), 'error'); return; }
  openGame(data.id);
}

async function answerChallenge(id, accept) {
  const res  = await apiFetch(`/api/games/${id}/${accept ? 'accept' : 'decline'}/`, { method: 'POST' });
  const data = await res.json().catch(() => ({}));
  Games.forgetInvite(id);
  if (!res.ok) { showToast(_apiError(data, 'That challenge is no longer open.'), 'error'); Games.refreshLobby(); return; }
  if (accept) openGame(id);
  else Games.refreshLobby();
}

function _savedLevel() {
  try { return localStorage.getItem('solo.botLevel') || 'medium'; } catch { return 'medium'; }
}
function _saveLevel(level) {
  try { localStorage.setItem('solo.botLevel', level); } catch { /* storage blocked */ }
}

// ── Notifications from the per-user socket (wired in dashboard.js) ──────────

const Games = {
  _invites: new Map(),   // game id → { layer, from }
  _resumes: new Map(),   // game id → layer of an open "wants to continue" prompt

  async init() {
    document.getElementById('nav-games')?.addEventListener('click', (e) => {
      if (e.metaKey || e.ctrlKey || e.shiftKey || e.altKey) return;
      e.preventDefault();
      openGames();
    });
    // Challenges that arrived while we weren't connected still count.
    const res = await apiFetch('/api/games/me/');
    if (!res.ok) return;
    const data = await res.json();
    data.incoming.forEach(g => this._invites.set(g.id, { layer: null, from: g.players.X }));
    this._renderBadge();
  },

  onNotification(msg) {
    if (msg.type === 'game_invite')        this._onInvite(msg);
    if (msg.type === 'game_invite_update') this._onInviteUpdate(msg);
    if (msg.type === 'match_found')        this._onMatchFound(msg);
    if (msg.type === 'game_resume')        this._onResume(msg);
    if (msg.type === 'game_resume_cancel') this._resumes.get(msg.game_id)?.close('withdrawn');
  },

  refreshLobby() {
    if (_activePanel instanceof GamesLobby) _activePanel.refresh();
  },

  forgetInvite(id) {
    const inv = this._invites.get(id);
    this._invites.delete(id);
    inv?.layer?.close('handled');
    this._renderBadge();
  },

  _renderBadge() {
    const slot = document.getElementById('games-badge');
    if (!slot) return;
    const n = this._invites.size;
    slot.innerHTML = n ? `<span class="badge is-entering" aria-label="${n} challenge${n > 1 ? 's' : ''}">${n}</span>` : '';
  },

  _onInvite(msg) {
    const from = msg.from_user;
    const id   = msg.game_id;
    if (this._invites.get(id)?.layer) return;
    this.refreshLobby();

    const titleId = 'gi-' + Math.random().toString(36).slice(2, 8);
    const { overlay, layer } = createModal({
      size: 'sm',
      role: 'alertdialog',
      labelledBy: titleId,
      cls: 'invite-card',
      initialFocus: '[data-act="accept"]',
      // Dismissing without answering (Escape, backdrop) is a decline, so the
      // challenger isn't left waiting. The buttons answer for themselves.
      onClose: (r) => {
        if (r === undefined && this._invites.has(id)) answerChallenge(id, false);
      },
      html: `
        <div class="invite-card-marks" aria-hidden="true">${MARK_SVG.X}${MARK_SVG.O}</div>
        ${avatarHtml({ name: from.display_name, url: from.avatar_url, size: 'lg' })}
        <h2 class="modal-title" id="${titleId}">${escHtml(from.display_name)} wants to play</h2>
        <p class="modal-desc">Tic-Tac-Toe · @${escHtml(from.username)} moves first as X.</p>
        <div class="modal-foot">
          <button type="button" class="btn btn-ghost" data-act="decline">Decline</button>
          <button type="button" class="btn btn-primary" data-act="accept">Accept</button>
        </div>`,
    });
    this._invites.set(id, { layer, from });
    this._renderBadge();
    announce(`${from.display_name} challenged you to Tic-Tac-Toe`);

    overlay.addEventListener('click', (e) => {
      const b = e.target.closest('[data-act]');
      if (!b) return;
      b.disabled = true;
      const accept = b.dataset.act === 'accept';
      layer.close(accept ? 'accept' : 'decline');
      answerChallenge(id, accept);
    });
  },

  _onInviteUpdate(msg) {
    const who = msg.by?.display_name || 'They';
    if (msg.status === 'accepted') {
      showToast(`${who} accepted. Game on!`);
      openGame(msg.game_id);
    } else if (msg.status === 'declined') {
      showToast(`${who} declined your challenge.`, 'error');
    } else if (msg.status === 'cancelled') {
      if (this._invites.has(msg.game_id)) showToast(`${who} withdrew the challenge.`);
      this.forgetInvite(msg.game_id);
    }
    this.refreshLobby();
  },

  // The other player reopened a game you're both in while you're elsewhere.
  _onResume(msg) {
    const id = msg.game_id;
    if (_activePanel instanceof GameBoard && _activePanel.id === id) return;
    if (_matchIntroId === id || this._resumes.has(id)) return;
    const from = msg.from_user;

    const titleId = 'gr-' + Math.random().toString(36).slice(2, 8);
    const { overlay, layer } = createModal({
      size: 'sm',
      role: 'alertdialog',
      labelledBy: titleId,
      cls: 'invite-card',
      initialFocus: '[data-act="join"]',
      // Dismissing without answering counts as "Not now", so they aren't left waiting.
      onClose: (r) => {
        this._resumes.delete(id);
        if (r === undefined || r === 'not-now') apiFetch(`/api/games/${id}/not-now/`, { method: 'POST' });
        if (r === 'withdrawn') showToast(`${from.display_name} left the game.`);
      },
      html: `
        <div class="invite-card-marks" aria-hidden="true">${MARK_SVG.X}${MARK_SVG.O}</div>
        ${avatarHtml({ name: from.display_name, url: from.avatar_url, size: 'lg' })}
        <h2 class="modal-title" id="${titleId}">${escHtml(from.display_name)} wants to continue your game</h2>
        <p class="modal-desc">Tic-Tac-Toe · they're waiting on the board.</p>
        <div class="modal-foot">
          <button type="button" class="btn btn-ghost" data-act="not-now">Not now</button>
          <button type="button" class="btn btn-primary" data-act="join">Join</button>
        </div>`,
    });
    this._resumes.set(id, layer);
    announce(`${from.display_name} wants to continue your Tic-Tac-Toe game`);

    overlay.addEventListener('click', (e) => {
      const b = e.target.closest('[data-act]');
      if (!b) return;
      layer.close(b.dataset.act);
      if (b.dataset.act === 'join') openGame(id);
    });
  },

  _onMatchFound(msg) {
    if (_activePanel instanceof GameBoard && _activePanel.id === msg.game_id) return;
    if (_activePanel instanceof GamesLobby) _activePanel.matched = true;
    openMatchIntro(msg.game_id);
  },
};

// ── Lobby ────────────────────────────────────────────────────────────────────

class GamesLobby {
  constructor(container) {
    this.container = container;
    this.data      = null;
    this.players   = [];
    this.query     = '';
    this.level     = _savedLevel();
    this.queued    = false;
    this.matched   = false;
    this._destroyed = false;
    this._timers   = {};
    this._render();
    this._bind();
    this.refresh();
    this._loadPlayers();
    this._timers.poll = setInterval(() => { if (!document.hidden) this._loadPlayers(); }, 15000);
  }

  _render() {
    this.container.innerHTML = `
      <section class="room games" aria-labelledby="gl-title">
        <header class="room-head">
          <button type="button" class="icon-btn room-nav-btn" data-act="nav" aria-label="Rooms">${icon('menu', 20)}</button>
          <div class="room-head-title">
            <h1 class="room-title" id="gl-title">Games</h1>
            <div class="room-sub"><span class="live-dot" aria-hidden="true"></span><span id="gl-online">Checking who's online…</span></div>
          </div>
        </header>
        <div class="games-scroll">
          <div class="games-wrap">
            <section class="game-hero">
              <div class="game-hero-art" aria-hidden="true">${this._heroBoard()}</div>
              <div class="game-hero-body">
                <p class="kicker">Two players · 3 in a row</p>
                <h2 class="game-hero-title">Tic-Tac-Toe</h2>
                <p class="game-hero-record" id="gl-record">&nbsp;</p>
                <div class="game-hero-actions">
                  <button type="button" class="btn btn-primary" data-act="quick">${GAME_ICON} Quick match</button>
                </div>
                <div class="bot-row">
                  <div class="segmented" role="radiogroup" aria-label="Bot difficulty">
                    ${BOT_LEVELS.map(l => `
                      <button type="button" role="radio" class="segmented-item" data-level="${l.id}"
                              aria-checked="${l.id === this.level}">${l.label}</button>`).join('')}
                  </div>
                  <button type="button" class="btn btn-secondary" data-act="bot">Play vs Bot</button>
                </div>
              </div>
            </section>

            <section class="search-card" id="gl-search" hidden aria-live="polite"></section>

            <section class="games-section" id="gl-incoming" hidden></section>
            <section class="games-section" id="gl-active" hidden></section>
            <section class="games-section" id="gl-outgoing" hidden></section>

            <section class="games-section">
              <div class="games-section-head">
                <h3>Players</h3>
                <span class="mono" id="gl-players-count"></span>
              </div>
              <div class="input-wrap games-find">
                <input class="input" type="search" id="gl-q" placeholder="Search by username" autocomplete="off"
                       autocapitalize="off" spellcheck="false" aria-label="Search players by username">
              </div>
              <div class="player-list" id="gl-players" role="list"></div>
            </section>

            <section class="games-section" id="gl-recent" hidden></section>
          </div>
        </div>
      </section>`;
    this.root = this.container.querySelector('.games');
    const q = (id) => document.getElementById(id);
    this._el = {
      online: q('gl-online'), record: q('gl-record'), search: q('gl-search'),
      incoming: q('gl-incoming'), active: q('gl-active'), outgoing: q('gl-outgoing'),
      players: q('gl-players'), playersCount: q('gl-players-count'), q: q('gl-q'), recent: q('gl-recent'),
    };
  }

  _heroBoard() {
    const b = 'XO-' + '-X-' + 'O-X';
    return `<div class="board board--mini">${[...b].map(c =>
      `<span class="cell">${c === '-' ? '' : MARK_SVG[c]}</span>`).join('')}</div>`;
  }

  _bind() {
    // Bind to this panel's own root: #main-panel outlives every panel.
    this.root.addEventListener('click', (e) => {
      const b = e.target.closest('[data-act], [data-level]');
      if (!b) return;
      if (b.dataset.level) { this._setLevel(b.dataset.level); return; }
      const id = b.closest('[data-game]')?.dataset.game;
      switch (b.dataset.act) {
        case 'nav':       Nav.open(); break;
        case 'quick':     this._quickMatch(); break;
        case 'cancel-q':  this._leaveQueue(); break;
        case 'bot':       this._leaveQueue({ quiet: true }); startBotGame(this.level); break;
        case 'challenge': challengePlayer(b.dataset.username, b); break;
        case 'accept':    answerChallenge(id, true); break;
        case 'decline':   answerChallenge(id, false); break;
        case 'resume':    openGame(id); break;
        case 'withdraw':  this._withdraw(id, b); break;
      }
    });

    // Arrow keys move within the difficulty radio group
    this.container.querySelector('.segmented').addEventListener('keydown', (e) => {
      if (!['ArrowLeft', 'ArrowRight', 'ArrowUp', 'ArrowDown'].includes(e.key)) return;
      e.preventDefault();
      const ids = BOT_LEVELS.map(l => l.id);
      const step = (e.key === 'ArrowRight' || e.key === 'ArrowDown') ? 1 : -1;
      this._setLevel(ids[(ids.indexOf(this.level) + step + ids.length) % ids.length], true);
    });

    this._el.q.addEventListener('input', () => {
      clearTimeout(this._timers.search);
      this._timers.search = setTimeout(() => {
        this.query = this._el.q.value.trim();
        this._loadPlayers();
      }, 220);
    });
  }

  _setLevel(level, focus = false) {
    this.level = level;
    _saveLevel(level);
    this.container.querySelectorAll('.segmented-item').forEach((el) => {
      const on = el.dataset.level === level;
      el.setAttribute('aria-checked', String(on));
      el.tabIndex = on ? 0 : -1;
      if (on && focus) el.focus();
    });
  }

  // ── Data ─────────────────────────────────────────────────────────────────

  async refresh() {
    const res = await apiFetch('/api/games/me/');
    if (this._destroyed || !res.ok) return;
    this.data = await res.json();
    this._renderOverview();
    if (this.data.queued && !this.queued) { this._showSearching(); this._tryMatch(); }   // e.g. queued from another tab
  }

  async _loadPlayers() {
    const q = this.query;
    const res = await apiFetch('/api/games/players/' + (q ? '?q=' + encodeURIComponent(q) : ''));
    if (this._destroyed || q !== this.query) return;
    if (!res.ok) {
      this._el.players.innerHTML = '<p class="games-empty">Players didn\'t load. Check your connection.</p>';
      return;
    }
    this.players = await res.json();
    this._renderPlayers();
  }

  // ── Render pieces ────────────────────────────────────────────────────────

  _renderOverview() {
    const d = this.data;
    const s = d.stats, b = d.bot_stats;
    const played = s.wins + s.losses + s.draws;
    const botPlayed = b.wins + b.losses + b.draws;
    this._el.record.innerHTML = [
      played ? `<span><strong>${s.wins}</strong> won</span><span><strong>${s.losses}</strong> lost</span><span><strong>${s.draws}</strong> drawn</span>`
             : '<span>No games against people yet</span>',
      botPlayed ? `<span class="game-hero-record-bot">vs Bot ${_recordText(b)}</span>` : '',
    ].join('');

    const n = d.online_count;
    this._el.online.textContent = n ? `${n} other player${n !== 1 ? 's' : ''} online` : 'No one else online · the bot is always in';
    this.container.querySelector('.room-sub .live-dot').classList.toggle('is-idle', !n);

    this._section(this._el.incoming, 'Challenges for you', d.incoming, (g) => {
      const p = g.players.X;
      return this._row(p, 'wants to play', `
        <button type="button" class="btn btn-ghost btn-sm" data-act="decline">Decline</button>
        <button type="button" class="btn btn-primary btn-sm" data-act="accept">Accept</button>`, g.id);
    });
    this._section(this._el.active, 'Games in progress', d.active, (g) => {
      const opp = _opponentOf(g);
      const turn = g.next === _mySymbol(g) ? 'Your turn' : `${opp.is_bot ? 'Bot' : opp.display_name.split(' ')[0]}'s turn`;
      return this._row(opp, turn, '<button type="button" class="btn btn-secondary btn-sm" data-act="resume">Resume</button>', g.id);
    });
    this._section(this._el.outgoing, 'Waiting for an answer', d.outgoing, (g) =>
      this._row(g.players.O, 'Challenge sent', '<button type="button" class="btn btn-ghost btn-sm" data-act="withdraw">Withdraw</button>', g.id));
    this._section(this._el.recent, 'Recent results', d.recent, (g) => {
      const opp = _opponentOf(g);
      const out = _outcomeFor(g);
      const label = { win: 'Won', loss: 'Lost', draw: 'Draw' }[out];
      const how = g.resigned ? (out === 'win' ? ' · they resigned' : ' · resigned')
                : g.abandoned ? (out === 'win' ? ' · they left' : ' · you left') : '';
      return this._row(opp, `${relativeTime(g.finished_at)}${how}`,
        `<span class="result-chip result-chip--${out}">${label}</span>`, g.id, true);
    });
  }

  _section(el, title, items, rowFn) {
    el.hidden = !items.length;
    if (!items.length) { el.innerHTML = ''; return; }
    el.innerHTML = `
      <div class="games-section-head"><h3>${escHtml(title)}</h3><span class="mono">${items.length}</span></div>
      <div class="player-list" role="list">${items.map(rowFn).join('')}</div>`;
  }

  _row(p, meta, actions, gameId = '', clickable = false) {
    const name = p.is_bot ? p.display_name : (p.display_name || p.username);
    const av = p.is_bot
      ? `<span class="avatar avatar--md bot-avatar" aria-hidden="true">${GAME_ICON}</span>`
      : avatarHtml({ name, url: p.avatar_url, size: 'md' });
    return `
      <div class="player-row" role="listitem" ${gameId ? `data-game="${escHtml(gameId)}"` : ''}>
        ${clickable ? `<button type="button" class="player-row-hit" data-act="resume" aria-label="Open game with ${escHtml(name)}"></button>` : ''}
        ${av}
        <span class="player-row-text">
          <span class="player-row-name truncate">${escHtml(name)}</span>
          <span class="player-row-meta truncate">${escHtml(meta)}</span>
        </span>
        <span class="player-row-actions">${actions}</span>
      </div>`;
  }

  _renderPlayers() {
    const list = this.players;
    const online = list.filter(p => p.online).length;
    this._el.playersCount.textContent = this.query ? `${list.length} found` : (online ? `${online} online` : '');
    if (!list.length) {
      this._el.players.innerHTML = this.query
        ? `<p class="games-empty">No one matches “${escHtml(this.query)}”.</p>`
        : `<div class="games-empty">
             <strong>No one else is online right now.</strong>
             Search a username to see if a friend is around, or warm up against the bot.
           </div>`;
      return;
    }
    this._el.players.innerHTML = list.map(p => {
      const meta = [
        '@' + p.username,
        _recordText(p.stats),
      ].join(' · ');
      const status = p.online
        ? '<span class="online-dot" title="Online"><span class="sr-only">Online</span></span>'
        : '<span class="sr-only">Offline</span>';
      const btn = p.online
        ? `<button type="button" class="btn btn-secondary btn-sm" data-act="challenge" data-username="${escHtml(p.username)}">Challenge</button>`
        : '<span class="player-row-offline">Offline</span>';
      return this._row(p, meta, btn).replace('<span class="player-row-text">', status + '<span class="player-row-text">');
    }).join('');
  }

  // ── Quick match ──────────────────────────────────────────────────────────

  async _quickMatch() {
    if (this.queued) return;
    this._showSearching();
    await this._tryMatch();
  }

  async _tryMatch() {
    clearTimeout(this._timers.retry);
    if (this._destroyed || !this.queued) return;
    const res  = await apiFetch('/api/games/quick-match/', { method: 'POST' });
    const data = await res.json().catch(() => ({}));
    if (this._destroyed || !this.queued) return;
    if (res.status === 200 && data.status === 'matched') {
      this.matched = true;
      openMatchIntro(data.game.id, data.game);
      return;
    }
    if (!res.ok) { this._hideSearching(); showToast('Quick match is unavailable right now.', 'error'); return; }
    if (data.online_count === 0) this._offerBot('No one else is online right now.');
    // Re-asking is harmless and catches two people who joined at the same instant.
    this._timers.retry = setTimeout(() => this._tryMatch(), QUICK_MATCH_RETRY_MS);
  }

  _showSearching() {
    this.queued = true;
    this._searchStart = Date.now();
    const el = this._el.search;
    el.hidden = false;
    el.innerHTML = `
      <div class="search-card-row">
        <span class="radar" aria-hidden="true"><span></span><span></span></span>
        <span class="search-card-text">
          <strong>Finding an opponent…</strong>
          <span class="mono" id="gl-search-time">0:00</span>
        </span>
        <button type="button" class="btn btn-ghost btn-sm" data-act="cancel-q">Cancel</button>
      </div>
      <div class="search-card-offer" id="gl-offer" hidden></div>`;
    this.container.querySelector('[data-act="quick"]').disabled = true;
    announce('Looking for an opponent');
    this._timers.tick = setInterval(() => {
      const t = document.getElementById('gl-search-time');
      if (t) t.textContent = formatDuration((Date.now() - this._searchStart) / 1000);
    }, 1000);
    this._timers.offer = setTimeout(() => this._offerBot('No one’s turned up yet.'), QUICK_MATCH_BOT_OFFER_MS);
  }

  _offerBot(reason) {
    const el = document.getElementById('gl-offer');
    if (!el || !el.hidden) return;
    el.hidden = false;
    const level = BOT_LEVELS.find(l => l.id === this.level)?.label || 'Medium';
    el.innerHTML = `
      <span>${escHtml(reason)} Play the bot while you wait?</span>
      <button type="button" class="btn btn-primary btn-sm" data-act="bot">Play Bot · ${escHtml(level)}</button>`;
  }

  _hideSearching() {
    this.queued = false;
    clearInterval(this._timers.tick);
    clearTimeout(this._timers.offer);
    clearTimeout(this._timers.retry);
    this._el.search.hidden = true;
    this._el.search.innerHTML = '';
    const btn = this.container.querySelector('[data-act="quick"]');
    if (btn) btn.disabled = false;
  }

  _leaveQueue({ quiet = false } = {}) {
    if (!this.queued) return;
    this._hideSearching();
    apiFetch('/api/games/quick-match/', { method: 'DELETE' });
    if (!quiet) announce('Stopped looking');
  }

  async _withdraw(id, btn) {
    btn.disabled = true;
    const res = await apiFetch(`/api/games/${id}/cancel/`, { method: 'POST' });
    if (!res.ok) showToast('That challenge was already answered.', 'error');
    this.refresh();
  }

  destroy() {
    this._destroyed = true;
    Object.values(this._timers).forEach((t) => { clearTimeout(t); clearInterval(t); });
    // Leaving the lobby stops the search, unless it just found someone.
    if (this.queued && !this.matched) apiFetch('/api/games/quick-match/', { method: 'DELETE' });
  }
}

// ── Board ────────────────────────────────────────────────────────────────────

// Centre of each cell on the 300×300 overlay used for the winning line
const _cellCentre = (i) => [50 + (i % 3) * 100, 50 + Math.floor(i / 3) * 100];

class GameBoard {
  constructor(id, container) {
    this.id        = id;
    this.container = container;
    this.game      = null;
    this.prevBoard = null;
    this.mine      = null;
    this.focusIdx  = 4;
    this.opponentHere = false;
    this._away     = null;   // why the opponent isn't on the board, and when the win can be claimed
    this._pending  = null;   // index of a move sent but not yet confirmed
    this._destroyed = false;
    this.socket    = null;
    this._render();
    this._bind();
    this._connect();
  }

  _render() {
    this.container.innerHTML = `
      <section class="room games" aria-labelledby="gb-title">
        <header class="room-head">
          <button type="button" class="icon-btn room-nav-btn" data-act="nav" aria-label="Rooms">${icon('menu', 20)}</button>
          <button type="button" class="icon-btn" data-act="lobby" aria-label="Back to games" title="Back to games">${icon('chevronL', 20)}</button>
          <div class="room-head-title">
            <h1 class="room-title" id="gb-title">Tic-Tac-Toe</h1>
            <div class="room-sub">
              <span class="conn" id="gb-conn" data-state="connecting" role="status">
                <span class="conn-dot" aria-hidden="true"></span><span class="conn-label">Connecting…</span>
              </span>
              <span class="room-sub-sep" aria-hidden="true">·</span>
              <span id="gb-vs" class="truncate"></span>
            </div>
          </div>
          <button type="button" class="btn btn-ghost btn-sm" data-act="resign" id="gb-resign" hidden>Resign</button>
        </header>
        <div class="games-scroll">
          <div class="game-stage">
            <div class="game-players" id="gb-players"></div>
            <p class="game-status" id="gb-status" aria-live="polite">&nbsp;</p>
            <div class="game-away" id="gb-away" hidden></div>
            <div class="board-wrap">
              <div class="board" id="gb-board" role="grid" aria-label="Tic-Tac-Toe board" aria-busy="true">
                ${[0, 1, 2].map(r => `<div class="board-row" role="row">${[0, 1, 2].map(c => {
                  const i = r * 3 + c;
                  return `<button type="button" class="cell" role="gridcell" data-i="${i}" tabindex="${i === 4 ? 0 : -1}" aria-disabled="true"></button>`;
                }).join('')}</div>`).join('')}
              </div>
              <svg class="win-line" id="gb-line" viewBox="0 0 300 300" aria-hidden="true" focusable="false"></svg>
              <div class="game-result" id="gb-result" hidden></div>
            </div>
          </div>
        </div>
      </section>`;
    this.root = this.container.querySelector('.games');
    const q = (id) => document.getElementById(id);
    this._el = {
      conn: q('gb-conn'), vs: q('gb-vs'), resign: q('gb-resign'), players: q('gb-players'),
      status: q('gb-status'), board: q('gb-board'), line: q('gb-line'), result: q('gb-result'),
      away: q('gb-away'),
    };
    this._cells = [...this._el.board.querySelectorAll('.cell')];
  }

  _bind() {
    // Bind to this panel's own root: #main-panel outlives every panel.
    this.root.addEventListener('click', (e) => {
      const cell = e.target.closest('.cell');
      if (cell) {
        if (cell.getAttribute('aria-disabled') !== 'true') this._play(Number(cell.dataset.i));
        return;
      }
      const b = e.target.closest('[data-act]');
      if (!b) return;
      switch (b.dataset.act) {
        case 'nav':     Nav.open(); break;
        case 'lobby':   this._leave(); break;
        case 'claim':   b.disabled = true; this._send({ type: 'claim' }); break;
        case 'resign':  this._resign(); break;
        case 'rematch': this._rematch(b); break;
        case 'retry':   this._retryNow(); break;
      }
    });
    this._el.conn.addEventListener('click', (e) => { if (e.target.closest('.conn-retry')) this._retryNow(); });

    // Arrow keys move around the grid; Enter/Space play the focused square.
    this._el.board.addEventListener('keydown', (e) => {
      const moves = { ArrowLeft: -1, ArrowRight: 1, ArrowUp: -3, ArrowDown: 3 };
      if (!(e.key in moves)) return;
      e.preventDefault();
      const i = this.focusIdx, d = moves[e.key];
      const col = i % 3;
      let next = i + d;
      if ((d === -1 && col === 0) || (d === 1 && col === 2) || next < 0 || next > 8) return;
      this._focusCell(next);
    });
    this._el.board.addEventListener('focusin', (e) => {
      const cell = e.target.closest('.cell');
      if (cell) this._focusCell(Number(cell.dataset.i), false);
    });
  }

  _focusCell(i, move = true) {
    this.focusIdx = i;
    this._cells.forEach((c, j) => { c.tabIndex = j === i ? 0 : -1; });
    if (move) this._cells[i].focus();
  }

  // ── Socket ───────────────────────────────────────────────────────────────

  // LiveSocket (socket.js) keeps the line alive and reconnects on its own;
  // the server resends the whole board on every connect.
  _connect() {
    this.socket = new LiveSocket(`/ws/games/${encodeURIComponent(this.id)}/`, {
      onState: (state) => { if (state !== 'live') this._setConn(state); },
      onOpen: () => {
        this.opponentHere = false;
        this._setConn('live');
      },
      onDenied: (code) => {
        this._el.status.textContent = code === 4004 ? 'This game doesn\'t exist.'
          : code === 4003 ? 'You\'re not a player in this game.'
          : 'Your session ended. Sign in again to keep playing.';
      },
      onMessage: (msg) => {
        if (msg.type === 'game_state')      this._onState(msg.game);
        if (msg.type === 'player_presence') this._onPresence(msg);
        if (msg.type === 'opponent')        this._onOpponent(msg);
        if (msg.type === 'error') {
          showToast(msg.error, 'error');
          this._pending = null;
          this._renderAway();   // re-enables Claim win if the claim was refused
          if (this.game) this._onState(this.game, { replay: false });
        }
      },
    });
  }

  _send(payload) {
    if (this.socket?.send(payload)) return true;
    showToast('Not connected — reconnecting…', 'error');
    this._retryNow();
    return false;
  }

  _retryNow() { this.socket?.retryNow(); }

  _setConn(state) {
    const el = this._el.conn;
    el.dataset.state = state;
    el.querySelector('.conn-label').innerHTML = {
      connecting:   'Connecting…',
      live:         'Live',
      reconnecting: 'Reconnecting…',
      offline:      'Offline · <button type="button" class="conn-retry">Retry</button>',
      denied:       'Can\'t open this game',
    }[state];
    if (state !== 'live') this._renderBoard();   // locks the board while we can't send
  }

  _onPresence(msg) {
    const me = getUser();
    if (!this.game || msg.username === me?.username) return;
    const name = msg.display_name || msg.username;
    if (msg.event === 'join') {
      if (this._away) showToast(`${name} is back.`);
      this.opponentHere = true;
      this._away = null;
      this._send({ type: 'here' });   // tell the newcomer we're already here
    } else if (msg.event === 'here') {
      this.opponentHere = true;
      this._away = null;
    } else if (msg.event === 'leave' || msg.event === 'busy') {
      this.opponentHere = false;
      this._setAway({ reason: msg.event === 'busy' ? 'busy' : msg.left ? 'left' : 'dropped', claimIn: msg.claim_in });
      if (msg.event === 'leave' && msg.left && this.game?.status === 'active') showToast(`${name} left the game.`);
    }
    this._renderPlayers();
    this._renderAway();
  }

  // Sent once on connect: where the opponent is right now.
  _onOpponent(msg) {
    this.opponentHere = msg.here;
    if (msg.here) this._away = null;
    else this._setAway({
      reason: !msg.online ? 'offline' : msg.notified ? 'notified' : msg.left ? 'left' : 'dropped',
      claimIn: msg.claim_in,
    });
    this._renderPlayers();
    this._renderAway();
  }

  _setAway({ reason, claimIn = 0 }) {
    this._away = { reason, claimAt: Date.now() + (claimIn || 0) * 1000 };
  }

  // A line under the status saying why the opponent isn't here, with a way
  // out so nobody waits on someone who isn't coming back.
  _renderAway() {
    clearTimeout(this._awayTimer);
    const el = this._el.away;
    const g = this.game;
    if (!g || !this._away || g.status !== 'active' || g.vs_bot) { el.hidden = true; el.innerHTML = ''; return; }

    const opp = _opponentOf(g);
    const name = (opp.display_name || opp.username).split(' ')[0];
    const text = {
      left:     `${name} left the game.`,
      busy:     `${name} can't play right now.`,
      offline:  `${name} is offline.`,
      notified: `We let ${name} know you're back. Waiting for them…`,
      dropped:  `${name} lost connection. Waiting for them to come back…`,
    }[this._away.reason];
    const wait = Math.ceil((this._away.claimAt - Date.now()) / 1000);
    const btn = wait > 0
      ? `<button type="button" class="btn btn-secondary btn-sm" disabled>Claim win in ${formatDuration(wait)}</button>`
      : '<button type="button" class="btn btn-primary btn-sm" data-act="claim">Claim win</button>';

    el.hidden = false;
    el.innerHTML = `<span class="game-away-text">${escHtml(text)}</span>${btn}`;
    if (wait > 0) this._awayTimer = setTimeout(() => this._renderAway(), 1000);
  }

  // ── State ────────────────────────────────────────────────────────────────

  _onState(game, { replay = true } = {}) {
    const first = !this.game;
    const was   = this.game?.status;
    this.prevBoard = replay ? (this.game?.board ?? null) : this.prevBoard;
    this.game = game;
    this.mine = _mySymbol(game);
    if (this._pending !== null && game.board[this._pending] !== '-') this._pending = null;

    if (first) {
      const opp = _opponentOf(game);
      this._el.vs.textContent = `vs ${opp.display_name}`;
      if (opp.is_bot) this.opponentHere = true;
    }
    this._renderPlayers();
    this._renderBoard({ animate: !first && replay });
    this._renderStatus();
    this._renderAway();
    if (game.status === 'finished' && was !== 'finished') this._finish({ animate: !first });
    else if (game.status === 'finished' && first) this._finish({ animate: false });
  }

  _myTurn() {
    const g = this.game;
    return !!g && g.status === 'active' && g.next === this.mine && this._pending === null
      && !!this.socket?.isOpen;
  }

  _renderPlayers() {
    const g = this.game;
    if (!g) return;
    const chip = (sym) => {
      const p = g.players[sym];
      const you = sym === this.mine;
      const name = you ? 'You' : (p.display_name || p.username);
      const av = p.is_bot
        ? `<span class="avatar avatar--lg bot-avatar" aria-hidden="true">${GAME_ICON}</span>`
        : avatarHtml({ name: p.display_name, url: p.avatar_url, size: 'lg' });
      const away = !you && !p.is_bot && !this.opponentHere && g.status === 'active';
      const turn = g.status === 'active' && g.next === sym;
      return `
        <div class="player-chip player-chip--${sym.toLowerCase()} ${turn ? 'is-turn' : ''} ${away ? 'is-away' : ''}">
          ${av}
          <span class="player-chip-text">
            <span class="player-chip-name truncate">${escHtml(name)}</span>
            <span class="player-chip-meta">${away ? 'Away' : (p.is_bot ? 'Computer' : '@' + escHtml(p.username))}</span>
          </span>
          <span class="player-chip-mark" aria-label="plays ${sym}">${MARK_SVG[sym]}</span>
        </div>`;
    };
    this._el.players.innerHTML = `${chip('X')}<span class="game-vs" aria-hidden="true">vs</span>${chip('O')}`;
  }

  _renderBoard({ animate = false } = {}) {
    const g = this.game;
    if (!g) return;
    const myTurn = this._myTurn();
    const board = this._pending !== null ? g.board.slice(0, this._pending) + this.mine + g.board.slice(this._pending + 1) : g.board;
    const line = g.winning_line || [];

    this._el.board.removeAttribute('aria-busy');
    this._el.board.dataset.myTurn = String(myTurn);
    this._el.board.dataset.mine = this.mine || '';
    this._el.board.classList.toggle('is-over', g.status === 'finished');
    this._el.board.classList.toggle('is-draw', g.result === 'draw');

    this._cells.forEach((cell, i) => {
      const v = board[i];
      const was = this.prevBoard ? this.prevBoard[i] : v;
      const fresh = (animate && v !== '-' && was === '-') || (i === this._pending);
      const key = v + (fresh ? '*' : '');
      if (cell.dataset.v !== key) {
        cell.innerHTML = v === '-' ? (this.mine ? `<span class="ghost">${MARK_SVG[this.mine]}</span>` : '') : MARK_SVG[v];
        cell.dataset.v = key;
        cell.classList.toggle('is-new', fresh);
      }
      // aria-disabled rather than disabled: a disabled button can't take
      // focus, and the board stays keyboard-navigable while you wait.
      const playable = myTurn && v === '-';
      cell.setAttribute('aria-disabled', String(!playable));
      cell.classList.toggle('is-playable', playable);
      cell.classList.toggle('is-last', g.last_move === i && g.status === 'active');
      cell.classList.toggle('is-win', line.includes(i));
      cell.classList.toggle('is-dim', g.status === 'finished' && line.length > 0 && !line.includes(i));
      const r = Math.floor(i / 3) + 1, c = (i % 3) + 1;
      cell.setAttribute('aria-label', `Row ${r}, column ${c}, ${v === '-' ? 'empty' : v}`);
    });
  }

  _renderStatus() {
    const g = this.game;
    const opp = _opponentOf(g);
    const oppName = opp.is_bot ? 'The bot' : (opp.display_name || opp.username).split(' ')[0];
    let text;
    switch (g.status) {
      case 'pending':   text = g.players.X.username === getUser()?.username ? `Waiting for ${oppName} to accept…` : 'Challenge waiting for your answer'; break;
      case 'declined':  text = `${oppName} declined this challenge.`; break;
      case 'cancelled': text = 'This challenge was withdrawn or expired.'; break;
      case 'active':
        text = g.next === this.mine ? 'Your turn' : (opp.is_bot ? 'The bot is thinking…' : `Waiting for ${oppName}…`);
        break;
      case 'finished': {
        const out = _outcomeFor(g);
        text = out === 'draw' ? 'It’s a draw.'
             : out === 'win'  ? (g.resigned ? `${oppName} resigned. You win!` : g.abandoned ? `${oppName} left. You win!` : 'You win!')
             : (g.resigned ? 'You resigned.' : g.abandoned ? `You left, so ${oppName} wins.` : `${oppName} wins.`);
        break;
      }
    }
    const el = this._el.status;
    el.className = 'game-status' + (g.status === 'active' && g.next === this.mine ? ' is-yours' : '');
    if (el.textContent !== text) el.textContent = text;
    this._el.resign.hidden = g.status !== 'active';
    _stageTitle = g.status === 'active' && g.next === this.mine ? 'Your turn · Tic-Tac-Toe' : 'Tic-Tac-Toe';
    updateTitle();
  }

  _finish({ animate }) {
    const g = this.game;
    const out = _outcomeFor(g);
    this._drawLine(g.winning_line, animate);

    const head = { win: 'You win', loss: 'You lose', draw: 'Draw' }[out];
    const opp = _opponentOf(g);
    const sub = out === 'draw' ? 'Nobody got three in a row.'
              : g.resigned ? (out === 'win' ? 'Your opponent resigned.' : 'You resigned this one.')
              : g.abandoned ? (out === 'win' ? 'Your opponent left the game.' : 'You left the game.')
              : out === 'win' ? 'Three in a row.' : `${opp.is_bot ? 'The bot' : opp.display_name} got three in a row.`;
    const el = this._el.result;
    el.hidden = false;
    el.className = `game-result game-result--${out}` + (animate ? ' is-entering' : '');
    el.innerHTML = `
      <div class="game-result-card">
        <p class="game-result-title">${head}</p>
        <p class="game-result-sub">${escHtml(sub)}</p>
        <div class="game-result-actions">
          <button type="button" class="btn btn-ghost btn-sm" data-act="lobby">Back to games</button>
          <button type="button" class="btn btn-primary btn-sm" data-act="rematch">Rematch</button>
        </div>
      </div>`;
    announce(`${head}. ${sub}`);
    if (animate) setTimeout(() => el.querySelector('[data-act="rematch"]')?.focus({ preventScroll: true }), 600);
  }

  _drawLine(line, animate) {
    if (!line) { this._el.line.innerHTML = ''; return; }
    this._el.line.dataset.winner = this.game.board[line[0]];
    const [x1, y1] = _cellCentre(line[0]);
    const [x2, y2] = _cellCentre(line[2]);
    // Run the stroke a little past the outer cells' centres
    const dx = (x2 - x1) * 0.14, dy = (y2 - y1) * 0.14;
    this._el.line.innerHTML = `<line pathLength="1" class="${animate ? 'is-drawing' : ''}"
      x1="${x1 - dx}" y1="${y1 - dy}" x2="${x2 + dx}" y2="${y2 + dy}"/>`;
  }

  // ── Actions ──────────────────────────────────────────────────────────────

  _play(i) {
    if (!this._myTurn() || this.game.board[i] !== '-') return;
    if (!this._send({ type: 'move', index: i })) return;
    this._pending = i;   // show it now; the server's state confirms it
    this._renderBoard();
  }

  async _resign() {
    const ok = await confirmDialog({
      title: 'Resign this game?',
      body: 'It counts as a loss.',
      confirmLabel: 'Resign',
      danger: true,
    });
    if (ok) this._send({ type: 'resign' });
  }

  _inLiveHumanGame() {
    return this.game?.status === 'active' && !this.game.vs_bot;
  }

  async _leave() {
    if (this._inLiveHumanGame()) {
      const opp = _opponentOf(this.game);
      const ok = await confirmDialog({
        title: 'Leave this game?',
        body: `${opp.display_name} will be told you left and can claim the win.`,
        confirmLabel: 'Leave',
        danger: true,
      });
      if (!ok) return;
    }
    openGames();
  }

  async _rematch(btn) {
    btn.disabled = true;
    const res  = await apiFetch(`/api/games/${this.id}/rematch/`, { method: 'POST' });
    const data = await res.json().catch(() => ({}));
    btn.disabled = false;
    if (!res.ok) {
      if (data.code === 'already_playing' && data.game_status === 'active') { openGame(data.game_id); return; }
      showToast(_apiError(data, 'Couldn\'t start a rematch.'), 'error');
      return;
    }
    if (data.status === 'active') { openGame(data.id); return; }
    btn.textContent = 'Rematch sent';
    btn.disabled = true;
    showToast(`Rematch sent to ${data.players.O.display_name}. It opens when they accept.`);
  }

  destroy() {
    this._destroyed = true;
    clearTimeout(this._awayTimer);
    if (this.socket) {
      // Navigating away inside the app is leaving on purpose; a closed tab or
      // a dropped connection gets the reconnect grace period instead.
      if (this._inLiveHumanGame() && this.socket.isOpen) this.socket.send({ type: 'leave' });
      this.socket.close();
      this.socket = null;
    }
  }
}
