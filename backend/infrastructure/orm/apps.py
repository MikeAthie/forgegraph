"""
ORM app configuration.
"""

from django.apps import AppConfig
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured


_pack_health_checked = False


class OrmConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "infrastructure.orm"
    label = "orm"
    verbose_name = "ForgeGraph ORM"

    def ready(self) -> None:
        global _pack_health_checked
        if _pack_health_checked or not getattr(
            settings, "VALIDATE_REQUIRED_OPERATING_MODEL_PACKS_ON_STARTUP", True
        ):
            return
        _pack_health_checked = True
        from application.services.operating_model_packs import (
            OperatingModelPackError,
            validate_required_operating_model_packs,
        )

        try:
            validate_required_operating_model_packs()
        except OperatingModelPackError as exc:
            raise ImproperlyConfigured(exc.message) from exc
