# AthleteOps Garmin Departments Implementation Plan

> **For Hermes:** Use subagent-driven-development skill to implement this plan task-by-task after Mike approves the strategy. Do not implement before approval.

**Goal:** Add a ForgeGraph-native AthleteOps training company setup with the departments needed for goal-driven endurance coaching, plus a Garmin Connect read-only ingestion path that pulls current user condition and recent training data into backend-owned durable state.

**Architecture:** Keep ForgeGraph backend authoritative. The Garmin connector is an adapter/service that fetches external data and normalizes it into durable Django models. Departments are registered through an installable operating model pack and/or setup service; LLM/runtime state may reason over snapshots later but never owns athlete state, training history, credentials, or recommendations.

**Tech Stack:** Django/DRF backend, existing ForgeGraph `Graph` company + `DepartmentRegistry` + operating model pack primitives, `python-garminconnect` for Garmin Connect API access, pytest + pytest-django, uv on Mike's Windows/Git Bash setup.

---

## Current context

- Repo: `C:/Users/mathi/projects/forgegraph`
- Branch: `main`
- Worktree is dirty with unrelated Atlas/media files and `backend/db.sqlite3` modified. Implementation should avoid touching unrelated files and should preferably happen in a fresh worktree/branch.
- Runtime invariant from `AGENTS.md`: backend is the only durable source of truth. Engine/client/events/snapshots cannot be authoritative.
- Existing relevant primitives:
  - `Graph` is the transitional company object.
  - `DepartmentRegistry` stores organization-owned departments.
  - `DepartmentMembership` assigns users to departments.
  - Operating model packs live under `operating_model_packs/<pack_id>/`.
  - `APIKey` stores encrypted credentials/OAuth tokens but currently has no `garmin` provider choice.
  - Department API already exists under `adapters/api/departments/`.

## Strategic scope for this first goal

Build only the foundation:

1. Register an **AthleteOps operating model pack** with departments.
2. Create a setup command/service that creates an AthleteOps company and departments.
3. Add Garmin read-only connector plumbing.
4. Persist normalized Garmin snapshots/activity summaries.
5. Provide a management command/API service that can pull Garmin data when credentials are configured.
6. Add tests with a fake Garmin client.

Do **not** yet build:

- Marathon plausibility scoring.
- Full plan generation.
- Garmin workout calendar publishing.
- UI dashboards.
- Nutrition/injury diagnosis.
- Automatic adaptation logic.

Those come after data ingestion is reliable.

---

## Department model

Create these departments for the generic training company:

| Department ID | Label | Responsibility |
|---|---|---|
| `athlete_data` | Athlete Data | Connect external sources, normalize athlete profile, Garmin daily health, activities, and recovery signals. |
| `condition_assessment` | Condition Assessment | Evaluate current fitness/readiness baseline and prepare evidence for goal plausibility scoring. |
| `endurance_planning` | Endurance Planning | Create running/cycling plan structures and workout intents. |
| `strength_cross_training` | Strength & Cross-Training | Manage strength/cross-training constraints, dumbbell/bodyweight templates, and load compatibility. |
| `safety_policy` | Safety & Policy | Enforce recovery, load progression, injury/pain, and approval gates. |
| `calendar_execution` | Calendar Execution | Convert approved workouts into Garmin calendar/workout-builder operations later; v1 is read-only/dry-run metadata only. |
| `coaching_review` | Coaching Review | Produce athlete-facing summaries, review packets, and future plan adjustment recommendations. |

The first Garmin pull primarily belongs to `athlete_data`; the normalized snapshot feeds `condition_assessment` later.

---

## Proposed files

### New files

