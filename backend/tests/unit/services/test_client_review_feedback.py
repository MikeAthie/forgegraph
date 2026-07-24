from __future__ import annotations

from typing import Any

from application.services.client_review_feedback import (
    ClientReviewComment,
    classify_client_review_comment,
    record_client_review_feedback,
)


class FakeWhiteboard:
    def __init__(self, metadata_json: dict[str, Any] | None = None) -> None:
        self.metadata_json = metadata_json or {}
        self.saved_update_fields: list[str] | None = None

    def save(self, *, update_fields: list[str]) -> None:
        self.saved_update_fields = update_fields


def test_client_review_comment_classifier_routes_pdf_feedback_to_department_cards() -> None:
    comments = [
        ClientReviewComment(
            page=1,
            comment_type="FreeText",
            content='Por qué la IA decidió hacer una campaña "Noir" y cosas de noche para lentes de sol?',
        ),
        ClientReviewComment(
            page=2,
            comment_type="FreeText",
            content="Esta imagen salió culera, no cachó ahí muy bien jaja",
        ),
        ClientReviewComment(
            page=3,
            comment_type="FreeText",
            content="Weekend distribuition esta ligado a un timeline de logistica para los envios?",
        ),
        ClientReviewComment(
            page=4,
            comment_type="FreeText",
            content="Logo Legacy",
        ),
    ]

    cards = [classify_client_review_comment(comment) for comment in comments]

    assert [card["category"] for card in cards] == [
        "strategy_rationale",
        "asset_quality",
        "logistics_ambiguity",
        "brand_logo_requirement",
    ]
    assert [card["department_slug"] for card in cards] == [
        "strategy_research",
        "qa_compliance",
        "channel_execution",
        "brand_content",
    ]
    assert all(card["status"] == "triaged" for card in cards)
    assert all(card["acceptance_criteria"] for card in cards)


def test_record_client_review_feedback_persists_cards_on_whiteboard_metadata() -> None:
    whiteboard = FakeWhiteboard(metadata_json={"existing": "preserved"})

    result = record_client_review_feedback(
        whiteboard=whiteboard,  # type: ignore[arg-type]
        comments=[
            ClientReviewComment(
                page=3,
                comment_type="FreeText",
                content="Aqui creo que en todos los posts debe de salir el logo de Legacy",
            )
        ],
        source="reviewed_pdf_annotations",
    )

    feedback = whiteboard.metadata_json["client_feedback"]
    assert whiteboard.metadata_json["existing"] == "preserved"
    assert whiteboard.saved_update_fields == ["metadata_json", "updated_at"]
    assert feedback["source"] == "reviewed_pdf_annotations"
    assert feedback["cards"] == result["cards"]
    assert feedback["cards"][0]["category"] == "brand_logo_requirement"
    assert feedback["cards"][0]["department_slug"] == "brand_content"
    assert feedback["cards"][0]["handoff_target"] == "qa_compliance"
    assert feedback["cards"][0]["evidence_links"][0]["type"] == "pdf_annotation"
