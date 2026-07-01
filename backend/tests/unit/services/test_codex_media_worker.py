from __future__ import annotations

import json

import pytest
from django.test import override_settings

from application.services.codex_media_worker import (
    CodexMediaWorker,
    enqueue_codex_image_job,
)
from application.services.codex_session_runtime import CodexSessionRunResult
from application.services.gemini_media import read_media_asset_version_content
from application.services.tenancy import ensure_default_organization
from infrastructure.orm.models import Graph, GraphVersion, MediaGenerationJob, User

pytestmark = pytest.mark.django_db


def _company(user: User) -> Graph:
    ensure_default_organization(user)
    organization = user.default_organization
    assert organization is not None
    company = Graph.objects.create(
        owner=user,
        organization=organization,
        name="Legacy",
        description="Spanish-first eyewear client.",
    )
    GraphVersion.objects.create(
        graph=company,
        version=1,
        graph_json={"nodes": [], "edges": [], "metadata": {}},
    )
    return company


def _fake_codex_runtime(**kwargs):
    prompt = kwargs["prompt"]
    return CodexSessionRunResult(
        status="succeeded",
        output_text=json.dumps(
            {
                "title": "Optical Noir Hero Frame",
                "composition": "premium editorial sunglasses on smoked glass",
                "palette": ["#050505", "#F3E8D1", "#A66A2A", "#0D3B34"],
                "headline": "",
                "notes": ["no text", "no logos", "no people", "mobile square"],
                "source_prompt_excerpt": prompt[:120],
            }
        ),
        error_text="",
        command_summary="codex exec <prompt>",
        duration_ms=25,
        exit_code=0,
    )


def test_codex_image_job_is_queued_not_generated_by_request(user):
    company = _company(user)

    job = enqueue_codex_image_job(
        user=user,
        company=company,
        prompt="Create Optical Noir campaign post 01; no text, no logos, no people.",
        idempotency_key="legacy-optical-noir:post-01",
    )

    assert job.provider == "codex"
    assert job.status == "pending"
    assert job.credential_id is None
    assert job.output_asset_id is None
    assert job.request_json["runtime_provider"] == "codex_session_runtime"
    assert MediaGenerationJob.objects.filter(company=company, provider="codex").count() == 1


def test_codex_media_worker_executes_pending_job_into_backend_asset(settings, tmp_path, user):
    settings.MEDIA_GENERATION_ARTIFACT_ROOT = tmp_path
    company = _company(user)
    job = enqueue_codex_image_job(
        user=user,
        company=company,
        prompt="Create Optical Noir campaign post 01; no text, no logos, no people.",
        idempotency_key="legacy-optical-noir:post-01",
    )

    with override_settings(ENABLE_CODEX_SESSION_RUNTIME=True):
        result = CodexMediaWorker(runtime=_fake_codex_runtime).process_next()

    assert result is not None
    assert result.job_id == job.id
    assert result.status == "succeeded"
    job.refresh_from_db()
    assert job.status == "succeeded"
    assert job.output_asset is not None
    assert job.output_asset.asset_type == "image"
    assert job.output_asset.metadata_json["source"] == "codex_media_worker"
    assert job.output_asset.metadata_json["codex_session"]["status"] == "succeeded"
    assert job.output_asset.metadata_json["quality_tier"] == "placeholder"
    assert job.output_asset.metadata_json["production_quality"] is False
    assert job.output_asset.metadata_json["quality_contract"]["renderer"] == "codex_spec_renderer"
    assert job.output_asset_version is not None
    content, mime_type, filename = read_media_asset_version_content(job.output_asset_version)
    assert content.startswith(b"\x89PNG")
    assert mime_type == "image/png"
    assert filename.endswith(".png")
    assert len(content) > 1000


def test_codex_media_worker_marks_failed_without_usable_output(settings, tmp_path, user):
    settings.MEDIA_GENERATION_ARTIFACT_ROOT = tmp_path
    company = _company(user)
    job = enqueue_codex_image_job(
        user=user,
        company=company,
        prompt="Create Optical Noir campaign post 02.",
        idempotency_key="legacy-optical-noir:post-02",
    )

    def failing_runtime(**_kwargs):
        return CodexSessionRunResult(
            status="failed",
            output_text="",
            error_text="token budget exhausted",
            command_summary="codex exec <prompt>",
            duration_ms=5,
            exit_code=1,
        )

    with override_settings(ENABLE_CODEX_SESSION_RUNTIME=True):
        result = CodexMediaWorker(runtime=failing_runtime).process_next()

    assert result is not None
    assert result.status == "failed"
    job.refresh_from_db()
    assert job.status == "failed"
    assert job.error_code == "codex_media_generation_failed"
    assert "token budget exhausted" in job.error_message
