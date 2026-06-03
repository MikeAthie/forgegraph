#!/usr/bin/env python
"""Controlled Atlas P2 backend-owned whiteboard load smoke.

This is evidence generation, not a public capacity benchmark. It drives only
generic backend APIs and treats DB/API state as authoritative.
"""

from __future__ import annotations

import argparse
import concurrent.futures
import json
import math
import os
import random
import string
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

AGENCY_PHASE_ID = "digital_marketing_pro.v1.atlas_agency_work_graph"
EXPECTED_WORKSTREAMS = [
    "strategy_brief",
    "legal_claims_precheck",
    "tech_execution_readiness",
    "media_channel_plan",
    "copy_message_house",
    "analytics_measurement_plan",
    "traffic_dependency_map",
    "content_asset_map",
    "timing_flighting_plan",
    "deployment_readiness_plan",
]
INITIAL_PARALLEL_WORKSTREAMS = [
    "account_brief_compilation",
    "strategy_brief",
    "legal_claims_precheck",
    "tech_execution_readiness",
    "media_channel_plan",
    "copy_message_house",
    "analytics_measurement_plan",
    "traffic_dependency_map",
]
INITIALLY_BLOCKED_WORKSTREAMS = [
    "content_asset_map",
    "timing_flighting_plan",
    "deployment_readiness_plan",
]
VERTICAL_ROUTE_PATTERN = ("/api/atlas/", "/api/marketing/", "/api/legacy/")


class ApiError(RuntimeError):
    def __init__(self, method: str, path: str, status: int, body: str) -> None:
        super().__init__(f"{method} {path} failed with {status}: {body[:1000]}")
        self.method = method
        self.path = path
        self.status = status
        self.body = body


class ApiClient:
    def __init__(self, base_url: str, *, token: str = "") -> None:
        self.base_url = base_url.rstrip("/")
        self.token = token
        self.routes: list[dict[str, str]] = []
        self._lock = threading.Lock()

    def child(self, *, token: str | None = None) -> ApiClient:
        child = ApiClient(self.base_url, token=self.token if token is None else token)
        child.routes = self.routes
        child._lock = self._lock
        return child

    def get(self, path: str) -> Any:
        return self._request("GET", path)

    def post(self, path: str, data: Any | None = None, *, key: str = "") -> Any:
        return self._request("POST", path, data=data or {}, idempotency_key=key)

    def patch(self, path: str, data: Any | None = None, *, key: str = "") -> Any:
        return self._request("PATCH", path, data=data or {}, idempotency_key=key)

    def _request(
        self,
        method: str,
        path: str,
        *,
        data: Any | None = None,
        idempotency_key: str = "",
    ) -> Any:
        url = f"{self.base_url}{path}"
        headers = {"Accept": "application/json"}
        body = None
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        if idempotency_key:
            headers["Idempotency-Key"] = idempotency_key
        if data is not None:
            body = json.dumps(data).encode("utf-8")
            headers["Content-Type"] = "application/json"
        with self._lock:
            self.routes.append({"method": method, "pathname": urllib.parse.urlparse(path).path})
        request = urllib.request.Request(url, data=body, headers=headers, method=method)
        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                raw = response.read().decode("utf-8")
                return json.loads(raw) if raw else {}
        except urllib.error.HTTPError as exc:
            raw = exc.read().decode("utf-8", errors="replace")
            raise ApiError(method, path, exc.code, raw) from exc


@dataclass(frozen=True)
class TenantFixture:
    index: int
    client: ApiClient
    company_id: str
    email: str


