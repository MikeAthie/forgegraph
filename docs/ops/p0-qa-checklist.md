# P0 QA Checklist

## Purpose
This checklist maps each P0 success criterion to an executable proof.

Use it before calling P0 complete.

## 1. Agent Node End-to-End

### Success criteria covered
- real `agent` node in graph contract
- multi-step internal tool loop
- step trace visibility
- approval pause/resume inside the same agent run

### Proof commands
```bash
cd engine
go test ./adapter/executor ./application/usecase ./test
go test ./test -run TestAgentWorkflowApprovalResume -v
```

### What this proves
- agent node executes without manual prompt/tool graph wiring
- approval-required tool calls pause the run
- resume continues the same agent execution path
- final agent output includes trace and stop reason

## 2. Marketplace Install-to-Execute

### Success criteria covered
- install means the same thing in backend, frontend, and engine
- runtime package delivery is tenant-aware
- executable packages are honest in the UI

### Proof command
```bash
cd frontend
npx playwright test __tests__/e2e/marketplace-runtime.spec.ts --project=chromium
```

### What this proves
- reviewed runtime package is installed from the UI
- backend delivers tenant runtime manifests
- engine picks up the manifest without manual file edits
- graph authoring adds the installed runtime tool
- the tool executes and renders output in the browser

## 3. Cloud-Safe Policy Enforcement

### Success criteria covered
- Cloud mode cannot execute `exec`
- unsafe runtime packages fail before runtime load
- policy denials are auditable and understandable

### Proof commands
```bash
cd backend
python -m pytest tests/unit/application/test_marketplace_runtime.py tests/integration/adapters/test_marketplace_api.py tests/integration/adapters/test_run_history_security_api.py

cd ../engine
go test ./adapter/tool ./adapter/executor
```

### What this proves
- Cloud review/install policy blocks unsafe runtime releases
- engine registry and executor reject Cloud-blocked tools
- policy-denied failures are preserved in audit-safe form

## 4. Stable Contracts

### Success criteria covered
- `SPECS.md` exists and matches serializer behavior
- run event contract is documented and enforced
- contract drift fails tests

### Proof commands
```bash
cd backend
python -m pytest tests/unit/application/test_serializers.py tests/integration/adapters/test_graph_api.py tests/integration/adapters/test_run_api.py
```

### What this proves
- Graph JSON optional contract fields are validated
- run event and engine callback shapes are allowlisted
- paused agent traces and run detail payloads are stable

## 5. Full Non-E2E Validation

### Proof commands
```bash
cd backend
python -m pytest tests --ignore=tests/e2e

cd ../engine
go test ./...

cd ../frontend
npm test
npx tsc --noEmit
```

## Exit Rule
P0 is complete when:
- all commands above pass
- the product story in [p0-beta-launch-notes.md](p0-beta-launch-notes.md) is still true
- no remaining P0 doc claims a missing capability that is already implemented
