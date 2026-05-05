"""
WebSocket routing for the ForgeGraph backend.

Clean Architecture: Frameworks & Drivers layer (Django/Channels wiring).
"""

from django.urls import path

from adapters.ws.organizations.consumers import OrganizationStateConsumer
from adapters.ws.runs.consumers import RunUpdatesConsumer

websocket_urlpatterns = [
    path("ws/organizations/<uuid:organization_id>/state/", OrganizationStateConsumer.as_asgi()),
    path("ws/runs/<uuid:run_id>/", RunUpdatesConsumer.as_asgi()),
]
