# CareerOps Candidate Competency Expansion PR 2 Implementation Plan

> **For Hermes:** Use subagent-driven-development skill to implement this plan task-by-task. If using Codex, use isolated worktrees and have Hermes verify every diff/test result.

**Goal:** Add a ForgeGraph-native CareerOps competency expansion slice inspired by `MadsLorentzen/ai-job-search` `/expand`: derive a source-backed candidate profile snapshot, proof-point digest, and competency expansion report from persisted CareerOps source assets, then make packet generation prefer those backend-owned expanded facts.

**Architecture:** Keep durable state in ForgeGraph backend records only. PR2 must not introduce local CSV/Markdown/profile files, live GitHub scraping, or client/engine-owned state. The canonical input remains the company-scoped `Asset` with `source_key="career_ops:cv_source"`; PR2 adds deterministic expansion services that read persisted asset metadata/provenance, write company-scoped `Asset`/`AssetVersion` records, materialize a candidate profile `StateProjection`, and expose an operator management command.

**Tech Stack:** Django ORM, existing `Asset`, `AssetVersion`, `Graph`, `Run`, `StateProjection`, `User`, existing CareerOps services, pytest, Django management command, uv/ruff.

---

## Current Context

Existing relevant files:

- `backend/application/services/career_ops_graph_contract.py`
  - Already defines `CAREER_OPS_BASE_CV_ARTIFACT_TYPE = "cv_source"`.
  - Already includes durable state keys:
    - `career_ops:candidate_profile`
    - `career_ops:cv_source`
    - `career_ops:proof_point_digest`
  - Does **not** yet define a `competency_expansion_report` durable state key/deliverable type.
- `backend/application/services/career_ops_packet_builder.py`
  - `_candidate_facts(company=...)` currently reads directly from `career_ops:cv_source` metadata.
  - Packet generation calls `build_career_ops_alignment_report`, `build_tailored_resume_draft`, `build_cover_letter_draft`, and ATS simulation.
- `backend/application/services/career_ops_content_alignment.py`
  - Already expects `candidate_facts` with `summary`, `proof_points`, `skills`, `projects`, `education`, `certifications`, `constraints`, and `github`-like fields.
  - Already requires source-backed claim maps and no invented missing keywords.
- `backend/application/services/career_ops_artifacts.py`
  - Existing `write_career_ops_deliverable(...)` and `write_career_ops_file_deliverable(...)` are opportunity-scoped and require `CompanyOpportunity`.
  - PR2 needs **company-scoped** candidate artifacts, not fake-opportunity artifacts.
- `backend/application/services/career_ops_projections.py`
  - Existing materializer is opportunity pipeline focused: `CAREER_OPS_PIPELINE_PROJECTION_TYPE = "career_ops:pipeline_snapshot"`.
  - PR2 should add a candidate profile projection instead of bloating the pipeline projection.
- `backend/infrastructure/orm/management/commands/run_career_ops_e2e.py`
  - `_ensure_base_cv(...)` seeds `career_ops:cv_source` with Mike's canonical CareerOps CV source metadata.
  - Packet generation currently works from this base asset directly.
- Existing tests:
  - `backend/tests/unit/services/test_career_ops_packet_builder.py`
  - `backend/tests/unit/services/test_career_ops_content_alignment.py`
  - `backend/tests/unit/services/test_career_ops_graph_contract.py`
  - `backend/tests/unit/services/test_career_ops_projections.py`
  - `backend/tests/unit/management/test_run_career_ops_e2e.py`

PR1 status:

- PR1 was implemented on branch/worktree:
  - `C:\w\fg-pr1-int`
  - branch `feat/careerops-outcomes-pr1`
  - commit `6200693 feat(career-ops): record application outcomes`
- PR2 can be implemented either:
  1. **Stacked after PR1** if PR1 remains unmerged; or
  2. **From updated main** after PR1 lands.
- PR2 does not logically depend on PR1 internals, but both touch `career_ops_graph_contract.py` and `career_ops_projections.py`, so stacking or rebasing carefully will avoid conflicts.

---

## PR2 Scope

### In Scope

1. Add deterministic candidate competency expansion from persisted CareerOps source assets.
2. Persist three company-scoped JSON artifacts:
   - `candidate_profile_snapshot`
   - `proof_point_digest`
   - `competency_expansion_report`
