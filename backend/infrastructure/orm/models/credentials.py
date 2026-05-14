"""Django ORM model group split from infrastructure.orm.models."""

from __future__ import annotations

# ruff: noqa: F401,F403,F405,I001

from infrastructure.orm.models.evaluations import *  # noqa: F403
from infrastructure.orm.models.base import _make_check_constraint


class APIKey(models.Model):
    """APIKey model for storing encrypted user API keys for LLM providers."""

    PROVIDER_CHOICES = [
        ("openai", "OpenAI"),
        ("anthropic", "Anthropic"),
        ("google", "Google AI"),
        ("openrouter", "OpenRouter"),
        ("gmail", "Gmail"),
        ("google_calendar", "Google Calendar"),
        ("google_tasks", "Google Tasks"),
        ("notion", "Notion"),
        ("slack", "Slack"),
        ("jira", "Jira"),
        ("linear", "Linear"),
        ("hubspot", "HubSpot"),
        ("google_drive", "Google Drive"),
        ("telegram", "Telegram"),
        ("twilio", "Twilio"),
        ("stripe", "Stripe"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(
        Organization,
        on_delete=models.CASCADE,
        related_name="api_keys",
    )
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="api_keys",
    )
    provider = models.CharField(max_length=32, choices=PROVIDER_CHOICES)
    name = models.CharField(max_length=100, help_text="User-friendly name for this key")
    encrypted_key = models.BinaryField(help_text="Fernet-encrypted API key")
    encrypted_refresh_token = models.BinaryField(
        null=True,
        blank=True,
        help_text="Fernet-encrypted OAuth refresh token",
    )
    token_expires_at = models.DateTimeField(null=True, blank=True)
    token_metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "api_keys"
        ordering = ["-created_at"]
        unique_together = [["organization", "provider", "name"]]
        indexes = [
            models.Index(
                fields=["organization", "provider"],
                name="api_keys_org_provider_idx",
            ),
            models.Index(fields=["user"], name="api_keys_user_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.provider} - {self.name} ({self.organization.name})"

    @property
    def key_hint(self) -> str:
        """Return last 4 characters of the decrypted key for display."""
        from infrastructure.crypto.encryption import decrypt_api_key

        try:
            decrypted = decrypt_api_key(bytes(self.encrypted_key))
            return f"****{decrypted[-4:]}" if len(decrypted) >= 4 else "****"
        except Exception:
            return "****"
