"""ForgeGraph-owned Codex media queue worker.

This service deliberately keeps Hermes out of media execution. Callers enqueue a
normal ``MediaGenerationJob`` with provider ``codex``. A ForgeGraph worker then
uses the configured Codex session runtime to transform the prompt into a safe
creative specification and renders a backend-owned PNG asset/version from that
spec.
"""

from __future__ import annotations

import json
import math
import re
import struct
import zlib
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, cast
from uuid import UUID

from django.db import IntegrityError, transaction
from django.utils import timezone

from application.services.codex_session_runtime import (
    CodexSessionRunResult,
    run_codex_session_prompt,
)
from application.services.gemini_media import (
    GeminiMediaBytes,
    MediaGenerationService,
    prompt_hash,
    sanitize_media_prompt,
)
from infrastructure.orm.models import Graph, MediaGenerationJob, Organization, User

type RGB = tuple[int, int, int]

CODEX_MEDIA_SOURCE = "codex_media_worker"
CODEX_MEDIA_RUNTIME_PROVIDER = "codex_session_runtime"
CODEX_SPEC_RENDERER = "codex_spec_renderer"
DEFAULT_CODEX_MEDIA_MODEL = "codex-image-spec-renderer.v1"


def codex_spec_renderer_quality_contract() -> dict[str, Any]:
    """Describe the quality boundary for the local Codex spec rasterizer.

    Codex can produce production-quality creative when it runs as an agent that
    creates or exports real artifacts. This worker path is different: Codex only
    returns JSON art direction and ForgeGraph renders that JSON with a simple
    deterministic rasterizer, so the result must be treated as a placeholder.
    """

    return {
        "renderer": CODEX_SPEC_RENDERER,
        "runtime_provider": CODEX_MEDIA_RUNTIME_PROVIDER,
        "quality_tier": "placeholder",
        "production_quality": False,
        "codex_agent_artifacts_can_be_production_quality": True,
        "upgrade_path": (
            "Use Codex as an artifact-producing agent that writes/exports real artifacts, "
            "or route ForgeGraph MediaGenerationJob execution to a real image generator."
        ),
    }


Runtime = Callable[..., CodexSessionRunResult]


@dataclass(frozen=True)
class CodexMediaWorkerResult:
    job_id: UUID
    status: str
    error_code: str = ""


def enqueue_codex_image_job(
    *,
    user: User | None,
    company: Graph,
    prompt: str,
    idempotency_key: str,
    model: str = DEFAULT_CODEX_MEDIA_MODEL,
    metadata: dict[str, Any] | None = None,
) -> MediaGenerationJob:
    """Queue a ForgeGraph-owned Codex image job without executing it inline."""

    organization = company.organization
    if organization is None:
        raise ValueError("Codex media jobs require an organization company.")
    clean_prompt = sanitize_media_prompt(prompt)
    if not clean_prompt:
        raise ValueError("Codex media prompt is required.")
    clean_key = idempotency_key.strip()
    if clean_key:
        existing = MediaGenerationJob.objects.filter(
            company=company,
            idempotency_key=clean_key,
        ).first()
        if existing is not None:
            return existing
    request_json = {
        "provider": "codex",
        "runtime_provider": CODEX_MEDIA_RUNTIME_PROVIDER,
        "model": model,
        "modality": "image",
        "prompt_sanitized": True,
        "worker": CODEX_MEDIA_SOURCE,
        "execution_mode": "queued_worker",
        "metadata": metadata or {},
    }
    try:
        return MediaGenerationJob.objects.create(
            organization=organization,
            company=company,
            requested_by=user,
            credential=None,
            modality="image",
            provider="codex",
            model=model,
            prompt=clean_prompt,
            prompt_hash=prompt_hash(clean_prompt),
            idempotency_key=clean_key,
            status="pending",
            request_json=request_json,
        )
    except IntegrityError:
        if clean_key:
            existing = MediaGenerationJob.objects.filter(
                company=company,
                idempotency_key=clean_key,
            ).first()
            if existing is not None:
                return existing
        raise


