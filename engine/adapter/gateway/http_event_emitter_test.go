package gateway

import (
	"context"
	"encoding/json"
	"errors"
	"net/http"
	"net/http/httptest"
	"os"
	"path/filepath"
	"strings"
	"sync/atomic"
	"testing"
	"time"

	"github.com/forgegraph/engine/application/port"
)

func writeCallbackDecision(
	t *testing.T,
	w http.ResponseWriter,
	statusCode int,
	decision string,
	safeToDiscard bool,
) {
	t.Helper()
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(statusCode)
	if err := json.NewEncoder(w).Encode(map[string]any{
		"decision":         decision,
		"reason":           decision,
		"backend_event_id": "backend-event",
		"safe_to_discard":  safeToDiscard,
		"conflict_code":    "",
		"retry_after_ms":   0,
	}); err != nil {
		t.Fatalf("Encode() error = %v", err)
	}
}

func TestNewHTTPEventEmitterRequiresCallbackURL(t *testing.T) {
	_, err := NewHTTPEventEmitter(HTTPEventEmitterConfig{})
	if !errors.Is(err, ErrEventCallbackNotConfigured) {
		t.Fatalf("err = %v, want ErrEventCallbackNotConfigured", err)
	}
}

func TestEmitAsyncSpoolsWhenBufferFull(t *testing.T) {
	spoolPath := filepath.Join(t.TempDir(), "events.jsonl")
	emitter := &HTTPEventEmitter{
		callbackURL:  "http://127.0.0.1:1",
		eventChan:    make(chan *port.ExecutionEvent, 1),
		maxRetries:   1,
		retryDelay:   10 * time.Millisecond,
		spoolPath:    spoolPath,
		spoolFlushCh: make(chan struct{}, 1),
	}

	emitter.eventChan <- port.NewEvent(port.EventTypeRunStarted, "run-1")
	emitter.EmitAsync(port.NewEvent(port.EventTypeNodeCompleted, "run-1"))

	data, readErr := os.ReadFile(spoolPath)
	if readErr != nil {
		t.Fatalf("ReadFile() error = %v", readErr)
	}
	lines := bytesSplitLines(data)
	if len(lines) != 1 {
		t.Fatalf("spool lines = %d, want 1", len(lines))
	}
	var event port.ExecutionEvent
	if err := json.Unmarshal(lines[0], &event); err != nil {
		t.Fatalf("json.Unmarshal() error = %v", err)
	}
	if event.Type != port.EventTypeNodeCompleted {
		t.Fatalf("event.Type = %s, want %s", event.Type, port.EventTypeNodeCompleted)
	}
}

func TestEmitAsyncAfterCloseSpoolsInsteadOfDropping(t *testing.T) {
	spoolPath := filepath.Join(t.TempDir(), "events.jsonl")
	emitter, err := NewHTTPEventEmitter(HTTPEventEmitterConfig{
		CallbackURL:        "http://127.0.0.1:1",
		BufferSize:         1,
		MaxRetries:         1,
		RetryDelay:         10 * time.Millisecond,
		SpoolFlushInterval: time.Hour,
		SpoolPath:          spoolPath,
	})
	if err != nil {
		t.Fatalf("NewHTTPEventEmitter() error = %v", err)
	}

	closeCtx, cancel := context.WithTimeout(context.Background(), 2*time.Second)
	defer cancel()
	if err := emitter.Close(closeCtx); err != nil {
		t.Fatalf("Close() error = %v", err)
	}

	emitter.EmitAsync(port.NewEvent(port.EventTypeRunCanceled, "run-closed"))

	data, readErr := os.ReadFile(spoolPath)
	if readErr != nil {
		t.Fatalf("ReadFile() error = %v", readErr)
	}
	lines := bytesSplitLines(data)
	if len(lines) != 1 {
		t.Fatalf("spool lines = %d, want 1", len(lines))
	}

	var event port.ExecutionEvent
	if err := json.Unmarshal(lines[0], &event); err != nil {
		t.Fatalf("json.Unmarshal() error = %v", err)
	}
	if event.RunID != "run-closed" {
		t.Fatalf("event.RunID = %s, want run-closed", event.RunID)
	}
}

