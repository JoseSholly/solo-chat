import json
import logging
from urllib.parse import parse_qs

from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncWebsocketConsumer
from rest_framework_simplejwt.exceptions import InvalidToken, TokenError
from rest_framework_simplejwt.tokens import AccessToken

from games.services import PresenceService

from .events import UserJoinedRoom, UserLeftRoom, event_bus
from .services import MessageService, RoomService

logger = logging.getLogger(__name__)


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
# Base for the authenticated sockets: heartbeat + never die on bad input
# ---------------------------------------------------------------------------


class LiveConsumer(AsyncWebsocketConsumer):
    """Answers the browser's heartbeat and keeps the line open when a message
    is malformed or handling it fails.

    The browser (static/js/socket.js) sends {"type": "ping"} every 20 s and
    reconnects if it hears nothing back for 45 s; the pong is that answer, and
    the traffic stops proxies from cutting the line as idle. An exception in a
    consumer would otherwise close the socket and start a reconnect loop, so
    it's logged and reported to the browser instead.

    Subclasses implement receive_message(data) and, optionally, on_ping().
    """

    async def receive(self, text_data=None, bytes_data=None):
        try:
            data = json.loads(text_data or "")
        except ValueError:
            return
        if not isinstance(data, dict):
            return
        try:
            if data.get("type") == "ping":
                await self.send(text_data=json.dumps({"type": "pong"}))
                await self.on_ping()
            else:
                await self.receive_message(data)
        except Exception:
            logger.exception("%s: error handling a message", type(self).__name__)
            await self.send(
                text_data=json.dumps(
                    {
                        "type": "error",
                        "error": "Something went wrong on our side. Try again.",
                        "code": "server_error",
                    }
                )
            )

    async def receive_message(self, data: dict):
        pass

    async def on_ping(self):
        pass

    async def reject(self, code: int):
        # Accept, then close: closing before accept() refuses the handshake, and
        # the browser only sees a generic 1006, never our code. With the code
        # it can tell "token expired" (refresh and retry) from "not allowed".
        await self.accept()
        await self.close(code=code)


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


class RoomChatConsumer(LiveConsumer):
    async def connect(self):
        slug = self.scope["url_route"]["kwargs"]["slug"]

        self.user = await database_sync_to_async(_authenticate_from_scope)(self.scope)
        if self.user is None:
            await self.reject(4001)
            return

        self.room = await self._get_room(slug)
        if self.room is None:
            await self.reject(4004)
            return

        if not await self._is_member():
            await self.reject(4003)
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

    async def receive_message(self, data):
        message_type = data.get("type", "text")

        # Text goes through the service, which emits MessageCreated.
        # Image/voice are handled by the REST upload endpoint, which also
        # emits MessageCreated — no WebSocket path needed here.
        if message_type == "text":
            content = data.get("content", "").strip()
            if not content:
                return
            await self._save_text(content)

        # Presence roll call: join/leave are only broadcast as they happen, so
        # a newcomer can't see who was already connected. Clients that are
        # already in the room answer a join with "here"; nothing is stored.
        elif message_type == "here":
            await self.channel_layer.group_send(
                self.group_name,
                {
                    "type": "presence_event",
                    "event": "here",
                    "username": self.user.username,
                    "display_name": self.user.display_name,
                },
            )

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
# Notification consumer — per-user channel, pushes unread badge updates and
# game invites. An open socket is also what counts someone as "online".
# ---------------------------------------------------------------------------


class NotificationConsumer(LiveConsumer):
    async def connect(self):
        self.user = await database_sync_to_async(_authenticate_from_scope)(self.scope)
        if self.user is None:
            await self.reject(4001)
            return

        self.group_name = f"user_{self.user.id}"
        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()
        await database_sync_to_async(PresenceService.connect)(self.user)

    async def disconnect(self, close_code):
        if hasattr(self, "group_name"):
            await self.channel_layer.group_discard(self.group_name, self.channel_name)
            await database_sync_to_async(PresenceService.disconnect)(self.user)

    async def on_ping(self):
        # The heartbeat is also what keeps this user listed as online.
        await database_sync_to_async(PresenceService.heartbeat)(self.user)

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

    # Games: forwarded as-is (see games/notify.py)
    async def game_invite(self, event):
        await self.send(text_data=json.dumps(event))

    async def game_invite_update(self, event):
        await self.send(text_data=json.dumps(event))

    async def match_found(self, event):
        await self.send(text_data=json.dumps(event))

    async def game_resume(self, event):
        await self.send(text_data=json.dumps(event))

    async def game_resume_cancel(self, event):
        await self.send(text_data=json.dumps(event))
