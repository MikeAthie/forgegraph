#!/usr/bin/env python3
"""Exchange Meta short-lived token for long-lived token without printing secrets.

Reads ../.env, requires real META_GRAPH_APP_ID, META_GRAPH_APP_SECRET, and
META_GRAPH_ACCESS_TOKEN. On success, updates META_GRAPH_ACCESS_TOKEN in ../.env
with the long-lived user token and writes a redacted receipt.
"""
from __future__ import annotations

import json
import re
import sys
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
ENV_PATH = ROOT.parent / ".env"
RECEIPT_PATH = ROOT / ".hermes" / "legacy_optical_noir_autopublish" / "meta_long_lived_token_receipt.json"


def parse_env(path: Path) -> dict[str, str]:
    env: dict[str, str] = {}
    for raw in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        if "=" in raw and not raw.lstrip().startswith("#"):
            k, v = raw.split("=", 1)
            env[k.strip()] = v.strip().strip('"').strip("'")
    return env


def graph_get(url: str, params: dict[str, str], *, timeout: int = 45) -> tuple[int, dict[str, Any]]:
    full = url + "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(full, headers={"Accept": "application/json", "User-Agent": "forgegraph-token-exchange/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            status = int(getattr(resp, "status", 200))
            body = resp.read(1024 * 1024)
    except urllib.error.HTTPError as exc:
        status = int(exc.code)
        body = exc.read(1024 * 1024)
    try:
        data = json.loads(body.decode("utf-8"))
    except Exception:
        data = {"_non_json": body[:500].decode("utf-8", errors="replace")}
    return status, data if isinstance(data, dict) else {"data": data}


def provider_error(data: dict[str, Any]) -> dict[str, str]:
    err = data.get("error") if isinstance(data, dict) else None
    if isinstance(err, dict):
        return {
            "type": str(err.get("type") or "provider_error"),
            "code": str(err.get("code") or ""),
            "subcode": str(err.get("error_subcode") or ""),
            "message": str(err.get("message") or "")[:500],
        }
    return {"type": "provider_error", "code": "", "subcode": "", "message": "Provider request failed."}


def replace_env_value(path: Path, key: str, value: str) -> None:
    text = path.read_text(encoding="utf-8", errors="ignore")
    pattern = re.compile(rf"^({re.escape(key)}=).*$", re.MULTILINE)
    if pattern.search(text):
        text = pattern.sub(lambda m: m.group(1) + value, text)
    else:
        text = text.rstrip() + f"\n{key}={value}\n"
    path.write_text(text, encoding="utf-8")


def main() -> int:
    env = parse_env(ENV_PATH)
    app_id = env.get("META_GRAPH_APP_ID", "").strip()
    app_secret = env.get("META_GRAPH_APP_SECRET", "").strip()
    short_token = (env.get("META_GRAPH_ACCESS_TOKEN") or env.get("INSTAGRAM_GRAPH_API") or "").strip()
    version = (env.get("META_GRAPH_API_VERSION") or "v24.0").strip().strip("/")
    ig_id = (env.get("META_GRAPH_IG_USER_ID_ALLOWLIST") or "").split(",")[0].strip()
    page_id_expected = (env.get("META_GRAPH_PAGE_ID_ALLOWLIST") or "").split(",")[0].strip()

    missing = []
    if not app_id or app_id.startswith("CHANGE_ME"):
        missing.append("META_GRAPH_APP_ID")
    if not app_secret or app_secret.startswith("CHANGE_ME"):
        missing.append("META_GRAPH_APP_SECRET")
    if not short_token or short_token.startswith("CHANGE_ME"):
        missing.append("META_GRAPH_ACCESS_TOKEN")
    if missing:
        print(json.dumps({"ok": False, "blocked": "missing_required_env", "missing": missing}, indent=2))
        return 2

    base = f"https://graph.facebook.com/{version}"
    status, exchanged = graph_get(
        f"{base}/oauth/access_token",
        {
            "grant_type": "fb_exchange_token",
            "client_id": app_id,
            "client_secret": app_secret,
            "fb_exchange_token": short_token,
        },
    )
    if status >= 300 or "error" in exchanged or not exchanged.get("access_token"):
        print(json.dumps({"ok": False, "stage": "exchange", "status": status, "error": provider_error(exchanged)}, indent=2))
        return 1

    long_token = str(exchanged["access_token"])
    expires_in = int(exchanged.get("expires_in") or 0)

    status, pages = graph_get(
        f"{base}/me/accounts",
        {"fields": "id,name,access_token,instagram_business_account,tasks", "access_token": long_token},
    )
    if status >= 300 or "error" in pages:
        print(json.dumps({"ok": False, "stage": "page_token", "status": status, "error": provider_error(pages)}, indent=2))
        return 1

    matched_page: dict[str, Any] = {}
    for page in pages.get("data", []):
        if not isinstance(page, dict):
            continue
        page_id = str(page.get("id") or "")
        linked_ig = str((page.get("instagram_business_account") or {}).get("id") or "")
        if (ig_id and linked_ig == ig_id) or (page_id_expected and page_id == page_id_expected):
            matched_page = page
            break

    # Keep META_GRAPH_ACCESS_TOKEN as the long-lived user token because the existing
    # autopublisher uses it to refresh the page token at runtime via /me/accounts.
    replace_env_value(ENV_PATH, "META_GRAPH_ACCESS_TOKEN", long_token)
    replace_env_value(ENV_PATH, "SOCIAL_CONNECTOR_PROVIDER", "meta_graph")
    replace_env_value(ENV_PATH, "SOCIAL_CONNECTOR_ALLOW_PROVIDER_PUBLISH", "true")
    if matched_page.get("access_token"):
        replace_env_value(ENV_PATH, "META_GRAPH_PAGE_ACCESS_TOKEN", str(matched_page.get("access_token")))

    receipt = {
        "ok": True,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "graph_version": version,
        "long_lived_user_token": {"stored_in": "META_GRAPH_ACCESS_TOKEN", "length": len(long_token), "expires_in_seconds": expires_in},
        "matched_page": {
            "id": str(matched_page.get("id") or ""),
            "name": str(matched_page.get("name") or ""),
            "instagram_business_account_id": str((matched_page.get("instagram_business_account") or {}).get("id") or ""),
            "page_token_stored": bool(matched_page.get("access_token")),
            "tasks": matched_page.get("tasks") or [],
        },
        "env_updated": ["META_GRAPH_ACCESS_TOKEN", "SOCIAL_CONNECTOR_PROVIDER", "SOCIAL_CONNECTOR_ALLOW_PROVIDER_PUBLISH"] + (["META_GRAPH_PAGE_ACCESS_TOKEN"] if matched_page.get("access_token") else []),
        "secrets_redacted": True,
    }
    RECEIPT_PATH.parent.mkdir(parents=True, exist_ok=True)
    RECEIPT_PATH.write_text(json.dumps(receipt, indent=2), encoding="utf-8")
    print(json.dumps(receipt, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