func TestEmitSpoolsOnDeliveryFailure(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/problem+json")
		w.WriteHeader(http.StatusServiceUnavailable)
		_, _ = w.Write([]byte(`{"detail":"backend unavailable"}`))
	}))
	defer server.Close()

	spoolPath := filepath.Join(t.TempDir(), "events.jsonl")
	emitter, err := NewHTTPEventEmitter(HTTPEventEmitterConfig{
		CallbackURL:        server.URL,
		Client:             server.Client(),
		MaxRetries:         1,
		RetryDelay:         10 * time.Millisecond,
		SpoolPath:          spoolPath,
		SpoolFlushInterval: time.Hour,
	})
	if err != nil {
		t.Fatalf("NewHTTPEventEmitter() error = %v", err)
	}
	defer func() {
		closeCtx, cancel := context.WithTimeout(context.Background(), 2*time.Second)
		defer cancel()
		if err := emitter.Close(closeCtx); err != nil {
			t.Fatalf("Close() error = %v", err)
		}
	}()

	err = emitter.Emit(context.Background(), port.NewEvent(port.EventTypeRunFailed, "run-1"))
	if err == nil {
		t.Fatal("expected Emit() error")
	}
	if !strings.Contains(err.Error(), "backend unavailable") {
		t.Fatalf("Emit() error = %v, want response body detail", err)
	}

	data, readErr := os.ReadFile(spoolPath)
	if readErr != nil {
		t.Fatalf("ReadFile() error = %v", readErr)
	}
	if len(data) == 0 {
		t.Fatal("expected spooled event payload")
	}

	var event port.ExecutionEvent
	line := data[:len(data)-1]
	if unmarshalErr := json.Unmarshal(line, &event); unmarshalErr != nil {
		t.Fatalf("json.Unmarshal() error = %v", unmarshalErr)
	}
	if event.RunID != "run-1" {
		t.Fatalf("event.RunID = %s, want run-1", event.RunID)
	}
}

func TestEmitRetriesAndSpoolsRawConflict(t *testing.T) {
	var requestCount atomic.Int32
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		requestCount.Add(1)
		w.Header().Set("Content-Type", "application/problem+json")
		w.WriteHeader(http.StatusConflict)
		_, _ = w.Write([]byte(`{"detail":"invalid run transition"}`))
	}))
	defer server.Close()

	spoolPath := filepath.Join(t.TempDir(), "events.jsonl")
	emitter := &HTTPEventEmitter{
		callbackURL:    server.URL,
		client:         server.Client(),
		maxRetries:     3,
		retryDelay:     10 * time.Millisecond,
		spoolPath:      spoolPath,
		deadLetterPath: filepath.Join(t.TempDir(), "events.dead.jsonl"),
		spoolFlushCh:   make(chan struct{}, 1),
	}

	err := emitter.Emit(context.Background(), port.NewEvent(port.EventTypeRunCompleted, "run-1"))
	if err == nil {
		t.Fatal("expected Emit() error")
	}
	if !strings.Contains(err.Error(), "status 409") {
		t.Fatalf("Emit() error = %v, want status 409 detail", err)
	}

	if got := requestCount.Load(); got != 3 {
		t.Fatalf("requestCount = %d, want 3", got)
	}
	if _, statErr := os.Stat(spoolPath); statErr != nil {
		t.Fatalf("expected spool file, got stat error %v", statErr)
	}
}

