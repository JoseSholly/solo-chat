# ChatRooms

> Real-time group chat with invite links, voice notes, and live presence — built on Django Channels and JWT auth, no frontend framework.

![Python](https://img.shields.io/badge/Python-3.11+-3776AB?style=flat&logo=python&logoColor=white)
![Django](https://img.shields.io/badge/Django-5.2-092E20?style=flat&logo=django&logoColor=white)
![Django Channels](https://img.shields.io/badge/Channels-4.3-red?style=flat)
![Redis](https://img.shields.io/badge/Redis-channel%20layer-DC382D?style=flat&logo=redis&logoColor=white)
![License](https://img.shields.io/badge/license-MIT-green?style=flat)

---

## What it does

ChatRooms lets users create private rooms, share invite links, and chat in real time — with text, images, and voice notes. It was built to demonstrate a complete full-stack WebSocket architecture without hiding behind a frontend framework or a hosted real-time service.

**Think Slack meets WhatsApp:** named rooms, one-click invite links, unread badges, and presence indicators — all from a single Django codebase with ~2 000 lines of vanilla JS.

---

## Features

| Feature | Details |
|---|---|
| **JWT Authentication** | Signup, login, logout. Access token (1 day) + rotating refresh token (7 days) + server-side blacklist on logout |
| **User Profiles** | Display name, @username, bio, avatar upload (served from `/media/`) |
| **Room Creation** | Any authenticated user can create a named room with an optional description |
| **Invite Links** | Each room has a `slug` UUID (separate from its `id`) embedded in shareable `/join/<slug>/` URLs |
| **Membership** | Rooms are private — join via invite only; creator cannot leave their own room |
| **Real-time Chat** | WebSocket connection per room via Django Channels + Redis channel layer |
| **Media Messages** | Upload images (≤ 10 MB) or voice notes (≤ 25 MB); MIME-validated before storage |
| **Presence Tracking** | `join` / `leave` system messages when members connect or disconnect |
| **Unread Counts** | Per-room unread badge on the dashboard, driven by `RoomMembership.last_seen` |
| **Live Badge Updates** | A per-user notification WebSocket pushes badge increments without polling |
| **Dark UI** | Single CSS file, Inter font, indigo accent — no frameworks, no bundlers |

---

## Tech Stack

| Layer | Technology | Why |
|---|---|---|
| Language | Python 3.11 | |
| Web framework | Django 5.2 | Batteries-included ORM, admin, auth primitives |
| REST API | Django REST Framework 3.17 | Serializers, generic views, JWT integration |
| Real-time | Django Channels 4.3 + Daphne (ASGI) | WebSocket protocol on top of Django's ASGI stack |
| Channel layer | Redis via `channels-redis` | Fan-out to all consumers in a group without shared memory |
| Auth | `djangorestframework-simplejwt` | Stateless JWT with built-in token blacklist |
| Password hashing | Argon2 (primary) | Designed for resistance to GPU brute-force |
| Image processing | Pillow | Avatar storage and image MIME validation |
| Static files (prod) | WhiteNoise | Serves compressed static files directly from Daphne — no separate CDN needed |
| Database driver (prod) | psycopg2-binary | PostgreSQL adapter |
| Database URL parsing | dj-database-url | Parses `DATABASE_URL` into Django's `DATABASES` dict |
| Admin | Jazzmin | Enhanced Django admin UI |
| Database | SQLite (dev) / PostgreSQL (prod) | Zero-config locally; UUID PK + concurrent writes in production |
| Package manager | `uv` | Fast resolver; reproducible installs via `uv.lock` |
| Container | Docker + Compose | Consistent local environment; single image for production |
| Frontend | Vanilla HTML + CSS + JS | No framework, no bundler, no transpiler |

---

## Architecture

### Request flow

```
HTTP (REST):
  Browser ──HTTPS──▶ Daphne (ASGI) ──▶ Django router
                                              │
                               ┌──────────────┤
                               ▼              ▼
                           DRF View       Admin
                               │
                           Service layer (RoomService / MessageService / MediaService)
                               │
                           SQLite (dev) / PostgreSQL (prod)

WebSocket:
  Browser ──WSS──▶ Daphne (ASGI) ──▶ URLRouter
                                          │
                                   RoomChatConsumer
                                    ├── JWT decode (query param)
                                    ├── Membership check (ORM)
                                    ├── group_add("room_{id}")
                                    │
                                    ├── receive(text) ──▶ MessageService.create_text()
                                    │                         │
                                    └── channel_layer.group_send ──▶ Redis pub/sub
                                                                           │
                                                    ┌──────────────────────┘
                                                    ▼
                                         All consumers in "room_{id}" group
                                         + "user_{id}" groups for unread badges
```

### ASGI protocol routing

```python
# config/asgi.py  (simplified)
ProtocolTypeRouter({
    "http":      get_asgi_application(),
    "websocket": AllowedHostsOriginValidator(
                     URLRouter(websocket_urlpatterns)
                 ),
})
```

### WebSocket consumers

| Consumer | Path | Auth | Group |
|---|---|---|---|
| `RoomChatConsumer` | `ws/chat/<uuid:slug>/` | JWT (query param) | `room_{room.id}` |
| `NotificationConsumer` | `ws/notifications/` | JWT (query param) | `user_{user.id}` |
| `ChatConsumer` | `ws/chat/<room_name>/` | None (legacy) | `chat_{room_name}` |

### Service layer

Business logic lives in `chat/services/`, not in views or consumers:

```
RoomService      — create / get / get_by_slug / add_member / remove_member / is_member / update_last_seen
MessageService   — get_history(limit=50) / create_text / create_media
MediaService     — validate(file, type)  — MIME type + file size enforcement
```

Both DRF views and WebSocket consumers call the same service methods, so there is no duplicated logic between the two request paths.

### Unread count design

`RoomMembership.last_seen` is updated to `timezone.now()` every time a user opens a room (`GET /api/rooms/<slug>/`). The dashboard serializer computes:

```python
unread_count = messages.filter(timestamp__gt=membership.last_seen).count()
```

A pre-built `membership_map` is passed through serializer context, so the dashboard endpoint resolves all rooms with **one query per user**, not N+1.

When a member sends a message, `RoomChatConsumer` fans out an `unread_update` event to every other member's `user_{id}` channel group. The `NotificationConsumer` relays it to their browser, which increments the sidebar badge — no polling required.

### Frontend architecture

`dashboard.html` is the only full page load after login. Selecting a room swaps the right-panel content via `innerHTML` and updates the browser URL with `history.pushState` — single-page behavior without a framework.

Each feature has its own JS file, loaded in dependency order via plain `<script>` tags:

```
api.js          — apiFetch() wrapper; intercepts 401, silently refreshes token, retries
auth.js         — authSignup / authLogin / authLogout
auth-guard.js   — Redirects unauthenticated users to /login/ on page load
dashboard.js    — Sidebar, room list, new-room modal
room.js         — RoomPanel class — owns the WebSocket, message rendering, input bar
profile.js      — Profile view / edit / avatar upload
```

`apiFetch()` intercepts every `401`, calls `/api/auth/token/refresh/`, updates `localStorage`, and retries the original request exactly once. On logout the refresh token is blacklisted server-side.

---

## Data Models

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
  timestamp
```

---

## Project Structure

```
solo-chat/
├── config/
│   ├── settings/
│   │   ├── base.py           # Shared settings — apps, middleware, auth, JWT, DRF, static/media
│   │   ├── dev.py            # Development — DEBUG=True, SQLite, localhost Redis
│   │   ├── local.py          # Personal machine overrides (gitignored)
│   │   └── prod.py           # Production — reads everything from environment variables
│   ├── urls.py               # Root URL conf + page routes
│   ├── asgi.py               # Dual-protocol ASGI app (HTTP + WebSocket)
│   └── wsgi.py
│
├── accounts/                 # Auth & user profiles
│   ├── models.py             # Custom User (email login, UUID PK, Argon2)
│   ├── serializers.py        # Signup · Login · Profile · PublicProfile
│   ├── views.py              # SignupView · LoginView · LogoutView · ProfileView · UserPublicProfileView
│   └── urls.py               # /api/auth/*
│
├── chat/                     # Rooms, messages, WebSocket
│   ├── models.py             # Room · RoomMembership · Message
│   ├── serializers.py        # Room · Message · DashboardRoom
│   ├── views.py              # CRUD views + invite/join + dashboard + media upload
│   ├── consumers.py          # RoomChatConsumer · NotificationConsumer · ChatConsumer (legacy)
│   ├── routing.py            # WebSocket URL patterns
│   ├── urls.py               # /api/* REST endpoints
│   └── services/
│       ├── __init__.py       # Re-exports RoomService · MessageService · MediaService
│       ├── room_service.py
│       ├── message_service.py
│       └── media_service.py
│
├── templates/
│   ├── accounts/
│   │   ├── signup.html
│   │   ├── login.html
│   │   └── profile.html
│   └── chat/
│       ├── dashboard.html    # Main SPA shell (sidebar + room panel)
│       ├── join.html         # Invite-link landing page
│       └── room.html         # Legacy anonymous chat
│
├── static/
│   ├── css/style.css         # Single stylesheet — dark theme, all pages
│   └── js/                   # Six feature JS files — see Frontend section
│
├── Dockerfile                # Production image (Daphne, no dev deps)
├── entrypoint.sh             # migrate → collectstatic → daphne on $PORT
├── docker-compose.yml        # Local dev — web + Redis, live-reload via volume mount
├── manage.py
├── pyproject.toml
└── uv.lock
```

---

## Getting Started

Two paths: Docker Compose (no local Python or Redis setup required) or manual.

---

### Option A — Docker Compose (recommended)

**Prerequisites:** Docker Desktop

```bash
git clone https://github.com/josesholly/solo-chat.git
cd solo-chat
docker compose up --build
```

That's it. Compose starts the Django dev server and a Redis container, mounts the source directory so code changes reload without rebuilding, and binds to `http://localhost:8000`.

To create a superuser inside the running container:

```bash
docker compose exec web python manage.py createsuperuser
```

---

### Option B — Manual

**Prerequisites:** Python 3.11+, Redis on `localhost:6379`, [`uv`](https://github.com/astral-sh/uv)

#### 1. Clone and install

```bash
git clone https://github.com/josesholly/solo-chat.git
cd solo-chat
uv sync
```

#### 2. Start Redis

```bash
# macOS / Linux
redis-server

# Windows
docker run -d -p 6379:6379 redis:alpine
```

#### 3. Apply migrations

```bash
python manage.py migrate
```

#### 4. (Optional) Create a superuser

```bash
python manage.py createsuperuser
```

#### 5. Run the server

```bash
python manage.py runserver
```

Daphne (ASGI) handles both HTTP and WebSocket. Visit `http://localhost:8000`.

---

### Settings environments

| Module | Used when |
|---|---|
| `config.settings.dev` | Default for `manage.py` and Docker Compose |
| `config.settings.local` | Personal overrides — copy from `dev`, gitignored |
| `config.settings.prod` | Production — all values read from environment variables |

To use local overrides, create `config/settings/local.py` (a template with commented examples is already there) and set:

```bash
export DJANGO_SETTINGS_MODULE=config.settings.local
```

---

## Typical First-Run Flow

1. Open `/signup/` and create an account — you land on `/dashboard/`
2. Click **New Room**, give it a name, and create it
3. Inside the room, click **Copy Invite Link**
4. Open that link in a second browser (or private window), sign in as a different user
5. The second user sees the join confirmation and enters the room
6. Both sessions are now live — messages and presence events appear in real time

---

## Page Routes

| URL | Page |
|---|---|
| `/` | Landing page |
| `/signup/` | Create an account |
| `/login/` | Log in |
| `/dashboard/` | Your rooms — select or create |
| `/profile/` | Edit display name, bio, and avatar |
| `/join/<slug>/` | Accept a room invite |
| `/admin/` | Django admin (Jazzmin) |

---

## API Reference

All authenticated endpoints require:

```
Authorization: Bearer <access_token>
```

### Auth — `/api/auth/`

| Method | Endpoint | Auth | Description |
|---|---|---|---|
| `POST` | `signup/` | — | Register; returns `{ access, refresh, user }` |
| `POST` | `login/` | — | Authenticate; returns `{ access, refresh, user }` |
| `POST` | `logout/` | ✓ | Blacklist the refresh token |
| `GET` | `me/` | ✓ | Current user profile |
| `PATCH` | `me/` | ✓ | Update display name, bio, or avatar (multipart) |
| `POST` | `token/refresh/` | — | Exchange refresh token for new access + refresh |
| `GET` | `users/<username>/` | ✓ | Public profile of another user |

### Rooms — `/api/`

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

### WebSocket — `ws/`

#### Chat — `ws/chat/<room-slug>/?token=<access_token>`

**Send** (client → server):

```jsonc
// Text message
{ "type": "text", "content": "Hello!" }

// Pre-uploaded media (after POST /api/rooms/<slug>/upload/)
{ "type": "image", "file_url": "/media/uploads/...", "timestamp": "..." }
{ "type": "voice", "file_url": "/media/uploads/...", "timestamp": "..." }
```

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

#### Notifications — `ws/notifications/?token=<access_token>`

Receive-only. Emits `unread_update` events when another member posts in a shared room:

```jsonc
{ "type": "unread_update", "room_slug": "<uuid>", "room_name": "engineering" }
```

---

## Key Design Decisions

**Custom User model upfront** — Defined before the first migration using `AbstractBaseUser` with `email` as `USERNAME_FIELD` and UUID as the primary key. Changing the User model after migrations exist requires squashing; doing it first costs nothing.

**Slug-based invite tokens** — Each room has a `slug` UUID field that is separate from its `id`. The slug is what appears in share links. It can be regenerated to invalidate outstanding invites without touching the room's primary key or any foreign keys.

**JWT passed as a WebSocket query parameter** — The WebSocket protocol does not support custom headers from browsers. Passing `?token=<access_token>` in the connection URL is the standard workaround. The token is short-lived (1 day) to limit exposure.

**Dual consumers for backward compatibility** — The original `ChatConsumer` (anonymous, room-name-based) is kept alongside the new `RoomChatConsumer` (JWT-authenticated, slug-based). Legacy `/chat/<room_name>/` pages continue to work without migration.

**Service layer between views and consumers** — `RoomService`, `MessageService`, and `MediaService` contain all business logic. Both DRF views and WebSocket consumers call into these services, so there is no logic duplication between the two request paths.

**N+1 prevention on the dashboard** — `DashboardRoomSerializer` receives a pre-built `{room_id: membership}` map in its context. All rooms are resolved with a single membership query instead of one per room.

**Argon2 as the primary password hasher** — Django ships Argon2 support but does not enable it by default. It is explicitly set as the first entry in `PASSWORD_HASHERS` for better brute-force resistance on commodity hardware.

---

## Production

### What the Docker image does

`entrypoint.sh` runs on every container start in this order:

1. `python manage.py migrate --noinput` — applies any pending migrations
2. `python manage.py collectstatic --noinput` — writes compressed static files to `staticfiles/`
3. `daphne -b 0.0.0.0 -p $PORT config.asgi:application` — starts the ASGI server

WhiteNoise serves `staticfiles/` directly from Daphne, so no separate static file server or CDN is required.

### Required environment variables

Set these wherever you deploy:

| Variable | Example | Notes |
|---|---|---|
| `SECRET_KEY` | *(generated)* | `python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"` |
| `ALLOWED_HOSTS` | `your-domain.com` | Comma-separated, no spaces |
| `CSRF_TRUSTED_ORIGINS` | `https://your-domain.com` | Comma-separated HTTPS origins |
| `DATABASE_URL` | `postgres://user:pass@host/db` | Standard PostgreSQL connection string |
| `REDIS_URL` | `redis://host:6379` | Used for the Channels layer |
| `DJANGO_SETTINGS_MODULE` | `config.settings.prod` | Must be set explicitly in production |

### Remaining production considerations

- [ ] Configure object storage (S3 or equivalent) for user-uploaded media — `MEDIA_ROOT` on the local filesystem is not persistent across container restarts
- [ ] Reduce `ACCESS_TOKEN_LIFETIME` to 15–30 minutes (currently 1 day)
- [ ] Set up log aggregation — Daphne writes to stdout, which container runtimes capture by default

---

## License

MIT