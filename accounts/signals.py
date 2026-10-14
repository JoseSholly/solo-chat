"""Clear a cached user (accounts/authentication.py) the moment it changes.

These are module-level functions on purpose: Django keeps signal receivers by
weak reference, so a function defined inside AppConfig.ready() would be
garbage-collected as soon as ready() returned and silently never run.

Bulk .update()/.bulk_update() send no signals; UserQuerySet covers those.
"""

from django.db.models.signals import m2m_changed, post_delete, post_save
from django.dispatch import receiver

from .authentication import forget_user
from .models import User


@receiver(post_save, sender=User, dispatch_uid="accounts.user_saved")
@receiver(post_delete, sender=User, dispatch_uid="accounts.user_deleted")
def user_changed(sender, instance, **kwargs):
    # Profile, password, is_active, ... or deletion: the next request reads
    # the fresh row.
    forget_user(instance.pk)


def access_changed(sender, instance, action, reverse, pk_set, **kwargs):
    """Groups and permissions are m2m: user.groups.add(...) saves no user.

    Seen from the user's side `instance` is the user; from the group's or
    permission's side (`reverse`) `pk_set` holds the affected user ids.
    """
    if action.startswith("post_") or action == "pre_clear":
        if not reverse:
            forget_user(instance.pk)
        elif pk_set:
            for pk in pk_set:
                forget_user(pk)
        else:  # reverse .clear(): the ids aren't given, so ask
            for pk in instance.user_set.values_list("pk", flat=True):
                forget_user(pk)


m2m_changed.connect(
    access_changed,
    sender=User.groups.through,
    dispatch_uid="accounts.groups_changed",
)
m2m_changed.connect(
    access_changed,
    sender=User.user_permissions.through,
    dispatch_uid="accounts.permissions_changed",
)