func TestFlushSpoolRequeuesRawNotFoundEvents(t *testing.T) {
	var requestCount atomic.Int32
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		requestCount.Add(1)
		w.Header().Set("Content-Type", "application/problem+json")
		w.WriteHeader(http.StatusNotFound)
		_, _ = w.Write([]byte(`{"detail":"Run with id 'missing' not found."}`))
	}))
	defer server.Close()

	spoolPath := filepath.Join(t.TempDir(), "events.jsonl")
	event := port.NewEvent(port.EventTypeRunCompleted, "missing")
	payload, err := json.Marshal(event)
	if err != nil {
		t.Fatalf("json.Marshal() error = %v", err)
	}
	if writeErr := os.WriteFile(spoolPath, append(payload, '\n'), 0o600); writeErr != nil {
		t.Fatalf("WriteFile() error = %v", writeErr)
	}

	emitter, err := NewHTTPEventEmitter(HTTPEventEmitterConfig{
		CallbackURL:        server.URL,
		Client:             server.Client(),
		MaxRetries:         3,
		RetryDelay:         10 * time.Millisecond,
		SpoolPath:          spoolPath,
		SpoolFlushInterval: time.Hour,
	})
	if err != nil {
		t.Fatalf("NewHTTPEventEmitter() error = %v", err)
	}
	defer func() {
		closeCtx, cancel := context.WithTimeout(context.Background(), 2*time.Second)
		defer cancel()
		if err := emitter.Close(closeCtx); err != nil {
			t.Fatalf("Close() error = %v", err)
		}
	}()

	remaining, err := emitter.flushSpool(context.Background())
	if err != nil {
		t.Fatalf("flushSpool() error = %v", err)
	}
	if remaining != 1 {
		t.Fatalf("remaining = %d, want 1", remaining)
	}
	if got := requestCount.Load(); got != 3 {
		t.Fatalf("requestCount = %d, want 3", got)
	}
	if _, statErr := os.Stat(spoolPath); statErr != nil {
		t.Fatalf("expected spool file to remain, stat error = %v", statErr)
	}
	if _, statErr := os.Stat(spoolPath + ".processing"); !os.IsNotExist(statErr) {
		t.Fatalf("expected processing file to be removed, stat error = %v", statErr)
	}
}

func TestEmitMinimalVerbosityDropsObservabilityEvents(t *testing.T) {
	var requestCount atomic.Int32
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		requestCount.Add(1)
		writeCallbackDecision(t, w, http.StatusOK, "accepted", true)
	}))
	defer server.Close()

	emitter, err := NewHTTPEventEmitter(HTTPEventEmitterConfig{
		CallbackURL:    server.URL,
		Client:         server.Client(),
		EventVerbosity: "minimal",
		MaxRetries:     1,
	})
	if err != nil {
		t.Fatalf("NewHTTPEventEmitter() error = %v", err)
	}
	defer func() {
		closeCtx, cancel := context.WithTimeout(context.Background(), 2*time.Second)
		defer cancel()
		if err := emitter.Close(closeCtx); err != nil {
			t.Fatalf("Close() error = %v", err)
		}
	}()

	if err := emitter.Emit(context.Background(), port.NewEvent(port.EventTypeNodeStreamChunk, "run-1")); err != nil {
		t.Fatalf("Emit() error = %v", err)
	}
	if got := requestCount.Load(); got != 0 {
		t.Fatalf("requestCount = %d, want 0", got)
	}
}

func TestEmitStampsEngineInstanceAndCategory(t *testing.T) {
	received := make(chan *port.ExecutionEvent, 1)
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		defer r.Body.Close()

		var envelope struct {
			Payload struct {
				AttemptID        string `json:"attempt_id"`
				Category         string `json:"category"`
				EngineInstanceID string `json:"engine_instance_id"`
			} `json:"payload"`
		}
		if err := json.NewDecoder(r.Body).Decode(&envelope); err != nil {
			t.Fatalf("Decode() error = %v", err)
		}
		received <- &port.ExecutionEvent{
			AttemptID:        envelope.Payload.AttemptID,
			Category:         port.EventCategory(envelope.Payload.Category),
			EngineInstanceID: envelope.Payload.EngineInstanceID,
		}
		writeCallbackDecision(t, w, http.StatusOK, "accepted", true)
	}))
	defer server.Close()

	emitter, err := NewHTTPEventEmitter(HTTPEventEmitterConfig{
		CallbackURL:      server.URL,
		Client:           server.Client(),
		EngineInstanceID: "engine-a",
		MaxRetries:       1,
	})
	if err != nil {
		t.Fatalf("NewHTTPEventEmitter() error = %v", err)
	}
	defer func() {
		closeCtx, cancel := context.WithTimeout(context.Background(), 2*time.Second)
		defer cancel()
		if err := emitter.Close(closeCtx); err != nil {
			t.Fatalf("Close() error = %v", err)
		}
	}()

	event := port.NewEvent(port.EventTypeRunStarted, "run-1")
	event.Category = ""
	if err := emitter.Emit(context.Background(), event); err != nil {
		t.Fatalf("Emit() error = %v", err)
	}

	select {
	case delivered := <-received:
		if delivered.EngineInstanceID != "engine-a" {
			t.Fatalf("EngineInstanceID = %s, want engine-a", delivered.EngineInstanceID)
		}
		if delivered.Category != port.EventCategoryState {
			t.Fatalf("Category = %s, want %s", delivered.Category, port.EventCategoryState)
		}
	case <-time.After(2 * time.Second):
		t.Fatal("timed out waiting for emitted event")
	}
}

