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


# ---------------------------------------------------------------------------
# Room QR code
# ---------------------------------------------------------------------------


def test_member_gets_invite_qr_as_svg(user, room):
    res = _client(user).get(f"/api/rooms/{room.slug}/qr/")

    assert res.status_code == 200
    assert res["Content-Type"] == "image/svg+xml"
    assert res["Cache-Control"] == "private, max-age=86400"
    assert b"<svg" in res.content
    assert b'xmlns="http://www.w3.org/2000/svg"' in res.content


def test_qr_encodes_the_join_url(user, room, monkeypatch):
    import segno

    encoded = []
    real_make = segno.make
    monkeypatch.setattr(
        "chat.views.segno.make",
        lambda content, **kw: encoded.append(content) or real_make(content, **kw),
    )

    _client(user).get(f"/api/rooms/{room.slug}/qr/")

    assert encoded == [f"http://testserver/join/{room.slug}/"]


def test_non_member_cannot_get_qr(other_user, room):
    res = _client(other_user).get(f"/api/rooms/{room.slug}/qr/")
    assert res.status_code == 403


def test_qr_for_unknown_room_is_404(user):
    res = _client(user).get("/api/rooms/00000000-0000-0000-0000-000000000000/qr/")
    assert res.status_code == 404


def test_anonymous_cannot_get_qr(room):
    res = APIClient().get(f"/api/rooms/{room.slug}/qr/")
    assert res.status_code == 401
