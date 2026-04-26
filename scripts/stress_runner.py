#!/usr/bin/env python3
"""Controlled ForgeGraph stress harness.

This script creates real runs through the backend API, waits on backend-owned
state for completion, captures queue/runtime transport metrics, optionally
injects infrastructure failures through Docker, and writes reproducible JSON
artifacts under logs/stress/.
"""

from __future__ import annotations

import argparse
import json
import os
import socket
import subprocess
import sys
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
ROOT_DIR = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT_DIR = ROOT_DIR / "logs" / "stress"


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def iso_now() -> str:
    return utc_now().isoformat()


def classify_error(message: str, *, http_status: int | None = None) -> str:
    normalized = (message or "").strip().lower()
    if http_status == 429 or "rate limit" in normalized:
        return "rate_limit"
    if http_status in {502, 503, 504}:
        return "connection"
    if "timeout" in normalized or "deadline exceeded" in normalized:
        return "timeout"
    if any(token in normalized for token in ("connection refused", "connection reset", "temporarily unavailable", "network", "unavailable")):
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
                error_message = deep_get(parsed, "error", "message") or deep_get(parsed, "detail")
                if error_message:
                    message = str(error_message)
                if exc.code == 401 and auth and retry_auth and self._email and self._password:
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
                if exc.code == 401 and auth and retry_auth and self._email and self._password:
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
    def __init__(self, *, root_dir: Path, compose_file: Path | None = None, base_env_file: Path | None = None) -> None:
        self.root_dir = root_dir
        self.compose_file = compose_file or (root_dir / "docker-compose.yml")
        self.base_env_file = base_env_file or (root_dir / ".env")

    def run(self, args: list[str], *, env_file: Path | None = None) -> None:
        command = ["docker", "compose", "-f", str(self.compose_file)]
        if env_file is not None:
            command.extend(["--env-file", str(env_file)])
        command.extend(args)
        subprocess.run(command, cwd=self.root_dir, check=True, capture_output=True, text=True)

    def stop(self, service: str) -> None:
        self.run(["stop", service])

    def start(self, service: str, *, env_file: Path | None = None, recreate: bool = False) -> None:
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
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", suffix=".env", delete=False) as handle:
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
        graph_version_id: str,
        output_dir: Path,
        per_run_timeout_seconds: float,
        poll_interval_seconds: float,
        metrics_client: HttpJsonClient | None = None,
        docker: DockerComposeController | None = None,
        input_payload: dict[str, Any] | None = None,
    ) -> None:
        self.client = client
        self.metrics_client = metrics_client or client
        self.graph_version_id = graph_version_id
        self.output_dir = output_dir
        self.per_run_timeout_seconds = per_run_timeout_seconds
        self.poll_interval_seconds = poll_interval_seconds
        self.docker = docker
        self.input_payload = input_payload or {}
        self._started_run_ids: list[str] = []
        self._run_ids_lock = threading.Lock()

    def fetch_metrics_summary(self) -> dict[str, Any]:
        payload, status_code, error = self.metrics_client.try_request("GET", "/api/metrics/summary")
        if status_code == 200 and payload:
            return deep_get(payload, "data", default={}) or {}
        if error:
            return {"error": error, "status_code": status_code}
        return {}

    def fetch_latest_graph_version(self, graph_id: str) -> str:
        payload = self.client.request("GET", f"/api/graphs/{graph_id}/versions/latest")
        version_id = str(deep_get(payload, "data", "id", default="") or "").strip()
        if not version_id:
            raise RuntimeError(f"could not resolve latest graph version for graph {graph_id}")
        return version_id

    def _note_run_started(self, run_id: str) -> None:
        with self._run_ids_lock:
            self._started_run_ids.append(run_id)

    def _current_run_ids(self) -> list[str]:
        with self._run_ids_lock:
            return list(self._started_run_ids)

    def start_run(self, *, scenario: str, concurrency: int, request_timeout_seconds: float) -> tuple[dict[str, Any] | None, int | None, str | None, int]:
        start_monotonic = time.perf_counter()
        payload, status_code, error = self.client.try_request(
            "POST",
            "/api/runs",
            body={
                "graph_version_id": self.graph_version_id,
                "input_json": self.input_payload,
            },
            timeout=request_timeout_seconds,
        )
        latency_ms = int((time.perf_counter() - start_monotonic) * 1000)
        return payload, status_code, error, latency_ms

    def wait_for_terminal(self, run_id: str) -> tuple[dict[str, Any] | None, str | None]:
        deadline = time.perf_counter() + self.per_run_timeout_seconds
        last_error: str | None = None
        while time.perf_counter() < deadline:
            payload, status_code, error = self.client.try_request(
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

    def run_single(self, *, scenario: str, concurrency: int, request_timeout_seconds: float) -> RunRecord:
        started_at = iso_now()
        payload, status_code, error, request_latency_ms = self.start_run(
            scenario=scenario,
            concurrency=concurrency,
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
                run_id="",
                start_time=started_at,
                end_time=end_time,
                latency_ms=request_latency_ms,
                status="failure",
                error=error_message,
                error_type=classify_error(error_message, http_status=status_code),
                http_status=status_code,
                redis_lag=deep_get(metrics_snapshot, "runtime_transport", "stream_lag"),
                redis_backlog=deep_get(metrics_snapshot, "runtime_transport", "stream_backlog"),
                queue_backlog_size=deep_get(metrics_snapshot, "queue", "total_depth"),
            )

        self._note_run_started(run_id)
        detail, wait_error = self.wait_for_terminal(run_id)
        end_time = iso_now()
        final_metrics = self.fetch_metrics_summary()

        if detail is None:
            error_message = wait_error or "timed out waiting for backend state"
            return RunRecord(
                scenario=scenario,
                concurrency=concurrency,
                run_id=run_id,
                start_time=started_at,
                end_time=end_time,
                latency_ms=int((datetime.fromisoformat(end_time) - datetime.fromisoformat(started_at)).total_seconds() * 1000),
                status="failure",
                error=error_message,
                error_type=classify_error(error_message),
                queue_status=str(created.get("queue_status") or "") or None,
                queue_attempts=created.get("queue_attempts"),
                redis_lag=deep_get(final_metrics, "runtime_transport", "stream_lag"),
                redis_backlog=deep_get(final_metrics, "runtime_transport", "stream_backlog"),
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
        retry_count = sum(max(attempts - 1, 0) for attempts in attempts_by_node.values())

        status_value = str(detail.get("status") or "").strip().lower()
        error_message = str(detail.get("error_message") or "").strip()
        run_latency_ms = request_latency_ms
        started_ts = detail.get("started_at")
        ended_ts = detail.get("ended_at")
        try:
            if started_ts and ended_ts:
                started_dt = datetime.fromisoformat(str(started_ts).replace("Z", "+00:00"))
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
            redis_backlog=deep_get(final_metrics, "runtime_transport", "stream_backlog"),
            queue_backlog_size=deep_get(final_metrics, "queue", "total_depth"),
            last_progress_at=str(detail.get("last_progress_at") or "") or None,
            recovery_state=str(detail.get("recovery_state") or "") or None,
            recovery_reason=str(detail.get("recovery_reason") or "") or None,
        )

    def execute_failure_plan(self, failure_plan: FailurePlan, notes: list[str]) -> None:
        if self.docker is None:
            notes.append("failure injection requested but docker control is unavailable")
            return

        deadline = time.perf_counter() + max(self.per_run_timeout_seconds, 30.0)
        while time.perf_counter() < deadline:
            if self._current_run_ids():
                break
            time.sleep(0.2)
        if not self._current_run_ids():
            notes.append(f"failure plan skipped because no runs were created for service {failure_plan.service}")
            return

        time.sleep(max(failure_plan.trigger_delay_seconds, 0.0))
        notes.append(f"injecting {failure_plan.action} on {failure_plan.service}")
        if failure_plan.action == "stop":
            self.docker.stop(failure_plan.service)
        elif failure_plan.action == "restart":
            self.docker.restart(failure_plan.service)
        else:
            raise RuntimeError(f"unsupported failure action: {failure_plan.action}")

        if failure_plan.restart_after_seconds is not None and failure_plan.action == "stop":
            time.sleep(max(failure_plan.restart_after_seconds, 0.0))
            self.docker.start(failure_plan.service)
            notes.append(f"restarted {failure_plan.service} after controlled stop")

    def compute_metrics(self, records: list[RunRecord]) -> ScenarioMetrics:
        latencies = [float(record.latency_ms) for record in records if record.latency_ms >= 0]
        success_count = sum(1 for record in records if record.status == "success")
        failed_count = sum(1 for record in records if record.status != "success")
        error_types = Counter(record.error_type for record in records if record.error_type)
        return ScenarioMetrics(
            total_runs=len(records),
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
        )

    def analyze_scenario(
        self,
        *,
        scenario: str,
        concurrency_levels: list[int],
        records: list[RunRecord],
        failure_plan: FailurePlan | None,
    ) -> FailureAnalysis:
        first_failure = next((record for record in records if record.status != "success"), None)
        breaking_point_value: str
        if first_failure is None:
            breaking_point_value = f"not observed up to concurrency {max(concurrency_levels)}"
        else:
            breaking_point_value = f"concurrency {first_failure.concurrency}"

        if failure_plan and any(record.status == "success" for record in records) and any(
            record.recovery_state for record in records
        ):
            behavior = "recovers"
        elif first_failure and all(record.status != "success" for record in records):
            behavior = "crashes"
        elif first_failure and any(
            (record.redis_backlog or 0) > 0 or record.error_type == "timeout" for record in records
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
            "metrics_before": result.metrics_before,
            "metrics_after": result.metrics_after,
            "metrics": asdict(result.metrics),
            "analysis": asdict(result.analysis),
            "notes": result.notes,
        }
        summary_path.write_text(json.dumps(summary_payload, indent=2, sort_keys=True), encoding="utf-8")

    def run_scenario(
        self,
        *,
        scenario: str,
        concurrency_levels: list[int],
        runs_per_level: int,
        request_timeout_seconds: float,
        failure_plan: FailurePlan | None = None,
    ) -> ScenarioResult:
        started_at = iso_now()
        self._started_run_ids = []
        notes: list[str] = []
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
        for concurrency in concurrency_levels:
            with ThreadPoolExecutor(max_workers=concurrency) as executor:
                futures = [
                    executor.submit(
                        self.run_single,
                        scenario=scenario,
                        concurrency=concurrency,
                        request_timeout_seconds=request_timeout_seconds,
                    )
                    for _ in range(runs_per_level)
                ]
                for future in as_completed(futures):
                    records.append(future.result())

        if injector is not None:
            injector.join(timeout=max(self.per_run_timeout_seconds, 30.0))
        if injector_error:
            notes.extend(f"failure injector error: {message}" for message in injector_error)

        metrics_after = self.fetch_metrics_summary()
        metrics = self.compute_metrics(records)
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
            records=records,
            metrics=metrics,
            analysis=analysis,
            metrics_before=metrics_before,
            metrics_after=metrics_after,
            notes=notes,
        )
        self.write_scenario_artifacts(result)
        return result


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="ForgeGraph stress harness")
    parser.add_argument("--base-url", default="http://localhost:8000", help="Backend base URL")
    parser.add_argument("--email", required=True, help="User email for API authentication")
    parser.add_argument("--password", required=True, help="User password for API authentication")
    parser.add_argument("--metrics-email", help="Optional admin email for metrics access")
    parser.add_argument("--metrics-password", help="Optional admin password for metrics access")
    parser.add_argument("--graph-version-id", help="Graph version to execute")
    parser.add_argument("--graph-id", help="Resolve the latest graph version from this graph id")
    parser.add_argument(
        "--scenario",
        choices=[
            "endpoint-saturation",
            "engine-concurrency",
            "redis-saturation",
            "llm-degradation-delay",
            "llm-degradation-timeout",
            "llm-degradation-unavailable",
            "failure-injection-engine-stop",
            "failure-injection-redis-stop",
            "all",
        ],
        default="all",
    )
    parser.add_argument("--concurrency", nargs="*", type=int, default=None)
    parser.add_argument("--runs", type=int, default=10, help="Runs per concurrency level")
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
    parser.add_argument("--llm-chaos-delay-ms", type=int, default=5000)
    parser.add_argument("--failure-trigger-delay-seconds", type=float, default=5.0)
    parser.add_argument("--failure-restart-after-seconds", type=float, default=10.0)
    parser.add_argument("--docker-compose-file", default=str(ROOT_DIR / "docker-compose.yml"))
    parser.add_argument("--env-file", default=str(ROOT_DIR / ".env"))
    return parser.parse_args()


