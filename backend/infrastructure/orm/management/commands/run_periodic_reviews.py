from __future__ import annotations

import json
from datetime import date
from typing import Any, cast

from django.core.management.base import BaseCommand, CommandError, CommandParser

from application.services.periodic_reviews import (
    PeriodicReviewError,
    current_due_review_period,
    due_periodic_reviews,
    execute_periodic_review,
)
from infrastructure.orm.models import Graph, PeriodicReviewDefinition, User


class Command(BaseCommand):
    help = "Run generic periodic review definitions that are due or explicitly selected."

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument("--due", action="store_true", default=False)
        parser.add_argument("--company-id", default="")
        parser.add_argument("--review-definition-id", default="")
        parser.add_argument("--period-start", default="")
        parser.add_argument("--period-end", default="")
        parser.add_argument("--dry-run", action="store_true", default=False)
        parser.add_argument("--force", action="store_true", default=False)
        parser.add_argument("--json", action="store_true", dest="output_json", default=False)

    def handle(self, *args: Any, **options: Any) -> None:
        company = _company(options.get("company_id") or "")
        review_id = str(options.get("review_definition_id") or "").strip()
        period_start = _optional_date(str(options.get("period_start") or "").strip())
        period_end = _optional_date(str(options.get("period_end") or "").strip())
        if (period_start is None) != (period_end is None):
            raise CommandError("--period-start and --period-end must be provided together.")
        force = bool(options.get("force", False))
        dry_run = bool(options.get("dry_run", False))
        if not bool(options.get("due")) and not review_id:
            raise CommandError("Use --due or --review-definition-id.")

        targets = _targets(
            company=company,
            review_id=review_id,
            due=bool(options.get("due")),
            force=force,
        )
        executions: list[dict[str, Any]] = []
        errors: list[dict[str, str]] = []
        for review in targets:
            user = _actor(review)
            period = current_due_review_period(review)
            try:
                summary = execute_periodic_review(
                    review=review,
                    user=user,
                    period_start=period_start or period.period_start,
                    period_end=period_end or period.period_end,
                    dry_run=dry_run,
                    force=force,
                    source_type="computed",
                    notes="Scheduled periodic review execution.",
                )
            except PeriodicReviewError as exc:
                errors.append(
                    {
                        "review_definition_id": str(review.id),
                        "code": exc.code,
                        "message": exc.message,
                    }
                )
                continue
            executions.append(summary.as_payload())

        payload = {
            "schema": "periodic_review_execution_batch.v1",
            "dry_run": dry_run,
            "force": force,
            "executions": executions,
            "errors": errors,
            "created_or_skipped_count": len(executions),
            "error_count": len(errors),
        }
        if options.get("output_json"):
            self.stdout.write(json.dumps(payload, sort_keys=True))
            return
        for item in executions:
            self.stdout.write(
                f"{item['review_definition_id']} {item['period_start']}.."
                f"{item['period_end']} {item['status']}"
            )
        if errors:
            raise CommandError(f"{len(errors)} periodic review(s) failed.")


def _targets(
    *,
    company: Graph | None,
    review_id: str,
    due: bool,
    force: bool,
) -> list[PeriodicReviewDefinition]:
    if review_id:
        queryset = PeriodicReviewDefinition.objects.select_related("company", "program").filter(
            id=review_id
        )
        if company is not None:
            queryset = queryset.filter(company=company)
        return list(queryset)
    if due:
        return [review for review, _period in due_periodic_reviews(company=company, force=force)]
    return []


def _company(company_id: str) -> Graph | None:
    if not company_id:
        return None
    company = Graph.objects.filter(id=company_id).first()
    if company is None:
        raise CommandError("Company was not found.")
    return cast(Graph, company)


def _actor(review: PeriodicReviewDefinition) -> User:
    if review.created_by_id and review.created_by is not None:
        return review.created_by
    return review.company.owner


def _optional_date(value: str) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise CommandError(f"Invalid date: {value}") from exc
