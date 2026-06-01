import json
from urllib.parse import parse_qs

from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncWebsocketConsumer
from rest_framework_simplejwt.exceptions import InvalidToken, TokenError
from rest_framework_simplejwt.tokens import AccessToken

from .services import MessageService, RoomService

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
                    "type":         "chat_message",
                    "message_type": "text",
                    "username":     data["username"],
                    "display_name": data["username"],
                    "content":      data["content"],
                    "timestamp":    message.timestamp.isoformat(),
                },
            )

        elif message_type in ("image", "voice"):
            await self.channel_layer.group_send(
                self.group_name,
                {
                    "type":         "chat_message",
                    "message_type": message_type,
                    "username":     data["username"],
                    "display_name": data["username"],
                    "file_url":     data["file_url"],
                    "timestamp":    data.get("timestamp", ""),
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

        self.user = await self._authenticate()
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

        await self.channel_layer.group_send(
            self.group_name,
            {
                "type":         "presence_event",
                "event":        "join",
                "username":     self.user.username,
                "display_name": self.user.display_name,
            },
        )

    async def disconnect(self, close_code):
        if not hasattr(self, "group_name"):
            return
        if hasattr(self, "user") and self.user:
            await self.channel_layer.group_send(
                self.group_name,
                {
                    "type":         "presence_event",
                    "event":        "leave",
                    "username":     self.user.username,
                    "display_name": self.user.display_name,
                },
            )
        await self.channel_layer.group_discard(self.group_name, self.channel_name)

    async def receive(self, text_data):
        data = json.loads(text_data)
        message_type = data.get("type", "text")

        if message_type == "text":
            content = data.get("content", "").strip()
            if not content:
                return
            message = await self._save_text(content)
            await self.channel_layer.group_send(
                self.group_name,
                {
                    "type":         "chat_message",
                    "message_type": "text",
                    "username":     self.user.username,
                    "display_name": self.user.display_name,
                    "sender_id":    str(self.user.id),
                    "avatar_url":   self.user.avatar.url if self.user.avatar else None,
                    "content":      content,
                    "timestamp":    message.timestamp.isoformat(),
                },
            )
            await self._notify_other_members()

        elif message_type in ("image", "voice"):
            await self.channel_layer.group_send(
                self.group_name,
                {
                    "type":         "chat_message",
                    "id":           data.get("id", ""),
                    "message_type": message_type,
                    "username":     self.user.username,
                    "display_name": self.user.display_name,
                    "sender_id":    str(self.user.id),
                    "avatar_url":   self.user.avatar.url if self.user.avatar else None,
                    "file_url":     data.get("file_url", ""),
                    "timestamp":    data.get("timestamp", ""),
                },
            )
            await self._notify_other_members()

    async def chat_message(self, event):
        await self.send(text_data=json.dumps(event))

    async def presence_event(self, event):
        await self.send(text_data=json.dumps(event))

    async def _notify_other_members(self):
        member_ids = await self._get_other_member_ids()
        for uid in member_ids:
            await self.channel_layer.group_send(
                f"user_{uid}",
                {
                    "type":      "unread_update",
                    "room_slug": str(self.room.slug),
                    "room_name": self.room.name,
                },
            )

    # -----------------------------------------------------------------------
    # Helpers
    # -----------------------------------------------------------------------

    @database_sync_to_async
    def _authenticate(self):
        query_string = self.scope.get("query_string", b"").decode()
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

    @database_sync_to_async
    def _get_other_member_ids(self):
        from .models import RoomMembership
        return list(
            RoomMembership.objects
            .filter(room=self.room)
            .exclude(user_id=self.user.id)
            .values_list("user_id", flat=True)
        )


# ---------------------------------------------------------------------------
# Notification consumer — per-user channel, pushes unread badge updates
# ---------------------------------------------------------------------------

class NotificationConsumer(AsyncWebsocketConsumer):

    async def connect(self):
        self.user = await self._authenticate()
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
        await self.send(text_data=json.dumps({
            "type":      "unread_update",
            "room_slug": event["room_slug"],
            "room_name": event["room_name"],
        }))

    @database_sync_to_async
    def _authenticate(self):
        query_string = self.scope.get("query_string", b"").decode()
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