def resolve_graph_version_id(harness: StressHarness, args: argparse.Namespace) -> str:
    if args.graph_version_id:
        return str(args.graph_version_id)
    if args.graph_id:
        return harness.fetch_latest_graph_version(str(args.graph_id))
    raise SystemExit("either --graph-version-id or --graph-id is required")


def build_scenario_plan(args: argparse.Namespace) -> list[tuple[str, list[int], int, FailurePlan | None, dict[str, str] | None]]:
    concurrency_levels = args.concurrency or DEFAULT_CONCURRENCY_LEVELS
    scenarios: list[tuple[str, list[int], int, FailurePlan | None, dict[str, str] | None]] = []
    if args.scenario in {"endpoint-saturation", "all"}:
        scenarios.append(("endpoint-saturation", concurrency_levels, args.runs, None, None))
    if args.scenario in {"engine-concurrency", "all"}:
        scenarios.append(("engine-concurrency", concurrency_levels, args.runs, None, None))
    if args.scenario in {"redis-saturation", "all"}:
        scenarios.append(("redis-saturation", concurrency_levels, args.runs, None, None))
    if args.scenario in {"llm-degradation-delay", "all"}:
        scenarios.append(
            (
                "llm-degradation-delay",
                concurrency_levels,
                args.runs,
                None,
                {
                    "FORGEGRAPH_LLM_CHAOS_MODE": "delay",
                    "FORGEGRAPH_LLM_CHAOS_DELAY_MS": str(args.llm_chaos_delay_ms),
                    "FORGEGRAPH_LLM_CHAOS_ERROR_MESSAGE": "simulated llm delay",
                },
            )
        )
    if args.scenario in {"llm-degradation-timeout", "all"}:
        scenarios.append(
            (
                "llm-degradation-timeout",
                concurrency_levels,
                args.runs,
                None,
                {
                    "FORGEGRAPH_LLM_CHAOS_MODE": "timeout",
                    "FORGEGRAPH_LLM_CHAOS_DELAY_MS": str(args.llm_chaos_delay_ms),
                    "FORGEGRAPH_LLM_CHAOS_ERROR_MESSAGE": "simulated llm timeout",
                },
            )
        )
    if args.scenario in {"llm-degradation-unavailable", "all"}:
        scenarios.append(
            (
                "llm-degradation-unavailable",
                concurrency_levels,
                args.runs,
                None,
                {
                    "FORGEGRAPH_LLM_CHAOS_MODE": "unavailable",
                    "FORGEGRAPH_LLM_CHAOS_DELAY_MS": "0",
                    "FORGEGRAPH_LLM_CHAOS_ERROR_MESSAGE": "simulated llm unavailable",
                },
            )
        )
    if args.scenario in {"failure-injection-engine-stop", "all"}:
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
    return scenarios


