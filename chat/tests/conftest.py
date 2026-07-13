import pytest

from chat.models import Room, RoomMembership


@pytest.fixture(autouse=True)
def in_memory_channel_layer(settings):
    """Swap Redis for an in-memory channel layer so tests don't need Redis."""
    settings.CHANNEL_LAYERS = {
        "default": {"BACKEND": "channels.layers.InMemoryChannelLayer"},
    }


@pytest.fixture
def user(django_user_model):
    return django_user_model.objects.create_user(
        email="alice@example.com",
        username="alice",
        display_name="Alice",
        password="pw",
    )


@pytest.fixture
def other_user(django_user_model):
    return django_user_model.objects.create_user(
        email="bob@example.com",
        username="bob",
        display_name="Bob",
        password="pw",
    )


@pytest.fixture
def third_user(django_user_model):
    return django_user_model.objects.create_user(
        email="carol@example.com",
        username="carol",
        display_name="Carol",
        password="pw",
    )


@pytest.fixture
def room(user):
    room = Room.objects.create(name="general", creator=user)
    RoomMembership.objects.create(user=user, room=room)
    return room


@pytest.fixture
def captured_events(monkeypatch):
    """Replace `event_bus` in service modules with a recorder.

    Isolates service tests from real handler side effects (channel layer, DB).
    """
    captured: list = []

    class Recorder:
        def emit(self, event):
            captured.append(event)

    recorder = Recorder()
    monkeypatch.setattr("chat.services.message_service.event_bus", recorder)
    monkeypatch.setattr("chat.services.room_service.event_bus", recorder)
    return captured