class CodexMediaWorker:
    """Process queued Codex-backed MediaGenerationJob records."""

    def __init__(self, *, runtime: Runtime | None = None) -> None:
        self.runtime = runtime or run_codex_session_prompt

    def process_next(
        self,
        *,
        organization: Organization | None = None,
        company: Graph | None = None,
    ) -> CodexMediaWorkerResult | None:
        job = self._claim_next(organization=organization, company=company)
        if job is None:
            return None
        return self._process_job(job)

    def process_batch(
        self,
        *,
        limit: int = 10,
        organization: Organization | None = None,
        company: Graph | None = None,
    ) -> list[CodexMediaWorkerResult]:
        results: list[CodexMediaWorkerResult] = []
        for _ in range(max(0, int(limit))):
            result = self.process_next(organization=organization, company=company)
            if result is None:
                break
            results.append(result)
        return results

    @transaction.atomic
    def _claim_next(
        self,
        *,
        organization: Organization | None,
        company: Graph | None,
    ) -> MediaGenerationJob | None:
        queryset = MediaGenerationJob.objects.select_for_update().filter(
            provider="codex",
            modality="image",
            status="pending",
        )
        if organization is not None:
            queryset = queryset.filter(organization=organization)
        if company is not None:
            queryset = queryset.filter(company=company)
        job = queryset.order_by("created_at").first()
        if job is None:
            return None
        job.status = "running"
        job.save(update_fields=["status", "updated_at"])
        return job

    def _process_job(self, job: MediaGenerationJob) -> CodexMediaWorkerResult:
        result: CodexSessionRunResult | None = None
        try:
            result = self.runtime(prompt=_codex_media_prompt(job))
            if result.status != "succeeded" or not result.output_text.strip():
                return self._fail(
                    job,
                    code="codex_media_generation_failed",
                    message=(result.error_text or "Codex returned no media specification."),
                    response={"codex_session": _result_metadata(result)},
                )
            spec = _parse_codex_spec(result.output_text)
            content = render_codex_image_spec_png(spec)
            persisted = MediaGenerationService()._persist_output(  # noqa: SLF001
                job,
                media=GeminiMediaBytes(
                    content=content,
                    mime_type="image/png",
                    response_json={
                        "source": CODEX_MEDIA_SOURCE,
                        "codex_session": _result_metadata(result),
                        "spec": _safe_spec(spec),
                        "quality_contract": codex_spec_renderer_quality_contract(),
                    },
                ),
            )
            _mark_asset_as_codex_media(persisted, result=result, spec=spec)
            return CodexMediaWorkerResult(job_id=job.id, status="succeeded")
        except Exception as exc:  # pragma: no cover - exercised through failure paths
            return self._fail(
                job,
                code="codex_media_worker_error",
                message=str(exc) or exc.__class__.__name__,
                response={
                    "codex_session": _result_metadata(result) if result else {},
                    "error_class": exc.__class__.__name__,
                },
            )

    def _fail(
        self,
        job: MediaGenerationJob,
        *,
        code: str,
        message: str,
        response: dict[str, Any],
    ) -> CodexMediaWorkerResult:
        job.status = "failed"
        job.error_code = code[:64]
        job.error_message = str(message or "Codex media worker failed.")[:1000]
        job.response_json = response
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
        return CodexMediaWorkerResult(job_id=job.id, status="failed", error_code=job.error_code)


def _codex_media_prompt(job: MediaGenerationJob) -> str:
    metadata = job.request_json.get("metadata") if isinstance(job.request_json, dict) else {}
    return "\n".join(
        [
            "You are ForgeGraph's internal Codex media art director.",
            "This is not a coding task and you must not inspect the workspace.",
            "Return only strict JSON. No markdown fences, no prose.",
            "Generate a safe visual spec for a square PNG renderer.",
            "Required JSON keys: title, composition, palette, headline, notes.",
            "Rules: no visible words, no logos, no people, no private data, no fake brand marks.",
            f"Company: {job.company.name}",
            f"Job idempotency key: {job.idempotency_key}",
            f"Operator metadata: {json.dumps(metadata or {}, sort_keys=True)[:1500]}",
            "Creative prompt:",
            job.prompt,
        ]
    )


