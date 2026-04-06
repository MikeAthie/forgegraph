package gateway

import (
	"context"
	"encoding/json"
	"errors"
	"net/http"
	"net/http/httptest"
	"os"
	"path/filepath"
	"sync"
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
	releaseRequests := make(chan struct{})
	var releaseOnce sync.Once
	var requestCount atomic.Int32

	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		requestCount.Add(1)
		<-releaseRequests
		w.WriteHeader(http.StatusOK)
	}))
	defer server.Close()
	defer releaseOnce.Do(func() { close(releaseRequests) })

	spoolPath := filepath.Join(t.TempDir(), "events.jsonl")
	emitter, err := NewHTTPEventEmitter(HTTPEventEmitterConfig{
		CallbackURL: server.URL,
		Client:      server.Client(),
		BufferSize:  1,
		RetryDelay:  10 * time.Millisecond,
		MaxRetries:  1,
		SpoolPath:   spoolPath,
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

	emitter.EmitAsync(port.NewEvent(port.EventTypeRunStarted, "run-1"))
	emitter.EmitAsync(port.NewEvent(port.EventTypeNodeStarted, "run-1"))

	thirdQueued := make(chan time.Duration, 1)
	start := time.Now()
	go func() {
		emitter.EmitAsync(port.NewEvent(port.EventTypeNodeCompleted, "run-1"))
		thirdQueued <- time.Since(start)
	}()

	select {
	case elapsed := <-thirdQueued:
		if elapsed > 150*time.Millisecond {
			t.Fatalf("third EmitAsync took %v, want fast spool fallback", elapsed)
		}
	case <-time.After(500 * time.Millisecond):
		t.Fatal("third EmitAsync did not return promptly")
	}

	processingPath := spoolPath + ".processing"
	assertEventually(t, 2*time.Second, func() bool {
		for _, candidatePath := range []string{spoolPath, processingPath} {
			info, statErr := os.Stat(candidatePath)
			if statErr == nil && info.Size() > 0 {
				return true
			}
		}
		return false
	})

	releaseOnce.Do(func() { close(releaseRequests) })

	flushCtx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()
	if err := emitter.Flush(flushCtx); err != nil {
		t.Fatalf("Flush() error = %v", err)
	}

	assertEventually(t, 2*time.Second, func() bool {
		for _, candidatePath := range []string{spoolPath, processingPath} {
			if _, statErr := os.Stat(candidatePath); !os.IsNotExist(statErr) {
				return false
			}
		}
		return true
	})

	if got := requestCount.Load(); got < 3 {
		t.Fatalf("requestCount = %d, want at least 3", got)
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
		w.WriteHeader(http.StatusServiceUnavailable)
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
