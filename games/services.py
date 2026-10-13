import random
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.db import transaction
from django.db.models import Case, Count, F, Q, When
from django.utils import timezone

from . import bot, notify
from .logic import O, X, empty_cells, is_full, next_symbol, other, place, winner
from .models import Game, GameSeat, MatchQueueEntry, UserPresence
from .serializers import user_brief

ONLINE_WINDOW = timedelta(seconds=90)  # clients heartbeat every 30s
CHALLENGE_TTL = timedelta(minutes=2)
# How long a dropped connection gets to come back before the other player
# may claim the win. Leaving on purpose or going offline skips the wait.
CLAIM_GRACE = timedelta(seconds=30)


class GameError(Exception):
    """A rule was broken. Carries the HTTP status the REST views answer with."""

    def __init__(self, message: str, code: str, status: int = 400, **extra):
        super().__init__(message)
        self.message = message
        self.code = code
        self.status = status
        self.extra = extra


# ---------------------------------------------------------------------------
# Presence
# ---------------------------------------------------------------------------


class PresenceService:
    @staticmethod
    def _cutoff():
        return timezone.now() - ONLINE_WINDOW

    @staticmethod
    def online_q(prefix: str = "") -> Q:
        return Q(
            **{
                f"{prefix}presence__connections__gt": 0,
                f"{prefix}presence__last_seen__gte": PresenceService._cutoff(),
            }
        )

    @staticmethod
    def connect(user) -> None:
        now = timezone.now()
        presence, created = UserPresence.objects.get_or_create(
            user=user, defaults={"connections": 1, "last_seen": now}
        )
        if created:
            return
        # A stale row means the count was left behind by a worker that died;
        # start over instead of adding to it.
        UserPresence.objects.filter(pk=presence.pk).update(
            connections=Case(
                When(last_seen__lt=PresenceService._cutoff(), then=1),
                default=F("connections") + 1,
            ),
            last_seen=now,
        )

    @staticmethod
    def disconnect(user) -> bool:
        """Returns whether the user still has another connection open."""
        UserPresence.objects.filter(user=user).update(
            connections=Case(
                When(connections__gt=0, then=F("connections") - 1), default=0
            )
        )
        still_online = PresenceService.is_online(user)
        if not still_online:
            MatchmakingService.leave(user)
        return still_online

    @staticmethod
    def heartbeat(user) -> None:
        UserPresence.objects.filter(user=user).update(last_seen=timezone.now())

    @staticmethod
    def is_online(user) -> bool:
        return (
            get_user_model()
            .objects.filter(PresenceService.online_q(), pk=user.pk)
            .exists()
        )

    @staticmethod
    def online_users(exclude=None, limit: int = 50):
        qs = get_user_model().objects.filter(PresenceService.online_q())
        if exclude is not None:
            qs = qs.exclude(pk=exclude.pk)
        return list(qs.order_by("display_name", "username")[:limit])


# ---------------------------------------------------------------------------
# Games
# ---------------------------------------------------------------------------


def _finish_if_over(game: Game) -> None:
    w = winner(game.board)
    if w is not None:
        game.result = Game.Result.X_WINS if w == X else Game.Result.O_WINS
    elif is_full(game.board):
        game.result = Game.Result.DRAW
    else:
        return
    game.status = Game.Status.FINISHED
    game.finished_at = timezone.now()


def _locked(game_id) -> Game:
    try:
        return (
            Game.objects.select_for_update()
            .select_related("player_x", "player_o")
            .get(pk=game_id)
        )
    except (Game.DoesNotExist, ValueError):
        raise GameError("Game not found.", "not_found", 404)