def main() -> int:
    args = parse_args()
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    started_at = utc_now()
    base_client = ApiClient(args.api_base_url)
    tenants = [create_tenant_fixture(base_client, index) for index in range(args.tenants)]
    work_items = [
        (tenant, whiteboard_index)
        for tenant in tenants
        for whiteboard_index in range(args.whiteboards_per_tenant)
    ]

    results: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.concurrency) as executor:
        futures = [
            executor.submit(run_whiteboard_flow, tenant, whiteboard_index)
            for tenant, whiteboard_index in work_items
        ]
        for future in concurrent.futures.as_completed(futures):
            try:
                results.append(future.result())
            except Exception as exc:  # noqa: BLE001 - artifact should include every failure.
                errors.append({"error": str(exc), "type": exc.__class__.__name__})

    projection_lag = sample_projection_lag(tenants[0].client)
    transport = sample_transport_evidence(tenants)
    route_paths = sorted({route["pathname"] for tenant in tenants for route in tenant.client.routes})
    vertical_routes = [
        path
        for path in route_paths
        if any(path.lower().startswith(prefix) for prefix in VERTICAL_ROUTE_PATTERN)
    ]
    lag_samples = [
        int(result.get("projection_lag_ms") or 0)
        for result in results
        if isinstance(result.get("projection_lag_ms"), int)
    ]
    if projection_lag.get("projection", {}).get("projection_lag_ms") is not None:
        lag_samples.append(int(projection_lag["projection"]["projection_lag_ms"]))
    p95_lag_ms = percentile(lag_samples, 95)
    active_dead_letters = int(
        len(projection_lag.get("active_dead_letters") or [])
        + sum(int(item.get("dead_letters", {}).get("active_count") or 0) for item in transport)
    )
    projection_evidence_available = projection_lag.get("available") is True
    transport_evidence_available = all(item.get("available") is True for item in transport)
    transport_backend_owned = all(
        item.get("authoritative_state_source") == "backend_db" for item in transport
    )
    summary = {
        "schema_version": "atlas_p2_load_smoke_v1",
        "started_at": started_at,
        "completed_at": utc_now(),
        "api_base_url": args.api_base_url,
        "requested": {
            "tenants": args.tenants,
            "whiteboards_per_tenant": args.whiteboards_per_tenant,
            "concurrency": args.concurrency,
        },
        "result_counts": {
            "total": len(results),
            "errors": len(errors),
            "terminal_phase_operations": sum(1 for item in results if item.get("operations_terminal")),
            "initial_parallel_unblocked": sum(1 for item in results if item.get("initial_parallel_unblocked")),
            "initial_dependencies_blocked": sum(
                1 for item in results if item.get("initial_dependencies_blocked")
            ),
            "final_workstreams_completed": sum(
                1 for item in results if item.get("final_workstreams_completed")
            ),
            "dependency_transitions_ok": sum(1 for item in results if item.get("dependency_transitions_ok")),
            "gate_passed": sum(1 for item in results if item.get("gate_result") == "pass"),
        },
        "evidence_availability": {
            "projection_lag": projection_evidence_available,
            "transport_evidence": transport_evidence_available,
            "transport_backend_owned": transport_backend_owned,
        },
        "projection_lag_p95_ms": p95_lag_ms,
        "projection_lag_threshold_ms": args.projection_lag_threshold_ms,
        "active_dead_letters": active_dead_letters,
        "vertical_routes": vertical_routes,
        "transport_evidence": transport,
        "projection_lag": projection_lag,
        "results": results,
        "errors": errors,
        "routes": route_paths,
        "authoritative_state_source": "backend_db",
    }
    summary["passed"] = (
        not errors
        and len(results) == len(work_items)
        and all(item.get("operations_terminal") for item in results)
        and all(item.get("initial_parallel_unblocked") for item in results)
        and all(item.get("initial_dependencies_blocked") for item in results)
        and all(item.get("final_workstreams_completed") for item in results)
        and all(item.get("dependency_transitions_ok") for item in results)
        and all(item.get("gate_result") == "pass" for item in results)
        and projection_evidence_available
        and transport_evidence_available
        and transport_backend_owned
        and p95_lag_ms <= args.projection_lag_threshold_ms
        and active_dead_letters == 0
        and not vertical_routes
    )
    write_artifacts(output_dir, summary)
    return 0 if summary["passed"] else 1


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run Atlas P2 whiteboard load smoke.")
    parser.add_argument("--tenants", type=int, default=2)
    parser.add_argument("--whiteboards-per-tenant", type=int, default=5)
    parser.add_argument("--concurrency", type=int, default=4)
    parser.add_argument("--output-dir", default="logs/atlas-p2-load")
    parser.add_argument(
        "--api-base-url",
        default=os.environ.get("ATLAS_LOAD_API_BASE_URL", "http://127.0.0.1:8000"),
    )
    parser.add_argument("--projection-lag-threshold-ms", type=int, default=2000)
    return parser.parse_args()


