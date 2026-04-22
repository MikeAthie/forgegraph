from __future__ import annotations

import html
import ipaddress
import re
import socket
from html.parser import HTMLParser
from typing import Any
from urllib.parse import parse_qs, unquote, urlparse

import requests

_USER_AGENT = "ForgeGraphRuntimeTools/1.0"
_DEFAULT_TIMEOUT_SECONDS = 10.0
_DEFAULT_MAX_FETCH_CHARS = 12000
_DEFAULT_MAX_SEARCH_RESULTS = 5
_MAX_FETCH_BYTES = 512_000

_TEXT_CONTENT_TYPES = (
    "text/",
    "application/json",
    "application/xml",
    "application/xhtml+xml",
)
_IPAddress = ipaddress.IPv4Address | ipaddress.IPv6Address


class RuntimeToolError(ValueError):
    pass


class _HTMLTextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._skip_depth = 0
        self._parts: list[str] = []
        self.title = ""
        self._in_title = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        lowered = tag.lower()
        if lowered in {"script", "style", "noscript"}:
            self._skip_depth += 1
        elif lowered == "title":
            self._in_title = True

    def handle_endtag(self, tag: str) -> None:
        lowered = tag.lower()
        if lowered in {"script", "style", "noscript"} and self._skip_depth > 0:
            self._skip_depth -= 1
        elif lowered == "title":
            self._in_title = False

    def handle_data(self, data: str) -> None:
        if self._skip_depth > 0:
            return
        normalized = _normalize_text(data)
        if not normalized:
            return
        if self._in_title and not self.title:
            self.title = normalized
        self._parts.append(normalized)

    @property
    def text(self) -> str:
        return _normalize_text(" ".join(self._parts))


def fetch_public_web_content(
    *,
    url: str,
    timeout_seconds: float = _DEFAULT_TIMEOUT_SECONDS,
    max_chars: int = _DEFAULT_MAX_FETCH_CHARS,
) -> dict[str, Any]:
    normalized_url = _validate_public_url(url)
    timeout = _clamp_timeout(timeout_seconds)
    max_text = _clamp_max_chars(max_chars)

    response = requests.get(
        normalized_url,
        timeout=timeout,
        headers={"User-Agent": _USER_AGENT, "Accept": "text/html, text/plain, application/json"},
    )
    response.raise_for_status()

    final_url = _validate_public_url(response.url)
    content_type = response.headers.get("Content-Type", "").split(";")[0].strip().lower()
    if content_type and not any(content_type.startswith(prefix) for prefix in _TEXT_CONTENT_TYPES):
        raise RuntimeToolError(f"Unsupported content type: {content_type}")

    body_text = response.text
    if len(body_text.encode("utf-8")) > _MAX_FETCH_BYTES:
        raise RuntimeToolError("Fetched content exceeds size limit.")

    title = ""
    extracted_text = body_text
    if "html" in content_type or "<html" in body_text.lower():
        parser = _HTMLTextExtractor()
        parser.feed(body_text)
        title = parser.title
        extracted_text = parser.text
    else:
        extracted_text = _normalize_text(body_text)

    truncated = len(extracted_text) > max_text
    if truncated:
        extracted_text = extracted_text[:max_text].rstrip()

    return {
        "url": final_url,
        "title": title,
        "content": extracted_text,
        "content_type": content_type or "text/plain",
        "status_code": response.status_code,
        "truncated": truncated,
    }


