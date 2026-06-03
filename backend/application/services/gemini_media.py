"""Backend-owned Gemini media generation services for company draft assets."""

from __future__ import annotations

import base64
import hashlib
import json
import mimetypes
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import requests
from django.conf import settings
from django.db import IntegrityError
from django.utils import timezone

from application.services.company_archive import ArchiveService
from application.services.credential_state import is_credential_revoked
from infrastructure.crypto.encryption import EncryptionError, decrypt_api_key
from infrastructure.orm.models import (
    APIKey,
    AssetVersion,
    Graph,
    MediaGenerationJob,
    Organization,
    User,
)

_EMAIL_RE = re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.IGNORECASE)
_LONG_NUMBER_RE = re.compile(r"\b(?:\d[\s-]?){8,}\d\b")
_WHITESPACE_RE = re.compile(r"\s+")
MAX_MEDIA_PROMPT_CHARS = 4000


class GeminiMediaError(RuntimeError):
    """Provider or credential error that has already been sanitized for operators."""

    def __init__(
        self,
        code: str,
        message: str,
        *,
        status_code: int | None = None,
        retryable: bool = False,
        response_json: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code
        self.retryable = retryable
        self.response_json = response_json or {}


@dataclass(frozen=True)
class GeminiMediaBytes:
    content: bytes
    mime_type: str
    response_json: dict[str, Any]


@dataclass(frozen=True)
class GeminiVideoPollResult:
    done: bool
    media: GeminiMediaBytes | None
    response_json: dict[str, Any]


@dataclass(frozen=True)
class MediaGenerationFallbackResult:
    primary_job: MediaGenerationJob
    fallback_job: MediaGenerationJob | None
    selected_job: MediaGenerationJob
    fallback_used: bool
    fallback_reason: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "primary_job_id": str(self.primary_job.id),
            "fallback_job_id": str(self.fallback_job.id) if self.fallback_job else None,
            "selected_job_id": str(self.selected_job.id),
            "fallback_used": self.fallback_used,
            "fallback_reason": self.fallback_reason,
            "primary_provider": self.primary_job.provider,
            "selected_provider": self.selected_job.provider,
            "selected_status": self.selected_job.status,
        }


def sanitize_media_prompt(prompt: str) -> str:
    """Remove obvious PII before storing or sending media context to Gemini."""

    sanitized = _EMAIL_RE.sub("[redacted-email]", str(prompt or ""))
    sanitized = _LONG_NUMBER_RE.sub("[redacted-number]", sanitized)
    sanitized = _WHITESPACE_RE.sub(" ", sanitized).strip()
    return sanitized[:MAX_MEDIA_PROMPT_CHARS]


def prompt_hash(prompt: str) -> str:
    return hashlib.sha256(prompt.encode("utf-8")).hexdigest()


def is_media_provider_limit_error(error_or_job: GeminiMediaError | MediaGenerationJob) -> bool:
    if isinstance(error_or_job, GeminiMediaError):
        if error_or_job.status_code == 429:
            return True
        text = _limit_error_text(
            code=error_or_job.code,
            message=error_or_job.message,
            response_json=error_or_job.response_json,
        )
    else:
        text = _limit_error_text(
            code=error_or_job.error_code,
            message=error_or_job.error_message,
            response_json=error_or_job.response_json,
        )
    return any(signature in text for signature in _LIMIT_ERROR_SIGNATURES)


def media_generation_job_payload(job: MediaGenerationJob) -> dict[str, Any]:
    return {
        "id": str(job.id),
        "organization_id": str(job.organization_id),
        "company_id": str(job.company_id),
        "requested_by_id": str(job.requested_by_id) if job.requested_by_id else None,
        "credential_id": str(job.credential_id) if job.credential_id else None,
        "modality": job.modality,
        "provider": job.provider,
        "model": job.model,
        "prompt": job.prompt,
        "prompt_hash": job.prompt_hash,
        "idempotency_key": job.idempotency_key,
        "status": job.status,
        "provider_operation_name": job.provider_operation_name,
        "output_asset_id": str(job.output_asset_id) if job.output_asset_id else None,
        "output_asset_version_id": (
            str(job.output_asset_version_id) if job.output_asset_version_id else None
        ),
        "output_mime_type": job.output_mime_type,
        "output_size_bytes": job.output_size_bytes,
        "error_code": job.error_code,
        "error_message": job.error_message,
        "created_at": job.created_at.isoformat() if job.created_at else None,
        "updated_at": job.updated_at.isoformat() if job.updated_at else None,
        "completed_at": job.completed_at.isoformat() if job.completed_at else None,
    }


