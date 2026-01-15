"""
Ensure a Django superuser exists for local development.

This command is safe to run repeatedly (idempotent). It will only create a user
if one with the configured email does not already exist.
"""

import os

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = "Create a superuser from DJANGO_SUPERUSER_* env vars (if missing)."

    def handle(self, *args, **options):
        should_create = os.environ.get("DJANGO_SUPERUSER_CREATE", "true").lower() in {
            "1",
            "true",
            "yes",
            "on",
        }
        if not should_create:
            return

        email = os.environ.get("DJANGO_SUPERUSER_EMAIL")
        password = os.environ.get("DJANGO_SUPERUSER_PASSWORD")

        if not email and not password:
            return

        if not email or not password:
            raise CommandError(
                "Both DJANGO_SUPERUSER_EMAIL and DJANGO_SUPERUSER_PASSWORD must be set."
            )

        email = email.strip().lower()
        User = get_user_model()

        existing = User.objects.filter(email=email).first()
        if existing:
            changed_fields: list[str] = []
            if not existing.is_staff:
                existing.is_staff = True
                changed_fields.append("is_staff")
            if not existing.is_superuser:
                existing.is_superuser = True
                changed_fields.append("is_superuser")
            if not existing.is_active:
                existing.is_active = True
                changed_fields.append("is_active")

            if changed_fields:
                existing.save(update_fields=changed_fields)
                self.stdout.write(self.style.SUCCESS(f"Updated superuser flags for {email}"))
            return

        User.objects.create_superuser(email=email, password=password)
        self.stdout.write(self.style.SUCCESS(f"Created superuser {email}"))
