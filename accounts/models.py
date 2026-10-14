import uuid

from django.contrib.auth.models import (
    AbstractBaseUser,
    BaseUserManager,
    PermissionsMixin,
)
from django.db import models


class UserQuerySet(models.QuerySet):
    """Bulk writes send no save() signals, so they clear the auth cache here."""

    def _forget(self, ids):
        from .authentication import forget_user

        for pk in ids:
            forget_user(pk)

    def update(self, **kwargs):
        ids = list(self.values_list("pk", flat=True))
        count = super().update(**kwargs)
        self._forget(ids)
        return count

    def bulk_update(self, objs, fields, batch_size=None):
        count = super().bulk_update(objs, fields, batch_size)
        self._forget(o.pk for o in objs)
        return count


class UserManager(BaseUserManager.from_queryset(UserQuerySet)):
    def create_user(self, email, username, display_name, password=None, **extra_fields):
        if not email:
            raise ValueError("Email is required")
        email = self.normalize_email(email)
        user = self.model(
            email=email, username=username, display_name=display_name, **extra_fields
        )
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(
        self, email, username, display_name, password=None, **extra_fields
    ):
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        return self.create_user(email, username, display_name, password, **extra_fields)


class User(AbstractBaseUser, PermissionsMixin):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    email = models.EmailField(unique=True)
    username = models.CharField(max_length=50, unique=True)
    display_name = models.CharField(max_length=100)
    avatar = models.ImageField(upload_to="avatars/", blank=True, null=True)
    bio = models.TextField(blank=True, default="")
    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)
    date_joined = models.DateTimeField(auto_now_add=True)

    objects = UserManager()

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = ["username", "display_name"]

    def __str__(self):
        return self.email
