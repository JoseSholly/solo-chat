from chat.events import MessageCreated, event_bus
from chat.models import Message, Room


class MessageService:
    HISTORY_LIMIT = 50

    @staticmethod
    def get_history(room: Room, since=None) -> list[Message]:
        qs = room.messages.select_related("sender").order_by("-timestamp")
        if since is not None:
            qs = qs.filter(timestamp__gte=since)
        return list(reversed(qs[: MessageService.HISTORY_LIMIT]))

    @staticmethod
    def create_text(room: Room, username: str, content: str, sender=None) -> Message:
        message = Message.objects.create(
            room=room,
            sender=sender,
            username=username,
            message_type=Message.MessageType.TEXT,
            content=content,
        )
        MessageService._emit_created(message, room)
        return message

    @staticmethod
    def create_media(
        room: Room, username: str, message_type: str, file, sender=None
    ) -> Message:
        allowed = {Message.MessageType.IMAGE, Message.MessageType.VOICE}
        if message_type not in allowed:
            raise ValueError(f"Invalid message_type: {message_type!r}")
        message = Message.objects.create(
            room=room,
            sender=sender,
            username=username,
            message_type=message_type,
            file=file,
        )
        MessageService._emit_created(message, room)
        return message

    @staticmethod
    def _emit_created(message: Message, room: Room) -> None:
        sender = message.sender
        event_bus.emit(
            MessageCreated(
                message_id=str(message.id),
                room_id=str(room.id),
                room_slug=str(room.slug),
                room_name=room.name,
                sender_id=str(sender.id) if sender else None,
                sender_username=message.username,
                sender_display_name=sender.display_name if sender else message.username,
                sender_avatar_url=sender.avatar.url
                if sender and sender.avatar
                else None,
                message_type=message.message_type,
                content=message.content,
                file_url=message.file.url if message.file else None,
                timestamp=message.timestamp.isoformat(),
            )
        )