3. Add a candidate profile `StateProjection` derived from those artifacts.
4. Add an operator management command to run the expansion.
5. Update packet builder to prefer the latest valid expanded candidate profile over ad hoc direct base-CV extraction, while retaining fallback behavior if no expansion exists.
6. Update the E2E command to run expansion after ensuring the base CV and include expansion artifact IDs in its JSON output.
7. Add focused unit tests and command tests.

### Out of Scope

- No live GitHub API calls.
- No browser/GitHub scraping.
- No PDF rendering changes.
- No new frontend UI/API endpoint.
- No LLM-based inference.
- No auto-apply or employer-facing side effects.
- No local Markdown/CSV profile state.
- No rewriting candidate facts from unsupported or weakly inferred claims.

---

## Data Contract

### Source asset contract

The canonical PR2 input is active company asset:

```python
Asset.objects.filter(
    company=company,
    status="active",
    source_key="career_ops:cv_source",
).first()
```

Source metadata may include top-level or `metadata_json["career_ops"]` values:

```json
{
  "summary": "...",
  "proof_points": ["..."],
  "skills": [...],
  "projects": [...],
  "education": [...],
  "certifications": [...],
  "constraints": {...},
  "github": "https://github.com/MikeAthie",
  "career_ops": {
    "deliverable_type": "cv_source",
    "summary": "...",
    "proof_points": [...]
  }
}
```

### Candidate profile snapshot format

Persist as `Asset.source_key = "career_ops:candidate_profile_snapshot"`.

```json
{
  "format": "career_ops_candidate_profile_snapshot_v1",
  "company_id": "...",
  "source_asset_refs": [
    {
      "type": "asset",
      "asset_id": "...",
      "source_key": "career_ops:cv_source",
      "content_hash": "...",
      "metadata_path": "metadata_json"
    }
  ],
  "identity": {
    "name": "Miguel Athie",
    "location": "Mexico City, MX",
    "email": "miguel.athien@gmail.com",
    "phone": "+52 55 3900 3599",
    "github": "https://github.com/MikeAthie"
  },
  "summary": {
    "text": "...",
    "source_refs": [{"type": "asset_metadata", "asset_id": "...", "path": "summary"}]
  },
  "competencies": [
    {
      "label": "Python backend APIs",
      "category": "backend",
      "confidence": "source_backed",
      "source_refs": [{"type": "asset_metadata", "asset_id": "...", "path": "proof_points[0]"}]
    }
  ],
  "proof_points": [
    {
      "text": "Built production APIs using Python, FastAPI, PostgreSQL, and Redis.",
      "tags": ["Python", "FastAPI", "PostgreSQL", "Redis"],
      "external_safe": true,
      "source_refs": [{"type": "asset_metadata", "asset_id": "...", "path": "proof_points[0]"}]
    }
  ],
  "projects": [...],
  "education": [...],
  "certifications": [...],
  "constraints": {...},
  "quality": {
    "source_backed": true,
    "unsourced_claims_promoted": false,
    "external_side_effects_allowed": false
  }
}
```

### Proof-point digest format

Persist as `Asset.source_key = "career_ops:proof_point_digest"`.

```json
{
  "format": "career_ops_proof_point_digest_v1",
  "source_asset_refs": [...],
  "groups": [
    {
      "category": "backend_api",
      "items": [
        {
          "text": "...",
          "tags": ["Python", "FastAPI"],
          "source_refs": [...]
        }
      ]
    }
  ],
  "external_safe_count": 12,
  "blocked_count": 0,
  "quality": {
    "every_item_has_source_ref": true,
    "external_side_effects_allowed": false
  }
}
```

### Competency expansion report format

Persist as `Asset.source_key = "career_ops:competency_expansion_report"`.

```json
{
  "format": "career_ops_competency_expansion_report_v1",
  "status": "expanded",
  "sources_processed": 1,
  "source_asset_refs": [...],
  "counts": {
    "competencies": 18,
    "proof_points": 9,
    "projects": 3,
    "certifications": 3,
    "warnings": 0
  },
  "diagnostics": {
    "dropped_unsourced_claims": [],
    "blocked_internal_leakage": [],
    "conflicts": [],
    "missing_recommended_fields": []
  },
  "quality": {
    "source_backed": true,
    "deterministic": true,
    "external_side_effects_allowed": false
  }
}
```

---

## Implementation Tasks

