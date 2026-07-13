import logging
from collections import defaultdict
from typing import Callable, Type

logger = logging.getLogger(__name__)


class EventBus:
    def __init__(self) -> None:
        self._handlers: dict[Type, list[Callable]] = defaultdict(list)

    def subscribe(self, event_cls: Type, handler: Callable) -> None:
        self._handlers[event_cls].append(handler)

    def emit(self, event) -> None:
        for handler in self._handlers.get(type(event), []):
            try:
                handler(event)
            except Exception:
                logger.exception("Event handler %r failed for %r", handler, event)


event_bus = EventBus()
