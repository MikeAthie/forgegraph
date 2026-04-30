from __future__ import annotations

import argparse
import hmac
import hashlib
import http.cookiejar
import json
import time
import urllib.error
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
    except urllib.error.URLError as exc:
        return 0, str(exc.reason)


def _wait_for_ok(url: str, *, opener: urllib.request.OpenerDirector, retries: int = 30) -> None:
    last_status = None
    last_body = ""
    for _ in range(retries):
        last_status, last_body = _request(opener, url)
        if 200 <= int(last_status) < 300:
            return
        time.sleep(2)
    raise SystemExit(f"Smoke check failed for {url}: status={last_status}, body={last_body}")


def _json_body(body: str, *, context: str) -> dict[str, object]:
    try:
        payload = json.loads(body or "{}")
    except json.JSONDecodeError as exc:
        raise SystemExit(f"{context} returned invalid JSON: {exc}") from exc
    if not isinstance(payload, dict):
        raise SystemExit(f"{context} returned a non-object JSON payload.")
    return payload


def _wrapped_data(body: str, *, context: str) -> dict[str, object]:
    payload = _json_body(body, context=context)
    data = payload.get("data")
    if not isinstance(data, dict):
        raise SystemExit(f"{context} response is missing a data object.")
    return data


def _auth_headers(access_token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {access_token}"}


def _post_signed_callback(
    opener: urllib.request.OpenerDirector,
    *,
    callback_url: str,
    callback_secret: str,
    payload: dict[str, object],
) -> tuple[int, str]:
    raw_body = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    timestamp_ms = str(payload.get("timestamp") or int(time.time() * 1000))
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
            return response.status, response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read().decode("utf-8")
    except urllib.error.URLError as exc:
        return 0, str(exc.reason)


def _signed_callback_test(
    opener: urllib.request.OpenerDirector,
    *,
    backend_url: str,
    callback_secret: str,
    run_id: str,
    tenant_id: str,
) -> None:
    callback_url = backend_url.rstrip("/") + "/api/runs/engine-events"
    payload = {
        "event_id": f"smoke-{uuid.uuid4()}",
        "type": "run_started",
        "category": "state",
        "run_id": run_id,
        "tenant_id": tenant_id,
        "timestamp": int(time.time() * 1000),
    }
    status_code, body = _post_signed_callback(
        opener,
        callback_url=callback_url,
        callback_secret=callback_secret,
        payload=payload,
    )
    if status_code != 200:
        raise SystemExit(
            "Signed engine callback smoke check failed: "
            f"status={status_code}, body={body}"
        )

    status_code, body = _post_signed_callback(
        opener,
        callback_url=callback_url,
        callback_secret=callback_secret,
        payload=payload,
    )
    if status_code != 200:
        raise SystemExit(
            "Duplicate signed callback smoke check failed: "
            f"status={status_code}, body={body}"
        )
    duplicate_payload = _wrapped_data(body, context="Duplicate callback smoke")
    if duplicate_payload.get("duplicate") is not True:
        raise SystemExit(f"Duplicate signed callback smoke check failed: body={body}")


def _authenticated_api_smoke(
    opener: urllib.request.OpenerDirector, *, backend_url: str
) -> tuple[str, str]:
    email = f"smoke-{uuid.uuid4()}@example.com"
    password = "SmokePass!234"
    register_url = backend_url.rstrip("/") + "/api/auth/register"
    login_url = backend_url.rstrip("/") + "/api/auth/login"
    me_url = backend_url.rstrip("/") + "/api/auth/me"
    org_me_url = backend_url.rstrip("/") + "/api/orgs/me"

    status_code, body = _request(
        opener,
        register_url,
        method="POST",
        data={"email": email, "password": password},
    )
    if status_code != 201:
        raise SystemExit(f"Registration smoke check failed: status={status_code}, body={body}")
    register_payload = _json_body(body, context="Registration smoke")
    tenant_id = str(register_payload.get("default_organization_id") or "")

    status_code, body = _request(
        opener,
        login_url,
        method="POST",
        data={"email": email, "password": password},
    )
    if status_code != 200:
        raise SystemExit(f"Login smoke check failed: status={status_code}, body={body}")
    login_payload = _json_body(body, context="Login smoke")
    access_token = str(login_payload.get("access") or "")
    if not access_token:
        raise SystemExit("Login smoke check failed: missing access token.")

    status_code, body = _request(
        opener,
        me_url,
        headers=_auth_headers(access_token),
    )
    if status_code != 200:
        raise SystemExit(
            f"Authenticated API smoke check failed: status={status_code}, body={body}"
        )
    me_payload = _json_body(body, context="Authenticated API smoke")
    tenant_id = str(me_payload.get("default_organization_id") or tenant_id)

    status_code, body = _request(
        opener,
        org_me_url,
        headers=_auth_headers(access_token),
    )
    if status_code == 200:
        org_data = _wrapped_data(body, context="Organization API smoke")
        organization = org_data.get("organization")
        if isinstance(organization, dict):
            tenant_id = str(organization.get("id") or tenant_id)

    if not tenant_id:
        raise SystemExit("Authenticated API smoke check failed: missing tenant id.")

    return access_token, tenant_id


def _create_smoke_run(
    opener: urllib.request.OpenerDirector,
    *,
    backend_url: str,
    access_token: str,
) -> str:
    headers = _auth_headers(access_token)
    graph_url = backend_url.rstrip("/") + "/api/graphs/"

    status_code, body = _request(
        opener,
        graph_url,
        method="POST",
        data={
            "name": f"Release smoke {uuid.uuid4()}",
            "description": "Release contract smoke graph",
        },
        headers=headers,
    )
    if status_code != 201:
        raise SystemExit(f"Graph smoke check failed: status={status_code}, body={body}")
    graph_data = _wrapped_data(body, context="Graph smoke")
    graph_id = str(graph_data.get("id") or "")
    if not graph_id:
        raise SystemExit(f"Graph smoke check failed: missing graph id, body={body}")

    graph_json = {
        "nodes": [{"id": "output-1", "type": "output", "name": "Output", "config": {}}],
        "edges": [{"id": "edge-1", "from": "START", "to": "output-1"}],
    }
    status_code, body = _request(
        opener,
        backend_url.rstrip("/") + f"/api/graphs/{graph_id}/versions",
        method="POST",
        data={"graph_json": graph_json},
        headers=headers,
    )
    if status_code != 201:
        raise SystemExit(f"Graph version smoke check failed: status={status_code}, body={body}")
    version_data = _wrapped_data(body, context="Graph version smoke")
    graph_version_id = str(version_data.get("id") or "")
    if not graph_version_id:
        raise SystemExit(f"Graph version smoke check failed: missing version id, body={body}")

    status_code, body = _request(
        opener,
        backend_url.rstrip("/") + "/api/runs/start",
        method="POST",
        data={"graph_version_id": graph_version_id, "input_json": {"release_smoke": True}},
        headers=headers,
    )
    if status_code != 201:
        raise SystemExit(f"Run start smoke check failed: status={status_code}, body={body}")
    run_data = _wrapped_data(body, context="Run start smoke")
    run_id = str(run_data.get("id") or "")
    if not run_id:
        raise SystemExit(f"Run start smoke check failed: missing run id, body={body}")
    return run_id


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

    opener = urllib.request.build_opener(
        urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar())
    )

    _wait_for_ok(args.backend_url.rstrip("/") + "/health", opener=opener)
    _wait_for_ok(args.backend_url.rstrip("/") + "/ready", opener=opener)
    access_token, tenant_id = _authenticated_api_smoke(opener, backend_url=args.backend_url)

    if not args.skip_engine and args.engine_url:
        _wait_for_ok(args.engine_url.rstrip("/") + "/ready", opener=opener)
        status_code, body = _request(opener, args.engine_url.rstrip("/") + "/metrics")
        if status_code != 200 or "# HELP" not in body:
            raise SystemExit("Engine metrics smoke check failed.")

    if not args.skip_frontend and args.frontend_url:
        _wait_for_ok(args.frontend_url.rstrip("/") + "/", opener=opener)
        _wait_for_ok(args.frontend_url.rstrip("/") + "/api/health/ready", opener=opener)

    if not args.skip_callback:
        if not args.callback_secret:
            raise SystemExit("--callback-secret is required unless --skip-callback is set.")
        run_id = _create_smoke_run(
            opener,
            backend_url=args.backend_url,
            access_token=access_token,
        )
        _signed_callback_test(
            opener,
            backend_url=args.backend_url,
            callback_secret=args.callback_secret,
            run_id=run_id,
            tenant_id=tenant_id,
        )


if __name__ == "__main__":
    main()
