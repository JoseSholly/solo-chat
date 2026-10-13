# Architecture

How requests move through Solo-Chat, where business logic lives, and how real-time updates reach the browser. Endpoint details are in the [API reference](api.md); tables and fields are in [Data models](data-models.md).

## Request flow

```
HTTP (REST):
  Browser ──HTTPS──▶ Daphne (ASGI) ──▶ Django router
                                              │
                               ┌──────────────┤
                               ▼              ▼
                           DRF View       Admin
                               │
                           Service layer (RoomService / MessageService / MediaService)
                               │           │
                               │           └─── event_bus.emit(MessageCreated | RoomCreated | …)
                               │
                          Repository layer (RoomDashboardRepository)  ◀── DashboardView
                               │
                           SQLite (dev) / PostgreSQL (prod)

WebSocket:
  Browser ──WSS──▶ Daphne (ASGI) ──▶ URLRouter
                                          │
                                   RoomChatConsumer
                                    ├── JWT decode (query param)
                                    ├── Membership check (ORM)
                                    ├── group_add("room_{id}")
                                    ├── emit UserJoinedRoom / UserLeftRoom
                                    │
                                    └── receive(text) ──▶ MessageService.create_text()
                                                              │
                                                              └── event_bus.emit(MessageCreated)
                                                                    │
                                                    ┌───────────────┴───────────────┐
                                                    ▼                               ▼
                                        broadcast_message_to_room       notify_other_members
                                                    │                               │
                                                    └── channel_layer.group_send ──▶ Redis pub/sub
                                                                                    │
                                                        ┌───────────────────────────┘
                                                        ▼
                                            "room_{id}"   +   "user_{id}"  groups
```

Games follow the same pattern with their own app (`games/`), service layer and consumer:

```
Game socket:
  Browser ──WSS──▶ GameConsumer  (ws/games/<uuid>/)
                    ├── JWT decode + "is this one of the two players?"
                    ├── group_add("game_{id}")
                    └── receive(move | resign) ──▶ GameService.move / resign   (row locked, rules checked)
                                                        │
                                                        ├── group_send("game_{id}", game_state)  ──▶ both players
                                                        └── vs bot: short pause ──▶ GameService.bot_move ──▶ game_state

Challenges & Quick match (REST):
  POST /api/games/challenges/ ──▶ GameService.challenge ──▶ notify.to_user ──▶ "user_{id}" ──▶ NotificationConsumer ──▶ invite dialog
  POST /api/games/quick-match/ ──▶ MatchmakingService.join ──▶ pairs with a waiting player ──▶ "match_found" to both
```

## WebSocket consumers

| Consumer | Path | Auth | Group |
|---|---|---|---|
| `RoomChatConsumer` | `ws/chat/<uuid:slug>/` | JWT (query param) | `room_{room.id}` |
| `NotificationConsumer` | `ws/notifications/` | JWT (query param) | `user_{user.id}` — also tracks online presence |
| `GameConsumer` | `ws/games/<uuid:game_id>/` | JWT (query param) + must be a player | `game_{game.id}` |
| `ChatConsumer` | `ws/chat/<room_name>/` | None (legacy) | `chat_{room_name}` |

## Service layer

Business logic lives in `chat/services/` and `games/services.py`, not in views or consumers:

```
RoomService        — create / get / get_by_slug / add_member / remove_member / is_member / update_last_seen
MessageService     — get_history(limit=50) / create_text / create_media
MediaService       — validate(file, type)  — MIME type + file size enforcement

PresenceService    — connect / disconnect / heartbeat / is_online / online_users
GameService        — challenge / accept / decline / cancel / move / resign / rematch
                     play_bot / bot_move / stats / stats_for / overview
MatchmakingService — join / leave / is_queued   (Quick match queue)
```

Game rules are pure functions in `games/logic.py` (win lines, whose turn, draws) and the computer opponent is `games/bot.py`; neither touches the database, so both are tested exhaustively without fixtures. Services raise `GameError(message, code, status)`, which the REST views turn into `{ error, code }` responses and the consumer sends back as an `error` event.

Both DRF views and WebSocket consumers call the same service methods, so there is no duplicated logic between the two request paths. Services also **emit domain events** rather than calling into the WebSocket layer directly — see below.

## Repository layer

Repositories live in `chat/repositories/`. They are introduced only when at least one of these holds: the query is complex, multiple services share the same data-access logic, persistence details deserve isolation, or the persistence mechanism is expected to evolve. Simple CRUD stays on the ORM inside the services — the ORM is already an excellent abstraction.

Today there is exactly one:

```
RoomDashboardRepository.get_user_dashboard(user) -> DashboardData
```

It encapsulates the three-subquery aggregate that powers the dashboard (latest message per room, member count, unread count) and returns a `DashboardData` dataclass so the view is just a thin call site.

## Event architecture

`chat/events/` is a lightweight, in-process event system used to decouple side effects (WebSocket broadcasts, notifications, `last_seen` bookkeeping) from the code that triggers them. It's a **hybrid** of two mechanisms:

- **Custom event bus** — services and consumers explicitly emit domain events with rich, primitive-only payloads. Handlers subscribe in `AppConfig.ready()`. Dispatch is synchronous and in-process; handler exceptions are logged and swallowed so one broken handler cannot fail a message write. Payloads carry IDs (not model instances), so a future move to an async broker is a swap of the dispatcher, not the payloads.
- **Django signals** — reserved for guarantees that must fire no matter how a model changes. One receiver today: `post_save(Message)` advances the sender's `RoomMembership.last_seen`, so sending a message can never leave you unread to yourself.

Events currently defined:

