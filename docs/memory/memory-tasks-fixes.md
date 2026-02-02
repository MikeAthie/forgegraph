# Memory System Fixes & Improvements Plan

## Objective
Address all critical, high, and medium priority issues identified during the Phase 1-3 implementation review. These fixes are required to make the memory system production-ready.

## Prerequisites
- Phases 1-3 of memory system implemented
- Access to all memory-related files across engine, backend, and frontend
- Test environment with Redis and PostgreSQL available

## Priority Legend
- 🔴 **Critical**: Must fix before production deployment
- 🟠 **High**: Fix within current sprint
- 🟡 **Medium**: Fix in next sprint

---

## Task List

### FIX-01: Robust JSON Extraction in LLM Summarizer ✅ COMPLETE

**Priority:** Critical
**Status:** ✅ Fully implemented and integrated.

**Files:**

- `engine/adapter/summarizer/json_extractor.go` ✅ Created
- `engine/adapter/summarizer/json_extractor_test.go` ✅ Created (32 tests passing, benchmarks <1ms)
- `engine/adapter/summarizer/llm_summarizer.go` ✅ Integrated

**Problem:**
Current `extractJSON()` function uses simple string index to find JSON boundaries. Nested braces, escaped characters, and malformed responses break extraction.

```go
// Current broken implementation
func extractJSON(content string) (string, error) {
    start := strings.Index(trimmed, "{")
    end := strings.LastIndex(trimmed, "}")
    // Fails on: {"text": "Use {this} syntax"}
}
```

**Implementation:**

- [ ] Replace naive string extraction with proper brace-counting parser:
  ```go
  // engine/adapter/summarizer/json_extractor.go

  package summarizer

  import (
      "encoding/json"
      "errors"
      "strings"
  )

  var (
      ErrNoJSONFound     = errors.New("no JSON object found in response")
      ErrInvalidJSON     = errors.New("extracted content is not valid JSON")
      ErrUnbalancedBraces = errors.New("unbalanced braces in response")
  )

  // ExtractJSON finds and extracts the first valid JSON object from a string.
  // Handles nested objects, escaped characters, and surrounding text.
  func ExtractJSON(content string) (string, error) {
      trimmed := strings.TrimSpace(content)

      // Fast path: try direct unmarshal first
      var test map[string]any
      if err := json.Unmarshal([]byte(trimmed), &test); err == nil {
          return trimmed, nil
      }

      // Find first opening brace
      start := strings.Index(trimmed, "{")
      if start == -1 {
          return "", ErrNoJSONFound
      }

      // Parse with brace counting, respecting strings
      end, err := findMatchingBrace(trimmed, start)
      if err != nil {
          return "", err
      }

      candidate := trimmed[start : end+1]

      // Validate extracted JSON
      if err := json.Unmarshal([]byte(candidate), &test); err != nil {
          return "", ErrInvalidJSON
      }

      return candidate, nil
  }

  // findMatchingBrace finds the index of the closing brace matching the opening brace at start.
  func findMatchingBrace(s string, start int) (int, error) {
      if s[start] != '{' {
          return -1, errors.New("start position must be an opening brace")
      }

      depth := 0
      inString := false
      escaped := false

      for i := start; i < len(s); i++ {
          c := s[i]

          // Handle escape sequences inside strings
          if escaped {
              escaped = false
              continue
          }

          if c == '\\' && inString {
              escaped = true
              continue
          }

          // Toggle string state on unescaped quotes
          if c == '"' {
              inString = !inString
              continue
          }

          // Only count braces outside strings
          if inString {
              continue
          }

          switch c {
          case '{':
              depth++
          case '}':
              depth--
              if depth == 0 {
                  return i, nil
              }
          }
      }

      return -1, ErrUnbalancedBraces
  }

  // ExtractJSONArray extracts the first valid JSON array from a string.
  func ExtractJSONArray(content string) (string, error) {
      trimmed := strings.TrimSpace(content)

      // Fast path
      var test []any
      if err := json.Unmarshal([]byte(trimmed), &test); err == nil {
          return trimmed, nil
      }

      start := strings.Index(trimmed, "[")
      if start == -1 {
          return "", ErrNoJSONFound
      }

      end, err := findMatchingBracket(trimmed, start)
      if err != nil {
          return "", err
      }

      candidate := trimmed[start : end+1]

      if err := json.Unmarshal([]byte(candidate), &test); err != nil {
          return "", ErrInvalidJSON
      }

      return candidate, nil
  }

  func findMatchingBracket(s string, start int) (int, error) {
      if s[start] != '[' {
          return -1, errors.New("start position must be an opening bracket")
      }

      depth := 0
      inString := false
      escaped := false

      for i := start; i < len(s); i++ {
          c := s[i]

          if escaped {
              escaped = false
              continue
          }

          if c == '\\' && inString {
              escaped = true
              continue
          }

          if c == '"' {
              inString = !inString
              continue
          }

          if inString {
              continue
          }

          switch c {
          case '[':
              depth++
          case ']':
              depth--
              if depth == 0 {
                  return i, nil
              }
          }
      }

      return -1, ErrUnbalancedBraces
  }
  ```

- [ ] Update `llm_summarizer.go` to use new extractor:
  ```go
  // In Summarize method, replace:
  // jsonStr, err := extractJSON(response.Content)
  // With:
  jsonStr, err := ExtractJSON(response.Content)
  if err != nil {
      log.Warn("JSON extraction failed, attempting cleanup",
          "error", err,
          "content_length", len(response.Content),
      )
      // Try with markdown code block removal
      cleaned := stripMarkdownCodeBlocks(response.Content)
      jsonStr, err = ExtractJSON(cleaned)
      if err != nil {
          return nil, fmt.Errorf("failed to extract JSON from LLM response: %w", err)
      }
  }
  ```

- [ ] Add helper to strip markdown code blocks:
  ```go
  func stripMarkdownCodeBlocks(content string) string {
      // Remove ```json ... ``` blocks
      re := regexp.MustCompile("(?s)```(?:json)?\\s*(.+?)\\s*```")
      if matches := re.FindStringSubmatch(content); len(matches) > 1 {
          return matches[1]
      }
      return content
  }
  ```

