from datetime import timedelta

import pytest
from django.utils import timezone

from games.models import Game, MatchQueueEntry, UserPresence
from games.services import (
    GameError,
    GameService,
    MatchmakingService,
    PresenceService,
)

pytestmark = pytest.mark.django_db


def _active(x, o):
    return Game.objects.create(player_x=x, player_o=o, status=Game.Status.ACTIVE)


def _play(game, moves):
    """Alternate X/O moves by index."""
    players = [game.player_x, game.player_o]
    for n, i in enumerate(moves):
        game = GameService.move(game.id, players[n % 2], i)
    return game


def _code(fn, *args):
    with pytest.raises(GameError) as exc:
        fn(*args)
    return exc.value.code


# -- Presence ----------------------------------------------------------------


def test_presence_counts_connections(alice):
    PresenceService.connect(alice)
    PresenceService.connect(alice)
    assert PresenceService.disconnect(alice) is True
    assert PresenceService.disconnect(alice) is False
    assert not PresenceService.is_online(alice)


def test_stale_presence_is_offline_and_resets_on_connect(alice):
    PresenceService.connect(alice)
    PresenceService.connect(alice)
    UserPresence.objects.update(last_seen=timezone.now() - timedelta(minutes=5))
    assert not PresenceService.is_online(alice)

    PresenceService.connect(alice)
    assert UserPresence.objects.get(user=alice).connections == 1


def test_going_offline_leaves_the_queue(alice, online):
    online(alice)
    MatchmakingService.join(alice)
    PresenceService.disconnect(alice)
    assert not MatchmakingService.is_queued(alice)


# -- Moves -------------------------------------------------------------------


def test_win_is_recorded(alice, bob):
    game = _play(_active(alice, bob), [0, 3, 1, 4, 2])
    assert game.status == Game.Status.FINISHED
    assert game.result == Game.Result.X_WINS
    assert game.winning_line == (0, 1, 2)
    assert game.finished_at is not None


def test_draw_is_recorded(alice, bob):
    #  X O X
    #  X O O
    #  O X X
    game = _play(_active(alice, bob), [0, 1, 2, 4, 3, 5, 7, 6, 8])
    assert game.result == Game.Result.DRAW
    assert game.winning_line is None


def test_turn_order_is_enforced(alice, bob):
    game = _active(alice, bob)
    assert _code(GameService.move, game.id, bob, 0) == "not_your_turn"
    GameService.move(game.id, alice, 0)
    assert _code(GameService.move, game.id, alice, 1) == "not_your_turn"


def test_taken_square_and_bad_index_are_rejected(alice, bob):
    game = _active(alice, bob)
    GameService.move(game.id, alice, 4)
    assert _code(GameService.move, game.id, bob, 4) == "occupied"
    assert _code(GameService.move, game.id, bob, 9) == "invalid_move"
    assert _code(GameService.move, game.id, bob, "x") == "invalid_move"


def test_outsiders_cannot_move(alice, bob, carol):
    game = _active(alice, bob)
    assert _code(GameService.move, game.id, carol, 0) == "forbidden"


def test_no_moves_after_the_game_ends(alice, bob):
    game = _play(_active(alice, bob), [0, 3, 1, 4, 2])
    assert _code(GameService.move, game.id, bob, 8) == "not_active"


def test_resign_gives_the_opponent_the_win(alice, bob):
    game = _active(alice, bob)
    game = GameService.resign(game.id, alice)
    assert game.result == Game.Result.O_WINS
    assert game.resigned
    assert game.winning_line is None


# -- Challenges --------------------------------------------------------------


def test_challenge_rules(alice, bob, online):
    assert _code(GameService.challenge, alice, "alice") == "self_challenge"
    assert _code(GameService.challenge, alice, "nobody") == "not_found"
    assert _code(GameService.challenge, alice, "bob") == "offline"

    online(bob)
    game = GameService.challenge(alice, "@Bob")
    assert game.status == Game.Status.PENDING
    assert game.player_x == alice and game.player_o == bob
    assert _code(GameService.challenge, alice, "bob") == "already_playing"
    online(alice)
    assert _code(GameService.challenge, bob, "alice") == "already_playing"


def test_only_the_challenged_player_accepts(alice, bob, carol, online):
    online(bob)
    game = GameService.challenge(alice, "bob")
    assert _code(GameService.accept, game.id, alice) == "forbidden"
    assert _code(GameService.accept, game.id, carol) == "forbidden"
    assert GameService.accept(game.id, bob).status == Game.Status.ACTIVE
    assert _code(GameService.accept, game.id, bob) == "not_pending"