### Task 1: Extend CareerOps graph contract

**Objective:** Declare PR2 artifact/deliverable/source-key names in one shared contract module.

**Files:**

- Modify: `backend/application/services/career_ops_graph_contract.py`
- Modify: `backend/tests/unit/services/test_career_ops_graph_contract.py`

**Step 1: Write failing test**

Add assertions:

```python
def test_career_ops_contract_includes_candidate_expansion_artifacts() -> None:
    assert "career_ops:candidate_profile_snapshot" in CAREER_OPS_DURABLE_STATE_KEYS
    assert "career_ops:proof_point_digest" in CAREER_OPS_DURABLE_STATE_KEYS
    assert "career_ops:competency_expansion_report" in CAREER_OPS_DURABLE_STATE_KEYS
    assert "candidate_profile_snapshot" in CAREER_OPS_DELIVERABLE_TYPES
    assert "proof_point_digest" in CAREER_OPS_DELIVERABLE_TYPES
    assert "competency_expansion_report" in CAREER_OPS_DELIVERABLE_TYPES
```

**Step 2: Run RED**

```bash
cd backend
FORGEGRAPH_ENV_FILE= DEBUG=0 SECRET_KEY=test ALLOWED_HOSTS=localhost,127.0.0.1 USE_SQLITE=true USE_IN_MEMORY_CACHE=1 USE_IN_MEMORY_CHANNEL_LAYER=1 SQLITE_DB_PATH=.hermes/career_ops_pr2_contract.sqlite3 UV_PROJECT_ENVIRONMENT=.venv-test-career-ops-e2e PYTHONPATH= PYTHONNOUSERSITE=1 uv run --group dev pytest tests/unit/services/test_career_ops_graph_contract.py -q --tb=short
```

Expected: fail because constants are missing.

**Step 3: Implement**

Add constants and tuple entries:

```python
CAREER_OPS_CANDIDATE_PROFILE_SNAPSHOT_SOURCE_KEY = "career_ops:candidate_profile_snapshot"
CAREER_OPS_PROOF_POINT_DIGEST_SOURCE_KEY = "career_ops:proof_point_digest"
CAREER_OPS_COMPETENCY_EXPANSION_REPORT_SOURCE_KEY = "career_ops:competency_expansion_report"
CAREER_OPS_CANDIDATE_PROFILE_PROJECTION_TYPE = "career_ops:candidate_profile"
```

Update `CAREER_OPS_DURABLE_STATE_KEYS` and `CAREER_OPS_DELIVERABLE_TYPES` accordingly.

**Step 4: Run GREEN**

Same pytest command; expected pass.

---

### Task 2: Add company-scoped CareerOps artifact writer

**Objective:** Persist candidate-level JSON artifacts without requiring a `CompanyOpportunity`.

**Files:**

- Modify: `backend/application/services/career_ops_artifacts.py`
- Create/modify test: `backend/tests/unit/services/test_career_ops_artifacts.py` if it exists; otherwise create it.

**Why:** Existing `write_career_ops_deliverable(...)` is opportunity-scoped and uses source keys like `career_ops:{opportunity.id}:{deliverable_type}`. PR2 profile artifacts are company-level durable state, so using a fake opportunity would violate the domain model.

**Step 1: Write failing tests**

Test behavior:

```python
def test_write_career_ops_company_json_artifact_versions_by_content_hash(user: User) -> None:
    company = _company(user)
    run = _run(company, user)

    asset, version = write_career_ops_company_json_artifact(
        company=company,
        run=run,
        source_key="career_ops:candidate_profile_snapshot",
        title="Candidate profile snapshot",
        artifact_type="candidate_profile_snapshot",
        payload={"format": "career_ops_candidate_profile_snapshot_v1", "quality": {"external_side_effects_allowed": False}},
    )

    assert asset.company == company
    assert asset.source_key == "career_ops:candidate_profile_snapshot"
    assert asset.metadata_json["career_ops"]["artifact_type"] == "candidate_profile_snapshot"
    assert asset.metadata_json["career_ops"]["external_side_effects_allowed"] is False
    assert version.mime_type == "application/json"
    assert version.provenance_json["career_ops"]["format"] == "career_ops_candidate_profile_snapshot_v1"

    _, same_version = write_career_ops_company_json_artifact(...same payload...)
    assert same_version.id == version.id
```

**Step 2: Implement helper**

