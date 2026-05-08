from __future__ import annotations

import base64
from typing import Any, cast

import pytest

from application.services import gemini_media
from application.services.gemini_media import (
    GeminiMediaBytes,
    GeminiMediaError,
    GeminiVideoPollResult,
    MediaGenerationService,
    read_media_asset_version_content,
    sanitize_media_prompt,
)
from application.services.tenancy import ensure_default_organization
from infrastructure.crypto.encryption import encrypt_api_key
from infrastructure.orm.models import APIKey, Graph, GraphVersion, MediaGenerationJob, User

pytestmark = pytest.mark.django_db


def _create_company(user: User, *, name: str = "Legacy Glasswear") -> Graph:
    ensure_default_organization(user)
    organization = user.default_organization
    assert organization is not None
    company = cast(
        Graph,
        Graph.objects.create(
            owner=user,
            organization=organization,
            name=name,
            description="Legacy Glasswear test company.",
        ),
    )
    GraphVersion.objects.create(
        graph=company,
        version=1,
        graph_json={"nodes": [], "edges": [], "metadata": {}},
    )
    return company


def _google_credential(user: User) -> APIKey:
    organization = user.default_organization
    assert organization is not None
    return APIKey.objects.create(
        organization=organization,
        user=user,
        provider="google",
        name="Legacy Gemini BYOK",
        encrypted_key=encrypt_api_key("gemini-test-key"),
    )


class _FakeMediaClient:
    image_calls = 0
    video_starts = 0
    video_polls = 0

    def generate_image(self, **kwargs: Any) -> GeminiMediaBytes:
        self.image_calls += 1
        return GeminiMediaBytes(
            content=b"fake-png",
            mime_type="image/png",
            response_json={"generatedImages": [{"image": {"imageBytes": "[omitted]"}}]},
        )

    def start_video(self, **kwargs: Any) -> tuple[str, dict[str, Any]]:
        self.video_starts += 1
        return "operations/legacy-video-1", {"name": "operations/legacy-video-1"}

    def poll_video(self, **kwargs: Any) -> GeminiVideoPollResult:
        self.video_polls += 1
        return GeminiVideoPollResult(
            done=True,
            media=GeminiMediaBytes(
                content=b"fake-mp4",
                mime_type="video/mp4",
                response_json={"done": True},
            ),
            response_json={"done": True},
        )


class _FailingImageClient(_FakeMediaClient):
    def generate_image(self, **kwargs: Any) -> GeminiMediaBytes:
        raise GeminiMediaError(
            "provider_http_error",
            "Gemini quota or model access failed.",
            status_code=429,
            retryable=True,
            response_json={"error": {"message": "quota"}},
        )


def test_sanitize_media_prompt_redacts_obvious_pii():
    prompt = "Send frame copy to buyer@example.com and card 4111 1111 1111 1111."

    sanitized = sanitize_media_prompt(prompt)

    assert "buyer@example.com" not in sanitized
    assert "4111" not in sanitized
    assert "[redacted-email]" in sanitized
    assert "[redacted-number]" in sanitized


def test_image_job_creates_backend_owned_draft_asset(settings, tmp_path, user):
    settings.MEDIA_GENERATION_ARTIFACT_ROOT = tmp_path
    company = _create_company(user)
    credential = _google_credential(user)

    job = MediaGenerationService(client=_FakeMediaClient()).create_job(
        user=user,
        company=company,
        credential=credential,
        modality="image",
        prompt="Legacy frame editorial draft for buyer@example.com",
        idempotency_key="phase-1-image",
    )

    assert job.status == "succeeded"
    assert job.provider == "google"
    assert job.output_asset is not None
    assert job.output_asset.asset_type == "image"
    assert job.output_asset.metadata_json["review_status"] == "draft"
    assert "buyer@example.com" not in job.prompt
    assert job.output_asset_version is not None
    content, mime_type, filename = read_media_asset_version_content(job.output_asset_version)
    assert content == b"fake-png"
    assert mime_type == "image/png"
    assert filename.endswith(".png")


def test_media_job_idempotency_reuses_existing_job(settings, tmp_path, user):
    settings.MEDIA_GENERATION_ARTIFACT_ROOT = tmp_path
    company = _create_company(user)
    credential = _google_credential(user)
    client = _FakeMediaClient()
    service = MediaGenerationService(client=client)

    first = service.create_job(
        user=user,
        company=company,
        credential=credential,
        modality="image",
        prompt="Legacy frame editorial draft",
        idempotency_key="phase-1-image",
    )
    second = service.create_job(
        user=user,
        company=company,
        credential=credential,
        modality="image",
        prompt="Different prompt should not regenerate",
        idempotency_key="phase-1-image",
    )

    assert second.id == first.id
    assert client.image_calls == 1
    assert MediaGenerationJob.objects.count() == 1


def test_video_job_poll_creates_video_draft_asset(settings, tmp_path, user):
    settings.MEDIA_GENERATION_ARTIFACT_ROOT = tmp_path
    company = _create_company(user)
    credential = _google_credential(user)
    service = MediaGenerationService(client=_FakeMediaClient())

    job = service.create_job(
        user=user,
        company=company,
        credential=credential,
        modality="video",
        prompt="Legacy product motion draft",
        idempotency_key="phase-1-video",
    )
    assert job.status == "running"
    assert job.provider_operation_name == "operations/legacy-video-1"

    job = service.poll_video_job(job=job)

    assert job.status == "succeeded"
    assert job.output_asset is not None
    assert job.output_asset.asset_type == "video"
    assert job.output_asset.metadata_json["review_status"] == "draft"
    assert job.output_asset_version is not None
    content, mime_type, filename = read_media_asset_version_content(job.output_asset_version)
    assert content == b"fake-mp4"
    assert mime_type == "video/mp4"
    assert filename.endswith(".mp4")


def test_failed_image_generation_records_failure(user):
    company = _create_company(user)
    credential = _google_credential(user)

    job = MediaGenerationService(client=_FailingImageClient()).create_job(
        user=user,
        company=company,
        credential=credential,
        modality="image",
        prompt="Legacy frame editorial draft",
    )

    assert job.status == "failed"
    assert job.error_code == "provider_http_error"
    assert "quota" in job.error_message.lower() or "access" in job.error_message.lower()
    assert job.output_asset is None


def test_credential_provider_mismatch_is_rejected(user):
    company = _create_company(user)
    organization = user.default_organization
    assert organization is not None
    credential = APIKey.objects.create(
        organization=organization,
        user=user,
        provider="openai",
        name="OpenAI",
        encrypted_key=encrypt_api_key("openai-test-key"),
    )

    with pytest.raises(GeminiMediaError, match="Google credential"):
        MediaGenerationService(client=_FakeMediaClient()).create_job(
            user=user,
            company=company,
            credential=credential,
            modality="image",
            prompt="Legacy frame editorial draft",
        )


def test_google_media_client_parses_image_bytes():
    encoded = base64.b64encode(b"image-bytes").decode()

    result = gemini_media._image_bytes_from_response(
        {"predictions": [{"bytesBase64Encoded": encoded, "mimeType": "image/png"}]}
    )

    assert result.content == b"image-bytes"
    assert result.mime_type == "image/png"
