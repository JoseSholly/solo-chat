import os

import cloudinary.uploader
from cloudinary_storage.storage import RESOURCE_TYPES, MediaCloudinaryStorage

# Cloudinary rejects audio uploaded as an image; it stores audio under "video".
AUDIO_EXTENSIONS = {".webm", ".ogg", ".m4a", ".mp3", ".wav", ".mp4"}


def _is_audio(name: str) -> bool:
    return os.path.splitext(name)[1].lower() in AUDIO_EXTENSIONS


class MediaAndAudioCloudinaryStorage(MediaCloudinaryStorage):
    """MediaCloudinaryStorage that also handles voice notes.

    Images keep the default "image" resource type. Audio is uploaded as
    "video", and its extension is kept on the stored name: Cloudinary drops it
    from the public_id, and url()/delete() need it to pick the resource type.
    """

    def _get_resource_type(self, name):
        if _is_audio(name):
            return RESOURCE_TYPES["VIDEO"]
        return super()._get_resource_type(name)

    def _save(self, name, content):
        public_id = super()._save(name, content)
        if _is_audio(name) and not _is_audio(public_id):
            return public_id + os.path.splitext(name)[1].lower()
        return public_id

    def delete(self, name):
        if not _is_audio(name):
            return super().delete(name)
        response = cloudinary.uploader.destroy(
            os.path.splitext(name)[0],
            invalidate=True,
            resource_type=RESOURCE_TYPES["VIDEO"],
        )
        return response["result"] == "ok"