Add:

```python
def write_career_ops_company_json_artifact(
    *,
    company: Graph,
    run: Run,
    source_key: str,
    title: str,
    artifact_type: str,
    payload: dict[str, Any],
) -> tuple[Asset, AssetVersion]:
    ...
```

Implementation notes:

- Import `Graph`.
- `json.dumps(payload, sort_keys=True, indent=2).encode("utf-8")`.
- `content_hash = sha256(data).hexdigest()`.
- `Asset.objects.get_or_create(company=company, source_key=source_key, ...)`.
- `Asset.metadata_json["career_ops"]` must include:
  - `artifact_type`
  - `source_key`
  - `live_ready: False`
  - `external_side_effects_allowed: False`
- `AssetVersion.content_uri = f"forgegraph://career-ops/{company.id}/{artifact_type}.json"`.
- No `ServiceDeliverable` required in PR2 unless later product surfaces need it. Candidate profile state should be durable `Asset` + `AssetVersion` + `StateProjection` first.

**Step 3: Run tests**

```bash
cd backend
... uv run --group dev pytest tests/unit/services/test_career_ops_artifacts.py -q --tb=short
```

---

### Task 3: Add pure competency expansion service

**Objective:** Normalize source-backed candidate facts into snapshot/digest/report payloads without database writes.

**Files:**

- Create: `backend/application/services/career_ops_competency_expansion.py`
- Create: `backend/tests/unit/services/test_career_ops_competency_expansion.py`

**Core API:**

```python
@dataclass(frozen=True, slots=True)
class CareerOpsCompetencyExpansionPayloads:
    candidate_profile_snapshot: dict[str, Any]
    proof_point_digest: dict[str, Any]
    competency_expansion_report: dict[str, Any]


def build_career_ops_competency_expansion_payloads(
    *,
    company: Graph,
    source_assets: Sequence[Asset],
) -> CareerOpsCompetencyExpansionPayloads:
    """Build deterministic source-backed CareerOps candidate expansion payloads."""
```

**Normalization rules:**

- Accept facts from `asset.metadata_json` and `asset.metadata_json["career_ops"]`.
- Merge top-level and `career_ops` fields, with top-level preferred when both are present.
- Every promoted item must include `source_refs`.
- Source ref format:

```python
{
    "type": "asset_metadata",
    "asset_id": str(asset.id),
    "source_key": asset.source_key,
    "path": "proof_points[0]",
}
```

- Do not promote missing-keyword inferred claims.
- Do not promote internal-leakage facts containing tokens from `INTERNAL_LEAKAGE_TOKENS` unless they are project names that are allowed in current CV guardrails. Keep this conservative: `metadata_json`, `provenance_json`, `raw tool`, and `prompt` must be blocked.
- Preserve canonical identity exactly from source, but if `github` contains dead/old `GreyCrossX`, report warning `noncanonical_github_profile` rather than silently replacing it. A later source update should fix it.
- Certifications are facts; do not underclaim C2 as C1.

**Competency tagging heuristic:**

Keep deterministic/simple. Tag proof points with known vocabulary already used by CareerOps:

```python
COMPETENCY_TAGS = {
    "Python": ("python", "fastapi", "django"),
    "REST APIs": ("rest api", "rest apis", "api contracts"),
    "PostgreSQL": ("postgresql", "postgres"),
    "Redis": ("redis", "redis streams"),
    "Celery": ("celery",),
    "WebSockets": ("websocket", "websockets"),
    "RAG": ("rag",),
    "Agentic AI": ("agentic", "agent workflows"),
    "React": ("react", "next.js", "nextjs"),
    "TypeScript": ("typescript", "ts"),
    "Go": ("golang", "go backend", "go services"),
    "Observability": ("observability", "operational visibility"),
}
```

Important: tags explain source text; they do not create standalone claims unless backed by a proof point/source field.

**Tests:**

1. `test_build_expansion_payloads_normalizes_source_backed_profile`
   - Source has summary, proof points, skills, projects, education, certifications.
   - Assert snapshot/digest/report formats.
   - Assert every competency/proof point has `source_refs`.
   - Assert `external_side_effects_allowed` false.

2. `test_expansion_dedupes_competencies_preserving_source_refs`
   - Two proof points mention Python/PostgreSQL.
   - Assert one `Python` competency with multiple refs or enough refs to trace both sources.

