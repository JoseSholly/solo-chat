import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from rest_framework.test import APIClient

pytestmark = pytest.mark.django_db


@pytest.fixture
def media_root(settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path


def _voice_note():
    return SimpleUploadedFile("note.webm", b"voice", content_type="audio/webm")


def _client(user):
    client = APIClient()
    client.force_authenticate(user)
    return client


def test_member_can_upload_voice_note(media_root, user, room):
    res = _client(user).post(
        f"/api/rooms/{room.slug}/upload/",
        {"file": _voice_note(), "message_type": "voice", "duration": "42.0"},
        format="multipart",
    )

    assert res.status_code == 201
    assert res.data["message_type"] == "voice"
    assert res.data["file_url"].endswith(".webm")
    assert res.data["duration"] == 42.0


def test_voice_note_without_duration_still_uploads(media_root, user, room):
    res = _client(user).post(
        f"/api/rooms/{room.slug}/upload/",
        {"file": _voice_note(), "message_type": "voice", "duration": "bogus"},
        format="multipart",
    )

    assert res.status_code == 201
    assert res.data["duration"] is None


def test_non_member_cannot_upload_voice_note(media_root, other_user, room):
    res = _client(other_user).post(
        f"/api/rooms/{room.slug}/upload/",
        {"file": _voice_note(), "message_type": "voice"},
        format="multipart",
    )

    assert res.status_code == 403


def test_upload_without_file_is_rejected(user, room):
    res = _client(user).post(
        f"/api/rooms/{room.slug}/upload/",
        {"message_type": "voice"},
        format="multipart",
    )

    assert res.status_code == 400
    assert res.data["code"] == "missing_file"