- [ ] Write comprehensive tests:
  ```go
  // engine/adapter/summarizer/json_extractor_test.go

  func TestExtractJSON_SimpleObject(t *testing.T) {
      input := `{"key": "value"}`
      result, err := ExtractJSON(input)
      require.NoError(t, err)
      assert.Equal(t, input, result)
  }

  func TestExtractJSON_NestedBraces(t *testing.T) {
      input := `Here is the summary: {"text": "Use {curly braces} for objects", "count": 5}`
      result, err := ExtractJSON(input)
      require.NoError(t, err)
      assert.Contains(t, result, "{curly braces}")
  }

  func TestExtractJSON_EscapedQuotes(t *testing.T) {
      input := `{"message": "He said \"hello\" to me"}`
      result, err := ExtractJSON(input)
      require.NoError(t, err)

      var parsed map[string]string
      require.NoError(t, json.Unmarshal([]byte(result), &parsed))
      assert.Equal(t, `He said "hello" to me`, parsed["message"])
  }

  func TestExtractJSON_MarkdownCodeBlock(t *testing.T) {
      input := "Here's the JSON:\n```json\n{\"key\": \"value\"}\n```\nThat's all."
      cleaned := stripMarkdownCodeBlocks(input)
      result, err := ExtractJSON(cleaned)
      require.NoError(t, err)
      assert.Equal(t, `{"key": "value"}`, result)
  }

  func TestExtractJSON_ComplexNesting(t *testing.T) {
      input := `{
          "summary": "Discussion about {APIs}",
          "facts": [
              {"key": "language", "value": "Go"},
              {"key": "syntax", "value": "uses {} for blocks"}
          ],
          "metadata": {"nested": {"deep": "value"}}
      }`
      result, err := ExtractJSON(input)
      require.NoError(t, err)

      var parsed map[string]any
      require.NoError(t, json.Unmarshal([]byte(result), &parsed))
      assert.Equal(t, "Discussion about {APIs}", parsed["summary"])
  }

  func TestExtractJSON_NoJSON(t *testing.T) {
      input := "This is just plain text without any JSON"
      _, err := ExtractJSON(input)
      assert.ErrorIs(t, err, ErrNoJSONFound)
  }

  func TestExtractJSON_UnbalancedBraces(t *testing.T) {
      input := `{"key": "value"`
      _, err := ExtractJSON(input)
      assert.ErrorIs(t, err, ErrUnbalancedBraces)
  }

  func TestExtractJSON_SurroundingText(t *testing.T) {
      input := `
          I've analyzed the conversation. Here's my summary:

          {"summary": "User discussed project requirements", "facts": []}

          Let me know if you need more details.
      `
      result, err := ExtractJSON(input)
      require.NoError(t, err)
      assert.True(t, strings.HasPrefix(result, "{"))
      assert.True(t, strings.HasSuffix(result, "}"))
  }
  ```

**Success Criteria:**
- [x] `ExtractJSON` correctly handles nested braces inside JSON values
- [x] Escaped quotes inside strings don't break parsing
- [x] Markdown code blocks are stripped before extraction
- [x] Clear error types distinguish between "no JSON" and "invalid JSON"
- [x] All test cases pass including edge cases (32 tests passing)
- [x] Existing summarization integration tests still pass
- [x] Benchmark shows <1ms extraction time for typical responses (664ns - 5.8µs)

**Best Practices:**
- Use proper parsing instead of regex for nested structures
- Provide specific error types for different failure modes
- Include cleanup/fallback strategies for common LLM output formats
- Log extraction failures with context for debugging

---

### FIX-02: Cost Tracking Error Handling 🔴
**Priority:** Critical
**Status:** ❌ Incomplete.

**Files:**
- `engine/adapter/summarizer/llm_summarizer.go`
- `engine/adapter/summarizer/cost_tracker.go`
- `engine/adapter/metrics/memory_metrics.go`

**Problem:**
Cost tracking errors are silently ignored, leading to billing inaccuracies.

**Review Notes:**
- **Missing:** The Dead Letter Queue (DLQ) mechanism is missing from `cost_tracker.go`.
- **Incorrect:** The retry loop in `recordCostsWithRetry` does not check for non-retryable validation errors as planned.
- **Inconsistent:** The failure metric `memoryCostTrackingFailures` is not recorded in the main `Summarize` function upon failure.

```go
// Current - error ignored
_ = s.costs.RecordSummarizationUsage(ctx, tenantID, model, response.Usage)
```

**Implementation:**

- [ ] Add metric for cost tracking failures:
  ```go
  // engine/adapter/metrics/memory_metrics.go

  var (
      // ... existing metrics ...

      memoryCostTrackingFailures = promauto.NewCounterVec(
          prometheus.CounterOpts{
              Name: "forgegraph_memory_cost_tracking_failures_total",
              Help: "Total cost tracking failures by type",
          },
          []string{"operation", "error_type"},
      )

      memoryCostTrackingRetries = promauto.NewCounter(
          prometheus.CounterOpts{
              Name: "forgegraph_memory_cost_tracking_retries_total",
              Help: "Total cost tracking retry attempts",
          },
      )
  )

  func RecordCostTrackingFailure(operation, errorType string) {
      memoryCostTrackingFailures.WithLabelValues(operation, errorType).Inc()
  }

  func RecordCostTrackingRetry() {
      memoryCostTrackingRetries.Inc()
  }
  ```

- [ ] Update cost tracking call with retry and logging:
  ```go
  // engine/adapter/summarizer/llm_summarizer.go

  func (s *LLMSummarizer) Summarize(ctx context.Context, messages []entity.Message, opts SummarizeOptions) (*entity.Summary, error) {
      // ... existing code to call LLM ...

      // Record costs with retry
      if s.costs != nil && response.Usage != nil {
          if err := s.recordCostsWithRetry(ctx, tenantID, model, response.Usage); err != nil {
              // Log but don't fail the operation
              log.Error("failed to record summarization cost after retries",
                  "tenant_id", tenantID,
                  "model", model,
                  "input_tokens", response.Usage.InputTokens,
                  "output_tokens", response.Usage.OutputTokens,
                  "error", err,
              )
              metrics.RecordCostTrackingFailure("summarization", categorizeError(err))
          }
      }

      // ... rest of method ...
  }

  func (s *LLMSummarizer) recordCostsWithRetry(ctx context.Context, tenantID, model string, usage *LLMUsage) error {
      const maxRetries = 3
      var lastErr error

      for attempt := 1; attempt <= maxRetries; attempt++ {
          err := s.costs.RecordSummarizationUsage(ctx, tenantID, model, usage)
          if err == nil {
              return nil
          }

          lastErr = err

          // Don't retry on context cancellation
          if ctx.Err() != nil {
              return ctx.Err()
          }

          // Don't retry on validation errors
          if isValidationError(err) {
              return err
          }

          if attempt < maxRetries {
              metrics.RecordCostTrackingRetry()
              log.Warn("cost tracking failed, retrying",
                  "attempt", attempt,
                  "error", err,
              )
              time.Sleep(time.Duration(attempt*100) * time.Millisecond)
          }
      }

      return fmt.Errorf("cost tracking failed after %d attempts: %w", maxRetries, lastErr)
  }

  func categorizeError(err error) string {
      if err == nil {
          return "none"
      }
      errStr := err.Error()
      switch {
      case strings.Contains(errStr, "connection"):
          return "connection"
      case strings.Contains(errStr, "timeout"):
          return "timeout"
      case strings.Contains(errStr, "constraint"):
          return "constraint"
      default:
          return "unknown"
      }
  }

  func isValidationError(err error) bool {
      if err == nil {
          return false
      }
      errStr := err.Error()
      return strings.Contains(errStr, "invalid") ||
          strings.Contains(errStr, "validation") ||
          strings.Contains(errStr, "constraint")
  }
  ```

- [ ] Add dead letter queue for failed cost records:
  ```go
  // engine/adapter/summarizer/cost_tracker.go

  type CostTracker struct {
      db          *sql.DB
      deadLetter  chan CostRecord
      wg          sync.WaitGroup
  }

  type CostRecord struct {
      TenantID     string
      Model        string
      Operation    string
      InputTokens  int64
      OutputTokens int64
      Timestamp    time.Time
      RetryCount   int
  }

  func NewCostTracker(db *sql.DB) *CostTracker {
      ct := &CostTracker{
          db:         db,
          deadLetter: make(chan CostRecord, 1000),
      }
      ct.startDeadLetterProcessor()
      return ct
  }

  func (ct *CostTracker) startDeadLetterProcessor() {
      ct.wg.Add(1)
      go func() {
          defer ct.wg.Done()
          ticker := time.NewTicker(30 * time.Second)
          defer ticker.Stop()

          var batch []CostRecord

          for {
              select {
              case record := <-ct.deadLetter:
                  batch = append(batch, record)
                  if len(batch) >= 100 {
                      ct.processBatch(batch)
                      batch = batch[:0]
                  }
              case <-ticker.C:
                  if len(batch) > 0 {
                      ct.processBatch(batch)
                      batch = batch[:0]
                  }
              }
          }
      }()
  }

  func (ct *CostTracker) processBatch(records []CostRecord) {
      for _, record := range records {
          ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
          err := ct.insertRecord(ctx, record)
          cancel()

          if err != nil {
              log.Error("dead letter processing failed",
                  "tenant_id", record.TenantID,
                  "retry_count", record.RetryCount,
                  "error", err,
              )
              // Write to file as last resort
              ct.writeToFallbackFile(record)
          }
      }
  }

  func (ct *CostTracker) writeToFallbackFile(record CostRecord) {
      // Append to fallback file for manual recovery
      f, err := os.OpenFile("cost_tracking_fallback.jsonl", os.O_APPEND|os.O_CREATE|os.O_WRONLY, 0644)
      if err != nil {
          log.Error("failed to write to fallback file", "error", err)
          return
      }
      defer f.Close()

      data, _ := json.Marshal(record)
      f.Write(append(data, '\n'))
  }

  func (ct *CostTracker) QueueForRetry(record CostRecord) {
      select {
      case ct.deadLetter <- record:
          // Queued successfully
      default:
          // Queue full, log and drop
          log.Error("dead letter queue full, dropping cost record",
              "tenant_id", record.TenantID,
          )
          metrics.RecordCostTrackingFailure("summarization", "queue_full")
      }
  }
  ```

- [ ] Write tests:
  ```go
  func TestCostTracking_RetryOnTransientError(t *testing.T) {
      calls := 0
      mockCosts := &MockCostTracker{
          RecordFunc: func(ctx context.Context, tenantID, model string, usage *LLMUsage) error {
              calls++
              if calls < 3 {
                  return errors.New("connection refused")
              }
              return nil
          },
      }

      summarizer := NewLLMSummarizer(mockLLM, mockCosts, nil)
      // ... trigger summarization ...

      assert.Equal(t, 3, calls) // Should retry twice then succeed
  }

  func TestCostTracking_NoRetryOnValidationError(t *testing.T) {
      calls := 0
      mockCosts := &MockCostTracker{
          RecordFunc: func(ctx context.Context, tenantID, model string, usage *LLMUsage) error {
              calls++
              return errors.New("invalid tenant_id format")
          },
      }

      summarizer := NewLLMSummarizer(mockLLM, mockCosts, nil)
      // ... trigger summarization ...

      assert.Equal(t, 1, calls) // Should not retry validation errors
  }

  func TestCostTracking_DeadLetterQueue(t *testing.T) {
      ct := NewCostTracker(db)

      // Queue a record
      ct.QueueForRetry(CostRecord{
          TenantID:    "test-tenant",
          Model:       "claude-haiku",
          InputTokens: 100,
      })

      // Wait for processing
      time.Sleep(100 * time.Millisecond)

      // Verify record was processed (check DB or mock)
  }
  ```

**Success Criteria:**
- [ ] Cost tracking failures are logged with full context
- [ ] Transient errors trigger up to 3 retries with backoff
- [ ] Validation errors don't trigger retries
- [ ] Prometheus metric tracks failure counts by type
- [ ] Dead letter queue captures failed records for later processing
- [ ] Fallback file created when all else fails
- [ ] Summarization still succeeds even if cost tracking fails

**Best Practices:**
- Never silently ignore errors that affect billing
- Use retry with exponential backoff for transient failures
- Categorize errors to enable targeted monitoring
- Provide fallback mechanisms (dead letter queue, file)
- Log enough context to debug issues in production

---

### FIX-03: MemoryGCService Safe Deletion Logic 🔴
**Priority:** Critical
**Status:** ❌ Incomplete.

**Files:**
- `backend/application/services/memory_gc.py`
- `backend/tests/unit/application/services/test_memory_gc.py`

**Problem:**
Current implementation assumes `tenant_id` equals `User.id`, but graph-scoped configurations also exist. This would incorrectly delete all graph memory.

**Review Notes:**
- **Missing:** Unit tests are missing (`test_memory_gc.py` was not found).
- **Missing:** The admin API endpoint to trigger the GC service is missing (`admin/views.py` was not found).

```python
# Current broken implementation
if prune_missing_users:
    user_ids = list(User.objects.values_list("id", flat=True))
    deleted, _ = MemoryChunk.objects.exclude(tenant_id__in=user_ids).delete()
    # BUG: Deletes all graph-scoped memory!
