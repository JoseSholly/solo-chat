"""Plain-dict shapes shared by the REST views and the WebSocket consumer.

Nothing here depends on who is asking, so one payload can be broadcast to
both players; the client works out its own symbol from `players`.
"""

from .logic import NEW_BOARD, O, X, next_symbol


def _avatar_url(user, request=None):
    if not user.avatar:
        return None
    return request.build_absolute_uri(user.avatar.url) if request else user.avatar.url


def user_brief(user, request=None) -> dict:
    return {
        "username": user.username,
        "display_name": user.display_name,
        "avatar_url": _avatar_url(user, request),
        "is_bot": False,
    }


def bot_brief(level: str) -> dict:
    return {
        "username": None,
        "display_name": f"Bot · {level.capitalize()}" if level else "Bot",
        "avatar_url": None,
        "is_bot": True,
    }


def game_state(game, request=None) -> dict:
    active = game.status == game.Status.ACTIVE
    line = game.winning_line
    return {
        "id": str(game.id),
        "status": game.status,
        "board": game.board or NEW_BOARD,
        "next": next_symbol(game.board) if active else None,
        "result": game.result or None,
        "resigned": game.resigned,
        "winning_line": list(line) if line else None,
        "last_move": game.last_move,
        "vs_bot": game.vs_bot,
        "bot_level": game.bot_level or None,
        "players": {
            X: user_brief(game.player_x, request),
            O: bot_brief(game.bot_level)
            if game.vs_bot
            else user_brief(game.player_o, request),
        },
        "created_at": game.created_at.isoformat(),
        "finished_at": game.finished_at.isoformat() if game.finished_at else None,
    }
