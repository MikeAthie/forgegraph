from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from django.utils import timezone

from infrastructure.orm.models import WorkWhiteboard


@dataclass(frozen=True)
class ClientReviewComment:
    page: int
    comment_type: str
    content: str
    rect: list[float] | None = None
    created_at: str = ""


def classify_client_review_comment(comment: ClientReviewComment) -> dict[str, Any]:
    """Map client PDF feedback into a durable whiteboard card shape."""

    text = comment.content.strip()
    lowered = text.lower()
    if _is_brand_logo_feedback(lowered):
        category = "brand_logo_requirement"
        department_slug = "brand_content"
        severity = "revision"
        title = "Add Legacy logo / brand mark to social posts"
        handoff_target = "qa_compliance"
        acceptance_criteria = [
            "All social post assets include an approved Legacy logo or brand mark treatment.",
            "The package manifest records brand_mark_applied=true for each post.",
            "No fake or unrelated brand marks appear in generated imagery.",
        ]
    elif _is_logistics_feedback(lowered):
        category = "logistics_ambiguity"
        department_slug = "channel_execution"
        severity = "revision"
        title = "Clarify social rollout wording versus shipping logistics"
        handoff_target = "client_approval_ops"
        acceptance_criteria = [
            "Replace ambiguous distribution language with weekend social rollout or posting schedule.",
            "State that shipping/fulfillment timelines require separate logistics details.",
            "Client-facing copy does not imply envíos or fulfillment unless provided by the client.",
        ]
    elif _is_asset_quality_feedback(lowered):
        category = "asset_quality"
        department_slug = "qa_compliance"
        severity = "blocker"
        title = "Replace or repair client-flagged weak image"
        handoff_target = "brand_content"
        acceptance_criteria = [
            "Client-flagged weak assets are replaced or marked blocked before package readiness.",
            "Per-asset QA identifies the affected post index and issue code.",
            "The final package is not labeled production-ready while a flagged asset remains.",
        ]
    else:
        category = "strategy_rationale"
        department_slug = "strategy_research"
        severity = "revision"
        title = "Explain Optical Noir strategy rationale"
        handoff_target = "brand_content"
        acceptance_criteria = [
            "Client-facing strategy explains Optical Noir as premium contrast/product photography.",
            "Copy does not imply sunglasses are being promoted for nighttime use.",
            "The rationale connects the visual system to brand recall and product focus.",
        ]
    return {
        "card_type": "client_feedback",
        "title": title,
        "status": "triaged",
        "category": category,
        "department_slug": department_slug,
        "severity": severity,
        "source": "pdf_annotation",
        "page": comment.page,
        "comment_type": comment.comment_type,
        "content": text,
        "acceptance_criteria": acceptance_criteria,
        "handoff_target": handoff_target,
        "evidence_links": [
            {
                "type": "pdf_annotation",
                "page": comment.page,
                "comment_type": comment.comment_type,
                "rect": comment.rect,
                "created_at": comment.created_at,
            }
        ],
    }


def record_client_review_feedback(
    *,
    whiteboard: WorkWhiteboard,
    comments: list[ClientReviewComment],
    source: str,
) -> dict[str, Any]:
    """Persist client review comments as whiteboard-owned feedback/card metadata."""

    cards = [classify_client_review_comment(comment) for comment in comments]
    payload = {
        "source": source,
        "recorded_at": timezone.now().isoformat(),
        "comments": [asdict(comment) for comment in comments],
        "cards": cards,
    }
    metadata = dict(whiteboard.metadata_json or {})
    metadata["client_feedback"] = payload
    whiteboard.metadata_json = metadata
    whiteboard.save(update_fields=["metadata_json", "updated_at"])
    return payload


def _is_brand_logo_feedback(lowered: str) -> bool:
    return "logo" in lowered or "legacy" in lowered and "marca" in lowered


def _is_logistics_feedback(lowered: str) -> bool:
    logistics_tokens = ("logistica", "logística", "envios", "envíos", "shipping", "fulfillment")
    return any(token in lowered for token in logistics_tokens)


def _is_asset_quality_feedback(lowered: str) -> bool:
    quality_tokens = ("culera", "no cach", "mal", "bad image", "off-target")
    return any(token in lowered for token in quality_tokens)