- `operating_model_packs/athlete_ops/manifest.yml`
- `operating_model_packs/athlete_ops/departments.yml`
- `operating_model_packs/athlete_ops/operations.yml`
- `operating_model_packs/athlete_ops/tools.yml`
- `operating_model_packs/athlete_ops/policies.yml`
- `operating_model_packs/athlete_ops/programs.yml`
- `operating_model_packs/athlete_ops/artifacts.yml`
- `operating_model_packs/athlete_ops/evaluations.yml`
- `backend/application/services/athlete_ops_setup.py`
- `backend/application/services/garmin_connector.py`
- `backend/application/services/athlete_training.py`
- `backend/infrastructure/orm/models/athlete_training.py`
- `backend/infrastructure/orm/management/commands/setup_athlete_ops_company.py`
- `backend/infrastructure/orm/management/commands/sync_garmin_athlete_data.py`
- `backend/tests/unit/services/test_athlete_ops_setup.py`
- `backend/tests/unit/services/test_garmin_connector.py`
- `backend/tests/unit/services/test_athlete_training_sync.py`
- `backend/tests/unit/management/test_setup_athlete_ops_company.py`
- `backend/tests/unit/management/test_sync_garmin_athlete_data.py`

### Modified files

- `backend/pyproject.toml`
  - Add optional/normal dependency: `garminconnect>=0.3.5` and likely `curl_cffi>=0.10.0` if needed by the Garmin library.
- `backend/infrastructure/orm/models/__init__.py`
  - Export `athlete_training` models.
- `backend/infrastructure/orm/models/credentials.py`
  - Add `("garmin", "Garmin Connect")` to `APIKey.PROVIDER_CHOICES`.
- New migration, likely `backend/infrastructure/orm/migrations/0098_athlete_training_garmin.py`.
- Potentially `backend/config/settings.py`
  - Add safe connector timeout/settings if not handled purely in service.

---

## Data model v1

Add a focused durable training data model. Keep it minimal.

### `AthleteProfile`

Purpose: company-scoped athlete profile and broad constraints.

Fields:

- `id UUID`
- `organization FK`
- `company FK(Graph)` unique
- `created_by FK(User, nullable)`
- `display_name CharField`
- `metadata_json JSONField`
  - Garmin profile fragments, demographics if available, user-supplied constraints later.
- `created_at`, `updated_at`

### `TrainingGoal`

Purpose: target event/goal contract.

Fields:

- `id UUID`
- `organization FK`
- `company FK(Graph)`
- `athlete_profile FK(AthleteProfile)`
- `goal_type CharField`, e.g. `race`
- `sport CharField`, e.g. `running`
- `event_name CharField`
- `event_date DateField(null=True)`
- `target_json JSONField`, e.g. `{ "type": "finish_time", "value": "02:59:59" }`
- `status CharField`, choices `draft`, `active`, `completed`, `archived`
- `created_at`, `updated_at`

### `AthleteDataConnection`

Purpose: company-owned external data source registration without making credentials visible.

Fields:

- `id UUID`
- `organization FK`
- `company FK(Graph)`
- `athlete_profile FK(AthleteProfile)`
- `provider CharField`, v1 `garmin`
- `credential FK(APIKey, nullable)`
- `status CharField`, choices `needs_credentials`, `ready`, `syncing`, `error`, `disabled`
- `last_synced_at DateTime(null=True)`
- `last_error TextField(blank=True)`
- `metadata_json JSONField`, safe non-secret config only
- uniqueness on `(company, provider)`

### `GarminDailySnapshot`

Purpose: one normalized daily health/readiness row per athlete/date.

Fields:

- `id UUID`
- `organization FK`
- `company FK(Graph)`
- `athlete_profile FK(AthleteProfile)`
- `snapshot_date DateField`
- `source CharField(default="garmin")`
- normalized nullable fields:
  - `sleep_score PositiveSmallIntegerField(null=True)`
  - `sleep_seconds PositiveIntegerField(null=True)`
  - `resting_hr PositiveSmallIntegerField(null=True)`
  - `hrv_status CharField(blank=True)`
  - `hrv_value FloatField(null=True)`
  - `body_battery_avg PositiveSmallIntegerField(null=True)`
  - `body_battery_min PositiveSmallIntegerField(null=True)`
  - `stress_avg PositiveSmallIntegerField(null=True)`
  - `training_readiness_score PositiveSmallIntegerField(null=True)`
  - `training_status CharField(blank=True)`
  - `vo2max_running FloatField(null=True)`
  - `vo2max_cycling FloatField(null=True)`