def require_service_disruption_allowed(args: argparse.Namespace, scenarios: list[tuple[str, list[int], int, FailurePlan | None, dict[str, str] | None]]) -> None:
    needs_disruption = any(plan is not None or env_overrides is not None for _, _, _, plan, env_overrides in scenarios)
    if needs_disruption and not args.allow_service_disruption:
        raise SystemExit(
            "--allow-service-disruption is required for LLM degradation or failure-injection scenarios"
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

    client = HttpJsonClient(args.base_url)
    client.login(args.email, args.password)

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
        graph_version_id=args.graph_version_id or "",
        output_dir=output_dir,
        per_run_timeout_seconds=args.run_timeout_seconds,
        poll_interval_seconds=args.poll_interval_seconds,
        docker=docker,
        input_payload=input_payload,
    )
    harness.graph_version_id = resolve_graph_version_id(harness, args)

    scenarios = build_scenario_plan(args)
    require_service_disruption_allowed(args, scenarios)

    manifest: dict[str, Any] = {
        "started_at": iso_now(),
        "base_url": args.base_url,
        "graph_version_id": harness.graph_version_id,
        "output_dir": str(output_dir),
        "results": [],
    }

    for scenario, concurrency_levels, runs_per_level, failure_plan, env_overrides in scenarios:
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
        manifest["results"].append(
            {
                "scenario": scenario,
                "metrics": asdict(result.metrics),
                "analysis": asdict(result.analysis),
            }
        )

    manifest["completed_at"] = iso_now()
    (output_dir / "manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8"
    )
    print(json.dumps(manifest, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
