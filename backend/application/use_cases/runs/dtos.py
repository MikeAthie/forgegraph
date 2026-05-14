"""Adapter-neutral DTOs for run use cases."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING, Any
from uuid import UUID

if TYPE_CHECKING:
    from application.services.llm_access import LLMAccessConfig
    from infrastructure.orm.models import (
        GraphVersion,
        Organization,
        ProcessedDecisionSubmission,
        Run,
        RunCheckpoint,
        User,
    )


@dataclass
class EngineCallbackContext:
    run: Run
    event: dict[str, Any]
    event_type: str
    event_id: Any
    event_time: datetime | None
    trace_context: dict[str, str]
    normalized_category: str
    state_mutation_enabled: bool
    callback_engine_instance_id: str
    callback_organization_id: UUID | None
    callback_idempotency_key: str
    callback_request_hash: str


@dataclass
class RunLifecycleMutation:
    run_payload: dict[str, Any]
    update_fields: list[str]
    pause_payload: dict[str, Any]
    node_id: str
    projection_kwargs: dict[str, Any]
    error_response: Any | None = None


@dataclass
class RunEngineDispatch:
    run: Run
    graph_version: GraphVersion
    outbound_graph: dict[str, Any]
    input_json: dict[str, Any]
    llm_access: LLMAccessConfig
    session_id: str | None
    tenant_id: str
    trace_metadata: dict[str, str]
    span_name: str
    trigger: str
    engine_rejected_event: str = "engine_rejected_run"
    failure_task_source: str | None = None


@dataclass
class RunStartRequestContext:
    user: User
    tenant_id: str
    tenant_uuid: UUID
    command_context: Any
    graph_version_id: UUID
    input_json: dict[str, Any]
    llm_access: LLMAccessConfig
    thread_id: Any
    session_id: str | None


@dataclass
class RunInvokeRequestContext:
    user: User
    tenant_id: str
    tenant_uuid: UUID
    command_context: Any
    thread_id: Any
    session_id: str
    input_json: dict[str, Any]
    llm_access: LLMAccessConfig
    latest_run: Run
    checkpoint: RunCheckpoint


@dataclass
class RunReplayRequestContext:
    user: User
    tenant_id: str
    tenant_uuid: UUID
    command_context: Any
    run: Run
    node_id: str
    llm_access: LLMAccessConfig
    checkpoint: RunCheckpoint
    input_json: dict[str, Any]
    session_id: str | None


@dataclass
class ReplayCheckpointSeed:
    state_json: dict[str, Any]
    completed_nodes: list[Any]
    skipped_nodes: list[Any]


@dataclass
class RunResumeRequestContext:
    user: User
    run: Run
    organization: Organization | None
    command_context: Any
    node_id: str
    input_json: dict[str, Any]
    submit_id: str
    decision_request_hash: str
    decision_submission: ProcessedDecisionSubmission | None
    resume_attempt_id: UUID


__all__ = [
    "EngineCallbackContext",
    "ReplayCheckpointSeed",
    "RunEngineDispatch",
    "RunInvokeRequestContext",
    "RunLifecycleMutation",
    "RunReplayRequestContext",
    "RunResumeRequestContext",
    "RunStartRequestContext",
]
