# Data Models

All primary keys that appear in URLs are UUIDs. Chat models live in `chat/models.py`, the user in `accounts/models.py`, games in `games/models.py`.

```
User
  id          UUID (PK)
  email       unique — used as USERNAME_FIELD for login
  username    unique, alphanumeric + underscore, lowercase-normalised on signup
  display_name
  avatar      ImageField → media/avatars/
  bio         TextField (optional)
  is_active · is_staff · date_joined

Room
  id          UUID (PK)
  name        unique display name
  description optional
  slug        UUID — the invite token in share links (separate from id)
  creator  ── User (nullable; null if creator deleted account)
  created_at

RoomMembership
  user     ── User
  room     ── Room
  joined_at
  last_seen   updated on every room open → drives unread counts
  UNIQUE (user, room)

Message
  id           UUID (PK)
  room      ── Room
  sender    ── User (nullable — legacy anonymous compat)
  username     always stored for display (survives sender deletion)
  message_type text | image | voice
  content      TextField (text messages)
  file         FileField → media/uploads/%Y/%m/%d/ (image/voice)
  duration     seconds, for voice notes (reported by the recorder)
  timestamp
```

## Games

```
UserPresence
  user      ── User (one-to-one)
  connections  open notification sockets (one per dashboard tab)
  last_seen    refreshed by the 30 s heartbeat
  → online = connections > 0 AND last_seen within 90 s

Game
  id           UUID (PK)
  player_x  ── User   — always present; moves first
  player_o  ── User   — null in bot games (the bot always plays O)
  vs_bot       bool
  bot_level    easy | medium | hard  (bot games only)
  board        9 chars, "-" = empty, cells 0–8 left→right, top→bottom
  last_move    0–8 (nullable)
  status       pending (a challenge) | active | finished | declined | cancelled
  result       x | o | draw  (set when finished)
  resigned     bool — the game ended by resignation, not three in a row
  created_at · updated_at · finished_at
  INDEX (status, finished_at)

MatchQueueEntry
  user      ── User (one-to-one) — a player waiting for Quick match
  created_at
```

Whose turn it is is not stored: it follows from the board (X moves first, so it is X's turn whenever both marks appear equally often). A player's record — wins, losses, draws — is computed from finished games rather than stored, so it can never disagree with the games themselves. See [Games](games.md) for the full rules.
