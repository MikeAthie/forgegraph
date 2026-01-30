# Phase 2: Intelligent Summarization

## Objective
Implement automatic summarization for long conversations, store summaries and extracted facts, and integrate summarization configuration across engine, backend, and frontend.

## Prerequisites
- Phase 1 complete (RedisMemoryStore, MessageBuffer, MemoryConfig plumbing)
- LLM client available in the Go engine
- Memory configuration JSON passed to StartRunRequest

---

## Task List

### P2-T01: Design Summarization Service Interface
**Files:**
- `engine/application/port/summarizer.go`
- `engine/domain/entity/summary.go`

- [x] Define Summarizer interface with Summarize and ExtractFacts.
- [x] Define SummarizeOptions (max tokens, model, preserve facts).
- [x] Create Summary and Fact domain entities with metadata.

```go
// engine/application/port/summarizer.go
package port

type Summarizer interface {
    Summarize(ctx context.Context, messages []entity.Message, opts SummarizeOptions) (*entity.Summary, error)
    ExtractFacts(ctx context.Context, messages []entity.Message) ([]entity.Fact, error)
}

type SummarizeOptions struct {
    MaxOutputTokens int
    PreserveFacts   bool
    Model           string
}

// engine/domain/entity/summary.go
package entity

type Summary struct {
    ID            string
    Content       string
    SourceCount   int
    FactsExtracted []Fact
    CreatedAt     time.Time
}

type Fact struct {
    Key         string
    Value       string
    Confidence  float64
    SourceNodeID string
}
```

**Acceptance Criteria:**
- [x] Interface defined with clear contracts
- [x] Summary entity captures metadata for retrieval
- [x] Fact entity includes confidence and source
- [x] Interface supports pluggable LLM backends

---

### P2-T02: Implement LLM-Based Summarizer
**Files:**
- `engine/adapter/summarizer/llm_summarizer.go`
- `engine/adapter/summarizer/llm_summarizer_test.go`

- [x] Implement LLMSummarizer with configurable model and retry.
- [x] Add prompt template for summary + facts JSON output.
- [x] Parse JSON response into Summary and Fact entities.
- [x] Add exponential backoff for transient failures.
- [x] Add unit tests with mocked LLM client.

```go
type LLMSummarizer struct {
    client     LLMClient
    model      string
    maxRetries int
}

const summarizePrompt = `Summarize the conversation concisely, preserving key decisions and facts.
Return JSON: {"summary":"...","facts":[{"key":"...","value":"...","confidence":0.0}]}`
```

**Acceptance Criteria:**
- [x] Summaries are coherent and compact
- [x] Facts extracted with confidence scores
- [x] Summarization completes in <5s for 50 messages
- [x] Retry logic handles transient errors
- [x] Unit and integration tests pass

---

### P2-T03: Create Async Summarization Worker
**Files:**
- `engine/application/usecase/summarization_worker.go`
- `engine/application/usecase/summarization_worker_test.go`

- [x] Implement worker pool with bounded queue.
- [x] Provide Submit method for enqueueing requests.
- [x] Store summaries in Redis on success.
- [x] Support graceful shutdown with context cancellation.
- [x] Add unit tests for async behavior.

```go
type SummarizationRequest struct {
    RunID    string
    TenantID string
    Messages []entity.Message
    Callback func(*entity.Summary, error)
}
```

**Acceptance Criteria:**
- [x] Summarization runs asynchronously (non-blocking)
- [x] Worker pool size configurable (default 2)
- [x] Queue backpressure prevents overload
- [x] Callback invoked with result or error
- [x] Worker stops cleanly on shutdown

---

### P2-T04: Implement Smart Trigger for Summarization
**Files:**
- `engine/adapter/executor/prompt_executor.go`
- `engine/application/usecase/scheduler.go`

- [x] Add SummarizationConfig to MemoryConfig.
- [x] Track messagesSinceSummary in runContext.
- [x] Trigger summarization when buffer reaches threshold.
- [x] Keep last N recent messages after summarization.
- [x] Enforce cooldown before next summarization.
- [x] Add metrics for trigger counts.

```go
type SummarizationConfig struct {
    Enabled          bool
    TriggerThreshold int
    KeepRecentCount  int
    CooldownMessages int
    Model            string
}
```