def search_public_web(
    *,
    query: str,
    allowed_domains: list[str] | None = None,
    blocked_domains: list[str] | None = None,
    max_results: int = _DEFAULT_MAX_SEARCH_RESULTS,
    timeout_seconds: float = _DEFAULT_TIMEOUT_SECONDS,
) -> dict[str, Any]:
    normalized_query = str(query or "").strip()
    if len(normalized_query) < 2:
        raise RuntimeToolError("query must be at least 2 characters")

    if allowed_domains and blocked_domains:
        raise RuntimeToolError("allowed_domains and blocked_domains cannot both be provided")

    timeout = _clamp_timeout(timeout_seconds)
    limit = max(1, min(int(max_results), 10))
    normalized_allowed = [_normalize_domain(domain) for domain in allowed_domains or [] if domain]
    normalized_blocked = [_normalize_domain(domain) for domain in blocked_domains or [] if domain]

    response = requests.get(
        "https://html.duckduckgo.com/html/",
        params={"q": normalized_query},
        timeout=timeout,
        headers={"User-Agent": _USER_AGENT, "Accept": "text/html"},
    )
    response.raise_for_status()

    results: list[dict[str, str]] = []
    for match in re.finditer(
        r'<a[^>]*class="result__a"[^>]*href="(?P<href>[^"]+)"[^>]*>(?P<title>.*?)</a>',
        response.text,
        re.IGNORECASE | re.DOTALL,
    ):
        title = _strip_html(match.group("title"))
        href = _resolve_search_result_url(match.group("href"))
        if not href:
            continue
        parsed = urlparse(href)
        hostname = (parsed.hostname or "").lower()
        if not hostname:
            continue
        if normalized_allowed and not any(
            _domain_matches(hostname, domain) for domain in normalized_allowed
        ):
            continue
        if normalized_blocked and any(
            _domain_matches(hostname, domain) for domain in normalized_blocked
        ):
            continue
        results.append({"title": title or href, "url": href})
        if len(results) >= limit:
            break

    return {"query": normalized_query, "results": results, "count": len(results)}


def _validate_public_url(raw_url: str) -> str:
    parsed = urlparse(str(raw_url or "").strip())
    if parsed.scheme not in {"http", "https"}:
        raise RuntimeToolError("Only http and https URLs are supported")
    if not parsed.hostname:
        raise RuntimeToolError("URL must include a hostname")

    hostname = parsed.hostname.lower()
    if hostname in {"localhost", "host.docker.internal"}:
        raise RuntimeToolError("Localhost and host-internal URLs are not allowed")

    _ensure_public_host(hostname)
    return parsed.geturl()


def _ensure_public_host(hostname: str) -> None:
    try:
        ip = ipaddress.ip_address(hostname)
        if _is_non_public_ip(ip):
            raise RuntimeToolError("Private or local network targets are not allowed")
        return
    except ValueError:
        pass

    try:
        infos = socket.getaddrinfo(hostname, None, proto=socket.IPPROTO_TCP)
    except socket.gaierror as exc:
        raise RuntimeToolError(f"Could not resolve host: {hostname}") from exc

    for info in infos:
        ip_text = info[4][0]
        ip = ipaddress.ip_address(ip_text)
        if _is_non_public_ip(ip):
            raise RuntimeToolError("Private or local network targets are not allowed")


def _is_non_public_ip(ip: _IPAddress) -> bool:
    return bool(
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_multicast
        or ip.is_reserved
        or ip.is_unspecified
    )


def _clamp_timeout(value: float) -> float:
    return max(1.0, min(float(value), 20.0))


def _clamp_max_chars(value: int) -> int:
    return max(500, min(int(value), 40000))


def _normalize_text(value: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(value or "")).strip()


def _strip_html(value: str) -> str:
    return _normalize_text(re.sub(r"<[^>]+>", " ", value or ""))


def _resolve_search_result_url(raw_href: str) -> str:
    href = html.unescape(raw_href or "").strip()
    if not href:
        return ""

    parsed = urlparse(href)
    if parsed.netloc.endswith("duckduckgo.com") and parsed.path.startswith("/l/"):
        target = parse_qs(parsed.query).get("uddg", [""])[0]
        if target:
            return unquote(target)
    if href.startswith("//"):
        return f"https:{href}"
    return href


def _normalize_domain(domain: str) -> str:
    normalized = str(domain or "").strip().lower()
    if not normalized:
        raise RuntimeToolError("domain filters must be non-empty strings")
    return normalized.lstrip(".")


def _domain_matches(hostname: str, domain: str) -> bool:
    return hostname == domain or hostname.endswith(f".{domain}")
