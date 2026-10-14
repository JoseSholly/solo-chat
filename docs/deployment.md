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

The production setup is a Railway server in Amsterdam, a Neon database in Frankfurt, and most users in West Africa. Most of a request's time is network distance, so the work is about saving round trips.

### Measuring

Every response carries a `Server-Timing` header (`config/middleware.py`):

```
Server-Timing: app;dur=19.7, db;dur=5.3;desc="7 queries"
```

Open DevTools → Network, click a request, then **Timing** to see how long the server spent and how much of it was the database. Requests slower than 500 ms are logged as `Slow request: …`, so they show up in Railway's logs. Railway's response-time chart is coarse, so use these for real numbers.

### What's in place

- **Connection pool.** Django's built-in pool (psycopg 3, `OPTIONS["pool"]` in `config/settings/prod.py`) keeps database connections open and reuses them. Without it, every request opened a new TLS connection to Frankfurt: several round trips before the first query. In a local test, 20 requests made 20 new connections without the pool and none with it. Under ASGI, Django recommends a pool rather than `CONN_MAX_AGE`. `CONN_HEALTH_CHECKS` tests a connection before reuse, so one broken while Neon was asleep is replaced, and idle connections close after 5 minutes. Use Neon's **direct** endpoint, not `-pooler`: the app does its own pooling.
- **Few queries per request.** Each query is another round trip. `chat/tests/test_query_counts.py` checks that the dashboard, room, members and games-lobby endpoints run the same number of queries however much data there is (no N+1). The games lobby went from 11 queries to 6.
- **Cached static files.** `config.storages.StaticFilesStorage` gives CSS/JS/icons content-hashed names, and WhiteNoise serves them as `immutable`. After the first visit, browsers load them with no request at all. Broken references inside third-party files are left alone instead of failing `collectstatic`.
- **Service worker** has no `fetch` handler. An empty one only routes every request through the worker.

### Options outside the code

- **Neon cold starts.** On Neon's free plan the database suspends after about 5 idle minutes, and the next request waits for it to wake (hundreds of ms). Paid plans can turn autosuspend off.
- **Database next to the server.** Railway Postgres in the same region would make each query well under a millisecond, instead of a few ms between Amsterdam and Frankfurt, at the cost of a migration.
- **Users far from Amsterdam.** Railway has no region nearer West Africa. Putting Cloudflare (free plan) in front of a custom domain caches static files at an edge close to users. API calls and WebSockets still go to Amsterdam.

