"""The busiest endpoints must not run more queries as data grows (no N+1).

Each test measures an endpoint with a little data, adds more of the same, and
checks the query count didn't change. Every query is a round trip to the
database, which in production is in another city.
"""

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext
from rest_framework.test import APIClient

from chat.models import Message, Room, RoomMembership
from games.models import Game
from games.services import PresenceService

pytestmark = pytest.mark.django_db


def _queries(client, url):
    with CaptureQueriesContext(connection) as ctx:
        res = client.get(url)
    assert res.status_code == 200, res.content
    return len(ctx.captured_queries)


def _client(user):
    c = APIClient()
    c.force_authenticate(user)
    return c


def _people(django_user_model, prefix, n):
    return [
        django_user_model.objects.create_user(
            email=f"{prefix}{i}@example.com",
            username=f"{prefix}{i}",
            display_name=f"{prefix.title()} {i}",
            password="pw",
        )
        for i in range(n)
    ]


def _room_with(owner, name, members, messages):
    room = Room.objects.create(name=name, creator=owner)
    RoomMembership.objects.create(user=owner, room=room)
    for m in members:
        RoomMembership.objects.create(user=m, room=room)
    for i in range(messages):
        sender = members[i % len(members)] if members else owner
        Message.objects.create(
            room=room, sender=sender, username=sender.username, content=f"m{i}"
        )
    return room


def test_dashboard_queries_do_not_grow_with_rooms(user, django_user_model):
    people = _people(django_user_model, "p", 3)
    _room_with(user, "one", people, 3)
    before = _queries(_client(user), "/api/dashboard/")
    for i in range(5):
        _room_with(user, f"more{i}", people, 4)
    assert _queries(_client(user), "/api/dashboard/") == before


def test_room_detail_queries_do_not_grow_with_messages(user, django_user_model):
    people = _people(django_user_model, "p", 2)
    room = _room_with(user, "talk", people, 2)
    url = f"/api/rooms/{room.slug}/"
    before = _queries(_client(user), url)
    more = _people(django_user_model, "q", 6)
    for m in more:
        RoomMembership.objects.create(user=m, room=room)
        Message.objects.create(room=room, sender=m, username=m.username, content="x")
    assert _queries(_client(user), url) == before


def test_room_members_queries_do_not_grow_with_members(user, django_user_model):
    room = _room_with(user, "crowd", _people(django_user_model, "p", 2), 0)
    url = f"/api/rooms/{room.slug}/members/"
    before = _queries(_client(user), url)
    for m in _people(django_user_model, "q", 8):
        RoomMembership.objects.create(user=m, room=room)
    assert _queries(_client(user), url) == before


def test_games_lobby_queries_do_not_grow_with_players_or_games(user, django_user_model):
    def play(n, prefix):
        people = _people(django_user_model, prefix, n)
        for p in people:
            PresenceService.connect(p)
            Game.objects.create(
                player_x=user,
                player_o=p,
                status=Game.Status.FINISHED,
                result=Game.Result.X_WINS,
            )
        return people

    PresenceService.connect(user)
    play(2, "a")
    me, players = (
        _queries(_client(user), "/api/games/me/"),
        _queries(_client(user), "/api/games/players/"),
    )
    play(6, "b")
    assert _queries(_client(user), "/api/games/me/") == me
    assert _queries(_client(user), "/api/games/players/") == players


def test_responses_carry_server_timing(user):
    res = _client(user).get("/api/dashboard/")
    timing = res["Server-Timing"]
    assert timing.startswith("app;dur=")
    assert "db;dur=" in timing and 'queries"' in timing


def test_hot_endpoints_stay_within_their_query_budget(user, django_user_model):
    """Each query is a round trip (~100 ms to a far-away database). These are
    the budgets the endpoints were brought down to; the authenticated user
    comes from the cache, so it isn't counted here."""
    from games.services import MatchmakingService

    people = _people(django_user_model, "p", 3)
    room = _room_with(user, "budget", people, 4)
    PresenceService.connect(user)
    for p in people:
        PresenceService.connect(p)
    c = _client(user)

    budgets = {
        "/api/dashboard/": 2,
        f"/api/rooms/{room.slug}/": 3,
        f"/api/rooms/{room.slug}/members/": 2,
        "/api/games/me/": 3,
        "/api/games/players/": 2,
    }
    for url, budget in budgets.items():
        assert _queries(c, url) <= budget, url

    with CaptureQueriesContext(connection) as ctx:
        assert c.post("/api/games/quick-match/").status_code == 202
    assert len(ctx.captured_queries) <= 3  # waiting: candidates, enqueue, count
    with CaptureQueriesContext(connection) as ctx:
        assert c.delete("/api/games/quick-match/").status_code == 204
    assert len(ctx.captured_queries) == 1
    assert not MatchmakingService.is_queued(user)