3. `test_expansion_blocks_internal_leakage`
   - Source proof point contains `metadata_json` or `raw tool`.
   - Assert not promoted to `proof_points`.
   - Assert report diagnostics include it.

4. `test_expansion_reports_noncanonical_github_without_silent_rewrite`
   - Source github `https://github.com/GreyCrossX`.
   - Assert snapshot identity still shows source value or omits it according to implementation decision.
   - Assert report warning includes `noncanonical_github_profile`.
   - Do **not** silently swap to `MikeAthie` unless the source asset contains that canonical value.

5. `test_expansion_keeps_c2_certification_text`
   - Source certification includes `Cambridge English C2 Proficiency`.
   - Assert no `C1` underclaim appears.

---

### Task 4: Add persistence orchestration service

**Objective:** Run pure expansion, persist artifacts, create a Run receipt, and materialize candidate profile projection.

**Files:**

- Modify: `backend/application/services/career_ops_competency_expansion.py`
- Modify: `backend/application/services/career_ops_projections.py`
- Test: `backend/tests/unit/services/test_career_ops_competency_expansion.py`
- Test: `backend/tests/unit/services/test_career_ops_projections.py`

**Core API:**

```python
@dataclass(frozen=True, slots=True)
class CareerOpsCompetencyExpansionResult:
    run_id: str
    candidate_profile_asset_version_id: str
    proof_point_digest_asset_version_id: str
    competency_expansion_report_asset_version_id: str
    projection_id: str
    external_side_effects_allowed: bool = False


def expand_career_ops_candidate_profile(
    *,
    company: Graph,
    actor: User,
    idempotency_key: str,
) -> CareerOpsCompetencyExpansionResult:
    ...
```

**Behavior:**

- Validate company has organization.
- Validate actor exists.
- Find active source assets:
  - Required: `career_ops:cv_source`
  - Future-compatible: support additional active assets with `metadata_json["career_ops"]["profile_source"] == True` but do not require them.
- Create backend `Run`:
  - `input_json["career_ops"]["pipeline"] = "candidate_competency_expansion"`
  - include `idempotency_key`
  - `external_side_effects_allowed: False`
- Call pure payload builder.
- Persist three company JSON artifacts with `write_career_ops_company_json_artifact`.
- Materialize profile projection.
- Mark Run succeeded and store output artifact version IDs.

**Projection addition:**

Add:

```python
CAREER_OPS_CANDIDATE_PROFILE_PROJECTION_TYPE = "career_ops:candidate_profile"


def materialize_career_ops_candidate_profile_projection(*, company: Graph) -> StateProjection:
    ...
```

Projection `json_state` should include:

```json
{
  "generated_at": "...",
  "candidate_profile_asset_version_id": "...",
  "proof_point_digest_asset_version_id": "...",
  "competency_expansion_report_asset_version_id": "...",
  "counts": {...},
  "diagnostics": {...},
  "external_side_effects_allowed": false
}
```

**Test assertions:**

- Exactly one projection of type `career_ops:candidate_profile` after repeated materialization.
- Result IDs correspond to existing `AssetVersion` rows.
- Run output includes all IDs.
- No external side effects.

---

### Task 5: Add management command

**Objective:** Provide an operator command to run PR2 expansion directly.

**Files:**

- Create: `backend/infrastructure/orm/management/commands/expand_career_ops_candidate_profile.py`
- Create: `backend/tests/unit/management/test_expand_career_ops_candidate_profile.py`

**Command interface:**

```bash
python manage.py expand_career_ops_candidate_profile \
  --company-id <uuid> \
  --user-id <uuid> \
  --idempotency-key careerops:expand:<company-id>:<date>
```

**Output JSON:**

```json
{
  "status": "ok",
  "run_id": "...",
  "company_id": "...",
  "candidate_profile_asset_version_id": "...",
  "proof_point_digest_asset_version_id": "...",
  "competency_expansion_report_asset_version_id": "...",
  "projection_id": "...",
  "external_side_effects_allowed": false
}
```

**Tests:**

- Creates base CV asset, calls command, asserts output JSON IDs.
- Reads back `AssetVersion.provenance_json` and asserts formats.
- Assert no `ServiceDeliverable` fake opportunity is required.
- Assert missing base CV exits with `CommandError` and useful message.

---

### Task 6: Make packet builder prefer expanded profile snapshot

