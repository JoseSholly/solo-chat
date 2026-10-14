import asyncio
import json
import logging

from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncWebsocketConsumer

from chat.consumers import _authenticate_from_scope

from .serializers import game_state
from .services import GameError, GameService, SeatService

logger = logging.getLogger(__name__)

BOT_THINK_SECONDS = 0.45  # long enough to read as a turn, short enough not to drag


class GameConsumer(AsyncWebsocketConsumer):
    """One socket per player per game. Moves, resigning and presence go
    through here; challenges and matchmaking are REST + notifications."""

    leaving = False  # the player said they're leaving, rather than dropping

    async def connect(self):
        self.game_id = str(self.scope["url_route"]["kwargs"]["game_id"])

        self.user = await database_sync_to_async(_authenticate_from_scope)(self.scope)
        if self.user is None:
            await self.close(code=4001)
            return

        game = await database_sync_to_async(GameService.get)(self.game_id)
        if game is None:
            await self.close(code=4004)
            return
        if not game.is_player(self.user):
            await self.close(code=4003)
            return

        self.group_name = f"game_{self.game_id}"
        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()

        await self.send_json({"type": "game_state", "game": game_state(game)})
        opponent = await database_sync_to_async(SeatService.join)(game, self.user)
        await self.send_json({"type": "opponent", **opponent})
        await self._presence("join")

        # The bot's turn may have been interrupted by a disconnect.
        await self._bot_turn()

    async def disconnect(self, close_code):
        if not hasattr(self, "group_name"):
            return
        await self.channel_layer.group_discard(self.group_name, self.channel_name)
        claim_in = await database_sync_to_async(SeatService.leave)(
            self.game_id, self.user, on_purpose=self.leaving
        )
        # Another tab of theirs is still on the board: nothing to announce.
        if claim_in is not None:
            await self._presence("leave", left=self.leaving, claim_in=claim_in)

    async def receive(self, text_data):
        try:
            data = json.loads(text_data)
        except ValueError:
            return
        kind = data.get("type")

        if kind == "move":
            if await self._run(
                GameService.move, self.game_id, self.user, data.get("index")
            ):
                await self._bot_turn(delay=True)
        elif kind == "resign":
            await self._run(GameService.resign, self.game_id, self.user)
        elif kind == "claim":
            await self._run(GameService.claim_win, self.game_id, self.user)
        elif kind == "leave":
            self.leaving = True
        elif kind == "here":
            await self._presence("here")

    # -- Group handlers -----------------------------------------------------

    async def game_update(self, event):
        await self.send_json({"type": "game_state", "game": event["game"]})

    async def player_presence(self, event):
        await self.send_json(event)

    # -- Helpers ------------------------------------------------------------

    async def send_json(self, payload):
        await self.send(text_data=json.dumps(payload))

    async def _broadcast(self, game):
        await self.channel_layer.group_send(
            self.group_name, {"type": "game_update", "game": game_state(game)}
        )

    async def _send_unexpected(self):
        # An unexpected server error is reported, not raised: raising closes the
        # socket, the browser reconnects, and the same error repeats in a loop.
        logger.exception("Game %s: unexpected error", self.game_id)
        await self.send_json(
            {
                "type": "error",
                "error": "Something went wrong on our side. Try again.",
                "code": "server_error",
            }
        )

    async def _run(self, method, *args) -> bool:
        try:
            game = await database_sync_to_async(method)(*args)
        except GameError as exc:
            await self.send_json(
                {"type": "error", "error": exc.message, "code": exc.code}
            )
            return False
        except Exception:
            await self._send_unexpected()
            return False
        await self._broadcast(game)
        return True

    async def _bot_turn(self, delay: bool = False):
        try:
            game = await database_sync_to_async(GameService.get)(self.game_id)
            if game is None or not game.vs_bot:
                return
            if delay:
                await asyncio.sleep(BOT_THINK_SECONDS)
            game = await database_sync_to_async(GameService.bot_move)(self.game_id)
        except Exception:
            await self._send_unexpected()
            return
        if game is not None:
            await self._broadcast(game)

    async def _presence(self, event, **extra):
        await self.channel_layer.group_send(
            self.group_name,
            {
                "type": "player_presence",
                "event": event,
                "username": self.user.username,
                "display_name": self.user.display_name,
                **extra,
            },
        )
