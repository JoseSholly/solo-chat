from django.urls import path, re_path

from . import consumers

websocket_urlpatterns = [
    # Authenticated slug-based consumer (new pages) — must come first so
    # Django's UUID converter matches before the catch-all str pattern below.
    path("ws/chat/<uuid:slug>/", consumers.RoomChatConsumer.as_asgi()),
    # Per-user notification channel (unread badge updates)
    path("ws/notifications/", consumers.NotificationConsumer.as_asgi()),
    # Legacy anonymous consumer (old /chat/<room_name>/ template)
    re_path(r"ws/chat/(?P<room_name>\w+)/$", consumers.ChatConsumer.as_asgi()),
]