func TestEmitIncludesAttemptID(t *testing.T) {
	received := make(chan *port.ExecutionEvent, 1)
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		defer r.Body.Close()

		var envelope struct {
			Payload struct {
				AttemptID string `json:"attempt_id"`
			} `json:"payload"`
		}
		if err := json.NewDecoder(r.Body).Decode(&envelope); err != nil {
			t.Fatalf("Decode() error = %v", err)
		}
		received <- &port.ExecutionEvent{AttemptID: envelope.Payload.AttemptID}
		writeCallbackDecision(t, w, http.StatusOK, "accepted", true)
	}))
	defer server.Close()

	emitter, err := NewHTTPEventEmitter(HTTPEventEmitterConfig{
		CallbackURL: server.URL,
		Client:      server.Client(),
		MaxRetries:  1,
	})
	if err != nil {
		t.Fatalf("NewHTTPEventEmitter() error = %v", err)
	}
	defer func() {
		closeCtx, cancel := context.WithTimeout(context.Background(), 2*time.Second)
		defer cancel()
		if err := emitter.Close(closeCtx); err != nil {
			t.Fatalf("Close() error = %v", err)
		}
	}()

	event := port.NewEvent(port.EventTypeNodeCompleted, "run-1").
		WithNode("node-1", "task", "Task").
		WithAttempt(2).
		WithAttemptID("attempt-b")
	if err := emitter.Emit(context.Background(), event); err != nil {
		t.Fatalf("Emit() error = %v", err)
	}

	select {
	case delivered := <-received:
		if delivered.AttemptID != "attempt-b" {
			t.Fatalf("AttemptID = %s, want attempt-b", delivered.AttemptID)
		}
	case <-time.After(2 * time.Second):
		t.Fatal("timed out waiting for emitted event")
	}
}

func TestEmitUsesCanonicalEventEnvelopeV2(t *testing.T) {
	received := make(chan map[string]any, 1)
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		defer r.Body.Close()

		var envelope map[string]any
		if err := json.NewDecoder(r.Body).Decode(&envelope); err != nil {
			t.Fatalf("Decode() error = %v", err)
		}
		received <- envelope
		writeCallbackDecision(t, w, http.StatusOK, "accepted", true)
	}))
	defer server.Close()

	emitter, err := NewHTTPEventEmitter(HTTPEventEmitterConfig{
		CallbackURL: server.URL,
		Client:      server.Client(),
		MaxRetries:  1,
	})
	if err != nil {
		t.Fatalf("NewHTTPEventEmitter() error = %v", err)
	}
	defer func() {
		closeCtx, cancel := context.WithTimeout(context.Background(), 2*time.Second)
		defer cancel()
		if err := emitter.Close(closeCtx); err != nil {
			t.Fatalf("Close() error = %v", err)
		}
	}()

	event := port.NewEvent(port.EventTypeNodeCompleted, "run-canonical").
		WithTenantID("tenant-1").
		WithNode("node-1", "prompt", "Prompt").
		WithAttempt(1).
		WithOutput(map[string]any{"ok": true})
	if err := emitter.Emit(context.Background(), event); err != nil {
		t.Fatalf("Emit() error = %v", err)
	}

	select {
	case envelope := <-received:
		for _, forbidden := range []string{"specversion", "data", "datacontenttype", "subject"} {
			if _, ok := envelope[forbidden]; ok {
				t.Fatalf("canonical envelope unexpectedly contains %s: %#v", forbidden, envelope)
			}
		}
		if got := envelope["schema_version"]; got != float64(2) {
			t.Fatalf("schema_version = %#v, want 2", got)
		}
		if got := envelope["source"]; got != "engine" {
			t.Fatalf("source = %#v, want engine", got)
		}
		if got := envelope["type"]; got != "node.completed" {
			t.Fatalf("type = %#v, want node.completed", got)
		}
		if got := envelope["tenant_id"]; got != "tenant-1" {
			t.Fatalf("tenant_id = %#v, want tenant-1", got)
		}
		if envelope["idempotency_key"] == "" || envelope["checksum"] == "" {
			t.Fatalf("missing canonical idempotency/checksum: %#v", envelope)
		}
		payload, ok := envelope["payload"].(map[string]any)
		if !ok || payload["node_id"] != "node-1" {
			t.Fatalf("payload = %#v, want node_id", envelope["payload"])
		}
	case <-time.After(2 * time.Second):
		t.Fatal("timed out waiting for emitted event")
	}
}

