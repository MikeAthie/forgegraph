from __future__ import annotations

import json
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import requests
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError, CommandParser

from application.services.gemini_media import (
    MediaGenerationService,
    media_generation_job_payload,
    sanitize_media_prompt,
)
from infrastructure.crypto.encryption import decrypt_api_key
from infrastructure.orm.management.commands._legacy_gemini_bootstrap import (
    LEGACY_GEMINI_ENV,
    LegacyGeminiBootstrapError,
    import_legacy_gemini_credential,
)
from infrastructure.orm.management.commands.seed_legacy_glasswear_phase0 import (
    DEFAULT_EMAIL,
    DEFAULT_GEMINI_MODEL,
    EXTERNAL_REF,
    EXTERNAL_SOURCE,
)
from infrastructure.orm.models import APIKey, Graph, User

TEXT_PROMPT = (
    "Legacy Glasswear Phase 1 sanitized context: limited 62-piece designer frame "
    "inventory, no customer PII, no payment data. Return one concise content angle "
    "and one operator risk for a measured drop test."
)
IMAGE_PROMPT = (
    "Create a premium product-campaign image draft for Legacy Glasswear: limited "
    "designer optical frames on a clean editorial surface, high-end retail lighting, "
    "no text, no logos, no people, no private customer data."
)
VIDEO_PROMPT = (
    "Create a short premium product video draft for Legacy Glasswear: slow cinematic "
    "movement across limited designer optical frames, clean editorial setting, no text, "
    "no logos, no people, no private customer data."
)


class Command(BaseCommand):
    help = "Run the Legacy Glasswear Phase 1 Gemini BYOK and media smoke."

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument("--email", default=DEFAULT_EMAIL)
        parser.add_argument("--env-var", default=LEGACY_GEMINI_ENV)
        parser.add_argument("--json", action="store_true", dest="output_json")
        parser.add_argument("--video-poll-attempts", type=int, default=20)
        parser.add_argument("--video-poll-interval-seconds", type=float, default=20.0)
        parser.add_argument("--evidence-dir", default="docs/legacy-ultimate-test")

    def handle(self, *args: Any, **options: Any) -> None:
        timestamp = datetime.now(UTC).strftime("%Y-%m-%d-%H%M%S")
        errors: list[str] = []

        try:
            credential_result = import_legacy_gemini_credential(
                email=str(options["email"]),
                env_var=str(options["env_var"]),
            )
        except LegacyGeminiBootstrapError as exc:
            raise CommandError(str(exc)) from exc

        user = User.objects.get(id=credential_result.user_id)
        company = Graph.objects.get(
            id=credential_result.company_id,
            external_source=EXTERNAL_SOURCE,
            external_ref=EXTERNAL_REF,
        )
        credential = APIKey.objects.get(id=credential_result.credential_id)

        text_probe = _run_gemini_text_probe(credential=credential, prompt=TEXT_PROMPT)
        if text_probe["status"] != "succeeded":
            errors.append(f"Gemini text probe failed: {text_probe.get('error_message')}")

        service = MediaGenerationService()
        image_job = service.create_job(
            user=user,
            company=company,
            credential=credential,
            modality="image",
            prompt=IMAGE_PROMPT,
            idempotency_key=f"legacy-phase1-smoke:{timestamp}:image",
        )
        if image_job.status != "succeeded":
            errors.append(f"Gemini image generation failed: {image_job.error_message}")

        video_job = service.create_job(
            user=user,
            company=company,
            credential=credential,
            modality="video",
            prompt=VIDEO_PROMPT,
            idempotency_key=f"legacy-phase1-smoke:{timestamp}:video",
        )
        attempts = max(0, int(options["video_poll_attempts"]))
        interval_seconds = max(0.0, float(options["video_poll_interval_seconds"]))
        for attempt in range(attempts):
            if video_job.status != "running":
                break
            if attempt > 0 and interval_seconds:
                time.sleep(interval_seconds)
            video_job = service.poll_video_job(job=video_job)
        if video_job.status != "succeeded":
            errors.append(f"Gemini video generation did not succeed: {video_job.error_message}")

        payload = {
            "phase": "phase-1-gemini-byok-media-proof",
            "created_at": datetime.now(UTC).isoformat(),
            "credential": credential_result.as_dict(),
            "text_probe": text_probe,
            "image_job": media_generation_job_payload(image_job),
            "video_job": media_generation_job_payload(video_job),
            "artifact_root": str(settings.MEDIA_GENERATION_ARTIFACT_ROOT),
            "status": "failed" if errors else "succeeded",
            "errors": errors,
        }
        evidence_path = _write_evidence(
            evidence_dir=str(options["evidence_dir"]),
            timestamp=timestamp,
            payload=payload,
        )
        payload["evidence_path"] = evidence_path

        if options["output_json"]:
            self.stdout.write(json.dumps(payload, indent=2, sort_keys=True))
        else:
            self.stdout.write(f"Phase 1 evidence: {evidence_path}")

        if errors:
            raise CommandError("; ".join(errors))


