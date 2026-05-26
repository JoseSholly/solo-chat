#!/bin/sh
set -e

echo "==> Applying database migrations..."
python manage.py migrate --noinput

echo "==> Collecting static files..."
python manage.py collectstatic --noinput

echo "==> Starting Daphne on port ${PORT:-8000}..."
exec daphne \
    -b 0.0.0.0 \
    -p "${PORT:-8000}" \
    config.asgi:application