func TestCanonicalMemoryIntentPayloadIsBackendOwnedShape(t *testing.T) {
	event := port.NewEvent(port.EventTypeMemoryFactExtracted, "run-memory").
		WithTenantID("tenant-1").
		WithOutput(map[string]any{
			"fact":        "Customer prefers concise approvals.",
			"source_span": "turn-12",
			"confidence":  0.91,
		})

	envelope := toCanonicalEventEnvelope(event)
	if got := envelope["type"]; got != "memory.fact_extracted" {
		t.Fatalf("type = %#v, want memory.fact_extracted", got)
	}
	payload, ok := envelope["payload"].(map[string]any)
	if !ok {
		t.Fatalf("payload = %#v, want object", envelope["payload"])
	}
	if _, ok := payload["output"]; ok {
		t.Fatalf("memory intent payload must not nest product memory under output: %#v", payload)
	}
	if got := payload["fact"]; got != "Customer prefers concise approvals." {
		t.Fatalf("fact = %#v", got)
	}
	if got := payload["source_span"]; got != "turn-12" {
		t.Fatalf("source_span = %#v", got)
	}
	if got := payload["confidence"]; got != 0.91 {
		t.Fatalf("confidence = %#v", got)
	}
}

func TestEmitAsyncFreezesMutableEventPayload(t *testing.T) {
	received := make(chan map[string]any, 1)
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		defer r.Body.Close()

		var envelope struct {
			Payload struct {
				Output map[string]any `json:"output"`
			} `json:"payload"`
		}
		if err := json.NewDecoder(r.Body).Decode(&envelope); err != nil {
			t.Fatalf("Decode() error = %v", err)
		}
		received <- envelope.Payload.Output
		writeCallbackDecision(t, w, http.StatusOK, "accepted", true)
	}))
	defer server.Close()

	emitter, err := NewHTTPEventEmitter(HTTPEventEmitterConfig{
		CallbackURL: server.URL,
		Client:      server.Client(),
		MaxRetries:  1,
	})
	if err != nil {
		t.Fatalf("NewHTTPEventEmitter() error = %v", err)
	}
	defer func() {
		closeCtx, cancel := context.WithTimeout(context.Background(), 2*time.Second)
		defer cancel()
		if err := emitter.Close(closeCtx); err != nil {
			t.Fatalf("Close() error = %v", err)
		}
	}()

	output := map[string]any{
		"memory_context": map[string]any{
			"curated_observation_count": 1,
			"curated_observations": []any{
				map[string]any{"title": "before"},
			},
		},
	}
	event := port.NewEvent(port.EventTypeNodeCompleted, "run-async-freeze").WithOutput(output)
	emitter.EmitAsync(event)

	output["memory_context"].(map[string]any)["curated_observation_count"] = 9
	output["memory_context"].(map[string]any)["curated_observations"].([]any)[0].(map[string]any)["title"] = "after"

	flushCtx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()
	if err := emitter.Flush(flushCtx); err != nil {
		t.Fatalf("Flush() error = %v", err)
	}

	select {
	case delivered := <-received:
		memoryContext, ok := delivered["memory_context"].(map[string]any)
		if !ok {
			t.Fatalf("memory_context missing from delivered payload: %#v", delivered)
		}
		if got := memoryContext["curated_observation_count"]; got != float64(1) {
			t.Fatalf("curated_observation_count = %#v, want 1", got)
		}
		curatedObservations, ok := memoryContext["curated_observations"].([]any)
		if !ok || len(curatedObservations) != 1 {
			t.Fatalf("curated_observations = %#v, want single observation", memoryContext["curated_observations"])
		}
		observation, ok := curatedObservations[0].(map[string]any)
		if !ok {
			t.Fatalf("observation = %#v, want object", curatedObservations[0])
		}
		if got := observation["title"]; got != "before" {
			t.Fatalf("title = %#v, want before", got)
		}
	case <-time.After(2 * time.Second):
		t.Fatal("timed out waiting for emitted event")
	}
}