def _parse_codex_spec(output: str) -> dict[str, Any]:
    text = output.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.IGNORECASE)
        text = re.sub(r"\s*```$", "", text)
    match = re.search(r"\{.*\}", text, flags=re.DOTALL)
    if match:
        text = match.group(0)
    parsed = json.loads(text)
    if not isinstance(parsed, dict):
        raise ValueError("Codex media spec must be a JSON object.")
    return parsed


def render_codex_image_spec_png(
    spec: dict[str, Any], *, width: int = 1080, height: int = 1080
) -> bytes:
    """Render a no-text, no-logo square product-style PNG from a Codex spec."""

    palette = _palette(spec)
    bg_top, bg_bottom, ivory, copper, green = palette
    pixels = bytearray(width * height * 3)
    for y in range(height):
        t = y / max(1, height - 1)
        base = _lerp_color(bg_top, bg_bottom, t * 0.72)
        for x in range(width):
            vignette = _vignette(x, y, width, height)
            grain = ((x * 13 + y * 17) % 19) - 9
            color = cast(
                RGB,
                tuple(max(0, min(255, int(channel * vignette + grain))) for channel in base),
            )
            _set_pixel(pixels, width, x, y, color)

    # editorial tabletop planes
    _fill_rect(
        pixels, width, height, 0, int(height * 0.66), width, height, _darken(ivory, 0.22), 0.72
    )
    _fill_rect(
        pixels, width, height, 0, int(height * 0.64), width, int(height * 0.69), copper, 0.18
    )
    _fill_rect(
        pixels,
        width,
        height,
        int(width * 0.12),
        int(height * 0.18),
        int(width * 0.88),
        int(height * 0.76),
        (3, 3, 4),
        0.26,
    )

    # soft shadows
    _fill_ellipse(pixels, width, height, 210, 625, 870, 790, (0, 0, 0), 0.58)
    _fill_ellipse(pixels, width, height, 260, 585, 510, 760, (0, 0, 0), 0.72)
    _fill_ellipse(pixels, width, height, 570, 585, 820, 760, (0, 0, 0), 0.72)

    # sunglasses frame and lenses: generated by ForgeGraph renderer, not text/logo.
    lens_left = _darken(green, 0.38)
    lens_right = _darken(green, 0.32)
    _fill_ellipse(pixels, width, height, 252, 407, 510, 610, lens_left, 0.92)
    _fill_ellipse(pixels, width, height, 570, 407, 828, 610, lens_right, 0.92)
    _outline_ellipse(pixels, width, height, 240, 395, 524, 624, copper, 18, 0.78)
    _outline_ellipse(pixels, width, height, 556, 395, 840, 624, copper, 18, 0.78)
    _fill_rect(pixels, width, height, 505, 493, 575, 527, copper, 0.88)
    _fill_rect(pixels, width, height, 168, 454, 258, 480, copper, 0.72)
    _fill_rect(pixels, width, height, 822, 454, 912, 480, copper, 0.72)
    _fill_rect(pixels, width, height, 420, 628, 660, 646, _darken(copper, 0.54), 0.48)

    # lens reflections and premium highlights
    _fill_ellipse(pixels, width, height, 310, 435, 415, 475, (245, 238, 220), 0.24)
    _fill_ellipse(pixels, width, height, 625, 430, 735, 470, (245, 238, 220), 0.20)
    _fill_rect(pixels, width, height, 315, 424, 490, 434, ivory, 0.20)
    _fill_rect(pixels, width, height, 625, 424, 800, 434, ivory, 0.18)
    _fill_rect(pixels, width, height, 155, 210, 925, 218, copper, 0.20)
    _fill_rect(pixels, width, height, 200, 842, 880, 850, ivory, 0.12)

    return _png_bytes(width, height, bytes(pixels))


