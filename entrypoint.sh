#!/bin/sh
set -e

echo "==> Applying database migrations..."
python manage.py migrate --noinput

echo "==> Collecting static files..."
python manage.py collectstatic --noinput

echo "==> Starting Daphne on port ${PORT:-8000}..."
# WebSocket keepalive: Daphne pings a quiet connection every 15 s (and drops
# it after 30 s without a pong), and there's no 24 h cap on how long a
# connection may stay open. The browser has its own heartbeat on top
# (static/js/socket.js), so lines stay busy and dead ones are spotted fast.
exec daphne \
    -b 0.0.0.0 \
    -p "${PORT:-8000}" \
    --ping-interval 15 \
    --ping-timeout 30 \
    --websocket_timeout -1 \
    config.asgi:application