```

**Implementation:**

- [ ] Refactor GC service with safe deletion:
  ```python
  # backend/application/services/memory_gc.py

  from __future__ import annotations

  import logging
  from dataclasses import dataclass
  from datetime import datetime, timedelta
  from typing import Set
  from uuid import UUID

  from django.contrib.auth import get_user_model
  from django.db import connection, transaction
  from django.db.models import Count

  from infrastructure.orm.models import Graph, MemoryChunk, MemoryEntry

  logger = logging.getLogger(__name__)
  User = get_user_model()


  @dataclass
  class GCResult:
      """Result of a garbage collection operation."""
      chunks_deleted: int = 0
      entries_deleted: int = 0
      orphaned_tenant_ids: list[UUID] = None
      dry_run: bool = False
      errors: list[str] = None

      def __post_init__(self):
          if self.orphaned_tenant_ids is None:
              self.orphaned_tenant_ids = []
          if self.errors is None:
              self.errors = []


  class MemoryGCService:
      """
      Garbage collection service for memory system.

      Handles cleanup of:
      - Expired memory entries (TTL-based)
      - Orphaned chunks (deleted users/graphs)
      - Old chunks beyond retention period
      """

      def __init__(
          self,
          chunk_retention_days: int = 90,
          entry_retention_days: int = 30,
          batch_size: int = 1000,
      ):
          self.chunk_retention_days = chunk_retention_days
          self.entry_retention_days = entry_retention_days
          self.batch_size = batch_size

      def get_valid_tenant_ids(self) -> Set[UUID]:
          """
          Get all valid tenant IDs from both users and graphs.

          Tenant IDs can come from:
          - User.id (user-scoped memory)
          - Graph.id (graph-scoped memory)
          """
          user_ids = set(User.objects.values_list("id", flat=True))
          graph_ids = set(Graph.objects.values_list("id", flat=True))

          valid_ids = user_ids | graph_ids
          logger.info(
              "Found valid tenant IDs",
              extra={
                  "user_count": len(user_ids),
                  "graph_count": len(graph_ids),
                  "total": len(valid_ids),
              },
          )
          return valid_ids

      def find_orphaned_tenant_ids(self) -> list[UUID]:
          """Find tenant IDs in memory that don't belong to any user or graph."""
          valid_ids = self.get_valid_tenant_ids()

          # Get unique tenant IDs from chunks
          chunk_tenant_ids = set(
              MemoryChunk.objects.values_list("tenant_id", flat=True).distinct()
          )

          # Find orphans
          orphaned = chunk_tenant_ids - valid_ids
          return list(orphaned)

      def cleanup_orphaned_chunks(
          self,
          tenant_ids: list[UUID] | None = None,
          dry_run: bool = False,
      ) -> GCResult:
          """
          Delete memory chunks for orphaned tenants.

          Args:
              tenant_ids: Specific tenant IDs to delete. If None, auto-detects orphans.
              dry_run: If True, only report what would be deleted.

          Returns:
              GCResult with deletion counts and any errors.
          """
          result = GCResult(dry_run=dry_run)

          # Auto-detect orphans if not specified
          if tenant_ids is None:
              tenant_ids = self.find_orphaned_tenant_ids()

          if not tenant_ids:
              logger.info("No orphaned tenant IDs found")
              return result

          result.orphaned_tenant_ids = tenant_ids

          # Safety check: don't delete if it's a large percentage
          total_chunks = MemoryChunk.objects.count()
          orphan_chunks = MemoryChunk.objects.filter(tenant_id__in=tenant_ids).count()

          if total_chunks > 0 and orphan_chunks / total_chunks > 0.5:
              error_msg = (
                  f"Safety check failed: {orphan_chunks}/{total_chunks} chunks "
                  f"({orphan_chunks/total_chunks*100:.1f}%) would be deleted. "
                  "This seems too high - please investigate manually."
              )
              logger.error(error_msg)
              result.errors.append(error_msg)
              return result

          logger.warning(
              "Preparing to delete orphaned chunks",
              extra={
                  "orphan_count": orphan_chunks,
                  "tenant_count": len(tenant_ids),
                  "dry_run": dry_run,
              },
          )

          if dry_run:
              result.chunks_deleted = orphan_chunks
              return result

          # Delete in batches to avoid long locks
          deleted_total = 0
          for tenant_id in tenant_ids:
              deleted = self._delete_chunks_for_tenant(tenant_id)
              deleted_total += deleted

          result.chunks_deleted = deleted_total
          logger.info(f"Deleted {deleted_total} orphaned chunks")
          return result

      def _delete_chunks_for_tenant(self, tenant_id: UUID) -> int:
          """Delete all chunks for a specific tenant in batches."""
          deleted_total = 0

          while True:
              # Get batch of IDs to delete
              chunk_ids = list(
                  MemoryChunk.objects.filter(tenant_id=tenant_id)
                  .values_list("id", flat=True)[: self.batch_size]
              )

              if not chunk_ids:
                  break

              # Delete batch
              deleted, _ = MemoryChunk.objects.filter(id__in=chunk_ids).delete()
              deleted_total += deleted

              logger.debug(
                  f"Deleted batch of {deleted} chunks for tenant {tenant_id}"
              )

          return deleted_total

      def cleanup_expired_entries(self, dry_run: bool = False) -> GCResult:
          """Delete memory entries that have expired based on their TTL."""
          result = GCResult(dry_run=dry_run)

          now = datetime.utcnow()
          expired_qs = MemoryEntry.objects.filter(expires_at__lt=now)
          count = expired_qs.count()

          if dry_run:
              result.entries_deleted = count
              return result

          # Delete in batches
          deleted_total = 0
          while True:
              batch_ids = list(
                  expired_qs.values_list("id", flat=True)[: self.batch_size]
              )
              if not batch_ids:
                  break

              deleted, _ = MemoryEntry.objects.filter(id__in=batch_ids).delete()
              deleted_total += deleted

          result.entries_deleted = deleted_total
          logger.info(f"Deleted {deleted_total} expired memory entries")
          return result

      def cleanup_old_chunks(
          self,
          max_age_days: int | None = None,
          dry_run: bool = False,
      ) -> GCResult:
          """Delete chunks older than the retention period."""
          result = GCResult(dry_run=dry_run)

          if max_age_days is None:
              max_age_days = self.chunk_retention_days

          cutoff = datetime.utcnow() - timedelta(days=max_age_days)
          old_qs = MemoryChunk.objects.filter(created_at__lt=cutoff)
          count = old_qs.count()

          logger.info(
              f"Found {count} chunks older than {max_age_days} days",
              extra={"cutoff": cutoff.isoformat()},
          )

          if dry_run:
              result.chunks_deleted = count
              return result

          # Delete in batches
          deleted_total = 0
          while True:
              batch_ids = list(
                  old_qs.values_list("id", flat=True)[: self.batch_size]
              )
              if not batch_ids:
                  break

              deleted, _ = MemoryChunk.objects.filter(id__in=batch_ids).delete()
              deleted_total += deleted

          result.chunks_deleted = deleted_total
          logger.info(f"Deleted {deleted_total} old chunks")
          return result

      def reindex_vectors(self) -> None:
          """
          Rebuild vector index for better performance.

          Note: This can be slow on large tables. Consider running during low-traffic periods.
          """
          logger.info("Starting vector index reindex")

          with connection.cursor() as cursor:
              # Check if index exists
              cursor.execute("""
                  SELECT indexname FROM pg_indexes
                  WHERE tablename = 'memory_chunks'
                  AND indexname = 'memory_chunks_embedding_ivfflat'
              """)
              if cursor.fetchone():
                  cursor.execute("REINDEX INDEX memory_chunks_embedding_ivfflat")
                  logger.info("Vector index reindexed successfully")
              else:
                  logger.warning("Vector index not found, skipping reindex")

      def run_full_gc(self, dry_run: bool = False) -> dict:
          """
          Run complete garbage collection cycle.

          Returns summary of all operations.
          """
          logger.info("Starting full GC cycle", extra={"dry_run": dry_run})

          results = {
              "expired_entries": self.cleanup_expired_entries(dry_run=dry_run),
              "orphaned_chunks": self.cleanup_orphaned_chunks(dry_run=dry_run),
              "old_chunks": self.cleanup_old_chunks(dry_run=dry_run),
          }

          total_deleted = sum(
              r.chunks_deleted + r.entries_deleted for r in results.values()
          )

          logger.info(
              "GC cycle complete",
              extra={
                  "total_deleted": total_deleted,
                  "dry_run": dry_run,
              },
          )

          return {
              "dry_run": dry_run,
              "expired_entries_deleted": results["expired_entries"].entries_deleted,
              "orphaned_chunks_deleted": results["orphaned_chunks"].chunks_deleted,
              "orphaned_tenant_ids": [
                  str(tid) for tid in results["orphaned_chunks"].orphaned_tenant_ids
              ],
              "old_chunks_deleted": results["old_chunks"].chunks_deleted,
              "total_deleted": total_deleted,
              "errors": [
                  e
                  for r in results.values()
                  for e in r.errors
              ],
          }
  ```

- [ ] Add admin endpoint with dry-run support:
  ```python
  # backend/adapters/api/admin/views.py

  from rest_framework.views import APIView
  from rest_framework.response import Response
  from rest_framework.permissions import IsAdminUser

  from application.services.memory_gc import MemoryGCService


  class MemoryGCView(APIView):
      permission_classes = [IsAdminUser]

      def get(self, request):
          """Preview what would be deleted (dry run)."""
          gc = MemoryGCService()
          result = gc.run_full_gc(dry_run=True)
          return Response(result)

      def post(self, request):
          """Execute garbage collection."""
          dry_run = request.data.get("dry_run", False)

          gc = MemoryGCService(
              chunk_retention_days=request.data.get("chunk_retention_days", 90),
              entry_retention_days=request.data.get("entry_retention_days", 30),
          )

          result = gc.run_full_gc(dry_run=dry_run)
          return Response(result)
  ```

- [ ] Write comprehensive tests:
  ```python
  # backend/tests/unit/application/services/test_memory_gc.py

  import pytest
  from uuid import uuid4
  from datetime import datetime, timedelta
  from unittest.mock import patch

  from application.services.memory_gc import MemoryGCService, GCResult
  from infrastructure.orm.models import MemoryChunk, MemoryEntry, Graph


  @pytest.fixture
  def gc_service():
      return MemoryGCService(batch_size=10)


  @pytest.fixture
  def user(db):
      from django.contrib.auth import get_user_model
      User = get_user_model()
      return User.objects.create_user(username="test", password="test")


  @pytest.fixture
  def graph(db, user):
      return Graph.objects.create(id=uuid4(), name="Test Graph", owner=user)


  class TestGetValidTenantIds:
      def test_includes_user_ids(self, gc_service, user):
          valid_ids = gc_service.get_valid_tenant_ids()
          assert user.id in valid_ids

      def test_includes_graph_ids(self, gc_service, graph):
          valid_ids = gc_service.get_valid_tenant_ids()
          assert graph.id in valid_ids

      def test_union_of_users_and_graphs(self, gc_service, user, graph):
          valid_ids = gc_service.get_valid_tenant_ids()
          assert len(valid_ids) >= 2
          assert user.id in valid_ids
          assert graph.id in valid_ids


  class TestFindOrphanedTenantIds:
      def test_finds_orphaned_ids(self, gc_service, db):
          orphan_id = uuid4()
          MemoryChunk.objects.create(
              tenant_id=orphan_id,
              content="test",
              embedding=[0.1] * 1536,
              source_timestamp=datetime.utcnow(),
          )

          orphans = gc_service.find_orphaned_tenant_ids()
          assert orphan_id in orphans

      def test_excludes_valid_user_ids(self, gc_service, user):
          MemoryChunk.objects.create(
              tenant_id=user.id,
              content="test",
              embedding=[0.1] * 1536,
              source_timestamp=datetime.utcnow(),
          )

          orphans = gc_service.find_orphaned_tenant_ids()
          assert user.id not in orphans

      def test_excludes_valid_graph_ids(self, gc_service, graph):
          MemoryChunk.objects.create(
              tenant_id=graph.id,
              content="test",
              embedding=[0.1] * 1536,
              source_timestamp=datetime.utcnow(),
          )

          orphans = gc_service.find_orphaned_tenant_ids()
          assert graph.id not in orphans


  class TestCleanupOrphanedChunks:
      def test_dry_run_does_not_delete(self, gc_service, db):
          orphan_id = uuid4()
          chunk = MemoryChunk.objects.create(
              tenant_id=orphan_id,
              content="test",
              embedding=[0.1] * 1536,
              source_timestamp=datetime.utcnow(),
          )

          result = gc_service.cleanup_orphaned_chunks(dry_run=True)

          assert result.dry_run is True
          assert result.chunks_deleted == 1
          assert MemoryChunk.objects.filter(id=chunk.id).exists()

      def test_deletes_orphaned_chunks(self, gc_service, db):
          orphan_id = uuid4()
          chunk = MemoryChunk.objects.create(
              tenant_id=orphan_id,
              content="test",
              embedding=[0.1] * 1536,
              source_timestamp=datetime.utcnow(),
          )

          result = gc_service.cleanup_orphaned_chunks(dry_run=False)

          assert result.chunks_deleted == 1
          assert not MemoryChunk.objects.filter(id=chunk.id).exists()

      def test_preserves_valid_user_chunks(self, gc_service, user):
          chunk = MemoryChunk.objects.create(
              tenant_id=user.id,
              content="user chunk",
              embedding=[0.1] * 1536,
              source_timestamp=datetime.utcnow(),
          )

          gc_service.cleanup_orphaned_chunks(dry_run=False)

          assert MemoryChunk.objects.filter(id=chunk.id).exists()

      def test_preserves_valid_graph_chunks(self, gc_service, graph):
          chunk = MemoryChunk.objects.create(
              tenant_id=graph.id,
              content="graph chunk",
              embedding=[0.1] * 1536,
              source_timestamp=datetime.utcnow(),
          )

          gc_service.cleanup_orphaned_chunks(dry_run=False)

          assert MemoryChunk.objects.filter(id=chunk.id).exists()

      def test_safety_check_prevents_mass_deletion(self, gc_service, db):
          # Create many orphaned chunks (> 50% of total)
          orphan_id = uuid4()
          for i in range(10):
              MemoryChunk.objects.create(
                  tenant_id=orphan_id,
                  content=f"orphan {i}",
                  embedding=[0.1] * 1536,
                  source_timestamp=datetime.utcnow(),
              )

          result = gc_service.cleanup_orphaned_chunks(dry_run=False)

          # Should fail safety check
          assert len(result.errors) > 0
          assert "Safety check failed" in result.errors[0]
          assert MemoryChunk.objects.count() == 10  # Nothing deleted


  class TestCleanupExpiredEntries:
      def test_deletes_expired_entries(self, gc_service, db):
          # Expired entry
          expired = MemoryEntry.objects.create(
              namespace="test",
              key="expired",
              value_json={"test": True},
              expires_at=datetime.utcnow() - timedelta(hours=1),
          )

          # Valid entry
          valid = MemoryEntry.objects.create(
              namespace="test",
              key="valid",
              value_json={"test": True},
              expires_at=datetime.utcnow() + timedelta(hours=1),
          )

          result = gc_service.cleanup_expired_entries(dry_run=False)

          assert result.entries_deleted == 1
          assert not MemoryEntry.objects.filter(id=expired.id).exists()
          assert MemoryEntry.objects.filter(id=valid.id).exists()


  class TestCleanupOldChunks:
      def test_deletes_old_chunks(self, gc_service, user):
          old_chunk = MemoryChunk.objects.create(
              tenant_id=user.id,
              content="old",
              embedding=[0.1] * 1536,
              source_timestamp=datetime.utcnow() - timedelta(days=100),
          )
          old_chunk.created_at = datetime.utcnow() - timedelta(days=100)
          old_chunk.save()

          new_chunk = MemoryChunk.objects.create(
              tenant_id=user.id,
              content="new",
              embedding=[0.1] * 1536,
              source_timestamp=datetime.utcnow(),
          )

          result = gc_service.cleanup_old_chunks(max_age_days=90, dry_run=False)

          assert result.chunks_deleted == 1
          assert not MemoryChunk.objects.filter(id=old_chunk.id).exists()
          assert MemoryChunk.objects.filter(id=new_chunk.id).exists()
  ```

**Success Criteria:**
- [ ] `get_valid_tenant_ids()` returns union of User IDs and Graph IDs
- [ ] Orphan detection correctly identifies chunks without valid owner
- [ ] User-scoped memory chunks are never deleted by orphan cleanup
- [ ] Graph-scoped memory chunks are never deleted by orphan cleanup
- [ ] Safety check prevents deletion of >50% of chunks
- [ ] Dry-run mode reports what would be deleted without deleting
- [ ] Batch deletion avoids long database locks
- [ ] All tests pass including edge cases

**Best Practices:**
- Always check both user AND graph ownership for tenant IDs
- Implement safety checks for destructive operations
- Provide dry-run mode for all deletion operations
- Delete in batches to avoid locking issues
- Log all deletions with enough context for audit

---

### FIX-04: TieredMemoryStore Error Handling 🔴
**Priority:** Critical
**Status:** ✅ Fully implemented and verified.

**Files:**
- `engine/adapter/store/tiered_memory_store.go`
- `engine/adapter/store/tiered_errors.go`
- `engine/adapter/store/tiered_memory_store_test.go`

**Problem:**
Write operations that partially succeed leave data in inconsistent state. Callers can't distinguish which tiers failed.

**Success Criteria:**
- [ ] `TieredWriteError` captures which tiers succeeded and failed
- [ ] Callers can distinguish partial success from complete failure
- [ ] `IsPartialSuccess()` correctly identifies when at least one tier succeeded
- [ ] Error message includes both successful and failed tiers
- [ ] Metrics track tier-level errors
- [ ] All tests pass

**Best Practices:**
- Use structured error types for complex failure modes
- Allow callers to make informed decisions about partial failures
- Log individual tier failures with context
- Track metrics at tier level for monitoring

---

### FIX-05: BatchGet Fallback Consistency 🔴
**Priority:** Critical
**Status:** ✅ Fully implemented and verified.

**Files:**
- `engine/adapter/store/redis_memory_store.go`
- `engine/application/port/memory_store.go`
- `engine/adapter/store/redis_memory_store_test.go`

**Problem:**
`Get()` has fallback behavior on Redis failure, but `BatchGet()` returns error without attempting fallback, causing inconsistent behavior.

**Success Criteria:**
- [ ] `BatchGet` uses fallback when circuit is open (same as `Get`)
- [ ] `BatchGet` uses fallback when Redis returns error (same as `Get`)
- [ ] `BatchSet` has same fallback behavior as `Set`
- [ ] Metrics record fallback usage for batch operations
- [ ] Individual key errors in batch don't fail entire operation
- [ ] All tests pass

**Best Practices:**
- Maintain consistent behavior across single and batch operations
- Use pipeline for batch Redis operations
- Handle individual key errors gracefully in batches
- Record metrics for batch operations separately

---

### FIX-06: VectorSearchService Threshold Semantics 🟠
**Priority:** High
**Files:**
- `backend/application/services/vector_search_service.py`
- `backend/tests/unit/application/services/test_vector_search.py`

**Problem:**
Threshold filtering applies to raw similarity after hybrid ranking uses combined score. This is confusing and can produce unexpected results.

**Implementation:**

- [ ] Refactor to filter by similarity BEFORE hybrid ranking:
  ```python
  # backend/application/services/vector_search_service.py

  from __future__ import annotations

  import math
  from dataclasses import dataclass
  from datetime import datetime
  from typing import List, Optional
  from uuid import UUID

  from domain.entities.memory_chunk import MemoryChunkEntity
  from application.ports.memory_chunk_repository import MemoryChunkRepository
  from application.ports.embedding_service import EmbeddingService


  @dataclass
  class SearchResult:
      """Result from vector similarity search."""
      chunk: MemoryChunkEntity
      similarity: float       # Raw cosine similarity (0-1)
      recency_score: float    # Time-based recency (0-1)
      combined_score: float   # Weighted combination


  class VectorSearchService:
      """
      Service for semantic memory retrieval.

      Implements hybrid ranking combining:
      1. Cosine similarity from vector search
      2. Recency boost for recent memories

      Filtering Strategy:
      - Threshold is applied to RAW SIMILARITY before ranking
      - This ensures only semantically relevant results are considered
      - Recency boost can then re-order but not include irrelevant results
      """

      def __init__(
          self,
          repository: MemoryChunkRepository,
          embedder: EmbeddingService,
          recency_decay_hours: float = 168.0,  # 1 week half-life
      ):
          self._repository = repository
          self._embedder = embedder
          self._recency_decay_hours = recency_decay_hours

      async def search(
          self,
          query: str,
          tenant_id: UUID,
          agent_id: Optional[UUID] = None,
          session_id: Optional[UUID] = None,
          top_k: int = 5,
          threshold: float = 0.7,
          recency_weight: float = 0.2,
      ) -> List[SearchResult]:
          """
          Search for relevant memory chunks.

          Args:
              query: Search query text
              tenant_id: Tenant ID for isolation
              agent_id: Optional agent ID filter
              session_id: Optional session ID filter
              top_k: Maximum results to return
              threshold: Minimum similarity score (0-1) BEFORE recency weighting
              recency_weight: Weight for recency in combined score (0-1)

          Returns:
              List of SearchResult sorted by combined score
          """
          # 1. Embed query
          embeddings = await self._embedder.embed([query])
          query_embedding = embeddings[0]

          # 2. Vector search with overfetch for filtering
          # Fetch extra candidates since some will be filtered by threshold
          fetch_count = max(top_k * 2, top_k + 10)

          candidates = list(
              self._repository.search(
                  embedding=query_embedding,
                  tenant_id=tenant_id,
                  agent_id=agent_id,
                  session_id=session_id,
                  top_k=fetch_count,
              )
          )

          # 3. Filter by similarity threshold FIRST
          # This ensures only semantically relevant results are considered
          filtered = [
              chunk for chunk in candidates
              if chunk.similarity >= threshold
          ]

          if not filtered:
              return []

          # 4. Calculate recency scores and combine
          now = datetime.utcnow()
          results = []

          for chunk in filtered:
              recency = self._calculate_recency(chunk.source_timestamp, now)
              combined = self._combine_scores(
                  similarity=chunk.similarity,
                  recency=recency,
                  recency_weight=recency_weight,
              )

              results.append(SearchResult(
                  chunk=chunk,
                  similarity=chunk.similarity,
                  recency_score=recency,
                  combined_score=combined,
              ))

          # 5. Sort by combined score and return top_k
          results.sort(key=lambda r: r.combined_score, reverse=True)
          return results[:top_k]

      def _calculate_recency(self, timestamp: datetime, now: datetime) -> float:
          """
          Calculate recency score with exponential decay.

          Score of 1.0 for current time, decaying with half-life of recency_decay_hours.
          """
          if timestamp is None:
              return 0.5  # Default for missing timestamp

          age_hours = max((now - timestamp).total_seconds() / 3600.0, 0.0)

          # Exponential decay: score = 0.5^(age / half_life)
          # At half_life hours, score = 0.5
          # At 2*half_life hours, score = 0.25
          decay_factor = age_hours / self._recency_decay_hours
          return math.pow(0.5, decay_factor)

      def _combine_scores(
          self,
          similarity: float,
          recency: float,
          recency_weight: float,
      ) -> float:
          """
          Combine similarity and recency scores.

          combined = (1 - recency_weight) * similarity + recency_weight * recency
          """
          sim_weight = 1.0 - recency_weight
          return (sim_weight * similarity) + (recency_weight * recency)
  ```

- [ ] Add docstrings explaining the filtering strategy
- [ ] Write tests for threshold behavior:
  ```python
  # backend/tests/unit/application/services/test_vector_search.py

  import pytest
  from datetime import datetime, timedelta
  from uuid import uuid4
  from unittest.mock import AsyncMock, MagicMock

  from application.services.vector_search_service import VectorSearchService


  @pytest.fixture
  def mock_repository():
      repo = MagicMock()
      return repo


  @pytest.fixture
  def mock_embedder():
      embedder = AsyncMock()
      embedder.embed.return_value = [[0.1] * 1536]
      return embedder


  @pytest.fixture
  def service(mock_repository, mock_embedder):
      return VectorSearchService(
          repository=mock_repository,
          embedder=mock_embedder,
          recency_decay_hours=168.0,
      )


  class TestThresholdFiltering:
      async def test_filters_below_threshold(self, service, mock_repository):
          """Results below threshold should be excluded even with high recency."""
          tenant_id = uuid4()

          # Create chunks with varying similarity
          chunks = [
              MagicMock(
                  similarity=0.9,  # Above threshold
                  source_timestamp=datetime.utcnow() - timedelta(days=30),
              ),
              MagicMock(
                  similarity=0.5,  # Below threshold
                  source_timestamp=datetime.utcnow(),  # Very recent
              ),
          ]
          mock_repository.search.return_value = chunks

          results = await service.search(
              query="test",
              tenant_id=tenant_id,
              threshold=0.7,
              recency_weight=0.9,  # High recency weight
          )

          # Should only get the high-similarity result
          assert len(results) == 1
          assert results[0].similarity == 0.9

      async def test_threshold_applies_to_raw_similarity(self, service, mock_repository):
          """Threshold should apply to similarity, not combined score."""
          tenant_id = uuid4()

          chunk = MagicMock(
              similarity=0.65,  # Just below 0.7 threshold
              source_timestamp=datetime.utcnow(),  # Max recency
          )
          mock_repository.search.return_value = [chunk]

          results = await service.search(
              query="test",
              tenant_id=tenant_id,
              threshold=0.7,
              recency_weight=0.5,
          )

          # Combined would be 0.5*0.65 + 0.5*1.0 = 0.825
          # But should still be filtered because similarity < threshold
          assert len(results) == 0


  class TestRecencyScoring:
      async def test_recent_chunks_boosted(self, service, mock_repository):
          """Recent chunks should rank higher with recency weight."""
          tenant_id = uuid4()

          now = datetime.utcnow()
          chunks = [
              MagicMock(similarity=0.8, source_timestamp=now - timedelta(days=7)),
              MagicMock(similarity=0.8, source_timestamp=now),  # Same similarity, more recent
          ]
          mock_repository.search.return_value = chunks

          results = await service.search(
              query="test",
              tenant_id=tenant_id,
              threshold=0.7,
              recency_weight=0.3,
          )

          # More recent should rank first
          assert results[0].chunk.source_timestamp == now

      async def test_recency_decay_formula(self, service):
          """Test the exponential decay formula."""
          now = datetime.utcnow()

          # At t=0, recency should be 1.0
          assert service._calculate_recency(now, now) == pytest.approx(1.0)

          # At t=half_life (168 hours = 1 week), recency should be 0.5
          one_week_ago = now - timedelta(hours=168)
          assert service._calculate_recency(one_week_ago, now) == pytest.approx(0.5)

          # At t=2*half_life, recency should be 0.25
          two_weeks_ago = now - timedelta(hours=336)
          assert service._calculate_recency(two_weeks_ago, now) == pytest.approx(0.25)


  class TestCombinedScoring:
      async def test_score_combination(self, service):
          """Test weighted combination of scores."""
          # 50/50 weight
          combined = service._combine_scores(
              similarity=0.8,
              recency=0.6,
              recency_weight=0.5,
          )
          assert combined == pytest.approx(0.7)

          # No recency weight
          combined = service._combine_scores(
              similarity=0.8,
              recency=0.6,
              recency_weight=0.0,
          )
          assert combined == pytest.approx(0.8)

          # Full recency weight
          combined = service._combine_scores(
              similarity=0.8,
              recency=0.6,
              recency_weight=1.0,
          )
          assert combined == pytest.approx(0.6)
  ```

**Success Criteria:**
- [ ] Threshold filters on raw similarity BEFORE hybrid ranking
- [ ] Results below threshold are excluded regardless of recency
- [ ] Recency scoring uses proper exponential decay
- [ ] Combined score formula is clear and documented
- [ ] All tests pass including edge cases

**Best Practices:**
- Document filtering semantics clearly in docstrings
- Use exponential decay for more natural time-based scoring
- Separate filtering (threshold) from ranking (combined score)
- Provide sensible defaults for recency parameters

---

### FIX-07: Summary Version Atomicity 🟠
**Priority:** High
**Files:**
- `engine/adapter/store/redis_memory_store.go`
- `engine/adapter/store/redis_scripts.go`

**Problem:**
Summary versioning uses separate INCR and SET operations. If INCR succeeds but SET fails, version counter is incremented without data.

**Implementation:**

- [ ] Create Lua script for atomic operations:
  ```go
  // engine/adapter/store/redis_scripts.go

  package store

  import "github.com/redis/go-redis/v9"

  // storeSummaryScript atomically:
  // 1. Increments version counter
  // 2. Stores versioned backup
  // 3. Stores current summary
  // 4. Evicts old version if > 5
  var storeSummaryScript = redis.NewScript(`
      local versionKey = KEYS[1]
      local currentKey = KEYS[2]
      local versionedKeyPrefix = KEYS[3]
      local data = ARGV[1]
      local ttl = tonumber(ARGV[2])

      -- Increment version atomically
      local version = redis.call('INCR', versionKey)

      -- Build versioned key
      local versionedKey = versionedKeyPrefix .. 'v' .. tostring(version)

      -- Store both versioned and current
      if ttl > 0 then
          redis.call('SET', versionedKey, data, 'EX', ttl)
          redis.call('SET', currentKey, data, 'EX', ttl)
      else
          redis.call('SET', versionedKey, data)
          redis.call('SET', currentKey, data)
      end

      -- Evict old version (keep last 5)
      if version > 5 then
          local oldVersion = version - 5
          local oldKey = versionedKeyPrefix .. 'v' .. tostring(oldVersion)
          redis.call('DEL', oldKey)
      end

      -- Set TTL on version counter too
      if ttl > 0 then
          redis.call('EXPIRE', versionKey, ttl)
      end

      return version
  `)

  // getSummaryHistoryScript gets summary and version info
  var getSummaryHistoryScript = redis.NewScript(`
      local versionKey = KEYS[1]
      local currentKey = KEYS[2]

      local version = redis.call('GET', versionKey)
      local current = redis.call('GET', currentKey)

      return {version or '0', current or ''}
  `)
  ```

- [ ] Update StoreSummary to use Lua script:
  ```go
  // engine/adapter/store/redis_memory_store.go

  func (s *RedisMemoryStore) StoreSummary(ctx context.Context, runID string, summary *entity.Summary) error {
      if s.isCircuitOpen() {
          return s.fallbackStoreSummary(ctx, runID, summary)
      }

      data, err := json.Marshal(summary)
      if err != nil {
          return fmt.Errorf("marshal summary: %w", err)
      }

      encoded := s.encodePayload(data)

      // Build keys
      versionKey := s.buildKey("_summary_versions", runID)
      currentKey := s.buildSummaryKey(runID, "current")
      versionedPrefix := s.buildSummaryKey(runID, "")

      // Execute atomic Lua script
      start := time.Now()
      version, err := storeSummaryScript.Run(
          ctx,
          s.client,
          []string{versionKey, currentKey, versionedPrefix},
          encoded,
          s.summaryTTL,
      ).Int64()

      duration := time.Since(start)

      if err != nil {
          s.recordFailure()
          metrics.RecordRedisOperation("store_summary", duration, err)

          if s.fallback != nil {
              log.Warn("redis store summary failed, using fallback",
                  "run_id", runID,
                  "error", err,
              )
              return s.fallbackStoreSummary(ctx, runID, summary)
          }
          return fmt.Errorf("store summary: %w", err)
      }

      s.resetFailures()
      metrics.RecordRedisOperation("store_summary", duration, nil)

      log.Debug("summary stored",
          "run_id", runID,
          "version", version,
          "size", len(data),
      )

      return nil
  }

  func (s *RedisMemoryStore) fallbackStoreSummary(ctx context.Context, runID string, summary *entity.Summary) error {
      if s.fallback == nil {
          return errCircuitOpen
      }

      key := fmt.Sprintf("summary:%s:current", runID)
      return s.fallback.Set(ctx, s.tenantID, key, summary, s.summaryTTL)
  }
  ```

- [ ] Add method to get summary with version info:
  ```go
  type SummaryWithVersion struct {
      Summary *entity.Summary
      Version int64
  }

  func (s *RedisMemoryStore) GetSummaryWithVersion(ctx context.Context, runID string) (*SummaryWithVersion, error) {
      if s.isCircuitOpen() {
          // Fallback doesn't track versions
          summary, found, err := s.fallbackGetSummary(ctx, runID)
          if err != nil || !found {
              return nil, err
          }
          return &SummaryWithVersion{Summary: summary, Version: 0}, nil
      }

      versionKey := s.buildKey("_summary_versions", runID)
      currentKey := s.buildSummaryKey(runID, "current")

      result, err := getSummaryHistoryScript.Run(
          ctx,
          s.client,
          []string{versionKey, currentKey},
      ).Slice()

      if err != nil {
          return nil, err
      }

      versionStr := result[0].(string)
      dataStr := result[1].(string)

      if dataStr == "" {
          return nil, nil
      }

      version, _ := strconv.ParseInt(versionStr, 10, 64)

      decoded, err := s.decodePayload([]byte(dataStr))
      if err != nil {
          return nil, err
      }

      var summary entity.Summary
      if err := json.Unmarshal(decoded, &summary); err != nil {
          return nil, err
      }

      return &SummaryWithVersion{
          Summary: &summary,
          Version: version,
      }, nil
  }
  ```

- [ ] Write tests:
  ```go
  func TestStoreSummary_AtomicVersioning(t *testing.T) {
      store := setupRedisStore(t)
      ctx := context.Background()

      // Store multiple summaries
      for i := 1; i <= 7; i++ {
          summary := &entity.Summary{
              Content: fmt.Sprintf("Summary v%d", i),
          }
          err := store.StoreSummary(ctx, "run-1", summary)
          require.NoError(t, err)
      }

      // Check current
      result, err := store.GetSummaryWithVersion(ctx, "run-1")
      require.NoError(t, err)
      assert.Equal(t, int64(7), result.Version)
      assert.Equal(t, "Summary v7", result.Summary.Content)

      // Check old versions exist (v3-v7, v1-v2 evicted)
      for v := 3; v <= 7; v++ {
          key := store.buildSummaryKey("run-1", fmt.Sprintf("v%d", v))
          exists, _ := store.client.Exists(ctx, key).Result()
          assert.Equal(t, int64(1), exists, "v%d should exist", v)
      }

      // v1 and v2 should be evicted
      for v := 1; v <= 2; v++ {
          key := store.buildSummaryKey("run-1", fmt.Sprintf("v%d", v))
          exists, _ := store.client.Exists(ctx, key).Result()
          assert.Equal(t, int64(0), exists, "v%d should be evicted", v)
      }
  }

  func TestStoreSummary_ConcurrentWrites(t *testing.T) {
      store := setupRedisStore(t)
      ctx := context.Background()

      var wg sync.WaitGroup
      for i := 0; i < 10; i++ {
          wg.Add(1)
          go func(n int) {
              defer wg.Done()
              summary := &entity.Summary{
                  Content: fmt.Sprintf("Concurrent %d", n),
              }
              err := store.StoreSummary(ctx, "run-concurrent", summary)
              assert.NoError(t, err)
          }(i)
      }

      wg.Wait()

      // Version should be exactly 10
      result, err := store.GetSummaryWithVersion(ctx, "run-concurrent")
      require.NoError(t, err)
      assert.Equal(t, int64(10), result.Version)
  }
  ```

**Success Criteria:**
- [ ] Version increment and data storage happen atomically
- [ ] Failed SET doesn't leave orphaned version counter
- [ ] Old versions (>5) are evicted atomically
- [ ] Concurrent writes produce correct version numbers
- [ ] Fallback works when Redis unavailable
- [ ] All tests pass

**Best Practices:**
- Use Lua scripts for operations that must be atomic
- Keep version counter and data lifecycle in sync
- Handle eviction within the atomic operation
- Test concurrent scenarios

---

### FIX-08: Bounded Embedding Cache 🟠
**Priority:** High
**Files:**
- `backend/application/services/embedding_service.py`
- `backend/tests/unit/application/services/test_embedding_service.py`

**Problem:**
Embedding cache grows unbounded, causing memory issues on long-running systems.

**Implementation:**

- [ ] Create bounded LRU cache:
  ```python
  # backend/application/services/embedding_cache.py

  from __future__ import annotations

  import asyncio
  from collections import OrderedDict
  from dataclasses import dataclass, field
  from typing import List, Optional, Tuple


  @dataclass
  class CacheStats:
      hits: int = 0
      misses: int = 0
      evictions: int = 0
      size: int = 0
      max_size: int = 0

      @property
      def hit_rate(self) -> float:
          total = self.hits + self.misses
          return self.hits / total if total > 0 else 0.0


  class BoundedEmbeddingCache:
      """
      Thread-safe LRU cache for embeddings with bounded size.

      Evicts least recently used entries when capacity is reached.
      Cache key is (model, text_hash) to handle different embedding models.
      """

      def __init__(self, max_size: int = 10000):
          """
          Initialize cache.

          Args:
              max_size: Maximum number of embeddings to cache.
                        Default 10000 = ~60MB for 1536-dim embeddings.
          """
          self._cache: OrderedDict[Tuple[str, str], List[float]] = OrderedDict()
          self._max_size = max_size
          self._lock = asyncio.Lock()
          self._stats = CacheStats(max_size=max_size)

      async def get(self, model: str, text: str) -> Optional[List[float]]:
          """Get cached embedding, updating access order."""
          key = self._make_key(model, text)

          async with self._lock:
              if key in self._cache:
                  # Move to end (most recently used)
                  self._cache.move_to_end(key)
                  self._stats.hits += 1
                  return self._cache[key]

              self._stats.misses += 1
              return None

      async def get_many(self, model: str, texts: List[str]) -> dict[str, List[float]]:
          """Get multiple cached embeddings."""
          results = {}

          async with self._lock:
              for text in texts:
                  key = self._make_key(model, text)
                  if key in self._cache:
                      self._cache.move_to_end(key)
                      results[text] = self._cache[key]
                      self._stats.hits += 1
                  else:
                      self._stats.misses += 1

          return results

      async def set(self, model: str, text: str, embedding: List[float]) -> None:
          """Cache embedding, evicting LRU if at capacity."""
          key = self._make_key(model, text)

          async with self._lock:
              # If already exists, update and move to end
              if key in self._cache:
                  self._cache[key] = embedding
                  self._cache.move_to_end(key)
                  return

              # Add new entry
              self._cache[key] = embedding

              # Evict LRU entries if over capacity
              while len(self._cache) > self._max_size:
                  self._cache.popitem(last=False)
                  self._stats.evictions += 1

              self._stats.size = len(self._cache)

      async def set_many(self, model: str, items: dict[str, List[float]]) -> None:
          """Cache multiple embeddings."""
          async with self._lock:
              for text, embedding in items.items():
                  key = self._make_key(model, text)

                  if key in self._cache:
                      self._cache[key] = embedding
                      self._cache.move_to_end(key)
                  else:
                      self._cache[key] = embedding

              # Evict after batch insert
              while len(self._cache) > self._max_size:
                  self._cache.popitem(last=False)
                  self._stats.evictions += 1

              self._stats.size = len(self._cache)

      async def clear(self) -> None:
          """Clear all cached embeddings."""
          async with self._lock:
              self._cache.clear()
              self._stats.size = 0

      async def get_stats(self) -> CacheStats:
          """Get cache statistics."""
          async with self._lock:
              self._stats.size = len(self._cache)
              return CacheStats(
                  hits=self._stats.hits,
                  misses=self._stats.misses,
                  evictions=self._stats.evictions,
                  size=self._stats.size,
                  max_size=self._stats.max_size,
              )

      def _make_key(self, model: str, text: str) -> Tuple[str, str]:
          """Create cache key from model and text."""
          # Use hash for long texts to save memory on keys
          if len(text) > 100:
              import hashlib
              text_hash = hashlib.sha256(text.encode()).hexdigest()[:16]
              return (model, text_hash)
          return (model, text)
  ```

- [ ] Update EmbeddingService to use bounded cache:
  ```python
  # backend/application/services/embedding_service.py

  from application.services.embedding_cache import BoundedEmbeddingCache


  class EmbeddingService:
      def __init__(
          self,
          client: OpenAIClient,
          model: str = "text-embedding-ada-002",
          cache_max_size: int = 10000,
          rate_limit_per_minute: int = 3000,
      ):
          self._client = client
          self._model = model
          self._cache = BoundedEmbeddingCache(max_size=cache_max_size)
          self._rate_limiter = RateLimiter(rate_limit_per_minute)

      async def embed(self, texts: List[str]) -> List[List[float]]:
          """Generate embeddings with caching."""
          # Check cache first
          cached = await self._cache.get_many(self._model, texts)

          # Find texts that need embedding
          to_embed = [t for t in texts if t not in cached]

          if to_embed:
              # Rate limit
              await self._rate_limiter.acquire(len(to_embed))

              # Call API
              new_embeddings = await self._client.create_embeddings(
                  model=self._model,
                  input=to_embed,
              )

              # Cache results
              await self._cache.set_many(
                  self._model,
                  dict(zip(to_embed, new_embeddings)),
              )

              # Merge cached and new
              for text, embedding in zip(to_embed, new_embeddings):
                  cached[text] = embedding

          # Return in original order
          return [cached[t] for t in texts]

      async def get_cache_stats(self) -> dict:
          """Get cache statistics for monitoring."""
          stats = await self._cache.get_stats()
          return {
              "hits": stats.hits,
              "misses": stats.misses,
              "hit_rate": stats.hit_rate,
              "evictions": stats.evictions,
              "size": stats.size,
              "max_size": stats.max_size,
          }
  ```

- [ ] Write tests:
  ```python
  # backend/tests/unit/application/services/test_embedding_cache.py

  import pytest
  import asyncio

  from application.services.embedding_cache import BoundedEmbeddingCache


  @pytest.fixture
  def cache():
      return BoundedEmbeddingCache(max_size=5)


  class TestBoundedCache:
      async def test_basic_get_set(self, cache):
          embedding = [0.1, 0.2, 0.3]
          await cache.set("model", "hello", embedding)

          result = await cache.get("model", "hello")
          assert result == embedding

      async def test_cache_miss(self, cache):
          result = await cache.get("model", "unknown")
          assert result is None

      async def test_lru_eviction(self, cache):
          # Fill cache
          for i in range(5):
              await cache.set("model", f"text{i}", [float(i)])

          # Access text0 to make it recent
          await cache.get("model", "text0")

          # Add new item, should evict text1 (oldest not accessed)
          await cache.set("model", "text5", [5.0])

          # text0 should still exist (was accessed)
          assert await cache.get("model", "text0") is not None

          # text1 should be evicted
          assert await cache.get("model", "text1") is None

          # text5 should exist
          assert await cache.get("model", "text5") is not None

      async def test_eviction_count(self, cache):
          for i in range(10):
              await cache.set("model", f"text{i}", [float(i)])

          stats = await cache.get_stats()
          assert stats.evictions == 5
          assert stats.size == 5

      async def test_different_models_separate_keys(self, cache):
          await cache.set("model1", "hello", [1.0])
          await cache.set("model2", "hello", [2.0])

          assert await cache.get("model1", "hello") == [1.0]
          assert await cache.get("model2", "hello") == [2.0]

      async def test_concurrent_access(self, cache):
          async def writer(n):
              for i in range(100):
                  await cache.set("model", f"text{n}_{i}", [float(i)])

          async def reader(n):
              for i in range(100):
                  await cache.get("model", f"text{n}_{i}")

          tasks = [writer(i) for i in range(5)] + [reader(i) for i in range(5)]
          await asyncio.gather(*tasks)

          stats = await cache.get_stats()
          assert stats.size <= 5  # Should respect max_size

      async def test_stats_tracking(self, cache):
          await cache.set("model", "text1", [1.0])
          await cache.get("model", "text1")  # Hit
          await cache.get("model", "text2")  # Miss

          stats = await cache.get_stats()
          assert stats.hits == 1
          assert stats.misses == 1
          assert stats.hit_rate == 0.5
  ```

**Success Criteria:**
- [ ] Cache evicts LRU entries when max_size reached
- [ ] Different models have separate cache entries
- [ ] Concurrent access is thread-safe
- [ ] Statistics track hits, misses, and evictions
- [ ] Memory usage stays bounded
- [ ] All tests pass

**Best Practices:**
- Use OrderedDict for efficient LRU implementation
- Protect shared state with async lock
- Track cache statistics for monitoring
- Hash long texts to save memory on keys

---

### FIX-09: AsyncIO Handling in gRPC Service 🟠
**Priority:** High
**Files:**
- `backend/adapters/grpc/memory_service.py`

**Problem:**
Using `asyncio.run()` in sync gRPC context blocks and loses async benefits.

**Implementation:**

- [ ] Refactor to use proper async handling:
  ```python
  # backend/adapters/grpc/memory_service.py

  from __future__ import annotations

  import asyncio
  import logging
  from concurrent.futures import ThreadPoolExecutor
  from typing import Optional
  from uuid import UUID

  import grpc

  from proto import memory_pb2, memory_pb2_grpc
  from application.services.vector_search_service import VectorSearchService


  logger = logging.getLogger(__name__)


  class AsyncMemoryServicer(memory_pb2_grpc.MemoryServiceServicer):
      """
      gRPC servicer for memory retrieval.

      Handles async-to-sync bridging for gRPC which uses sync handlers.
      """

      def __init__(
          self,
          search_service: VectorSearchService,
          max_workers: int = 4,
      ):
          self._search_service = search_service
          self._executor = ThreadPoolExecutor(max_workers=max_workers)

          # Create dedicated event loop for async operations
          self._loop = asyncio.new_event_loop()
          self._loop_thread = None
          self._start_loop()

      def _start_loop(self):
          """Start the async event loop in a background thread."""
          import threading

          def run_loop():
              asyncio.set_event_loop(self._loop)
              self._loop.run_forever()

          self._loop_thread = threading.Thread(target=run_loop, daemon=True)
          self._loop_thread.start()

      def _run_async(self, coro, timeout: float = 30.0):
          """Run async coroutine from sync context."""
          future = asyncio.run_coroutine_threadsafe(coro, self._loop)
          try:
              return future.result(timeout=timeout)
          except asyncio.TimeoutError:
              future.cancel()
              raise

      def RetrieveMemory(
          self,
          request: memory_pb2.RetrieveMemoryRequest,
          context: grpc.ServicerContext,
      ) -> memory_pb2.RetrieveMemoryResponse:
          """Retrieve relevant memories for a query."""
          try:
              # Validate request
              if not request.query:
                  return memory_pb2.RetrieveMemoryResponse(
                      error="query is required"
                  )

              if not request.tenant_id:
                  return memory_pb2.RetrieveMemoryResponse(
                      error="tenant_id is required"
                  )

              # Parse UUIDs
              try:
                  tenant_id = UUID(request.tenant_id)
                  agent_id = UUID(request.agent_id) if request.agent_id else None
                  session_id = UUID(request.session_id) if request.session_id else None
              except ValueError as e:
                  return memory_pb2.RetrieveMemoryResponse(
                      error=f"invalid UUID: {e}"
                  )

              # Execute search asynchronously
              results = self._run_async(
                  self._search_service.search(
                      query=request.query,
                      tenant_id=tenant_id,
                      agent_id=agent_id,
                      session_id=session_id,
                      top_k=request.top_k or 5,
                      threshold=request.threshold or 0.7,
                      recency_weight=request.recency_weight or 0.2,
                  ),
                  timeout=10.0,
              )

              # Convert to proto
              chunks = [
                  memory_pb2.MemoryChunk(
                      id=str(r.chunk.id),
                      content=r.chunk.content,
                      similarity=r.similarity,
                      combined_score=r.combined_score,
                      chunk_type=r.chunk.chunk_type or "",
                      timestamp=int(r.chunk.source_timestamp.timestamp())
                          if r.chunk.source_timestamp else 0,
                  )
                  for r in results
              ]

              return memory_pb2.RetrieveMemoryResponse(chunks=chunks)

          except asyncio.TimeoutError:
              logger.error("Memory search timed out", extra={"query": request.query[:50]})
              return memory_pb2.RetrieveMemoryResponse(
                  error="search timed out"
              )
          except Exception as e:
              logger.exception("Memory search failed")
              return memory_pb2.RetrieveMemoryResponse(
                  error=f"internal error: {str(e)}"
              )

      def shutdown(self):
          """Clean shutdown of async resources."""
          if self._loop and self._loop.is_running():
              self._loop.call_soon_threadsafe(self._loop.stop)
          if self._loop_thread:
              self._loop_thread.join(timeout=5.0)
          self._executor.shutdown(wait=True)


  def create_memory_servicer(search_service: VectorSearchService) -> AsyncMemoryServicer:
      """Factory function for creating memory servicer."""
      return AsyncMemoryServicer(search_service)
  ```

- [ ] Add proper shutdown handling in server:
  ```python
  # backend/adapters/grpc/server.py

  def serve():
      server = grpc.server(ThreadPoolExecutor(max_workers=10))

      # Create services
      search_service = VectorSearchService(...)
      memory_servicer = create_memory_servicer(search_service)

      memory_pb2_grpc.add_MemoryServiceServicer_to_server(
          memory_servicer, server
      )

      server.add_insecure_port('[::]:50052')
      server.start()

      def handle_shutdown(signum, frame):
          logger.info("Shutting down gRPC server...")
          memory_servicer.shutdown()
          server.stop(grace=5)

      signal.signal(signal.SIGTERM, handle_shutdown)
      signal.signal(signal.SIGINT, handle_shutdown)

      server.wait_for_termination()
  ```

- [ ] Write tests:
  ```python
  # backend/tests/unit/adapters/grpc/test_memory_service.py

  import pytest
  from unittest.mock import AsyncMock, MagicMock
  from uuid import uuid4

  from adapters.grpc.memory_service import AsyncMemoryServicer
  from proto import memory_pb2


  @pytest.fixture
  def mock_search_service():
      service = AsyncMock()
      service.search.return_value = []
      return service


  @pytest.fixture
  def servicer(mock_search_service):
      s = AsyncMemoryServicer(mock_search_service)
      yield s
      s.shutdown()


  class TestRetrieveMemory:
      def test_missing_query(self, servicer):
          request = memory_pb2.RetrieveMemoryRequest(
              tenant_id=str(uuid4()),
          )
          response = servicer.RetrieveMemory(request, None)
          assert "query is required" in response.error

      def test_missing_tenant_id(self, servicer):
          request = memory_pb2.RetrieveMemoryRequest(
              query="test",
          )
          response = servicer.RetrieveMemory(request, None)
          assert "tenant_id is required" in response.error

      def test_invalid_uuid(self, servicer):
          request = memory_pb2.RetrieveMemoryRequest(
              query="test",
              tenant_id="not-a-uuid",
          )
          response = servicer.RetrieveMemory(request, None)
          assert "invalid UUID" in response.error

      def test_successful_search(self, servicer, mock_search_service):
          mock_search_service.search.return_value = [
              MagicMock(
                  chunk=MagicMock(
                      id=uuid4(),
                      content="test content",
                      chunk_type="message",
                      source_timestamp=None,
                  ),
                  similarity=0.85,
                  combined_score=0.9,
              )
          ]

          request = memory_pb2.RetrieveMemoryRequest(
              query="test query",
              tenant_id=str(uuid4()),
              top_k=5,
          )

          response = servicer.RetrieveMemory(request, None)

          assert response.error == ""
          assert len(response.chunks) == 1
          assert response.chunks[0].content == "test content"
          assert response.chunks[0].similarity == pytest.approx(0.85)

      def test_search_timeout(self, servicer, mock_search_service):
          async def slow_search(*args, **kwargs):
              await asyncio.sleep(15)  # Longer than timeout
              return []

          mock_search_service.search = slow_search

          request = memory_pb2.RetrieveMemoryRequest(
              query="test",
              tenant_id=str(uuid4()),
          )

          response = servicer.RetrieveMemory(request, None)
          assert "timed out" in response.error
  ```

**Success Criteria:**
- [ ] Async search runs without blocking gRPC thread pool
- [ ] Dedicated event loop handles async operations
- [ ] Timeout prevents hanging requests
- [ ] Proper error messages for validation failures
- [ ] Clean shutdown of async resources
- [ ] All tests pass

**Best Practices:**
- Use dedicated event loop for async operations in sync context
- Set reasonable timeouts for external calls
- Validate all inputs before processing
- Log errors with context for debugging
- Clean up resources on shutdown

---

### FIX-10: Token Eviction Metrics 🟡
**Priority:** Medium
**Files:**
- `engine/domain/entity/message_buffer.go`
- `engine/adapter/metrics/memory_metrics.go`

**Problem:**
Token-based evictions happen silently without metrics, making it hard to tune configuration.

**Implementation:**

- [ ] Add metrics for eviction:
  ```go
  // engine/adapter/metrics/memory_metrics.go

  var (
      memoryBufferEvictions = promauto.NewCounterVec(
          prometheus.CounterOpts{
              Name: "forgegraph_memory_buffer_evictions_total",
              Help: "Total message evictions from buffer",
          },
          []string{"reason", "tenant_id"},
      )

      memoryBufferEvictedMessages = promauto.NewCounterVec(
          prometheus.CounterOpts{
              Name: "forgegraph_memory_buffer_evicted_messages_total",
              Help: "Total messages evicted from buffer",
          },
          []string{"reason", "tenant_id"},
      )

      memoryBufferEvictedTokens = promauto.NewCounterVec(
          prometheus.CounterOpts{
              Name: "forgegraph_memory_buffer_evicted_tokens_total",
              Help: "Total tokens evicted from buffer",
          },
          []string{"tenant_id"},
      )
  )

  func RecordBufferEviction(reason string, tenantID string, messageCount int, tokenCount int) {
      memoryBufferEvictions.WithLabelValues(reason, tenantID).Inc()
      memoryBufferEvictedMessages.WithLabelValues(reason, tenantID).Add(float64(messageCount))
      if tokenCount > 0 {
          memoryBufferEvictedTokens.WithLabelValues(tenantID).Add(float64(tokenCount))
      }
  }
  ```

- [ ] Update MessageBuffer to report evictions:
  ```go
  // engine/domain/entity/message_buffer.go

  type EvictionCallback func(reason string, count int, tokens int)

  type MessageBuffer struct {
      // ... existing fields ...
      onEviction EvictionCallback
  }

  func (b *MessageBuffer) SetEvictionCallback(cb EvictionCallback) {
      b.mu.Lock()
      defer b.mu.Unlock()
      b.onEviction = cb
  }

  func (b *MessageBuffer) Push(msg Message) {
      b.mu.Lock()
      defer b.mu.Unlock()

      // Check capacity eviction
      if b.count >= b.capacity {
          evicted := b.messages[b.head]
          evictedTokens := 0
          if b.tokenLimit > 0 {
              evictedTokens = b.tokenCounts[b.head]
              b.currentTokens -= evictedTokens
          }

          if b.onEviction != nil {
              b.onEviction("capacity", 1, evictedTokens)
          }
      }

      // ... rest of Push ...
  }

  func (b *MessageBuffer) trimToTokenLimit() int {
      // ... existing logic to find cutIndex ...

      if cutIndex > 0 {
          evictedTokens := 0
          for i := 0; i < cutIndex; i++ {
              idx := (b.head + i) % b.capacity
              evictedTokens += b.tokenCounts[idx]
          }

          if b.onEviction != nil {
              b.onEviction("token_limit", cutIndex, evictedTokens)
          }
      }

      // ... rest of method ...
  }
  ```

- [ ] Wire up in scheduler:
  ```go
  // In scheduler when creating buffer
  buffer := entity.NewMessageBuffer(bufferSize)
  buffer.SetEvictionCallback(func(reason string, count int, tokens int) {
      metrics.RecordBufferEviction(reason, tenantID, count, tokens)
  })
  ```

**Success Criteria:**
- [ ] Capacity evictions recorded with count
- [ ] Token limit evictions recorded with count and tokens
- [ ] Metrics include tenant ID for per-tenant analysis
- [ ] Dashboard can show eviction rates over time

---

### FIX-11: Optimized Analytics Queries 🟡
**Priority:** Medium
**Files:**
- `backend/adapters/api/memory/views.py`

**Problem:**
Multiple queries fetch overlapping data, causing unnecessary database load.

**Implementation:**

- [ ] Consolidate queries:
  ```python
  # backend/adapters/api/memory/views.py

  class MemoryAnalyticsView(APIView):
      def get(self, request):
          tenant_id = get_tenant_id(request)
          period = self._parse_period(request.query_params.get("period", "30d"))
          cutoff = datetime.utcnow() - period

          # Single aggregated query for usage stats
          usage_stats = MemoryUsage.objects.filter(
              tenant_id=tenant_id,
              recorded_at__gte=cutoff,
          ).aggregate(
              summarization_calls=Coalesce(Sum('summarization_calls'), 0),
              summarization_tokens=Coalesce(Sum('summarization_tokens'), 0),
              summarization_cost=Coalesce(Sum('estimated_cost_usd'), Value(0.0)),
              embedding_calls=Coalesce(Sum('embedding_calls'), 0),
              embedding_tokens=Coalesce(Sum('embedding_tokens'), 0),
          )

          # Single query for chunk stats with top agents
          chunk_stats = MemoryChunk.objects.filter(
              tenant_id=tenant_id,
          ).aggregate(
              total_chunks=Count('id'),
              unique_agents=Count('agent_id', distinct=True),
              unique_sessions=Count('session_id', distinct=True),
          )

          # Top agents (limited)
          top_agents = list(
              MemoryChunk.objects.filter(tenant_id=tenant_id)
              .values('agent_id')
              .annotate(chunks=Count('id'))
              .order_by('-chunks')[:10]
          )

          # Storage estimate (more accurate)
          storage_estimate = self._estimate_storage(tenant_id)

          return Response({
              "period": str(period),
              "summarization": {
                  "calls": usage_stats['summarization_calls'],
                  "tokens": usage_stats['summarization_tokens'],
                  "cost_usd": float(usage_stats['summarization_cost']),
              },
              "embedding": {
                  "calls": usage_stats['embedding_calls'],
                  "tokens": usage_stats['embedding_tokens'],
                  "cost_usd": 0.0,  # TODO: Phase 4
              },
              "chunks": {
                  "total": chunk_stats['total_chunks'],
                  "unique_agents": chunk_stats['unique_agents'],
                  "unique_sessions": chunk_stats['unique_sessions'],
              },
              "top_agents": top_agents,
              "storage": storage_estimate,
          })

      def _estimate_storage(self, tenant_id: UUID) -> dict:
          """Estimate storage usage for tenant."""
          with connection.cursor() as cursor:
              # Use pg_column_size for accurate estimate
              cursor.execute("""
                  SELECT
                      COUNT(*) as count,
                      COALESCE(SUM(pg_column_size(content)), 0) as content_bytes,
                      COALESCE(SUM(pg_column_size(embedding)), 0) as embedding_bytes
                  FROM memory_chunks
                  WHERE tenant_id = %s
              """, [str(tenant_id)])
              row = cursor.fetchone()

          return {
              "chunk_count": row[0],
              "content_bytes": row[1],
              "embedding_bytes": row[2],
              "total_bytes": row[1] + row[2],
          }
  ```

**Success Criteria:**
- [ ] Single query for usage aggregation
- [ ] Top agents limited to 10
- [ ] Storage estimate uses actual column sizes
- [ ] Query count reduced by at least 50%

---

### FIX-12: Distributed Tracing Support 🟡
**Priority:** Medium
**Files:**
- `engine/adapter/store/redis_memory_store.go`
- `engine/adapter/summarizer/llm_summarizer.go`
- `backend/application/services/vector_search_service.py`

**Problem:**
No distributed tracing makes it hard to debug cross-service memory operations.

**Implementation:**

- [ ] Add tracing to Go components:
  ```go
  // engine/adapter/tracing/memory_tracing.go

  import (
      "go.opentelemetry.io/otel"
      "go.opentelemetry.io/otel/attribute"
      "go.opentelemetry.io/otel/trace"
  )

  var tracer = otel.Tracer("forgegraph.memory")

  func StartSpan(ctx context.Context, name string, attrs ...attribute.KeyValue) (context.Context, trace.Span) {
      return tracer.Start(ctx, name, trace.WithAttributes(attrs...))
  }

  // Usage in redis_memory_store.go:
  func (s *RedisMemoryStore) Get(ctx context.Context, namespace, key string) (any, bool, error) {
      ctx, span := tracing.StartSpan(ctx, "redis.memory.get",
          attribute.String("namespace", namespace),
          attribute.String("tenant_id", s.tenantID),
      )
      defer span.End()

      // ... existing code ...

      if err != nil {
          span.RecordError(err)
          span.SetStatus(codes.Error, err.Error())
      }

      return result, found, err
  }
  ```

- [ ] Add tracing to Python components:
  ```python
  # backend/application/services/vector_search_service.py

  from opentelemetry import trace

  tracer = trace.get_tracer("forgegraph.memory")

  class VectorSearchService:
      async def search(self, ...) -> List[SearchResult]:
          with tracer.start_as_current_span("vector.search") as span:
              span.set_attribute("query_length", len(query))
              span.set_attribute("tenant_id", str(tenant_id))
              span.set_attribute("top_k", top_k)

              # ... search logic ...

              span.set_attribute("results_count", len(results))
              return results
  ```

**Success Criteria:**
- [ ] Traces capture Redis operations with timing
- [ ] Traces capture vector search with query info
- [ ] Traces capture LLM summarization with token counts
- [ ] Cross-service traces link properly

---

## Acceptance Criteria (Overall)

1. [ ] All critical fixes (FIX-01 to FIX-05) implemented and tested
2. [ ] All high priority fixes (FIX-06 to FIX-09) implemented and tested
3. [ ] All medium priority fixes (FIX-10 to FIX-12) implemented and tested
4. [ ] No regressions in existing tests
5. [ ] Performance benchmarks meet targets
6. [ ] Documentation updated

## Status: IN PROGRESS (1/12 complete)

## Dependencies

- Phases 1-3 implemented
- Redis and PostgreSQL test environments available
- OpenTelemetry configured (for FIX-12)

## Estimated Total Effort

| Priority | Fixes | Effort |
|----------|-------|--------|
| Critical | 5 | ~5 days |
| High | 4 | ~4 days |
| Medium | 3 | ~2 days |
| **Total** | **12** | **~11 days** |

## Output

- [x] Robust JSON extraction with proper parsing
- [ ] Reliable cost tracking with retry and fallback
- [ ] Safe garbage collection respecting all tenant types
- [ ] Structured error handling for tiered storage
- [ ] Consistent fallback behavior for batch operations
- [ ] Clear threshold filtering semantics
- [ ] Atomic summary versioning
- [ ] Bounded embedding cache with LRU eviction
- [ ] Proper async handling in gRPC
- [ ] Eviction metrics for monitoring
- [ ] Optimized analytics queries
- [ ] Distributed tracing support
