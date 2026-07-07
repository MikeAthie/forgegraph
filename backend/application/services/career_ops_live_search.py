"""Deterministic CareerOps live-search skill helpers.

The service prepares search queries and normalizes provider hits into candidate
live posting records. It owns no durable state and performs no employer-facing
actions.
"""

from __future__ import annotations

import html
import re
from dataclasses import dataclass
from html.parser import HTMLParser
from typing import Any, Protocol
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse
from urllib.request import Request, urlopen

SOURCE_MODE = "live_search_skill"
DEFAULT_MAX_RESULTS = 10

_SEARCH_USER_AGENT = "ForgeGraphCareerOpsLiveSearch/1.0"
_TRACKING_QUERY_KEYS = {
    "fbclid",
    "gclid",
    "igshid",
    "mc_cid",
    "mc_eid",
    "msclkid",
    "ref",
    "source",
    "spm",
    "utm",
}
_SKILL_KEYWORDS = (
    "Python",
    "FastAPI",
    "Django",
    "Go",
    "PostgreSQL",
    "Redis",
    "Celery",
    "RAG",
    "LangGraph",
    "agentic workflows",
    "Prometheus",
    "React",
    "Next.js",
    "TypeScript",
)
_LOCATION_PRIORITY = (
    "Spain",
    "Mexico",
    "European Union",
    "Europe",
    "Remote",
)
_ACTION_FIELD_NAMES = {
    "apply",
    "apply_url",
    "applyUrl",
    "application_url",
    "applicationUrl",
    "application_link",
    "browser_action",
    "browser_submission",
    "send_payload",
    "submission_payload",
}


@dataclass(frozen=True, slots=True)
class CareerOpsLiveSearchIntent:
    query: str
    max_results: int = DEFAULT_MAX_RESULTS
    source_mode: str = SOURCE_MODE
    external_side_effects_allowed: bool = False


class CareerOpsLiveSearchProvider(Protocol):
    provider_name: str

    def search(self, *, query: str, max_results: int) -> list[dict[str, Any]]:
        """Return provider hits for a search query."""


class StaticCareerOpsLiveSearchProvider:
    """Deterministic provider for tests and manual JSON-fixture reruns."""

    def __init__(self, hits: list[dict[str, Any]], *, provider_name: str = "career_ops_live_search_fixture") -> None:
        self.provider_name = provider_name
        self._hits = [dict(hit) for hit in hits if isinstance(hit, dict)]

    def search(self, *, query: str, max_results: int) -> list[dict[str, Any]]:
        del query
        return [dict(hit) for hit in self._hits[: _max_results(max_results)]]


class StdlibCareerOpsLiveSearchProvider:
    """Best-effort web search provider using only Python stdlib.

    Search failures intentionally degrade to an empty result set so manual reruns
    do not make the CareerOps command brittle.
    """

    provider_name = "stdlib_duckduckgo_html"

    def __init__(self, *, timeout_seconds: float = 8.0) -> None:
        self.timeout_seconds = max(1.0, min(float(timeout_seconds), 20.0))

    def search(self, *, query: str, max_results: int) -> list[dict[str, Any]]:
        normalized_query = _bounded_text(query, 500)
        if not normalized_query:
            return []
        result_limit = _max_results(max_results)
        duckduckgo_url = f"https://html.duckduckgo.com/html/?{urlencode({'q': normalized_query})}"
        duckduckgo_results = _parse_duckduckgo_html(
            _fetch_search_html(duckduckgo_url, timeout_seconds=self.timeout_seconds),
            limit=result_limit,
        )
        if duckduckgo_results:
            return duckduckgo_results
        bing_url = f"https://www.bing.com/search?{urlencode({'q': normalized_query})}"
        return _parse_bing_html(
            _fetch_search_html(bing_url, timeout_seconds=self.timeout_seconds),
            limit=result_limit,
        )


