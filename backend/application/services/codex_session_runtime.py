"""Local Codex-session runtime for operator-owned ForgeGraph testing.

This adapter deliberately treats Codex as a local/dev runtime, not a persisted
customer credential. It never reads or stores Codex OAuth files; it only invokes
``codex exec`` through the operator's existing shell session and persists the
result as normal ForgeGraph artifacts.
"""

from __future__ import annotations

import hashlib
import subprocess
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from django.conf import settings
from django.db import transaction

from application.services.company_run_task_routing import attach_deliverable_to_stage_task
from application.services.department_pipeline import (
    attach_asset_to_stage,
    attach_deliverable_to_stage,
)
from infrastructure.orm.models import (
    Asset,
    AssetVersion,
    ProgramStageState,
    ServiceDeliverable,
    ServiceEngagement,
    User,
)

CODEX_SESSION_SOURCE = "codex_session_runtime"


class CodexSessionRuntimeDisabled(RuntimeError):
    """Raised when the local Codex runtime is used without explicit opt-in."""


class CodexSessionRuntimeError(RuntimeError):
    """Raised when Codex returns no usable deliverable output."""


@dataclass(frozen=True)
class CodexSessionRunResult:
    status: Literal["succeeded", "failed"]
    output_text: str
    error_text: str
    command_summary: str
    duration_ms: int
    exit_code: int


Runner = Callable[..., CodexSessionRunResult]


def run_codex_session_prompt(
    *,
    prompt: str,
    runner: Runner | None = None,
    workdir: str | Path | None = None,
    timeout_seconds: int | None = None,
) -> CodexSessionRunResult:
    """Invoke the operator's local Codex session for a text-only prompt."""

    _assert_enabled()
    clean_prompt = _clean_prompt(prompt)
    codex_command = str(getattr(settings, "CODEX_SESSION_COMMAND", "codex") or "codex")
    command = [codex_command, "exec"]
    resolved_workdir = str(workdir or getattr(settings, "CODEX_SESSION_WORKDIR", "."))
    resolved_timeout = int(
        timeout_seconds or getattr(settings, "CODEX_SESSION_TIMEOUT_SECONDS", 180)
    )
    if runner is not None:
        return runner(command, cwd=resolved_workdir, timeout=resolved_timeout, prompt=clean_prompt)
    return _subprocess_runner(
        command,
        cwd=resolved_workdir,
        timeout=resolved_timeout,
        input_text=clean_prompt,
    )


@transaction.atomic
def build_codex_deliverable_for_stage(
    *,
    engagement: ServiceEngagement,
    stage_state: ProgramStageState,
    user: User | None,
    deliverable_type: str,
    title: str,
    prompt: str,
    runtime: Callable[..., CodexSessionRunResult] | None = None,
) -> ServiceDeliverable:
    """Generate a stage-owned markdown deliverable from Codex session output."""

    if stage_state.company_id != engagement.company_id:
        raise ValueError("Codex deliverable stage must belong to the engagement company.")
    if (stage_state.state_json or {}).get("service_engagement_id") != str(engagement.id):
        raise ValueError("Codex deliverable stage must belong to the target engagement.")

    result = (runtime or run_codex_session_prompt)(
        prompt=_stage_prompt(engagement, stage_state, prompt)
    )
    if result.status != "succeeded" or not result.output_text.strip():
        raise CodexSessionRuntimeError("Codex session did not return usable deliverable output.")

    content = result.output_text.strip()
    data = content.encode("utf-8")
    digest = hashlib.sha256(data).hexdigest()
    asset, _ = Asset.objects.get_or_create(
        company=engagement.company,
        source_key=f"codex-session:{engagement.id}:{stage_state.stage_id}:{deliverable_type}",
        defaults={
            "organization": engagement.organization,
            "title": title,
            "asset_type": "codex_session_deliverable",
            "created_by_type": "agent",
            "created_by_id": user.id if user else None,
        },
    )
    asset.organization = engagement.organization
    asset.title = title
    asset.asset_type = "codex_session_deliverable"
    asset.status = "active"
    asset.metadata_json = {
        "source": CODEX_SESSION_SOURCE,
        "deliverable_type": deliverable_type,
        "stage_id": stage_state.stage_id,
        "codex_session": _result_metadata(result),
        "inline_preview": content[:12000],
    }
    asset.save()

    version = AssetVersion.objects.filter(asset=asset, content_hash=digest).first()
    if version is None:
        latest_num = (
            AssetVersion.objects.filter(asset=asset)
            .order_by("-version_number")
            .values_list("version_number", flat=True)
            .first()
            or 0
        )
        version = AssetVersion.objects.create(
            asset=asset,
            version_number=latest_num + 1,
            content_uri=f"forgegraph://codex-session/{engagement.id}/{deliverable_type}.md",
            content_hash=digest,
            mime_type="text/markdown",
            size_bytes=len(data),
            provenance_json={
                "source": CODEX_SESSION_SOURCE,
                "inline_content": content,
                "codex_session": _result_metadata(result),
            },
        )

    deliverable, _ = ServiceDeliverable.objects.get_or_create(
        engagement=engagement,
        deliverable_type=deliverable_type,
        defaults={
            "organization": engagement.organization,
            "company": engagement.company,
            "created_by": user,
        },
    )
    deliverable.organization = engagement.organization
    deliverable.company = engagement.company
    deliverable.title = title
    deliverable.status = "ready"
    deliverable.visibility = "customer"
    deliverable.artifact = asset
    deliverable.summary = _summary_for_content(content)
    deliverable.metadata_json = {
        "source": CODEX_SESSION_SOURCE,
        "asset_version_id": str(version.id),
        "codex_session": _result_metadata(result),
    }
    deliverable.save()
    attach_asset_to_stage(asset, stage_state, output_kind=deliverable_type)
    attach_deliverable_to_stage(deliverable, stage_state, output_kind=deliverable_type)
    attach_deliverable_to_stage_task(
        stage_state,
        deliverable,
        asset_versions=[version],
        runtime_provider=CODEX_SESSION_SOURCE,
    )
    asset.origin_deliverable_id = deliverable.id
    asset.save(update_fields=["origin_deliverable_id", "updated_at"])
    return deliverable


