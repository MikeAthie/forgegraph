from __future__ import annotations

import json
import time
from datetime import timedelta
from pathlib import Path
from typing import Any, cast
from uuid import uuid4

import pytest
import yaml
from django.conf import settings
from django.core.cache import cache
from django.test import override_settings
from django.urls import URLPattern, URLResolver, get_resolver
from rest_framework import status
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import AccessToken

from application.services.auth_state import revoke_access_token
from infrastructure.orm.models import AuditLog, OrganizationMembership, User
from infrastructure.security import s2s

pytestmark = pytest.mark.django_db

MATRIX_PATH = Path(__file__).resolve().parents[4] / "docs/security/route-security-matrix.yaml"
METHOD_NAMES = ("get", "post", "put", "patch", "delete")
EXCLUDED_ROUTE_PARTS = ("/health/", "/ready/", "/schema", "/docs", "/redoc")


def _load_matrix() -> dict[str, Any]:
    matrix = yaml.safe_load(MATRIX_PATH.read_text(encoding="utf-8"))
    if not isinstance(matrix, dict):
        raise AssertionError("Security matrix must be a mapping.")
    return cast(dict[str, Any], matrix)


def _iter_api_routes() -> set[tuple[str, str]]:
    routes: set[tuple[str, str]] = set()

    def walk(patterns: list[URLPattern | URLResolver], prefix: str = "") -> None:
        for pattern in patterns:
            route_part = str(pattern.pattern)
            if isinstance(pattern, URLResolver):
                walk(pattern.url_patterns, prefix + route_part)
                continue
            path = ("/" + prefix + route_part).replace("//", "/")
            if path.endswith("/"):
                path = path[:-1]
            if not path.startswith("/api/"):
                continue
            if any(part in path for part in EXCLUDED_ROUTE_PARTS):
                continue
            callback = pattern.callback
            view_class = getattr(callback, "view_class", None)
            if view_class is not None:
                methods = [method.upper() for method in METHOD_NAMES if hasattr(view_class, method)]
            else:
                actions = getattr(callback, "actions", None)
                methods = (
                    sorted({method.upper() for method in actions if method in METHOD_NAMES})
                    if actions
                    else ["GET"]
                )
            routes.update((path, method) for method in methods)

    walk(get_resolver().url_patterns)
    return routes


def _matrix_route_methods() -> set[tuple[str, str]]:
    matrix = _load_matrix()
    route_methods: set[tuple[str, str]] = set()
    for route in matrix["routes"]:
        for path in route["paths"]:
            for method in route["methods"]:
                if method == "WEBSOCKET":
                    continue
                route_methods.add((path.rstrip("/"), method))
    return route_methods


def _routes_by_surface(surface: str) -> list[tuple[str, str]]:
    matrix = _load_matrix()
    result: list[tuple[str, str]] = []
    for route in matrix["routes"]:
        if route["auth_surface"] != surface:
            continue
        method = next(
            (candidate for candidate in route["methods"] if candidate != "WEBSOCKET"), None
        )
        if method is None:
            continue
        result.append((route["paths"][0].rstrip("/"), method))
    return result


def _concrete_path(path: str) -> str:
    replacements = {
        "<uuid:agent_id>": str(uuid4()),
        "<uuid:approval_id>": str(uuid4()),
        "<uuid:asset_id>": str(uuid4()),
        "<uuid:context_pack_id>": str(uuid4()),
        "<uuid:credential_id>": str(uuid4()),
        "<uuid:dead_letter_id>": str(uuid4()),
        "<uuid:decision_id>": str(uuid4()),
        "<uuid:draft_id>": str(uuid4()),
        "<uuid:graph_id>": str(uuid4()),
        "<uuid:graph_version_id>": str(uuid4()),
        "<uuid:intent_id>": str(uuid4()),
        "<uuid:job_id>": str(uuid4()),
        "<uuid:observation_id>": str(uuid4()),
        "<uuid:operation_id>": str(uuid4()),
        "<uuid:opportunity_id>": str(uuid4()),
        "<uuid:order_id>": str(uuid4()),
        "<uuid:organization_id>": str(uuid4()),
        "<uuid:policy_rule_id>": str(uuid4()),
        "<uuid:prompt_id>": str(uuid4()),
        "<uuid:release_id>": str(uuid4()),
        "<uuid:reservation_id>": str(uuid4()),
        "<uuid:run_id>": str(uuid4()),
        "<uuid:signal_id>": str(uuid4()),
        "<uuid:task_id>": str(uuid4()),
        "<uuid:template_id>": str(uuid4()),
        "<uuid:user_id>": str(uuid4()),
        "<uuid:version_id>": str(uuid4()),
        "<str:cache_key>": "cache-key",
        "<str:dead_letter_key>": f"event:{uuid4()}",
        "<str:node_id>": "node-1",
        "<str:public_status_token>": "status-token",
        "<str:provider>": "openai",
        "<slug:company_slug>": "legacy-glasswear",
        "<slug:package_slug>": "demo-package",
    }
    for marker, value in replacements.items():
        path = path.replace(marker, value)
    return path