def build_career_ops_live_search_queries(
    *,
    cv_text: str,
    constraints: dict[str, Any],
    prompt: str,
    extra_queries: list[str] | None = None,
    max_queries: int = 8,
) -> list[str]:
    """Build deterministic search queries from CV facts, constraints, and prompt."""

    queries: list[str] = []
    for query in extra_queries or []:
        _append_unique_query(queries, query)

    skills = _extract_skills(cv_text)
    primary_skill = skills[0] if skills else "backend"
    secondary_skill = skills[1] if len(skills) > 1 else "AI"
    locations = _authorized_search_locations(constraints)
    for location in locations:
        _append_unique_query(queries, f'"{primary_skill}" "{secondary_skill}" backend AI jobs {location}')

    if any(skill.casefold() == "rag" for skill in skills):
        for location in locations[:2]:
            _append_unique_query(queries, f'RAG backend engineer jobs {location}')

    workflow_phrase = _workflow_phrase(cv_text=cv_text, prompt=prompt)
    if workflow_phrase:
        for location in locations[:2]:
            _append_unique_query(queries, f'"{workflow_phrase}" backend jobs {location}')

    prompt_terms = _prompt_role_terms(prompt)
    if prompt_terms:
        for location in locations[:2]:
            _append_unique_query(queries, f"{prompt_terms} jobs {location}")

    return queries[: max(1, min(int(max_queries or 1), 20))]


def run_career_ops_live_search(
    *,
    cv_text: str,
    constraints: dict[str, Any],
    prompt: str,
    provider: CareerOpsLiveSearchProvider | None = None,
    extra_queries: list[str] | None = None,
    max_results: int = DEFAULT_MAX_RESULTS,
) -> list[dict[str, Any]]:
    """Run the live-search skill and return normalized live posting records."""

    result_limit = _max_results(max_results)
    search_provider = provider or StdlibCareerOpsLiveSearchProvider()
    queries = build_career_ops_live_search_queries(
        cv_text=cv_text,
        constraints=constraints,
        prompt=prompt,
        extra_queries=extra_queries,
    )
    postings: list[dict[str, Any]] = []
    seen_urls: set[str] = set()
    for query in queries:
        if len(postings) >= result_limit:
            break
        remaining = result_limit - len(postings)
        try:
            hits = search_provider.search(query=query, max_results=remaining)
        except Exception:
            hits = []
        for rank, hit in enumerate(hits, start=1):
            if not isinstance(hit, dict):
                continue
            posting = normalize_career_ops_live_search_hit(
                hit,
                provider_name=getattr(search_provider, "provider_name", "career_ops_live_search_provider"),
                source_query=query,
                source_rank=rank,
            )
            if not posting:
                continue
            url = str(posting["url"])
            if url in seen_urls:
                continue
            seen_urls.add(url)
            postings.append(posting)
            if len(postings) >= result_limit:
                break
    return postings


def normalize_career_ops_live_search_hit(
    hit: dict[str, Any],
    *,
    provider_name: str,
    source_query: str,
    source_rank: int,
) -> dict[str, Any]:
    url = _canonical_url(hit.get("url") or hit.get("href") or hit.get("link"))
    if not url:
        return {}

    title = _bounded_text(hit.get("title") or _title_from_url(url) or "Untitled role", 240)
    company = _bounded_text(hit.get("company") or hit.get("employer") or _company_from_url(url), 160)
    location = _bounded_text(hit.get("location") or hit.get("locations") or "", 240)
    if not location:
        location = _safe_location_from_source_query(source_query)
    description = _bounded_text(
        hit.get("description") or hit.get("summary") or hit.get("snippet") or "",
        4000,
    )
    provider = _bounded_text(hit.get("provider") or provider_name or "career_ops_live_search_provider", 120)
    posting = {
        "title": title or "Untitled role",
        "company": company or "Unknown employer",
        "location": location,
        "url": url,
        "description": description,
        "salary_range_usd": _salary_range(hit.get("salary_range_usd")),
        "provider": provider,
        "source_query": _bounded_text(source_query, 500),
        "source_rank": max(1, int(source_rank or 1)),
        "source_mode": SOURCE_MODE,
        "external_side_effects_allowed": False,
    }
    return _drop_action_fields(posting)


class _DuckDuckGoHTMLParser(HTMLParser):
    def __init__(self, *, limit: int) -> None:
        super().__init__(convert_charrefs=True)
        self.limit = limit
        self.results: list[dict[str, Any]] = []
        self._active_link: dict[str, str] | None = None
        self._capture_link_text = False
        self._capture_snippet = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if len(self.results) >= self.limit:
            return
        attributes = {key: value or "" for key, value in attrs}
        classes = set(attributes.get("class", "").split())
        if tag.lower() == "a" and "result__a" in classes:
            self._active_link = {"url": _resolve_duckduckgo_href(attributes.get("href", "")), "title": ""}
            self._capture_link_text = True
        elif "result__snippet" in classes and self.results:
            self._capture_snippet = True

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() == "a" and self._capture_link_text and self._active_link is not None:
            if self._active_link.get("url"):
                self.results.append(dict(self._active_link))
            self._active_link = None
            self._capture_link_text = False
        if self._capture_snippet and tag.lower() in {"a", "div", "span"}:
            self._capture_snippet = False

    def handle_data(self, data: str) -> None:
        text = _bounded_text(data, 1000)
        if not text:
            return
        if self._capture_link_text and self._active_link is not None:
            current = self._active_link.get("title", "")
            self._active_link["title"] = _bounded_text(f"{current} {text}", 240)
        elif self._capture_snippet and self.results:
            current = self.results[-1].get("snippet", "")
            self.results[-1]["snippet"] = _bounded_text(f"{current} {text}", 1000)