def test_decline_and_cancel(alice, bob, online):
    online(bob)
    game = GameService.challenge(alice, "bob")
    assert _code(GameService.cancel, game.id, bob) == "forbidden"
    assert GameService.decline(game.id, bob).status == Game.Status.DECLINED

    game = GameService.challenge(alice, "bob")
    assert GameService.cancel(game.id, alice).status == Game.Status.CANCELLED


def test_old_challenges_expire(alice, bob, online):
    online(bob)
    game = GameService.challenge(alice, "bob")
    Game.objects.filter(pk=game.pk).update(
        created_at=timezone.now() - timedelta(minutes=5)
    )
    assert _code(GameService.accept, game.id, bob) == "not_pending"


# -- Bot ---------------------------------------------------------------------


def test_bot_game_plays_o_after_the_human(alice):
    game = GameService.play_bot(alice, "hard")
    assert game.vs_bot and game.status == Game.Status.ACTIVE
    game = GameService.move(game.id, alice, 0)
    assert _code(GameService.move, game.id, alice, 1) == "not_your_turn"
    game = GameService.bot_move(game.id)
    assert game.board.count("O") == 1
    assert GameService.bot_move(game.id) is None  # not the bot's turn


def test_bot_level_is_validated(alice):
    assert _code(GameService.play_bot, alice, "impossible") == "invalid_level"


def test_rematch(alice, bob, online):
    game = GameService.resign(GameService.play_bot(alice, "easy").id, alice)
    again = GameService.rematch(game.id, alice)
    assert again.vs_bot and again.bot_level == "easy" and again.pk != game.pk

    online(alice, bob)
    game = GameService.resign(_active(alice, bob).id, bob)
    again = GameService.rematch(game.id, bob)
    assert again.status == Game.Status.PENDING
    assert again.player_x == bob and again.player_o == alice


# -- Quick match -------------------------------------------------------------


def test_quick_match_pairs_two_waiting_players(alice, bob, online):
    online(alice, bob)
    assert MatchmakingService.join(alice) is None
    assert MatchmakingService.is_queued(alice)

    game = MatchmakingService.join(bob)
    assert game.status == Game.Status.ACTIVE
    assert {game.player_x, game.player_o} == {alice, bob}
    assert MatchQueueEntry.objects.count() == 0


def test_quick_match_skips_people_who_went_offline(alice, bob, online):
    online(alice, bob)
    MatchmakingService.join(alice)
    UserPresence.objects.filter(user=alice).update(connections=0)
    assert MatchmakingService.join(bob) is None
    assert not MatchmakingService.is_queued(alice)


# -- Records -----------------------------------------------------------------


def test_stats_count_human_games_only(alice, bob):
    _play(_active(alice, bob), [0, 3, 1, 4, 2])  # alice (X) wins
    _play(_active(bob, alice), [0, 3, 1, 4, 2])  # bob (X) wins
    _play(_active(alice, bob), [0, 1, 2, 4, 3, 5, 7, 6, 8])  # draw
    GameService.resign(GameService.play_bot(alice, "easy").id, alice)  # bot win

    assert GameService.stats(alice) == {"wins": 1, "losses": 1, "draws": 1}
    assert GameService.stats(bob) == {"wins": 1, "losses": 1, "draws": 1}
    assert GameService.stats(alice, vs_bot=True) == {"wins": 0, "losses": 1, "draws": 0}


def test_lobby_records_match_stats(alice, bob):
    """The lobby gets both records from one query; they must agree with stats()."""
    _play(_active(alice, bob), [0, 3, 1, 4, 2])  # alice (X) wins
    _play(_active(bob, alice), [0, 3, 1, 4, 2])  # bob (X) wins
    _play(_active(bob, alice), [0, 3, 1, 4, 2])  # bob (X) wins again
    _play(_active(alice, bob), [0, 1, 2, 4, 3, 5, 7, 6, 8])  # draw
    GameService.resign(_active(bob, alice).id, bob)  # bob resigns: alice wins
    GameService.resign(GameService.play_bot(alice, "easy").id, alice)  # bot win
    _play(_active(alice, bob), [0])  # still active: not counted

    for user in (alice, bob):
        overview = GameService.overview(user)
        assert overview["stats"] == GameService.stats(user)
        assert overview["bot_stats"] == GameService.stats(user, vs_bot=True)
    assert GameService.overview(alice)["stats"] == {"wins": 2, "losses": 2, "draws": 1}
    assert GameService.overview(alice)["bot_stats"] == {
        "wins": 0,
        "losses": 1,
        "draws": 0,
    }
