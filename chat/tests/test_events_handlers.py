from unittest.mock import MagicMock

import pytest

from chat.events import MessageCreated, UserJoinedRoom, UserLeftRoom
from chat.events.handlers import (
    broadcast_message_to_room,
    broadcast_presence,
    notify_other_members_of_message,
)
from chat.models import RoomMembership


def _sample_message_event(**overrides):
    defaults = dict(
        message_id="m-1",
        room_id="r-1",
        room_slug="slug-1",
        room_name="general",
        sender_id="u-1",
        sender_username="alice",
        sender_display_name="Alice",
        sender_avatar_url=None,
        message_type="text",
        content="hello",
        file_url=None,
        timestamp="2026-07-13T12:00:00+00:00",
    )
    defaults.update(overrides)
    return MessageCreated(**defaults)


@pytest.fixture
def mock_channel_layer(monkeypatch):
    """Replace get_channel_layer with a mock whose group_send records calls."""
    calls = []

    async def group_send(group, message):
        calls.append((group, message))

    layer = MagicMock()
    layer.group_send = group_send
    monkeypatch.setattr("chat.events.handlers.get_channel_layer", lambda: layer)
    return calls


def test_broadcast_message_to_room_sends_to_room_group(mock_channel_layer):
    event = _sample_message_event()

    broadcast_message_to_room(event)

    assert len(mock_channel_layer) == 1
    group, payload = mock_channel_layer[0]
    assert group == "room_r-1"
    assert payload["type"] == "chat_message"
    assert payload["id"] == "m-1"
    assert payload["username"] == "alice"
    assert payload["display_name"] == "Alice"
    assert payload["sender_id"] == "u-1"
    assert payload["content"] == "hello"
    assert payload["file_url"] == ""
    assert payload["timestamp"] == "2026-07-13T12:00:00+00:00"


def test_broadcast_message_to_room_uses_file_url_for_media(mock_channel_layer):
    event = _sample_message_event(
        message_type="image", content=None, file_url="/media/pic.jpg"
    )

    broadcast_message_to_room(event)

    _, payload = mock_channel_layer[0]
    assert payload["message_type"] == "image"
    assert payload["content"] == ""
    assert payload["file_url"] == "/media/pic.jpg"


def test_broadcast_message_to_room_noop_without_channel_layer(monkeypatch):
    monkeypatch.setattr("chat.events.handlers.get_channel_layer", lambda: None)
    broadcast_message_to_room(_sample_message_event())  # must not raise


@pytest.mark.django_db
def test_notify_other_members_of_message_sends_to_each_non_sender(
    mock_channel_layer, user, other_user, third_user, room
):
    RoomMembership.objects.create(user=other_user, room=room)
    RoomMembership.objects.create(user=third_user, room=room)
    event = _sample_message_event(
        room_id=str(room.id),
        room_slug=str(room.slug),
        room_name=room.name,
        sender_id=str(user.id),
    )

    notify_other_members_of_message(event)

    groups = {call[0] for call in mock_channel_layer}
    assert groups == {f"user_{other_user.id}", f"user_{third_user.id}"}
    # sender is excluded
    assert f"user_{user.id}" not in groups

    # payload shape
    _, payload = mock_channel_layer[0]
    assert payload["type"] == "unread_update"
    assert payload["room_slug"] == str(room.slug)
    assert payload["room_name"] == room.name


@pytest.mark.django_db
def test_notify_other_members_sends_nothing_when_sender_is_only_member(
    mock_channel_layer, user, room
):
    event = _sample_message_event(
        room_id=str(room.id),
        room_slug=str(room.slug),
        room_name=room.name,
        sender_id=str(user.id),
    )

    notify_other_members_of_message(event)

    assert mock_channel_layer == []


def test_broadcast_presence_join(mock_channel_layer):
    event = UserJoinedRoom(
        room_id="r-1", user_id="u-1", username="alice", display_name="Alice"
    )

    broadcast_presence(event)

    group, payload = mock_channel_layer[0]
    assert group == "room_r-1"
    assert payload["type"] == "presence_event"
    assert payload["event"] == "join"
    assert payload["username"] == "alice"
    assert payload["display_name"] == "Alice"


def test_broadcast_presence_leave(mock_channel_layer):
    event = UserLeftRoom(
        room_id="r-1", user_id="u-1", username="alice", display_name="Alice"
    )

    broadcast_presence(event)

    _, payload = mock_channel_layer[0]
    assert payload["event"] == "leave"
