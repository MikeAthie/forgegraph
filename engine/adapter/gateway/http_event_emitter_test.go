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

func TestEmitDoesNotRetryOrSpoolOnNonRetryableConflict(t *testing.T) {
	var requestCount atomic.Int32
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		requestCount.Add(1)
		w.Header().Set("Content-Type", "application/problem+json")
		w.WriteHeader(http.StatusConflict)
		_, _ = w.Write([]byte(`{"detail":"invalid run transition"}`))
	}))
	defer server.Close()

	spoolPath := filepath.Join(t.TempDir(), "events.jsonl")
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

	err = emitter.Emit(context.Background(), port.NewEvent(port.EventTypeRunCompleted, "run-1"))
	if err == nil {
		t.Fatal("expected Emit() error")
	}
	if !strings.Contains(err.Error(), "status 409") {
		t.Fatalf("Emit() error = %v, want status 409 detail", err)
	}

	if got := requestCount.Load(); got != 1 {
		t.Fatalf("requestCount = %d, want 1", got)
	}
	if _, statErr := os.Stat(spoolPath); !os.IsNotExist(statErr) {
		t.Fatalf("expected no spool file, got stat error %v", statErr)
	}
}

func TestFlushSpoolDropsNonRetryableNotFoundEvents(t *testing.T) {
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
	if remaining != 0 {
		t.Fatalf("remaining = %d, want 0", remaining)
	}
	if got := requestCount.Load(); got != 1 {
		t.Fatalf("requestCount = %d, want 1", got)
	}
	for _, candidatePath := range []string{spoolPath, spoolPath + ".processing"} {
		if _, statErr := os.Stat(candidatePath); !os.IsNotExist(statErr) {
			t.Fatalf("expected %s to be removed, stat error = %v", candidatePath, statErr)
		}
	}
}

func TestEmitMinimalVerbosityDropsObservabilityEvents(t *testing.T) {
	var requestCount atomic.Int32
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		requestCount.Add(1)
		w.WriteHeader(http.StatusOK)
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
			Data port.ExecutionEvent `json:"data"`
		}
		if err := json.NewDecoder(r.Body).Decode(&envelope); err != nil {
			t.Fatalf("Decode() error = %v", err)
		}
		received <- &envelope.Data
		w.WriteHeader(http.StatusOK)
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
			Data port.ExecutionEvent `json:"data"`
		}
		if err := json.NewDecoder(r.Body).Decode(&envelope); err != nil {
			t.Fatalf("Decode() error = %v", err)
		}
		received <- &envelope.Data
		w.WriteHeader(http.StatusOK)
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

func TestEmitAsyncFreezesMutableEventPayload(t *testing.T) {
	received := make(chan map[string]any, 1)
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		defer r.Body.Close()

		var envelope struct {
			Data struct {
				Output map[string]any `json:"output"`
			} `json:"data"`
		}
		if err := json.NewDecoder(r.Body).Decode(&envelope); err != nil {
			t.Fatalf("Decode() error = %v", err)
		}
		received <- envelope.Data.Output
		w.WriteHeader(http.StatusOK)
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

func assertEventually(t *testing.T, timeout time.Duration, condition func() bool) {
	t.Helper()

	deadline := time.Now().Add(timeout)
	for time.Now().Before(deadline) {
		if condition() {
			return
		}
		time.Sleep(20 * time.Millisecond)
	}
	t.Fatal("condition was not satisfied before timeout")
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