class GoogleMediaClient:
    """Minimal Gemini Developer API media client using backend-owned requests."""

    def __init__(
        self, *, api_base_url: str | None = None, session: requests.Session | None = None
    ) -> None:
        self.api_base_url = (api_base_url or settings.GEMINI_API_BASE_URL).rstrip("/")
        self.session = session or requests.Session()

    def generate_image(
        self,
        *,
        api_key: str,
        model: str,
        prompt: str,
        aspect_ratio: str = "1:1",
    ) -> GeminiMediaBytes:
        if _is_imagen_model(model):
            return self._generate_imagen_image(
                api_key=api_key,
                model=model,
                prompt=prompt,
                aspect_ratio=aspect_ratio,
            )

        return self._generate_gemini_image(api_key=api_key, model=model, prompt=prompt)

    def _generate_imagen_image(
        self,
        *,
        api_key: str,
        model: str,
        prompt: str,
        aspect_ratio: str,
    ) -> GeminiMediaBytes:
        payload = {
            "instances": [{"prompt": prompt}],
            "parameters": {
                "sampleCount": 1,
                "aspectRatio": aspect_ratio,
                "personGeneration": "dont_allow",
                "includeRaiReason": True,
            },
        }
        response_json = self._post_json(
            f"/models/{_model_path(model)}:predict",
            api_key=api_key,
            payload=payload,
            timeout=180,
        )
        return _image_bytes_from_response(response_json)

    def _generate_gemini_image(
        self,
        *,
        api_key: str,
        model: str,
        prompt: str,
    ) -> GeminiMediaBytes:
        payload = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"responseModalities": ["TEXT", "IMAGE"]},
        }
        response_json = self._post_json(
            f"/models/{_model_path(model)}:generateContent",
            api_key=api_key,
            payload=payload,
            timeout=180,
        )
        return _image_bytes_from_response(response_json)

    def start_video(
        self,
        *,
        api_key: str,
        model: str,
        prompt: str,
        aspect_ratio: str = "16:9",
    ) -> tuple[str, dict[str, Any]]:
        payload = {
            "instances": [{"prompt": prompt}],
            "parameters": {
                "sampleCount": 1,
                "numberOfVideos": 1,
                "aspectRatio": aspect_ratio,
                "personGeneration": "dont_allow",
            },
        }
        response_json = self._post_json(
            f"/models/{_model_path(model)}:predictLongRunning",
            api_key=api_key,
            payload=payload,
            timeout=180,
        )
        operation_name = str(response_json.get("name") or "").strip()
        if not operation_name:
            raise GeminiMediaError(
                "missing_operation_name",
                "Gemini video generation did not return an operation name.",
                response_json=_without_large_payloads(response_json),
            )
        return operation_name, _without_large_payloads(response_json)

    def poll_video(self, *, api_key: str, operation_name: str) -> GeminiVideoPollResult:
        response_json = self._get_json(
            _operation_path(operation_name), api_key=api_key, timeout=180
        )
        if response_json.get("error"):
            error_payload = response_json.get("error")
            error: dict[str, Any] = error_payload if isinstance(error_payload, dict) else {}
            raise GeminiMediaError(
                "provider_operation_failed",
                str(error.get("message") or "Gemini video operation failed."),
                status_code=_int_or_none(error.get("code")),
                response_json=_without_large_payloads(response_json),
            )
        if not bool(response_json.get("done")):
            return GeminiVideoPollResult(
                done=False,
                media=None,
                response_json=_without_large_payloads(response_json),
            )

        video_uri = _first_string(
            response_json,
            [
                ("response", "generateVideoResponse", "generatedSamples", 0, "video", "uri"),
                ("response", "generatedVideos", 0, "video", "uri"),
                ("response", "generated_videos", 0, "video", "uri"),
                ("response", "generatedSamples", 0, "video", "uri"),
            ],
        )
        if not video_uri:
            inline = _inline_video_from_response(response_json)
            if inline is not None:
                return GeminiVideoPollResult(
                    done=True,
                    media=inline,
                    response_json=_without_large_payloads(response_json),
                )
            raise GeminiMediaError(
                "missing_video_uri",
                "Gemini video operation completed without a downloadable video URI.",
                response_json=_without_large_payloads(response_json),
            )

        media = self._download_media(video_uri, api_key=api_key, default_mime_type="video/mp4")
        return GeminiVideoPollResult(
            done=True,
            media=GeminiMediaBytes(
                content=media.content,
                mime_type=media.mime_type,
                response_json=_without_large_payloads(response_json),
            ),
            response_json=_without_large_payloads(response_json),
        )

    def _post_json(
        self,
        path: str,
        *,
        api_key: str,
        payload: dict[str, Any],
        timeout: int,
    ) -> dict[str, Any]:
        response = self.session.post(
            f"{self.api_base_url}{path}",
            headers=_headers(api_key),
            json=payload,
            timeout=timeout,
        )
        return _json_or_provider_error(response)

    def _get_json(self, path: str, *, api_key: str, timeout: int) -> dict[str, Any]:
        response = self.session.get(
            f"{self.api_base_url}{path}",
            headers=_headers(api_key),
            timeout=timeout,
        )
        return _json_or_provider_error(response)

    def _download_media(
        self,
        uri: str,
        *,
        api_key: str,
        default_mime_type: str,
    ) -> GeminiMediaBytes:
        parsed = urlparse(uri)
        if not parsed.scheme:
            uri = f"{self.api_base_url}/{uri.lstrip('/')}"
        response = self.session.get(uri, headers=_headers(api_key), timeout=300)
        if response.status_code >= 400:
            _ = _json_or_provider_error(response)
        mime_type = response.headers.get("content-type", "").split(";")[0].strip()
        return GeminiMediaBytes(
            content=response.content,
            mime_type=mime_type or default_mime_type,
            response_json={},
        )