class _BingHTMLParser(HTMLParser):
    def __init__(self, *, limit: int) -> None:
        super().__init__(convert_charrefs=True)
        self.limit = limit
        self.results: list[dict[str, Any]] = []
        self._active_result: dict[str, str] | None = None
        self._inside_heading = False
        self._capture_title = False
        self._capture_snippet = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        normalized_tag = tag.lower()
        attributes = {key: value or "" for key, value in attrs}
        classes = set(attributes.get("class", "").split())
        if normalized_tag == "li" and "b_algo" in classes:
            self._finish_result()
            if len(self.results) < self.limit:
                self._active_result = {"url": "", "title": "", "snippet": ""}
                self._inside_heading = False
                self._capture_title = False
                self._capture_snippet = False
            return
        if self._active_result is None:
            return
        if normalized_tag == "h2":
            self._inside_heading = True
        elif normalized_tag == "a" and self._inside_heading and not self._active_result.get("url"):
            self._active_result["url"] = attributes.get("href", "")
            self._capture_title = True
        elif normalized_tag == "p" and not self._active_result.get("snippet"):
            self._capture_snippet = True

    def handle_endtag(self, tag: str) -> None:
        if self._active_result is None:
            return
        normalized_tag = tag.lower()
        if normalized_tag == "a" and self._capture_title:
            self._capture_title = False
        elif normalized_tag == "h2":
            self._inside_heading = False
        elif normalized_tag == "p" and self._capture_snippet:
            self._capture_snippet = False
        elif normalized_tag == "li":
            self._finish_result()

    def handle_data(self, data: str) -> None:
        if self._active_result is None:
            return
        text = _bounded_text(data, 1000)
        if not text:
            return
        if self._capture_title:
            current = self._active_result.get("title", "")
            self._active_result["title"] = _bounded_text(f"{current} {text}", 240)
        elif self._capture_snippet:
            current = self._active_result.get("snippet", "")
            self._active_result["snippet"] = _bounded_text(f"{current} {text}", 1000)

    def close(self) -> None:
        super().close()
        self._finish_result()

    def _finish_result(self) -> None:
        if self._active_result is None or len(self.results) >= self.limit:
            self._active_result = None
            return
        url = _bounded_text(self._active_result.get("url", ""), 2000)
        if url:
            result = {
                "url": url,
                "title": _bounded_text(self._active_result.get("title", ""), 240),
            }
            snippet = _bounded_text(self._active_result.get("snippet", ""), 1000)
            if snippet:
                result["snippet"] = snippet
            self.results.append(result)
        self._active_result = None
        self._inside_heading = False
        self._capture_title = False
        self._capture_snippet = False


def _fetch_search_html(url: str, *, timeout_seconds: float) -> str:
    request = Request(
        url,
        headers={
            "User-Agent": _SEARCH_USER_AGENT,
            "Accept": "text/html",
        },
        method="GET",
    )
    try:
        with urlopen(request, timeout=timeout_seconds) as response:  # noqa: S310 - user-triggered public search.
            charset = response.headers.get_content_charset() or "utf-8"
            return response.read(512_000).decode(charset, errors="replace")
    except Exception:
        return ""


def _parse_duckduckgo_html(body: str, *, limit: int) -> list[dict[str, Any]]:
    parser = _DuckDuckGoHTMLParser(limit=_max_results(limit))
    try:
        parser.feed(body)
        parser.close()
    except Exception:
        return []
    return parser.results


def _parse_bing_html(body: str, *, limit: int) -> list[dict[str, Any]]:
    parser = _BingHTMLParser(limit=_max_results(limit))
    try:
        parser.feed(body)
        parser.close()
    except Exception:
        return []
    return parser.results


def _extract_skills(cv_text: str) -> list[str]:
    text = str(cv_text or "").casefold()
    return [skill for skill in _SKILL_KEYWORDS if skill.casefold() in text]


