"""Heartbeat and resilience shared by every authenticated socket (LiveConsumer)."""

from datetime import timedelta

import pytest
from asgiref.sync import async_to_sync
from channels.db import database_sync_to_async
from channels.routing import URLRouter
from channels.testing import WebsocketCommunicator
from django.utils import timezone
from rest_framework_simplejwt.tokens import AccessToken

from chat.models import RoomMembership
from chat.routing import websocket_urlpatterns
from chat.services import MessageService
from games.models import UserPresence
from games.services import GameService


def _ws(user, path):
    token = str(AccessToken.for_user(user))
    return WebsocketCommunicator(
        URLRouter(websocket_urlpatterns), f"{path}?token={token}"
    )


async def _drain(comm):
    """Skip join/presence/game frames sent on connect."""
    while not await comm.receive_nothing(timeout=0.2):
        await comm.receive_output()


def _paths(room, game):
    return [
        f"/ws/chat/{room.slug}/",
        "/ws/notifications/",
        f"/ws/games/{game.id}/",
    ]


@pytest.mark.django_db(transaction=True)
def test_every_socket_answers_ping_with_pong(room, user):
    game = GameService.play_bot(user, "easy")

    async def scenario():
        for path in _paths(room, game):
            comm = _ws(user, path)
            assert (await comm.connect())[0], path
            await _drain(comm)
            await comm.send_json_to({"type": "ping"})
            assert await comm.receive_json_from(timeout=2) == {"type": "pong"}, path
            await comm.disconnect()

    async_to_sync(scenario)()


@pytest.mark.django_db(transaction=True)
def test_malformed_frames_do_not_close_the_socket(room, user):
    game = GameService.play_bot(user, "easy")

    async def scenario():
        for path in _paths(room, game):
            comm = _ws(user, path)
            assert (await comm.connect())[0], path
            await _drain(comm)
            await comm.send_to(text_data="not json {")
            await comm.send_to(text_data="[1, 2, 3]")
            await comm.send_json_to({"type": "ping"})
            assert await comm.receive_json_from(timeout=2) == {"type": "pong"}, path
            await comm.disconnect()

    async_to_sync(scenario)()


@pytest.mark.django_db(transaction=True)
def test_room_handler_error_is_reported_and_socket_stays_open(room, user, monkeypatch):
    def boom(*args, **kwargs):
        raise RuntimeError("database fell over")

    monkeypatch.setattr(MessageService, "create_text", staticmethod(boom))

    async def scenario():
        comm = _ws(user, f"/ws/chat/{room.slug}/")
        assert (await comm.connect())[0]
        await _drain(comm)
        await comm.send_json_to({"type": "text", "content": "hello"})
        error = await comm.receive_json_from(timeout=2)
        assert error["type"] == "error" and error["code"] == "server_error"
        await comm.send_json_to({"type": "ping"})
        assert await comm.receive_json_from(timeout=2) == {"type": "pong"}
        await comm.disconnect()

    async_to_sync(scenario)()


@pytest.mark.django_db(transaction=True)
def test_notification_ping_keeps_presence_fresh(user):
    _set_stale = database_sync_to_async(
        lambda: UserPresence.objects.filter(user=user).update(
            last_seen=timezone.now() - timedelta(minutes=5)
        )
    )

    async def scenario():
        comm = _ws(user, "/ws/notifications/")
        assert (await comm.connect())[0]
        await _set_stale()
        await comm.send_json_to({"type": "ping"})
        assert await comm.receive_json_from(timeout=2) == {"type": "pong"}
        await comm.disconnect()

    stale_before = timezone.now() - timedelta(minutes=1)
    async_to_sync(scenario)()
    # Disconnect drops the connection count, but last_seen was refreshed by the ping.
    assert UserPresence.objects.get(user=user).last_seen > stale_before


@pytest.mark.django_db(transaction=True)
def test_room_message_still_works(room, user, other_user):
    RoomMembership.objects.create(user=other_user, room=room)

    async def scenario():
        comm = _ws(user, f"/ws/chat/{room.slug}/")
        assert (await comm.connect())[0]
        await _drain(comm)
        await comm.send_json_to({"type": "text", "content": "hi"})
        while True:
            msg = await comm.receive_json_from(timeout=2)
            if msg["type"] == "chat_message":
                assert msg["content"] == "hi"
                break
        await comm.disconnect()

    async_to_sync(scenario)()


@pytest.mark.django_db(transaction=True)
def test_refusals_reach_the_browser_as_close_codes(room, user, other_user):
    """Closing before accept() would refuse the handshake, and a browser would
    only see 1006. Accept-then-close delivers the code the client acts on."""
    game = GameService.play_bot(user, "easy")

    async def closed_with(path, token):
        comm = WebsocketCommunicator(
            URLRouter(websocket_urlpatterns), f"{path}?token={token}"
        )
        assert (await comm.connect())[0], path
        while True:
            out = await comm.receive_output(timeout=2)
            if out["type"] == "websocket.close":
                return out["code"]

    async def scenario():
        bad = "not-a-token"
        for path in _paths(room, game):
            assert await closed_with(path, bad) == 4001, path
        outsider = str(AccessToken.for_user(other_user))
        assert await closed_with(f"/ws/chat/{room.slug}/", outsider) == 4003
        assert await closed_with(f"/ws/games/{game.id}/", outsider) == 4003
        missing = "00000000-0000-0000-0000-000000000000"
        assert await closed_with(f"/ws/chat/{missing}/", outsider) == 4004
        assert await closed_with(f"/ws/games/{missing}/", outsider) == 4004

    async_to_sync(scenario)()