class OpenRouterMediaClient:
    """OpenRouter media client using its OpenAI-compatible chat completions API."""

    def __init__(
        self, *, api_base_url: str | None = None, session: requests.Session | None = None
    ) -> None:
        self.api_base_url = (api_base_url or settings.OPENROUTER_API_BASE_URL).rstrip("/")
        self.session = session or requests.Session()

    def generate_image(
        self,
        *,
        api_key: str,
        model: str,
        prompt: str,
        aspect_ratio: str = "1:1",
    ) -> GeminiMediaBytes:
        model_name = model.strip() or settings.OPENROUTER_IMAGE_MODEL
        payload = {
            "model": model_name,
            "messages": [{"role": "user", "content": prompt}],
            "stream": False,
        }
        if _openrouter_model_outputs_text(model_name):
            payload["modalities"] = ["image", "text"]
            payload["image_config"] = {"aspect_ratio": aspect_ratio, "image_size": "0.5K"}
        else:
            payload["modalities"] = ["image"]
        response_json = self._post_json(
            "/chat/completions",
            api_key=api_key,
            payload=payload,
            timeout=300,
        )
        return _openrouter_image_bytes_from_response(response_json)

    def _post_json(
        self,
        path: str,
        *,
        api_key: str,
        payload: dict[str, Any],
        timeout: int,
    ) -> dict[str, Any]:
        response = self.session.post(
            f"{self.api_base_url}{path}",
            headers=_openrouter_headers(api_key),
            json=payload,
            timeout=timeout,
        )
        return _json_or_provider_error(response, provider_label="OpenRouter")


class OpenAIImageMediaClient:
    """OpenAI Images API client using backend-owned requests."""

    def __init__(
        self, *, api_base_url: str | None = None, session: requests.Session | None = None
    ) -> None:
        self.api_base_url = (api_base_url or settings.OPENAI_API_BASE_URL).rstrip("/")
        self.session = session or requests.Session()

    def generate_image(
        self,
        *,
        api_key: str,
        model: str,
        prompt: str,
        aspect_ratio: str = "1:1",
    ) -> GeminiMediaBytes:
        del aspect_ratio
        model_name = model.strip() or settings.OPENAI_IMAGE_MODEL
        payload: dict[str, Any] = {
            "model": model_name,
            "prompt": prompt,
            "n": 1,
            "size": "1024x1024",
        }
        if _openai_image_model_accepts_response_format(model_name):
            payload["response_format"] = "b64_json"
        response_json = self._post_json(
            "/images/generations",
            api_key=api_key,
            payload=payload,
            timeout=300,
        )
        return _openai_image_bytes_from_response(response_json)

    def _post_json(
        self,
        path: str,
        *,
        api_key: str,
        payload: dict[str, Any],
        timeout: int,
    ) -> dict[str, Any]:
        response = self.session.post(
            f"{self.api_base_url}{path}",
            headers=_openai_headers(api_key),
            json=payload,
            timeout=timeout,
        )
        return _json_or_provider_error(response, provider_label="OpenAI")


