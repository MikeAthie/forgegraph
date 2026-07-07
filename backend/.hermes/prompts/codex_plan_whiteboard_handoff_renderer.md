You are Codex running in PLAN MODE for the ForgeGraph backend repo.

IMPORTANT: Planning only. Do not implement code. Do not modify source files. Your only allowed write is one markdown plan under `backend/.hermes/plans/` (or `.hermes/plans/` relative to this backend working directory). Inspect the repo and write a concrete implementation plan.

User/product context:
- Mike wants ForgeGraph/Atlas to produce polished client-facing agency deliverables, not Markdown dumps or plain internal reports.
- Hermes is allowed as inspiration, but ForgeGraph must own runtime behavior independently. Do not make ForgeGraph depend on Hermes at runtime.
- The immediate diagnosis: ForgeGraph's generated strategy report content is aligned, but the format is below agency standard. It is a plain memo renderer, not a client handoff package.
- Earlier professional package shape that looked good: executive/client approval packet first, then department deliverables as separate rendered artifacts: strategy/research brief, brand content pack, channel calendar, CRM/WhatsApp scripts, measurement plan, QA report, email body, manifest, client-safe ZIP, and campaign/hero assets.
- Current ForgeGraph output path to improve includes `application/services/strategy_report_builder.py`, which has a basic `_markdown_to_html` and hand-written PDF text stream.
- There is already newer generic formatting infrastructure in:
  - `application/services/deliverable_formatting.py`
  - `application/services/deliverable_format_renderers.py`
  - `application/services/deliverable_format_profiles.py`
  - `application/services/deliverable_format_quality.py`
- There is also a more prompt-specific package path in `application/services/atlas_prompt_delivery.py` that creates `Legacy_Optical_Noir_Handoff.html`, PDF, assets, manifest, ZIP, but it is too specific and renders department content as escaped text blocks.
- We want to turn this into a generic, whiteboard/kanban-compatible ForgeGraph handoff packaging capability.

Hermes kanban ideas to inspect for inspiration only:
- Local Hermes checkout likely exists at `C:/Users/mathi/AppData/Local/hermes/hermes-agent`.
- Inspect these if available:
  - `hermes_cli/kanban_db.py`
  - `hermes_cli/kanban.py`
  - `tools/kanban_tools.py`
  - `plugins/kanban/`
  - docs under `website/docs/user-guide/features/kanban*.md`
- Useful ideas to adapt conceptually, not copy verbatim: durable board/task state, task links, comments/tail/activity, worker dispatch boundaries, attachments/artifacts, task status transitions, profile/lane specialization, and final completion receipts.
- Do NOT add a Hermes dependency or shell out to Hermes. Translate ideas into ForgeGraph-native primitives.

ForgeGraph architectural constraints:
- Keep ForgeGraph generic and business-agnostic.
- Put Atlas/Legacy/agency style in format profiles/config/metadata, not hardcoded renderers/models.
- Prefer existing primitives before new models/migrations: `CompanyProgram`, `ProgramStageState`, `ServiceDeliverable`, `Asset`, `AssetVersion`, `TaskRoutingRecord`, existing whiteboard models if present.
- Client-facing ZIPs should not include Markdown unless explicitly requested; HTML/PDF/PNG/JSON manifest are preferred for clients.
- Source content remains canonical in ServiceDeliverables/AssetVersions; HTML/PDF/email/ZIP are derived artifacts with provenance.
- Derived artifacts must be persisted as real `AssetVersion`s with provenance, not loose files only.
- Provenance should include renderer name/version, profile ref/hash, source deliverable IDs, source asset version IDs/hashes, request/idempotency, quality gate result, and output hash.
- Connector limitations should be explicit and separate from deliverable planning.
- No claim of live publishing/delivery unless receipts exist.

Planning deliverable requirements:
- Save the plan as `.hermes/plans/YYYY-MM-DD_HHMMSS-whiteboard-client-handoff-renderer.md`.
- Start with the exact header structure:
  # Whiteboard Client Handoff Renderer Implementation Plan
  > **For Hermes:** Use subagent-driven-development skill to implement this plan task-by-task.
  **Goal:** ...
  **Architecture:** ...
  **Tech Stack:** ...
- Include a PR roadmap / slice sequence. Mike may review an existing PR first, so structure it so implementation can wait for current PR review.
- Include exact likely files to modify/create and focused tests to add.
- Include TDD-style tasks with verification commands.
- Make the plan actionable for Codex implementation later.
- Include a section: "Hermes Kanban ideas to borrow" mapping Hermes ideas to ForgeGraph-native implementation choices.
- Include a section: "What not to do" covering no hardcoded Legacy/Atlas logic, no Markdown in client ZIP by default, no Hermes runtime dependency, no live-send claims without receipts.
- Include a section: "Acceptance criteria" with programmatic quality gates and a real fixture/smoke package run.
- Include Windows/Git Bash verification commands using Mike's known ForgeGraph env:
  `UV_PROJECT_ENVIRONMENT=.venv-test-department-pipeline uv run python -m pytest ... -q`
  `UV_PROJECT_ENVIRONMENT=.venv-test-department-pipeline uv run ruff check ...`
  `UV_PROJECT_ENVIRONMENT=.venv-test-department-pipeline uv run python manage.py check`

Do not produce generic `src/...` paths. Inspect the actual repository and use actual paths. Do not implement. Write only the plan markdown file.