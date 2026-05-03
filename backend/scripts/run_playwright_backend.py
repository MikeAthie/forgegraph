from __future__ import annotations

import os
import signal
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def run_step(args: list[str], env: dict[str, str]) -> None:
    subprocess.run(args, cwd=PROJECT_ROOT, env=env, check=True)


def terminate_process(process: subprocess.Popen[str] | None) -> None:
    if process is None or process.poll() is not None:
        return
    process.terminate()
    try:
        process.wait(timeout=10)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=5)


def main() -> int:
    env = os.environ.copy()
    backend_port = env.get("PLAYWRIGHT_BACKEND_PORT", env.get("BACKEND_PORT", "8002"))
    runtime_fixture_email = env.get(
        "PLAYWRIGHT_RUNTIME_FIXTURE_EMAIL",
        "playwright-runtime@example.com",
    )
    runtime_fixture_password = env.get(
        "PLAYWRIGHT_RUNTIME_FIXTURE_PASSWORD",
        "ForgeGraphTest!12345",
    )
    runtime_fixture_tenant_id = env.get(
        "PLAYWRIGHT_RUNTIME_TENANT_ID",
        "00000000-0000-0000-0000-00000000e2e1",
    )
    runtime_fixture_package_slug = env.get(
        "PLAYWRIGHT_RUNTIME_PACKAGE_SLUG",
        "playwright-runtime-health-check",
    )
    runtime_fixture_package_name = env.get(
        "PLAYWRIGHT_RUNTIME_PACKAGE_NAME",
        "Playwright Runtime Health Check",
    )
    runtime_fixture_tool_name = env.get(
        "PLAYWRIGHT_RUNTIME_TOOL_NAME",
        "playwright_runtime_health_check",
    )
    runtime_fixture_tool_url = env.get(
        "PLAYWRIGHT_RUNTIME_TOOL_URL",
        f"http://127.0.0.1:{backend_port}/health",
    )

    env.setdefault("MEMORY_GRPC_HOST", "127.0.0.1")
    env.setdefault("MEMORY_GRPC_PORT", "50052")
    env["REDIS_HOST"] = env.get("PLAYWRIGHT_REDIS_HOST", "127.0.0.1")
    env["REDIS_PORT"] = env.get("PLAYWRIGHT_REDIS_PORT", "6379")
    env["REDIS_ADDR"] = f"{env['REDIS_HOST']}:{env['REDIS_PORT']}"
    for key in (
        "REDIS_SENTINEL_ADDRS",
        "REDIS_SENTINELS",
        "REDIS_SENTINEL_MASTER_NAME",
        "REDIS_SENTINEL_USERNAME",
        "REDIS_SENTINEL_PASSWORD",
    ):
        env[key] = ""

    run_step(
        [sys.executable, "manage.py", "migrate", "--noinput", "--verbosity", "0"],
        env,
    )
    run_step(
        [
            sys.executable,
            "manage.py",
            "seed_playwright_runtime_fixture",
            "--email",
            runtime_fixture_email,
            "--password",
            runtime_fixture_password,
            "--tenant-id",
            runtime_fixture_tenant_id,
            "--package-slug",
            runtime_fixture_package_slug,
            "--package-name",
            runtime_fixture_package_name,
            "--tool-name",
            runtime_fixture_tool_name,
            "--runtime-url",
            runtime_fixture_tool_url,
        ],
        env,
    )

    grpc_process = subprocess.Popen(
        [sys.executable, "-m", "adapters.grpc.server"],
        cwd=PROJECT_ROOT,
        env=env,
        text=True,
    )
    runtime_intent_process = subprocess.Popen(
        [
            sys.executable,
            "manage.py",
            "process_runtime_write_intents",
            "--consumer",
            "playwright-runtime-intents",
        ],
        cwd=PROJECT_ROOT,
        env=env,
        text=True,
    )
    run_queue_process = subprocess.Popen(
        [
            sys.executable,
            "manage.py",
            "process_run_queue",
            "--worker-id",
            "playwright-run-queue",
        ],
        cwd=PROJECT_ROOT,
        env=env,
        text=True,
    )
    runserver_process = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "daphne",
            "-b",
            "127.0.0.1",
            "-p",
            str(backend_port),
            "config.asgi:application",
        ],
        cwd=PROJECT_ROOT,
        env=env,
        text=True,
    )

    def handle_shutdown(signum: int, _frame: object) -> None:
        terminate_process(runserver_process)
        terminate_process(run_queue_process)
        terminate_process(runtime_intent_process)
        terminate_process(grpc_process)
        raise SystemExit(128 + signum)

    signal.signal(signal.SIGTERM, handle_shutdown)
    signal.signal(signal.SIGINT, handle_shutdown)

    try:
        runserver_exit = runserver_process.wait()
        return runserver_exit
    finally:
        terminate_process(runserver_process)
        terminate_process(run_queue_process)
        terminate_process(runtime_intent_process)
        terminate_process(grpc_process)


if __name__ == "__main__":
    raise SystemExit(main())