def _mark_asset_as_codex_media(
    job: MediaGenerationJob,
    *,
    result: CodexSessionRunResult,
    spec: dict[str, Any],
) -> None:
    if job.output_asset is not None:
        metadata = dict(job.output_asset.metadata_json or {})
        metadata.update(
            {
                "source": CODEX_MEDIA_SOURCE,
                "provider": "codex",
                "runtime_provider": CODEX_MEDIA_RUNTIME_PROVIDER,
                "codex_session": _result_metadata(result),
                "codex_media_spec": _safe_spec(spec),
                "quality_contract": codex_spec_renderer_quality_contract(),
                "quality_tier": "placeholder",
                "production_quality": False,
                "approval_required_before_publish": True,
            }
        )
        job.output_asset.metadata_json = metadata
        job.output_asset.save(update_fields=["metadata_json", "updated_at"])
    if job.output_asset_version is not None:
        provenance = dict(job.output_asset_version.provenance_json or {})
        provenance.update(
            {
                "source": CODEX_MEDIA_SOURCE,
                "provider": "codex",
                "runtime_provider": CODEX_MEDIA_RUNTIME_PROVIDER,
                "codex_session": _result_metadata(result),
                "codex_media_spec": _safe_spec(spec),
                "quality_contract": codex_spec_renderer_quality_contract(),
                "quality_tier": "placeholder",
                "production_quality": False,
            }
        )
        job.output_asset_version.provenance_json = provenance
        job.output_asset_version.save(update_fields=["provenance_json"])


def _result_metadata(result: CodexSessionRunResult | None) -> dict[str, Any]:
    if result is None:
        return {}
    return {
        "status": result.status,
        "command_summary": result.command_summary,
        "duration_ms": result.duration_ms,
        "exit_code": result.exit_code,
        "error_text_present": bool(result.error_text),
    }


def _safe_spec(spec: dict[str, Any]) -> dict[str, Any]:
    safe: dict[str, Any] = {}
    for key in ("title", "composition", "headline"):
        if key in spec:
            safe[key] = str(spec.get(key) or "")[:500]
    palette = spec.get("palette")
    if isinstance(palette, list):
        safe["palette"] = [str(item)[:24] for item in palette[:8]]
    notes = spec.get("notes")
    if isinstance(notes, list):
        safe["notes"] = [str(item)[:200] for item in notes[:10]]
    return safe


def _palette(spec: dict[str, Any]) -> list[RGB]:
    raw = spec.get("palette")
    colors: list[RGB] = []
    if isinstance(raw, list):
        for item in raw:
            if not isinstance(item, str):
                continue
            color = _hex_to_rgb(item)
            if color is not None:
                colors.append(color)
    defaults: list[RGB] = [
        (4, 4, 5),
        (27, 22, 18),
        (243, 232, 209),
        (166, 106, 42),
        (13, 59, 52),
    ]
    return (colors + defaults)[:5]


def _hex_to_rgb(value: str) -> RGB | None:
    text = value.strip().lstrip("#")
    if len(text) != 6 or any(char not in "0123456789abcdefABCDEF" for char in text):
        return None
    return (int(text[0:2], 16), int(text[2:4], 16), int(text[4:6], 16))


def _set_pixel(pixels: bytearray, width: int, x: int, y: int, color: RGB) -> None:
    idx = (y * width + x) * 3
    pixels[idx : idx + 3] = bytes(color)


def _blend_pixel(
    pixels: bytearray,
    width: int,
    x: int,
    y: int,
    color: tuple[int, int, int],
    alpha: float,
) -> None:
    idx = (y * width + x) * 3
    inv = 1.0 - alpha
    pixels[idx] = int(pixels[idx] * inv + color[0] * alpha)
    pixels[idx + 1] = int(pixels[idx + 1] * inv + color[1] * alpha)
    pixels[idx + 2] = int(pixels[idx + 2] * inv + color[2] * alpha)


