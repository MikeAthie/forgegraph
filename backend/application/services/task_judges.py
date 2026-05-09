"""Backend-owned task judge configuration and deterministic evaluation."""

from __future__ import annotations

import json
import re
from typing import Any

from django.db import transaction
from django.utils import timezone

from infrastructure.orm.models import TaskJudge, TaskRecord, User

MAX_CRITERIA = 12
MAX_CRITERION_LENGTH = 500
MAX_EVIDENCE_SNAPSHOT_BYTES = 64 * 1024
STOPWORDS = {
    "about",
    "after",
    "against",
    "also",
    "and",
    "are",
    "before",
    "but",
    "can",
    "from",
    "has",
    "have",
    "include",
    "includes",
    "into",
    "must",
    "not",
    "only",
    "our",
    "should",
    "task",
    "that",
    "the",
    "their",
    "this",
    "with",
}


def normalize_judge_criteria(criteria: Any) -> list[str]:
    raw_items: list[Any]
    if isinstance(criteria, str):
        raw_items = re.split(r"\r?\n|;", criteria)
    elif isinstance(criteria, list):
        raw_items = criteria
    else:
        raw_items = []

    normalized: list[str] = []
    for item in raw_items:
        text = str(item or "").strip()
        if not text:
            continue
        normalized.append(text[:MAX_CRITERION_LENGTH])
        if len(normalized) >= MAX_CRITERIA:
            break
    return normalized


def normalize_judge_evidence_snapshot(evidence_snapshot: Any) -> dict[str, Any]:
    if evidence_snapshot in (None, ""):
        return {}
    if not isinstance(evidence_snapshot, dict):
        return {"value": _json_text(evidence_snapshot)[:MAX_EVIDENCE_SNAPSHOT_BYTES]}
    try:
        encoded = json.dumps(evidence_snapshot, sort_keys=True, ensure_ascii=False)
    except TypeError:
        encoded = json.dumps(
            json.loads(json.dumps(evidence_snapshot, default=str)),
            sort_keys=True,
            ensure_ascii=False,
        )
    if len(encoded.encode("utf-8")) > MAX_EVIDENCE_SNAPSHOT_BYTES:
        return {
            "truncated": True,
            "json_excerpt": encoded[:MAX_EVIDENCE_SNAPSHOT_BYTES],
        }
    parsed = json.loads(encoded)
    return parsed if isinstance(parsed, dict) else {"value": parsed}


def task_judge_payload(judge: TaskJudge | None) -> dict[str, Any] | None:
    if judge is None:
        return None
    return {
        "id": str(judge.id),
        "task_id": str(judge.task_id),
        "organization_id": str(judge.organization_id),
        "execution_id": str(judge.execution_id),
        "source_node_id": judge.source_node_id,
        "title": judge.title,
        "instructions": judge.instructions,
        "criteria": normalize_judge_criteria(judge.criteria_json),
        "pass_threshold": judge.pass_threshold,
        "status": judge.status,
        "score": judge.score,
        "result": judge.result_json,
        "evaluated_at": judge.evaluated_at.isoformat() if judge.evaluated_at else None,
        "created_at": judge.created_at.isoformat(),
        "updated_at": judge.updated_at.isoformat(),
    }


def task_judge_summary(judge: TaskJudge | None) -> dict[str, Any] | None:
    if judge is None:
        return None
    return {
        "id": str(judge.id),
        "title": judge.title,
        "criteria_count": len(normalize_judge_criteria(judge.criteria_json)),
        "pass_threshold": judge.pass_threshold,
        "status": judge.status,
        "score": judge.score,
        "evaluated_at": judge.evaluated_at.isoformat() if judge.evaluated_at else None,
    }


@transaction.atomic
def configure_task_judge(
    *,
    task: TaskRecord,
    user: User,
    title: str,
    instructions: str,
    criteria: Any,
    pass_threshold: int,
    evidence_snapshot: Any = None,
) -> TaskJudge:
    normalized_criteria = normalize_judge_criteria(criteria)
    normalized_evidence = normalize_judge_evidence_snapshot(evidence_snapshot)
    judge, created = TaskJudge.objects.update_or_create(
        task=task,
        defaults={
            "organization": task.organization,
            "execution": task.execution,
            "source_node_id": task.source_node_id,
            "title": title.strip()[:255],
            "instructions": instructions.strip(),
            "criteria_json": normalized_criteria,
            "pass_threshold": pass_threshold,
            "status": "pending",
            "score": None,
            "result_json": {"evidence_snapshot": normalized_evidence}
            if normalized_evidence
            else {},
            "evaluated_at": None,
            "updated_by": user,
        },
    )
    if created:
        judge.created_by = user
        judge.save(update_fields=["created_by", "updated_at"])
    return judge