class MediaGenerationService:
    """Create and poll backend-owned media jobs for a company."""

    def __init__(
        self,
        *,
        client: Any | None = None,
        openrouter_client: Any | None = None,
        openai_client: Any | None = None,
    ) -> None:
        self.client = client or GoogleMediaClient()
        self.openrouter_client = openrouter_client or OpenRouterMediaClient()
        self.openai_client = openai_client or OpenAIImageMediaClient()

    def create_job(
        self,
        *,
        user: User,
        company: Graph,
        credential: APIKey,
        modality: str,
        prompt: str,
        idempotency_key: str = "",
        model: str = "",
    ) -> MediaGenerationJob:
        organization = company.organization
        if organization is None:
            raise GeminiMediaError("invalid_company", "Media jobs require an organization company.")
        self._validate_credential(company=company, credential=credential)

        modality = modality.strip().lower()
        if modality not in {"image", "video"}:
            raise GeminiMediaError("invalid_modality", "Media modality must be image or video.")
        provider = str(credential.provider or "").strip().lower()
        if provider in {"openrouter", "openai"} and modality == "video":
            raise GeminiMediaError(
                "unsupported_modality",
                "Video media generation is currently supported only for Google Gemini/Veo credentials.",
            )

        idempotency_key = idempotency_key.strip()
        existing = self._find_existing_job(company=company, idempotency_key=idempotency_key)
        if existing is not None:
            return existing

        sanitized_prompt = sanitize_media_prompt(prompt)
        if not sanitized_prompt:
            raise GeminiMediaError("empty_prompt", "Media prompt is required.")
        selected_model = model.strip() or _default_model(modality, provider=provider)

        job = self._create_pending_job(
            user=user,
            company=company,
            organization=organization,
            credential=credential,
            modality=modality,
            provider=provider,
            model=selected_model,
            prompt=sanitized_prompt,
            idempotency_key=idempotency_key,
        )
        if modality == "image":
            return self._run_image_job(job)
        return self._start_video_job(job)

    def _find_existing_job(
        self,
        *,
        company: Graph,
        idempotency_key: str,
    ) -> MediaGenerationJob | None:
        if not idempotency_key:
            return None
        return MediaGenerationJob.objects.filter(
            company=company,
            idempotency_key=idempotency_key,
        ).first()

    def _create_pending_job(
        self,
        *,
        user: User,
        company: Graph,
        organization: Organization,
        credential: APIKey,
        modality: str,
        provider: str,
        model: str,
        prompt: str,
        idempotency_key: str,
    ) -> MediaGenerationJob:
        try:
            return MediaGenerationJob.objects.create(
                organization=organization,
                company=company,
                requested_by=user,
                credential=credential,
                modality=modality,
                provider=provider,
                model=model,
                prompt=prompt,
                prompt_hash=prompt_hash(prompt),
                idempotency_key=idempotency_key,
                status="pending",
                request_json={
                    "provider": provider,
                    "model": model,
                    "modality": modality,
                    "prompt_sanitized": True,
                },
            )
        except IntegrityError:
            if idempotency_key:
                existing = MediaGenerationJob.objects.filter(
                    company=company,
                    idempotency_key=idempotency_key,
                ).first()
                if existing is not None:
                    return existing
            raise

    def create_image_job_with_provider_fallback(
        self,
        *,
        user: User,
        company: Graph,
        primary_credential: APIKey,
        fallback_credential: APIKey,
        prompt: str,
        idempotency_key: str,
        primary_model: str = "",
        fallback_model: str = "",
    ) -> MediaGenerationFallbackResult:
        """Create a draft image with Google first and OpenRouter on quota/token limits.

        This helper is intentionally media-only and backend-owned. It records each
        provider attempt as a normal MediaGenerationJob so retries are observable
        without making the engine or test harness authoritative for durable media
        state.
        """

        base_key = idempotency_key.strip()
        if not base_key:
            raise GeminiMediaError(
                "idempotency_key_required",
                "Provider fallback media generation requires an idempotency key.",
            )
        if str(primary_credential.provider or "").strip().lower() != "google":
            raise GeminiMediaError(
                "provider_mismatch",
                "Provider fallback media generation requires a Google primary credential.",
            )
        if str(fallback_credential.provider or "").strip().lower() != "openrouter":
            raise GeminiMediaError(
                "provider_mismatch",
                "Provider fallback media generation requires an OpenRouter fallback credential.",
            )

        primary_job = self.create_job(
            user=user,
            company=company,
            credential=primary_credential,
            modality="image",
            prompt=prompt,
            idempotency_key=_scoped_idempotency_key(base_key, "google"),
            model=primary_model,
        )
        if primary_job.status == "succeeded":
            return MediaGenerationFallbackResult(
                primary_job=primary_job,
                fallback_job=None,
                selected_job=primary_job,
                fallback_used=False,
                fallback_reason="",
            )

        if not is_media_provider_limit_error(primary_job):
            return MediaGenerationFallbackResult(
                primary_job=primary_job,
                fallback_job=None,
                selected_job=primary_job,
                fallback_used=False,
                fallback_reason=primary_job.error_code or "primary_failed",
            )

        fallback_job = self.create_job(
            user=user,
            company=company,
            credential=fallback_credential,
            modality="image",
            prompt=prompt,
            idempotency_key=_scoped_idempotency_key(base_key, "openrouter"),
            model=fallback_model,
        )
        return MediaGenerationFallbackResult(
            primary_job=primary_job,
            fallback_job=fallback_job,
            selected_job=fallback_job,
            fallback_used=True,
            fallback_reason=_media_provider_limit_reason(primary_job),
        )

    def poll_video_job(self, *, job: MediaGenerationJob) -> MediaGenerationJob:
        if job.modality != "video":
            raise GeminiMediaError("invalid_modality", "Only video media jobs can be polled.")
        if job.status == "succeeded":
            return job
        if job.status == "failed":
            return job
        if not job.provider_operation_name:
            raise GeminiMediaError("missing_operation_name", "Video job has no provider operation.")
        if job.credential is None:
            self._mark_failed(
                job,
                code="missing_credential",
                message="Video job credential is unavailable.",
                response_json={},
            )
            return job

        try:
            api_key = self._decrypt_credential(job.credential)
            result = self.client.poll_video(
                api_key=api_key,
                operation_name=job.provider_operation_name,
            )
            if not result.done:
                job.status = "running"
                job.response_json = result.response_json
                job.save(update_fields=["status", "response_json", "updated_at"])
                return job
            assert result.media is not None
            return self._persist_output(job, media=result.media)
        except GeminiMediaError as exc:
            self._mark_failed(
                job,
                code=exc.code,
                message=exc.message,
                response_json=exc.response_json,
            )
            return job
        except OSError as exc:
            self._mark_failed(
                job,
                code="artifact_write_failed",
                message="Media artifact storage is unavailable.",
                response_json={"error": exc.__class__.__name__},
            )
            return job

    def _run_image_job(self, job: MediaGenerationJob) -> MediaGenerationJob:
        try:
            api_key = self._decrypt_credential(job.credential)
            media_client = self._media_client_for_job(job)
            media = media_client.generate_image(
                api_key=api_key,
                model=job.model,
                prompt=job.prompt,
            )
            return self._persist_output(job, media=media)
        except GeminiMediaError as exc:
            self._mark_failed(
                job,
                code=exc.code,
                message=exc.message,
                response_json=exc.response_json,
            )
            return job
        except OSError as exc:
            self._mark_failed(
                job,
                code="artifact_write_failed",
                message="Media artifact storage is unavailable.",
                response_json={"error": exc.__class__.__name__},
            )
            return job

    def _start_video_job(self, job: MediaGenerationJob) -> MediaGenerationJob:
        try:
            if job.provider != "google":
                raise GeminiMediaError(
                    "unsupported_modality",
                    "Video media generation is currently supported only for Google Gemini/Veo credentials.",
                )
            api_key = self._decrypt_credential(job.credential)
            operation_name, response_json = self.client.start_video(
                api_key=api_key,
                model=job.model,
                prompt=job.prompt,
            )
            job.status = "running"
            job.provider_operation_name = operation_name
            job.response_json = response_json
            job.save(
                update_fields=[
                    "status",
                    "provider_operation_name",
                    "response_json",
                    "updated_at",
                ]
            )
            return job
        except GeminiMediaError as exc:
            self._mark_failed(
                job,
                code=exc.code,
                message=exc.message,
                response_json=exc.response_json,
            )
            return job

    def _persist_output(
        self, job: MediaGenerationJob, *, media: GeminiMediaBytes
    ) -> MediaGenerationJob:
        relative_path, content_uri = _write_media_artifact(
            company=job.company,
            job=job,
            content=media.content,
            mime_type=media.mime_type,
        )
        asset = ArchiveService().create_asset(
            company=job.company,
            title=f"{_provider_display_name(job.provider)} {job.modality} draft",
            asset_type=job.modality,
            source_key=f"media-generation:{job.id}",
            created_by_type="system",
            created_by_id=job.requested_by_id,
            metadata={
                "source": "media_generation",
                "provider": job.provider,
                "model": job.model,
                "modality": job.modality,
                "review_status": "draft",
                "media_generation_job_id": str(job.id),
                "approval_required_before_publish": True,
            },
        )
        version = ArchiveService().create_asset_version(
            asset=asset,
            content_uri=content_uri,
            content=media.content,
            mime_type=media.mime_type,
            provenance={
                "source": "media_generation",
                "provider": job.provider,
                "model": job.model,
                "media_generation_job_id": str(job.id),
                "review_status": "draft",
                "artifact_root": "logs/media-generations",
                "artifact_path": relative_path,
                "provider_operation_name": job.provider_operation_name,
            },
        )
        job.status = "succeeded"
        job.output_asset = asset
        job.output_asset_version = version
        job.output_mime_type = media.mime_type
        job.output_size_bytes = len(media.content)
        job.response_json = media.response_json
        job.error_code = ""
        job.error_message = ""
        job.completed_at = timezone.now()
        job.save(
            update_fields=[
                "status",
                "output_asset",
                "output_asset_version",
                "output_mime_type",
                "output_size_bytes",
                "response_json",
                "error_code",
                "error_message",
                "completed_at",
                "updated_at",
            ]
        )
        return job

    def _mark_failed(
        self,
        job: MediaGenerationJob,
        *,
        code: str,
        message: str,
        response_json: dict[str, Any],
    ) -> None:
        job.status = "failed"
        job.error_code = code[:64]
        job.error_message = message[:1000]
        job.response_json = response_json
        job.completed_at = timezone.now()
        job.save(
            update_fields=[
                "status",
                "error_code",
                "error_message",
                "response_json",
                "completed_at",
                "updated_at",
            ]
        )

    def _validate_credential(self, *, company: Graph, credential: APIKey) -> None:
        if credential.organization_id != company.organization_id:
            raise GeminiMediaError(
                "credential_not_found",
                "Media generation credential was not found for this company organization.",
            )
        if str(credential.provider).strip().lower() not in {"google", "openrouter", "openai"}:
            raise GeminiMediaError(
                "provider_mismatch",
                "Media generation requires a Google, OpenRouter, or OpenAI credential.",
            )
        if is_credential_revoked(credential.token_metadata):
            raise GeminiMediaError(
                "credential_revoked", "Media generation credential has been revoked."
            )

    def _media_client_for_job(self, job: MediaGenerationJob) -> Any:
        if job.provider == "openrouter":
            return self.openrouter_client
        if job.provider == "openai":
            return self.openai_client
        return self.client

    def _decrypt_credential(self, credential: APIKey | None) -> str:
        if credential is None:
            raise GeminiMediaError("missing_credential", "Gemini credential is unavailable.")
        try:
            return decrypt_api_key(bytes(credential.encrypted_key)).strip()
        except EncryptionError as exc:
            raise GeminiMediaError(
                "credential_decrypt_failed",
                "Gemini credential cannot be decrypted.",
            ) from exc