def _authorized_search_locations(constraints: dict[str, Any]) -> list[str]:
    raw_locations = [str(item).strip() for item in constraints.get("work_authorized_regions") or [] if str(item).strip()]
    excluded = {str(item).casefold() for item in constraints.get("excluded_regions") or []}
    locations: list[str] = []
    for preferred in _LOCATION_PRIORITY:
        if preferred in raw_locations and preferred.casefold() not in excluded:
            locations.append(preferred)
    for location in raw_locations:
        if location not in locations and location.casefold() not in excluded:
            locations.append(location)
    return locations or ["Remote"]


def _workflow_phrase(*, cv_text: str, prompt: str) -> str:
    combined = f"{cv_text}\n{prompt}".casefold()
    if "agentic workflows" in combined:
        return "agentic workflows"
    if "agent workflows" in combined:
        return "agent workflows"
    if "workflow" in combined:
        return "workflow automation"
    return ""


def _prompt_role_terms(prompt: str) -> str:
    text = str(prompt or "").casefold()
    if "backend" in text and ("platform" in text or "ai" in text):
        return "backend AI platform engineer"
    if "backend" in text:
        return "backend engineer"
    if "ai" in text:
        return "AI engineer"
    return ""


def _append_unique_query(queries: list[str], query: str) -> None:
    normalized = _bounded_text(query, 500)
    if normalized and normalized not in queries:
        queries.append(normalized)


def _salary_range(value: Any) -> list[int]:
    if isinstance(value, (list, tuple)) and len(value) >= 2:
        try:
            return [int(float(value[0])), int(float(value[1]))]
        except (TypeError, ValueError):
            return [0, 0]
    return [0, 0]


def _safe_location_from_source_query(source_query: str) -> str:
    text = f" {_bounded_text(source_query, 500).casefold()} "
    if not text.strip():
        return ""
    if re.search(r"\b(united states|u\.?s\.?a\.?|usa|u\.?s\.?|us)\b", text):
        return ""
    if re.search(r"\bspain\b", text):
        return "Spain Remote"
    if re.search(r"\bmexico\b", text):
        return "Mexico Remote"
    if re.search(r"\beuropean union\b|\beurope\b|\beu\b", text):
        return "European Union Remote" if re.search(r"\beuropean union\b|\beu\b", text) else "Europe Remote"
    if re.search(r"\bremote\b", text):
        return "Remote"
    return ""


def _canonical_url(value: Any) -> str:
    raw_url = html.unescape(str(value or "")).strip()
    if not raw_url:
        return ""
    parsed = urlparse(raw_url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return ""
    kept_query = [
        (key, value)
        for key, value in parse_qsl(parsed.query, keep_blank_values=False)
        if not _is_tracking_query_key(key)
    ]
    query = urlencode(kept_query, doseq=True)
    path = parsed.path or "/"
    if path != "/":
        path = path.rstrip("/")
    return urlunparse(
        (
            parsed.scheme.lower(),
            parsed.netloc.lower(),
            path,
            "",
            query,
            "",
        )
    )


def _is_tracking_query_key(key: str) -> bool:
    normalized = key.strip().casefold()
    return normalized in _TRACKING_QUERY_KEYS or normalized.startswith("utm_")


def _resolve_duckduckgo_href(raw_href: str) -> str:
    href = html.unescape(str(raw_href or "")).strip()
    if not href:
        return ""
    parsed = urlparse(href)
    if parsed.netloc.endswith("duckduckgo.com") and parsed.path.startswith("/l/"):
        for key, value in parse_qsl(parsed.query):
            if key == "uddg":
                return value
    if href.startswith("//"):
        return f"https:{href}"
    return href


def _title_from_url(url: str) -> str:
    path = urlparse(url).path.strip("/")
    if not path:
        return ""
    tail = path.split("/")[-1]
    return " ".join(part.capitalize() for part in re.split(r"[-_]+", tail) if part)


def _company_from_url(url: str) -> str:
    hostname = (urlparse(url).hostname or "").lower()
    if not hostname:
        return "Unknown employer"
    parts = [part for part in hostname.split(".") if part not in {"www", "jobs", "careers", "com", "net", "org"}]
    if not parts:
        return "Unknown employer"
    return " ".join(part.capitalize() for part in re.split(r"[-_]+", parts[0]) if part)


def _drop_action_fields(posting: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in posting.items() if key not in _ACTION_FIELD_NAMES}


def _bounded_text(value: Any, limit: int) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()[:limit]


def _max_results(value: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = DEFAULT_MAX_RESULTS
    return max(1, min(parsed, 25))