def _generic_request(
    client: APIClient,
    method: str,
    path: str,
    *,
    body: str = "{}",
    **headers: str,
):
    concrete_path = _concrete_path(path)
    generic = cast(Any, client.generic)
    response = generic(
        method,
        concrete_path,
        data=body if method in {"POST", "PUT", "PATCH"} else "",
        content_type="application/json",
        **headers,
    )
    if response.status_code in {301, 308} and not concrete_path.endswith("/"):
        response = generic(
            method,
            concrete_path + "/",
            data=body if method in {"POST", "PUT", "PATCH"} else "",
            content_type="application/json",
            **headers,
        )
    return response


def _signed_headers(
    *,
    secret: str,
    body: bytes = b"",
    timestamp_ms: int | None = None,
) -> dict[str, str]:
    timestamp = str(timestamp_ms if timestamp_ms is not None else int(time.time() * 1000))
    return {
        "HTTP_X_FORGEGRAPH_TIMESTAMP": timestamp,
        "HTTP_X_FORGEGRAPH_SIGNATURE": s2s.build_signature(secret, timestamp, body),
    }


def test_route_security_matrix_covers_every_production_api_route_and_run_websocket():
    actual = _iter_api_routes()
    expected = _matrix_route_methods()
    missing = sorted(actual - expected)
    extra = sorted(expected - actual)
    assert not missing, f"Routes missing from docs/security/route-security-matrix.yaml: {missing}"
    assert not extra, f"Matrix contains stale route entries: {extra}"

    matrix = _load_matrix()
    run_websocket_entries = [
        route
        for route in matrix["routes"]
        if "/ws/runs/<uuid:run_id>/" in route["paths"]
        and "WEBSOCKET" in route["methods"]
        and route["auth_surface"] == "websocket_ticket"
    ]
    assert run_websocket_entries, (
        "Matrix must explicitly cover /ws/runs/<run_id>/ websocket tickets."
    )

    organization_websocket_entries = [
        route
        for route in matrix["routes"]
        if "/ws/organizations/<uuid:organization_id>/state/" in route["paths"]
        and "WEBSOCKET" in route["methods"]
        and route["auth_surface"] == "websocket_ticket"
    ]
    assert organization_websocket_entries, (
        "Matrix must explicitly cover /ws/organizations/<organization_id>/state websocket tickets."
    )


def test_jwt_matrix_routes_reject_unauthenticated_requests(api_client: APIClient):
    failures: list[tuple[str, str, int]] = []
    for path, method in _routes_by_surface("jwt"):
        response = _generic_request(api_client, method, path)
        if response.status_code != status.HTTP_401_UNAUTHORIZED:
            failures.append((method, path, response.status_code))
    assert not failures


@override_settings(ENGINE_CALLBACK_SECRET="test-secret")
def test_engine_signed_matrix_routes_reject_missing_and_invalid_signatures(api_client: APIClient):
    for path, method in _routes_by_surface("engine_signed"):
        missing = _generic_request(api_client, method, path)
        assert missing.status_code == status.HTTP_401_UNAUTHORIZED

        invalid = _generic_request(
            api_client,
            method,
            path,
            HTTP_X_FORGEGRAPH_TIMESTAMP=str(int(time.time() * 1000)),
            HTTP_X_FORGEGRAPH_SIGNATURE="not-a-valid-signature",
        )
        assert invalid.status_code == status.HTTP_401_UNAUTHORIZED


@override_settings(ENGINE_CALLBACK_SECRET="test-secret", ENGINE_CALLBACK_MAX_SKEW_SECONDS=60)
def test_engine_signed_routes_reject_stale_timestamps(api_client: APIClient):
    stale_timestamp = int((time.time() - 120) * 1000)
    response = cast(Any, api_client).get(
        f"/api/engine/runtime-intents/{uuid4()}",
        **_signed_headers(secret="test-secret", timestamp_ms=stale_timestamp),
    )
    assert response.status_code == status.HTTP_401_UNAUTHORIZED
    assert response.data["reason"] == "stale_timestamp"


@override_settings(ENGINE_CALLBACK_SECRET="test-secret")
def test_engine_signed_routes_reject_exact_replay_but_allow_fresh_retry(api_client: APIClient):
    cache.clear()
    path = f"/api/engine/runtime-intents/{uuid4()}"
    timestamp_ms = int(time.time() * 1000)
    headers = _signed_headers(secret="test-secret", timestamp_ms=timestamp_ms)

    first = cast(Any, api_client).get(path, **headers)
    assert first.status_code != status.HTTP_401_UNAUTHORIZED

    replay = cast(Any, api_client).get(path, **headers)
    assert replay.status_code == status.HTTP_401_UNAUTHORIZED
    assert replay.data["reason"] == "replayed_signature"

    fresh = cast(Any, api_client).get(
        path,
        **_signed_headers(secret="test-secret", timestamp_ms=timestamp_ms + 1),
    )
    assert fresh.status_code != status.HTTP_401_UNAUTHORIZED