def read_media_asset_version_content(version: AssetVersion) -> tuple[bytes, str, str]:
    provenance = version.provenance_json if isinstance(version.provenance_json, dict) else {}
    relative_path = str(provenance.get("artifact_path") or "").strip()
    if not relative_path:
        raise FileNotFoundError("Asset version has no local media artifact.")
    artifact_root = _artifact_root()
    candidate = (artifact_root / relative_path).resolve()
    if not _is_relative_to(candidate, artifact_root):
        raise PermissionError("Asset version artifact path escapes the media artifact root.")
    content = candidate.read_bytes()
    filename = candidate.name
    mime_type = version.mime_type or mimetypes.guess_type(filename)[0] or "application/octet-stream"
    return content, mime_type, filename


def _write_media_artifact(
    *,
    company: Graph,
    job: MediaGenerationJob,
    content: bytes,
    mime_type: str,
) -> tuple[str, str]:
    extension = _extension_for_mime_type(mime_type)
    relative_path = f"{company.id}/{job.id}{extension}"
    artifact_path = (_artifact_root() / relative_path).resolve()
    if not _is_relative_to(artifact_path, _artifact_root()):
        raise PermissionError("Media artifact path escapes the media artifact root.")
    artifact_path.parent.mkdir(parents=True, exist_ok=True)
    artifact_path.write_bytes(content)
    return relative_path, f"forgegraph://media-generations/{relative_path}"


