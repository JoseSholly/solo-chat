# Deployment

Running Solo-Chat in production with the Docker image. For local setup see [Getting started](getting-started.md).

## What the Docker image does

`entrypoint.sh` runs on every container start in this order:

1. `python manage.py migrate --noinput` — applies any pending migrations
2. `python manage.py collectstatic --noinput` — writes compressed static files to `staticfiles/`
3. `daphne -b 0.0.0.0 -p $PORT config.asgi:application` — starts the ASGI server

WhiteNoise serves `staticfiles/` directly from Daphne, so no separate static file server or CDN is required.

## Required environment variables

Set these wherever you deploy:

| Variable | Example | Notes |
|---|---|---|
| `SECRET_KEY` | *(generated)* | `python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"` |
| `ALLOWED_HOSTS` | `your-domain.com` | Comma-separated, no spaces |
| `CSRF_TRUSTED_ORIGINS` | `https://your-domain.com` | Comma-separated HTTPS origins |
| `DATABASE_URL` | `postgres://user:pass@host/db` | Standard PostgreSQL connection string |
| `REDIS_URL` | `redis://host:6379` | Used for the Channels layer |
| `DJANGO_SETTINGS_MODULE` | `config.settings.prod` | Must be set explicitly in production |
| `RESEND_API_KEY` | `re_…` | Sends password-reset emails through [Resend](https://resend.com). Without it, emails are written to the logs instead of sent |
| `DEFAULT_FROM_EMAIL` | `Solo-Chat <no-reply@your-domain.com>` | Sender address. Defaults to Resend's shared `onboarding@resend.dev` (see below) |
| `SITE_URL` | `https://your-domain.com` | Optional. Origin used in emailed links; if unset it's taken from the request |

### Email (password reset)

Password-reset emails go through Resend's HTTPS API (`accounts/email.py`), not SMTP: Railway blocks outgoing SMTP on its Free and Hobby plans.

1. Create an API key in Resend and set `RESEND_API_KEY`.
2. With the default sender `onboarding@resend.dev`, Resend only delivers to **your own Resend account address** — fine for trying it out.
3. To email any user, verify a domain you own in Resend (it gives you DNS records to add), then set `DEFAULT_FROM_EMAIL` to an address on that domain.

## Notes for games

- Games need nothing extra: they use the same Redis channel layer (`REDIS_URL`) as chat, and their tables are created by the `migrate` step above.
- Online presence counts open notification sockets. When a worker is killed without closing its sockets, its users simply drop off the online list 90 seconds after their last heartbeat, and are counted correctly again on their next connection.

## Performance

The production setup is a Railway server in **Amsterdam**, a Neon database in **AWS us-east-1 (N. Virginia)**, and most users in West Africa. Most of a request's time is round trips: browser ↔ server (~100+ ms from Lagos) and server ↔ database (~90–100 ms between Amsterdam and Virginia, *per query*).

### Measuring

Every response carries a `Server-Timing` header (`config/middleware.py`):

```
Server-Timing: app;dur=292.1, db;dur=276.7;desc="3 queries"
```

Open DevTools → Network, click a request, then **Timing** to see how long the server spent and how much of it was the database. Requests slower than 500 ms are logged as `Slow request: …`, so they show up in Railway's logs. If `app` is much bigger than `db`, round trips are happening outside the queries (connection setup, health checks, BEGIN/COMMIT).

To measure the database round trip itself, run this **inside the deployed service** (a shell in the running container), not on your laptop:

```bash
python manage.py dbping
# Round trip per query: median 91.5 ms ...  Far: likely another continent.
```

### Where the database should be

Every query costs one server ↔ database round trip, so the database's region decides the floor for every request. Measured with the real endpoints and a simulated database latency:

| Endpoint | Before | Fewer round trips (DB in Virginia) | + DB next to the server |
|---|---|---|---|
| `GET /api/dashboard/` | 475 ms | 108 ms | 27 ms |
| `GET /api/rooms/<slug>/` | 751 ms | 292 ms | 54 ms |
| `GET /api/rooms/<slug>/members/` | 564 ms | 197 ms | 41 ms |
| `GET /api/games/me/` | 757 ms | 299 ms | 59 ms |
| `GET /api/games/players/` | 289 ms | 101 ms | 23 ms |
| `POST /api/games/quick-match/` | 1029 ms | 292 ms | 49 ms |
| `DELETE /api/games/quick-match/` | 467 ms | 103 ms | 21 ms |
| `POST /api/games/bot/` | 563 ms | 195 ms | 36 ms |

**Move the database to Europe.** Neon can't change a project's region, so create a new one and copy the data:

1. In Neon, create a new project in **AWS Europe (Frankfurt) — eu-central-1**, the closest Neon region to Railway's Amsterdam (about 10 ms).
2. Schedule a few minutes when nobody is using the app (writes made during the copy would be lost).
3. Copy everything with the PostgreSQL 16+ client tools, using each project's **direct** connection string (not `-pooler`):
   ```bash
   pg_dump --format=custom --no-owner --no-acl "$OLD_DATABASE_URL" > solochat.dump
   pg_restore --no-owner --no-acl --dbname "$NEW_DATABASE_URL" solochat.dump
   ```
   (Neon's console also has an import tool that does the same.)
4. In Railway, set `DATABASE_URL` to the new project's direct connection string and redeploy. `migrate` runs on start and should report nothing to apply.
5. Run `python manage.py dbping` in the service: it should report about 10 ms and "Close". Log in and check rooms, messages and game records.
6. Keep the old project for a few days, then delete it.

Everyone stays signed in: user accounts and the token blacklist are copied with the rest of the database, and the JWT signing key (`SECRET_KEY`) doesn't change.

### What's in place

- **Connection pool** (`OPTIONS["pool"]` in `config/settings/prod.py`, psycopg 3). A request borrows an open connection instead of connecting (TCP + TLS + auth, several round trips). Under ASGI, Django recommends a pool rather than `CONN_MAX_AGE`. Use Neon's **direct** endpoint, not `-pooler`: the app does its own pooling.
  - `CONN_HEALTH_CHECKS` is **off**: with a pool it pings every connection before every request, a full extra round trip on every call (it was costing ~100 ms each).
  - Instead `min_size: 0` and `max_idle: 120` close idle connections within a few minutes, before Neon suspends its compute (~5 min) and would break them.
- **Cached signed-in user** (`accounts/authentication.py`). Every API request used to look the user up in the database. It's now cached for up to 60 s and cleared the moment the user changes: `save()`/`delete()` (signals in `accounts/signals.py`), bulk `update()`/`bulk_update()` (`UserQuerySet`), and group or permission changes. In production the cache is Redis, shared by all server processes, so a change in one is seen by all; if Redis is unavailable, requests fall back to the database. Tests in `accounts/tests.py` cover each path.
- **Fewer queries per request.** Room pages fetch the room, the membership, the member count and the creator in one query (`RoomService.get_with_membership`). The dashboard computes unread counts inside the rooms query. The games lobby gets all its games in one query, and "am I queued / who's online" in another. Player records are one `UNION ALL` instead of two queries. `chat/tests/test_query_counts.py` holds each endpoint to its query budget and checks counts don't grow with data.
- **No hidden round trips on the queue.** Django wraps `QuerySet.delete()` and `bulk_create()` in `BEGIN`/`COMMIT` even for one row, so joining and leaving the Quick match queue are single plain SQL statements.
- **Cached static files.** `config.storages.StaticFilesStorage` gives CSS/JS/icons content-hashed names, and WhiteNoise serves them as `immutable`, so after the first visit browsers load them with no request.
- **Service worker** has no `fetch` handler. An empty one only routes every request through the worker.

### Options outside the code

- **Neon cold starts.** On Neon's free plan the database suspends after about 5 idle minutes, and the next request waits for it to wake (the occasional 1–1.5 s request in the logs). Paid plans can turn autosuspend off.
- **Users far from Amsterdam.** Railway has no region nearer West Africa. Putting Cloudflare (free plan) in front of a custom domain caches static files at an edge close to users. API calls and WebSockets still go to Amsterdam.
