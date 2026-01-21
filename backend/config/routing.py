"""
WebSocket routing for the ForgeGraph backend.

Clean Architecture: Frameworks & Drivers layer (Django/Channels wiring).
"""

from django.urls import path

from adapters.ws.runs.consumers import RunUpdatesConsumer

websocket_urlpatterns = [
    path("ws/runs/<uuid:run_id>/", RunUpdatesConsumer.as_asgi()),
]