**Acceptance Criteria:**
- [x] Trigger fires only at configured threshold
- [x] Recent messages preserved after summarization
- [x] Cooldown prevents repeated summaries
- [x] Per-graph config overrides defaults
- [x] Integration test verifies single summarization at 50 messages

---

### P2-T05: Store and Retrieve Summaries in Redis
**Files:**
- `engine/adapter/store/redis_memory_store.go`

- [x] Add StoreSummary/GetSummary/GetFact methods.
- [x] Use versioned keys for summary history.
- [x] Store facts as individual keys for lookup.
- [x] Enforce TTL (default 7 days).
- [x] Add unit tests for versioning and retrieval.

Key structure:
```
forgegraph:tenant:{tenant_id}:summary:{run_id}:current
forgegraph:tenant:{tenant_id}:summary:{run_id}:v{n}
forgegraph:tenant:{tenant_id}:facts:{run_id}:{fact_key}
```

**Acceptance Criteria:**
- [x] Current summary retrievable by run ID
- [x] Last 5 versions retained
- [x] Facts retrievable by fact key
- [x] Keys expire after TTL
- [x] Redis errors handled gracefully

---

### P2-T06: Prepend Summaries to Prompts
**Files:**
- `engine/adapter/executor/prompt_executor.go`

- [x] Prepend summary block before recent messages.
- [x] Format facts as key-value list.
- [x] Omit summary/facts section when empty.
- [x] Add integration test verifying prompt layout.

Prompt structure:
```
[System prompt]

Summary of earlier conversation:
{summary}

Key facts:
- key: value

[Recent messages]

[Current input]
```

**Acceptance Criteria:**
- [x] Summary included when available
- [x] Facts formatted consistently
- [x] No empty sections rendered
- [x] Prompt rendering verified by logs/tests

---

### P2-T07: Add Summarization Configuration to Django/Frontend
**Files:**
- `backend/infrastructure/orm/models.py`
- `backend/infrastructure/orm/migrations/0012_summarization_config.py`
- `backend/adapters/api/graphs/serializers.py`
- `frontend/components/graph-editor/dialogs/MemoryConfigDialog.tsx`

- [x] Add summarization fields to MemoryConfiguration model.
- [x] Create migration with defaults.
- [x] Serialize fields in API responses.
- [x] Add UI controls in Advanced section.
- [x] Validate threshold and keep_recent limits.

Model fields:
```python
summarization_enabled = models.BooleanField(default=False)
summarization_threshold = models.PositiveIntegerField(default=30)
summarization_keep_recent = models.PositiveIntegerField(default=10)
summarization_model = models.CharField(max_length=50, default='claude-haiku')
```

**Acceptance Criteria:**
- [x] API exposes summarization settings
- [x] Frontend can edit and save settings
- [x] Validation: threshold >= keep_recent + 10
- [x] Config flows to engine via memory_config_json

---

### P2-T08: Implement Cost Tracking for Summarization
**Files:**
- `engine/adapter/summarizer/cost_tracker.go`
- `backend/domain/entities/memory_usage.py`
- `backend/adapters/api/memory/usage_views.py`

- [x] Track tokens and costs per tenant in engine.
- [x] Persist daily usage in Django.
- [x] Expose usage API endpoint.
- [x] Add Prometheus metrics for summarization cost.
- [x] Add tests for cost calculation.

Pricing config (per 1K tokens):
```
claude-haiku: input 0.00025, output 0.00125
```

**Acceptance Criteria:**
- [x] Costs tracked per tenant and per day
- [x] API returns cost and token counts
- [x] Metrics exported for dashboards
- [x] Tests cover pricing calculation

---

## Acceptance Criteria (Phase 2 Overall)

1. Summarization service and worker integrated
2. Summaries stored and retrieved in Redis
3. Prompt includes summaries and facts when available
4. Summarization configuration editable in UI
5. Costs tracked and exposed via API/metrics
6. Unit and integration tests pass

## Status: DONE

## Dependencies

- Phase 1 complete

## Output

- [x] Summarizer interface and entities
- [x] LLM summarizer implementation + tests
- [x] Async summarization worker
- [x] Smart trigger logic in prompt executor
- [x] Redis summary/fact storage
- [x] Summarization config in Django and UI
- [x] Cost tracking and usage API
