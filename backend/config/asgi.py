"""
ASGI config for ForgeGraph backend.

Clean Architecture: This belongs to the Frameworks & Drivers layer.
"""

import os

from django.core.asgi import get_asgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

application = get_asgi_application()
