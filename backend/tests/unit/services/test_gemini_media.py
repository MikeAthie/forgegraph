from __future__ import annotations

import base64
from typing import Any, cast

import pytest

from application.services import gemini_media
from application.services.gemini_media import (
    GeminiMediaBytes,
    GeminiMediaError,
    GeminiVideoPollResult,
    GoogleMediaClient,
    MediaGenerationService,
    OpenRouterMediaClient,
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


def _openrouter_credential(user: User) -> APIKey:
    organization = user.default_organization
    assert organization is not None
    return APIKey.objects.create(
        organization=organization,
        user=user,
        provider="openrouter",
        name="Legacy OpenRouter BYOK",
        encrypted_key=encrypt_api_key("openrouter-test-key"),
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


class _PaidPlanImageClient(_FakeMediaClient):
    def generate_image(self, **kwargs: Any) -> GeminiMediaBytes:
        raise GeminiMediaError(
            "provider_http_error",
            "Imagen 3 is only available on paid plans. Please upgrade your account.",
            status_code=400,
            retryable=False,
            response_json={
                "error": {
                    "message": "Imagen 3 is only available on paid plans. Please upgrade your account."
                }
            },
        )


class _FakeResponse:
    status_code = 200
    reason = "OK"

    def __init__(self, payload: dict[str, Any]) -> None:
        self._payload = payload

    def json(self) -> dict[str, Any]:
        return self._payload


class _RecordingSession:
    def __init__(self, payload: dict[str, Any]) -> None:
        self.payload = payload
        self.posts: list[dict[str, Any]] = []

    def post(self, url: str, **kwargs: Any) -> _FakeResponse:
        self.posts.append({"url": url, **kwargs})
        return _FakeResponse(self.payload)


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


def test_openrouter_image_job_creates_backend_owned_draft_asset(settings, tmp_path, user):
    settings.MEDIA_GENERATION_ARTIFACT_ROOT = tmp_path
    company = _create_company(user)
    credential = _openrouter_credential(user)

    job = MediaGenerationService(openrouter_client=_FakeMediaClient()).create_job(
        user=user,
        company=company,
        credential=credential,
        modality="image",
        prompt="Legacy OpenRouter frame editorial draft",
        model="google/gemini-3.1-flash-image-preview",
        idempotency_key="phase-1-openrouter-image",
    )

    assert job.status == "succeeded"
    assert job.provider == "openrouter"
    assert job.output_asset is not None
    assert job.output_asset.asset_type == "image"
    assert job.output_asset.metadata_json["provider"] == "openrouter"
    assert job.output_asset.metadata_json["review_status"] == "draft"
    assert job.output_asset_version is not None
    content, mime_type, filename = read_media_asset_version_content(job.output_asset_version)
    assert content == b"fake-png"
    assert mime_type == "image/png"
    assert filename.endswith(".png")


def test_image_job_falls_back_to_openrouter_on_google_limit_error(settings, tmp_path, user):
    settings.MEDIA_GENERATION_ARTIFACT_ROOT = tmp_path
    company = _create_company(user)
    google_credential = _google_credential(user)
    openrouter_credential = _openrouter_credential(user)
    google_client = _FailingImageClient()
    openrouter_client = _FakeMediaClient()
    service = MediaGenerationService(
        client=google_client,
        openrouter_client=openrouter_client,
    )

    result = service.create_image_job_with_provider_fallback(
        user=user,
        company=company,
        primary_credential=google_credential,
        fallback_credential=openrouter_credential,
        prompt="Legacy Phase 7 campaign image draft",
        idempotency_key="phase-7-provider-fallback",
        primary_model="imagen-4.0-generate-001",
        fallback_model="google/gemini-3.1-flash-image-preview",
    )
    repeated = service.create_image_job_with_provider_fallback(
        user=user,
        company=company,
        primary_credential=google_credential,
        fallback_credential=openrouter_credential,
        prompt="A changed prompt must not create duplicate jobs",
        idempotency_key="phase-7-provider-fallback",
        primary_model="imagen-4.0-generate-001",
        fallback_model="google/gemini-3.1-flash-image-preview",
    )

    assert result.fallback_used is True
    assert result.primary_job.status == "failed"
    assert result.primary_job.provider == "google"
    assert result.fallback_job is not None
    assert result.fallback_job.status == "succeeded"
    assert result.selected_job.id == result.fallback_job.id
    assert result.selected_job.provider == "openrouter"
    assert result.selected_job.output_asset is not None
    assert result.selected_job.output_asset.metadata_json["review_status"] == "draft"
    assert (
        result.selected_job.output_asset.metadata_json["approval_required_before_publish"] is True
    )
    assert repeated.selected_job.id == result.selected_job.id
    assert google_client.image_calls == 0
    assert openrouter_client.image_calls == 1
    assert MediaGenerationJob.objects.count() == 2


def test_image_job_falls_back_to_openrouter_on_google_paid_plan_limit(settings, tmp_path, user):
    settings.MEDIA_GENERATION_ARTIFACT_ROOT = tmp_path
    company = _create_company(user)
    google_credential = _google_credential(user)
    openrouter_credential = _openrouter_credential(user)
    service = MediaGenerationService(
        client=_PaidPlanImageClient(),
        openrouter_client=_FakeMediaClient(),
    )

    result = service.create_image_job_with_provider_fallback(
        user=user,
        company=company,
        primary_credential=google_credential,
        fallback_credential=openrouter_credential,
        prompt="Legacy Phase 7 campaign image draft",
        idempotency_key="phase-7-provider-plan-fallback",
        primary_model="imagen-4.0-generate-001",
        fallback_model="google/gemini-3.1-flash-image-preview",
    )

    assert result.fallback_used is True
    assert result.primary_job.status == "failed"
    assert result.fallback_job is not None
    assert result.fallback_reason == "only_available_on_paid_plans"
    assert result.selected_job.provider == "openrouter"
    assert result.selected_job.output_asset is not None
    assert result.selected_job.output_asset.metadata_json["review_status"] == "draft"
    assert MediaGenerationJob.objects.count() == 2


def test_openrouter_video_job_is_rejected_before_provider_call(user):
    company = _create_company(user)
    credential = _openrouter_credential(user)

    with pytest.raises(GeminiMediaError, match="Video media generation"):
        MediaGenerationService(openrouter_client=_FakeMediaClient()).create_job(
            user=user,
            company=company,
            credential=credential,
            modality="video",
            prompt="Legacy video draft",
            idempotency_key="phase-1-openrouter-video",
        )

    assert MediaGenerationJob.objects.count() == 0


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

    with pytest.raises(GeminiMediaError, match="Google or OpenRouter credential"):
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


def test_google_media_client_parses_gemini_native_image_part_after_text():
    encoded = base64.b64encode(b"native-image-bytes").decode()

    result = gemini_media._image_bytes_from_response(
        {
            "candidates": [
                {
                    "content": {
                        "parts": [
                            {"text": "Draft ready."},
                            {"inlineData": {"data": encoded, "mimeType": "image/webp"}},
                        ]
                    }
                }
            ]
        }
    )

    assert result.content == b"native-image-bytes"
    assert result.mime_type == "image/webp"


def test_google_media_client_uses_generate_content_for_gemini_image_model():
    encoded = base64.b64encode(b"native-image-bytes").decode()
    session = _RecordingSession(
        {
            "candidates": [
                {"content": {"parts": [{"inlineData": {"data": encoded, "mimeType": "image/png"}}]}}
            ]
        }
    )
    client = GoogleMediaClient(
        api_base_url="https://gemini.test/v1beta", session=cast(Any, session)
    )

    result = client.generate_image(
        api_key="gemini-test-key",
        model="gemini-3.1-flash-image-preview",
        prompt="Legacy image draft",
    )

    assert result.content == b"native-image-bytes"
    assert session.posts[0]["url"].endswith(
        "/models/gemini-3.1-flash-image-preview:generateContent"
    )
    assert session.posts[0]["json"]["generationConfig"]["responseModalities"] == [
        "TEXT",
        "IMAGE",
    ]


def test_google_media_client_uses_imagen_predict_for_imagen_model():
    encoded = base64.b64encode(b"imagen-bytes").decode()
    session = _RecordingSession(
        {"predictions": [{"bytesBase64Encoded": encoded, "mimeType": "image/png"}]}
    )
    client = GoogleMediaClient(
        api_base_url="https://gemini.test/v1beta", session=cast(Any, session)
    )

    result = client.generate_image(
        api_key="gemini-test-key",
        model="imagen-4.0-generate-001",
        prompt="Legacy image draft",
    )

    assert result.content == b"imagen-bytes"
    assert session.posts[0]["url"].endswith("/models/imagen-4.0-generate-001:predict")


def test_openrouter_media_client_parses_image_data_url():
    encoded = base64.b64encode(b"openrouter-image").decode()
    session = _RecordingSession(
        {
            "choices": [
                {
                    "message": {
                        "content": "Draft ready.",
                        "images": [
                            {
                                "type": "image_url",
                                "image_url": {"url": f"data:image/png;base64,{encoded}"},
                            }
                        ],
                    }
                }
            ]
        }
    )
    client = OpenRouterMediaClient(
        api_base_url="https://openrouter.test/api/v1", session=cast(Any, session)
    )

    result = client.generate_image(
        api_key="openrouter-test-key",
        model="black-forest-labs/flux.2-klein-4b",
        prompt="Legacy image draft",
    )

    assert result.content == b"openrouter-image"
    assert result.mime_type == "image/png"
    assert session.posts[0]["url"].endswith("/chat/completions")
    assert session.posts[0]["headers"]["Authorization"] == "Bearer openrouter-test-key"
    assert session.posts[0]["json"]["modalities"] == ["image"]
    assert "max_tokens" not in session.posts[0]["json"]
    assert "image_config" not in session.posts[0]["json"]


def test_openrouter_media_client_uses_gemini_image_config():
    encoded = base64.b64encode(b"openrouter-gemini-image").decode()
    session = _RecordingSession(
        {
            "choices": [
                {
                    "message": {
                        "images": [
                            {
                                "type": "image_url",
                                "image_url": {"url": f"data:image/png;base64,{encoded}"},
                            }
                        ],
                    }
                }
            ]
        }
    )
    client = OpenRouterMediaClient(
        api_base_url="https://openrouter.test/api/v1", session=cast(Any, session)
    )

    result = client.generate_image(
        api_key="openrouter-test-key",
        model="google/gemini-3.1-flash-image-preview",
        prompt="Legacy image draft",
    )

    assert result.content == b"openrouter-gemini-image"
    assert session.posts[0]["json"]["modalities"] == ["image", "text"]
    assert "max_tokens" not in session.posts[0]["json"]
    assert session.posts[0]["json"]["image_config"] == {
        "aspect_ratio": "1:1",
        "image_size": "0.5K",
    }