def test_expired_and_revoked_tokens_are_rejected(user: User):
    expired_token = AccessToken.for_user(user)
    expired_token.set_exp(lifetime=timedelta(seconds=-1))

    expired_client = APIClient()
    expired_client.credentials(HTTP_AUTHORIZATION=f"Bearer {expired_token}")
    expired = expired_client.get("/api/auth/me")
    assert expired.status_code == status.HTTP_401_UNAUTHORIZED

    revoked_token = AccessToken.for_user(user)
    revoke_access_token(revoked_token)
    revoked_client = APIClient()
    revoked_client.credentials(HTTP_AUTHORIZATION=f"Bearer {revoked_token}")
    revoked = revoked_client.get("/api/auth/me")
    assert revoked.status_code == status.HTTP_401_UNAUTHORIZED


@override_settings(API_REQUEST_MAX_BYTES=16)
def test_api_request_size_middleware_rejects_oversized_api_payload(api_client: APIClient):
    response = api_client.post(
        "/api/auth/login",
        data=json.dumps({"email": "a" * 32, "password": "b" * 32}),
        content_type="application/json",
    )
    assert response.status_code == status.HTTP_413_REQUEST_ENTITY_TOO_LARGE
    assert response.json()["error"]["code"] == "REQUEST_TOO_LARGE"


def test_global_api_throttle_defaults_are_configured():
    rest_framework = cast(dict[str, Any], settings.REST_FRAMEWORK)
    throttle_classes = cast(list[str], rest_framework["DEFAULT_THROTTLE_CLASSES"])
    throttle_rates = cast(dict[str, str], rest_framework["DEFAULT_THROTTLE_RATES"])

    assert "rest_framework.throttling.AnonRateThrottle" in throttle_classes
    assert "rest_framework.throttling.UserRateThrottle" in throttle_classes
    assert throttle_rates["anon"]
    assert throttle_rates["user"]


def test_rate_limited_matrix_case_is_exercised_by_auth_scope(api_client: APIClient):
    cache.clear()
    rest_framework = cast(dict[str, Any], settings.REST_FRAMEWORK)
    throttle_rates = cast(dict[str, str], rest_framework["DEFAULT_THROTTLE_RATES"])
    throttled_settings = {
        **rest_framework,
        "DEFAULT_THROTTLE_RATES": {
            **throttle_rates,
            "auth_login": "1/min",
        },
    }
    with override_settings(REST_FRAMEWORK=throttled_settings):
        first = api_client.post(
            "/api/auth/login",
            data={"email": "nobody@example.com", "password": "wrong"},
            format="json",
        )
        second = api_client.post(
            "/api/auth/login",
            data={"email": "nobody@example.com", "password": "wrong"},
            format="json",
        )

    assert first.status_code in {status.HTTP_400_BAD_REQUEST, status.HTTP_401_UNAUTHORIZED}
    assert second.status_code == status.HTTP_429_TOO_MANY_REQUESTS


def test_sensitive_matrix_rows_declare_audit_actions():
    matrix = _load_matrix()
    sensitive_ids = {
        "operator-runtime-intents-intent-id-replay",
        "operator-runtime-intents-intent-id-acknowledge",
        "operator-runs-run-id-force-fail",
        "operator-runs-run-id-force-cancel",
        "operator-runs-run-id-force-rehydrate",
        "credentials",
        "credentials-credential-id",
        "credentials-credential-id-rotate",
        "credentials-credential-id-revoke",
        "executions-run-id-cancel",
        "executions-run-id-resume",
        "executions-run-id-replay",
        "orgs-members",
        "orgs-members-user-id",
        "retention-cleanup",
        "retention-export",
        "marketplace-releases-release-id-review",
        "prompts-prompt-id-publish",
        "templates-template-id-shares",
        "runs-run-id-cancel",
        "runs-run-id-resume",
        "runs-run-id-replay",
        "ops-dead-letters-dead-letter-key-replay",
        "ops-dead-letters-dead-letter-key-resolve",
    }
    entries = {route["id"]: route for route in matrix["routes"]}
    missing = [
        route_id
        for route_id in sensitive_ids
        if not entries.get(route_id, {}).get("sensitive_audit_action")
    ]
    assert not missing


def test_org_membership_sensitive_action_writes_audit_log(
    authenticated_client: APIClient, user: User
):
    target = User.objects.create_user(email="new-member@example.com", password="testpassword123")

    response = authenticated_client.post(
        "/api/orgs/members",
        data={"email": target.email, "role": "viewer"},
        format="json",
    )

    assert response.status_code == status.HTTP_201_CREATED
    membership = OrganizationMembership.objects.get(
        organization=user.default_organization,
        user=target,
    )
    audit = AuditLog.objects.get(
        action="org.member_added",
        resource_type="organization_membership",
        resource_id=str(membership.id),
    )
    assert audit.actor == user
    assert str(audit.tenant_id) == str(user.default_organization_id)
    assert audit.metadata["target_user_id"] == str(target.id)
    assert "password" not in audit.metadata
