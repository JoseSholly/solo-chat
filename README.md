# ChatRooms

> Real-time group chat with invite links, voice notes, live presence, and two-player games — built on Django Channels and JWT auth, no frontend framework.

---

## What it does

ChatRooms lets users create private rooms, share invite links, and chat in real time — with text, images, and voice notes. Between conversations they can play Tic-Tac-Toe against anyone who's online, or against the computer when nobody is around. It was built to demonstrate a complete full-stack WebSocket architecture without hiding behind a frontend framework or a hosted real-time service.

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
| **Presence Tracking** | Live "who's here" in every room: `join` / `leave` events, plus a `here` roll call so newcomers see who was already connected |
| **Unread Counts** | Per-room unread badge on the dashboard, driven by `RoomMembership.last_seen` |
| **Live Badge Updates** | A per-user notification WebSocket pushes badge increments without polling |
| **Games — Tic-Tac-Toe** | Challenge anyone online, search by username, or use **Quick match**; moves are validated server-side and pushed live over a per-game WebSocket. Win/loss/draw record on profiles. [More →](docs/games.md) |
| **Play vs Bot** | Easy, Medium or unbeatable Hard (minimax) computer opponent, offered automatically when nobody else is online |
| **Dark UI** | One token-based stylesheet (Instrument Sans + IBM Plex Mono, single accent), vanilla JS components, in-browser voice recording, real upload progress — no frameworks, no bundlers |

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

## Quick start

```bash
git clone https://github.com/josesholly/solo-chat.git
cd solo-chat
docker compose up --build          # web + Redis on http://localhost:8000
```

Or without Docker (Python 3.11+, Redis on `localhost:6379`, [`uv`](https://github.com/astral-sh/uv)):

```bash
uv sync
uv run python manage.py migrate
uv run python manage.py runserver
```

Run the tests (no Redis needed):

```bash
uv run python -m pytest
```

Full setup, settings modules and test commands: [docs/getting-started.md](docs/getting-started.md).

---

## Documentation

| Page | What's in it |
|---|---|
| [Getting started](docs/getting-started.md) | Local setup (Docker or manual), settings, tests, linting |
| [Games](docs/games.md) | Matchmaking, the bot, rules, records, the board, adding another game |
| [Architecture](docs/architecture.md) | Request flow, consumers, services, events, presence, frontend, design decisions |
| [Data models](docs/data-models.md) | Users, rooms, messages, games |
| [API reference](docs/api.md) | Page routes, REST endpoints, WebSocket messages |
| [Project structure](docs/project-structure.md) | What lives where |
| [Deployment](docs/deployment.md) | Production Docker image and environment variables |

---

## License

MIT