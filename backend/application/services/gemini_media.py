"""Backend-owned Gemini media generation services for company draft assets."""

from __future__ import annotations

import base64
import hashlib
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
from infrastructure.orm.models import APIKey, AssetVersion, Graph, MediaGenerationJob, User

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


def sanitize_media_prompt(prompt: str) -> str:
    """Remove obvious PII before storing or sending media context to Gemini."""

    sanitized = _EMAIL_RE.sub("[redacted-email]", str(prompt or ""))
    sanitized = _LONG_NUMBER_RE.sub("[redacted-number]", sanitized)
    sanitized = _WHITESPACE_RE.sub(" ", sanitized).strip()
    return sanitized[:MAX_MEDIA_PROMPT_CHARS]


def prompt_hash(prompt: str) -> str:
    return hashlib.sha256(prompt.encode("utf-8")).hexdigest()


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


class MediaGenerationService:
    """Create and poll backend-owned media jobs for a company."""

    def __init__(self, *, client: Any | None = None) -> None:
        self.client = client or GoogleMediaClient()

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

        idempotency_key = idempotency_key.strip()
        if idempotency_key:
            existing = MediaGenerationJob.objects.filter(
                company=company,
                idempotency_key=idempotency_key,
            ).first()
            if existing is not None:
                return existing

        sanitized_prompt = sanitize_media_prompt(prompt)
        if not sanitized_prompt:
            raise GeminiMediaError("empty_prompt", "Media prompt is required.")
        selected_model = model.strip() or _default_model(modality)

        try:
            job = MediaGenerationJob.objects.create(
                organization=organization,
                company=company,
                requested_by=user,
                credential=credential,
                modality=modality,
                provider="google",
                model=selected_model,
                prompt=sanitized_prompt,
                prompt_hash=prompt_hash(sanitized_prompt),
                idempotency_key=idempotency_key,
                status="pending",
                request_json={
                    "provider": "google",
                    "model": selected_model,
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

        if modality == "image":
            return self._run_image_job(job)
        return self._start_video_job(job)

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

    def _run_image_job(self, job: MediaGenerationJob) -> MediaGenerationJob:
        try:
            api_key = self._decrypt_credential(job.credential)
            media = self.client.generate_image(
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

    def _start_video_job(self, job: MediaGenerationJob) -> MediaGenerationJob:
        try:
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
            title=f"Gemini {job.modality} draft",
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
                "Gemini credential was not found for this company organization.",
            )
        if str(credential.provider).strip().lower() != "google":
            raise GeminiMediaError(
                "provider_mismatch", "Media generation requires a Google credential."
            )
        if is_credential_revoked(credential.token_metadata):
            raise GeminiMediaError("credential_revoked", "Gemini credential has been revoked.")

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


def _default_model(modality: str) -> str:
    if modality == "image":
        return str(settings.GEMINI_IMAGEN_MODEL)
    return str(settings.GEMINI_VEO_MODEL)


def _headers(api_key: str) -> dict[str, str]:
    return {
        "Content-Type": "application/json",
        "x-goog-api-key": api_key,
    }


def _model_path(model: str) -> str:
    return model.strip().removeprefix("models/")


def _operation_path(operation_name: str) -> str:
    value = operation_name.strip()
    parsed = urlparse(value)
    if parsed.scheme and parsed.netloc:
        return parsed.path
    return "/" + value.lstrip("/")


def _json_or_provider_error(response: requests.Response) -> dict[str, Any]:
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
            or f"Gemini request failed with HTTP {response.status_code}."
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
