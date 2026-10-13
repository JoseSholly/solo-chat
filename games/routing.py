from django.urls import path

from . import consumers

websocket_urlpatterns = [
    path("ws/games/<uuid:game_id>/", consumers.GameConsumer.as_asgi()),
]
