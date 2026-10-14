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