- `raw_json JSONField(default=dict)` with sanitized/source payload fragments only.
- unique `(athlete_profile, snapshot_date, source)`.

### `TrainingActivitySummary`

Purpose: normalized activity summaries for recent runs/rides/strength sessions.

Fields:

- `id UUID`
- `organization FK`
- `company FK(Graph)`
- `athlete_profile FK(AthleteProfile)`
- `source CharField(default="garmin")`
- `external_activity_id CharField`
- `sport CharField`
- `started_at DateTimeField(null=True)`
- `duration_seconds PositiveIntegerField(null=True)`
- `distance_meters FloatField(null=True)`
- `avg_hr PositiveSmallIntegerField(null=True)`
- `max_hr PositiveSmallIntegerField(null=True)`
- `avg_power FloatField(null=True)`
- `training_load FloatField(null=True)`
- `aerobic_training_effect FloatField(null=True)`
- `anaerobic_training_effect FloatField(null=True)`
- `raw_json JSONField(default=dict)` sanitized summary only.
- unique `(athlete_profile, source, external_activity_id)`.

---

## Garmin connector v1

### Credential strategy

Use two paths:

1. **Test/fake path**: fake Garmin client injected into service. Required for unit tests.
2. **Local real path**: management command reads credentials from env or stored `APIKey` later.

Recommended v1 real credential sources:

- `GARMIN_EMAIL`
- `GARMIN_PASSWORD`
- optional interactive MFA callback for command-line use.

Do not store Mike's credentials in repo or plan files. Do not print secrets. Do not log Garmin raw auth responses.

### Service design

`backend/application/services/garmin_connector.py`

Define:

```python
@dataclass(frozen=True)
class GarminCredentials:
    email: str
    password: str

@dataclass(frozen=True)
class GarminPullWindow:
    start_date: date
    end_date: date
    activities_limit: int = 100

class GarminConnectorError(RuntimeError): ...

class GarminConnector:
    def __init__(self, credentials: GarminCredentials, *, client_factory=None, token_store_path: str | None = None): ...
    def fetch_profile(self) -> dict[str, Any]: ...
    def fetch_daily_snapshot(self, target_date: date) -> dict[str, Any]: ...
    def fetch_recent_activities(self, *, start_date: date, end_date: date, limit: int = 100) -> list[dict[str, Any]]: ...
    def fetch_window(self, window: GarminPullWindow) -> dict[str, Any]: ...
```

Implementation should wrap `garminconnect.Garmin` behind a tiny adapter so tests do not import or call the real package.

### Normalization service

`backend/application/services/athlete_training.py`

Define:

```python
def sync_garmin_window(
    *,
    company: Graph,
    athlete_profile: AthleteProfile,
    connector: GarminConnectorProtocol,
    start_date: date,
    end_date: date,
    initiated_by: User | None = None,
) -> dict[str, Any]:
    ...
```

Return:

```json
{
  "status": "ok",
  "provider": "garmin",
  "daily_snapshots_upserted": 14,
  "activities_upserted": 27,
  "window": {"start_date": "...", "end_date": "..."},
  "missing_fields": ["training_readiness", "cycling_vo2max"]
}
```

---

## Setup command behavior

### `setup_athlete_ops_company`

Command:

```bash
uv run python manage.py setup_athlete_ops_company \
  --company-name "Mike AthleteOps" \
  --external-ref "athleteops-mike" \
  --goal-event "Marine Corps Marathon" \
  --goal-date "2026-10-25" \
  --target-finish-time "02:59:59"
```

Expected behavior:

- Resolve default org/user.
- Create/reuse `Graph` company with `external_source="athlete_ops"` and supplied `external_ref`.
- Install `athlete_ops` pack for company if pack service supports it cleanly.
- Create/reuse all 7 `DepartmentRegistry` rows for the organization.
- Create/reuse `AthleteProfile` for company.
- Create/reuse active `TrainingGoal` if supplied.
- Create/reuse `AthleteDataConnection(provider="garmin", status="needs_credentials")`.
- Print JSON summary with IDs and department slugs.

### `sync_garmin_athlete_data`

Command:

```bash
GARMIN_EMAIL="..." GARMIN_PASSWORD="..." \
uv run python manage.py sync_garmin_athlete_data \
  --company-ref "athleteops-mike" \
  --days 112
```

Expected behavior:

- Find company by `external_source="athlete_ops"`, `external_ref`.
- Find profile and Garmin connection.
- Login to Garmin.
- Pull recent daily snapshots and activity summaries.
- Upsert normalized rows.
- Update connection status + `last_synced_at`.
- Print sanitized JSON summary.
- On missing credentials, return clear non-secret error.

---

## Implementation tasks

### Task 1: Create an isolated worktree/branch

**Objective:** Avoid dirty `main` state and unrelated Atlas/media files.

**Files:** none modified in main worktree.

**Steps:**

1. From `C:/Users/mathi/projects/forgegraph`, create a worktree:

```bash
git fetch origin main
git worktree add ../forgegraph-worktrees/athleteops-garmin -b feature/athleteops-garmin origin/main
```

2. Verify clean status:

```bash
git status --short
```

Expected: empty.

---

### Task 2: Add AthleteOps operating model pack skeleton

**Objective:** Define the company departments and first operations in pack data.

**Files:**

- Create: `operating_model_packs/athlete_ops/manifest.yml`
- Create: `operating_model_packs/athlete_ops/departments.yml`
- Create: `operating_model_packs/athlete_ops/operations.yml`
- Create: `operating_model_packs/athlete_ops/tools.yml`
- Create: `operating_model_packs/athlete_ops/policies.yml`
- Create: `operating_model_packs/athlete_ops/programs.yml`
- Create: `operating_model_packs/athlete_ops/artifacts.yml`
- Create: `operating_model_packs/athlete_ops/evaluations.yml`
- Test: `backend/tests/unit/services/test_operating_model_pack_health.py` may need extension or new `test_athlete_ops_pack_health.py`.

**Verification:**

```bash
cd backend
UV_PROJECT_ENVIRONMENT=.venv-test-athleteops uv run python manage.py check
UV_PROJECT_ENVIRONMENT=.venv-test-athleteops uv run pytest tests/unit/services/test_operating_model_pack_health.py -v
```

Expected: pack parser accepts `athlete_ops` without breaking `digital_marketing_pro`.

---

### Task 3: Add athlete training models and migration

**Objective:** Persist athlete profile, goal, connection, daily snapshots, and activities as backend-owned state.

**Files:**

- Create: `backend/infrastructure/orm/models/athlete_training.py`
- Modify: `backend/infrastructure/orm/models/__init__.py`
- Create: `backend/infrastructure/orm/migrations/0098_athlete_training_garmin.py`
- Modify: `backend/infrastructure/orm/models/credentials.py`

**Test first:** create model tests in `backend/tests/unit/services/test_athlete_training_sync.py` validating uniqueness and upsert behavior after service exists. If doing pure migration first, run Django checks/migrations.

**Verification:**

```bash
cd backend
UV_PROJECT_ENVIRONMENT=.venv-test-athleteops uv run python manage.py makemigrations --check --dry-run
UV_PROJECT_ENVIRONMENT=.venv-test-athleteops uv run python manage.py check
```

Expected: no model drift after committed migration; check passes.

---

### Task 4: Add AthleteOps setup service

**Objective:** Idempotently create/reuse the AthleteOps company, departments, athlete profile, goal, and Garmin data connection.

**Files:**

- Create: `backend/application/services/athlete_ops_setup.py`
- Create: `backend/tests/unit/services/test_athlete_ops_setup.py`

**Key tests:**