**Objective:** Use backend-owned expanded candidate profile when available, falling back to base CV metadata for backward compatibility.

**Files:**

- Modify: `backend/application/services/career_ops_packet_builder.py`
- Modify: `backend/tests/unit/services/test_career_ops_packet_builder.py`

**Implementation approach:**

Add helper:

```python
def _expanded_candidate_profile_asset(*, company: Graph) -> Asset | None:
    return Asset.objects.filter(
        company=company,
        status="active",
        source_key=CAREER_OPS_CANDIDATE_PROFILE_SNAPSHOT_SOURCE_KEY,
    ).first()
```

Then `_candidate_facts(company=...)` should:

1. Try latest profile snapshot `AssetVersion` provenance.
2. Convert snapshot to current `candidate_facts` shape:
   - `summary`: snapshot summary text
   - `proof_points`: list of proof point texts
   - `skills`: grouped skills/competencies
   - `projects`
   - `education`
   - `certifications`
   - `constraints`
   - `github`
   - `asset_id`
   - `candidate_profile_asset_version_id`
3. If no valid snapshot, fallback to existing base CV extraction.

**Do not auto-run expansion inside packet builder in PR2.** Packet generation should not silently mutate profile state. E2E/command flow should run expansion explicitly.

**Tests:**

- Existing no-base-CV block behavior still passes.
- Existing base-CV fallback behavior still passes.
- New test: when profile snapshot exists, packet builder uses snapshot facts, not stale base CV facts.
  - Base CV proof point says only `Python`.
  - Snapshot proof point says `Python FastAPI Redis`.
  - Posting asks for Redis.
  - Assert generated resume includes Redis because snapshot is preferred.
- Assert packet `source_refs` include candidate profile asset/version ref.

---

### Task 7: Wire PR2 into E2E command

**Objective:** Ensure `run_career_ops_e2e` creates/uses expanded profile before generating packets.

**Files:**

- Modify: `backend/infrastructure/orm/management/commands/run_career_ops_e2e.py`
- Modify: `backend/tests/unit/management/test_run_career_ops_e2e.py`

**Implementation:**

After `_ensure_base_cv(...)`, call:

```python
expansion = expand_career_ops_candidate_profile(
    company=company,
    actor=actor,
    idempotency_key=f"{idempotency_key}:candidate-expansion",
)
```

Add output fields:

```json
{
  "candidate_profile_asset_version_id": "...",
  "proof_point_digest_asset_version_id": "...",
  "competency_expansion_report_asset_version_id": "...",
  "candidate_profile_projection_id": "..."
}
```

**Tests:**

Update `test_run_career_ops_e2e_command_persists_forgegraph_state`:

- Assert payload includes expansion IDs.
- Assert `AssetVersion` rows exist.
- Assert `candidate_profile_snapshot` includes `Cambridge English C2 Proficiency` if source includes it.
- Assert packet text still includes C2 certification.
- Assert `StateProjection.objects.filter(company=company, projection_type="career_ops:candidate_profile").exists()`.

---

### Task 8: Final verification and PR hygiene

**Commands:**

Run focused PR2 tests:

```bash
cd backend
FORGEGRAPH_ENV_FILE= DEBUG=0 SECRET_KEY=test ALLOWED_HOSTS=localhost,127.0.0.1 USE_SQLITE=true USE_IN_MEMORY_CACHE=1 USE_IN_MEMORY_CHANNEL_LAYER=1 SQLITE_DB_PATH=.hermes/career_ops_pr2.sqlite3 UV_PROJECT_ENVIRONMENT=.venv-test-career-ops-e2e PYTHONPATH= PYTHONNOUSERSITE=1 uv run --group dev pytest \
  tests/unit/services/test_career_ops_competency_expansion.py \
  tests/unit/services/test_career_ops_artifacts.py \
  tests/unit/services/test_career_ops_packet_builder.py \
  tests/unit/services/test_career_ops_graph_contract.py \
  tests/unit/services/test_career_ops_projections.py \
  tests/unit/management/test_expand_career_ops_candidate_profile.py \
  tests/unit/management/test_run_career_ops_e2e.py \
  -q --tb=short --disable-warnings
```

Run static checks:

```bash
cd backend
UV_PROJECT_ENVIRONMENT=.venv-test-career-ops-e2e PYTHONPATH= PYTHONNOUSERSITE=1 uv run ruff check \
  application/services/career_ops_competency_expansion.py \
  application/services/career_ops_artifacts.py \
  application/services/career_ops_packet_builder.py \
  application/services/career_ops_graph_contract.py \
  application/services/career_ops_projections.py \
  infrastructure/orm/management/commands/expand_career_ops_candidate_profile.py \
  infrastructure/orm/management/commands/run_career_ops_e2e.py \
  tests/unit/services/test_career_ops_competency_expansion.py \
  tests/unit/management/test_expand_career_ops_candidate_profile.py
```

Run Django check:

```bash
cd backend
KEY=$(UV_PROJECT_ENVIRONMENT=.venv-test-career-ops-e2e PYTHONPATH= PYTHONNOUSERSITE=1 uv run python - <<'PY'
from cryptography.fernet import Fernet
print(Fernet.generate_key().decode())
PY
)
FORGEGRAPH_ENV_FILE= DEBUG=0 SECRET_KEY=test ALLOWED_HOSTS=localhost,127.0.0.1 ENCRYPTION_KEY="$KEY" USE_SQLITE=true USE_IN_MEMORY_CACHE=1 USE_IN_MEMORY_CHANNEL_LAYER=1 SQLITE_DB_PATH=.hermes/career_ops_pr2_check.sqlite3 UV_PROJECT_ENVIRONMENT=.venv-test-career-ops-e2e PYTHONPATH= PYTHONNOUSERSITE=1 uv run python manage.py check
```

Optional local command smoke:

1. Create user/company/base CV in a temporary SQLite DB.
2. Run `expand_career_ops_candidate_profile`.
3. Read back the three artifact versions and candidate profile projection.
4. Verify all external side effects flags are false.

PR hygiene:

```bash
git status --short
git diff --check
git diff --cached --check
git diff --cached | grep -Ein 'secret|password|token|api[_-]?key|credential|authorization' || true
```

Stage only PR2 files; do not stage unrelated `.hermes/codex_media_workdir/`, Docker smoke artifacts, or prior untracked PR1 plan unless explicitly desired.

---

## Suggested Worktree / Codex Execution Plan

If implementing with Codex/concurrent worktrees:

1. Start from PR1 branch if stacking:

```bash
git worktree add C:/w/fg-pr2-int -b feat/careerops-competency-expansion-pr2 C:/w/fg-pr1-int
```

Or start from updated main after PR1 merge:

```bash
git fetch origin
git worktree add C:/w/fg-pr2-int -b feat/careerops-competency-expansion-pr2 origin/main
```

2. Safe parallel lanes:

- Lane A: pure expansion service + unit tests.
- Lane B: company artifact writer + projection tests.
- Lane C: command + E2E/packet-builder integration tests.

3. Merge into integration worktree only after Hermes reads diffs and runs tests. Do not trust agent self-reports.

---

## Risks / Guardrails

- **Over-inference risk:** PR2 must not promote claims just because a job market wants them. It can tag existing proof points, not invent new proof.
- **Source-ref risk:** Every promoted competency/proof point must have at least one source ref.
- **State ownership risk:** Runtime events, agent memory, local files, and client payloads are not authoritative.
- **Opportunity coupling risk:** Candidate profile artifacts are company/candidate-level, not opportunity-level. Do not require a fake opportunity.
- **Staleness risk:** If source CV asset changes, old expansion artifacts can become stale. PR2 should include source asset IDs/hashes in payloads so PR3+ can add explicit freshness checks.
- **GitHub link hygiene:** Do not silently rewrite source facts. If source says `GreyCrossX`, report `noncanonical_github_profile`; if source says `MikeAthie`, use it.
- **C2 guardrail:** Preserve `Cambridge English C2 Proficiency`; do not output C1.
- **External side effects:** All PR2 quality/provenance payloads must include `external_side_effects_allowed: false`.

---

## Definition of Done

- `expand_career_ops_candidate_profile` service exists and persists three company-scoped JSON artifacts.
- Management command emits JSON with artifact/projection IDs.
- Candidate profile projection materializes from durable artifacts.
- Packet builder prefers expanded profile snapshot when present and falls back to base CV when absent.
- E2E command includes PR2 expansion IDs and continues producing packets.
- Focused tests, ruff, py_compile, and Django check pass.
- No local profile files, no live GitHub scraping, no employer-facing side effects.
