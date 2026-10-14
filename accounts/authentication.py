"""Who is making this request, without asking the database every time.

SimpleJWT looks the user up on every API request. When the database is a
long way off that is a full round trip (about 100 ms) before the view even
starts, so the user is kept in the cache for USER_CACHE_SECONDS.

The cache is never trusted over the database for long, and it is cleared the
moment a user changes, however the change is made:
  - user.save() / user.delete()                      (signals, accounts/apps.py)
  - User.objects.filter(...).update(...) / bulk_update (UserQuerySet)
  - changes to a user's groups or permissions         (signals, accounts/apps.py)
In production the cache is Redis, shared by every server process, so a change
made in one is seen by all. TTL is only the backstop for a change made behind
Django's back (raw SQL, another tool editing the database).

If the cache itself fails (Redis down), requests carry on by asking the
database, as if nothing were cached.
"""

import logging

from django.core.cache import cache
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework_simplejwt.settings import api_settings

logger = logging.getLogger(__name__)

USER_CACHE_SECONDS = 60


def user_cache_key(user_id) -> str:
    return f"auth-user:{user_id}"


def forget_user(user_id) -> None:
    """Drop one user from the cache. Never raises."""
    try:
        cache.delete(user_cache_key(user_id))
    except Exception:
        logger.warning("Couldn't clear cached user %s", user_id, exc_info=True)


def get_active_user(user_id):
    """The active user with this id, or None. Cached for USER_CACHE_SECONDS."""
    from .models import User

    key = user_cache_key(user_id)
    try:
        user = cache.get(key)
    except Exception:
        logger.warning(
            "User cache unavailable; reading from the database", exc_info=True
        )
        user = None
    if user is None:
        try:
            user = User.objects.get(pk=user_id)
        except (User.DoesNotExist, ValueError, TypeError):
            return None
        try:
            cache.set(key, user, USER_CACHE_SECONDS)
        except Exception:
            logger.warning("Couldn't cache user %s", user_id, exc_info=True)
    return user if user.is_active else None


class CachedJWTAuthentication(JWTAuthentication):
    def get_user(self, validated_token):
        try:
            user_id = validated_token[api_settings.USER_ID_CLAIM]
        except KeyError:
            return super().get_user(validated_token)  # raises the usual InvalidToken

        user = get_active_user(user_id)
        if user is None:
            # Unknown or disabled: let SimpleJWT produce its normal error.
            return super().get_user(validated_token)
        return user