def create_tenant_fixture(base_client: ApiClient, index: int) -> TenantFixture:
    suffix = random_suffix()
    email = f"atlas-p2-load-{index}-{suffix}@example.com"
    password = "ForgeGraphLoad!12345"
    base_client.post("/api/auth/register", {"email": email, "password": password})
    login = base_client.post("/api/auth/login", {"email": email, "password": password})
    token = str(login.get("access") or "")
    if not token:
        raise RuntimeError("Login did not return an access token.")
    client = base_client.child(token=token)
    company = data(
        client.post(
            "/api/graphs/",
            {
                "name": f"Atlas P2 Load Tenant {index}",
                "description": "Controlled Atlas P2 load fixture.",
            },
        )
    )
    company_id = str(company["id"])
    client.post(
        f"/api/graphs/{company_id}/versions",
        {
            "graph_json": {
                "nodes": [],
                "edges": [],
                "metadata": {"atlas_p2_load": True, "tenant_index": index},
            }
        },
        key=f"atlas-p2-load:graph-version:{company_id}",
    )
    client.post(
        f"/api/companies/{company_id}/packs/install",
        {
            "pack_id": "digital_marketing_pro.v1",
            "role": "primary",
            "config": {
                "skip_graph_version": True,
                "available_connectors": ["email_connector", "social_connector", "analytics_connector"],
                "connector_modes": {
                    "email_connector": "sandbox",
                    "social_connector": "sandbox",
                    "analytics_connector": "sandbox",
                },
            },
        },
        key=f"atlas-p2-load:pack:{company_id}",
    )
    return TenantFixture(index=index, client=client, company_id=company_id, email=email)


def run_whiteboard_flow(tenant: TenantFixture, whiteboard_index: int) -> dict[str, Any]:
    client = tenant.client
    key_prefix = f"atlas-p2-load:t{tenant.index}:w{whiteboard_index}"
    thread = data(
        client.post(
            "/api/communication/threads",
            {
                "company_id": tenant.company_id,
                "title": f"Atlas P2 load request {whiteboard_index}",
                "thread_type": "support",
                "visibility_mode": "mixed",
                "source_key": key_prefix,
            },
            key=f"{key_prefix}:thread",
        )
    )["thread"]
    message = data(
        client.post(
            f"/api/communication/threads/{thread['id']}/messages",
            {
                "message_kind": "request",
                "body": (
                    "Create a Legacy DEPP GOLD campaign with 10,000 MXN budget across email, "
                    "social, and analytics. Keep connector blockers explicit."
                ),
                "visibility": "customer",
            },
            key=f"{key_prefix}:message",
        )
    )["message"]
    routed = data(
        client.post(
            f"/api/communication/messages/{message['id']}/route-request",
            {},
            key=f"{key_prefix}:route",
        )
    )
    whiteboard = routed.get("whiteboard") or {}
    whiteboard_id = str(whiteboard.get("id") or "")
    if not whiteboard_id:
        raise RuntimeError("Route request did not create a whiteboard.")
    patch_whiteboard_context(client, whiteboard_id, key_prefix)
    ready = data(
        client.post(
            f"/api/whiteboards/{whiteboard_id}/ready-for-planning",
            {},
            key=f"{key_prefix}:ready",
        )
    )["whiteboard"]
    start = phase_action(client, whiteboard_id, "start", key=f"{key_prefix}:phase-start")
    contract = wait_for_phase_workstreams(client, whiteboard_id)
    initial = workstreams_by_id(contract)
    for workstream_id in [
        *INITIAL_PARALLEL_WORKSTREAMS,
        "content_asset_map",
        "timing_flighting_plan",
        "deployment_readiness_plan",
    ]:
        complete_workstream(client, whiteboard_id, workstream_id, key_prefix)
    after_complete = get_phase_contract(client, whiteboard_id)
    synthesis = phase_action(client, whiteboard_id, "synthesize", key=f"{key_prefix}:phase-synthesize")
    evaluated = phase_action(
        client,
        whiteboard_id,
        "evaluate",
        data={"scorecard": phase_scorecard()},
        key=f"{key_prefix}:phase-evaluate",
    )
    final_contract = get_phase_contract(client, whiteboard_id)
    operation_ids = [
        start["operation"]["id"],
        synthesis["operation"]["id"],
        evaluated["operation"]["id"],
    ]
    operations = [get_operation(client, whiteboard_id, operation_id) for operation_id in operation_ids]
    projection_lag = sample_projection_lag(client)
    final_workstreams = workstreams_by_id(final_contract)
    return {
        "tenant_index": tenant.index,
        "whiteboard_index": whiteboard_index,
        "company_id": tenant.company_id,
        "thread_id": thread["id"],
        "message_id": message["id"],
        "whiteboard_id": whiteboard_id,
        "ready_status": ready.get("status"),
        "initial_parallel_unblocked": all(
            initial.get(workstream_id, {}).get("status") != "blocked"
            for workstream_id in INITIAL_PARALLEL_WORKSTREAMS
        ),
        "initial_dependencies_blocked": all(
            initial.get(workstream_id, {}).get("status") == "blocked"
            for workstream_id in INITIALLY_BLOCKED_WORKSTREAMS
        ),
        "final_workstreams_completed": all(
            final_workstreams.get(workstream_id, {}).get("status") == "completed"
            for workstream_id in EXPECTED_WORKSTREAMS
        ),
        "dependency_transitions_ok": (
            all(
                initial.get(workstream_id, {}).get("status") == "blocked"
                for workstream_id in INITIALLY_BLOCKED_WORKSTREAMS
            )
            and all(
                final_workstreams.get(workstream_id, {}).get("status") == "completed"
                for workstream_id in EXPECTED_WORKSTREAMS
            )
        ),
        "operations": [
            {
                "id": operation["id"],
                "kind": operation["kind"],
                "status": operation["status"],
                "terminal": operation["terminal"],
            }
            for operation in operations
        ],
        "operations_terminal": all(
            operation.get("terminal") is True and operation.get("status") == "completed"
            for operation in operations
        ),
        "projection_lag_ms": int(projection_lag.get("projection", {}).get("projection_lag_ms") or 0),
        "phase_status": final_contract.get("current_state", {}).get("status"),
        "gate_result": final_contract.get("current_state", {}).get("gate", {}).get("result"),
        "after_complete_statuses": {
            key: value.get("status") for key, value in workstreams_by_id(after_complete).items()
        },
    }


