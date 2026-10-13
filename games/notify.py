"""Pushes from game services to connected browsers.

`user_<id>` is the per-user group joined by chat's NotificationConsumer;
`game_<id>` is joined by both players' GameConsumer.
"""

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer


def _send(group: str, payload: dict) -> None:
    channel_layer = get_channel_layer()
    if channel_layer is None:
        return
    async_to_sync(channel_layer.group_send)(group, payload)


def to_user(user_id, event_type: str, **data) -> None:
    _send(f"user_{user_id}", {"type": event_type, **data})


def to_game(game_id, event_type: str, **data) -> None:
    _send(f"game_{game_id}", {"type": event_type, **data})
