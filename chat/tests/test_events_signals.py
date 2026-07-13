from datetime import timedelta

import pytest
from django.utils import timezone

from chat.models import Message, RoomMembership


pytestmark = pytest.mark.django_db


def test_post_save_message_advances_sender_last_seen(user, room):
    membership = RoomMembership.objects.get(user=user, room=room)
    stale = timezone.now() - timedelta(hours=1)
    RoomMembership.objects.filter(pk=membership.pk).update(last_seen=stale)

    Message.objects.create(
        room=room,
        sender=user,
        username=user.username,
        message_type=Message.MessageType.TEXT,
        content="hi",
    )

    membership.refresh_from_db()
    assert membership.last_seen > stale


def test_post_save_message_without_sender_is_a_noop(user, room):
    membership = RoomMembership.objects.get(user=user, room=room)
    stale = timezone.now() - timedelta(hours=1)
    RoomMembership.objects.filter(pk=membership.pk).update(last_seen=stale)

    Message.objects.create(
        room=room,
        sender=None,
        username="anon",
        message_type=Message.MessageType.TEXT,
        content="hi",
    )

    membership.refresh_from_db()
    assert membership.last_seen == stale


def test_message_update_does_not_advance_last_seen(user, room):
    message = Message.objects.create(
        room=room,
        sender=user,
        username=user.username,
        message_type=Message.MessageType.TEXT,
        content="hi",
    )
    membership = RoomMembership.objects.get(user=user, room=room)
    stale = timezone.now() - timedelta(hours=1)
    RoomMembership.objects.filter(pk=membership.pk).update(last_seen=stale)

    message.content = "edited"
    message.save(update_fields=["content"])

    membership.refresh_from_db()
    assert membership.last_seen == stale
