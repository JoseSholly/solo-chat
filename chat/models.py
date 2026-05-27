import uuid

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import FileExtensionValidator
from django.db import models


def validate_file_size(value):
    if value.size > 10 * 1024 * 1024:
        raise ValidationError("File too large. Maximum allowed size is 10 MB.")


class Room(models.Model):
    id          = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name        = models.CharField(max_length=100, unique=True)
    description = models.TextField(blank=True, default="")
    slug        = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    creator     = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_rooms",
    )
    created_at  = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name


class RoomMembership(models.Model):
    user      = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="memberships",
    )
    room      = models.ForeignKey(Room, on_delete=models.CASCADE, related_name="memberships")
    joined_at = models.DateTimeField(auto_now_add=True)
    last_seen = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = [("user", "room")]

    def __str__(self):
        return f"{self.user} in {self.room}"


class Message(models.Model):
    class MessageType(models.TextChoices):
        TEXT  = "text",  "Text"
        IMAGE = "image", "Image"
        VOICE = "voice", "Voice Note"

    id           = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    room         = models.ForeignKey(Room, on_delete=models.CASCADE, related_name="messages")
    sender       = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="messages",
    )
    username     = models.CharField(max_length=50)
    message_type = models.CharField(max_length=10, choices=MessageType.choices, default=MessageType.TEXT)
    content      = models.TextField(blank=True, null=True)
    file         = models.FileField(
        upload_to="uploads/%Y/%m/%d/",
        blank=True,
        null=True,
        validators=[
            FileExtensionValidator(["jpg", "jpeg", "png", "gif", "webp", "mp3", "ogg", "wav"]),
            validate_file_size,
        ],
    )
    timestamp    = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["timestamp"]

    def __str__(self):
        return f"[{self.room.name}] {self.username}: {self.message_type}"

    @property
    def file_url(self):
        return self.file.url if self.file else None
