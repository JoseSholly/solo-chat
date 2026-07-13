from django.apps import AppConfig


class ChatConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "chat"

    def ready(self) -> None:
        from chat.events import event_bus
        from chat.events.handlers import register_all
        from chat.events import signals  # noqa: F401

        register_all(event_bus)
