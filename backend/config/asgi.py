"""
ASGI config for ForgeGraph backend.

Clean Architecture: This belongs to the Frameworks & Drivers layer.
"""

import os

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

from django.core.asgi import get_asgi_application

django_asgi_app = get_asgi_application()

from channels.routing import ProtocolTypeRouter, URLRouter  # noqa: E402

from adapters.ws.middleware import JwtQueryStringAuthMiddleware  # noqa: E402
from config.routing import websocket_urlpatterns  # noqa: E402

application = ProtocolTypeRouter(
    {
        "http": django_asgi_app,
        "websocket": JwtQueryStringAuthMiddleware(URLRouter(websocket_urlpatterns)),
    }
)