class GameService:
    @staticmethod
    def get(game_id) -> Game | None:
        try:
            return Game.objects.select_related("player_x", "player_o").get(pk=game_id)
        except (Game.DoesNotExist, ValueError):
            return None

    @staticmethod
    def expire_challenges() -> None:
        Game.objects.filter(
            status=Game.Status.PENDING, created_at__lt=timezone.now() - CHALLENGE_TTL
        ).update(status=Game.Status.CANCELLED)

    @staticmethod
    def live_game_between(a, b) -> Game | None:
        return (
            Game.objects.filter(
                Q(player_x=a, player_o=b) | Q(player_x=b, player_o=a),
                status__in=[Game.Status.PENDING, Game.Status.ACTIVE],
            )
            .order_by("-created_at")
            .first()
        )

    # -- Challenges ---------------------------------------------------------

    @staticmethod
    def challenge(challenger, username: str) -> Game:
        User = get_user_model()
        username = (username or "").strip().lstrip("@")
        if not username:
            raise GameError("Who do you want to play?", "missing_username")
        try:
            opponent = User.objects.get(username__iexact=username)
        except User.DoesNotExist:
            raise GameError("No one goes by that username.", "not_found", 404)
        if opponent.pk == challenger.pk:
            raise GameError("You can't challenge yourself.", "self_challenge")
        if not PresenceService.is_online(opponent):
            raise GameError(
                f"{opponent.display_name} isn't online right now.", "offline", 409
            )

        GameService.expire_challenges()
        existing = GameService.live_game_between(challenger, opponent)
        if existing is not None:
            raise GameError(
                f"You already have a game with {opponent.display_name}.",
                "already_playing",
                409,
                game_id=str(existing.id),
                game_status=existing.status,
            )

        game = Game.objects.create(player_x=challenger, player_o=opponent)
        notify.to_user(
            opponent.id,
            "game_invite",
            game_id=str(game.id),
            from_user=user_brief(challenger),
        )
        return game

    @staticmethod
    def _respond(game_id, user, *, as_symbol: str, new_status: str) -> Game:
        GameService.expire_challenges()
        with transaction.atomic():
            game = _locked(game_id)
            if game.vs_bot or game.symbol_of(user) != as_symbol:
                raise GameError(
                    "This challenge isn't yours to answer.", "forbidden", 403
                )
            if game.status != Game.Status.PENDING:
                raise GameError(
                    "This challenge is no longer open.",
                    "not_pending",
                    410,
                    game_status=game.status,
                )
            game.status = new_status
            game.save(update_fields=["status", "updated_at"])
        return game

    @staticmethod
    def accept(game_id, user) -> Game:
        game = GameService._respond(
            game_id, user, as_symbol=O, new_status=Game.Status.ACTIVE
        )
        notify.to_user(
            game.player_x_id,
            "game_invite_update",
            game_id=str(game.id),
            status="accepted",
            by=user_brief(user),
        )
        return game

    @staticmethod
    def decline(game_id, user) -> Game:
        game = GameService._respond(
            game_id, user, as_symbol=O, new_status=Game.Status.DECLINED
        )
        notify.to_user(
            game.player_x_id,
            "game_invite_update",
            game_id=str(game.id),
            status="declined",
            by=user_brief(user),
        )
        return game

    @staticmethod
    def cancel(game_id, user) -> Game:
        game = GameService._respond(
            game_id, user, as_symbol=X, new_status=Game.Status.CANCELLED
        )
        notify.to_user(
            game.player_o_id,
            "game_invite_update",
            game_id=str(game.id),
            status="cancelled",
            by=user_brief(user),
        )
        return game

    # -- Bot ----------------------------------------------------------------

    @staticmethod
    def play_bot(user, level: str) -> Game:
        if level not in bot.LEVELS:
            raise GameError("Pick easy, medium or hard.", "invalid_level")
        MatchmakingService.leave(user)
        return Game.objects.create(
            player_x=user,
            vs_bot=True,
            bot_level=level,
            status=Game.Status.ACTIVE,
        )

    @staticmethod
    def bot_move(game_id) -> Game | None:
        """Play the bot's turn, if it is the bot's turn. Returns the game if it moved."""
        with transaction.atomic():
            game = _locked(game_id)
            if (
                not game.vs_bot
                or game.status != Game.Status.ACTIVE
                or next_symbol(game.board) != O
            ):
                return None
            index = bot.choose_move(game.board, O, game.bot_level)
            game.board = place(game.board, index, O)
            game.last_move = index
            _finish_if_over(game)
            game.save()
        return game

    # -- Play ---------------------------------------------------------------

    @staticmethod
    def move(game_id, user, index) -> Game:
        try:
            index = int(index)
        except (TypeError, ValueError):
            raise GameError("Pick a square from 0 to 8.", "invalid_move")
        if not 0 <= index <= 8:
            raise GameError("Pick a square from 0 to 8.", "invalid_move")

        with transaction.atomic():
            game = _locked(game_id)
            symbol = game.symbol_of(user)
            if symbol is None:
                raise GameError("You're not in this game.", "forbidden", 403)
            if game.status != Game.Status.ACTIVE:
                raise GameError("This game isn't being played.", "not_active", 409)
            if next_symbol(game.board) != symbol:
                raise GameError("It's not your turn.", "not_your_turn", 409)
            if index not in empty_cells(game.board):
                raise GameError("That square is taken.", "occupied", 409)

            game.board = place(game.board, index, symbol)
            game.last_move = index
            _finish_if_over(game)
            game.save()
        return game

    @staticmethod
    def resign(game_id, user) -> Game:
        with transaction.atomic():
            game = _locked(game_id)
            symbol = game.symbol_of(user)
            if symbol is None:
                raise GameError("You're not in this game.", "forbidden", 403)
            if game.status != Game.Status.ACTIVE:
                raise GameError("This game isn't being played.", "not_active", 409)
            game.result = (
                Game.Result.X_WINS if other(symbol) == X else Game.Result.O_WINS
            )
            game.resigned = True
            game.status = Game.Status.FINISHED
            game.finished_at = timezone.now()
            game.save()
        return game

    @staticmethod
    def claim_win(game_id, user) -> Game:
        """End the game in your favour because the other player left the board."""
        with transaction.atomic():
            game = _locked(game_id)
            symbol = game.symbol_of(user)
            if symbol is None:
                raise GameError("You're not in this game.", "forbidden", 403)
            if game.status != Game.Status.ACTIVE or game.vs_bot:
                raise GameError("This game isn't being played.", "not_active", 409)
            status = SeatService.opponent_status(game, user)
            if status["here"]:
                raise GameError("They're back. Play on!", "opponent_here", 409)
            if status["claim_in"] > 0:
                raise GameError("Give them a moment to reconnect.", "too_soon", 409)
            game.result = Game.Result.X_WINS if symbol == X else Game.Result.O_WINS
            game.abandoned = True
            game.status = Game.Status.FINISHED
            game.finished_at = timezone.now()
            game.save()
        return game

    @staticmethod
    def not_now(game_id, user) -> Game:
        """Answer a resume request with "Not now": the other player can claim
        the win instead of waiting."""
        game = GameService.get(game_id)
        if game is None:
            raise GameError("Game not found.", "not_found", 404)
        if not game.is_player(user):
            raise GameError("You're not in this game.", "forbidden", 403)
        if game.status != Game.Status.ACTIVE:
            raise GameError("This game isn't being played.", "not_active", 409)
        seat, _ = GameSeat.objects.get_or_create(game=game, user=user)
        if seat.connections == 0:
            GameSeat.objects.filter(pk=seat.pk).update(left=True)
            notify.to_game(
                game.id,
                "player_presence",
                event="busy",
                username=user.username,
                display_name=user.display_name,
                left=True,
                claim_in=0,
            )
        return game

    @staticmethod
    def rematch(game_id, user) -> Game:
        game = GameService.get(game_id)
        if game is None:
            raise GameError("Game not found.", "not_found", 404)
        if not game.is_player(user):
            raise GameError("You're not in this game.", "forbidden", 403)
        if game.status != Game.Status.FINISHED:
            raise GameError("Finish this game first.", "not_finished", 409)
        if game.vs_bot:
            return GameService.play_bot(user, game.bot_level)
        return GameService.challenge(user, game.opponent_of(user).username)

    # -- Records ------------------------------------------------------------

    @staticmethod
    def stats_for(users, vs_bot: bool = False) -> dict:
        """{user_id: {"wins", "losses", "draws"}} in two grouped queries."""
        ids = [u.pk for u in users]
        out = {uid: {"wins": 0, "losses": 0, "draws": 0} for uid in ids}
        if not ids:
            return out
        finished = Game.objects.filter(status=Game.Status.FINISHED, vs_bot=vs_bot)
        for field, mine in (
            ("player_x", Game.Result.X_WINS),
            ("player_o", Game.Result.O_WINS),
        ):
            rows = (
                finished.filter(**{f"{field}__in": ids})
                .values(field, "result")
                .annotate(n=Count("id"))
            )
            for row in rows:
                rec = out[row[field]]
                if row["result"] == Game.Result.DRAW:
                    rec["draws"] += row["n"]
                elif row["result"] == mine:
                    rec["wins"] += row["n"]
                else:
                    rec["losses"] += row["n"]
        return out

    @staticmethod
    def stats(user, vs_bot: bool = False) -> dict:
        return GameService.stats_for([user], vs_bot=vs_bot)[user.pk]

    @staticmethod
    def overview(user) -> dict:
        """Everything the lobby needs about the signed-in player, as models."""
        GameService.expire_challenges()
        mine = Game.objects.filter(Q(player_x=user) | Q(player_o=user)).select_related(
            "player_x", "player_o"
        )
        return {
            "stats": GameService.stats(user),
            "bot_stats": GameService.stats(user, vs_bot=True),
            "incoming": list(mine.filter(status=Game.Status.PENDING, player_o=user)),
            "outgoing": list(mine.filter(status=Game.Status.PENDING, player_x=user)),
            "active": list(mine.filter(status=Game.Status.ACTIVE)[:10]),
            "recent": list(
                mine.filter(status=Game.Status.FINISHED).order_by("-finished_at")[:10]
            ),
            "queued": MatchmakingService.is_queued(user),
        }


