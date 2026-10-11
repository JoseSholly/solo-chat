import math

from django.core.exceptions import ValidationError

IMAGE_MAX_BYTES = 10 * 1024 * 1024  # 10 MB
VOICE_MAX_BYTES = 25 * 1024 * 1024  # 25 MB
VOICE_MAX_SECONDS = 60 * 60  # generous ceiling; the recorder itself stops at 10 min

ALLOWED_IMAGE_TYPES = {"image/jpeg", "image/png", "image/gif", "image/webp"}
ALLOWED_AUDIO_TYPES = {
    "audio/mpeg",
    "audio/mp4",
    "audio/ogg",
    "audio/wav",
    "audio/webm",
}


class MediaService:
    @staticmethod
    def validate(file, message_type: str) -> None:
        if message_type == "image":
            if file.content_type not in ALLOWED_IMAGE_TYPES:
                raise ValidationError(f"Unsupported image type: {file.content_type}")
            if file.size > IMAGE_MAX_BYTES:
                raise ValidationError("Image exceeds 10 MB limit.")

        elif message_type == "voice":
            if file.content_type not in ALLOWED_AUDIO_TYPES:
                raise ValidationError(f"Unsupported audio type: {file.content_type}")
            if file.size > VOICE_MAX_BYTES:
                raise ValidationError("Voice note exceeds 25 MB limit.")

        else:
            raise ValidationError(f"Unknown message_type: {message_type!r}")

    @staticmethod
    def parse_duration(raw, message_type: str) -> float | None:
        """Client-reported voice note length in seconds; anything unusable is dropped."""
        if message_type != "voice" or raw in (None, ""):
            return None
        try:
            seconds = float(raw)
        except (TypeError, ValueError):
            return None
        if not math.isfinite(seconds) or not 0 < seconds <= VOICE_MAX_SECONDS:
            return None
        return round(seconds, 2)