- Creates exactly 7 active departments with expected slugs.
- Re-running setup does not duplicate departments/company/profile/connection.
- Creates a `TrainingGoal` when goal args are provided.
- Company has `external_source="athlete_ops"` and caller-provided `external_ref`.
- Department metadata includes pack/source and responsibilities.

**Verification:**

```bash
cd backend
UV_PROJECT_ENVIRONMENT=.venv-test-athleteops uv run pytest tests/unit/services/test_athlete_ops_setup.py -v
```

---

### Task 5: Add setup management command

**Objective:** Provide a real operator entry point for local setup.

**Files:**

- Create: `backend/infrastructure/orm/management/commands/setup_athlete_ops_company.py`
- Create: `backend/tests/unit/management/test_setup_athlete_ops_company.py`

**Verification:**

```bash
cd backend
UV_PROJECT_ENVIRONMENT=.venv-test-athleteops uv run pytest tests/unit/management/test_setup_athlete_ops_company.py -v
UV_PROJECT_ENVIRONMENT=.venv-test-athleteops uv run python manage.py setup_athlete_ops_company --help
```

Expected: command prints help and tests pass.

---

### Task 6: Add Garmin dependency and connector adapter

**Objective:** Wrap Garmin Connect access behind a testable connector service.

**Files:**

- Modify: `backend/pyproject.toml`
- Create: `backend/application/services/garmin_connector.py`
- Create: `backend/tests/unit/services/test_garmin_connector.py`

**Implementation notes:**

- Import `garminconnect` lazily so unit tests and environments without credentials do not try real login.
- Redact email/password from exceptions/logs.
- Allow fake client injection.
- Use a configurable token store path under `.hermes/garmin_tokens/<company_id>/` or a safe temp path for command runs. Do not commit token files.

**Verification:**

```bash
cd backend
UV_PROJECT_ENVIRONMENT=.venv-test-athleteops uv sync --all-groups
UV_PROJECT_ENVIRONMENT=.venv-test-athleteops uv run pytest tests/unit/services/test_garmin_connector.py -v
```

---

### Task 7: Add Garmin normalization/upsert service

**Objective:** Turn raw Garmin responses into durable `GarminDailySnapshot` and `TrainingActivitySummary` rows.

**Files:**

- Create/Modify: `backend/application/services/athlete_training.py`
- Extend: `backend/tests/unit/services/test_athlete_training_sync.py`

**Key tests:**

- Upserts daily snapshots by `(athlete_profile, date, source)`.
- Upserts activities by `(athlete_profile, source, external_activity_id)`.
- Handles missing Garmin fields without crashing.
- Returns `missing_fields` for unavailable values.
- Does not store secrets in `raw_json`.

**Verification:**

```bash
cd backend
UV_PROJECT_ENVIRONMENT=.venv-test-athleteops uv run pytest tests/unit/services/test_athlete_training_sync.py -v
```

---

### Task 8: Add Garmin sync management command

**Objective:** Provide local/operator real-data pull via env credentials.

**Files:**

- Create: `backend/infrastructure/orm/management/commands/sync_garmin_athlete_data.py`
- Create: `backend/tests/unit/management/test_sync_garmin_athlete_data.py`

**Command examples:**

```bash
GARMIN_EMAIL="..." GARMIN_PASSWORD="..." \
UV_PROJECT_ENVIRONMENT=.venv-test-athleteops uv run python manage.py sync_garmin_athlete_data \
  --company-ref athleteops-mike \
  --days 112
```

**Test expectations:**

- Missing env credentials returns a clear command error.
- Fake connector path can be injected/mocked and writes expected rows.
- Command output is sanitized JSON.

---

### Task 9: Run focused verification

**Objective:** Prove the setup and Garmin ingestion foundation works without real credentials.

**Commands:**

