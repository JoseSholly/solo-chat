import pytest
from asgiref.sync import async_to_sync
from channels.db import database_sync_to_async
from channels.routing import URLRouter
from channels.testing import WebsocketCommunicator
from rest_framework_simplejwt.tokens import AccessToken

from chat.routing import websocket_urlpatterns
from games.models import Game
from games.services import GameService, PresenceService


def _ws(user, path):
    token = str(AccessToken.for_user(user))
    return WebsocketCommunicator(
        URLRouter(websocket_urlpatterns), f"{path}?token={token}"
    )


async def _next(comm, kind):
    while True:
        msg = await comm.receive_json_from(timeout=3)
        if msg.get("type") == kind:
            return msg


@pytest.mark.django_db(transaction=True)
def test_two_players_play_to_a_win(alice, bob):
    game = Game.objects.create(player_x=alice, player_o=bob, status=Game.Status.ACTIVE)
    path = f"/ws/games/{game.id}/"

    async def scenario():
        a, b = _ws(alice, path), _ws(bob, path)
        assert (await a.connect())[0]
        assert (await _next(a, "game_state"))["game"]["next"] == "X"
        assert (await b.connect())[0]
        await _next(b, "game_state")

        # Out of turn: only the sender hears about it.
        await b.send_json_to({"type": "move", "index": 0})
        assert (await _next(b, "error"))["code"] == "not_your_turn"

        for player, index in [(a, 0), (b, 3), (a, 1), (b, 4), (a, 2)]:
            await player.send_json_to({"type": "move", "index": index})
            state = (await _next(a, "game_state"))["game"]
            assert state["board"][index] in "XO"

        assert state["status"] == "finished"
        assert state["result"] == "x"
        assert state["winning_line"] == [0, 1, 2]
        await a.disconnect()
        await b.disconnect()

    async_to_sync(scenario)()


@pytest.mark.django_db(transaction=True)
def test_outsider_is_rejected(alice, bob, carol):
    game = Game.objects.create(player_x=alice, player_o=bob, status=Game.Status.ACTIVE)

    async def scenario():
        c = _ws(carol, f"/ws/games/{game.id}/")
        connected, code = await c.connect()
        assert not connected and code == 4003

    async_to_sync(scenario)()


@pytest.mark.django_db(transaction=True)
def test_bot_answers_a_move(alice):
    game = GameService.play_bot(alice, "hard")

    async def scenario():
        a = _ws(alice, f"/ws/games/{game.id}/")
        assert (await a.connect())[0]
        await _next(a, "game_state")
        await a.send_json_to({"type": "move", "index": 4})
        after_human = (await _next(a, "game_state"))["game"]
        assert after_human["next"] == "O"
        after_bot = (await _next(a, "game_state"))["game"]
        assert after_bot["board"].count("O") == 1
        assert after_bot["next"] == "X"
        assert after_bot["players"]["O"]["is_bot"] is True
        await a.disconnect()

    async_to_sync(scenario)()


@pytest.mark.django_db(transaction=True)
def test_notification_socket_tracks_presence_and_delivers_invites(alice, bob):
    async def scenario():
        b = _ws(bob, "/ws/notifications/")
        assert (await b.connect())[0]
        await b.send_json_to({"type": "ping"})
        await b.receive_nothing(timeout=0.2)

        game = await database_sync_to_async(GameService.challenge)(alice, "bob")
        invite = await _next(b, "game_invite")
        assert invite["game_id"] == str(game.id)
        assert invite["from_user"]["username"] == "alice"

        await b.disconnect()

    async_to_sync(scenario)()
    assert not PresenceService.is_online(bob)
