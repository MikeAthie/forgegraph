"""Company archive, extraction, context pack, and evidence services."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from typing import Any, cast
from uuid import UUID

from django.db import IntegrityError
from django.db.models import Q

from application.services.interaction import (
    brief_from_record,
    brief_payload,
    get_current_brief_record,
)
from infrastructure.orm.models import (
    Asset,
    AssetExtract,
    AssetVersion,
    ContextPack,
    DecisionRecord,
    EvidenceLink,
    Graph,
    MemoryObservation,
    NodeRun,
    OperatingBriefRecord,
    PolicyRule,
    Run,
    TaskRecord,
)

DELIVERABLE_KEYS = (
    "deliverable",
    "final_deliverable",
    "strategy",
    "strategy_report",
    "report",
    "final_report",
    "campaign_plan",
    "execution_plan",
)
MAX_CONTEXT_ASSETS = 8
MAX_CONTEXT_POLICIES = 5
MAX_CONTEXT_MEMORIES = 5
MAX_CONTEXT_DECISIONS = 5
MAX_CHUNKS = 8
CHUNK_SIZE = 1200
MAX_CONTEXT_PACK_BYTES = 32 * 1024
MAX_CONTEXT_FIELD_BUDGET_BYTES = MAX_CONTEXT_PACK_BYTES - 1024
MAX_CONTEXT_STRING_LENGTH = 1000
MAX_CONTEXT_LIST_ITEMS = 20
MAX_CONTEXT_DICT_ITEMS = 50


@dataclass(frozen=True)
class ArchivedDeliverable:
    asset: Asset
    version: AssetVersion
    extract: AssetExtract | None


class ArchiveService:
    """Create and query backend-owned company archive assets."""

    def archive_deliverable_as_asset(
        self,
        *,
        run: Run,
        node_run: NodeRun | None = None,
    ) -> list[ArchivedDeliverable]:
        company = run.graph_version.graph
        organization = run.organization or company.organization
        if organization is None:
            return []

        payload = node_run.output_json if node_run is not None else run.output_json
        deliverables = _deliverable_items(payload)
        if not deliverables:
            return []

        task = _task_for_node_run(run=run, node_run=node_run)
        archived: list[ArchivedDeliverable] = []
        for key, value in deliverables:
            source_key = _source_key(run=run, node_run=node_run, key=key)
            title = _title_for_deliverable(key=key, value=value)
            item = self.create_asset(
                company=company,
                title=title,
                asset_type="deliverable",
                source_key=source_key,
                origin_operation=run,
                origin_task=task,
                origin_node_run=node_run,
                created_by_type="agent",
                metadata={
                    "source": "run_output" if node_run is None else "node_output",
                    "source_key": key,
                    "run_id": str(run.id),
                    "node_run_id": str(node_run.id) if node_run else None,
                    "node_id": node_run.node_id if node_run else None,
                },
            )
            version = self.create_asset_version(
                asset=item,
                content_uri=_content_uri(run=run, node_run=node_run, key=key),
                content=_canonical_payload(value),
                mime_type=_mime_type_for_value(value),
                provenance={
                    "source": "deliverable",
                    "source_key": key,
                    "generated_by": "run" if node_run is None else "node_run",
                    "run_id": str(run.id),
                    "node_run_id": str(node_run.id) if node_run else None,
                },
            )
            extract = AssetExtractionService().extract_asset_version(version)
            archived.append(ArchivedDeliverable(asset=item, version=version, extract=extract))
        return archived

    def create_asset(
        self,
        *,
        company: Graph,
        title: str,
        asset_type: str,
        source_key: str = "",
        origin_operation: Run | None = None,
        origin_task: TaskRecord | None = None,
        origin_node_run: NodeRun | None = None,
        origin_deliverable_id: UUID | None = None,
        created_by_type: str = "system",
        created_by_id: UUID | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> Asset:
        if company.organization_id is None:
            raise ValueError("Assets require an organization-scoped company.")
        defaults = {
            "organization": company.organization,
            "title": title[:255],
            "asset_type": asset_type,
            "origin_operation": origin_operation,
            "origin_task": origin_task,
            "origin_node_run": origin_node_run,
            "origin_deliverable_id": origin_deliverable_id,
            "created_by_type": created_by_type,
            "created_by_id": created_by_id,
            "status": "active",
            "metadata_json": metadata or {},
        }
        if source_key:
            asset, created = Asset.objects.get_or_create(
                company=company,
                source_key=source_key,
                defaults=defaults,
            )
            if not created and asset.status != "active":
                asset.status = "active"
                asset.save(update_fields=["status", "updated_at"])
            return asset
        return Asset.objects.create(company=company, source_key="", **defaults)

    def create_asset_version(
        self,
        *,
        asset: Asset,
        content_uri: str,
        content: bytes,
        mime_type: str | None = None,
        provenance: dict[str, Any] | None = None,
    ) -> AssetVersion:
        content_hash = hashlib.sha256(content).hexdigest()
        existing = AssetVersion.objects.filter(asset=asset, content_hash=content_hash).first()
        if existing is not None:
            return existing

        latest = (
            AssetVersion.objects.filter(asset=asset)
            .order_by("-version_number")
            .values_list("version_number", flat=True)
            .first()
        )
        version_number = int(latest or 0) + 1
        try:
            return AssetVersion.objects.create(
                asset=asset,
                version_number=version_number,
                content_uri=content_uri,
                content_hash=content_hash,
                mime_type=mime_type or "",
                size_bytes=len(content),
                provenance_json=provenance or {},
            )
        except IntegrityError:
            found = AssetVersion.objects.filter(asset=asset, content_hash=content_hash).first()
            if found is not None:
                return found
            raise

    def mark_asset_superseded(self, *, asset: Asset) -> Asset:
        asset.status = "superseded"
        asset.save(update_fields=["status", "updated_at"])
        return asset

    def get_company_assets(
        self,
        *,
        company: Graph,
        asset_type: str | None = None,
        status: str | None = None,
        operation_id: UUID | None = None,
    ) -> list[Asset]:
        queryset = Asset.objects.filter(company=company).select_related(
            "origin_operation",
            "origin_task",
            "origin_node_run",
        )
        if asset_type:
            queryset = queryset.filter(asset_type=asset_type)
        if status:
            queryset = queryset.filter(status=status)
        if operation_id:
            queryset = queryset.filter(origin_operation_id=operation_id)
        return list(queryset.order_by("-created_at")[:100])


class AssetExtractionService:
    """Deterministic v1 extractor for text, markdown, and JSON content."""

    def extract_asset_version(self, asset_version: AssetVersion) -> AssetExtract:
        extract, _ = AssetExtract.objects.get_or_create(
            asset_version=asset_version,
            defaults={
                "company": asset_version.asset.company,
                "embedding_status": "pending",
                "metadata_json": {},
            },
        )
        try:
            value = _load_content_value(asset_version)
            text = _value_to_text(value)
            if not text.strip():
                return self.mark_extract_failed(
                    extract,
                    reason="No extractable text content was found.",
                )
            chunks = _chunk_text(text)
            extract.summary = _summary_for_text(text)
            extract.text_content = text
            extract.chunks_json = chunks
            extract.claims_json = _claims_for_text(text)
            extract.entities_json = _entities_for_text(text)
            extract.embedding_status = "indexed"
            extract.metadata_json = {
                **(extract.metadata_json or {}),
                "extractor": "deterministic_text_v1",
                "chunk_count": len(chunks),
            }
            extract.save(
                update_fields=[
                    "summary",
                    "text_content",
                    "chunks_json",
                    "claims_json",
                    "entities_json",
                    "embedding_status",
                    "metadata_json",
                ]
            )
            return extract
        except Exception as exc:
            return self.mark_extract_failed(extract, reason=str(exc))

    def mark_extract_indexed(self, extract: AssetExtract) -> AssetExtract:
        extract.embedding_status = "indexed"
        extract.save(update_fields=["embedding_status"])
        return extract

    def mark_extract_failed(self, extract: AssetExtract, *, reason: str) -> AssetExtract:
        extract.embedding_status = "failed"
        extract.metadata_json = {**(extract.metadata_json or {}), "failure_reason": reason}
        extract.save(update_fields=["embedding_status", "metadata_json"])
        return extract


class ContextPackService:
    """Build bounded context packs for execution without engine-owned retrieval."""

    def build_context_pack(
        self,
        *,
        company_id: UUID | str | Graph,
        operation_id: UUID | str | Run | None = None,
        task_id: UUID | str | TaskRecord | None = None,
        node_run_id: UUID | str | NodeRun | None = None,
        department_id: str | None = None,
        brief_snapshot: dict[str, Any] | None = None,
        created_for: str = "task_execution",
    ) -> ContextPack:
        company = _resolve_company(company_id)
        organization = company.organization
        if organization is None:
            raise ValueError("Context packs require an organization-scoped company.")
        operation = _resolve_operation(company, operation_id)
        task = _resolve_task(company, task_id)
        node_run = _resolve_node_run(company, node_run_id)
        brief_snapshot = brief_snapshot or _brief_snapshot(company=company, operation=operation)
        query_text = _context_query_text(
            brief_snapshot=brief_snapshot, operation=operation, task=task
        )

        policy_refs = _policy_refs(company=company, department_id=department_id, task=task)
        asset_refs = _asset_refs(company=company, query_text=query_text)
        memory_refs = _memory_refs(company=company, operation=operation)
        decision_refs = _decision_refs(company=company, operation=operation, task=task)
        assumptions = _assumptions_from_brief(brief_snapshot)
        scope = {
            "operation_id": str(operation.id) if operation else None,
            "task_id": str(task.id) if task else None,
            "node_run_id": str(node_run.id) if node_run else None,
            "department_id": department_id or None,
        }
        bounded_fields = _bounded_context_fields(
            {
                "scope_json": scope,
                "brief_snapshot_json": brief_snapshot,
                "asset_refs_json": asset_refs,
                "memory_refs_json": memory_refs,
                "decision_refs_json": decision_refs,
                "policy_refs_json": policy_refs,
                "assumptions_json": assumptions,
            }
        )

        return ContextPack.objects.create(
            organization=organization,
            company=company,
            operation=operation,
            task=task,
            node_run=node_run,
            department_id=(department_id or ""),
            scope_json=bounded_fields["scope_json"],
            brief_snapshot_json=bounded_fields["brief_snapshot_json"],
            asset_refs_json=bounded_fields["asset_refs_json"],
            memory_refs_json=bounded_fields["memory_refs_json"],
            decision_refs_json=bounded_fields["decision_refs_json"],
            policy_refs_json=bounded_fields["policy_refs_json"],
            assumptions_json=bounded_fields["assumptions_json"],
            created_for=created_for,
        )

    def attach_context_pack_to_run(
        self,
        *,
        run: Run,
        created_for: str = "operation_planning",
        outbound_graph: dict[str, Any] | None = None,
        context_pack_mode: str = "fresh_at_dispatch",
    ) -> tuple[ContextPack, dict[str, Any] | None]:
        company = run.graph_version.graph
        context_pack = _context_pack_from_run_metadata(run)
        if context_pack is None:
            input_json = dict(run.input_json or {})
            brief_snapshot = input_json.get("operating_brief")
            if not isinstance(brief_snapshot, dict):
                brief_snapshot = input_json.get("operation_brief")
                if isinstance(brief_snapshot, str):
                    brief_snapshot = {"objective": brief_snapshot}
                elif not isinstance(brief_snapshot, dict):
                    brief_snapshot = None

            context_pack = self.build_context_pack(
                company_id=company,
                operation_id=run,
                brief_snapshot=brief_snapshot,
                created_for=created_for,
            )
        else:
            existing_metadata = (
                run.dispatch_graph_json.get("metadata")
                if isinstance(run.dispatch_graph_json, dict)
                else {}
            )
            if isinstance(existing_metadata, dict):
                context_pack_mode = str(
                    existing_metadata.get("context_pack_mode")
                    or existing_metadata.get("context_pack_replay_behavior")
                    or "existing_for_run"
                )
        context_payload = context_pack_payload(context_pack)

        persisted_graph = dict(run.dispatch_graph_json or {})
        persisted_metadata = dict(persisted_graph.get("metadata") or {})
        persisted_metadata["context_pack_id"] = str(context_pack.id)
        persisted_metadata["context_pack"] = context_payload
        persisted_metadata["context_pack_mode"] = context_pack_mode
        persisted_graph["metadata"] = persisted_metadata
        run.dispatch_graph_json = persisted_graph

        outbound_with_context: dict[str, Any] | None = None
        if outbound_graph is not None:
            outbound_with_context = dict(outbound_graph)
            outbound_metadata = dict(outbound_with_context.get("metadata") or {})
            outbound_metadata["context_pack_id"] = str(context_pack.id)
            outbound_metadata["context_pack"] = context_payload
            outbound_metadata["context_pack_mode"] = context_pack_mode
            outbound_with_context["metadata"] = outbound_metadata

        EvidenceLinkService().record_context_usage(
            context_pack_id=context_pack.id,
            operation_id=run.id,
            used_for="planning",
        )
        return context_pack, outbound_with_context


class EvidenceLinkService:
    """Persist traceability for evidence that was supplied to work."""

    def record_context_usage(
        self,
        *,
        context_pack_id: UUID | str,
        operation_id: UUID | str | None = None,
        task_id: UUID | str | None = None,
        node_run_id: UUID | str | None = None,
        decision_id: UUID | str | None = None,
        used_for: str = "planning",
    ) -> list[EvidenceLink]:
        context_pack = ContextPack.objects.select_related("company", "organization").get(
            id=context_pack_id
        )
        links: list[EvidenceLink] = []
        for ref in _list_of_dicts(context_pack.asset_refs_json):
            asset_id = ref.get("asset_id")
            if not asset_id:
                continue
            link = self.record_asset_usage(
                company=context_pack.company,
                asset_id=asset_id,
                asset_version_id=ref.get("asset_version_id"),
                asset_extract_id=ref.get("asset_extract_id"),
                context_pack=context_pack,
                operation_id=operation_id,
                task_id=task_id,
                node_run_id=node_run_id,
                decision_id=decision_id,
                used_for=used_for,
                relevance_score=ref.get("relevance_score"),
                reason=ref.get("reason"),
            )
            links.append(link)
        return links

    def record_asset_usage(
        self,
        *,
        company: Graph,
        asset_id: UUID | str,
        asset_version_id: UUID | str | None = None,
        asset_extract_id: UUID | str | None = None,
        context_pack: ContextPack | None = None,
        operation_id: UUID | str | None = None,
        task_id: UUID | str | None = None,
        node_run_id: UUID | str | None = None,
        decision_id: UUID | str | None = None,
        deliverable_id: UUID | None = None,
        used_for: str,
        relevance_score: float | None = None,
        reason: str | None = None,
    ) -> EvidenceLink:
        if context_pack is not None and context_pack.company_id != company.id:
            raise ValueError("Context pack does not belong to company.")
        asset = Asset.objects.get(id=asset_id, company=company)
        version = _resolve_asset_version(asset=asset, value=asset_version_id)
        extract = _resolve_asset_extract(asset=asset, value=asset_extract_id)
        operation = _resolve_operation(company, operation_id)
        task = _resolve_task(company, task_id)
        node_run = _resolve_node_run(company, node_run_id)
        decision = _resolve_decision(company, decision_id)
        usage_key = _evidence_usage_key(
            context_pack=context_pack,
            asset=asset,
            version=version,
            extract=extract,
            operation=operation,
            task=task,
            node_run=node_run,
            decision=decision,
            deliverable_id=deliverable_id,
            used_for=used_for,
        )
        link, _ = EvidenceLink.objects.get_or_create(
            company=company,
            usage_key=usage_key,
            defaults={
                "organization": company.organization,
                "context_pack": context_pack,
                "asset": asset,
                "asset_version": version,
                "asset_extract": extract,
                "operation": operation,
                "task": task,
                "node_run": node_run,
                "decision": decision,
                "deliverable_id": deliverable_id,
                "used_for": used_for,
                "relevance_score": _optional_float(relevance_score),
                "reason": reason,
            },
        )
        return link


def context_pack_payload(context_pack: ContextPack) -> dict[str, Any]:
    return {
        "id": str(context_pack.id),
        "company_id": str(context_pack.company_id),
        "operation_id": str(context_pack.operation_id) if context_pack.operation_id else None,
        "task_id": str(context_pack.task_id) if context_pack.task_id else None,
        "node_run_id": str(context_pack.node_run_id) if context_pack.node_run_id else None,
        "department_id": context_pack.department_id or None,
        "scope": context_pack.scope_json,
        "brief_snapshot": context_pack.brief_snapshot_json,
        "asset_refs": context_pack.asset_refs_json,
        "memory_refs": context_pack.memory_refs_json,
        "decision_refs": context_pack.decision_refs_json,
        "policy_refs": context_pack.policy_refs_json,
        "assumptions": context_pack.assumptions_json,
        "created_for": context_pack.created_for,
        "created_at": context_pack.created_at.isoformat(),
    }


def asset_payload(asset: Asset) -> dict[str, Any]:
    latest_version = asset.versions.order_by("-version_number").first()
    return {
        "id": str(asset.id),
        "organization_id": str(asset.organization_id),
        "company_id": str(asset.company_id),
        "title": asset.title,
        "asset_type": asset.asset_type,
        "source_key": asset.source_key,
        "origin_operation_id": str(asset.origin_operation_id)
        if asset.origin_operation_id
        else None,
        "origin_task_id": str(asset.origin_task_id) if asset.origin_task_id else None,
        "origin_node_run_id": str(asset.origin_node_run_id) if asset.origin_node_run_id else None,
        "origin_deliverable_id": (
            str(asset.origin_deliverable_id) if asset.origin_deliverable_id else None
        ),
        "created_by_type": asset.created_by_type,
        "created_by_id": str(asset.created_by_id) if asset.created_by_id else None,
        "status": asset.status,
        "metadata": asset.metadata_json,
        "latest_version_id": str(latest_version.id) if latest_version else None,
        "created_at": asset.created_at.isoformat(),
        "updated_at": asset.updated_at.isoformat(),
    }


def asset_version_payload(version: AssetVersion) -> dict[str, Any]:
    return {
        "id": str(version.id),
        "asset_id": str(version.asset_id),
        "version_number": version.version_number,
        "content_uri": version.content_uri,
        "content_hash": version.content_hash or None,
        "mime_type": version.mime_type or None,
        "size_bytes": version.size_bytes,
        "provenance": version.provenance_json,
        "created_at": version.created_at.isoformat(),
    }


def evidence_link_payload(link: EvidenceLink) -> dict[str, Any]:
    return {
        "id": str(link.id),
        "company_id": str(link.company_id),
        "context_pack_id": str(link.context_pack_id) if link.context_pack_id else None,
        "asset_id": str(link.asset_id),
        "asset_version_id": str(link.asset_version_id) if link.asset_version_id else None,
        "asset_extract_id": str(link.asset_extract_id) if link.asset_extract_id else None,
        "operation_id": str(link.operation_id) if link.operation_id else None,
        "task_id": str(link.task_id) if link.task_id else None,
        "node_run_id": str(link.node_run_id) if link.node_run_id else None,
        "decision_id": str(link.decision_id) if link.decision_id else None,
        "deliverable_id": str(link.deliverable_id) if link.deliverable_id else None,
        "used_for": link.used_for,
        "relevance_score": link.relevance_score,
        "reason": link.reason,
        "created_at": link.created_at.isoformat(),
    }


def _deliverable_items(payload: Any) -> list[tuple[str, Any]]:
    if not isinstance(payload, dict):
        return []
    items: list[tuple[str, Any]] = []
    for key in DELIVERABLE_KEYS:
        value = payload.get(key)
        if _has_content(value):
            items.append((key, value))
    return items


def _has_content(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, (list, dict)):
        return bool(value)
    return True


def _source_key(*, run: Run, node_run: NodeRun | None, key: str) -> str:
    if node_run is not None:
        return f"node:{node_run.id}:output:{key}"
    return f"run:{run.id}:output:{key}"


def _content_uri(*, run: Run, node_run: NodeRun | None, key: str) -> str:
    if node_run is not None:
        return f"forgegraph://node-runs/{node_run.id}/output/{key}"
    return f"forgegraph://runs/{run.id}/output/{key}"


def _title_for_deliverable(*, key: str, value: Any) -> str:
    label = key.replace("_", " ").title()
    text = _value_to_text(value).strip().replace("\n", " ")
    if text:
        return f"{label}: {text[:120]}".strip()
    return label


def _canonical_payload(value: Any) -> bytes:
    if isinstance(value, bytes):
        return value
    if isinstance(value, str):
        return value.encode("utf-8")
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")


def _mime_type_for_value(value: Any) -> str:
    if isinstance(value, str):
        return "text/plain"
    if isinstance(value, (dict, list)):
        return "application/json"
    return "application/octet-stream"


def _task_for_node_run(*, run: Run, node_run: NodeRun | None) -> TaskRecord | None:
    if node_run is None:
        return None
    return (
        TaskRecord.objects.filter(execution=run)
        .filter(Q(current_step=node_run) | Q(source_node_id=node_run.node_id))
        .order_by("-updated_at")
        .first()
    )


def _load_content_value(asset_version: AssetVersion) -> Any:
    company = asset_version.asset.company
    uri = asset_version.content_uri
    run_match = re.fullmatch(r"forgegraph://runs/([^/]+)/output/(.+)", uri)
    if run_match:
        run = Run.objects.get(id=run_match.group(1), graph_version__graph=company)
        payload = run.output_json if isinstance(run.output_json, dict) else {}
        return payload.get(run_match.group(2))
    node_match = re.fullmatch(r"forgegraph://node-runs/([^/]+)/output/(.+)", uri)
    if node_match:
        node_run = NodeRun.objects.get(id=node_match.group(1), run__graph_version__graph=company)
        payload = node_run.output_json if isinstance(node_run.output_json, dict) else {}
        return payload.get(node_match.group(2))
    inline_match = re.fullmatch(r"forgegraph://assets/([^/]+)/inline", uri)
    if inline_match and str(asset_version.id) == inline_match.group(1):
        provenance = (
            asset_version.provenance_json if isinstance(asset_version.provenance_json, dict) else {}
        )
        if "inline_content" in provenance:
            return provenance["inline_content"]
    return None


def _value_to_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, (dict, list)):
        return json.dumps(value, indent=2, sort_keys=True, default=str)
    return str(value)


def _summary_for_text(text: str) -> str:
    normalized = re.sub(r"\s+", " ", text).strip()
    return normalized[:500]


def _chunk_text(text: str) -> list[dict[str, Any]]:
    normalized = text.strip()
    chunks: list[dict[str, Any]] = []
    for index, start in enumerate(range(0, len(normalized), CHUNK_SIZE)):
        if index >= MAX_CHUNKS:
            break
        chunk = normalized[start : start + CHUNK_SIZE].strip()
        if chunk:
            chunks.append(
                {
                    "index": index,
                    "text": chunk,
                    "char_start": start,
                    "char_end": start + len(chunk),
                }
            )
    return chunks


def _claims_for_text(text: str) -> list[dict[str, Any]]:
    claims: list[dict[str, Any]] = []
    for line in re.split(r"[\n.;]", text):
        clean = line.strip()
        if not clean:
            continue
        lower = clean.lower()
        if any(token in lower for token in ("must", "should", "will", "cannot", "can't")):
            claims.append({"text": clean[:300], "type": "statement"})
        if len(claims) >= 12:
            break
    return claims


def _entities_for_text(text: str) -> list[str]:
    candidates = re.findall(r"\b[A-Z][A-Za-z0-9&.-]*(?:\s+[A-Z][A-Za-z0-9&.-]*){0,3}\b", text)
    seen: set[str] = set()
    entities: list[str] = []
    for item in candidates:
        if item in seen:
            continue
        seen.add(item)
        entities.append(item)
        if len(entities) >= 20:
            break
    return entities


def _resolve_company(value: UUID | str | Graph) -> Graph:
    if isinstance(value, Graph):
        return value
    return cast(Graph, Graph.objects.select_related("organization").get(id=value))


def _resolve_operation(company: Graph, value: UUID | str | Run | None) -> Run | None:
    if value is None:
        return None
    if isinstance(value, Run):
        if value.graph_version.graph_id != company.id:
            raise ValueError("Operation does not belong to company.")
        return value
    operation = Run.objects.filter(id=value, graph_version__graph=company).first()
    if operation is None:
        raise ValueError("Operation does not belong to company.")
    return operation


def _resolve_task(company: Graph, value: UUID | str | TaskRecord | None) -> TaskRecord | None:
    if value is None:
        return None
    if isinstance(value, TaskRecord):
        if value.execution.graph_version.graph_id != company.id:
            raise ValueError("Task does not belong to company.")
        return value
    task = TaskRecord.objects.filter(id=value, execution__graph_version__graph=company).first()
    if task is None:
        raise ValueError("Task does not belong to company.")
    return task


def _resolve_node_run(company: Graph, value: UUID | str | NodeRun | None) -> NodeRun | None:
    if value is None:
        return None
    if isinstance(value, NodeRun):
        if value.run.graph_version.graph_id != company.id:
            raise ValueError("Node run does not belong to company.")
        return value
    node_run = NodeRun.objects.filter(id=value, run__graph_version__graph=company).first()
    if node_run is None:
        raise ValueError("Node run does not belong to company.")
    return node_run


def _resolve_decision(company: Graph, value: UUID | str | None) -> DecisionRecord | None:
    if value is None:
        return None
    decision = (
        DecisionRecord.objects.select_related(
            "execution__graph_version__graph",
            "task__execution__graph_version__graph",
            "source_approval_task__run__graph_version__graph",
        )
        .filter(id=value, organization=company.organization)
        .first()
    )
    if decision is None or not _decision_belongs_to_company(decision=decision, company=company):
        raise ValueError("Decision does not belong to company.")
    return decision


def _brief_snapshot(*, company: Graph, operation: Run | None) -> dict[str, Any] | None:
    record: OperatingBriefRecord | None = get_current_brief_record(
        company=company,
        operation=operation,
    )
    if record is None and operation is not None:
        record = get_current_brief_record(company=company, operation=None)
    if record is None:
        return None
    return brief_payload(brief_from_record(record), record=record)


def _context_query_text(
    *,
    brief_snapshot: dict[str, Any] | None,
    operation: Run | None,
    task: TaskRecord | None,
) -> str:
    values: list[str] = []
    if brief_snapshot:
        for key in ("objective", "deliverable"):
            value = brief_snapshot.get(key)
            if isinstance(value, str):
                values.append(value)
        for key in ("constraints", "success_criteria", "stakeholders", "dependencies"):
            raw = brief_snapshot.get(key)
            if isinstance(raw, list):
                values.extend(str(item) for item in raw)
    if operation and isinstance(operation.input_json, dict):
        values.append(_value_to_text(operation.input_json))
    if task:
        values.extend([task.title, task.summary])
    return " ".join(values)


def _policy_refs(
    *,
    company: Graph,
    department_id: str | None,
    task: TaskRecord | None,
) -> list[dict[str, Any]]:
    scope_filters = Q(scope_type="company")
    if department_id:
        scope_filters |= Q(scope_type="department", scope_id=department_id)
    if task:
        scope_filters |= Q(scope_type="task_type", scope_id=task.source_node_id)
    policies = (
        PolicyRule.objects.filter(company=company, status="active")
        .filter(scope_filters)
        .order_by("-confidence", "-updated_at")[:MAX_CONTEXT_POLICIES]
    )
    return [
        {
            "policy_rule_id": str(policy.id),
            "title": policy.title,
            "scope_type": policy.scope_type,
            "scope_id": policy.scope_id or None,
            "condition": policy.condition_json,
            "recommendation": policy.recommendation_json,
            "confidence": policy.confidence,
        }
        for policy in policies
    ]


def _asset_refs(*, company: Graph, query_text: str) -> list[dict[str, Any]]:
    terms = _terms(query_text)
    extracts = (
        AssetExtract.objects.filter(company=company, asset_version__asset__status="active")
        .exclude(embedding_status="failed")
        .select_related("asset_version__asset")
        .order_by("-created_at")[:50]
    )
    scored: list[tuple[float, AssetExtract]] = []
    for extract in extracts:
        text = " ".join(
            [
                extract.summary or "",
                extract.text_content[:1000] if extract.text_content else "",
                " ".join(extract.entities_json or []),
                extract.asset_version.asset.title,
            ]
        )
        score = _lexical_score(terms, text)
        if score > 0 or not terms:
            scored.append((score, extract))
    scored.sort(key=lambda item: (item[0], item[1].created_at), reverse=True)
    refs: list[dict[str, Any]] = []
    for score, extract in scored[:MAX_CONTEXT_ASSETS]:
        asset = extract.asset_version.asset
        refs.append(
            {
                "asset_id": str(asset.id),
                "asset_version_id": str(extract.asset_version_id),
                "asset_extract_id": str(extract.id),
                "title": asset.title,
                "asset_type": asset.asset_type,
                "summary": extract.summary,
                "entities": extract.entities_json,
                "relevance_score": round(score, 3),
                "reason": "lexical_match" if score > 0 else "recent_company_knowledge",
            }
        )
    return refs


def _memory_refs(*, company: Graph, operation: Run | None) -> list[dict[str, Any]]:
    queryset = MemoryObservation.objects.active().filter(
        tenant_id=company.organization_id,
        graph_id=company.id,
    )
    if operation is not None:
        queryset = queryset.filter(Q(run_id=operation.id) | Q(scope="graph"))
    memories = queryset.order_by("-last_seen_at", "-created_at")[:MAX_CONTEXT_MEMORIES]
    return [
        {
            "memory_observation_id": str(memory.id),
            "type": memory.type,
            "title": memory.title,
            "content": memory.content[:500],
            "scope": memory.scope,
            "topic_key": memory.topic_key,
        }
        for memory in memories
    ]


def _decision_refs(
    *,
    company: Graph,
    operation: Run | None,
    task: TaskRecord | None,
) -> list[dict[str, Any]]:
    queryset = DecisionRecord.objects.filter(organization=company.organization).filter(
        Q(execution__graph_version__graph=company)
        | Q(task__execution__graph_version__graph=company)
        | Q(source_approval_task__run__graph_version__graph=company)
    )
    if operation is not None:
        queryset = queryset.filter(Q(execution=operation) | Q(execution__isnull=True))
    if task is not None:
        queryset = queryset.filter(Q(task=task) | Q(task__isnull=True))
    decisions = queryset.order_by("-resolved_at", "-created_at")[:MAX_CONTEXT_DECISIONS]
    return [
        {
            "decision_id": str(decision.id),
            "decision_type": decision.decision_type,
            "status": decision.status,
            "context": decision.context_json,
            "resolution": decision.resolution_json,
        }
        for decision in decisions
    ]


def _assumptions_from_brief(brief_snapshot: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not brief_snapshot:
        return []
    assumptions = brief_snapshot.get("assumptions")
    if isinstance(assumptions, list):
        return _list_of_dicts(assumptions)
    return []


def _terms(text: str) -> set[str]:
    return {term.lower() for term in re.findall(r"[A-Za-z0-9]{3,}", text)}


def _lexical_score(terms: set[str], text: str) -> float:
    if not terms:
        return 0.0
    haystack = text.lower()
    matched = sum(1 for term in terms if term in haystack)
    return matched / max(len(terms), 1)


def _list_of_dicts(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def _optional_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _resolve_asset_version(*, asset: Asset, value: UUID | str | None) -> AssetVersion | None:
    if not value:
        return None
    version = AssetVersion.objects.filter(id=value, asset=asset).first()
    if version is None:
        raise ValueError("Asset version does not belong to asset.")
    return version


def _resolve_asset_extract(*, asset: Asset, value: UUID | str | None) -> AssetExtract | None:
    if not value:
        return None
    extract = AssetExtract.objects.filter(id=value, asset_version__asset=asset).first()
    if extract is None:
        raise ValueError("Asset extract does not belong to asset.")
    return extract


def _decision_belongs_to_company(*, decision: DecisionRecord, company: Graph) -> bool:
    execution = decision.execution
    if execution is not None and execution.graph_version.graph_id == company.id:
        return True
    task = decision.task
    if task is not None and task.execution.graph_version.graph_id == company.id:
        return True
    approval = decision.source_approval_task
    if approval is not None and approval.run.graph_version.graph_id == company.id:
        return True
    return False


def _context_pack_from_run_metadata(run: Run) -> ContextPack | None:
    graph = run.dispatch_graph_json if isinstance(run.dispatch_graph_json, dict) else {}
    metadata = graph.get("metadata") if isinstance(graph, dict) else {}
    if not isinstance(metadata, dict):
        return None
    raw_context_pack_id = str(metadata.get("context_pack_id") or "").strip()
    if not raw_context_pack_id:
        return None
    return ContextPack.objects.filter(
        id=raw_context_pack_id,
        company=run.graph_version.graph,
        operation=run,
    ).first()


def _evidence_usage_key(
    *,
    context_pack: ContextPack | None,
    asset: Asset,
    version: AssetVersion | None,
    extract: AssetExtract | None,
    operation: Run | None,
    task: TaskRecord | None,
    node_run: NodeRun | None,
    decision: DecisionRecord | None,
    deliverable_id: UUID | None,
    used_for: str,
) -> str:
    payload = {
        "context_pack_id": str(context_pack.id) if context_pack else None,
        "asset_id": str(asset.id),
        "asset_version_id": str(version.id) if version else None,
        "asset_extract_id": str(extract.id) if extract else None,
        "operation_id": str(operation.id) if operation else None,
        "task_id": str(task.id) if task else None,
        "node_run_id": str(node_run.id) if node_run else None,
        "decision_id": str(decision.id) if decision else None,
        "deliverable_id": str(deliverable_id) if deliverable_id else None,
        "used_for": used_for,
    }
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _bounded_context_fields(fields: dict[str, Any]) -> dict[str, Any]:
    bounded = {key: _bound_context_value(value) for key, value in fields.items()}
    shrink_order = [
        "memory_refs_json",
        "decision_refs_json",
        "asset_refs_json",
        "policy_refs_json",
        "assumptions_json",
    ]
    while _json_size(bounded) > MAX_CONTEXT_FIELD_BUDGET_BYTES:
        removed = False
        for key in shrink_order:
            value = bounded.get(key)
            if isinstance(value, list) and value:
                value.pop()
                removed = True
                if _json_size(bounded) <= MAX_CONTEXT_FIELD_BUDGET_BYTES:
                    break
        if removed:
            continue
        bounded["brief_snapshot_json"] = _bound_context_value(
            bounded.get("brief_snapshot_json"),
            string_limit=250,
            list_limit=5,
            dict_items=20,
        )
        if _json_size(bounded) <= MAX_CONTEXT_FIELD_BUDGET_BYTES:
            break
        bounded["brief_snapshot_json"] = {"truncated": True}
        break
    return bounded


def _bound_context_value(
    value: Any,
    *,
    string_limit: int = MAX_CONTEXT_STRING_LENGTH,
    list_limit: int = MAX_CONTEXT_LIST_ITEMS,
    dict_items: int = MAX_CONTEXT_DICT_ITEMS,
    depth: int = 0,
) -> Any:
    if value is None or isinstance(value, (bool, int, float)):
        return value
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, str):
        return value[:string_limit]
    if depth >= 6:
        return str(value)[:string_limit]
    if isinstance(value, list):
        return [
            _bound_context_value(
                item,
                string_limit=string_limit,
                list_limit=list_limit,
                dict_items=dict_items,
                depth=depth + 1,
            )
            for item in value[:list_limit]
        ]
    if isinstance(value, dict):
        bounded: dict[str, Any] = {}
        for index, key in enumerate(sorted(value.keys(), key=str)):
            if index >= dict_items:
                break
            bounded[str(key)[:120]] = _bound_context_value(
                value[key],
                string_limit=string_limit,
                list_limit=list_limit,
                dict_items=dict_items,
                depth=depth + 1,
            )
        return bounded
    return str(value)[:string_limit]


def _json_size(value: Any) -> int:
    return len(
        json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    )
