from dataclasses import dataclass

from chat.events.bus import EventBus


@dataclass(frozen=True)
class _Foo:
    x: int


@dataclass(frozen=True)
class _Bar:
    y: str


def test_emit_calls_subscribed_handler():
    bus = EventBus()
    received = []
    bus.subscribe(_Foo, received.append)

    bus.emit(_Foo(x=1))

    assert received == [_Foo(x=1)]


def test_emit_calls_all_handlers_for_same_event():
    bus = EventBus()
    a, b = [], []
    bus.subscribe(_Foo, a.append)
    bus.subscribe(_Foo, b.append)

    bus.emit(_Foo(x=7))

    assert a == [_Foo(x=7)]
    assert b == [_Foo(x=7)]


def test_emit_ignores_handlers_for_other_event_types():
    bus = EventBus()
    foo_handlers, bar_handlers = [], []
    bus.subscribe(_Foo, foo_handlers.append)
    bus.subscribe(_Bar, bar_handlers.append)

    bus.emit(_Foo(x=1))

    assert foo_handlers == [_Foo(x=1)]
    assert bar_handlers == []


def test_emit_with_no_subscribers_is_a_noop():
    bus = EventBus()
    bus.emit(_Foo(x=99))  # must not raise


def test_handler_exception_is_swallowed(caplog):
    import logging

    bus = EventBus()

    def bad(_event):
        raise RuntimeError("boom")

    bus.subscribe(_Foo, bad)

    with caplog.at_level(logging.ERROR, logger="chat.events.bus"):
        bus.emit(_Foo(x=1))  # must not raise

    errors = [r for r in caplog.records if r.levelno == logging.ERROR]
    assert errors, "expected an ERROR log from the bus"
    assert errors[0].exc_info is not None
    assert isinstance(errors[0].exc_info[1], RuntimeError)


def test_failing_handler_does_not_block_later_handlers():
    bus = EventBus()
    received = []

    def bad(_event):
        raise RuntimeError("boom")

    bus.subscribe(_Foo, bad)
    bus.subscribe(_Foo, received.append)

    bus.emit(_Foo(x=42))

    assert received == [_Foo(x=42)]
