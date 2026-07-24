"""CareerOps posting liveness classification adapted from santifer/career-ops."""

from __future__ import annotations

import re
from dataclasses import dataclass

HARD_EXPIRED_PATTERNS = (
    r"job (is )?no longer available",
    r"job.*no longer open",
    r"position has been filled",
    r"this job has expired",
    r"job posting has expired",
    r"no longer accepting applications",
    r"this (position|role|job) (is )?no longer",
    r"this job (listing )?is closed",
    r"job (listing )?not found",
    r"the page you are looking for doesn.t exist",
    r"applications?\s+(?:(?:have|are|is)\s+)?closed",
    r"closed on \d{1,2}\s+(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)",
    r"closed on (?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)\w*\s+\d{1,2}",
    r"diese stelle (ist )?(nicht mehr|bereits) besetzt",
    r"offre (expirée|n'est plus disponible)",
)

LISTING_PAGE_PATTERNS = (
    r"\d+\s+jobs?\s+found",
    r"search for jobs page is loaded",
)

BOT_CHALLENGE_PATTERNS = (
    r"just a moment",
    r"performing security verification",
    r"checking your browser before",
    r"verify you are (a |not a )?human",
    r"enable javascript and cookies to continue",
    r"attention required.*cloudflare",
    r"\bray id\b",
    r"\bcf-ray\b",
    r"please complete the security check",
)

EXPIRED_URL_PATTERNS = (r"[?&]error=true",)
APPLY_PATTERNS = (
    r"\bapply\b",
    r"\bsolicitar\b",
    r"\bbewerben\b",
    r"\bpostuler\b",
    r"submit application",
    r"easy apply",
    r"start application",
    r"ich bewerbe mich",
    r"\baplikuj\b",
    r"panelu aplikowania",
    r"wyślij (cv|aplikacj)",
)
MIN_CONTENT_CHARS = 300


@dataclass(frozen=True, slots=True)
class CareerOpsLivenessResult:
    result: str
    code: str
    reason: str

    def as_dict(self) -> dict[str, str]:
        return {"result": self.result, "code": self.code, "reason": self.reason}


def classify_career_ops_liveness(  # noqa: C901
    *,
    status: int = 0,
    final_url: str = "",
    body_text: str = "",
    apply_controls: list[str] | tuple[str, ...] | None = None,
) -> CareerOpsLivenessResult:
    """Classify posting liveness using the reference Career-Ops heuristic order."""

    controls = list(apply_controls or [])
    if status in {404, 410}:
        return CareerOpsLivenessResult("expired", "http_gone", f"HTTP {status}")

    bot_challenge = _first_match(BOT_CHALLENGE_PATTERNS, body_text)
    if bot_challenge:
        return CareerOpsLivenessResult(
            "uncertain", "bot_challenge", f"anti-bot challenge: {bot_challenge}"
        )
    if status in {403, 503}:
        return CareerOpsLivenessResult(
            "uncertain", "access_blocked", f"HTTP {status} (access blocked, likely anti-bot)"
        )

    expired_url = _first_match(EXPIRED_URL_PATTERNS, final_url)
    if expired_url:
        return CareerOpsLivenessResult("expired", "expired_url", f"redirect to {final_url}")

    expired_body = _first_match(HARD_EXPIRED_PATTERNS, body_text)
    if expired_body:
        return CareerOpsLivenessResult(
            "expired", "expired_body", f"pattern matched: {expired_body}"
        )

    if _has_apply_control(controls):
        return CareerOpsLivenessResult(
            "active", "apply_control_visible", "visible apply control detected"
        )

    listing_page = _first_match(LISTING_PAGE_PATTERNS, body_text)
    if listing_page:
        return CareerOpsLivenessResult(
            "expired", "listing_page", f"pattern matched: {listing_page}"
        )

    if body_text_clean := body_text.strip():
        if len(body_text_clean) < MIN_CONTENT_CHARS and status:
            return CareerOpsLivenessResult(
                "expired", "insufficient_content", "insufficient content - likely nav/footer only"
            )
        if len(body_text_clean) < MIN_CONTENT_CHARS:
            return CareerOpsLivenessResult(
                "uncertain", "unverified_short_text", "short JD text without fetched HTTP status"
            )

    return CareerOpsLivenessResult(
        "uncertain", "no_apply_control", "content present but no visible apply control found"
    )


def _first_match(patterns: tuple[str, ...], text: str = "") -> str | None:
    for pattern in patterns:
        if re.search(pattern, text or "", re.IGNORECASE):
            return pattern
    return None


def _has_apply_control(controls: list[str]) -> bool:
    return any(
        re.search(pattern, control, re.IGNORECASE)
        for control in controls
        for pattern in APPLY_PATTERNS
    )
