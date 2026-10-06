import pytest
from asgiref.sync import async_to_sync
from channels.routing import URLRouter
from channels.testing import WebsocketCommunicator
from rest_framework_simplejwt.tokens import AccessToken

from chat.models import RoomMembership
from chat.routing import websocket_urlpatterns


def _connect_as(user, room):
    token = str(AccessToken.for_user(user))
    return WebsocketCommunicator(
        URLRouter(websocket_urlpatterns), f"/ws/chat/{room.slug}/?token={token}"
    )


async def _next_presence(comm, event):
    while True:
        msg = await comm.receive_json_from(timeout=2)
        if msg.get("type") == "presence_event" and msg.get("event") == event:
            return msg


@pytest.mark.django_db(transaction=True)
def test_here_roll_call_tells_newcomer_who_is_present(room, user, other_user):
    RoomMembership.objects.create(user=other_user, room=room)

    async def scenario():
        alice = _connect_as(user, room)
        assert (await alice.connect())[0]
        await _next_presence(alice, "join")  # her own join

        bob = _connect_as(other_user, room)
        assert (await bob.connect())[0]
        joined = await _next_presence(alice, "join")
        assert joined["username"] == "bob"

        # Alice answers Bob's arrival; Bob learns she was already here.
        await alice.send_json_to({"type": "here"})
        here = await _next_presence(bob, "here")
        assert here["username"] == "alice"
        assert here["display_name"] == "Alice"

        await alice.disconnect()
        await bob.disconnect()

    async_to_sync(scenario)()


@pytest.mark.django_db(transaction=True)
def test_here_is_not_persisted_as_a_message(room, user):
    async def scenario():
        alice = _connect_as(user, room)
        assert (await alice.connect())[0]
        await alice.send_json_to({"type": "here"})
        await _next_presence(alice, "here")
        await alice.disconnect()

    async_to_sync(scenario)()
    assert room.messages.count() == 0
