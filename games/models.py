import uuid

from django.conf import settings
from django.db import models

from .logic import NEW_BOARD, O, X, winning_line


class UserPresence(models.Model):
    """Who is online right now, counted by open notification sockets.

    `last_seen` is refreshed by a client heartbeat; a stale row (a worker that
    died without running disconnect) stops counting as online on its own.
    """

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="presence"
    )
    connections = models.PositiveIntegerField(default=0)
    last_seen = models.DateTimeField()

    def __str__(self):
        return f"{self.user} ({self.connections})"


class Game(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "Pending"  # a challenge waiting for an answer
        ACTIVE = "active", "Active"
        FINISHED = "finished", "Finished"
        DECLINED = "declined", "Declined"
        CANCELLED = "cancelled", "Cancelled"

    class Result(models.TextChoices):
        X_WINS = "x", "X wins"
        O_WINS = "o", "O wins"
        DRAW = "draw", "Draw"

    class BotLevel(models.TextChoices):
        EASY = "easy", "Easy"
        MEDIUM = "medium", "Medium"
        HARD = "hard", "Hard"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    player_x = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="games_as_x"
    )
    # Empty for games against the bot: the bot always plays O.
    player_o = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="games_as_o",
    )
    vs_bot = models.BooleanField(default=False)
    bot_level = models.CharField(
        max_length=10, choices=BotLevel.choices, blank=True, default=""
    )
    board = models.CharField(max_length=9, default=NEW_BOARD)
    last_move = models.PositiveSmallIntegerField(null=True, blank=True)
    status = models.CharField(
        max_length=10, choices=Status.choices, default=Status.PENDING
    )
    result = models.CharField(
        max_length=4, choices=Result.choices, blank=True, default=""
    )
    resigned = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    finished_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["status", "finished_at"])]

    def __str__(self):
        o = f"bot ({self.bot_level})" if self.vs_bot else self.player_o
        return f"{self.player_x} vs {o} [{self.status}]"

    def symbol_of(self, user) -> str | None:
        if user is None:
            return None
        if self.player_x_id == user.id:
            return X
        if self.player_o_id == user.id:
            return O
        return None

    def player(self, symbol: str):
        return self.player_x if symbol == X else self.player_o

    def opponent_of(self, user):
        return self.player_o if self.player_x_id == user.id else self.player_x

    def is_player(self, user) -> bool:
        return self.symbol_of(user) is not None

    @property
    def winning_line(self):
        if (
            self.result in (self.Result.X_WINS, self.Result.O_WINS)
            and not self.resigned
        ):
            return winning_line(self.board)
        return None


class MatchQueueEntry(models.Model):
    """A player waiting for Quick match."""

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="match_queue"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]
