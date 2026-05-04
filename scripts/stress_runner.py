#!/usr/bin/env python3
"""Controlled ForgeGraph stress harness.

This script creates real runs through the backend API, waits on backend-owned
state for completion, captures queue/runtime transport metrics, optionally
injects infrastructure failures through Docker, and writes reproducible JSON
artifacts under logs/stress/.
"""

from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import os
import socket
import subprocess
import tempfile
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


TERMINAL_RUN_STATUSES = {"succeeded", "failed", "canceled"}
DEFAULT_CONCURRENCY_LEVELS = [5, 10, 20, 50]
CAPACITY_TIERS: dict[str, dict[str, Any]] = {
    "alpha": {
        "target": "5-10 concurrent agents",
        "max_concurrency": 10,
        "meaning": "internal/customer design partners only",
    },
    "private-beta": {
        "target": "25-50 concurrent agents",
        "max_concurrency": 50,
        "meaning": "limited external users",
    },
    "production-v1": {
        "target": "100 concurrent agents",
        "max_concurrency": 100,
        "meaning": "reliable multi-org operation",
    },
    "production-scale": {
        "target": "500+ concurrent agents after three Phase 3 Gate E evidence runs",
        "max_concurrency": 500,
        "meaning": "proven high-scale company OS; roadmap until measured",
    },
}
PHASE3_CAPACITY_GATES: dict[str, dict[str, Any]] = {
    "A": {
        "concurrent_agents": 25,
        "duration_seconds": 3600,
        "tenant_count": 1,
        "description": "25 concurrent agents for 1 hour with zero silent drops.",
        "max_dead_letter_rate": 0.0,
    },
    "B": {
        "concurrent_agents": 50,
        "duration_seconds": 7200,
        "tenant_count": 1,
        "description": "50 concurrent agents for 2 hours with projection lag p95 under 2s.",
        "max_projection_lag_ms": 2000,
        "max_dead_letter_rate": 0.0,
    },
    "C": {
        "concurrent_agents": 100,
        "duration_seconds": 14400,
        "tenant_count": 5,
        "description": "100 concurrent agents for 4 hours with retry/dead-letter within SLO.",
        "max_dead_letter_rate": 0.001,
        "requires_retries": True,
    },
    "D": {
        "concurrent_agents": 250,
        "duration_seconds": 14400,
        "tenant_count": 10,
        "description": "250 concurrent agents for 4 hours with reconnect storm coverage.",
        "max_dead_letter_rate": 0.001,
        "requires_websocket_reconnect_storm": True,
    },
    "E": {
        "concurrent_agents": 500,
        "duration_seconds": 28800,
        "tenant_count": 25,
        "description": "500 concurrent agents for 8 hours, multi-tenant, HITL, memory, accounting, failures.",
        "max_backend_api_p95_ms": 300,
        "max_event_ingestion_p95_ms": 500,
        "max_projection_lag_ms": 2000,
        "max_websocket_p95_ms": 1000,
        "max_dead_letter_rate": 0.001,
        "requires_multi_tenant": True,
        "requires_hitl": True,
        "requires_memory_writes": True,
        "requires_accounting": True,
        "requires_retries": True,
        "requires_llm_throttling": True,
        "requires_failure_injection": True,
        "requires_websocket_reconnect_storm": True,
        "requires_duplicate_event_storm": True,
    },
}
PRODUCTION_SCALE_SCENARIOS = {
    "synthetic-no-llm-500",
    "controlled-llm-latency",
    "real-provider-capacity",
}
SCENARIO_CHOICES = [
    "endpoint-saturation",
    "engine-concurrency",
    "redis-saturation",
    "llm-degradation-delay",
    "llm-degradation-timeout",
    "llm-degradation-unavailable",
    "failure-injection-engine-stop",
    "failure-injection-redis-stop",
    "synthetic-no-llm-500",
    "controlled-llm-latency",
    "real-provider-capacity",
    "websocket-reconnect-storm",
    "duplicate-event-storm",
    "all",
]
ROOT_DIR = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT_DIR = ROOT_DIR / "logs" / "stress"


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def iso_now() -> str:
    return utc_now().isoformat()


def _build_callback_signature(*, secret: str, timestamp_ms: str, body: bytes) -> str:
    message = f"{timestamp_ms}.".encode("utf-8") + body
    return hmac.new(secret.encode("utf-8"), message, hashlib.sha256).hexdigest()


def classify_error(message: str, *, http_status: int | None = None) -> str:
    normalized = (message or "").strip().lower()
    if http_status == 429 or "rate limit" in normalized:
        return "rate_limit"
    if http_status in {502, 503, 504}:
        return "connection"
    if "timeout" in normalized or "deadline exceeded" in normalized:
        return "timeout"
    if any(
        token in normalized
        for token in (
            "connection refused",
            "connection reset",
            "temporarily unavailable",
            "network",
            "unavailable",
        )
    ):
        return "connection"
    if http_status and http_status >= 500:
        return "internal"
    return "internal" if normalized else "unknown"


