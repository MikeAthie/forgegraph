# P0-F02 Implementation Tickets

## Goal
Convert `P0-F02` into reviewable implementation slices with explicit file targets, acceptance criteria, tests, and PR boundaries.

`P0-F02` is the marketplace/runtime coherence epic:
- backend must classify packages honestly
- installation must produce a runtime-meaningful outcome
- engine must be able to load approved runtime packages without manual file edits
- frontend must stop implying that every installed package is executable

## Current Repo Reality
The current codebase already has a marketplace catalog, release review flow, installation records, and editor quick-add support.

The current gap is specific:
- backend stores package/release metadata in `NodeRegistryPackage`, `NodeRegistryRelease`, and `NodePackageInstallation`
- frontend treats installed packages as palette-ready nodes using `execution_node_type` and `config_defaults`
- engine only knows how to load tool manifests from local JSON files through `TOOL_MANIFEST_DIR`

That means the product currently mixes two meanings:
- package as a preset/template
- package as an executable runtime extension

`P0-F02` fixes that ambiguity.

## Ticketing Strategy
The safest split is:
1. package contract and release model
2. backend manifest delivery and tenant install semantics
3. engine remote manifest loading and refresh
4. frontend marketplace truthfulness and quick-add behavior
5. end-to-end install-to-execute proof and operator visibility

This keeps the package semantics stable before engine and UI start depending on them.

---

## PR-1: Package Contract and Release Model

### Objective
Introduce explicit package classes and release metadata so the backend API can distinguish template packages from runtime-backed packages.

### Scope
- architecture docs
- ORM and serializer contract
- release validation
- API payload expansion

### Expected Files

#### New files
- `docs/architecture/marketplace-runtime-contract.md`
- `backend/infrastructure/orm/migrations/0039_marketplace_runtime_contract.py`

#### Backend files
- `backend/infrastructure/orm/models.py`
- `backend/adapters/api/marketplace/serializers.py`
- `backend/adapters/api/marketplace/views.py`
- `backend/tests/integration/adapters/test_marketplace_api.py`

#### Frontend type files
- `frontend/lib/api.ts`

### Acceptance Criteria
- [ ] `NodeRegistryRelease` has explicit metadata for package/runtime classification.
- [ ] The API can distinguish at least:
  - template-only package releases
  - runtime-backed package releases
- [ ] Release submission rejects inconsistent payloads, such as runtime releases without a runtime manifest payload.
- [ ] Installed package payloads include enough fields for frontend truthfulness without engine work landing yet.
- [ ] The package contract is written down in `docs/architecture/marketplace-runtime-contract.md`.

### Tests
- backend integration tests for:
  - valid template release submission
  - valid runtime release submission
  - invalid mixed metadata rejection
  - package/install payload serialization
- frontend type-level compatibility checks via existing TS compile/test path

### PR Boundary Notes
- Do not add engine remote loading here.
- Do not add frontend UI behavior here beyond API type compatibility.
- Prefer adding release fields now rather than retrofitting them after engine work starts.

---

## PR-2: Backend Manifest Delivery and Tenant Install Semantics

### Objective
Create a backend delivery path that turns approved runtime package installs into a tenant-scoped manifest set the engine can consume.

### Scope
- backend manifest rendering service
- tenant-scoped delivery endpoint
- install metadata/checksum handling
- package load state returned to operators

### Expected Files

#### New files
- `backend/application/services/marketplace_runtime.py`
- `backend/tests/unit/application/test_marketplace_runtime.py`

#### Backend files
- `backend/adapters/api/marketplace/views.py`
- `backend/adapters/api/marketplace/serializers.py`
- `backend/adapters/api/marketplace/urls.py`
- `backend/infrastructure/orm/models.py`
- `backend/tests/integration/adapters/test_marketplace_api.py`

#### Optional files depending on implementation
- `backend/application/services/audit_log.py`
- `backend/application/services/run_preparation.py`

### Acceptance Criteria
- [ ] Backend exposes a tenant-scoped manifest payload for installed runtime packages.
- [ ] Manifest responses are versioned and include a checksum or signature-friendly digest.
- [ ] Template-only packages do not appear in runtime manifest delivery payloads.
- [ ] Install records can surface manifest delivery state, such as ready, blocked, or invalid.
- [ ] Unauthorized tenants cannot fetch another tenant's installed runtime packages.

### Tests
- backend unit tests for manifest rendering and filtering logic
- backend integration tests for:
  - install runtime package
  - fetch installed runtime manifest payload
  - version pinning and latest selection
  - cross-tenant access denial
  - template packages excluded from runtime manifest endpoint

### PR Boundary Notes
- Keep the delivery protocol simple and explicit.
- Do not make the engine depend on polling or refresh behavior yet.
- If checksums are introduced here, their format must remain stable for PR-3.

---

## PR-3: Engine Remote Manifest Loading and Refresh

### Objective
Allow the engine to load tenant-aware runtime manifests from the control plane while preserving local manifest loading for self-hosted and development use.

### Scope
- manifest client/gateway
- registry merge rules
- refresh trigger or polling behavior
- visibility into manifest load failures

### Expected Files

#### New files
- `engine/adapter/gateway/marketplace_manifest_client.go`
- `engine/adapter/gateway/marketplace_manifest_client_test.go`
- `engine/adapter/tool/registry_test.go`

#### Engine files
- `engine/main.go`
- `engine/adapter/tool/registry.go`
- `engine/adapter/executor/tool_executor_test.go`
- `engine/test/integration_test.go`

#### Optional files depending on implementation
- `engine/adapter/tool/builtin_tools.go`
- `engine/application/port/health_reporter.go`