def _artifact_root() -> Path:
    root = Path(settings.MEDIA_GENERATION_ARTIFACT_ROOT).resolve()
    root.mkdir(parents=True, exist_ok=True)
    return root


def _is_relative_to(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
        return True
    except ValueError:
        return False


def _default_model(modality: str, *, provider: str = "google") -> str:
    if provider == "openrouter":
        return str(settings.OPENROUTER_IMAGE_MODEL)
    if provider == "openai":
        return str(settings.OPENAI_IMAGE_MODEL)
    if modality == "image":
        return str(settings.GEMINI_IMAGEN_MODEL)
    return str(settings.GEMINI_VEO_MODEL)


_LIMIT_ERROR_SIGNATURES = (
    "429",
    "too many requests",
    "resource_exhausted",
    "rate limit",
    "rate_limited",
    "quota",
    "token limit",
    "max token",
    "max_tokens",
    "max output",
    "context limit",
    "context_length",
    "context window",
    "finishreason=max_tokens",
    '"finishreason": "max_tokens"',
    '"finish_reason": "max_tokens"',
    "only available on paid plans",
    "upgrade your account",
)


def _limit_error_text(
    *,
    code: str = "",
    message: str = "",
    response_json: dict[str, Any] | None = None,
) -> str:
    try:
        response_text = json.dumps(response_json or {}, sort_keys=True)
    except TypeError:
        response_text = str(response_json or {})
    return f"{code} {message} {response_text}".lower()


def _media_provider_limit_reason(job: MediaGenerationJob) -> str:
    text = _limit_error_text(
        code=job.error_code,
        message=job.error_message,
        response_json=job.response_json,
    )
    for signature in _LIMIT_ERROR_SIGNATURES:
        if signature in text:
            return signature.strip('"').replace(" ", "_")
    return job.error_code or "provider_limit"


def _scoped_idempotency_key(base_key: str, provider: str) -> str:
    suffix = f":{provider}"
    max_base = max(1, 128 - len(suffix))
    return f"{base_key[:max_base]}{suffix}"


def _openrouter_model_outputs_text(model: str) -> bool:
    normalized = model.strip().lower()
    return normalized.startswith("google/gemini") or normalized.startswith("openai/")


def _openai_image_model_accepts_response_format(model: str) -> bool:
    return model.strip().lower().startswith("dall-e-")


def _headers(api_key: str) -> dict[str, str]:
    return {
        "Content-Type": "application/json",
        "x-goog-api-key": api_key,
    }


def _openrouter_headers(api_key: str) -> dict[str, str]:
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}",
    }
    if referer := str(settings.OPENROUTER_HTTP_REFERER or "").strip():
        headers["HTTP-Referer"] = referer
    if title := str(settings.OPENROUTER_APP_TITLE or "").strip():
        headers["X-Title"] = title
    return headers


