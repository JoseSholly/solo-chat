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

## Notes for games

- Games need nothing extra: they use the same Redis channel layer (`REDIS_URL`) as chat, and their tables are created by the `migrate` step above.
- Online presence counts open notification sockets. When a worker is killed without closing its sockets, its users simply drop off the online list 90 seconds after their last heartbeat, and are counted correctly again on their next connection.

