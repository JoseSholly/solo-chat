from datetime import timedelta

import pytest
from django.utils import timezone

from chat.models import Message, Room, RoomMembership
from chat.repositories import RoomDashboardRepository


pytestmark = pytest.mark.django_db


def test_get_user_dashboard_returns_empty_when_user_has_no_rooms(user):
    data = RoomDashboardRepository.get_user_dashboard(user)

    assert data.rooms == []
    assert data.membership_map == {}
    assert data.last_message_map == {}
    assert data.unread_data == {}


def test_get_user_dashboard_room_with_no_messages(user, room):
    data = RoomDashboardRepository.get_user_dashboard(user)

    assert [r.id for r in data.rooms] == [room.id]
    assert room.id in data.membership_map
    assert data.last_message_map == {}
    assert data.unread_data == {}
    assert data.rooms[0].member_count_annotation == 1
    assert data.rooms[0].latest_message_id is None


def test_get_user_dashboard_room_with_unread_messages(user, other_user, room):
    RoomMembership.objects.create(user=other_user, room=room)
    membership = RoomMembership.objects.get(user=user, room=room)
    RoomMembership.objects.filter(pk=membership.pk).update(
        last_seen=timezone.now() - timedelta(hours=1)
    )

    m1 = Message.objects.create(
        room=room, sender=other_user, username=other_user.username,
        message_type=Message.MessageType.TEXT, content="hi",
    )
    m2 = Message.objects.create(
        room=room, sender=other_user, username=other_user.username,
        message_type=Message.MessageType.TEXT, content="you there?",
    )
    # Force distinct timestamps — SQLite auto_now_add can tie within one tick.
    now = timezone.now()
    Message.objects.filter(pk=m1.pk).update(timestamp=now - timedelta(minutes=2))
    Message.objects.filter(pk=m2.pk).update(timestamp=now - timedelta(minutes=1))

    data = RoomDashboardRepository.get_user_dashboard(user)

    assert data.unread_data[room.id] == 2
    assert data.rooms[0].member_count_annotation == 2
    # latest message wins the last_message_map slot
    latest = data.last_message_map[room.id]
    assert latest.content == "you there?"
    assert data.rooms[0].latest_message_id == latest.id
    # sanity: the earlier message is not the "latest"
    assert m1.id != latest.id


def test_get_user_dashboard_no_unread_when_last_seen_is_after_latest_message(
    user, other_user, room
):
    RoomMembership.objects.create(user=other_user, room=room)
    Message.objects.create(
        room=room, sender=other_user, username=other_user.username,
        message_type=Message.MessageType.TEXT, content="hi",
    )
    # Move last_seen forward, past the message
    membership = RoomMembership.objects.get(user=user, room=room)
    RoomMembership.objects.filter(pk=membership.pk).update(
        last_seen=timezone.now() + timedelta(minutes=1)
    )

    data = RoomDashboardRepository.get_user_dashboard(user)

    assert data.unread_data == {}


def test_get_user_dashboard_across_multiple_rooms(user, other_user):
    r1 = Room.objects.create(name="alpha", creator=user)
    r2 = Room.objects.create(name="beta", creator=user)
    RoomMembership.objects.create(user=user, room=r1)
    RoomMembership.objects.create(user=user, room=r2)
    RoomMembership.objects.create(user=other_user, room=r1)

    # r1 has an unread message; r2 has no messages
    RoomMembership.objects.filter(user=user, room=r1).update(
        last_seen=timezone.now() - timedelta(hours=1)
    )
    Message.objects.create(
        room=r1, sender=other_user, username=other_user.username,
        message_type=Message.MessageType.TEXT, content="hey",
    )

    data = RoomDashboardRepository.get_user_dashboard(user)

    room_ids = {r.id for r in data.rooms}
    assert room_ids == {r1.id, r2.id}
    assert data.unread_data == {r1.id: 1}
    assert r1.id in data.last_message_map
    assert r2.id not in data.last_message_map
