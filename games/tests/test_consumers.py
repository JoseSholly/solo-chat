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
def test_leaving_on_purpose_lets_the_other_player_claim_the_win(alice, bob, online):
    online(alice, bob)
    game = Game.objects.create(player_x=alice, player_o=bob, status=Game.Status.ACTIVE)
    path = f"/ws/games/{game.id}/"

    async def scenario():
        a, b = _ws(alice, path), _ws(bob, path)
        assert (await a.connect())[0]
        assert (await b.connect())[0]
        assert (await _next(b, "opponent"))["here"] is True

        await b.send_json_to({"type": "leave"})
        await b.disconnect()
        gone = await _next(a, "player_presence")
        while gone["event"] != "leave":
            gone = await _next(a, "player_presence")
        assert gone["left"] is True and gone["claim_in"] == 0

        await a.send_json_to({"type": "claim"})
        state = (await _next(a, "game_state"))["game"]
        assert state["status"] == "finished"
        assert state["result"] == "x"
        assert state["abandoned"] is True
        await a.disconnect()

    async_to_sync(scenario)()


@pytest.mark.django_db(transaction=True)
def test_dropped_connection_gets_a_grace_period(alice, bob, online):
    online(alice, bob)
    game = Game.objects.create(player_x=alice, player_o=bob, status=Game.Status.ACTIVE)
    path = f"/ws/games/{game.id}/"

    async def scenario():
        a, b = _ws(alice, path), _ws(bob, path)
        assert (await a.connect())[0]
        assert (await b.connect())[0]
        await b.disconnect()
        gone = await _next(a, "player_presence")
        while gone["event"] != "leave":
            gone = await _next(a, "player_presence")
        assert gone["left"] is False and gone["claim_in"] == 30

        await a.send_json_to({"type": "claim"})
        assert (await _next(a, "error"))["code"] == "too_soon"
        await a.disconnect()

    async_to_sync(scenario)()


@pytest.mark.django_db(transaction=True)
def test_resuming_asks_the_other_player_to_come_back(alice, bob):
    game = Game.objects.create(player_x=alice, player_o=bob, status=Game.Status.ACTIVE)
    path = f"/ws/games/{game.id}/"

    async def scenario():
        bn = _ws(bob, "/ws/notifications/")
        assert (await bn.connect())[0]
        await bn.receive_nothing(timeout=0.2)  # let the presence row be written
        # Bob played earlier, then went elsewhere in the app.
        b = _ws(bob, path)
        assert (await b.connect())[0]
        await b.send_json_to({"type": "leave"})
        await b.disconnect()

        a = _ws(alice, path)
        assert (await a.connect())[0]
        status = await _next(a, "opponent")
        assert status["notified"] is True and status["here"] is False

        resume = await _next(bn, "game_resume")
        assert resume["game_id"] == str(game.id)
        assert resume["from_user"]["username"] == "alice"

        # Bob says "Not now": Alice can claim straight away.
        await database_sync_to_async(GameService.not_now)(game.id, bob)
        busy = await _next(a, "player_presence")
        while busy["event"] != "busy":
            busy = await _next(a, "player_presence")
        assert busy["claim_in"] == 0

        await a.disconnect()
        await bn.disconnect()

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


@pytest.mark.django_db(transaction=True)
def test_unexpected_error_is_reported_without_dropping_the_socket(alice, monkeypatch):
    game = GameService.play_bot(alice, "easy")

    def boom(*args):
        raise RuntimeError("database fell over")

    monkeypatch.setattr(GameService, "move", staticmethod(boom))

    async def scenario():
        a = _ws(alice, f"/ws/games/{game.id}/")
        assert (await a.connect())[0]
        await _next(a, "game_state")
        await a.send_json_to({"type": "move", "index": 0})
        assert (await _next(a, "error"))["code"] == "server_error"
        # Still connected: the next frame is answered, not refused.
        await a.send_json_to({"type": "here"})
        await _next(a, "player_presence")
        await a.disconnect()

    async_to_sync(scenario)()