def _openai_headers(api_key: str) -> dict[str, str]:
    return {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}",
    }


def _provider_display_name(provider: str) -> str:
    if provider == "openai":
        return "OpenAI"
    if provider == "openrouter":
        return "OpenRouter"
    if provider == "google":
        return "Gemini"
    return provider.title() or "Media"


def _model_path(model: str) -> str:
    return model.strip().removeprefix("models/")


def _is_imagen_model(model: str) -> bool:
    normalized = _model_path(model).lower()
    return normalized.startswith("imagen-") or normalized.startswith("imagegeneration@")


def _operation_path(operation_name: str) -> str:
    value = operation_name.strip()
    parsed = urlparse(value)
    if parsed.scheme and parsed.netloc:
        return parsed.path
    return "/" + value.lstrip("/")


def _json_or_provider_error(
    response: requests.Response, *, provider_label: str = "Gemini"
) -> dict[str, Any]:
    try:
        payload = response.json()
    except ValueError:
        payload = {}
    if response.status_code >= 400:
        error_payload = payload.get("error") if isinstance(payload, dict) else {}
        if not isinstance(error_payload, dict):
            error_payload = {}
        message = str(
            error_payload.get("message")
            or response.reason
            or f"{provider_label} request failed with HTTP {response.status_code}."
        )
        raise GeminiMediaError(
            "provider_http_error",
            message,
            status_code=response.status_code,
            retryable=response.status_code == 429 or response.status_code >= 500,
            response_json=_without_large_payloads(payload if isinstance(payload, dict) else {}),
        )
    if not isinstance(payload, dict):
        raise GeminiMediaError(
            "invalid_provider_response", "Gemini response was not a JSON object."
        )
    return payload


def _image_bytes_from_response(response_json: dict[str, Any]) -> GeminiMediaBytes:
    encoded = _first_string(
        response_json,
        [
            ("generatedImages", 0, "image", "imageBytes"),
            ("predictions", 0, "bytesBase64Encoded"),
            ("predictions", 0, "image", "imageBytes"),
            ("candidates", 0, "content", "parts", 0, "inlineData", "data"),
            ("candidates", 0, "content", "parts", 0, "inline_data", "data"),
        ],
    )
    inline_image = _first_inline_image_part(response_json)
    if not encoded and inline_image is not None:
        encoded = inline_image.get("data", "")
    mime_type = (
        _first_string(
            response_json,
            [
                ("generatedImages", 0, "image", "mimeType"),
                ("predictions", 0, "mimeType"),
                ("predictions", 0, "image", "mimeType"),
                ("candidates", 0, "content", "parts", 0, "inlineData", "mimeType"),
                ("candidates", 0, "content", "parts", 0, "inline_data", "mimeType"),
            ],
        )
        or (inline_image.get("mimeType") if inline_image is not None else "")
        or (inline_image.get("mime_type") if inline_image is not None else "")
        or "image/png"
    )
    if not encoded:
        raise GeminiMediaError(
            "missing_image_bytes",
            "Gemini image response did not include image bytes.",
            response_json=_without_large_payloads(response_json),
        )
    try:
        content = base64.b64decode(encoded)
    except ValueError as exc:
        raise GeminiMediaError(
            "invalid_image_bytes", "Gemini image bytes were not base64."
        ) from exc
    return GeminiMediaBytes(
        content=content,
        mime_type=mime_type,
        response_json=_without_large_payloads(response_json),
    )


