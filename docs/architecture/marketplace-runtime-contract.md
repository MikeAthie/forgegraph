# Marketplace Runtime Contract

## Purpose
ForgeGraph marketplace packages serve two different roles:
- installable node templates for the editor
- runtime-backed extensions that the engine can fetch, load, and execute per tenant

This document defines the stable P0 contract between the control plane, engine, and frontend.

## P0 Package Kinds
P0 supports four explicit release classes:

- `template_http`
- `template_prompt`
- `runtime_tool`
- `runtime_transform`

`package_kind` is the canonical field that tells the product what a release means.

`execution_node_type` still matters, but only as the node surface the editor should create.

## Required Mapping
Each `package_kind` maps to exactly one editor node type:

| package_kind | execution_node_type | Meaning |
| --- | --- | --- |
| `template_http` | `http` | Editor preset only. Installing it makes a configured HTTP node available. |
| `template_prompt` | `prompt` | Editor preset only. Installing it makes a configured prompt node available. |
| `runtime_tool` | `tool` | Runtime-backed tool package. Install means the release is eligible for tenant-scoped manifest delivery to the engine. |
| `runtime_transform` | `transform` | Runtime-backed transform package. Contract exists in P0, but execution is still blocked. |

The backend must reject mismatched combinations.

## Release Fields
Each marketplace release now carries:

- `package_kind`
- `runtime_manifest`
- `manifest_version`
- `cloud_allowed`
- `review_notes`

### Field Meaning
- `package_kind`: the explicit class of the release.
- `runtime_manifest`: the runtime payload for executable releases. `null` for template releases.
- `manifest_version`: schema version of `runtime_manifest`.
- `cloud_allowed`: whether the release is allowed in ForgeGraph Cloud.
- `review_notes`: operator notes captured during review.

## Runtime Manifest Rules

### Template Releases
Template releases do not declare `runtime_manifest`.

They remain editor-first presets and must be honest about that.

### Runtime Tool Releases
`runtime_tool` releases must provide a runtime manifest compatible with the engine tool registry direction:

```json
{
  "name": "crm_lookup",
  "version": "1.0.0",
  "kind": "http",
  "description": "Look up a customer in the CRM.",
  "config_schema": {},
  "default_config": {},
  "http": {
    "url": "https://api.example.com/crm/lookup",
    "method": "POST"
  }
}
```

Rules:
- `name` is required and is the canonical runtime tool name.
- `version` should match the release version when present.
- `kind` must be `http` or `exec`.
- `http` releases require `http.url`.
- `exec` releases require `exec.command`.
- if `config_defaults.tool` is present, it must match `runtime_manifest.name`.

### Runtime Transform Releases
`runtime_transform` releases must provide:

```json
{
  "name": "normalize_customer_record",
  "version": "1.0.0",
  "kind": "transform"
}
```

This contract is stored in P0 even though remote transform execution is not implemented yet.

## Runtime Delivery Semantics

### Runtime manifest endpoint
Tenant-scoped runtime manifests are delivered from the control plane through:

`GET /api/marketplace/runtime-manifests?tenant_id=<tenant_uuid>`

Properties:
- authenticated with `X-Forgegraph-Timestamp` + `X-Forgegraph-Signature`
- emits `ETag`
- supports `If-None-Match`
- returns only runtime-ready releases for the requested tenant

### Runtime preview endpoint
Operators can inspect the delivered manifest through:

`GET /api/marketplace/runtime-manifest-preview`

This is the truthful admin surface for:
- package delivery state
- manifest checksum
- delivered tool list

### Engine loading
The engine loads marketplace runtime manifests when these env vars are set:
- `CONTROL_PLANE_URL`
- `ENGINE_CALLBACK_SECRET`
- `TENANT_ID`

Optional refresh polling:
- `MARKETPLACE_MANIFEST_REFRESH_SECONDS`

If a release is installed after engine startup, polling refresh is the supported P0 mechanism that picks it up without redeploying the engine.

## Cloud Scope For P0
P0 Cloud supports:
- `template_http`
- `template_prompt`
- `runtime_tool` where the runtime manifest is HTTP-backed and `cloud_allowed = true`

P0 Cloud does not support:
- `runtime_tool` backed by `exec`
- arbitrary remote code execution
- unreviewed tenant-provided runtime packages
- `runtime_transform` execution

## Install Semantics

### Template Releases
Install means:
- the package appears in the editor marketplace and quick-add flows
- the frontend can create a node with the package defaults

It does not mean runtime code was delivered.

### Runtime Releases
Install means:
- the package is approved for a tenant
- the release becomes eligible for tenant-scoped runtime manifest delivery
- the frontend can identify it as runtime-backed instead of template-only
- the engine can load it on startup or polling refresh when runtime policy allows it

## Truthfulness Requirements
The UI must not imply:
- every installed package is immediately executable
- every `tool` package already exists in the engine registry
- Cloud can execute `exec`-backed packages

The API payload must carry enough metadata for the frontend to label packages honestly.

P0 truthful delivery states are:
- `template`
- `ready`
- `blocked`
- `invalid`

## Safety Rules
P0 Cloud enforcement is end-to-end:
- review-time approval blocks unsafe releases
- install-time policy blocks unsupported runtime releases
- manifest delivery omits non-ready releases
- engine runtime rejects cloud-blocked `exec` tools even if a bad definition somehow reaches it

This means Cloud safety is enforced at:
- review
- install
- delivery
- execution
