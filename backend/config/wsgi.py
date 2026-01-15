"""
WSGI config for ForgeGraph backend.

Clean Architecture: This belongs to the Frameworks & Drivers layer.
"""

import os

from django.core.wsgi import get_wsgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

application = get_wsgi_application()
