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
# Add these at the top of your settings.py


load_dotenv()

# Replace the DATABASES section of your settings.py with this
tmpPostgres = urlparse(os.getenv("DATABASE_URL"))

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": tmpPostgres.path.replace("/", ""),
        "USER": tmpPostgres.username,
        "PASSWORD": tmpPostgres.password,
        "HOST": tmpPostgres.hostname,
        "PORT": 5432,
        "OPTIONS": dict(parse_qsl(tmpPostgres.query)),
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
MIDDLEWARE.insert(1, "whitenoise.middleware.WhiteNoiseMiddleware")

STORAGES = {
    "default": {
        "BACKEND": "cloudinary_storage.storage.MediaCloudinaryStorage",
    },
    "staticfiles": {
        "BACKEND": "whitenoise.storage.CompressedStaticFilesStorage",
    },
}

# ─── Cloudinary ──────────────────────────────────────────────────────────────
CLOUDINARY_STORAGE = {
    "CLOUD_NAME": os.environ["CLOUDINARY_CLOUD_NAME"],
    "API_KEY": os.environ["CLOUDINARY_API_KEY"],
    "API_SECRET": os.environ["CLOUDINARY_API_SECRET"],
    "DEFAULT_FOLDER": "solo-chat",
}