# ---------------------------------------------------------------------------
# Who is on the board
# ---------------------------------------------------------------------------


class SeatService:
    @staticmethod
    def join(game, user) -> dict:
        """Count a board socket in. Returns the opponent's status for the
        joiner, after telling an opponent who's online elsewhere in the app
        that this player is back."""
        seat, _ = GameSeat.objects.get_or_create(game=game, user=user)
        GameSeat.objects.filter(pk=seat.pk).update(
            connections=F("connections") + 1, away_since=None, left=False
        )
        if game.vs_bot or game.status != Game.Status.ACTIVE:
            return {"here": True, "online": True, "left": False, "claim_in": 0}

        status = SeatService.opponent_status(game, user)
        opponent = game.opponent_of(user)
        # Only an opponent who has been on this board before needs asking back:
        # a new game already reached them as a match or an accepted challenge.
        been_here = GameSeat.objects.filter(game=game, user=opponent).exists()
        status["notified"] = not status["here"] and status["online"] and been_here
        if status["notified"]:
            notify.to_user(
                opponent.id,
                "game_resume",
                game_id=str(game.id),
                from_user=user_brief(user),
            )
        return status

    @staticmethod
    def leave(game_id, user, on_purpose: bool = False) -> int | None:
        """Count a board socket out. When it was the player's last one, returns
        how many seconds until the other player may claim the win."""
        now = timezone.now()
        seats = GameSeat.objects.filter(game_id=game_id, user=user)
        seats.update(
            connections=Case(
                When(connections__gt=0, then=F("connections") - 1), default=0
            )
        )
        seat = seats.first()
        if seat is None or seat.connections > 0:
            return None
        seats.update(away_since=now, left=on_purpose)

        game = GameService.get(game_id)
        if game is None or game.vs_bot or game.status != Game.Status.ACTIVE:
            return None
        # Withdraw a resume request the opponent hasn't answered yet.
        notify.to_user(
            game.opponent_of(user).id, "game_resume_cancel", game_id=str(game_id)
        )
        if on_purpose or not PresenceService.is_online(user):
            return 0
        return int(CLAIM_GRACE.total_seconds())

    @staticmethod
    def opponent_status(game, user) -> dict:
        opponent = game.opponent_of(user)
        seat = GameSeat.objects.filter(game=game, user=opponent).first()
        online = PresenceService.is_online(opponent)
        here = online and seat is not None and seat.connections > 0
        left = bool(seat and seat.left)
        if here or left or not online:
            claim_in = 0
        else:
            since = (seat.away_since if seat else None) or game.updated_at
            remaining = CLAIM_GRACE - (timezone.now() - since)
            claim_in = max(0, int(remaining.total_seconds() + 0.999))
        return {"here": here, "online": online, "left": left, "claim_in": claim_in}