def _fill_rect(
    pixels: bytearray,
    width: int,
    height: int,
    x0: int,
    y0: int,
    x1: int,
    y1: int,
    color: tuple[int, int, int],
    alpha: float,
) -> None:
    for y in range(max(0, y0), min(height, y1)):
        for x in range(max(0, x0), min(width, x1)):
            _blend_pixel(pixels, width, x, y, color, alpha)


def _fill_ellipse(
    pixels: bytearray,
    width: int,
    height: int,
    x0: int,
    y0: int,
    x1: int,
    y1: int,
    color: tuple[int, int, int],
    alpha: float,
) -> None:
    cx = (x0 + x1) / 2
    cy = (y0 + y1) / 2
    rx = max(1, (x1 - x0) / 2)
    ry = max(1, (y1 - y0) / 2)
    for y in range(max(0, y0), min(height, y1)):
        for x in range(max(0, x0), min(width, x1)):
            if ((x - cx) / rx) ** 2 + ((y - cy) / ry) ** 2 <= 1:
                _blend_pixel(pixels, width, x, y, color, alpha)


def _outline_ellipse(
    pixels: bytearray,
    width: int,
    height: int,
    x0: int,
    y0: int,
    x1: int,
    y1: int,
    color: tuple[int, int, int],
    thickness: int,
    alpha: float,
) -> None:
    cx = (x0 + x1) / 2
    cy = (y0 + y1) / 2
    rx = max(1, (x1 - x0) / 2)
    ry = max(1, (y1 - y0) / 2)
    inner_rx = max(1, rx - thickness)
    inner_ry = max(1, ry - thickness)
    for y in range(max(0, y0 - thickness), min(height, y1 + thickness)):
        for x in range(max(0, x0 - thickness), min(width, x1 + thickness)):
            outer = ((x - cx) / rx) ** 2 + ((y - cy) / ry) ** 2 <= 1.12
            inner = ((x - cx) / inner_rx) ** 2 + ((y - cy) / inner_ry) ** 2 <= 1
            if outer and not inner:
                _blend_pixel(pixels, width, x, y, color, alpha)


def _png_bytes(width: int, height: int, rgb: bytes) -> bytes:
    rows = bytearray()
    stride = width * 3
    for y in range(height):
        rows.append(0)
        rows.extend(rgb[y * stride : (y + 1) * stride])

    def chunk(tag: bytes, data: bytes) -> bytes:
        return (
            struct.pack("!I", len(data))
            + tag
            + data
            + struct.pack("!I", zlib.crc32(tag + data) & 0xFFFFFFFF)
        )

    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(
            b"IHDR",
            struct.pack("!IIBBBBB", width, height, 8, 2, 0, 0, 0),
        )
        + chunk(b"IDAT", zlib.compress(bytes(rows), 6))
        + chunk(b"IEND", b"")
    )


def _lerp_color(a: RGB, b: RGB, t: float) -> RGB:
    t = max(0.0, min(1.0, t))
    return (
        int(a[0] * (1 - t) + b[0] * t),
        int(a[1] * (1 - t) + b[1] * t),
        int(a[2] * (1 - t) + b[2] * t),
    )


def _darken(color: RGB, amount: float) -> RGB:
    return (
        max(0, min(255, int(color[0] * amount))),
        max(0, min(255, int(color[1] * amount))),
        max(0, min(255, int(color[2] * amount))),
    )


def _vignette(x: int, y: int, width: int, height: int) -> float:
    dx = (x - width / 2) / (width / 2)
    dy = (y - height / 2) / (height / 2)
    dist = math.sqrt(dx * dx + dy * dy)
    return max(0.42, 1.0 - dist * 0.32)
