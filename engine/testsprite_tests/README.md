# Historical TestSprite Smoke Artifacts

These Python files are retained only as historical TestSprite output. They are
marked skipped because they mostly probe `/ready` or `/metrics` and do not
exercise the engine gRPC contract, runtime-intent Redis transport, callbacks,
pause/resume, or drain behavior.

Use the engine Go suites and scripted gates as production evidence:

- `go test ./...`
- `go test -race ./...`
- `bash scripts/ci/run_engine_deterministic.sh`
- `bash scripts/ci/run_engine_integration.sh`
- `bash scripts/ci/run_launch_qa_engine.sh`

Rewrite these files before re-enabling them. A production-capable replacement
must drive gRPC plus `/ready` and `/metrics` and must verify backend-owned run
state rather than treating health endpoints as workflow coverage.
