"""
ORM app configuration.
"""

from django.apps import AppConfig


class OrmConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "infrastructure.orm"
    label = "orm"
    verbose_name = "ForgeGraph ORM"
