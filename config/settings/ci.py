from .base import *

SECRET_KEY = "ci-only-secret-key-not-for-production"

DEBUG = False

ALLOWED_HOSTS = ["localhost", "127.0.0.1"]

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": ":memory:",
    }
}

CHANNEL_LAYERS = {
    "default": {
        "BACKEND": "channels.layers.InMemoryChannelLayer",
    }
}

PASSWORD_HASHERS = [
    "django.contrib.auth.hashers.MD5PasswordHasher",
]