def _json_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    try:
        return json.dumps(value, sort_keys=True, ensure_ascii=False)
    except TypeError:
        return str(value)


def _collect_evidence(judge: TaskJudge) -> tuple[str, list[dict[str, Any]]]:
    task = judge.task
    evidence_parts: list[str] = []
    sources: list[dict[str, Any]] = []

    def add_source(name: str, value: Any) -> None:
        text = _json_text(value).strip()
        if not text:
            sources.append({"source": name, "available": False, "length": 0})
            return
        evidence_parts.append(text)
        sources.append({"source": name, "available": True, "length": len(text)})

    add_source("task_summary", task.summary)
    current_step = task.current_step if task.current_step_id else None
    if current_step is not None:
        add_source("current_step_output", current_step.output_json)
        add_source("current_step_error", current_step.error_json)
    else:
        add_source("current_step_output", None)
        add_source("current_step_error", None)
    add_source("run_output", task.execution.output_json)
    add_source("run_error", task.execution.error_message)
    if isinstance(judge.result_json, dict):
        add_source("judge_evidence_snapshot", judge.result_json.get("evidence_snapshot"))

    return "\n\n".join(evidence_parts).lower(), sources


def _keywords(text: str) -> list[str]:
    terms = re.findall(r"[a-z0-9][a-z0-9_-]{2,}", text.lower())
    seen: set[str] = set()
    result: list[str] = []
    for term in terms:
        if term in STOPWORDS or term in seen:
            continue
        seen.add(term)
        result.append(term)
    return result


def _evaluate_criterion(criterion: str, evidence_text: str) -> dict[str, Any]:
    normalized_criterion = " ".join(criterion.lower().split())
    if normalized_criterion and normalized_criterion in evidence_text:
        terms = _keywords(criterion)
        return {
            "criterion": criterion,
            "passed": True,
            "score": 100,
            "matched_terms": terms,
            "missing_terms": [],
            "match_type": "exact_phrase",
        }

    terms = _keywords(criterion)
    if not terms:
        return {
            "criterion": criterion,
            "passed": False,
            "score": 0,
            "matched_terms": [],
            "missing_terms": [],
            "match_type": "no_keywords",
        }

    matched = [term for term in terms if term in evidence_text]
    missing = [term for term in terms if term not in evidence_text]
    score = round((len(matched) / len(terms)) * 100)
    return {
        "criterion": criterion,
        "passed": score >= 60,
        "score": score,
        "matched_terms": matched,
        "missing_terms": missing,
        "match_type": "keyword_overlap",
    }


@transaction.atomic
def evaluate_task_judge(*, judge: TaskJudge, user: User) -> TaskJudge:
    criteria = normalize_judge_criteria(judge.criteria_json)
    evidence_snapshot = (
        judge.result_json.get("evidence_snapshot") if isinstance(judge.result_json, dict) else {}
    )
    evidence_text, evidence_sources = _collect_evidence(judge)
    evaluated_at = timezone.now()

    if not criteria or not evidence_text.strip():
        judge.status = "inconclusive"
        judge.score = 0
        judge.result_json = {
            "algorithm": "deterministic_keyword_v1",
            "criteria": [],
            "evidence_sources": evidence_sources,
            "evidence_snapshot": evidence_snapshot,
            "evaluated_by": str(user.id),
            "reason": "Judge needs at least one criterion and backend task evidence.",
        }
    else:
        criterion_results = [
            _evaluate_criterion(criterion, evidence_text) for criterion in criteria
        ]
        score = round(
            sum(int(result["score"]) for result in criterion_results) / len(criterion_results)
        )
        judge.score = score
        judge.status = "passed" if score >= judge.pass_threshold else "failed"
        judge.result_json = {
            "algorithm": "deterministic_keyword_v1",
            "criteria": criterion_results,
            "evidence_sources": evidence_sources,
            "evidence_snapshot": evidence_snapshot,
            "evaluated_by": str(user.id),
            "passed_count": len([result for result in criterion_results if result["passed"]]),
            "total_count": len(criterion_results),
        }

    judge.evaluated_at = evaluated_at
    judge.updated_by = user
    judge.save(
        update_fields=[
            "status",
            "score",
            "result_json",
            "evaluated_at",
            "updated_by",
            "updated_at",
        ]
    )
    return judge
