# Legacy Tutorial Video Process Evaluation: 2026-05-08

## Capture

- Command:
  `PLAYWRIGHT_RUNTIME_TARGET=docker PLAYWRIGHT_REUSE_EXISTING_SERVER=true PLAYWRIGHT_DEMO_CAPTURE=true PLAYWRIGHT_DEMO_CAPTURE_DIR=logs/legacy-tutorial-playwright-output npx playwright test --config=playwright.demo.config.ts __tests__/demo-captures/legacy-tutorial-videos.spec.ts --project=demo-chromium`
- Result: 5 passed.
- Stable outputs replaced:
  - `01-registration.webm`
  - `02-company-objective.webm`
  - `03-create-first-agent.webm`
  - `04-create-first-judge.webm`
  - `05-run-first-judge.webm`

## Evaluation

- Registration is clear enough for tutorial use. The route-aware copy explains the workspace goal, and the loading state reads as account creation.
- Company objective and suggested setup are now strong. The guide overlay is absent by default, panels do not overlap, and the step names are understandable.
- Department selection is usable but dense. The optional-skill area is good for product truth, but the clip needs narration or callouts in editing to explain why the selected skill matters.
- Judge creation is functional and approval-gated. The task detail and judge form fit without clipping, but the page has a lot of competing text for a first-time viewer.
- Judge evaluation is the clearest proof step. The status, grade, and pass-rate band are visible after evaluation.

## Improvements Made During This Pass

- Replaced repeated login recording in clips 02-05 with backend-token browser setup.
- Regenerated all stable tutorial clips after the capture-spec change.
- Kept raw Playwright output under ignored logs while preserving stable tutorial assets in docs.

## Remaining Gaps

- Some clips still begin with a brief page-loading frame because Playwright records from page creation. Edited tutorial output should trim the first fraction of a second for clips 03-05.
- The judge/task screen is still information-heavy. A future product pass should add a compact tutorial-friendly task summary band without changing backend ownership.
- The tutorial sequence covers registration, first company setup, first department selection, first judge creation, and first judge evaluation. It does not yet show inventory, approvals, or visual asset brief work from Phase 6.

## Decision

Use the regenerated clips as the current tutorial source material. Next capture iteration should add a second sequence for Phase 6 operator work: company workspace, inventory, approval tasks, reservation proof, operation status, and visual asset brief deliverables.