def _openrouter_image_bytes_from_response(response_json: dict[str, Any]) -> GeminiMediaBytes:
    image_url = _first_string(
        response_json,
        [
            ("choices", 0, "message", "images", 0, "image_url", "url"),
            ("choices", 0, "message", "images", 0, "imageUrl", "url"),
        ],
    )
    if not image_url:
        raise GeminiMediaError(
            "missing_image_bytes",
            "OpenRouter image response did not include image bytes.",
            response_json=_without_large_payloads(response_json),
        )
    content, mime_type = _decode_data_url(image_url)
    return GeminiMediaBytes(
        content=content,
        mime_type=mime_type,
        response_json=_without_large_payloads(response_json),
    )


def _openai_image_bytes_from_response(response_json: dict[str, Any]) -> GeminiMediaBytes:
    encoded = _first_string(response_json, [("data", 0, "b64_json")])
    if not encoded:
        raise GeminiMediaError(
            "missing_image_bytes",
            "OpenAI image response did not include image bytes.",
            response_json=_without_large_payloads(response_json),
        )
    try:
        content = base64.b64decode(encoded)
    except ValueError as exc:
        raise GeminiMediaError(
            "invalid_image_bytes", "OpenAI image bytes were not base64."
        ) from exc
    output_format = str(response_json.get("output_format") or "png").strip().lower()
    mime_type = {
        "jpeg": "image/jpeg",
        "jpg": "image/jpeg",
        "png": "image/png",
        "webp": "image/webp",
    }.get(output_format, "image/png")
    return GeminiMediaBytes(
        content=content,
        mime_type=mime_type,
        response_json=_without_large_payloads(response_json),
    )


def _decode_data_url(value: str) -> tuple[bytes, str]:
    prefix, separator, encoded = value.partition(",")
    if not separator or ";base64" not in prefix:
        raise GeminiMediaError(
            "invalid_image_url", "OpenRouter image URL was not a base64 data URL."
        )
    mime_type = prefix.removeprefix("data:").split(";", 1)[0] or "image/png"
    try:
        return base64.b64decode(encoded), mime_type
    except ValueError as exc:
        raise GeminiMediaError(
            "invalid_image_bytes", "OpenRouter image bytes were not base64."
        ) from exc


def _first_inline_image_part(response_json: dict[str, Any]) -> dict[str, Any] | None:
    candidates = response_json.get("candidates")
    if not isinstance(candidates, list):
        return None
    for candidate in candidates:
        if not isinstance(candidate, dict):
            continue
        content = candidate.get("content")
        if not isinstance(content, dict):
            continue
        parts = content.get("parts")
        if not isinstance(parts, list):
            continue
        for part in parts:
            if not isinstance(part, dict):
                continue
            inline_data = part.get("inlineData") or part.get("inline_data")
            if not isinstance(inline_data, dict):
                continue
            encoded = inline_data.get("data")
            if isinstance(encoded, str) and encoded.strip():
                return inline_data
    return None


def _inline_video_from_response(response_json: dict[str, Any]) -> GeminiMediaBytes | None:
    encoded = _first_string(
        response_json,
        [
            ("response", "generatedVideos", 0, "video", "bytesBase64Encoded"),
            ("response", "generated_videos", 0, "video", "bytesBase64Encoded"),
            ("response", "generatedVideos", 0, "video", "videoBytes"),
            ("response", "generated_videos", 0, "video", "videoBytes"),
        ],
    )
    if not encoded:
        return None
    try:
        content = base64.b64decode(encoded)
    except ValueError as exc:
        raise GeminiMediaError(
            "invalid_video_bytes", "Gemini video bytes were not base64."
        ) from exc
    return GeminiMediaBytes(
        content=content,
        mime_type="video/mp4",
        response_json=_without_large_payloads(response_json),
    )


def _first_string(payload: dict[str, Any], paths: list[tuple[Any, ...]]) -> str:
    for path in paths:
        value: Any = payload
        for part in path:
            if isinstance(part, int):
                if not isinstance(value, list) or len(value) <= part:
                    value = None
                    break
                value = value[part]
                continue
            if not isinstance(value, dict):
                value = None
                break
            value = value.get(part)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def _without_large_payloads(payload: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(payload, dict):
        return {}
    scrubbed: dict[str, Any] = {}
    for key, value in payload.items():
        if key in {"imageBytes", "bytesBase64Encoded", "videoBytes", "data"}:
            scrubbed[key] = "[omitted]"
        elif isinstance(value, dict):
            scrubbed[key] = _without_large_payloads(value)
        elif isinstance(value, list):
            scrubbed[key] = [
                _without_large_payloads(item) if isinstance(item, dict) else item for item in value
            ]
        else:
            scrubbed[key] = value
    return scrubbed


def _extension_for_mime_type(mime_type: str) -> str:
    if mime_type == "image/jpeg":
        return ".jpg"
    if mime_type == "image/png":
        return ".png"
    if mime_type == "video/mp4":
        return ".mp4"
    return mimetypes.guess_extension(mime_type or "") or ".bin"


def _int_or_none(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
