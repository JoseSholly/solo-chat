import pytest

from games.services import PresenceService


@pytest.fixture(autouse=True)
def in_memory_channel_layer(settings):
    """Swap Redis for an in-memory channel layer so tests don't need Redis."""
    settings.CHANNEL_LAYERS = {
        "default": {"BACKEND": "channels.layers.InMemoryChannelLayer"},
    }


def _make(django_user_model, name):
    return django_user_model.objects.create_user(
        email=f"{name}@example.com",
        username=name,
        display_name=name.capitalize(),
        password="pw",
    )


@pytest.fixture
def alice(django_user_model):
    return _make(django_user_model, "alice")


@pytest.fixture
def bob(django_user_model):
    return _make(django_user_model, "bob")


@pytest.fixture
def carol(django_user_model):
    return _make(django_user_model, "carol")


@pytest.fixture
def online():
    """Mark users as online, as if their notification socket were open."""

    def _online(*users):
        for u in users:
            PresenceService.connect(u)

    return _online