```bash
cd backend
UV_PROJECT_ENVIRONMENT=.venv-test-athleteops uv run ruff check application/services/athlete_ops_setup.py application/services/garmin_connector.py application/services/athlete_training.py infrastructure/orm/management/commands/setup_athlete_ops_company.py infrastructure/orm/management/commands/sync_garmin_athlete_data.py tests/unit/services/test_athlete_ops_setup.py tests/unit/services/test_garmin_connector.py tests/unit/services/test_athlete_training_sync.py tests/unit/management/test_setup_athlete_ops_company.py tests/unit/management/test_sync_garmin_athlete_data.py
UV_PROJECT_ENVIRONMENT=.venv-test-athleteops uv run pytest tests/unit/services/test_athlete_ops_setup.py tests/unit/services/test_garmin_connector.py tests/unit/services/test_athlete_training_sync.py tests/unit/management/test_setup_athlete_ops_company.py tests/unit/management/test_sync_garmin_athlete_data.py -v
UV_PROJECT_ENVIRONMENT=.venv-test-athleteops uv run python manage.py check
```

Use Mike's known Windows/Git Bash workaround: `UV_PROJECT_ENVIRONMENT=.venv-test-athleteops` rather than reusing a problematic repo/container `.venv`.

---

### Task 10: Optional real Garmin smoke test

**Objective:** Pull Mike's actual Garmin data only if he provides credentials in environment variables locally.

**Prerequisite:** Mike explicitly provides/sets Garmin credentials. Do not ask for credentials in chat. Prefer Mike entering them into his local shell.

**Commands:**

```bash
cd backend
UV_PROJECT_ENVIRONMENT=.venv-test-athleteops uv run python manage.py setup_athlete_ops_company \
  --company-name "Mike AthleteOps" \
  --external-ref "athleteops-mike" \
  --goal-event "Marine Corps Marathon" \
  --goal-date "2026-10-25" \
  --target-finish-time "02:59:59"

GARMIN_EMAIL="..." GARMIN_PASSWORD="..." \
UV_PROJECT_ENVIRONMENT=.venv-test-athleteops uv run python manage.py sync_garmin_athlete_data \
  --company-ref "athleteops-mike" \
  --days 112
```

**Expected output:** sanitized JSON with counts for `daily_snapshots_upserted` and `activities_upserted`.

---

## Acceptance criteria

- AthleteOps pack exists and validates without breaking existing pack health.
- Setup service/command creates a company, 7 departments, athlete profile, training goal, and Garmin connection idempotently.
- Garmin connector supports fake-client tests and real env-credential command path.
- Normalized Garmin daily snapshots and activity summaries persist in backend-owned DB tables.
- Sync command updates connection status and returns sanitized counts.
- No secrets appear in logs, command output, raw JSON, fixtures, or tests.
- Existing Atlas/digital marketing workflows remain untouched.
- Focused tests, `ruff check`, and `python manage.py check` pass.

---

## Risks / tradeoffs

1. **Garmin unofficial API fragility**
   - `python-garminconnect` uses Garmin Connect endpoints that may change or rate-limit.
   - Mitigation: adapter boundary, graceful errors, no product logic directly tied to raw payload shape.

2. **MFA/login friction**
   - Garmin may require MFA.
   - Mitigation: command-line MFA callback later; v1 can report `mfa_required` cleanly if unavailable.

3. **Credential storage**
   - Storing Garmin password is sensitive.
   - Mitigation: v1 real sync via local env only; `APIKey(provider="garmin")` support can be added but avoid UI credential flows until security policy is reviewed.

4. **Over-modeling**
   - Too many training models too early could slow iteration.
   - Mitigation: only profile, goal, connection, daily snapshot, activity summary now.

5. **Dirty main worktree**
   - There are unrelated untracked/modified files.
   - Mitigation: implement in a clean git worktree.

---

## Next plan after this foundation

After this plan is implemented and verified, the next plan should be:

> `Goal in + Garmin data pulled -> Current condition assessment + plausibility score out`

That next phase should add:

- Assessment service.
- Sub-3 marathon target pace conversion.
- Performance proximity/run-base/recovery/time/constraint scoring.
- Assessment output schema.
- Tests using synthetic Garmin histories.
