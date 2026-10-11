from unittest.mock import patch

import pytest
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile

from chat.events import LastSeenUpdated, MessageCreated, RoomCreated
from chat.models import Message, Room, RoomMembership
from chat.services import MediaService, MessageService, RoomService


pytestmark = pytest.mark.django_db


# ---------------------------------------------------------------------------
# MessageService
# ---------------------------------------------------------------------------


def test_create_text_persists_and_emits_message_created(captured_events, user, room):
    message = MessageService.create_text(room, user.username, "hello", sender=user)

    assert Message.objects.filter(pk=message.pk, content="hello").exists()
    assert len(captured_events) == 1

    event = captured_events[0]
    assert isinstance(event, MessageCreated)
    assert event.message_id == str(message.id)
    assert event.room_id == str(room.id)
    assert event.room_slug == str(room.slug)
    assert event.sender_id == str(user.id)
    assert event.sender_username == user.username
    assert event.sender_display_name == user.display_name
    assert event.message_type == "text"
    assert event.content == "hello"
    assert event.file_url is None


def test_create_text_without_sender_emits_event_with_null_sender_id(
    captured_events, room
):
    MessageService.create_text(room, "anon", "hi", sender=None)

    event = captured_events[0]
    assert event.sender_id is None
    assert event.sender_username == "anon"
    assert event.sender_display_name == "anon"  # falls back to message.username


def test_create_media_rejects_invalid_type(captured_events, user, room):
    with pytest.raises(ValueError):
        MessageService.create_media(
            room, user.username, "text", file=object(), sender=user
        )

    assert captured_events == []
    assert Message.objects.count() == 0


def test_create_media_voice_persists_and_emits_file_url(
    captured_events, settings, tmp_path, user, room
):
    settings.MEDIA_ROOT = tmp_path
    file = SimpleUploadedFile("note.webm", b"voice", content_type="audio/webm")

    message = MessageService.create_media(
        room, user.username, "voice", file, sender=user, duration=12.3
    )

    assert message.message_type == "voice"
    assert message.file.name.endswith(".webm")
    assert message.duration == 12.3
    event = captured_events[0]
    assert event.message_type == "voice"
    assert event.file_url == message.file.url
    assert event.duration == 12.3


def test_create_media_image_ignores_duration(
    captured_events, settings, tmp_path, user, room
):
    settings.MEDIA_ROOT = tmp_path
    file = SimpleUploadedFile("pic.png", b"img", content_type="image/png")

    message = MessageService.create_media(
        room, user.username, "image", file, sender=user, duration=5
    )

    assert message.duration is None


# ---------------------------------------------------------------------------
# MediaService
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("content_type", ["audio/webm", "audio/mp4", "audio/ogg"])
def test_validate_accepts_recorded_voice_formats(content_type):
    file = SimpleUploadedFile("note", b"voice", content_type=content_type)
    MediaService.validate(file, "voice")


def test_validate_rejects_non_audio_voice_note():
    file = SimpleUploadedFile("note.png", b"img", content_type="image/png")
    with pytest.raises(ValidationError):
        MediaService.validate(file, "voice")


def test_validate_rejects_oversized_voice_note():
    file = SimpleUploadedFile("note.webm", b"voice", content_type="audio/webm")
    file.size = 25 * 1024 * 1024 + 1
    with pytest.raises(ValidationError):
        MediaService.validate(file, "voice")


# ---------------------------------------------------------------------------
# RoomService
# ---------------------------------------------------------------------------


def test_create_room_creates_membership_and_emits_room_created(captured_events, user):
    room = RoomService.create(user, "team-x", description="the x-team")

    assert Room.objects.filter(pk=room.pk).exists()
    assert RoomMembership.objects.filter(user=user, room=room).exists()

    assert len(captured_events) == 1
    event = captured_events[0]
    assert isinstance(event, RoomCreated)
    assert event.room_id == str(room.id)
    assert event.creator_id == str(user.id)
    assert event.name == "team-x"


def test_create_room_is_atomic_when_membership_fails(user):
    """If the membership write raises, the room row must roll back."""
    from chat.services import room_service as room_service_module

    def failing_create(*args, **kwargs):
        raise RuntimeError("simulated failure")

    with patch.object(RoomMembership.objects, "create", side_effect=failing_create):
        with pytest.raises(RuntimeError):
            room_service_module.RoomService.create(user, "doomed")

    assert not Room.objects.filter(name="doomed").exists()


def test_update_last_seen_updates_field_and_emits_event(captured_events, user, room):
    RoomService.update_last_seen(user, room)

    assert len(captured_events) == 1
    event = captured_events[0]
    assert isinstance(event, LastSeenUpdated)
    assert event.room_id == str(room.id)
    assert event.user_id == str(user.id)


def test_is_member_false_for_anonymous_or_none(user, room):
    assert RoomService.is_member(None, room) is False


def test_get_by_slug_returns_none_for_missing_room():
    import uuid

    assert RoomService.get_by_slug(uuid.uuid4()) is None


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("12.34", 12.3),
        (59.96, 60.0),
        (None, None),
        ("", None),
        ("abc", None),
        ("0", None),
        ("-3", None),
        ("inf", None),
        ("nan", None),
    ],
)
def test_parse_duration(raw, expected):
    assert MediaService.parse_duration(raw) == expected
