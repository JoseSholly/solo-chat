import os

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.dev")

from channels.routing import ProtocolTypeRouter, URLRouter
from channels.security.websocket import AllowedHostsOriginValidator
from django.core.asgi import get_asgi_application

# get_asgi_application() initializes the Django app registry.
# chat.routing must be imported after this call or consumers that
# touch models will raise AppRegistryNotReady at startup.
django_asgi_app = get_asgi_application()

from chat import routing  # noqa: E402

application = ProtocolTypeRouter({
    "http": django_asgi_app,
    "websocket": AllowedHostsOriginValidator(
        URLRouter(routing.websocket_urlpatterns)
    ),
})