def _assert_enabled() -> None:
    if not getattr(settings, "ENABLE_CODEX_SESSION_RUNTIME", False):
        raise CodexSessionRuntimeDisabled(
            "codex_session runtime is disabled. Set ENABLE_CODEX_SESSION_RUNTIME=true for local operator testing."
        )


def _subprocess_runner(
    command: Sequence[str],
    *,
    cwd: str,
    timeout: int,
    input_text: str,
) -> CodexSessionRunResult:
    started = time.monotonic()
    try:
        completed = subprocess.run(
            list(command),
            cwd=cwd,
            timeout=timeout,
            check=False,
            capture_output=True,
            input=input_text,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
    except FileNotFoundError:
        return CodexSessionRunResult(
            status="failed",
            output_text="",
            error_text="codex CLI was not found on PATH.",
            command_summary="codex exec <prompt>",
            duration_ms=_duration_ms(started),
            exit_code=127,
        )
    except subprocess.TimeoutExpired as exc:
        return CodexSessionRunResult(
            status="failed",
            output_text=exc.stdout or "",
            error_text="codex session runtime timed out.",
            command_summary="codex exec <prompt>",
            duration_ms=_duration_ms(started),
            exit_code=124,
        )
    return CodexSessionRunResult(
        status="succeeded" if completed.returncode == 0 else "failed",
        output_text=completed.stdout or "",
        error_text=completed.stderr or "",
        command_summary="codex exec <prompt>",
        duration_ms=_duration_ms(started),
        exit_code=completed.returncode,
    )


def _stage_prompt(
    engagement: ServiceEngagement, stage_state: ProgramStageState, prompt: str
) -> str:
    state = stage_state.state_json or {}
    return "\n".join(
        [
            "You are a company department producing a client-ready markdown deliverable.",
            "This is NOT a coding task. Do not inspect the workspace or acknowledge readiness.",
            "Return only the final deliverable markdown requested below.",
            f"Company/client: {engagement.company.name}",
            f"Engagement: {engagement.public_summary or engagement.catalog_item.title}",
            f"Department stage: {stage_state.stage_id}",
            f"Department slug: {state.get('department_slug') or stage_state.stage_id}",
            "",
            "Deliverable request:",
            _clean_prompt(prompt),
        ]
    )


def _clean_prompt(prompt: str) -> str:
    return str(prompt or "").strip()[:12000]


def _duration_ms(started: float) -> int:
    return int((time.monotonic() - started) * 1000)


def _result_metadata(result: CodexSessionRunResult) -> dict[str, object]:
    return {
        "status": result.status,
        "command_summary": result.command_summary,
        "duration_ms": result.duration_ms,
        "exit_code": result.exit_code,
        "local_operator_runtime": True,
    }


def _summary_for_content(content: str) -> str:
    for line in content.splitlines():
        clean = line.strip(" #\t")
        if clean:
            return clean[:500]
    return "Codex session generated deliverable."