def _run_gemini_text_probe(*, credential: APIKey, prompt: str) -> dict[str, Any]:
    started_at = time.monotonic()
    try:
        api_key = decrypt_api_key(bytes(credential.encrypted_key)).strip()
        sanitized_prompt = sanitize_media_prompt(prompt)
        response = requests.post(
            f"{settings.GEMINI_API_BASE_URL}/models/{DEFAULT_GEMINI_MODEL}:generateContent",
            headers={
                "Content-Type": "application/json",
                "x-goog-api-key": api_key,
            },
            json={
                "contents": [{"role": "user", "parts": [{"text": sanitized_prompt}]}],
                "generationConfig": {"temperature": 0.2, "maxOutputTokens": 256},
            },
            timeout=120,
        )
        latency_ms = int((time.monotonic() - started_at) * 1000)
        payload = _response_json(response)
        if response.status_code >= 400:
            error_payload = payload.get("error")
            error: dict[str, Any] = error_payload if isinstance(error_payload, dict) else {}
            return {
                "status": "failed",
                "provider": "google",
                "model": DEFAULT_GEMINI_MODEL,
                "latency_ms": latency_ms,
                "status_code": response.status_code,
                "error_message": str(error.get("message") or response.reason),
            }
        text = _first_text(payload)
        usage = (
            payload.get("usageMetadata") if isinstance(payload.get("usageMetadata"), dict) else {}
        )
        finish_reason = ""
        candidates = payload.get("candidates")
        if isinstance(candidates, list) and candidates and isinstance(candidates[0], dict):
            finish_reason = str(candidates[0].get("finishReason") or "")
        return {
            "status": "succeeded",
            "provider": "google",
            "model": str(payload.get("modelVersion") or DEFAULT_GEMINI_MODEL),
            "latency_ms": latency_ms,
            "finish_reason": finish_reason,
            "usage": usage,
            "content_preview": text[:500],
        }
    except Exception as exc:
        latency_ms = int((time.monotonic() - started_at) * 1000)
        return {
            "status": "failed",
            "provider": "google",
            "model": DEFAULT_GEMINI_MODEL,
            "latency_ms": latency_ms,
            "error_message": str(exc),
        }


def _response_json(response: requests.Response) -> dict[str, Any]:
    try:
        payload = response.json()
    except ValueError:
        return {}
    return payload if isinstance(payload, dict) else {}


def _first_text(payload: dict[str, Any]) -> str:
    candidates = payload.get("candidates")
    if not isinstance(candidates, list) or not candidates:
        return ""
    first = candidates[0]
    if not isinstance(first, dict):
        return ""
    content = first.get("content")
    if not isinstance(content, dict):
        return ""
    parts = content.get("parts")
    if not isinstance(parts, list):
        return ""
    return "".join(str(part.get("text") or "") for part in parts if isinstance(part, dict))


def _write_evidence(*, evidence_dir: str, timestamp: str, payload: dict[str, Any]) -> str:
    root = Path(settings.BASE_DIR).parent / evidence_dir
    root.mkdir(parents=True, exist_ok=True)
    path = root / f"phase-1-gemini-media-evidence-{timestamp}.md"
    body = [
        "# Phase 1 Gemini BYOK Media Evidence",
        "",
        f"- Status: `{payload['status']}`",
        f"- Created at: `{payload['created_at']}`",
        f"- Credential ID: `{payload['credential']['credential_id']}`",
        f"- Provider: `{payload['credential']['provider']}`",
        f"- Key present: `{payload['credential']['key_present']}`",
        f"- Text probe status: `{payload['text_probe']['status']}`",
        f"- Image job: `{payload['image_job']['id']}` / `{payload['image_job']['status']}`",
        f"- Video job: `{payload['video_job']['id']}` / `{payload['video_job']['status']}`",
        f"- Artifact root: `{payload['artifact_root']}`",
        "",
        "## Raw Summary",
        "",
        "```json",
        json.dumps(payload, indent=2, sort_keys=True),
        "```",
        "",
    ]
    path.write_text("\n".join(body), encoding="utf-8")
    return str(path)
