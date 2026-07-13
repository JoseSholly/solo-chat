import json
from urllib.parse import parse_qs

from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncWebsocketConsumer
from rest_framework_simplejwt.exceptions import InvalidToken, TokenError
from rest_framework_simplejwt.tokens import AccessToken

from .events import UserJoinedRoom, UserLeftRoom, event_bus
from .services import MessageService, RoomService


def _authenticate_from_scope(scope):
    query_string = scope.get("query_string", b"").decode()
    params = parse_qs(query_string)
    token_list = params.get("token", [])
    if not token_list:
        return None
    try:
        payload = AccessToken(token_list[0])
        from accounts.models import User

        return User.objects.get(id=payload["user_id"])
    except (InvalidToken, TokenError, KeyError, Exception):
        return None


# ---------------------------------------------------------------------------
# Legacy consumer — anonymous, used by the old /chat/<room_name>/ template
# ---------------------------------------------------------------------------


class ChatConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        self.room_name = self.scope["url_route"]["kwargs"]["room_name"]
        self.group_name = f"chat_{self.room_name}"
        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()

    async def disconnect(self, close_code):
        await self.channel_layer.group_discard(self.group_name, self.channel_name)

    async def receive(self, text_data):
        data = json.loads(text_data)
        message_type = data.get("type", "text")

        if message_type == "text":
            message = await self._save_text(data["username"], data["content"])
            await self.channel_layer.group_send(
                self.group_name,
                {
                    "type": "chat_message",
                    "message_type": "text",
                    "username": data["username"],
                    "display_name": data["username"],
                    "content": data["content"],
                    "timestamp": message.timestamp.isoformat(),
                },
            )

        elif message_type in ("image", "voice"):
            await self.channel_layer.group_send(
                self.group_name,
                {
                    "type": "chat_message",
                    "message_type": message_type,
                    "username": data["username"],
                    "display_name": data["username"],
                    "file_url": data["file_url"],
                    "timestamp": data.get("timestamp", ""),
                },
            )

    async def chat_message(self, event):
        await self.send(text_data=json.dumps(event))

    @database_sync_to_async
    def _save_text(self, username: str, content: str):
        room, _ = RoomService.get_or_create(self.room_name)
        return MessageService.create_text(room, username, content)


# ---------------------------------------------------------------------------
# Authenticated consumer — slug-based, used by the new dashboard/room pages
# ---------------------------------------------------------------------------


class RoomChatConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        slug = self.scope["url_route"]["kwargs"]["slug"]

        self.user = await database_sync_to_async(_authenticate_from_scope)(self.scope)
        if self.user is None:
            await self.close(code=4001)
            return

        self.room = await self._get_room(slug)
        if self.room is None:
            await self.close(code=4004)
            return

        if not await self._is_member():
            await self.close(code=4003)
            return

        self.group_name = f"room_{self.room.id}"
        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()

        await database_sync_to_async(event_bus.emit)(
            UserJoinedRoom(
                room_id=str(self.room.id),
                user_id=str(self.user.id),
                username=self.user.username,
                display_name=self.user.display_name,
            )
        )

    async def disconnect(self, close_code):
        if not hasattr(self, "group_name"):
            return
        if getattr(self, "user", None) and getattr(self, "room", None):
            await database_sync_to_async(event_bus.emit)(
                UserLeftRoom(
                    room_id=str(self.room.id),
                    user_id=str(self.user.id),
                    username=self.user.username,
                    display_name=self.user.display_name,
                )
            )
        await self.channel_layer.group_discard(self.group_name, self.channel_name)

    async def receive(self, text_data):
        data = json.loads(text_data)
        message_type = data.get("type", "text")

        # Text goes through the service, which emits MessageCreated.
        # Image/voice are handled by the REST upload endpoint, which also
        # emits MessageCreated — no WebSocket path needed here.
        if message_type == "text":
            content = data.get("content", "").strip()
            if not content:
                return
            await self._save_text(content)

    async def chat_message(self, event):
        await self.send(text_data=json.dumps(event))

    async def presence_event(self, event):
        await self.send(text_data=json.dumps(event))

    # -----------------------------------------------------------------------
    # Helpers
    # -----------------------------------------------------------------------

    @database_sync_to_async
    def _get_room(self, slug):
        return RoomService.get_by_slug(slug)

    @database_sync_to_async
    def _is_member(self):
        return RoomService.is_member(self.user, self.room)

    @database_sync_to_async
    def _save_text(self, content: str):
        return MessageService.create_text(
            self.room, self.user.username, content, sender=self.user
        )


# ---------------------------------------------------------------------------
# Notification consumer — per-user channel, pushes unread badge updates
# ---------------------------------------------------------------------------


class NotificationConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        self.user = await database_sync_to_async(_authenticate_from_scope)(self.scope)
        if self.user is None:
            await self.close(code=4001)
            return

        self.group_name = f"user_{self.user.id}"
        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()

    async def disconnect(self, close_code):
        if hasattr(self, "group_name"):
            await self.channel_layer.group_discard(self.group_name, self.channel_name)

    async def receive(self, text_data):
        pass  # client never sends to this consumer

    async def unread_update(self, event):
        await self.send(
            text_data=json.dumps(
                {
                    "type": "unread_update",
                    "room_slug": event["room_slug"],
                    "room_name": event["room_name"],
                }
            )
        )