def percentile(values: list[float], pct: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    idx = (len(ordered) - 1) * pct
    lower = int(idx)
    upper = min(lower + 1, len(ordered) - 1)
    if lower == upper:
        return float(ordered[lower])
    fraction = idx - lower
    return float(ordered[lower] * (1 - fraction) + ordered[upper] * fraction)


def deep_get(payload: dict[str, Any] | None, *path: str, default: Any = None) -> Any:
    current: Any = payload
    for part in path:
        if not isinstance(current, dict) or part not in current:
            return default
        current = current[part]
    return current


def metric_int(payload: dict[str, Any] | None, *path: str) -> int | None:
    value = deep_get(payload, *path)
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def metric_float(payload: dict[str, Any] | None, *path: str) -> float | None:
    value = deep_get(payload, *path)
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def metric_delta(
    before: dict[str, Any] | None,
    after: dict[str, Any] | None,
    *path: str,
) -> int | None:
    before_value = metric_int(before, *path)
    after_value = metric_int(after, *path)
    if before_value is None or after_value is None:
        return None
    return max(after_value - before_value, 0)


def metric_first_float(
    payload: dict[str, Any] | None, paths: list[tuple[str, ...]]
) -> float | None:
    for path in paths:
        value = metric_float(payload, *path)
        if value is not None:
            return value
    return None


def _count_decisions(run_detail: dict[str, Any]) -> int | None:
    for key in ("decisions", "pending_decisions", "approval_tasks"):
        value = run_detail.get(key)
        if isinstance(value, list):
            return len(value)
    return None


def _count_memory_writes(run_detail: dict[str, Any]) -> int | None:
    memory_activity = run_detail.get("memory_activity")
    if isinstance(memory_activity, dict):
        for key in ("write_count", "observation_count", "created_count"):
            value = memory_activity.get(key)
            if isinstance(value, int):
                return value
    value = run_detail.get("memory_writes")
    return int(value) if isinstance(value, (int, float)) else None


def _extract_run_cost_usd(run_detail: dict[str, Any]) -> float | None:
    for key in ("cost_to_date", "total_cost_usd", "cost_usd"):
        value = run_detail.get(key)
        if isinstance(value, (int, float)):
            return float(value)
    accounting = run_detail.get("accounting")
    if isinstance(accounting, dict):
        value = accounting.get("total_cost_usd")
        if isinstance(value, (int, float)):
            return float(value)
    return None


def load_env_file(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.exists():
        return values
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip()
    return values


@dataclass
class RunRecord:
    scenario: str
    concurrency: int
    tenant_slot: int
    run_id: str
    start_time: str
    end_time: str
    latency_ms: int
    status: str
    error: str
    error_type: str
    http_status: int | None = None
    queue_status: str | None = None
    queue_attempts: int | None = None
    node_execution_time_ms: int | None = None
    node_retry_count: int = 0
    duplicate_node_execution: bool = False
    redis_lag: int | None = None
    redis_backlog: int | None = None
    queue_backlog_size: int | None = None
    last_progress_at: str | None = None
    recovery_state: str | None = None
    recovery_reason: str | None = None
    decision_count: int | None = None
    memory_write_count: int | None = None
    cost_usd: float | None = None
    websocket_reconnects: int = 0
    duplicate_event_attempts: int = 0


@dataclass
class ScenarioMetrics:
    total_runs: int
    successful_runs: int
    failed_runs: int
    avg_latency_ms: float | None
    max_latency_ms: int | None
    latency_p95_ms: float | None
    timeouts: int
    retry_count: int
    duplicate_node_execution_count: int
    error_types: dict[str, int]
    max_queue_backlog: int | None
    max_runtime_backlog: int | None
    max_runtime_lag: int | None
    backend_api_latency_p95_ms: float | None
    websocket_send_latency_p95_ms: float | None
    backend_api_latency_within_target: bool | None
    websocket_send_latency_within_target: bool | None
    websocket_messages_dropped_delta: int | None
    runtime_dead_letter_delta: int | None
    queue_bounded: bool | None
    success_rate: float | None
    dead_letter_rate: float | None
    event_dead_letter_delta: int | None
    projection_lag_p95_ms: float | None
    event_ingestion_latency_p95_ms: float | None
    tenant_slots: int
    decision_count: int
    memory_write_count: int
    cost_usd_total: float
    websocket_reconnects: int
    duplicate_event_attempts: int


@dataclass
class FailureAnalysis:
    scenario: str
    breaking_point: str
    first_failure_type: str
    system_behavior: str
    data_integrity: str


@dataclass
class ScenarioResult:
    scenario: str
    started_at: str
    completed_at: str
    concurrency_levels: list[int]
    runs_per_level: int
    duration_seconds: float | None
    capacity_gate: str | None
    requested_features: dict[str, bool]
    records: list[RunRecord]
    metrics: ScenarioMetrics
    analysis: FailureAnalysis
    metrics_before: dict[str, Any] = field(default_factory=dict)
    metrics_after: dict[str, Any] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)


@dataclass
class FailurePlan:
    service: str
    action: str
    trigger_delay_seconds: float
    restart_after_seconds: float | None = None


@dataclass
class Phase3GateEvaluation:
    gate: str
    passed: bool
    requirements: dict[str, bool]
    reasons: list[str]


class HttpJsonClient:
    def __init__(self, base_url: str) -> None:
        self.base_url = base_url.rstrip("/")
        self.access_token: str | None = None
        self._email: str | None = None
        self._password: str | None = None

    def set_access_token(self, token: str) -> None:
        self.access_token = token

    def login(self, email: str, password: str) -> str:
        self._email = email
        self._password = password
        payload = self.request(
            "POST",
            "/api/auth/login",
            body={"email": email, "password": password},
            auth=False,
        )
        token = str(payload.get("access") or "").strip()
        if not token:
            raise RuntimeError("login did not return an access token")
        self.access_token = token
        return token

    def request(
        self,
        method: str,
        path: str,
        *,
        body: dict[str, Any] | None = None,
        auth: bool = True,
        timeout: float = 30.0,
    ) -> dict[str, Any]:
        url = self.base_url + path
        data = None
        headers = {"Accept": "application/json"}
        if body is not None:
            data = json.dumps(body).encode("utf-8")
            headers["Content-Type"] = "application/json"
        if auth and self.access_token:
            headers["Authorization"] = f"Bearer {self.access_token}"

        request = urllib.request.Request(url, data=data, headers=headers, method=method)
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                raw = response.read().decode("utf-8")
                return json.loads(raw) if raw else {}
        except urllib.error.HTTPError as exc:
            raw = exc.read().decode("utf-8")
            detail = raw
            payload: dict[str, Any] = {}
            if raw:
                try:
                    payload = json.loads(raw)
                except json.JSONDecodeError:
                    payload = {}
            if payload:
                detail = json.dumps(payload)
            raise RuntimeError(f"HTTP {exc.code} {path}: {detail}") from exc
        except urllib.error.URLError as exc:
            raise RuntimeError(f"request failed for {path}: {exc.reason}") from exc
        except TimeoutError as exc:
            raise RuntimeError(f"request timed out for {path}: {exc}") from exc
        except socket.timeout as exc:
            raise RuntimeError(f"request timed out for {path}: {exc}") from exc

    def try_request(
        self,
        method: str,
        path: str,
        *,
        body: dict[str, Any] | None = None,
        auth: bool = True,
        timeout: float = 30.0,
        retry_auth: bool = True,
    ) -> tuple[dict[str, Any] | None, int | None, str | None]:
        url = self.base_url + path
        data = None
        headers = {"Accept": "application/json"}
        if body is not None:
            data = json.dumps(body).encode("utf-8")
            headers["Content-Type"] = "application/json"
        if auth and self.access_token:
            headers["Authorization"] = f"Bearer {self.access_token}"
        request = urllib.request.Request(url, data=data, headers=headers, method=method)
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                raw = response.read().decode("utf-8")
                payload = json.loads(raw) if raw else {}
                return payload, response.status, None
        except urllib.error.HTTPError as exc:
            raw = exc.read().decode("utf-8")
            message = raw or str(exc)
            try:
                parsed = json.loads(raw) if raw else {}
                error_message = deep_get(parsed, "error", "message") or deep_get(
                    parsed, "detail"
                )
                if error_message:
                    message = str(error_message)
                if (
                    exc.code == 401
                    and auth
                    and retry_auth
                    and self._email
                    and self._password
                ):
                    self.login(self._email, self._password)
                    return self.try_request(
                        method,
                        path,
                        body=body,
                        auth=auth,
                        timeout=timeout,
                        retry_auth=False,
                    )
                return parsed, exc.code, message
            except json.JSONDecodeError:
                if (
                    exc.code == 401
                    and auth
                    and retry_auth
                    and self._email
                    and self._password
                ):
                    self.login(self._email, self._password)
                    return self.try_request(
                        method,
                        path,
                        body=body,
                        auth=auth,
                        timeout=timeout,
                        retry_auth=False,
                    )
                return None, exc.code, message
        except urllib.error.URLError as exc:
            return None, None, str(exc.reason)
        except TimeoutError as exc:
            return None, None, str(exc)
        except socket.timeout as exc:
            return None, None, str(exc)


class DockerComposeController:
    def __init__(
        self,
        *,
        root_dir: Path,
        compose_file: Path | None = None,
        base_env_file: Path | None = None,
    ) -> None:
        self.root_dir = root_dir
        self.compose_file = compose_file or (root_dir / "docker-compose.yml")
        self.base_env_file = base_env_file or (root_dir / ".env")

    def run(self, args: list[str], *, env_file: Path | None = None) -> None:
        command = ["docker", "compose", "-f", str(self.compose_file)]
        if env_file is not None:
            command.extend(["--env-file", str(env_file)])
        command.extend(args)
        subprocess.run(
            command, cwd=self.root_dir, check=True, capture_output=True, text=True
        )

    def stop(self, service: str) -> None:
        self.run(["stop", service])

    def start(
        self, service: str, *, env_file: Path | None = None, recreate: bool = False
    ) -> None:
        args = ["up", "-d"]
        if recreate:
            args.append("--force-recreate")
        args.append(service)
        self.run(args, env_file=env_file)

    def restart(self, service: str, *, env_file: Path | None = None) -> None:
        self.run(["restart", service], env_file=env_file)

    def recreate_with_overrides(self, service: str, overrides: dict[str, str]) -> None:
        base_env = load_env_file(self.base_env_file)
        merged = {**base_env, **overrides}
        with tempfile.NamedTemporaryFile(
            "w", encoding="utf-8", suffix=".env", delete=False
        ) as handle:
            for key in sorted(merged):
                handle.write(f"{key}={merged[key]}\n")
            env_path = Path(handle.name)
        try:
            self.start(service, env_file=env_path, recreate=True)
        finally:
            env_path.unlink(missing_ok=True)


class StressHarness:
    def __init__(
        self,
        *,
        client: HttpJsonClient,
        clients: list[HttpJsonClient] | None = None,
        graph_version_id: str,
        output_dir: Path,
        per_run_timeout_seconds: float,
        poll_interval_seconds: float,
        metrics_client: HttpJsonClient | None = None,
        docker: DockerComposeController | None = None,
        input_payload: dict[str, Any] | None = None,
        requested_features: dict[str, bool] | None = None,
        websocket_base_url: str = "",
        engine_callback_secret: str = "",
        client_graph_version_ids: list[str] | None = None,
    ) -> None:
        self.client = client
        self.clients = clients or [client]
        self.metrics_client = metrics_client or client
        self.graph_version_id = graph_version_id
        self.output_dir = output_dir
        self.per_run_timeout_seconds = per_run_timeout_seconds
        self.poll_interval_seconds = poll_interval_seconds
        self.docker = docker
        self.input_payload = input_payload or {}
        self.requested_features = requested_features or {}
        self.websocket_base_url = websocket_base_url
        self.engine_callback_secret = engine_callback_secret
        self.client_graph_version_ids = client_graph_version_ids or []
        self._started_run_ids: list[str] = []
        self._run_ids_lock = threading.Lock()

    def fetch_metrics_summary(self) -> dict[str, Any]:
        payload, status_code, error = self.metrics_client.try_request(
            "GET", "/api/metrics/summary"
        )
        if status_code == 200 and payload:
            return deep_get(payload, "data", default={}) or {}
        if error:
            return {"error": error, "status_code": status_code}
        return {}

    def fetch_latest_graph_version(self, graph_id: str) -> str:
        payload = self.client.request("GET", f"/api/graphs/{graph_id}/versions/latest")
        version_id = str(deep_get(payload, "data", "id", default="") or "").strip()
        if not version_id:
            raise RuntimeError(
                f"could not resolve latest graph version for graph {graph_id}"
            )
        return version_id

    def _note_run_started(self, run_id: str) -> None:
        with self._run_ids_lock:
            self._started_run_ids.append(run_id)

    def _current_run_ids(self) -> list[str]:
        with self._run_ids_lock:
            return list(self._started_run_ids)

    def _input_payload_for_run(
        self,
        *,
        scenario: str,
        concurrency: int,
        tenant_slot: int,
        sequence: int,
    ) -> dict[str, Any]:
        payload = dict(self.input_payload)
        stress_profile = payload.get("stress_profile")
        if not isinstance(stress_profile, dict):
            stress_profile = {}
        stress_profile.update(
            {
                "scenario": scenario,
                "concurrency": concurrency,
                "tenant_slot": tenant_slot,
                "sequence": sequence,
                "requested_features": self.requested_features,
            }
        )
        payload["stress_profile"] = stress_profile
        return payload

    def start_run(
        self,
        *,
        client: HttpJsonClient,
        scenario: str,
        concurrency: int,
        tenant_slot: int,
        sequence: int,
        request_timeout_seconds: float,
    ) -> tuple[dict[str, Any] | None, int | None, str | None, int]:
        start_monotonic = time.perf_counter()
        graph_version_id = (
            self.client_graph_version_ids[tenant_slot]
            if tenant_slot < len(self.client_graph_version_ids)
            and self.client_graph_version_ids[tenant_slot]
            else self.graph_version_id
        )
        payload, status_code, error = client.try_request(
            "POST",
            "/api/runs",
            body={
                "graph_version_id": graph_version_id,
                "input_json": self._input_payload_for_run(
                    scenario=scenario,
                    concurrency=concurrency,
                    tenant_slot=tenant_slot,
                    sequence=sequence,
                ),
            },
            timeout=request_timeout_seconds,
        )
        latency_ms = int((time.perf_counter() - start_monotonic) * 1000)
        return payload, status_code, error, latency_ms

    def wait_for_terminal(
        self,
        *,
        client: HttpJsonClient,
        run_id: str,
    ) -> tuple[dict[str, Any] | None, str | None]:
        deadline = time.perf_counter() + self.per_run_timeout_seconds
        last_error: str | None = None
        while time.perf_counter() < deadline:
            payload, status_code, error = client.try_request(
                "GET",
                f"/api/runs/{run_id}",
                timeout=min(10.0, self.poll_interval_seconds + 5.0),
            )
            if status_code == 200 and payload:
                run_data = deep_get(payload, "data", default={}) or {}
                status_value = str(run_data.get("status") or "").strip().lower()
                if status_value in TERMINAL_RUN_STATUSES:
                    return run_data, None
            elif error:
                last_error = error
            time.sleep(self.poll_interval_seconds)
        return None, last_error or "timed out waiting for terminal status"

    def run_single(
        self,
        *,
        scenario: str,
        concurrency: int,
        request_timeout_seconds: float,
        sequence: int,
    ) -> RunRecord:
        tenant_slot = sequence % max(len(self.clients), 1)
        client = self.clients[tenant_slot]
        started_at = iso_now()
        payload, status_code, error, request_latency_ms = self.start_run(
            client=client,
            scenario=scenario,
            concurrency=concurrency,
            tenant_slot=tenant_slot,
            sequence=sequence,
            request_timeout_seconds=request_timeout_seconds,
        )
        created = deep_get(payload, "data", default={}) or {}
        run_id = str(created.get("id") or "")
        metrics_snapshot = self.fetch_metrics_summary()

        if not run_id:
            end_time = iso_now()
            error_message = error or "run creation failed"
            return RunRecord(
                scenario=scenario,
                concurrency=concurrency,
                tenant_slot=tenant_slot,
                run_id="",
                start_time=started_at,
                end_time=end_time,
                latency_ms=request_latency_ms,
                status="failure",
                error=error_message,
                error_type=classify_error(error_message, http_status=status_code),
                http_status=status_code,
                redis_lag=deep_get(metrics_snapshot, "runtime_transport", "stream_lag"),
                redis_backlog=deep_get(
                    metrics_snapshot, "runtime_transport", "stream_backlog"
                ),
                queue_backlog_size=deep_get(metrics_snapshot, "queue", "total_depth"),
            )

        self._note_run_started(run_id)
        detail, wait_error = self.wait_for_terminal(client=client, run_id=run_id)
        end_time = iso_now()
        final_metrics = self.fetch_metrics_summary()

        if detail is None:
            error_message = wait_error or "timed out waiting for backend state"
            return RunRecord(
                scenario=scenario,
                concurrency=concurrency,
                tenant_slot=tenant_slot,
                run_id=run_id,
                start_time=started_at,
                end_time=end_time,
                latency_ms=int(
                    (
                        datetime.fromisoformat(end_time)
                        - datetime.fromisoformat(started_at)
                    ).total_seconds()
                    * 1000
                ),
                status="failure",
                error=error_message,
                error_type=classify_error(error_message),
                queue_status=str(created.get("queue_status") or "") or None,
                queue_attempts=created.get("queue_attempts"),
                redis_lag=deep_get(final_metrics, "runtime_transport", "stream_lag"),
                redis_backlog=deep_get(
                    final_metrics, "runtime_transport", "stream_backlog"
                ),
                queue_backlog_size=deep_get(final_metrics, "queue", "total_depth"),
            )

        node_runs = detail.get("node_runs") or []
        duplicate_keys: set[tuple[str, int]] = set()
        seen_keys: set[tuple[str, int]] = set()
        retry_count = 0
        attempts_by_node: dict[str, int] = {}
        node_execution_time_ms = 0
        for node_run in node_runs:
            node_id = str(node_run.get("node_id") or "")
            attempt = int(node_run.get("attempt") or 1)
            key = (node_id, attempt)
            if key in seen_keys:
                duplicate_keys.add(key)
            seen_keys.add(key)
            attempts_by_node[node_id] = max(attempts_by_node.get(node_id, 0), attempt)
            duration_ms = node_run.get("duration_ms")
            if isinstance(duration_ms, int):
                node_execution_time_ms += duration_ms
        retry_count = sum(
            max(attempts - 1, 0) for attempts in attempts_by_node.values()
        )

        status_value = str(detail.get("status") or "").strip().lower()
        error_message = str(detail.get("error_message") or "").strip()
        run_latency_ms = request_latency_ms
        started_ts = detail.get("started_at")
        ended_ts = detail.get("ended_at")
        try:
            if started_ts and ended_ts:
                started_dt = datetime.fromisoformat(
                    str(started_ts).replace("Z", "+00:00")
                )
                ended_dt = datetime.fromisoformat(str(ended_ts).replace("Z", "+00:00"))
                run_latency_ms = int((ended_dt - started_dt).total_seconds() * 1000)
            elif isinstance(detail.get("duration_ms"), int):
                run_latency_ms = int(detail["duration_ms"])
        except ValueError:
            pass

        final_status = "success" if status_value == "succeeded" else "failure"
        if not error_message and final_status == "failure":
            error_message = f"run finished with status {status_value}"

        return RunRecord(
            scenario=scenario,
            concurrency=concurrency,
            tenant_slot=tenant_slot,
            run_id=run_id,
            start_time=started_at,
            end_time=end_time,
            latency_ms=run_latency_ms,
            status=final_status,
            error=error_message,
            error_type=classify_error(error_message),
            http_status=status_code,
            queue_status=str(detail.get("queue_status") or "") or None,
            queue_attempts=detail.get("queue_attempts"),
            node_execution_time_ms=node_execution_time_ms or None,
            node_retry_count=retry_count,
            duplicate_node_execution=bool(duplicate_keys),
            redis_lag=deep_get(final_metrics, "runtime_transport", "stream_lag"),
            redis_backlog=deep_get(
                final_metrics, "runtime_transport", "stream_backlog"
            ),
            queue_backlog_size=deep_get(final_metrics, "queue", "total_depth"),
            last_progress_at=str(detail.get("last_progress_at") or "") or None,
            recovery_state=str(detail.get("recovery_state") or "") or None,
            recovery_reason=str(detail.get("recovery_reason") or "") or None,
            decision_count=_count_decisions(detail),
            memory_write_count=_count_memory_writes(detail),
            cost_usd=_extract_run_cost_usd(detail),
        )

    def execute_failure_plan(self, failure_plan: FailurePlan, notes: list[str]) -> None:
        if self.docker is None:
            notes.append(
                "failure injection requested but docker control is unavailable"
            )
            return

        deadline = time.perf_counter() + max(self.per_run_timeout_seconds, 30.0)
        while time.perf_counter() < deadline:
            if self._current_run_ids():
                break
            time.sleep(0.2)
        if not self._current_run_ids():
            notes.append(
                f"failure plan skipped because no runs were created for service {failure_plan.service}"
            )
            return

        time.sleep(max(failure_plan.trigger_delay_seconds, 0.0))
        notes.append(f"injecting {failure_plan.action} on {failure_plan.service}")
        if failure_plan.action == "stop":
            self.docker.stop(failure_plan.service)
        elif failure_plan.action == "restart":
            self.docker.restart(failure_plan.service)
        else:
            raise RuntimeError(f"unsupported failure action: {failure_plan.action}")

        if (
            failure_plan.restart_after_seconds is not None
            and failure_plan.action == "stop"
        ):
            time.sleep(max(failure_plan.restart_after_seconds, 0.0))
            self.docker.start(failure_plan.service)
            notes.append(f"restarted {failure_plan.service} after controlled stop")

    def simulate_websocket_reconnect_storm(
        self,
        *,
        records: list[RunRecord],
        reconnects_per_run: int,
        notes: list[str],
    ) -> None:
        if reconnects_per_run <= 0:
            return
        try:
            import websocket  # type: ignore[import-not-found]
        except Exception:
            notes.append(
                "websocket reconnect storm skipped because websocket-client is not installed"
            )
            return
        websocket_base = (self.websocket_base_url or self.client.base_url).rstrip("/")
        websocket_base = websocket_base.replace("https://", "wss://").replace(
            "http://", "ws://"
        )
        for record in records:
            if not record.run_id or record.status != "success":
                continue
            client = self.clients[record.tenant_slot % max(len(self.clients), 1)]
            for _ in range(reconnects_per_run):
                try:
                    ticket_payload = client.request(
                        "POST", "/api/ws-ticket", timeout=10.0
                    )
                    ticket = str(
                        deep_get(ticket_payload, "data", "ticket", default="") or ""
                    )
                    if not ticket:
                        notes.append(
                            f"websocket reconnect skipped for {record.run_id}: no ticket"
                        )
                        continue
                    query = urllib.parse.urlencode(
                        {
                            "ticket": ticket,
                            "event_level": "default",
                            "last_seen_state_version": "0",
                        }
                    )
                    ws = websocket.create_connection(
                        f"{websocket_base}/ws/runs/{urllib.parse.quote(record.run_id)}/?{query}",
                        timeout=5,
                    )
                    try:
                        ws.recv()
                    finally:
                        ws.close()
                    record.websocket_reconnects += 1
                except Exception as exc:  # noqa: BLE001
                    notes.append(
                        f"websocket reconnect failed for {record.run_id}: {exc}"
                    )
                    break

    def simulate_duplicate_event_storm(
        self,
        *,
        records: list[RunRecord],
        attempts_per_run: int,
        notes: list[str],
    ) -> None:
        if attempts_per_run <= 0:
            return
        if not self.engine_callback_secret:
            notes.append(
                "duplicate event storm skipped because no engine callback secret was provided"
            )
            return
        for record in records:
            if not record.run_id or record.status != "success":
                continue
            client = self.clients[record.tenant_slot % max(len(self.clients), 1)]
            detail_payload, status_code, error = client.try_request(
                "GET",
                f"/api/runs/{record.run_id}",
                timeout=10.0,
            )
            if status_code != 200 or not detail_payload:
                notes.append(
                    f"duplicate event skipped for {record.run_id}: {error or status_code}"
                )
                continue
            detail = deep_get(detail_payload, "data", default={}) or {}
            tenant_id = str(
                detail.get("organization_id")
                or detail.get("tenant_id")
                or deep_get(detail, "organization", "id", default="")
                or ""
            )
            if not tenant_id:
                notes.append(
                    f"duplicate event skipped for {record.run_id}: tenant id unavailable"
                )
                continue
            event_id = f"stress-duplicate-{record.run_id}"
            event = {
                "event_id": event_id,
                "run_id": record.run_id,
                "tenant_id": tenant_id,
                "type": "node_stream_chunk",
                "timestamp": int(time.time() * 1000),
                "node_id": "stress_duplicate_event",
                "node_type": "observability",
                "attempt": 1,
                "output": {
                    "chunk": "duplicate storm payload",
                    "chunk_index": 0,
                },
            }
            body = json.dumps(event, sort_keys=True).encode("utf-8")
            for attempt in range(attempts_per_run):
                timestamp_ms = str(int(time.time() * 1000) + attempt)
                signature = _build_callback_signature(
                    secret=self.engine_callback_secret,
                    timestamp_ms=timestamp_ms,
                    body=body,
                )
                request = urllib.request.Request(
                    self.client.base_url + "/api/runs/engine-events",
                    data=body,
                    headers={
                        "Accept": "application/json",
                        "Content-Type": "application/json",
                        "X-Forgegraph-Timestamp": timestamp_ms,
                        "X-Forgegraph-Signature": signature,
                    },
                    method="POST",
                )
                try:
                    with urllib.request.urlopen(request, timeout=10.0) as response:
                        if response.status < 500:
                            record.duplicate_event_attempts += 1
                except Exception as exc:  # noqa: BLE001
                    notes.append(
                        f"duplicate event attempt failed for {record.run_id}: {exc}"
                    )
                    break

    def compute_metrics(
        self,
        records: list[RunRecord],
        *,
        metrics_before: dict[str, Any],
        metrics_after: dict[str, Any],
    ) -> ScenarioMetrics:
        latencies = [
            float(record.latency_ms) for record in records if record.latency_ms >= 0
        ]
        success_count = sum(1 for record in records if record.status == "success")
        failed_count = sum(1 for record in records if record.status != "success")
        error_types = Counter(
            record.error_type for record in records if record.error_type
        )
        queue_backlogs = [
            int(record.queue_backlog_size)
            for record in records
            if record.queue_backlog_size is not None
        ]
        runtime_backlogs = [
            int(record.redis_backlog)
            for record in records
            if record.redis_backlog is not None
        ]
        runtime_lags = [
            int(record.redis_lag) for record in records if record.redis_lag is not None
        ]
        queue_max_depth_target = metric_int(
            metrics_after, "slo", "queue_max_depth_target"
        )
        max_queue_backlog = max(queue_backlogs, default=None)
        api_p95 = metric_float(metrics_after, "api", "latency_ms_p95")
        api_p95_target = metric_float(metrics_after, "slo", "api_p95_latency_ms_target")
        projection_lag_p95 = metric_first_float(
            metrics_after,
            [
                ("projection", "lag_ms_p95"),
                ("projections", "lag_ms_p95"),
                ("system_state", "projection_lag_ms_p95"),
                ("system_state", "projection_lag_ms"),
            ],
        )
        event_ingestion_p95 = metric_first_float(
            metrics_after,
            [
                ("events", "ingestion_latency_ms_p95"),
                ("event_ingestion", "latency_ms_p95"),
                ("runtime_transport", "ingestion_latency_ms_p95"),
            ],
        )
        ws_send_p95 = metric_float(metrics_after, "websocket", "send_latency_ms_p95")
        ws_send_p95_target = metric_float(
            metrics_after,
            "slo",
            "websocket_send_p95_latency_ms_target",
        )
        runtime_dead_letters = metric_delta(
            metrics_before,
            metrics_after,
            "runtime_transport",
            "dead_lettered_total",
        )
        event_dead_letters = metric_delta(
            metrics_before,
            metrics_after,
            "events",
            "dead_lettered_total",
        )
        total_dead_letters = (runtime_dead_letters or 0) + (event_dead_letters or 0)
        dead_letter_metrics_available = (
            runtime_dead_letters is not None or event_dead_letters is not None
        )
        total_runs = len(records)
        return ScenarioMetrics(
            total_runs=total_runs,
            successful_runs=success_count,
            failed_runs=failed_count,
            avg_latency_ms=(sum(latencies) / len(latencies)) if latencies else None,
            max_latency_ms=max((int(value) for value in latencies), default=None),
            latency_p95_ms=percentile(latencies, 0.95),
            timeouts=sum(1 for record in records if record.error_type == "timeout"),
            retry_count=sum(record.node_retry_count for record in records),
            duplicate_node_execution_count=sum(
                1 for record in records if record.duplicate_node_execution
            ),
            error_types=dict(error_types),
            max_queue_backlog=max_queue_backlog,
            max_runtime_backlog=max(runtime_backlogs, default=None),
            max_runtime_lag=max(runtime_lags, default=None),
            backend_api_latency_p95_ms=api_p95,
            websocket_send_latency_p95_ms=ws_send_p95,
            backend_api_latency_within_target=(
                None
                if api_p95 is None or api_p95_target is None
                else api_p95 <= api_p95_target
            ),
            websocket_send_latency_within_target=(
                None
                if ws_send_p95 is None or ws_send_p95_target is None
                else ws_send_p95 <= ws_send_p95_target
            ),
            websocket_messages_dropped_delta=metric_delta(
                metrics_before,
                metrics_after,
                "websocket",
                "messages_dropped_total",
            ),
            runtime_dead_letter_delta=runtime_dead_letters,
            queue_bounded=(
                None
                if max_queue_backlog is None or queue_max_depth_target is None
                else max_queue_backlog <= queue_max_depth_target
            ),
            success_rate=(success_count / total_runs) if total_runs else None,
            dead_letter_rate=(
                (total_dead_letters / total_runs)
                if total_runs and dead_letter_metrics_available
                else None
            ),
            event_dead_letter_delta=event_dead_letters,
            projection_lag_p95_ms=projection_lag_p95,
            event_ingestion_latency_p95_ms=event_ingestion_p95,
            tenant_slots=len({record.tenant_slot for record in records})
            if records
            else 0,
            decision_count=sum(record.decision_count or 0 for record in records),
            memory_write_count=sum(
                record.memory_write_count or 0 for record in records
            ),
            cost_usd_total=sum(record.cost_usd or 0.0 for record in records),
            websocket_reconnects=sum(record.websocket_reconnects for record in records),
            duplicate_event_attempts=sum(
                record.duplicate_event_attempts for record in records
            ),
        )

    def analyze_scenario(
        self,
        *,
        scenario: str,
        concurrency_levels: list[int],
        records: list[RunRecord],
        failure_plan: FailurePlan | None,
    ) -> FailureAnalysis:
        first_failure = next(
            (record for record in records if record.status != "success"), None
        )
        breaking_point_value: str
        if first_failure is None:
            breaking_point_value = (
                f"not observed up to concurrency {max(concurrency_levels)}"
            )
        else:
            breaking_point_value = f"concurrency {first_failure.concurrency}"

        if (
            failure_plan
            and any(record.status == "success" for record in records)
            and any(record.recovery_state for record in records)
        ):
            behavior = "recovers"
        elif first_failure and all(record.status != "success" for record in records):
            behavior = "crashes"
        elif first_failure and any(
            (record.redis_backlog or 0) > 0 or record.error_type == "timeout"
            for record in records
        ):
            behavior = "stalls"
        else:
            behavior = "degrades"

        data_integrity = "safe"
        if any(record.duplicate_node_execution for record in records):
            data_integrity = "risk"

        return FailureAnalysis(
            scenario=scenario,
            breaking_point=breaking_point_value,
            first_failure_type=first_failure.error_type if first_failure else "none",
            system_behavior=behavior,
            data_integrity=data_integrity,
        )

    def write_scenario_artifacts(self, result: ScenarioResult) -> None:
        scenario_dir = self.output_dir / result.scenario
        scenario_dir.mkdir(parents=True, exist_ok=True)

        runs_path = scenario_dir / "runs.jsonl"
        with runs_path.open("w", encoding="utf-8") as handle:
            for record in result.records:
                handle.write(json.dumps(asdict(record), sort_keys=True) + "\n")

        summary_path = scenario_dir / "summary.json"
        summary_payload = {
            "scenario": result.scenario,
            "started_at": result.started_at,
            "completed_at": result.completed_at,
            "concurrency_levels": result.concurrency_levels,
            "runs_per_level": result.runs_per_level,
            "duration_seconds": result.duration_seconds,
            "capacity_gate": result.capacity_gate,
            "requested_features": result.requested_features,
            "metrics_before": result.metrics_before,
            "metrics_after": result.metrics_after,
            "metrics": asdict(result.metrics),
            "analysis": asdict(result.analysis),
            "notes": result.notes,
        }
        summary_path.write_text(
            json.dumps(summary_payload, indent=2, sort_keys=True), encoding="utf-8"
        )

    def run_scenario(
        self,
        *,
        scenario: str,
        concurrency_levels: list[int],
        runs_per_level: int,
        request_timeout_seconds: float,
        failure_plan: FailurePlan | None = None,
        duration_seconds: float | None = None,
        capacity_gate: str | None = None,
    ) -> ScenarioResult:
        started_at = iso_now()
        self._started_run_ids = []
        notes: list[str] = []
        if scenario == "synthetic-no-llm-500":
            notes.append(
                "Use only with an output-only deterministic graph; this separates engine/backend throughput from LLM capacity."
            )
        elif scenario == "controlled-llm-latency":
            notes.append(
                "Uses fake/chaos LLM latency and queue controls to measure backpressure separately from scheduler throughput."
            )
        elif scenario == "real-provider-capacity":
            notes.append(
                "Cost-bearing provider scenario; use realistic model, cost accounting, memory writes, and WebSocket observers."
            )
        elif scenario.startswith("llm-degradation"):
            notes.append("LLM throttling/backpressure scenario enabled.")
        metrics_before = self.fetch_metrics_summary()

        injector: threading.Thread | None = None
        injector_error: list[str] = []
        if failure_plan is not None:

            def _inject() -> None:
                try:
                    self.execute_failure_plan(failure_plan, notes)
                except Exception as exc:  # noqa: BLE001
                    injector_error.append(str(exc))

            injector = threading.Thread(target=_inject, daemon=True)
            injector.start()

        records: list[RunRecord] = []
        sequence = 0
        for concurrency in concurrency_levels:
            level_started = time.perf_counter()
            level_records_started = 0
            while True:
                batch_size = (
                    concurrency if duration_seconds is not None else runs_per_level
                )
                with ThreadPoolExecutor(max_workers=concurrency) as executor:
                    futures = []
                    for _ in range(batch_size):
                        futures.append(
                            executor.submit(
                                self.run_single,
                                scenario=scenario,
                                concurrency=concurrency,
                                request_timeout_seconds=request_timeout_seconds,
                                sequence=sequence,
                            )
                        )
                        sequence += 1
                    level_records_started += batch_size
                    for future in as_completed(futures):
                        records.append(future.result())
                if duration_seconds is None:
                    break
                elapsed = time.perf_counter() - level_started
                if (
                    elapsed >= duration_seconds
                    and level_records_started >= runs_per_level
                ):
                    break

        if injector is not None:
            injector.join(timeout=max(self.per_run_timeout_seconds, 30.0))
        if injector_error:
            notes.extend(
                f"failure injector error: {message}" for message in injector_error
            )

        if self.requested_features.get("ws_reconnects"):
            self.simulate_websocket_reconnect_storm(
                records=records,
                reconnects_per_run=1,
                notes=notes,
            )
        if self.requested_features.get("duplicate_events"):
            self.simulate_duplicate_event_storm(
                records=records,
                attempts_per_run=2,
                notes=notes,
            )

        metrics_after = self.fetch_metrics_summary()
        metrics = self.compute_metrics(
            records,
            metrics_before=metrics_before,
            metrics_after=metrics_after,
        )
        analysis = self.analyze_scenario(
            scenario=scenario,
            concurrency_levels=concurrency_levels,
            records=records,
            failure_plan=failure_plan,
        )
        result = ScenarioResult(
            scenario=scenario,
            started_at=started_at,
            completed_at=iso_now(),
            concurrency_levels=concurrency_levels,
            runs_per_level=runs_per_level,
            duration_seconds=duration_seconds,
            capacity_gate=capacity_gate,
            requested_features=dict(self.requested_features),
            records=records,
            metrics=metrics,
            analysis=analysis,
            metrics_before=metrics_before,
            metrics_after=metrics_after,
            notes=notes,
        )
        self.write_scenario_artifacts(result)
        return result


def aggregate_phase3_gate_result(
    results: list[ScenarioResult],
    *,
    capacity_gate: str | None,
) -> ScenarioResult | None:
    if not results or not capacity_gate:
        return None
    if len(results) == 1:
        return results[0]

    records = [record for result in results for record in result.records]
    concurrency_levels = metrics_by_concurrency(results)
    metrics = aggregate_phase3_metrics(results, records)
    first_failure = next(
        (record for record in records if record.status != "success"), None
    )
    failure_injection_observed = any(
        "injecting " in note for result in results for note in result.notes
    )
    requested_features = {
        key: any(result.requested_features.get(key, False) for result in results)
        for key in {
            "decisions",
            "memory_writes",
            "accounting",
            "retries",
            "llm_throttling",
            "ws_reconnects",
            "duplicate_events",
        }
    }
    notes = [
        f"{result.scenario}: {note}" for result in results for note in result.notes
    ]
    return ScenarioResult(
        scenario=f"phase3-gate-{capacity_gate}",
        started_at=min(result.started_at for result in results),
        completed_at=max(result.completed_at for result in results),
        concurrency_levels=concurrency_levels,
        runs_per_level=sum(result.runs_per_level for result in results),
        duration_seconds=max(
            (
                result.duration_seconds
                for result in results
                if result.duration_seconds is not None
            ),
            default=None,
        ),
        capacity_gate=capacity_gate,
        requested_features=requested_features,
        records=records,
        metrics=metrics,
        analysis=FailureAnalysis(
            scenario=f"phase3-gate-{capacity_gate}",
            breaking_point=(
                f"concurrency {first_failure.concurrency}"
                if first_failure
                else f"not observed up to concurrency {max(concurrency_levels, default=0)}"
            ),
            first_failure_type=first_failure.error_type if first_failure else "none",
            system_behavior="recovers" if failure_injection_observed else "degrades",
            data_integrity="risk" if metrics.duplicate_node_execution_count else "safe",
        ),
        metrics_before=results[0].metrics_before,
        metrics_after=results[-1].metrics_after,
        notes=notes,
    )


def aggregate_phase3_metrics(
    results: list[ScenarioResult],
    records: list[RunRecord],
) -> ScenarioMetrics:
    latencies = [
        float(record.latency_ms) for record in records if record.latency_ms >= 0
    ]
    success_count = sum(result.metrics.successful_runs for result in results)
    failed_count = sum(result.metrics.failed_runs for result in results)
    error_types: Counter[str] = Counter()
    for result in results:
        error_types.update(result.metrics.error_types)
    runtime_dead_letters = _sum_optional_int(
        result.metrics.runtime_dead_letter_delta for result in results
    )
    event_dead_letters = _sum_optional_int(
        result.metrics.event_dead_letter_delta for result in results
    )
    total_dead_letters = (runtime_dead_letters or 0) + (event_dead_letters or 0)
    dead_letter_metrics_available = (
        runtime_dead_letters is not None or event_dead_letters is not None
    )
    total_runs = sum(result.metrics.total_runs for result in results)
    return ScenarioMetrics(
        total_runs=total_runs,
        successful_runs=success_count,
        failed_runs=failed_count,
        avg_latency_ms=(sum(latencies) / len(latencies)) if latencies else None,
        max_latency_ms=max((int(value) for value in latencies), default=None),
        latency_p95_ms=percentile(latencies, 0.95),
        timeouts=sum(result.metrics.timeouts for result in results),
        retry_count=sum(result.metrics.retry_count for result in results),
        duplicate_node_execution_count=sum(
            result.metrics.duplicate_node_execution_count for result in results
        ),
        error_types=dict(error_types),
        max_queue_backlog=_max_optional_int(
            result.metrics.max_queue_backlog for result in results
        ),
        max_runtime_backlog=_max_optional_int(
            result.metrics.max_runtime_backlog for result in results
        ),
        max_runtime_lag=_max_optional_int(
            result.metrics.max_runtime_lag for result in results
        ),
        backend_api_latency_p95_ms=_max_optional_float(
            result.metrics.backend_api_latency_p95_ms for result in results
        ),
        websocket_send_latency_p95_ms=_max_optional_float(
            result.metrics.websocket_send_latency_p95_ms for result in results
        ),
        backend_api_latency_within_target=_all_known_true(
            result.metrics.backend_api_latency_within_target for result in results
        ),
        websocket_send_latency_within_target=_all_known_true(
            result.metrics.websocket_send_latency_within_target for result in results
        ),
        websocket_messages_dropped_delta=_sum_optional_int(
            result.metrics.websocket_messages_dropped_delta for result in results
        ),
        runtime_dead_letter_delta=runtime_dead_letters,
        queue_bounded=_all_known_true(
            result.metrics.queue_bounded for result in results
        ),
        success_rate=(success_count / total_runs) if total_runs else None,
        dead_letter_rate=(
            (total_dead_letters / total_runs)
            if total_runs and dead_letter_metrics_available
            else None
        ),
        event_dead_letter_delta=event_dead_letters,
        projection_lag_p95_ms=_max_optional_float(
            result.metrics.projection_lag_p95_ms for result in results
        ),
        event_ingestion_latency_p95_ms=_max_optional_float(
            result.metrics.event_ingestion_latency_p95_ms for result in results
        ),
        tenant_slots=(
            len({record.tenant_slot for record in records})
            if records
            else max((result.metrics.tenant_slots for result in results), default=0)
        ),
        decision_count=sum(result.metrics.decision_count for result in results),
        memory_write_count=sum(result.metrics.memory_write_count for result in results),
        cost_usd_total=sum(result.metrics.cost_usd_total for result in results),
        websocket_reconnects=sum(
            result.metrics.websocket_reconnects for result in results
        ),
        duplicate_event_attempts=sum(
            result.metrics.duplicate_event_attempts for result in results
        ),
    )


def evaluate_phase3_gate(
    result: ScenarioResult, *, tenant_client_count: int
) -> Phase3GateEvaluation | None:
    if not result.capacity_gate:
        return None
    gate = result.capacity_gate.upper()
    spec = PHASE3_CAPACITY_GATES[gate]
    metrics = result.metrics
    requirements: dict[str, bool] = {}
    reasons: list[str] = []

    def require(name: str, passed: bool, reason: str) -> None:
        requirements[name] = bool(passed)
        if not passed:
            reasons.append(reason)

    max_concurrency = max(result.concurrency_levels, default=0)
    observed_duration = _elapsed_seconds(result.started_at, result.completed_at)
    require(
        "concurrency",
        max_concurrency >= int(spec["concurrent_agents"]),
        f"observed concurrency {max_concurrency}, required {spec['concurrent_agents']}",
    )
    require(
        "duration",
        observed_duration >= float(spec["duration_seconds"]),
        f"observed duration {round(observed_duration, 2)}s, required {spec['duration_seconds']}s",
    )
    required_tenants = int(spec.get("tenant_count") or 1)
    require(
        "tenant_count",
        tenant_client_count >= required_tenants
        and metrics.tenant_slots >= min(required_tenants, tenant_client_count),
        f"observed {metrics.tenant_slots} tenant slots from {tenant_client_count} clients, required {required_tenants}",
    )
    require(
        "successful_runs",
        metrics.failed_runs == 0,
        f"{metrics.failed_runs} run(s) failed",
    )
    require(
        "zero_duplicate_node_execution",
        metrics.duplicate_node_execution_count == 0,
        f"{metrics.duplicate_node_execution_count} duplicate node execution(s) observed",
    )
    max_dead_letter_rate = spec.get("max_dead_letter_rate")
    if max_dead_letter_rate is not None:
        require(
            "dead_letter_rate",
            metrics.dead_letter_rate is not None
            and metrics.dead_letter_rate <= float(max_dead_letter_rate),
            f"dead-letter rate {metrics.dead_letter_rate} exceeds {max_dead_letter_rate}",
        )
    max_api = spec.get("max_backend_api_p95_ms")
    if max_api is not None:
        require(
            "backend_api_p95",
            metrics.backend_api_latency_p95_ms is not None
            and metrics.backend_api_latency_p95_ms <= float(max_api),
            f"backend API p95 {metrics.backend_api_latency_p95_ms}ms exceeds {max_api}ms or is missing",
        )
    max_ingestion = spec.get("max_event_ingestion_p95_ms")
    if max_ingestion is not None:
        require(
            "event_ingestion_p95",
            metrics.event_ingestion_latency_p95_ms is not None
            and metrics.event_ingestion_latency_p95_ms <= float(max_ingestion),
            f"event ingestion p95 {metrics.event_ingestion_latency_p95_ms}ms exceeds {max_ingestion}ms or is missing",
        )
    max_projection = spec.get("max_projection_lag_ms")
    if max_projection is not None:
        require(
            "projection_lag_p95",
            metrics.projection_lag_p95_ms is not None
            and metrics.projection_lag_p95_ms <= float(max_projection),
            f"projection lag p95 {metrics.projection_lag_p95_ms}ms exceeds {max_projection}ms or is missing",
        )
    max_ws = spec.get("max_websocket_p95_ms")
    if max_ws is not None:
        require(
            "websocket_p95",
            metrics.websocket_send_latency_p95_ms is not None
            and metrics.websocket_send_latency_p95_ms <= float(max_ws),
            f"websocket p95 {metrics.websocket_send_latency_p95_ms}ms exceeds {max_ws}ms or is missing",
        )
    _require_feature(
        requirements=requirements,
        reasons=reasons,
        spec=spec,
        result=result,
        spec_key="requires_hitl",
        feature_key="decisions",
        metric_count=metrics.decision_count,
        label="HITL decisions",
    )
    _require_feature(
        requirements=requirements,
        reasons=reasons,
        spec=spec,
        result=result,
        spec_key="requires_memory_writes",
        feature_key="memory_writes",
        metric_count=metrics.memory_write_count,
        label="memory writes",
    )
    _require_feature(
        requirements=requirements,
        reasons=reasons,
        spec=spec,
        result=result,
        spec_key="requires_accounting",
        feature_key="accounting",
        metric_count=1 if metrics.cost_usd_total > 0 else 0,
        label="accounting writes",
    )
    _require_feature(
        requirements=requirements,
        reasons=reasons,
        spec=spec,
        result=result,
        spec_key="requires_retries",
        feature_key="retries",
        metric_count=metrics.retry_count,
        label="runtime retries",
    )
    if spec.get("requires_llm_throttling"):
        require(
            "llm_throttling",
            result.requested_features.get("llm_throttling", False)
            and any("llm throttling" in note.lower() for note in result.notes),
            "LLM throttling/backpressure scenario was not observed",
        )
    if spec.get("requires_websocket_reconnect_storm"):
        require(
            "websocket_reconnect_storm",
            result.requested_features.get("ws_reconnects", False)
            and metrics.websocket_reconnects > 0,
            "websocket reconnect storm was not observed",
        )
    if spec.get("requires_duplicate_event_storm"):
        require(
            "duplicate_event_storm",
            result.requested_features.get("duplicate_events", False)
            and metrics.duplicate_event_attempts > 0,
            "duplicate event storm was not observed",
        )
    if spec.get("requires_failure_injection"):
        require(
            "failure_injection",
            any("injecting " in note for note in result.notes),
            "required failure injection was not observed",
        )

    return Phase3GateEvaluation(
        gate=gate,
        passed=all(requirements.values()),
        requirements=requirements,
        reasons=reasons,
    )


def write_phase3_gate_report(
    *,
    output_dir: Path,
    result: ScenarioResult,
    evaluation: Phase3GateEvaluation,
    source_results: list[ScenarioResult] | None = None,
) -> None:
    sources = source_results or [result]
    if len(sources) == 1:
        artifact_paths: dict[str, Any] = {
            "summary": f"{sources[0].scenario}/summary.json",
            "runs": f"{sources[0].scenario}/runs.jsonl",
        }
    else:
        artifact_paths = {
            "scenarios": {
                source.scenario: {
                    "summary": f"{source.scenario}/summary.json",
                    "runs": f"{source.scenario}/runs.jsonl",
                }
                for source in sources
            }
        }
    payload = {
        "gate": evaluation.gate,
        "passed": evaluation.passed,
        "requirements": evaluation.requirements,
        "reasons": evaluation.reasons,
        "scenario": result.scenario,
        "started_at": result.started_at,
        "completed_at": result.completed_at,
        "concurrency_levels": result.concurrency_levels,
        "duration_seconds": result.duration_seconds,
        "requested_features": result.requested_features,
        "metrics": asdict(result.metrics),
        "artifact_paths": artifact_paths,
    }
    (output_dir / f"phase3-gate-{evaluation.gate}.json").write_text(
        json.dumps(payload, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    status_value = "PASS" if evaluation.passed else "FAIL"
    lines = [
        f"# Phase 3 Gate {evaluation.gate} Evidence",
        "",
        f"Status: **{status_value}**",
        "",
        f"Scenario: `{result.scenario}`",
        f"Concurrency: `{result.concurrency_levels}`",
        f"Duration target: `{result.duration_seconds}` seconds",
        "",
        "## Requirements",
        "",
    ]
    for key, passed in evaluation.requirements.items():
        marker = "PASS" if passed else "FAIL"
        lines.append(f"- {marker}: `{key}`")
    if evaluation.reasons:
        lines.extend(["", "## Blocking Reasons", ""])
        lines.extend(f"- {reason}" for reason in evaluation.reasons)
    (output_dir / f"phase3-gate-{evaluation.gate}.md").write_text(
        "\n".join(lines) + "\n",
        encoding="utf-8",
    )


def metrics_by_concurrency(results: list[ScenarioResult]) -> list[int]:
    return sorted(
        {concurrency for result in results for concurrency in result.concurrency_levels}
    )


def _sum_optional_int(values: Any) -> int | None:
    present = [int(value) for value in values if value is not None]
    return sum(present) if present else None


def _max_optional_int(values: Any) -> int | None:
    present = [int(value) for value in values if value is not None]
    return max(present, default=None)


def _max_optional_float(values: Any) -> float | None:
    present = [float(value) for value in values if value is not None]
    return max(present, default=None)


def _all_known_true(values: Any) -> bool | None:
    present = [bool(value) for value in values if value is not None]
    return all(present) if present else None


def _elapsed_seconds(started_at: str, completed_at: str) -> float:
    try:
        started = datetime.fromisoformat(started_at.replace("Z", "+00:00"))
        completed = datetime.fromisoformat(completed_at.replace("Z", "+00:00"))
    except ValueError:
        return 0.0
    return max((completed - started).total_seconds(), 0.0)


def _require_feature(
    *,
    requirements: dict[str, bool],
    reasons: list[str],
    spec: dict[str, Any],
    result: ScenarioResult,
    spec_key: str,
    feature_key: str,
    metric_count: int,
    label: str,
) -> None:
    if not spec.get(spec_key):
        return
    passed = result.requested_features.get(feature_key, False) and metric_count > 0
    requirements[feature_key] = passed
    if not passed:
        reasons.append(f"required {label} were not observed")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="ForgeGraph stress harness")
    parser.add_argument(
        "--base-url", default="http://localhost:8000", help="Backend base URL"
    )
    parser.add_argument(
        "--email", required=True, help="User email for API authentication"
    )
    parser.add_argument(
        "--password", required=True, help="User password for API authentication"
    )
    parser.add_argument(
        "--metrics-email", help="Optional admin email for metrics access"
    )
    parser.add_argument(
        "--metrics-password", help="Optional admin password for metrics access"
    )
    parser.add_argument("--graph-version-id", help="Graph version to execute")
    parser.add_argument(
        "--graph-id", help="Resolve the latest graph version from this graph id"
    )
    parser.add_argument(
        "--scenario",
        choices=SCENARIO_CHOICES,
        default="all",
    )
    parser.add_argument(
        "--capacity-tier",
        choices=sorted(CAPACITY_TIERS),
        help="Use the tier target as default concurrency when --concurrency is omitted.",
    )
    parser.add_argument(
        "--capacity-gate",
        choices=sorted(PHASE3_CAPACITY_GATES),
        help="Evaluate the run against Phase 3 capacity Gate A-E.",
    )
    parser.add_argument("--concurrency", nargs="*", type=int, default=None)
    parser.add_argument(
        "--runs", type=int, default=10, help="Runs per concurrency level"
    )
    parser.add_argument(
        "--duration-seconds",
        type=float,
        default=None,
        help="Run each concurrency level for this duration. Phase 3 gates default to their required duration.",
    )
    parser.add_argument("--request-timeout-seconds", type=float, default=20.0)
    parser.add_argument("--run-timeout-seconds", type=float, default=180.0)
    parser.add_argument("--poll-interval-seconds", type=float, default=2.0)
    parser.add_argument(
        "--output-dir",
        default=str(DEFAULT_OUTPUT_DIR / utc_now().strftime("%Y%m%dT%H%M%SZ")),
    )
    parser.add_argument(
        "--input-json",
        default="{}",
        help="Literal JSON object passed as input_json to each run",
    )
    parser.add_argument("--allow-service-disruption", action="store_true")
    parser.add_argument(
        "--allow-real-provider",
        action="store_true",
        help="Required for real-provider-capacity so cost-bearing provider calls are explicit.",
    )
    parser.add_argument("--llm-chaos-delay-ms", type=int, default=5000)
    parser.add_argument("--llm-mock-delay-ms", type=int, default=1500)
    parser.add_argument("--llm-mock-max-in-flight", type=int, default=4)
    parser.add_argument("--llm-mock-error-mode", default="off")
    parser.add_argument("--llm-max-concurrency", type=int, default=4)
    parser.add_argument("--llm-max-queue-size", type=int, default=32)
    parser.add_argument("--llm-queue-timeout-ms", type=int, default=5000)
    parser.add_argument("--failure-trigger-delay-seconds", type=float, default=5.0)
    parser.add_argument("--failure-restart-after-seconds", type=float, default=10.0)
    parser.add_argument(
        "--tenant-credentials-file",
        help=(
            "Optional JSON file with tenant credentials. Accepts a list or {'tenants': [...]} "
            "where each entry has email/password and optional graph_version_id."
        ),
    )
    parser.add_argument(
        "--websocket-base-url",
        default="",
        help="Override WS base URL for reconnect storms.",
    )
    parser.add_argument(
        "--engine-callback-secret",
        default=os.environ.get("ENGINE_CALLBACK_SECRET", ""),
        help="Secret used to sign duplicate-event storm callbacks.",
    )
    parser.add_argument("--simulate-decisions", action="store_true")
    parser.add_argument("--simulate-memory-writes", action="store_true")
    parser.add_argument("--simulate-accounting", action="store_true")
    parser.add_argument("--simulate-retries", action="store_true")
    parser.add_argument("--simulate-ws-reconnects", action="store_true")
    parser.add_argument("--simulate-duplicate-events", action="store_true")
    parser.add_argument(
        "--docker-compose-file", default=str(ROOT_DIR / "docker-compose.yml")
    )
    parser.add_argument("--env-file", default=str(ROOT_DIR / ".env"))
    return parser.parse_args()


def resolve_graph_version_id(harness: StressHarness, args: argparse.Namespace) -> str:
    if args.graph_version_id:
        return str(args.graph_version_id)
    if args.graph_id:
        return harness.fetch_latest_graph_version(str(args.graph_id))
    if harness.client_graph_version_ids and all(harness.client_graph_version_ids):
        return harness.client_graph_version_ids[0]
    raise SystemExit("either --graph-version-id or --graph-id is required")


def resolve_concurrency_levels(args: argparse.Namespace, *, scenario: str) -> list[int]:
    if args.concurrency:
        return list(args.concurrency)
    if args.capacity_gate:
        return [int(PHASE3_CAPACITY_GATES[args.capacity_gate]["concurrent_agents"])]
    if scenario == "synthetic-no-llm-500":
        return [CAPACITY_TIERS["production-scale"]["max_concurrency"]]
    if args.capacity_tier:
        return [int(CAPACITY_TIERS[args.capacity_tier]["max_concurrency"])]
    return DEFAULT_CONCURRENCY_LEVELS


def resolve_duration_seconds(args: argparse.Namespace) -> float | None:
    if args.duration_seconds is not None:
        return max(float(args.duration_seconds), 0.0)
    if args.capacity_gate:
        return float(PHASE3_CAPACITY_GATES[args.capacity_gate]["duration_seconds"])
    return None


def requested_features_from_args(args: argparse.Namespace) -> dict[str, bool]:
    gate_spec = PHASE3_CAPACITY_GATES.get(str(args.capacity_gate or "").upper(), {})
    return {
        "decisions": bool(args.simulate_decisions or gate_spec.get("requires_hitl")),
        "memory_writes": bool(
            args.simulate_memory_writes or gate_spec.get("requires_memory_writes")
        ),
        "accounting": bool(
            args.simulate_accounting or gate_spec.get("requires_accounting")
        ),
        "retries": bool(args.simulate_retries or gate_spec.get("requires_retries")),
        "llm_throttling": bool(
            gate_spec.get("requires_llm_throttling")
            or args.scenario
            in {
                "all",
                "llm-degradation-delay",
                "llm-degradation-timeout",
                "llm-degradation-unavailable",
                "controlled-llm-latency",
                "real-provider-capacity",
            }
        ),
        "ws_reconnects": bool(
            args.simulate_ws_reconnects
            or gate_spec.get("requires_websocket_reconnect_storm")
        ),
        "duplicate_events": bool(
            args.simulate_duplicate_events
            or gate_spec.get("requires_duplicate_event_storm")
        ),
    }


def load_tenant_clients(
    *,
    base_url: str,
    args: argparse.Namespace,
    primary_client: HttpJsonClient,
) -> tuple[list[HttpJsonClient], list[str]]:
    if not args.tenant_credentials_file:
        return [primary_client], []

    path = Path(args.tenant_credentials_file)
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise SystemExit(
            f"--tenant-credentials-file must contain valid JSON: {exc}"
        ) from exc
    entries = payload.get("tenants") if isinstance(payload, dict) else payload
    if not isinstance(entries, list) or not entries:
        raise SystemExit(
            "--tenant-credentials-file must contain a non-empty tenant list"
        )

    clients: list[HttpJsonClient] = []
    graph_version_ids: list[str] = []
    for index, entry in enumerate(entries):
        if not isinstance(entry, dict):
            raise SystemExit(f"tenant entry {index} must be an object")
        email = str(entry.get("email") or "").strip()
        password = str(entry.get("password") or "").strip()
        if not email or not password:
            raise SystemExit(f"tenant entry {index} requires email and password")
        client = HttpJsonClient(base_url)
        client.login(email, password)
        clients.append(client)
        graph_version_ids.append(str(entry.get("graph_version_id") or "").strip())
    return clients, graph_version_ids


def llm_backpressure_env(
    args: argparse.Namespace, *, mode: str, delay_ms: int
) -> dict[str, str]:
    return {
        "FORGEGRAPH_LLM_CHAOS_MODE": mode,
        "FORGEGRAPH_LLM_CHAOS_DELAY_MS": str(delay_ms),
        "FORGEGRAPH_LLM_CHAOS_ERROR_MESSAGE": f"simulated llm {mode}",
        "ENGINE_LLM_MAX_CONCURRENCY": str(args.llm_max_concurrency),
        "ENGINE_LLM_MAX_QUEUE_SIZE": str(args.llm_max_queue_size),
        "ENGINE_LLM_QUEUE_TIMEOUT_MS": str(args.llm_queue_timeout_ms),
        "PLAYWRIGHT_LLM_MOCK_DELAY_MS": str(args.llm_mock_delay_ms),
        "PLAYWRIGHT_LLM_MOCK_MAX_IN_FLIGHT": str(args.llm_mock_max_in_flight),
        "PLAYWRIGHT_LLM_MOCK_ERROR_MODE": str(args.llm_mock_error_mode),
    }


def require_production_scale_runs_cover_concurrency(
    args: argparse.Namespace,
    *,
    scenario: str,
    concurrency_levels: list[int],
) -> None:
    required_runs = max(concurrency_levels)
    if args.runs >= required_runs:
        return
    raise SystemExit(
        f"{scenario} requires --runs >= {required_runs} so the measured run count "
        "can actually exercise the requested concurrency."
    )


def build_scenario_plan(
    args: argparse.Namespace,
) -> list[tuple[str, list[int], int, FailurePlan | None, dict[str, str] | None]]:
    scenarios: list[
        tuple[str, list[int], int, FailurePlan | None, dict[str, str] | None]
    ] = []
    if args.scenario in {"endpoint-saturation", "all"}:
        concurrency_levels = resolve_concurrency_levels(
            args, scenario="endpoint-saturation"
        )
        scenarios.append(
            ("endpoint-saturation", concurrency_levels, args.runs, None, None)
        )
    if args.scenario in {"engine-concurrency", "all"}:
        concurrency_levels = resolve_concurrency_levels(
            args, scenario="engine-concurrency"
        )
        scenarios.append(
            ("engine-concurrency", concurrency_levels, args.runs, None, None)
        )
    if args.scenario in {"redis-saturation", "all"}:
        concurrency_levels = resolve_concurrency_levels(
            args, scenario="redis-saturation"
        )
        scenarios.append(
            ("redis-saturation", concurrency_levels, args.runs, None, None)
        )
    if args.scenario in {"llm-degradation-delay", "all"}:
        concurrency_levels = resolve_concurrency_levels(
            args, scenario="llm-degradation-delay"
        )
        scenarios.append(
            (
                "llm-degradation-delay",
                concurrency_levels,
                args.runs,
                None,
                llm_backpressure_env(
                    args, mode="delay", delay_ms=args.llm_chaos_delay_ms
                ),
            )
        )
    if args.scenario in {"llm-degradation-timeout", "all"}:
        concurrency_levels = resolve_concurrency_levels(
            args, scenario="llm-degradation-timeout"
        )
        scenarios.append(
            (
                "llm-degradation-timeout",
                concurrency_levels,
                args.runs,
                None,
                llm_backpressure_env(
                    args, mode="timeout", delay_ms=args.llm_chaos_delay_ms
                ),
            )
        )
    if args.scenario in {"llm-degradation-unavailable", "all"}:
        concurrency_levels = resolve_concurrency_levels(
            args, scenario="llm-degradation-unavailable"
        )
        scenarios.append(
            (
                "llm-degradation-unavailable",
                concurrency_levels,
                args.runs,
                None,
                llm_backpressure_env(args, mode="unavailable", delay_ms=0),
            )
        )
    if args.scenario in {"failure-injection-engine-stop", "all"}:
        concurrency_levels = resolve_concurrency_levels(
            args, scenario="failure-injection-engine-stop"
        )
        scenarios.append(
            (
                "failure-injection-engine-stop",
                concurrency_levels,
                args.runs,
                FailurePlan(
                    service="engine",
                    action="stop",
                    trigger_delay_seconds=args.failure_trigger_delay_seconds,
                    restart_after_seconds=args.failure_restart_after_seconds,
                ),
                None,
            )
        )
    if args.scenario in {"failure-injection-redis-stop", "all"}:
        concurrency_levels = resolve_concurrency_levels(
            args, scenario="failure-injection-redis-stop"
        )
        scenarios.append(
            (
                "failure-injection-redis-stop",
                concurrency_levels,
                args.runs,
                FailurePlan(
                    service="redis",
                    action="stop",
                    trigger_delay_seconds=args.failure_trigger_delay_seconds,
                    restart_after_seconds=args.failure_restart_after_seconds,
                ),
                None,
            )
        )
    if args.scenario in {"websocket-reconnect-storm", "all"}:
        concurrency_levels = resolve_concurrency_levels(
            args, scenario="websocket-reconnect-storm"
        )
        args.simulate_ws_reconnects = True
        scenarios.append(
            ("websocket-reconnect-storm", concurrency_levels, args.runs, None, None)
        )
    if args.scenario in {"duplicate-event-storm", "all"}:
        concurrency_levels = resolve_concurrency_levels(
            args, scenario="duplicate-event-storm"
        )
        args.simulate_duplicate_events = True
        scenarios.append(
            ("duplicate-event-storm", concurrency_levels, args.runs, None, None)
        )
    if args.scenario == "synthetic-no-llm-500":
        concurrency_levels = resolve_concurrency_levels(
            args, scenario="synthetic-no-llm-500"
        )
        require_production_scale_runs_cover_concurrency(
            args,
            scenario="synthetic-no-llm-500",
            concurrency_levels=concurrency_levels,
        )
        scenarios.append(
            (
                "synthetic-no-llm-500",
                concurrency_levels,
                args.runs,
                None,
                None,
            )
        )
    if args.scenario == "controlled-llm-latency":
        concurrency_levels = resolve_concurrency_levels(
            args, scenario="controlled-llm-latency"
        )
        require_production_scale_runs_cover_concurrency(
            args,
            scenario="controlled-llm-latency",
            concurrency_levels=concurrency_levels,
        )
        scenarios.append(
            (
                "controlled-llm-latency",
                concurrency_levels,
                args.runs,
                None,
                llm_backpressure_env(
                    args, mode="delay", delay_ms=args.llm_mock_delay_ms
                ),
            )
        )
    if args.scenario == "real-provider-capacity":
        concurrency_levels = resolve_concurrency_levels(
            args, scenario="real-provider-capacity"
        )
        require_production_scale_runs_cover_concurrency(
            args,
            scenario="real-provider-capacity",
            concurrency_levels=concurrency_levels,
        )
        scenarios.append(
            (
                "real-provider-capacity",
                concurrency_levels,
                args.runs,
                None,
                None,
            )
        )
    return scenarios


def require_service_disruption_allowed(
    args: argparse.Namespace,
    scenarios: list[
        tuple[str, list[int], int, FailurePlan | None, dict[str, str] | None]
    ],
) -> None:
    needs_disruption = any(
        plan is not None or env_overrides is not None
        for _, _, _, plan, env_overrides in scenarios
    )
    if needs_disruption and not args.allow_service_disruption:
        raise SystemExit(
            "--allow-service-disruption is required for LLM degradation or failure-injection scenarios"
        )
    if (
        any(scenario == "real-provider-capacity" for scenario, *_ in scenarios)
        and not args.allow_real_provider
    ):
        raise SystemExit(
            "--allow-real-provider is required for real-provider-capacity because it may incur provider cost"
        )


def main() -> int:
    args = parse_args()
    try:
        input_payload = json.loads(args.input_json)
    except json.JSONDecodeError as exc:
        raise SystemExit(f"--input-json must be valid JSON: {exc}") from exc
    if not isinstance(input_payload, dict):
        raise SystemExit("--input-json must decode to a JSON object")

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    scenarios = build_scenario_plan(args)
    require_service_disruption_allowed(args, scenarios)
    duration_seconds = resolve_duration_seconds(args)
    requested_features = requested_features_from_args(args)

    client = HttpJsonClient(args.base_url)
    client.login(args.email, args.password)
    tenant_clients, tenant_graph_version_ids = load_tenant_clients(
        base_url=args.base_url,
        args=args,
        primary_client=client,
    )

    metrics_client: HttpJsonClient | None = None
    if args.metrics_email and args.metrics_password:
        metrics_client = HttpJsonClient(args.base_url)
        metrics_client.login(args.metrics_email, args.metrics_password)

    docker = DockerComposeController(
        root_dir=ROOT_DIR,
        compose_file=Path(args.docker_compose_file),
        base_env_file=Path(args.env_file),
    )

    harness = StressHarness(
        client=client,
        metrics_client=metrics_client,
        clients=tenant_clients,
        graph_version_id=args.graph_version_id or "",
        output_dir=output_dir,
        per_run_timeout_seconds=args.run_timeout_seconds,
        poll_interval_seconds=args.poll_interval_seconds,
        docker=docker,
        input_payload=input_payload,
        requested_features=requested_features,
        websocket_base_url=args.websocket_base_url,
        engine_callback_secret=args.engine_callback_secret,
        client_graph_version_ids=tenant_graph_version_ids,
    )
    harness.graph_version_id = resolve_graph_version_id(harness, args)

    manifest: dict[str, Any] = {
        "started_at": iso_now(),
        "base_url": args.base_url,
        "graph_version_id": harness.graph_version_id,
        "output_dir": str(output_dir),
        "capacity_tier": args.capacity_tier,
        "capacity_gate": args.capacity_gate,
        "phase3_capacity_gates": PHASE3_CAPACITY_GATES,
        "duration_seconds": duration_seconds,
        "tenant_client_count": len(tenant_clients),
        "requested_features": requested_features,
        "capacity_tiers": CAPACITY_TIERS,
        "phase3_notice": (
            "Synthetic and CI load smokes are regression evidence only. "
            "Production-scale 500+ must not be marketed until Phase 3 Gate E "
            "passes three times with real acceptance metrics."
        ),
        "results": [],
        "gate_evaluations": [],
    }

    scenario_results: list[ScenarioResult] = []
    for (
        scenario,
        concurrency_levels,
        runs_per_level,
        failure_plan,
        env_overrides,
    ) in scenarios:
        if env_overrides:
            docker.recreate_with_overrides("engine", env_overrides)
            time.sleep(3)
        try:
            result = harness.run_scenario(
                scenario=scenario,
                concurrency_levels=concurrency_levels,
                runs_per_level=runs_per_level,
                request_timeout_seconds=args.request_timeout_seconds,
                failure_plan=failure_plan,
                duration_seconds=duration_seconds,
                capacity_gate=args.capacity_gate,
            )
        finally:
            if env_overrides:
                docker.recreate_with_overrides(
                    "engine",
                    {
                        "FORGEGRAPH_LLM_CHAOS_MODE": "off",
                        "FORGEGRAPH_LLM_CHAOS_DELAY_MS": "0",
                        "FORGEGRAPH_LLM_CHAOS_ERROR_MESSAGE": "",
                    },
                )
                time.sleep(3)
        scenario_results.append(result)
        manifest["results"].append(
            {
                "scenario": scenario,
                "metrics": asdict(result.metrics),
                "analysis": asdict(result.analysis),
            }
        )

    gate_result = aggregate_phase3_gate_result(
        scenario_results,
        capacity_gate=args.capacity_gate,
    )
    if gate_result is not None:
        gate_evaluation = evaluate_phase3_gate(
            gate_result,
            tenant_client_count=len(tenant_clients),
        )
        if gate_evaluation is not None:
            write_phase3_gate_report(
                output_dir=output_dir,
                result=gate_result,
                evaluation=gate_evaluation,
                source_results=scenario_results,
            )
            manifest["gate_evaluations"].append(asdict(gate_evaluation))

    manifest["completed_at"] = iso_now()
    (output_dir / "manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8"
    )
    print(json.dumps(manifest, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
