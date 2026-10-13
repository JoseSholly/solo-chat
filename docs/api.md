# API Reference

Pages, REST endpoints and WebSocket messages. For how the pieces fit together see [Architecture](architecture.md); for the game rules behind the `/api/games/` endpoints see [Games](games.md).

- [Page routes](#page-routes)
- [Auth](#auth--apiauth) · [Rooms](#rooms--api) · [Games](#games--apigames)
- WebSockets: [Chat](#chat--wschatroom-slugtokenaccess_token) · [Notifications](#notifications--wsnotificationstokenaccess_token) · [Game](#game--wsgamesgame-idtokenaccess_token)

## Page routes

| URL | Page |
|---|---|
| `/` | Landing page |
| `/signup/` | Create an account |
| `/login/` | Log in |
| `/dashboard/` | Your rooms — select or create |
| `/dashboard/?room=<slug>` | Dashboard with a room open |
| `/dashboard/?games` | Games lobby (Tic-Tac-Toe) |
| `/dashboard/?game=<id>` | Dashboard with a game board open |
| `/profile/` | Edit display name, bio, and avatar |
| `/join/<slug>/` | Accept a room invite |
| `/admin/` | Django admin (Jazzmin) |

## Authentication

All authenticated endpoints require:

```
Authorization: Bearer <access_token>
```

## Auth — `/api/auth/`

| Method | Endpoint | Auth | Description |
|---|---|---|---|
| `POST` | `signup/` | — | Register; returns `{ access, refresh, user }` |
| `POST` | `login/` | — | Authenticate; returns `{ access, refresh, user }` |
| `POST` | `logout/` | ✓ | Blacklist the refresh token |
| `GET` | `me/` | ✓ | Current user profile |
| `PATCH` | `me/` | ✓ | Update display name, bio, or avatar (multipart) |
| `POST` | `token/refresh/` | — | Exchange refresh token for new access + refresh |
| `GET` | `users/<username>/` | ✓ | Public profile of another user, including `game_stats` (`{ wins, losses, draws }` against people) |

## Rooms — `/api/`

| Method | Endpoint | Auth | Description |
|---|---|---|---|
| `GET` | `dashboard/` | ✓ | All rooms — last message preview + unread count |
| `POST` | `rooms/` | ✓ | Create a room (`name` required, `description` optional) |
| `GET` | `rooms/<slug>/` | ✓ member | Room info + last 50 messages; updates `last_seen` |
| `POST` | `rooms/<slug>/upload/` | ✓ member | Upload image or voice note (multipart) |
| `PATCH` | `rooms/<slug>/seen/` | ✓ member | Manually mark room as read |
| `GET` | `rooms/<slug>/members/` | ✓ member | Paginated member list (`limit`, `offset`) |
| `POST` | `rooms/<slug>/leave/` | ✓ member | Leave a room (creator cannot leave) |
| `DELETE` | `rooms/<slug>/delete/` | ✓ creator | Permanently delete a room |
| `GET` | `invite/<slug>/` | public | Resolve invite link — room info + member count |
| `POST` | `invite/<slug>/join/` | ✓ | Join a room via invite link |

## Games — `/api/games/`

All endpoints require authentication. Games are returned in one shape everywhere (REST responses and the game socket's `game_state` event):

```jsonc
{
  "id": "<uuid>",
  "status": "active",            // pending | active | finished | declined | cancelled
  "board": "X---O----",          // 9 cells, left→right, top→bottom; "-" is empty
  "next": "X",                   // whose turn, or null when not active
  "result": null,                // "x" | "o" | "draw" once finished
  "resigned": false,
  "winning_line": null,          // e.g. [0, 1, 2] after a three-in-a-row win
  "last_move": 4,
  "vs_bot": false,
  "bot_level": null,             // easy | medium | hard for bot games
  "players": {
    "X": { "username": "alice", "display_name": "Alice", "avatar_url": null, "is_bot": false },
    "O": { "username": "bob",   "display_name": "Bob",   "avatar_url": null, "is_bot": false }
  },
  "created_at": "2026-10-13T12:00:00+00:00",
  "finished_at": null
}
```

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `players/` | Players online right now (excluding you), each with `online` and `stats` |
| `GET` | `players/?q=<text>` | Search everyone by username or display name (online first, max 20) |
| `GET` | `me/` | Lobby overview: `stats`, `bot_stats`, `incoming` / `outgoing` challenges, `active` games, `recent` results, `queued`, `online_count` |
| `POST` | `challenges/` | Challenge a player: `{ "username": "bob" }`. `201` with the pending game |
| `POST` | `<id>/accept/` | Accept a challenge (challenged player only) |
| `POST` | `<id>/decline/` | Decline a challenge (challenged player only) |
| `POST` | `<id>/cancel/` | Withdraw your challenge (challenger only) |
| `GET` | `<id>/` | Game state (players only) |
| `POST` | `<id>/rematch/` | After a finished game: a new bot game, or a new challenge to the same opponent |
| `POST` | `bot/` | Start a game against the computer: `{ "level": "easy" \| "medium" \| "hard" }` |
| `POST` | `quick-match/` | Join Quick match. `200 { status: "matched", game }` or `202 { status: "waiting", online_count }` |
| `DELETE` | `quick-match/` | Leave the Quick match queue |

Errors use the same `{ "error", "code" }` shape as the rest of the API:

| Status | `code` | When |
|---|---|---|
| `400` | `missing_username`, `self_challenge`, `invalid_level`, `invalid_move` | Bad input |
| `403` | `forbidden` | Not your game / not your challenge to answer |
| `404` | `not_found` | Unknown user or game |
| `409` | `offline` | The player you challenged isn't online |
| `409` | `already_playing` | You already have a pending or active game with them (response includes `game_id`, `game_status`) |
| `409` | `not_your_turn`, `occupied`, `not_active`, `not_finished` | Move or rematch out of order |
| `410` | `not_pending` | Challenge already answered, withdrawn or expired (challenges expire after 2 minutes) |

## WebSocket — `ws/`

### Chat — `ws/chat/<room-slug>/?token=<access_token>`

**Send** (client → server):

```jsonc
// Text message — the consumer calls MessageService.create_text,
// which emits MessageCreated. Handlers broadcast + push unread updates.
{ "type": "text", "content": "Hello!" }
```

Image and voice messages are sent purely via `POST /api/rooms/<slug>/upload/`. That REST call runs through `MessageService.create_media`, which emits `MessageCreated` — the broadcast handler fans it out to the room and the notify handler pushes unread updates. No client-initiated WebSocket frame is required (any that arrive are ignored).

**Receive** (server → all clients in room):

```jsonc
// Chat message (text, image, or voice)
{
  "type": "chat_message",
  "message_type": "text",
  "id": "<uuid>",
  "display_name": "Alice",
  "username": "alice",
  "avatar_url": "/media/avatars/alice.jpg",
  "content": "Hello!",
  "file_url": null,
  "timestamp": "2025-01-01T12:00:00Z"
}

// Presence events
{ "type": "presence_event", "event": "join",  "display_name": "Bob", "username": "bob" }
{ "type": "presence_event", "event": "leave", "display_name": "Bob", "username": "bob" }
```

**Close codes:**

| Code | Meaning |
|---|---|
| `4001` | Authentication failed or token expired |
| `4003` | Not a room member |
| `4004` | Room does not exist |

The client does not attempt reconnection on these codes.

### Notifications — `ws/notifications/?token=<access_token>`

One per signed-in tab. An open notification socket is also what marks you as **online** for games.

**Send** (client → server):

```jsonc
// Heartbeat every 30 s. Without it you drop off the online list after 90 s.
{ "type": "ping" }
```

**Receive:**

```jsonc
// Another member posted in a shared room
{ "type": "unread_update", "room_slug": "<uuid>", "room_name": "engineering" }

// Someone challenged you
{ "type": "game_invite", "game_id": "<uuid>",
  "from_user": { "username": "alice", "display_name": "Alice", "avatar_url": null, "is_bot": false } }

// Your challenge was answered — or a challenge to you was withdrawn
{ "type": "game_invite_update", "game_id": "<uuid>",
  "status": "accepted",            // accepted | declined | cancelled
  "by": { "username": "bob", "display_name": "Bob", "avatar_url": null, "is_bot": false } }

// Quick match paired you with someone
{ "type": "match_found", "game_id": "<uuid>" }
```

### Game — `ws/games/<game-id>/?token=<access_token>`

One socket per player per game. Only the game's two players can connect.

**Send** (client → server):

```jsonc
{ "type": "move", "index": 4 }     // 0–8, left→right, top→bottom
{ "type": "resign" }
{ "type": "here" }                 // answer an opponent's "join" so they know you're present
```

**Receive:**

```jsonc
// Sent on connect and after every move or resignation (same shape as the REST game)
{ "type": "game_state", "game": { /* see Games above */ } }

// Opponent presence: join / leave as they happen, "here" in answer to a join
{ "type": "player_presence", "event": "join", "username": "bob", "display_name": "Bob" }

// A rejected move or resignation — sent only to the player who tried it
{ "type": "error", "error": "It's not your turn.", "code": "not_your_turn" }
```

In bot games the server sends two `game_state` events per turn: your move, then (about 0.45 s later) the bot's reply.

**Close codes** are the same as the chat socket: `4001` auth failed, `4003` not a player in this game, `4004` game does not exist.
