import pytest
from rest_framework.test import APIClient

from games.models import Game

pytestmark = pytest.mark.django_db


def _client(user):
    c = APIClient()
    c.force_authenticate(user)
    return c


def test_players_lists_who_is_online(alice, bob, carol, online):
    online(alice, bob)
    res = _client(alice).get("/api/games/players/")
    assert res.status_code == 200
    assert [p["username"] for p in res.json()] == ["bob"]
    assert res.json()[0]["stats"] == {"wins": 0, "losses": 0, "draws": 0}


def test_players_search_includes_offline_people(alice, bob, carol, online):
    online(bob)
    res = _client(alice).get("/api/games/players/", {"q": "o"})  # bob, carol
    names = [(p["username"], p["online"]) for p in res.json()]
    assert names == [("bob", True), ("carol", False)]


def test_challenge_offline_player_is_409(alice, bob):
    res = _client(alice).post(
        "/api/games/challenges/", {"username": "bob"}, format="json"
    )
    assert res.status_code == 409
    assert res.json()["code"] == "offline"


def test_challenge_accept_flow(alice, bob, online):
    online(alice, bob)
    res = _client(alice).post(
        "/api/games/challenges/", {"username": "bob"}, format="json"
    )
    assert res.status_code == 201
    game_id = res.json()["id"]

    me = _client(bob).get("/api/games/me/").json()
    assert [g["id"] for g in me["incoming"]] == [game_id]

    res = _client(bob).post(f"/api/games/{game_id}/accept/")
    assert res.status_code == 200
    assert res.json()["status"] == "active"
    assert res.json()["players"]["X"]["username"] == "alice"


def test_game_detail_is_players_only(alice, bob, carol):
    game = Game.objects.create(player_x=alice, player_o=bob, status=Game.Status.ACTIVE)
    assert _client(alice).get(f"/api/games/{game.id}/").status_code == 200
    assert _client(carol).get(f"/api/games/{game.id}/").status_code == 403


def test_bot_game_and_quick_match(alice, bob, online):
    res = _client(alice).post("/api/games/bot/", {"level": "hard"}, format="json")
    assert res.status_code == 201
    assert res.json()["players"]["O"]["is_bot"]

    online(alice, bob)
    assert _client(alice).post("/api/games/quick-match/").status_code == 202
    res = _client(bob).post("/api/games/quick-match/")
    assert res.status_code == 200
    assert res.json()["status"] == "matched"


def test_public_profile_includes_record(alice, bob):
    res = _client(alice).get("/api/auth/users/bob/")
    assert res.json()["game_stats"] == {"wins": 0, "losses": 0, "draws": 0}
