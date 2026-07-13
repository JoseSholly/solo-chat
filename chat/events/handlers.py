from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer

from .bus import EventBus
from .events import MessageCreated, UserJoinedRoom, UserLeftRoom


def broadcast_message_to_room(event: MessageCreated) -> None:
    channel_layer = get_channel_layer()
    if channel_layer is None:
        return
    async_to_sync(channel_layer.group_send)(
        f"room_{event.room_id}",
        {
            "type": "chat_message",
            "id": event.message_id,
            "message_type": event.message_type,
            "username": event.sender_username,
            "display_name": event.sender_display_name,
            "sender_id": event.sender_id,
            "avatar_url": event.sender_avatar_url,
            "content": event.content or "",
            "file_url": event.file_url or "",
            "timestamp": event.timestamp,
        },
    )


def notify_other_members_of_message(event: MessageCreated) -> None:
    from chat.models import RoomMembership

    channel_layer = get_channel_layer()
    if channel_layer is None:
        return

    other_ids = list(
        RoomMembership.objects.filter(room_id=event.room_id)
        .exclude(user_id=event.sender_id)
        .values_list("user_id", flat=True)
    )
    for uid in other_ids:
        async_to_sync(channel_layer.group_send)(
            f"user_{uid}",
            {
                "type": "unread_update",
                "room_slug": event.room_slug,
                "room_name": event.room_name,
            },
        )


def broadcast_presence(event) -> None:
    channel_layer = get_channel_layer()
    if channel_layer is None:
        return
    async_to_sync(channel_layer.group_send)(
        f"room_{event.room_id}",
        {
            "type": "presence_event",
            "event": "join" if isinstance(event, UserJoinedRoom) else "leave",
            "username": event.username,
            "display_name": event.display_name,
        },
    )


def register_all(bus: EventBus) -> None:
    bus.subscribe(MessageCreated, broadcast_message_to_room)
    bus.subscribe(MessageCreated, notify_other_members_of_message)
    bus.subscribe(UserJoinedRoom, broadcast_presence)
    bus.subscribe(UserLeftRoom, broadcast_presence)
