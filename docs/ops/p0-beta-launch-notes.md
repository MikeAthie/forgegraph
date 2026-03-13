# P0 Beta Launch Notes

## Scope
These notes describe the currently supported P0 runtime surface after:
- `P0-F01` agent runtime groundwork
- `P0-F02` marketplace runtime delivery
- `P0-F03` Cloud-safe execution enforcement
- `P0-F04` graph and run-event contract publication

## What Is Supported

### Graph authoring
- `agent` is a first-class node type in backend, engine, and frontend.
- Graph payloads follow the stable contract in [SPECS](../../SPECS.md).
- Run detail and live updates follow the stable contract in [Run Event Contract](../architecture/run-event-contract.md).

### Marketplace package classes
- `template_http`
- `template_prompt`
- `runtime_tool`
- `runtime_transform`

Current executable Cloud path:
- `runtime_tool`

Current non-executable or restricted path:
- `template_http`
- `template_prompt`
- `runtime_transform`

These still appear honestly in the marketplace UI, but only runtime-ready packages are treated as executable runtime tools.

### Cloud-safe behavior
- Cloud mode blocks `exec` tools at review time.
- Cloud mode blocks unsafe runtime installs.
- Cloud mode excludes blocked runtime manifests from delivery.
- Engine runtime rejects Cloud-blocked tool definitions even if they somehow reach execution.
- Policy-denied failures are redacted and audit-logged.

### Runtime delivery
- Engine can load local manifests from `TOOL_MANIFEST_DIR`.
- Engine can also load tenant-scoped runtime manifests from the control plane.
- Remote manifest loading supports `ETag` / `If-None-Match`.
- Polling refresh is controlled by `MARKETPLACE_MANIFEST_REFRESH_SECONDS`.

## Browser-Level Proof
The current install-to-execute proof is:

```bash
cd frontend
npx playwright test __tests__/e2e/marketplace-runtime.spec.ts --project=chromium
```

This proof covers:
- marketplace install through browser UI
- remote manifest delivery to engine
- graph creation in the editor
- runtime tool insertion from installed packages
- real run execution through backend + engine
- rendered run output in the browser

## Current Known Limits
- `runtime_transform` is modeled in the contract but intentionally not delivered to the current engine runtime path.
- The marketplace remains curated for Cloud. This is not a public arbitrary plugin system.
- Browser-level proof currently covers runtime package install-to-execute. Agent approval/resume proof is covered by engine integration tests rather than a browser E2E flow.

## Recommended Validation Commands

### Backend
```bash
cd backend
python -m pytest tests --ignore=tests/e2e
```

### Engine
```bash
cd engine
go test ./...
```

### Frontend
```bash
cd frontend
npm test
npx tsc --noEmit
```

## Operator Notes
- For engine runtime env vars and refresh behavior, see [Engine Marketplace Runtime](engine-marketplace-runtime.md).
- For package delivery semantics, see [Marketplace Runtime Contract](../architecture/marketplace-runtime-contract.md).
