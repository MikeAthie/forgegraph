# Digital Marketing Pro Operating Model Pack

## Architecture

Digital Marketing Pro is implemented as `digital_marketing_pro.v1`, an installable Company Operating Model Pack. ForgeGraph core remains company-agnostic: DMP labels such as Engagement, Stone, Opinion, Campaign, Creative Brief, and Living Instruction File live in pack manifests and frontend labels, not in marketing-specific backend routes or models.

The pack compiles into existing ForgeGraph concepts:

- Company: `Graph`
- Operating model: `GraphVersion`
- Operations and tasks: `Run`, `TaskRecord`, `TaskLifecycleRecord`
- Artifacts and revisions: `Asset`, `AssetVersion`, `AssetDependency`
- Decisions and approvals: `DecisionRecord`, `ApprovalTask`
- Memory and evidence: `MemoryObservation`, `ContextPack`, `EvidenceLink`
- Tools: `NodeRegistryPackage`, `NodeRegistryRelease`, `NodePackageInstallation`, `ToolExecution`
- Signals and objectives: `CompanySignal`, `CompanyOperationObjective`

Generic gaps are represented by neutral models such as `OperatingModelPackRelease`, `CompanyOperatingModelInstallation`, `CompanyProgram`, `ProgramStageState`, `AssertionRecord`, `StateProjection`, `EvaluationRun`, `PolicyEvaluation`, and `ReworkPlan`.

## DMP Mapping

| DMP concept | ForgeGraph primitive |
| --- | --- |
| Marketing engagement | `CompanyProgram` labeled Engagement by the pack |
| 12-part methodology | Pack stage templates plus `ProgramStageState` |
| Stone vs Opinion | `AssertionRecord` with pack labels for FACT and OPINION |
| DMP artifacts | `Asset` / `AssetVersion` surfaced as work artifacts |
| v1/v2 two views | Generic revision lineage and canonical revision pointer |
| Living Instruction File | `StateProjection` type `currently_true_state` |
| Decision matrix | `ReworkPlan` and `ReworkPlanItem` |
| QA check | `EvaluationRun` using DMP evaluation profiles |
| Approval framework | `PolicyPack`, `PolicyEvaluation`, decisions, and approvals |
| Agents | Department and capability blueprints compiled into the operating model |
| Connectors | Marketplace/runtime tool packages |
| Portfolio ops | Generic roles, assignments, capacity, and portfolio snapshots |

## Runtime Invariants

- The backend remains the only durable source of truth.
- The engine may execute graph work, but it does not own DMP engagement state, artifact lineage, policy state, QA state, or currently-true projections.
- Events are observability/transport artifacts only.
- No durable state is stored in `~/.claude-marketing` or any local DMP clone.
- No `/api/marketing/*` routes or `Marketing*` core models are introduced.
- Side-effecting actions must pass through generic policy evaluation, approval, audit, and tool execution controls.

## Install, Upgrade, Remove

Install loads `operating_model_packs/digital_marketing_pro/manifest.yml`, validates the pack checksum, syncs an `OperatingModelPackRelease`, and creates a company-scoped `CompanyOperatingModelInstallation`.

Install also creates or updates company-scoped evaluation profiles, policy packs/rules, signal taxonomies, team roles, dashboard metadata, operation templates, and a saved operating model version.

Upgrade re-runs the same installer against the requested pack id/version and updates company-scoped pack records. Remove marks the installation as removed; it does not delete company programs, artifacts, decisions, approvals, or audit history.

## Rollback

Disable the pack by removing or marking the `CompanyOperatingModelInstallation` as removed. Existing backend-owned records remain inspectable. Because the implementation is additive and generic, rollback does not require deleting DMP state tables or changing engine behavior.
