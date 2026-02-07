# P3 Launch QA Matrix

## Scope
- Functional: run lifecycle, node execution, error routing, metrics, audit visibility.
- Security: credential revoke/rotate, secret redaction, credential resolution hard-fails on revoked keys.
- UX: graph editor canvas + wizard + node dialog keyboard/form validation coverage.
- Reliability/Performance Proxy: scheduler + executor resilience tests for retry/backoff and execution flow.

## CI Mapping
- Workflow: `.github/workflows/ci.yml`
- Launch jobs:
  - `launch_qa_backend`
  - `launch_qa_engine`
  - `launch_qa_frontend`
  - `launch_qa_report` (artifact: `launch-qa-report.md`)

## Test Commands
- Backend launch gate:
  - `uv run pytest tests/integration/adapters/test_run_api.py tests/integration/adapters/test_run_history_security_api.py tests/integration/adapters/test_credentials_security_api.py tests/integration/adapters/test_audit_logs_api.py tests/integration/adapters/test_metrics_api.py tests/unit/services/test_redaction.py -q`
- Engine launch gate:
  - `go test ./application/usecase -run "Scheduler|OnError|RetryAfter|NonRetryable" -count=1`
  - `go test ./adapter/executor -run "HTTPExecutor|ToolExecutor|PromptExecutor" -count=1`
- Frontend launch gate:
  - `npm test -- --runInBand __tests__/components/graph-editor/GraphEditor.test.tsx __tests__/components/graph-editor/wizard/AgentWizard.test.tsx __tests__/components/graph-editor/NodeConfigDialog.test.tsx`

## Residual Risks
- Provider-side instability (OAuth/API outages) can still affect final pre-launch validation windows.
- Performance validation is currently proxy-driven in CI; sustained staging load tests should remain in release checklist.