func TestEmitCallbackDecisionStatusPairs(t *testing.T) {
	tests := []struct {
		name           string
		statusCode     int
		decision       string
		safeToDiscard  bool
		wantErr        bool
		wantRequests   int32
		wantSpool      bool
		wantDeadLetter bool
	}{
		{
			name:          "accepted",
			statusCode:    http.StatusOK,
			decision:      "accepted",
			safeToDiscard: true,
			wantRequests:  1,
		},
		{
			name:          "duplicate applied",
			statusCode:    http.StatusOK,
			decision:      "duplicate",
			safeToDiscard: true,
			wantRequests:  1,
		},
		{
			name:          "stale superseded conflict",
			statusCode:    http.StatusConflict,
			decision:      "stale_superseded",
			safeToDiscard: true,
			wantRequests:  1,
		},
		{
			name:          "ordering conflict retry",
			statusCode:    http.StatusConflict,
			decision:      "retry_required",
			safeToDiscard: false,
			wantErr:       true,
			wantRequests:  2,
			wantSpool:     true,
		},
		{
			name:           "invalid schema dead letter",
			statusCode:     http.StatusBadRequest,
			decision:       "reject_invalid",
			safeToDiscard:  true,
			wantErr:        true,
			wantRequests:   1,
			wantDeadLetter: true,
		},
		{
			name:          "unsafe accepted response retries",
			statusCode:    http.StatusOK,
			decision:      "accepted",
			safeToDiscard: false,
			wantErr:       true,
			wantRequests:  2,
			wantSpool:     true,
		},
	}

	for _, tc := range tests {
		t.Run(tc.name, func(t *testing.T) {
			var requestCount atomic.Int32
			server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
				requestCount.Add(1)
				writeCallbackDecision(t, w, tc.statusCode, tc.decision, tc.safeToDiscard)
			}))
			defer server.Close()

			tempDir := t.TempDir()
			spoolPath := filepath.Join(tempDir, "events.jsonl")
			deadLetterPath := filepath.Join(tempDir, "events.dead.jsonl")
			emitter, err := NewHTTPEventEmitter(HTTPEventEmitterConfig{
				CallbackURL:        server.URL,
				Client:             server.Client(),
				MaxRetries:         2,
				RetryDelay:         10 * time.Millisecond,
				SpoolPath:          spoolPath,
				DeadLetterPath:     deadLetterPath,
				SpoolFlushInterval: time.Hour,
			})
			if err != nil {
				t.Fatalf("NewHTTPEventEmitter() error = %v", err)
			}
			defer func() {
				closeCtx, cancel := context.WithTimeout(context.Background(), 2*time.Second)
				defer cancel()
				if err := emitter.Close(closeCtx); err != nil {
					t.Fatalf("Close() error = %v", err)
				}
			}()

			err = emitter.Emit(context.Background(), port.NewEvent(port.EventTypeRunCompleted, "run-1"))
			if tc.wantErr && err == nil {
				t.Fatal("expected Emit() error")
			}
			if !tc.wantErr && err != nil {
				t.Fatalf("Emit() error = %v", err)
			}
			if got := requestCount.Load(); got != tc.wantRequests {
				t.Fatalf("requestCount = %d, want %d", got, tc.wantRequests)
			}
			if _, statErr := os.Stat(spoolPath); tc.wantSpool != (statErr == nil) {
				t.Fatalf("spool exists = %v, want %v (stat error %v)", statErr == nil, tc.wantSpool, statErr)
			}
			if _, statErr := os.Stat(deadLetterPath); tc.wantDeadLetter != (statErr == nil) {
				t.Fatalf(
					"dead-letter exists = %v, want %v (stat error %v)",
					statErr == nil,
					tc.wantDeadLetter,
					statErr,
				)
			}
		})
	}
}

