import importlib
from unittest.mock import patch

import pytest
from django.core.files.base import ContentFile


@pytest.fixture
def storage(monkeypatch):
    # cloudinary_storage reads credentials at import time; dummy ones suffice
    # because every network call below is mocked.
    monkeypatch.setenv("CLOUDINARY_CLOUD_NAME", "test")
    monkeypatch.setenv("CLOUDINARY_API_KEY", "key")
    monkeypatch.setenv("CLOUDINARY_API_SECRET", "secret")
    module = importlib.import_module("config.settings.cloudinary.storages")
    return module.MediaAndAudioCloudinaryStorage()


@pytest.mark.parametrize("name", ["note.webm", "note.m4a", "note.OGG", "note.mp3"])
def test_audio_uses_video_resource_type(storage, name):
    assert storage._get_resource_type(name) == "video"


def test_images_keep_image_resource_type(storage):
    assert storage._get_resource_type("photo.png") == "image"


def test_save_keeps_audio_extension(storage):
    with patch("cloudinary.uploader.upload") as upload:
        upload.return_value = {"public_id": "media/uploads/note_abc"}
        name = storage._save("uploads/note.webm", ContentFile(b"voice"))

    assert upload.call_args.kwargs["resource_type"] == "video"
    assert name == "media/uploads/note_abc.webm"
    assert "/video/upload/" in storage.url(name)
    assert storage.url(name).endswith("note_abc.webm")


def test_save_image_returns_public_id_unchanged(storage):
    with patch("cloudinary.uploader.upload") as upload:
        upload.return_value = {"public_id": "media/uploads/photo_abc"}
        name = storage._save("uploads/photo.png", ContentFile(b"img"))

    assert upload.call_args.kwargs["resource_type"] == "image"
    assert name == "media/uploads/photo_abc"


def test_delete_audio_strips_extension(storage):
    with patch("cloudinary.uploader.destroy") as destroy:
        destroy.return_value = {"result": "ok"}
        assert storage.delete("media/uploads/note_abc.webm")

    destroy.assert_called_once_with(
        "media/uploads/note_abc", invalidate=True, resource_type="video"
    )
