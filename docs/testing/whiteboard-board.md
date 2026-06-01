# Whiteboard Board Command Center

`WorkWhiteboard` is the durable project/work-effort context. The board projection is built from DB truth and does not introduce a separate board table.

`TaskRoutingRecord` is the Kanban card. `DepartmentRegistry` is the lane/department owner. Board-only card metadata such as title, customer visibility, safe link IDs, blocker reason, and evidence references lives in sanitized `metadata_json` / `resolution_json`.

`TaskRecord` is execution projection data only. A `TaskRecord` without a same-company `TaskRoutingRecord` for the whiteboard must never appear as a board card.

Board `project` payloads use generic workboard language as the primary shape:
`project_name`, `work_status`, generic context summaries, and
`semantic_aliases` for legacy compatibility. Legacy `title` and `status` remain
present for existing clients, but primary tests should assert `project_name` and
`work_status` first.

The routing or traffic department owns board structure: card creation, reassignment, priority, due date, close/reopen, and structural status changes. Assigned department members with company access may update their own card progress and attach sanitized evidence references. Customers receive read-only customer-safe board summaries. Other clients must receive no board/card access.

`ready_for_review` is only the board status. The board contract also emits `review_kind` / `review` so clients can distinguish department review, human approval, and automated evaluation gates. Human approval is satisfied only by `ApprovalTask` or a linked `DecisionRecord`; department status updates cannot complete a pending human approval card. Automated gates are represented by same-company `EvaluationRun` / `EvaluationScorecard` IDs only. Customer-safe board payloads hide internal approval/evaluation IDs, including secondary decision and scorecard IDs, unless the exact link is explicitly marked customer-visible.

Kafka is transport only. Board events use topic `forgegraph.whiteboard.board.events.v1`, schema version `whiteboard_board_event_v1`, and Kafka key `whiteboard_id` so ordering is preserved per project. Events contain IDs and routing metadata only; they must not include raw message bodies, raw prompts, evidence bundles, provider payloads, private configs, secrets, or traces.

Redis stores a fast board snapshot at the whiteboard snapshot key with `:board` suffix. It is a cache only and is rebuilt from Postgres by `rebuild_whiteboard_board_snapshot_from_db`.

Run targeted checks:

```bash
cd backend
python -m pytest tests/unit/services/test_whiteboard_board.py tests/unit/api/test_whiteboard_board_api.py tests/unit/services/test_whiteboard_board_kafka.py
python -m ruff check application/services/whiteboard_boards.py application/services/whiteboard_board_kafka.py adapters/api/whiteboards tests/unit/services/test_whiteboard_board.py tests/unit/api/test_whiteboard_board_api.py tests/unit/services/test_whiteboard_board_kafka.py

cd ../frontend
npx tsc --noEmit
npx eslint components/company/WhiteboardPanel.tsx domain/repositories/whiteboardRepository.ts lib/api.ts __tests__/product-modes/fixtures.ts __tests__/product-modes/whiteboard-board.regression.spec.ts
USE_SQLITE=true npx playwright test __tests__/product-modes --project=chromium
```

Kafka broker integration remains opt-in. Default tests use fake publisher/consumer paths and receipt records.
