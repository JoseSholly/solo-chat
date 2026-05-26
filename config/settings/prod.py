import os

import dj_database_url

from .base import *

SECRET_KEY = os.environ["SECRET_KEY"]

DEBUG = False

ALLOWED_HOSTS = os.environ.get("ALLOWED_HOSTS", "").split(",")

# Railway terminates SSL at the proxy — trust the forwarded header instead of
# redirecting internally (SECURE_SSL_REDIRECT=True would cause an infinite loop).
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SECURE_SSL_REDIRECT = False  # handled by Railway's ingress
SECURE_HSTS_SECONDS = 31536000
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True

# W008 is silenced because SSL redirect is intentionally delegated to Railway.
SILENCED_SYSTEM_CHECKS = ["security.W008"]

CSRF_TRUSTED_ORIGINS = os.environ.get("CSRF_TRUSTED_ORIGINS", "").split(",")

# ─── Database ────────────────────────────────────────────────────────────────
# Railway injects DATABASE_URL automatically when a Postgres service is linked.
DATABASES = {
    "default": dj_database_url.config(
        conn_max_age=600,
        conn_health_checks=True,
    )
}

# ─── Channel layer ───────────────────────────────────────────────────────────
# Railway injects REDIS_URL automatically when a Redis service is linked.
CHANNEL_LAYERS = {
    "default": {
        "BACKEND": "channels_redis.core.RedisChannelLayer",
        "CONFIG": {
            "hosts": [os.environ["REDIS_URL"]],
        },
    }
}

# ─── Static files ────────────────────────────────────────────────────────────
STATIC_ROOT = BASE_DIR / "staticfiles"

# Insert WhiteNoise right after SecurityMiddleware so it serves static files
# before any auth or session processing.
MIDDLEWARE.insert(1, "whitenoise.middleware.WhiteNoiseMiddleware")

STORAGES = {
    "staticfiles": {
        "BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage",
    },
}
