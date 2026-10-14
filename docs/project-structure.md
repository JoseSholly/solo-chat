# Project Structure

Where things live. Django apps own their models, services, consumers and tests; the frontend is plain templates plus one stylesheet and a handful of script files.

```
solo-chat/
├── config/
│   ├── settings/
│   │   ├── base.py           # Shared settings — apps, middleware, auth, JWT, DRF, static/media
│   │   ├── dev.py            # Development — DEBUG=True, SQLite, localhost Redis
│   │   ├── local.py          # Personal machine overrides (gitignored, create it yourself)
│   │   ├── prod.py           # Production — reads everything from environment variables
│   │   └── cloudinary/       # Media storage settings for production
│   ├── urls.py               # Root URL conf + page routes
│   ├── asgi.py               # Dual-protocol ASGI app (HTTP + WebSocket)
│   ├── middleware.py         # ServerTimingMiddleware — Server-Timing header, slow-request log
│   ├── storages.py           # Hashed, compressed static files (one-year cache)
│   └── wsgi.py
│
├── accounts/                 # Auth & user profiles
│   ├── models.py             # Custom User (email login, UUID PK, Argon2)
│   ├── serializers.py        # Signup · Login · Profile · PublicProfile · Forgot/Reset password
│   ├── email.py              # ResendEmailBackend — Django email over Resend's HTTPS API
│   ├── views.py              # Signup · Login · Logout · Profile · PublicProfile · ForgotPassword · ResetPassword
│   ├── tests.py              # Password reset flow + Resend backend
│   └── urls.py               # /api/auth/*
│
├── chat/                     # Rooms, messages, WebSocket
│   ├── models.py             # Room · RoomMembership · Message
│   ├── serializers.py        # Room · Message · DashboardRoom
│   ├── views.py              # CRUD views + invite/join + dashboard + media upload
│   ├── consumers.py          # RoomChatConsumer · NotificationConsumer · ChatConsumer (legacy)
│   ├── routing.py            # WebSocket URL patterns
│   ├── urls.py               # /api/* REST endpoints
│   ├── apps.py               # AppConfig.ready() wires event handlers + signal receivers
│   ├── services/
│   │   ├── __init__.py       # Re-exports RoomService · MessageService · MediaService
│   │   ├── room_service.py
│   │   ├── message_service.py
│   │   └── media_service.py
│   ├── repositories/
│   │   ├── __init__.py
│   │   └── room_dashboard_repository.py   # Complex dashboard aggregate
│   ├── events/
│   │   ├── __init__.py       # Re-exports event_bus and event dataclasses
│   │   ├── bus.py            # EventBus (subscribe / emit)
│   │   ├── events.py         # Frozen dataclass events (primitive IDs only)
│   │   ├── handlers.py       # broadcast_message_to_room · notify_other_members · broadcast_presence
│   │   └── signals.py        # post_save(Message) → advance sender's last_seen
│   └── tests/                # pytest suite — see Getting Started → Running tests
│       ├── conftest.py       # Fixtures + in-memory channel layer override
│       ├── test_consumers.py
│       ├── test_events_bus.py
│       ├── test_events_signals.py
│       ├── test_events_handlers.py
│       ├── test_live_sockets.py  # ping/pong, bad frames, close codes on every socket
│       ├── test_query_counts.py  # hot endpoints don't run more queries as data grows
│       ├── test_repositories.py
│       ├── test_services.py
│       ├── test_storages.py
│       └── test_views.py
│
├── games/                    # Two-player games (Tic-Tac-Toe) and online presence
│   ├── models.py             # UserPresence · Game · MatchQueueEntry
│   ├── logic.py              # Pure Tic-Tac-Toe rules: win lines, whose turn, draws
│   ├── bot.py                # Computer opponent — easy / medium / hard (minimax)
│   ├── services.py           # PresenceService · GameService · MatchmakingService · GameError
│   ├── serializers.py        # game_state() / user_brief() — one payload for REST and WebSocket
│   ├── notify.py             # Pushes to "user_{id}" and "game_{id}" channel groups
│   ├── consumers.py          # GameConsumer — moves, resign, presence, bot turns
│   ├── routing.py            # ws/games/<uuid>/ (included from chat/routing.py)
│   ├── views.py              # Players, overview, challenges, bot games, Quick match
│   ├── urls.py               # /api/games/*
│   ├── admin.py
│   └── tests/                # logic · bot (exhaustive) · services · consumers · views
│
├── templates/
│   ├── accounts/
│   │   ├── signup.html
│   │   ├── login.html
│   │   ├── forgot_password.html
│   │   ├── reset_password.html
│   │   ├── profile.html
│   │   └── email/            # password_reset.txt / .html
│   ├── chat/
│   │   ├── dashboard.html    # Main SPA shell (sidebar + room / games panel)
│   │   ├── join.html         # Invite-link landing page
│   │   └── room.html         # Legacy anonymous chat
│   ├── partials/pwa.html     # Manifest + service-worker registration
│   ├── landing.html
│   └── sw.js                 # Service worker (served at /sw.js)
│
├── static/
│   ├── css/style.css         # Single stylesheet — dark theme, all pages (section 10: games)
│   ├── icons/ · manifest.webmanifest
│   └── js/                   # One file per feature — see Architecture → Frontend architecture
│       ├── socket.js         # LiveSocket — every WebSocket: heartbeat, reconnect, token refresh
│       └── games.js          # Games lobby, board, invites, Quick match
│
├── docs/                     # This documentation
│
├── Dockerfile                # Production image (Daphne, no dev deps)
├── entrypoint.sh             # migrate → collectstatic → daphne on $PORT
├── docker-compose.yml        # Local dev — web + Redis, live-reload via volume mount
├── manage.py
├── pyproject.toml
└── uv.lock
```