# ---------------------------------------------------------------------------
# Quick match
# ---------------------------------------------------------------------------


class MatchmakingService:
    @staticmethod
    def join(user) -> Game | None:
        """Pair with someone already waiting, or start waiting. Returns the new
        game when paired, None when now waiting."""
        game = None
        with transaction.atomic():
            # People who went away without leaving the queue can't be matched.
            MatchQueueEntry.objects.exclude(
                user__in=get_user_model().objects.filter(PresenceService.online_q())
            ).delete()

            candidates = (
                MatchQueueEntry.objects.exclude(user=user)
                .select_related("user")
                .order_by("created_at")[:5]
            )
            for entry in candidates:
                # Deleting the row is the claim: if another request got to it
                # first, nothing is deleted and we try the next one.
                if MatchQueueEntry.objects.filter(pk=entry.pk).delete()[0]:
                    MatchQueueEntry.objects.filter(user=user).delete()
                    x, o = random.sample([user, entry.user], 2)
                    game = Game.objects.create(
                        player_x=x, player_o=o, status=Game.Status.ACTIVE
                    )
                    break
            else:
                MatchQueueEntry.objects.get_or_create(user=user)

        if game is not None:
            for p in (game.player_x, game.player_o):
                notify.to_user(p.id, "match_found", game_id=str(game.id))
        return game

    @staticmethod
    def leave(user) -> None:
        MatchQueueEntry.objects.filter(user=user).delete()

    @staticmethod
    def is_queued(user) -> bool:
        return MatchQueueEntry.objects.filter(user=user).exists()
