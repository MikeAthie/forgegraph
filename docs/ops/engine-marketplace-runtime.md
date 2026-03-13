# Engine Marketplace Runtime Delivery

## Purpose
The engine can now load tenant-scoped runtime tool manifests from the control plane instead of relying only on local JSON files.

This doc covers the environment variables and the refresh behavior introduced for marketplace runtime delivery.

## Required Environment Variables

### `CONTROL_PLANE_URL`
Base URL for the ForgeGraph backend.

Example:

```bash
CONTROL_PLANE_URL=http://backend:8000
```

### `ENGINE_CALLBACK_SECRET`
Shared secret used to sign control-plane requests.

The backend verifies this secret on the runtime manifest endpoint.

### `TENANT_ID`
Organization or tenant identifier whose installed runtime packages should be loaded.

If `TENANT_ID` is missing, remote marketplace manifest loading is skipped.

## Optional Environment Variables

### `TOOL_MANIFEST_DIR`
Directory containing local tool manifest JSON files.

Local manifests still load first. This keeps self-host and local development flows working.

### `MARKETPLACE_MANIFEST_REFRESH_SECONDS`
Polling interval for remote manifest refresh.

Behavior:
- `0` or unset: fetch once at engine startup only
- positive integer: fetch at startup, then poll on that interval

Example:

```bash
MARKETPLACE_MANIFEST_REFRESH_SECONDS=30
```

## Load Order
The engine now applies tool definitions in this order:

1. built-in tool definitions already registered in code
2. local manifest files from `TOOL_MANIFEST_DIR`
3. remote runtime manifests fetched from the control plane

The last successful load wins for matching tool names.

## Remote Fetch Behavior
At startup, when `CONTROL_PLANE_URL`, `ENGINE_CALLBACK_SECRET`, and `TENANT_ID` are set, the engine requests:

```text
GET /api/marketplace/runtime-manifests?tenant_id=<TENANT_ID>
```

The request is signed with:
- `X-Forgegraph-Timestamp`
- `X-Forgegraph-Signature`

The backend returns a tenant-scoped payload with:
- `tenant_id`
- `manifest_version`
- `tools`
- `packages`
- `checksum`
- `generated_at`

## Refresh and Caching
The engine stores the last manifest checksum and sends it back as `If-None-Match` on the next poll.

If the backend returns `304 Not Modified`, the registry is left unchanged.

If the backend returns a new payload, the registry validates the remote definitions and swaps them in.

## Delivery Rules
Only runtime-ready `runtime_tool` releases are delivered to the engine in P0.

The backend intentionally excludes packages that are:
- template-only
- blocked in Cloud
- invalid
- `runtime_transform`

This means the engine does not need to guess which installed packages are executable.

## Operational Notes
- Remote manifest loading is tenant-scoped, not global.
- Startup succeeds even if remote manifest loading is disabled.
- Startup also succeeds if local manifests load but remote loading is unavailable.
- If remote loading fails, check backend reachability, shared secret alignment, and `TENANT_ID`.
- The admin Marketplace page exposes a runtime manifest preview so operators can compare what should be delivered with what the engine is configured to fetch.
