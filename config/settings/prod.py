import os

from dotenv import load_dotenv
from urllib.parse import urlparse, parse_qsl
from .base import *

load_dotenv()
SECRET_KEY = os.environ["SECRET_KEY"]

DEBUG = False

ALLOWED_HOSTS = [h for h in os.environ.get("ALLOWED_HOSTS", "").split(",") if h]

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

CSRF_TRUSTED_ORIGINS = [
    o for o in os.environ.get("CSRF_TRUSTED_ORIGINS", "").split(",") if o
]

# ─── Database ────────────────────────────────────────────────────────────────
load_dotenv()

tmpPostgres = urlparse(os.getenv("DATABASE_URL"))

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": tmpPostgres.path.replace("/", ""),
        "USER": tmpPostgres.username,
        "PASSWORD": tmpPostgres.password,
        "HOST": tmpPostgres.hostname,
        "PORT": 5432,
        "OPTIONS": {
            **dict(parse_qsl(tmpPostgres.query)),  # sslmode etc. from DATABASE_URL
            # Reuse connections instead of opening a new one per request. A new
            # connection costs several round trips (TCP, TLS, auth) before the
            # first query, and every round trip to the database is expensive
            # when it's in another region. Under ASGI, Django recommends a pool
            # over persistent connections (CONN_MAX_AGE).
            "pool": {
                # No connections are kept forever: after a couple of idle minutes
                # they're closed, before Neon suspends its compute (~5 min) and
                # drops them. A connection broken that way would otherwise fail
                # the first request that picked it up.
                "min_size": 0,
                "max_size": 10,
                "timeout": 10,  # seconds to wait for a free connection
                "max_idle": 120,  # one idle connection is closed per period
            },
        },
        # Deliberately off. With a pool, this would test every connection before
        # each request, an extra round trip (~100 ms to a far-away database)
        # on every single request. The short idle time above covers what it
        # was for.
        "CONN_HEALTH_CHECKS": False,
    }
}

# ─── Cache ───────────────────────────────────────────────────────────────────
# Shared by every server process, so clearing a cached user (accounts/
# authentication.py) or a rate-limit counter in one is seen by all. Redis sits
# next to the server on Railway's private network: about a millisecond, against
# ~100 ms for a query to a database in another region.
CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.redis.RedisCache",
        "LOCATION": os.environ["REDIS_URL"],
        "KEY_PREFIX": "solochat",
    }
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
MIDDLEWARE.insert(
    MIDDLEWARE.index("django.middleware.security.SecurityMiddleware") + 1,
    "whitenoise.middleware.WhiteNoiseMiddleware",
)

STORAGES = {
    "default": {
        "BACKEND": "config.settings.cloudinary.storages.MediaAndAudioCloudinaryStorage",
    },
    # Content-hashed file names (style.4f1c2a9e.css): WhiteNoise serves them
    # with a one-year "immutable" cache, so repeat visits load CSS/JS/icons from
    # the browser with no network round trip. A changed file gets a new name.
    "staticfiles": {
        "BACKEND": "config.storages.StaticFilesStorage",
    },
}

# ─── Cloudinary ──────────────────────────────────────────────────────────────
CLOUDINARY_STORAGE = {
    "CLOUD_NAME": os.environ["CLOUDINARY_CLOUD_NAME"],
    "API_KEY": os.environ["CLOUDINARY_API_KEY"],
    "API_SECRET": os.environ["CLOUDINARY_API_SECRET"],
    "DEFAULT_FOLDER": "solo-chat",
}

# ─── Email (Resend) ──────────────────────────────────────────────────────────
# base.py read these before load_dotenv() ran; read them again so a .env file
# works as well as real environment variables.
RESEND_API_KEY = os.environ.get("RESEND_API_KEY", RESEND_API_KEY)
if RESEND_API_KEY:
    EMAIL_BACKEND = "accounts.email.ResendEmailBackend"
DEFAULT_FROM_EMAIL = os.environ.get("DEFAULT_FROM_EMAIL", DEFAULT_FROM_EMAIL)
SITE_URL = os.environ.get("SITE_URL", SITE_URL).rstrip("/")