def patch_whiteboard_context(client: ApiClient, whiteboard_id: str, key_prefix: str) -> None:
    client.patch(
        f"/api/whiteboards/{whiteboard_id}",
        {
            "objective": "Launch a measured demand campaign for Legacy DEPP GOLD.",
            "budget_limit": "10000 MXN",
            "timeline": "two-week launch window",
            "constraints": {"inventory": "limited", "compliance": "avoid unsupported claims"},
            "delivery_context": {
                "requested_channels": ["email", "Instagram", "Facebook", "TikTok"],
                "connector_readiness": {
                    "email_connector": "sandbox",
                    "social_connector": "sandbox",
                    "analytics_connector": "sandbox",
                    "whatsapp_connector": "not_configured",
                },
            },
            "known_facts": {"product": "Legacy DEPP GOLD", "price": "599 MXN"},
        },
        key=f"{key_prefix}:context",
    )


def wait_for_phase_workstreams(client: ApiClient, whiteboard_id: str) -> dict[str, Any]:
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        contract = get_phase_contract(client, whiteboard_id)
        if len(contract.get("workstreams") or []) >= len(EXPECTED_WORKSTREAMS):
            return contract
        time.sleep(0.5)
    raise RuntimeError(f"Phase workstreams did not materialize for {whiteboard_id}.")


def phase_action(
    client: ApiClient,
    whiteboard_id: str,
    action: str,
    *,
    data: Any | None = None,
    key: str,
) -> dict[str, Any]:
    payload = data or {}
    result = data_or_envelope(
        client.post(
            f"/api/whiteboards/{whiteboard_id}/phases/{AGENCY_PHASE_ID}/{action}",
            payload,
            key=key,
        )
    )
    operation = result.get("operation") or {}
    if operation.get("id"):
        wait_for_operation(client, whiteboard_id, str(operation["id"]))
    return result


