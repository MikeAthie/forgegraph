# ForgeGraph V2 Launch Quickstart

This guide is the fastest path from a fresh checkout to a production-like V2 workflow run.

## 1. Start the Stack

Use the repo helper script:

```bash
./dev up
```

Services:
- Frontend: `http://localhost:3000`
- Backend API: `http://localhost:8000`
- Engine gRPC: `localhost:50051`

## 2. Create an Account and Sign In

1. Open `http://localhost:3000`.
2. Register and sign in.
3. Confirm your default organization was created.

## 3. Credentials and Provider Setup

Open **Credentials** and connect what your template needs:

- LLM:
  - `openai` or `anthropic`
- Integrations:
  - `gmail`
  - `google_calendar`
  - `google_tasks`
  - `telegram`
  - `twilio` (for WhatsApp)

Notes:
- OAuth providers must be configured before OAuth connect flows.
- Credentials are encrypted at rest and now support rotation/revocation endpoints:
  - `POST /api/credentials/{credential_id}/rotate`
  - `POST /api/credentials/{credential_id}/revoke`

## 4. Start from a Launch Template

Open **Templates** and clone a starter flow:

- Personal productivity: **Personal Life Manager** (quick-start alias: Personal Assistant)
- Communication/governance: **Investor Update Email (Human Gate)**
- Content/research: **Research Brief**, **Customer FAQ Generator**

During clone:
- Pick preferred LLM provider/model.
- Optionally inject a credential into prompt nodes.

## 5. Run and Validate

1. Start the cloned graph run with sample input.
2. Inspect live status in Runs.
3. Verify node outcomes and final output in run detail.
4. If a human gate is present, resolve approval and resume.

## 6. Verify Operational Readiness

Check the V2 launch surfaces:

- Metrics summary: `GET /api/metrics/summary`
  - queue depth, p95 latency, failure rate, per-tenant queue distribution, guardrails
- Audit logs: `GET /api/audit-logs/`
  - filters: `action_prefix`, `run_id`, `resource_id`, `created_from`, `created_to`, `q`
- Retention policies:
  - `GET/PUT /api/retention/`
  - `POST /api/retention/cleanup`

## 7. Recommended Launch Gate Command Set

Backend:

```bash
uv run pytest backend/tests/integration/adapters/test_run_api.py backend/tests/integration/adapters/test_run_history_security_api.py backend/tests/integration/adapters/test_credentials_security_api.py backend/tests/integration/adapters/test_audit_logs_api.py backend/tests/integration/adapters/test_metrics_api.py -q
```

Engine:

```bash
go test ./application/usecase -run "Scheduler|OnError|RetryAfter|NonRetryable" -count=1
go test ./adapter/executor -run "HTTPExecutor|ToolExecutor|PromptExecutor" -count=1
```

Frontend:

```bash
npm test -- --runInBand __tests__/components/graph-editor/GraphEditor.test.tsx __tests__/components/graph-editor/wizard/AgentWizard.test.tsx __tests__/components/graph-editor/NodeConfigDialog.test.tsx
```

For CI mapping, see `docs/v2/p3-launch-qa-matrix.md`.
