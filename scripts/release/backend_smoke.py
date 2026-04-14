from __future__ import annotations

import argparse
import hmac
import hashlib
import http.cookiejar
import json
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid


def _request(
    opener: urllib.request.OpenerDirector,
    url: str,
    *,
    method: str = "GET",
    data: dict[str, object] | None = None,
    headers: dict[str, str] | None = None,
) -> tuple[int, str]:
    body = None
    merged_headers = {"Content-Type": "application/json"}
    if headers:
        merged_headers.update(headers)
    if data is not None:
        body = json.dumps(data).encode("utf-8")
    request = urllib.request.Request(url, data=body, headers=merged_headers, method=method)
    try:
        with opener.open(request, timeout=15) as response:
            return response.status, response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read().decode("utf-8")


def _wait_for_ok(url: str, *, opener: urllib.request.OpenerDirector, retries: int = 30) -> None:
    last_status = None
    last_body = ""
    for _ in range(retries):
        last_status, last_body = _request(opener, url)
        if 200 <= int(last_status) < 300:
            return
        time.sleep(2)
    raise SystemExit(f"Smoke check failed for {url}: status={last_status}, body={last_body}")


def _signed_callback_test(
    opener: urllib.request.OpenerDirector,
    *,
    backend_url: str,
    callback_secret: str,
) -> None:
    callback_url = backend_url.rstrip("/") + "/api/runs/engine-events"
    payload = {
        "event_id": f"smoke-{uuid.uuid4()}",
        "type": "run_started",
        "run_id": str(uuid.uuid4()),
        "tenant_id": str(uuid.uuid4()),
    }
    raw_body = json.dumps(payload).encode("utf-8")
    timestamp_ms = str(int(time.time() * 1000))
    signature = hmac.new(
        callback_secret.encode("utf-8"),
        f"{timestamp_ms}.".encode("utf-8") + raw_body,
        hashlib.sha256,
    ).hexdigest()
    request = urllib.request.Request(
        callback_url,
        data=raw_body,
        method="POST",
        headers={
            "Content-Type": "application/json",
            "X-Forgegraph-Timestamp": timestamp_ms,
            "X-Forgegraph-Signature": signature,
        },
    )
    try:
        with opener.open(request, timeout=15) as response:
            status_code = response.status
    except urllib.error.HTTPError as exc:
        status_code = exc.code
    if status_code in {401, 403}:
        raise SystemExit("Signed engine callback smoke check failed with unauthorized response.")


def _authenticated_api_smoke(opener: urllib.request.OpenerDirector, *, backend_url: str) -> None:
    email = f"smoke-{uuid.uuid4()}@example.com"
    password = "SmokePass!234"
    register_url = backend_url.rstrip("/") + "/api/auth/register"
    login_url = backend_url.rstrip("/") + "/api/auth/login"
    me_url = backend_url.rstrip("/") + "/api/auth/me"

    status_code, _ = _request(
        opener,
        register_url,
        method="POST",
        data={"email": email, "password": password},
    )
    if status_code != 201:
        raise SystemExit(f"Registration smoke check failed: status={status_code}")

    status_code, body = _request(
        opener,
        login_url,
        method="POST",
        data={"email": email, "password": password},
    )
    if status_code != 200:
        raise SystemExit(f"Login smoke check failed: status={status_code}")
    login_payload = json.loads(body)
    access_token = str(login_payload.get("access") or "")
    if not access_token:
        raise SystemExit("Login smoke check failed: missing access token.")

    status_code, _ = _request(
        opener,
        me_url,
        headers={"Authorization": f"Bearer {access_token}"},
    )
    if status_code != 200:
        raise SystemExit(f"Authenticated API smoke check failed: status={status_code}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Backend/frontend/engine release smoke test.")
    parser.add_argument("--backend-url", required=True)
    parser.add_argument("--frontend-url")
    parser.add_argument("--engine-url")
    parser.add_argument("--callback-secret", default="")
    parser.add_argument("--skip-frontend", action="store_true")
    parser.add_argument("--skip-engine", action="store_true")
    parser.add_argument("--skip-callback", action="store_true")
    args = parser.parse_args()

    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))

    _wait_for_ok(args.backend_url.rstrip("/") + "/health", opener=opener)
    _wait_for_ok(args.backend_url.rstrip("/") + "/ready", opener=opener)
    _authenticated_api_smoke(opener, backend_url=args.backend_url)

    if not args.skip_engine and args.engine_url:
        _wait_for_ok(args.engine_url.rstrip("/") + "/ready", opener=opener)
        status_code, body = _request(opener, args.engine_url.rstrip("/") + "/metrics")
        if status_code != 200 or "# HELP" not in body:
            raise SystemExit("Engine metrics smoke check failed.")

    if not args.skip_frontend and args.frontend_url:
        _wait_for_ok(args.frontend_url.rstrip("/") + "/", opener=opener)

    if not args.skip_callback:
        if not args.callback_secret:
            raise SystemExit("--callback-secret is required unless --skip-callback is set.")
        _signed_callback_test(opener, backend_url=args.backend_url, callback_secret=args.callback_secret)


if __name__ == "__main__":
    main()

