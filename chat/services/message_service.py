from chat.models import Message, Room


class MessageService:
    HISTORY_LIMIT = 50

    @staticmethod
    def get_history(room: Room) -> list[Message]:
        qs = room.messages.select_related("sender").order_by("-timestamp")[: MessageService.HISTORY_LIMIT]
        return list(reversed(qs))

    @staticmethod
    def create_text(room: Room, username: str, content: str, sender=None) -> Message:
        return Message.objects.create(
            room=room,
            sender=sender,
            username=username,
            message_type=Message.MessageType.TEXT,
            content=content,
        )

    @staticmethod
    def create_media(room: Room, username: str, message_type: str, file, sender=None) -> Message:
        allowed = {Message.MessageType.IMAGE, Message.MessageType.VOICE}
        if message_type not in allowed:
            raise ValueError(f"Invalid message_type: {message_type!r}")
        return Message.objects.create(
            room=room,
            sender=sender,
            username=username,
            message_type=message_type,
            file=file,
        )