func TestEmitAuthFailureDoesNotRetrySpoolOrDeadLetter(t *testing.T) {
	var requestCount atomic.Int32
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		requestCount.Add(1)
		writeCallbackDecision(t, w, http.StatusUnauthorized, "reject_invalid", false)
	}))
	defer server.Close()

	tempDir := t.TempDir()
	spoolPath := filepath.Join(tempDir, "events.jsonl")
	deadLetterPath := filepath.Join(tempDir, "events.dead.jsonl")
	emitter, err := NewHTTPEventEmitter(HTTPEventEmitterConfig{
		CallbackURL:        server.URL,
		Client:             server.Client(),
		MaxRetries:         3,
		RetryDelay:         10 * time.Millisecond,
		SpoolPath:          spoolPath,
		DeadLetterPath:     deadLetterPath,
		SpoolFlushInterval: time.Hour,
	})
	if err != nil {
		t.Fatalf("NewHTTPEventEmitter() error = %v", err)
	}
	defer func() {
		closeCtx, cancel := context.WithTimeout(context.Background(), 2*time.Second)
		defer cancel()
		if err := emitter.Close(closeCtx); err != nil {
			t.Fatalf("Close() error = %v", err)
		}
	}()

	err = emitter.Emit(context.Background(), port.NewEvent(port.EventTypeRunFailed, "run-auth"))
	if err == nil {
		t.Fatal("expected Emit() error")
	}
	if got := requestCount.Load(); got != 1 {
		t.Fatalf("requestCount = %d, want 1", got)
	}
	if _, statErr := os.Stat(spoolPath); !os.IsNotExist(statErr) {
		t.Fatalf("expected no spool file, stat error = %v", statErr)
	}
	if _, statErr := os.Stat(deadLetterPath); !os.IsNotExist(statErr) {
		t.Fatalf("expected no dead-letter file, stat error = %v", statErr)
	}
}

func TestEmitSpoolsWhenSuccessResponseMissingDecision(t *testing.T) {
	var requestCount atomic.Int32
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		requestCount.Add(1)
		w.WriteHeader(http.StatusOK)
	}))
	defer server.Close()

	spoolPath := filepath.Join(t.TempDir(), "events.jsonl")
	emitter, err := NewHTTPEventEmitter(HTTPEventEmitterConfig{
		CallbackURL:        server.URL,
		Client:             server.Client(),
		MaxRetries:         2,
		RetryDelay:         10 * time.Millisecond,
		SpoolPath:          spoolPath,
		SpoolFlushInterval: time.Hour,
	})
	if err != nil {
		t.Fatalf("NewHTTPEventEmitter() error = %v", err)
	}
	defer func() {
		closeCtx, cancel := context.WithTimeout(context.Background(), 2*time.Second)
		defer cancel()
		if err := emitter.Close(closeCtx); err != nil {
			t.Fatalf("Close() error = %v", err)
		}
	}()

	err = emitter.Emit(context.Background(), port.NewEvent(port.EventTypeRunStarted, "run-missing-decision"))
	if err == nil {
		t.Fatal("expected Emit() error")
	}
	if got := requestCount.Load(); got != 2 {
		t.Fatalf("requestCount = %d, want 2", got)
	}
	if _, statErr := os.Stat(spoolPath); statErr != nil {
		t.Fatalf("expected spool file, stat error = %v", statErr)
	}
}

func assertEventually(t *testing.T, timeout time.Duration, condition func() bool) {
	t.Helper()

	if condition() {
		return
	}
	timer := time.NewTimer(timeout)
	defer timer.Stop()
	ticker := time.NewTicker(20 * time.Millisecond)
	defer ticker.Stop()
	for {
		select {
		case <-timer.C:
			t.Fatal("condition was not satisfied before timeout")
		case <-ticker.C:
			if condition() {
				return
			}
		}
	}
}

func bytesSplitLines(data []byte) [][]byte {
	lines := make([][]byte, 0)
	start := 0
	for i, b := range data {
		if b != '\n' {
			continue
		}
		if i > start {
			lines = append(lines, data[start:i])
		}
		start = i + 1
	}
	if start < len(data) {
		lines = append(lines, data[start:])
	}
	return lines
}