def complete_workstream(client: ApiClient, whiteboard_id: str, workstream_id: str, key_prefix: str) -> None:
    client.post(
        f"/api/whiteboards/{whiteboard_id}/phases/{AGENCY_PHASE_ID}/workstreams/{workstream_id}/complete",
        {
            "result": {
                "summary": f"{workstream_id} completed by Atlas P2 load smoke.",
                "score": 90,
                "evidence_mode": "load_smoke",
            }
        },
        key=f"{key_prefix}:workstream:{workstream_id}",
    )


def get_phase_contract(client: ApiClient, whiteboard_id: str) -> dict[str, Any]:
    return data(client.get(f"/api/whiteboards/{whiteboard_id}/phases/{AGENCY_PHASE_ID}"))[
        "whiteboard_phase_contract"
    ]


def get_operation(client: ApiClient, whiteboard_id: str, operation_id: str) -> dict[str, Any]:
    return data(client.get(f"/api/whiteboards/{whiteboard_id}/operations/{operation_id}"))["operation"]


def wait_for_operation(client: ApiClient, whiteboard_id: str, operation_id: str) -> dict[str, Any]:
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        operation = get_operation(client, whiteboard_id, operation_id)
        if operation.get("terminal") is True:
            return operation
        time.sleep(0.5)
    raise RuntimeError(f"Operation {operation_id} did not reach a terminal status.")


def sample_projection_lag(client: ApiClient) -> dict[str, Any]:
    try:
        return {"available": True, **data(client.get("/api/ops/projection-lag"))}
    except ApiError as exc:
        return {"available": False, "status": exc.status, "error": exc.body}


def sample_transport_evidence(tenants: list[TenantFixture]) -> list[dict[str, Any]]:
    evidence = []
    for tenant in tenants:
        try:
            payload = data(
                tenant.client.get(
                    "/api/ops/transport-evidence?transport=whiteboard_board_kafka"
                )
            )
            evidence.append({"available": True, **payload.get("transport_evidence", {})})
        except ApiError as exc:
            evidence.append({"available": False, "status": exc.status, "error": exc.body})
    return evidence


def phase_scorecard() -> dict[str, Any]:
    return {
        "strategy_readiness": 94,
        "legal_precheck": "pass",
        "measurement_readiness": 91,
        "execution_readiness": 90,
        "asset_plan_readiness": 92,
        "timing_readiness": 89,
    }


def workstreams_by_id(contract: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        str(item.get("id")): item
        for item in contract.get("workstreams", [])
        if isinstance(item, dict)
    }


def data(payload: Any) -> Any:
    if isinstance(payload, dict) and "data" in payload:
        return payload["data"]
    return payload


def data_or_envelope(payload: Any) -> dict[str, Any]:
    value = data(payload)
    if not isinstance(value, dict):
        raise RuntimeError(f"Expected response data object, got {type(value).__name__}.")
    return value


def percentile(values: list[int], percentile_value: int) -> int:
    if not values:
        return 0
    ordered = sorted(values)
    index = max(0, min(len(ordered) - 1, math.ceil((percentile_value / 100) * len(ordered)) - 1))
    return ordered[index]


def write_artifacts(output_dir: Path, summary: dict[str, Any]) -> None:
    (output_dir / "atlas-p2-load.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    lines = [
        "# Atlas P2 Load Smoke",
        "",
        f"- Passed: {summary['passed']}",
        f"- Total whiteboards: {summary['result_counts']['total']}",
        f"- Errors: {summary['result_counts']['errors']}",
        f"- Projection lag p95 ms: {summary['projection_lag_p95_ms']}",
        f"- Active dead letters: {summary['active_dead_letters']}",
        f"- Vertical routes: {len(summary['vertical_routes'])}",
        "",
        "This is controlled P2 evidence only, not a public capacity claim.",
    ]
    (output_dir / "atlas-p2-load.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def random_suffix(length: int = 8) -> str:
    alphabet = string.ascii_lowercase + string.digits
    return "".join(random.choice(alphabet) for _ in range(length))


def utc_now() -> str:
    return datetime.now(UTC).isoformat()


if __name__ == "__main__":
    sys.exit(main())