| Event | Emitted from | Handlers |
|---|---|---|
| `MessageCreated` | `MessageService.create_text` / `create_media` | `broadcast_message_to_room`, `notify_other_members_of_message` |
| `RoomCreated` | `RoomService.create` | *(none yet — reserved for audit / welcome logic)* |
| `UserJoinedRoom` / `UserLeftRoom` | `RoomChatConsumer.connect` / `disconnect` | `broadcast_presence` |
| `LastSeenUpdated` | `RoomService.update_last_seen` | *(none yet — reserved for read-receipt propagation)* |

Because `MessageService` emits `MessageCreated`, **any** code path that creates a message — WebSocket text, REST media upload, admin, a future scheduled bot — automatically triggers the same broadcast and unread fanout. The consumer no longer owns transport-adjacent logic.

## Online presence and games

"Online" means "has the dashboard open". `NotificationConsumer` already holds one socket per signed-in tab, so it doubles as the presence signal:

- On connect it calls `PresenceService.connect` (increments `UserPresence.connections`), on disconnect `PresenceService.disconnect` (decrements; leaving the last tab also takes you out of the Quick match queue).
- The browser sends `{ "type": "ping" }` every 30 s; a user counts as online only while `connections > 0` **and** `last_seen` is under 90 s old. If a worker dies without running `disconnect`, the stale row stops counting by itself and the next connect resets it.

Game invites, answers and Quick match results are pushed to the same `user_{id}` groups through `games/notify.py`, so a challenge pops up wherever you are on the dashboard — in a room or in the lobby.

Moves go over the per-game socket. `GameService.move` takes the game row with `select_for_update()` inside a transaction, so two moves can't land at once, and whose turn it is is derived from the board itself (X always moves first), so there is no separate turn field to drift out of sync. In bot games the human move and the bot's reply are two separate saves; the consumer broadcasts the first, waits briefly so the bot reads as an opponent, then plays and broadcasts the second. If the socket drops between the two, the bot plays its turn as soon as the player reconnects.

Quick match pairs two waiting players by deleting the other player's queue row: `DELETE` returns the row count, so if two requests race for the same opponent only one of them deletes it and gets the match. That works the same on SQLite and PostgreSQL. More detail is in [Games](games.md).

## Unread count design

`RoomMembership.last_seen` is updated to `timezone.now()` in two places: when a user opens a room (`GET /api/rooms/<slug>/` → `RoomService.update_last_seen`), and automatically for the sender of every new message via the `post_save(Message)` signal receiver.

The dashboard endpoint delegates to `RoomDashboardRepository.get_user_dashboard(user)`, which resolves memberships, latest-message-per-room, member counts, and unread counts in **three queries total** (a subquery-annotated room fetch, a batched last-message fetch, and a subquery-based unread aggregation) — not N+1.

When a member sends a message, the `MessageCreated` event fans out to two handlers: one broadcasts the message to the room group, the other pushes an `unread_update` to every other member's `user_{id}` channel group. The `NotificationConsumer` relays those to browsers, which increment the sidebar badge — no polling required.

## Frontend architecture

`dashboard.html` is the only full page load after login. Selecting a room — or opening Games — swaps the right-panel content via `innerHTML` and updates the browser URL with `history.pushState` (`?room=<slug>`, `?games`, `?game=<id>`) — single-page behavior without a framework. Exactly one panel lives in the stage at a time (`_activePanel` in `room.js`); each panel class has a `destroy()` that closes its socket and timers before the next one renders.

Each feature has its own JS file, loaded in dependency order via plain `<script>` tags:

```
api.js          — apiFetch() wrapper; intercepts 401, silently refreshes token, retries
auth.js         — authSignup / authLogin / authLogout
auth-guard.js   — Redirects unauthenticated users to /login/ on page load
ui.js           — Shared UI primitives: icons, avatars, time formatting, modals/drawers, menus
dashboard.js    — Sidebar, room list, notification socket (+ presence heartbeat), new-room modal, URL routing
messages.js     — MessageList: timeline rendering, grouping, media, voice playback
composer.js     — Composer: text input, uploads with progress, voice recording
room.js         — RoomPanel class — owns the room WebSocket, presence, details drawer
games.js        — Games lobby, Tic-Tac-Toe board (GameBoard owns the game WebSocket), invites, Quick match
profile.js      — Profile view / edit / avatar upload
```

`apiFetch()` intercepts every `401`, calls `/api/auth/token/refresh/`, updates `localStorage`, and retries the original request exactly once. On logout the refresh token is blacklisted server-side.

## Key design decisions

**Custom User model upfront** — Defined before the first migration using `AbstractBaseUser` with `email` as `USERNAME_FIELD` and UUID as the primary key. Changing the User model after migrations exist requires squashing; doing it first costs nothing.

**Slug-based invite tokens** — Each room has a `slug` UUID field that is separate from its `id`. The slug is what appears in share links. It can be regenerated to invalidate outstanding invites without touching the room's primary key or any foreign keys.

**JWT passed as a WebSocket query parameter** — The WebSocket protocol does not support custom headers from browsers. Passing `?token=<access_token>` in the connection URL is the standard workaround. The token is short-lived (1 day) to limit exposure.

**Argon2 as the primary password hasher** — Django ships Argon2 support but does not enable it by default. It is explicitly set as the first entry in `PASSWORD_HASHERS` for better brute-force resistance on commodity hardware.

**Games reuse the chat infrastructure** — Presence rides on the notification socket every dashboard tab already opens, invites travel through the existing `user_{id}` groups, and the game socket copies the chat consumer's JWT and close-code conventions. The only new moving part is one consumer per game.

**The bot runs on the server** — Bot games use the same `Game` rows, rules and board UI as games between people, results are stored the same way, and a client can't fake a bot result. They are recorded but kept out of the head-to-head record, which counts games against people only.
