"""Run the ForgeGraph-owned CareerOps first-prompt discovery flow."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from django.core.management.base import BaseCommand, CommandError, CommandParser

from application.services.career_ops_first_prompt import run_career_ops_first_prompt
from application.services.career_ops_live_search import (
    StaticCareerOpsLiveSearchProvider,
    run_career_ops_live_search,
)
from application.services.tenancy import ensure_default_organization
from infrastructure.orm.models import User

DEFAULT_CONSTRAINTS = {
    "citizenships": ["Mexico", "Spain"],
    "work_authorized_regions": ["Mexico", "European Union", "Spain"],
    "excluded_regions": ["United States"],
    "no_us_work_visa": True,
    "willing_to_relocate": True,
    "target_salary_usd": 60000,
    "salary_flexible": True,
}


class Command(BaseCommand):
    help = "Run the ForgeGraph-owned CareerOps first prompt: company, whiteboard, kanban cards, possible jobs."

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument("--user-id", default="")
        parser.add_argument("--user-email", default="careerops-operator@example.local")
        parser.add_argument("--cv-text-file", default="")
        parser.add_argument("--cv-pdf-path", default="")
        parser.add_argument("--cv-text", default="")
        parser.add_argument("--prompt", required=True)
        parser.add_argument("--idempotency-key", required=True)
        parser.add_argument("--constraints-json", default="")
        parser.add_argument("--live-postings-json-file", default="")
        parser.add_argument("--live-postings-json", default="")
        parser.add_argument("--live-search-skill", action="store_true")
        parser.add_argument("--live-search-query", action="append", default=[])
        parser.add_argument("--live-search-max-results", type=int, default=10)
        parser.add_argument("--live-search-results-json-file", default="")

    def handle(self, *args: object, **options: object) -> None:
        user = _resolve_user(user_id=str(options["user_id"]), user_email=str(options["user_email"]))
        cv_text = _load_cv_text(
            cv_text=str(options["cv_text"]),
            cv_text_file=str(options["cv_text_file"]),
            cv_pdf_path=str(options["cv_pdf_path"]),
        )
        constraints = _load_constraints(str(options["constraints_json"]))
        live_postings = _load_live_postings(
            raw_json=str(options["live_postings_json"]),
            json_file=str(options["live_postings_json_file"]),
        )
        source_mode = "live_url_discovery" if live_postings is not None else "deterministic_fake_provider"
        live_search_options = _live_search_options(options)
        if live_postings is None and bool(options["live_search_skill"]):
            live_postings = _run_live_search_skill(
                cv_text=cv_text,
                constraints=constraints,
                prompt=str(options["prompt"]),
                live_search_queries=live_search_options["queries"],
                max_results=live_search_options["max_results"],
                results_json_file=live_search_options["results_json_file"],
            )
            source_mode = "live_search_skill"
        elif live_search_options["has_live_search_inputs"] and live_postings is None:
            raise CommandError("--live-search-query/--live-search-results-json-file require --live-search-skill.")
        result = run_career_ops_first_prompt(
            actor=user,
            cv_text=cv_text,
            constraints=constraints,
            prompt=str(options["prompt"]),
            idempotency_key=str(options["idempotency_key"]),
            live_postings=live_postings,
        )
        payload = {
            "status": "ok",
            "source_mode": source_mode,
            "company_id": result.company_id,
            "whiteboard_id": result.whiteboard_id,
            "program_id": result.program_id,
            "engagement_id": result.engagement_id,
            "department_ids": result.department_ids,
            "task_ids": result.task_ids,
            "postings": result.postings,
            "external_side_effects_allowed": False,
        }
        self.stdout.write(json.dumps(payload, ensure_ascii=False, sort_keys=True))


def _resolve_user(*, user_id: str, user_email: str) -> User:
    if user_id:
        try:
            user = User.objects.get(id=user_id)
        except User.DoesNotExist as exc:
            raise CommandError(f"User not found: {user_id}") from exc
    else:
        email = user_email.strip() or "careerops-operator@example.local"
        user = User.objects.filter(email=email).first() or User.objects.create_user(email=email)
    ensure_default_organization(user)
    return user


def _load_cv_text(*, cv_text: str, cv_text_file: str, cv_pdf_path: str) -> str:
    if cv_text.strip():
        return cv_text
    if cv_text_file.strip():
        return _read_text_file(cv_text_file)
    if cv_pdf_path.strip():
        return _extract_pdf_text(cv_pdf_path)
    raise CommandError("Provide one of --cv-text, --cv-text-file, or --cv-pdf-path.")


def _read_text_file(path_value: str) -> str:
    path = Path(path_value)
    if not path.exists():
        raise CommandError(f"CV text file does not exist: {path_value}")
    return path.read_text(encoding="utf-8")


def _extract_pdf_text(path_value: str) -> str:
    path = Path(path_value)
    if not path.exists():
        raise CommandError(f"CV PDF does not exist: {path_value}")
    try:
        import fitz  # type: ignore[import-not-found]
    except Exception as exc:  # pragma: no cover - depends on runtime image
        raise CommandError("PyMuPDF/fitz is required for --cv-pdf-path extraction.") from exc
    try:
        doc = fitz.open(str(path))
        return "\n\n".join(page.get_text("text") for page in doc)
    except Exception as exc:  # pragma: no cover - defensive around malformed PDFs
        raise CommandError(f"Failed to extract CV PDF text: {exc}") from exc


def _load_live_postings(*, raw_json: str, json_file: str) -> list[dict[str, Any]] | None:
    if raw_json.strip():
        return _parse_live_postings(raw_json)
    if json_file.strip():
        path = Path(json_file)
        if not path.exists():
            raise CommandError(f"Live postings JSON file does not exist: {json_file}")
        return _parse_live_postings(path.read_text(encoding="utf-8"))
    return None


def _parse_live_postings(raw_json: str) -> list[dict[str, Any]]:
    try:
        parsed = json.loads(raw_json)
    except json.JSONDecodeError as exc:
        raise CommandError(f"Invalid live postings JSON: {exc}") from exc
    if not isinstance(parsed, list):
        raise CommandError("Live postings JSON must decode to a list of objects.")
    postings: list[dict[str, Any]] = []
    for index, item in enumerate(parsed, start=1):
        if not isinstance(item, dict):
            raise CommandError(f"Live posting at index {index} must be an object.")
        postings.append(dict(item))
    return postings


def _live_search_options(options: dict[str, object]) -> dict[str, Any]:
    raw_queries = options.get("live_search_query") or []
    if isinstance(raw_queries, str):
        queries = [raw_queries]
    else:
        queries = [str(query) for query in raw_queries if str(query).strip()]
    results_json_file = str(options.get("live_search_results_json_file") or "")
    max_results = int(options.get("live_search_max_results") or 10)
    return {
        "queries": queries,
        "max_results": max_results,
        "results_json_file": results_json_file,
        "has_live_search_inputs": bool(queries or results_json_file.strip()),
    }


def _run_live_search_skill(
    *,
    cv_text: str,
    constraints: dict[str, Any],
    prompt: str,
    live_search_queries: list[str],
    max_results: int,
    results_json_file: str,
) -> list[dict[str, Any]]:
    provider = None
    if results_json_file.strip():
        path = Path(results_json_file)
        if not path.exists():
            raise CommandError(f"Live search results JSON file does not exist: {results_json_file}")
        provider = StaticCareerOpsLiveSearchProvider(
            _parse_live_postings(path.read_text(encoding="utf-8")),
            provider_name="career_ops_live_search_fixture",
        )
    return run_career_ops_live_search(
        cv_text=cv_text,
        constraints=constraints,
        prompt=prompt,
        provider=provider,
        extra_queries=live_search_queries,
        max_results=max_results,
    )


def _load_constraints(raw_json: str) -> dict[str, Any]:
    if not raw_json.strip():
        return dict(DEFAULT_CONSTRAINTS)
    try:
        parsed = json.loads(raw_json)
    except json.JSONDecodeError as exc:
        raise CommandError(f"Invalid --constraints-json: {exc}") from exc
    if not isinstance(parsed, dict):
        raise CommandError("--constraints-json must decode to an object.")
    return {**DEFAULT_CONSTRAINTS, **parsed}