### Acceptance Criteria
- [ ] Engine can fetch and register runtime package manifests from the backend for the current tenant.
- [ ] Local filesystem manifests still work for dev and self-hosted mode.
- [ ] Registry behavior is deterministic when builtin, local, and remote definitions share a name/version.
- [ ] Invalid or unsupported runtime manifests fail visibly and do not silently become executable.
- [ ] Engine refresh behavior is explicit:
  - startup-only
  - polling
  - or admin-triggered refresh

### Tests
- engine unit tests for:
  - remote manifest load success
  - invalid manifest rejection
  - merge precedence between builtin/local/remote tools
  - refresh no-op when checksum has not changed
- engine integration tests for:
  - boot with remote manifest payload
  - execute a runtime-backed tool after remote load

### PR Boundary Notes
- Do not redesign the entire tool registry.
- Keep Cloud and self-host behavior explicit instead of trying to hide the difference.
- Any refresh mode introduced here must be reflected in ops docs later.

---

## PR-4: Frontend Marketplace Truthfulness and Quick-Add UX

### Objective
Make the admin marketplace page, node palette, and quick-add flows reflect the real package semantics after PR-1 through PR-3 land.

### Scope
- marketplace labels and badges
- quick-add eligibility
- blocked-state messaging
- admin publish/install forms aligned to package classes

### Expected Files

#### Frontend files
- `frontend/lib/api.ts`
- `frontend/pages/admin/marketplace.tsx`
- `frontend/components/graph-editor/GraphEditor.tsx`
- `frontend/components/graph-editor/NodePalette.tsx`
- `frontend/components/graph-editor/QuickToolBar.tsx`
- `frontend/lib/node-palette-catalog.ts`

#### Frontend tests
- `frontend/__tests__/components/graph-editor/GraphEditor.test.tsx`
- `frontend/__tests__/components/graph-editor/NodePalette.test.tsx`
- `frontend/__tests__/components/graph-editor/QuickToolBar.test.tsx`
- `frontend/__tests__/pages/admin/marketplace.test.tsx` (new)

### Acceptance Criteria
- [ ] Marketplace UI clearly distinguishes template packages from executable runtime packages.
- [ ] The publish/review/install surfaces show package class and Cloud eligibility.
- [ ] Quick-add only enables packages that are both installed and executable in the current product mode.
- [ ] Users can see why a package is unavailable, blocked, or template-only.
- [ ] Palette and quick toolbar copy stop implying "installed means runnable" unless runtime support is present.

### Tests
- frontend component tests for:
  - package badges and labels
  - disabled quick-add state
  - blocked reason rendering
  - admin publish form behavior for package class selection
- graph editor tests for adding a runtime-backed installed package vs rejecting a template-only quick-add

### PR Boundary Notes
- Do not invent a new package browsing IA here.
- This PR should consume the stable backend contract instead of shaping it.
- Keep the copy literal and operational, not marketing-heavy.

---

## PR-5: End-to-End Install-to-Execute Validation and Operator Visibility

### Objective
Prove the full install-to-execute path with one official runtime package and expose enough operator status to support the feature in practice.

### Scope
- one official package path exercised end-to-end
- installation/runtime health visibility
- final contract/demo coverage

### Expected Files

#### Backend files
- `backend/adapters/api/marketplace/views.py`
- `backend/tests/integration/adapters/test_marketplace_api.py`

#### Engine files
- `engine/test/integration_test.go`

#### Frontend files
- `frontend/pages/admin/marketplace.tsx`
- `frontend/components/graph-editor/GraphEditor.tsx`

#### Frontend tests
- `frontend/__tests__/e2e/marketplace-runtime.spec.ts` (new)

#### Docs
- `docs/mvp/mvp-tasks-p0.md`
- `docs/mvp/forgegraph-mvp-implementation-plan.md`
- `docs/mvp/p0-f02-implementation-tickets.md`

### Acceptance Criteria
- [ ] A reviewed runtime package can be installed through the marketplace UI or API.
- [ ] The engine can pick up that installation without manual manifest file edits.
- [ ] The installed package can be added from the editor and executed successfully.
- [ ] Operator-facing status makes it obvious whether a package is:
  - installed
  - runtime-ready
  - blocked
  - or failed to load
- [ ] The demo path is backed by tests, not just manual verification.

### Tests
- backend integration test covering install plus manifest availability
- engine integration test covering remote-manifest-backed execution
- frontend e2e test covering:
  - install package
  - add package node
  - run graph
  - observe successful execution

### PR Boundary Notes
- This is the first PR where `P0-F02` should feel complete from a buyer or operator perspective.
- Limit the demo package set to one or two official packages. Do not broaden the marketplace surface here.

---

## Optional PR-0: Marketplace Contract Review

### Objective
Land the marketplace/runtime contract doc before implementation if the team wants agreement on package classes and Cloud behavior first.

### Expected Files
- `docs/architecture/marketplace-runtime-contract.md`
- `docs/mvp/mvp-tasks-p0.md`
- `docs/mvp/forgegraph-mvp-implementation-plan.md`
- `docs/mvp/p0-f02-implementation-tickets.md`

### Acceptance Criteria
- [ ] Package classes, install semantics, and Cloud-safe scope are agreed before schema work starts.

---

## Recommended Merge Order
1. Optional PR-0
2. PR-1
3. PR-2
4. PR-3
5. PR-4
6. PR-5

## Final Ticket-Level Definition of Done
- [ ] All PRs merged in order or with explicitly managed overlap
- [ ] Marketplace packages mean the same thing in backend, frontend, and engine
- [ ] Runtime-backed installs can be executed without manual manifest file editing
- [ ] Template-only packages are clearly labeled and never implied to be executable
- [ ] Test coverage exists across backend, engine, and frontend layers for the install-to-execute path
