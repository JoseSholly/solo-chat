from django.core.exceptions import ValidationError

IMAGE_MAX_BYTES = 10 * 1024 * 1024  # 10 MB
VOICE_MAX_BYTES = 25 * 1024 * 1024  # 25 MB

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
