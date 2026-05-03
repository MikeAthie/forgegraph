package gateway

import (
	"context"
	"encoding/json"
	"errors"
	"net/http"
	"net/http/httptest"
	"strings"
	"sync/atomic"
	"testing"
	"time"

	"github.com/forgegraph/engine/application/port"
)

type stubInnerRuntimeIntentPublisher struct {
	count int32
	err   error
}

func (p *stubInnerRuntimeIntentPublisher) Publish(ctx context.Context, intent *port.RuntimeIntentEnvelope) error {
	_ = ctx
	_ = intent
	atomic.AddInt32(&p.count, 1)
	return p.err
}

func runtimeIntentOutcomeResponse(t *testing.T, w http.ResponseWriter, outcome string) {
	t.Helper()
	_ = json.NewEncoder(w).Encode(map[string]any{
		"data": map[string]any{
			"outcome":     outcome,
			"reason":      "test outcome",
			"error_class": "test",
		},
	})
}

func newBackendAckPublisherForTest(t *testing.T, serverURL string, inner *stubInnerRuntimeIntentPublisher, timeout time.Duration) *BackendAcknowledgedRuntimeIntentPublisher {
	t.Helper()
	publisher, err := NewBackendAcknowledgedRuntimeIntentPublisher(
		inner,
		serverURL,
		"test-secret",
		nil,
		RuntimeIntentOutcomeWaitConfig{
			Timeout:      timeout,
			PollInterval: time.Millisecond,
		},
	)
	if err != nil {
		t.Fatalf("NewBackendAcknowledgedRuntimeIntentPublisher() error = %v", err)
	}
	return publisher
}

func TestBackendAcknowledgedRuntimeIntentPublisherAcceptsProcessedAndDuplicate(t *testing.T) {
	for _, outcome := range []string{"processed", "duplicate"} {
		t.Run(outcome, func(t *testing.T) {
			server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
				if r.Method != http.MethodGet {
					t.Fatalf("method = %s", r.Method)
				}
				if !strings.HasPrefix(r.URL.Path, "/api/engine/runtime-intents/") {
					t.Fatalf("path = %s", r.URL.Path)
				}
				runtimeIntentOutcomeResponse(t, w, outcome)
			}))
			defer server.Close()

			inner := &stubInnerRuntimeIntentPublisher{}
			publisher := newBackendAckPublisherForTest(t, server.URL, inner, 50*time.Millisecond)
			err := publisher.Publish(context.Background(), &port.RuntimeIntentEnvelope{
				IntentID:   "intent-" + outcome,
				IntentType: "pause_run",
				RunID:      "run-1",
			})
			if err != nil {
				t.Fatalf("Publish() error = %v", err)
			}
			if atomic.LoadInt32(&inner.count) != 1 {
				t.Fatalf("expected inner publisher to be called once, got %d", inner.count)
			}
		})
	}
}

func TestBackendAcknowledgedRuntimeIntentPublisherRejectsTerminalFailureOutcomes(t *testing.T) {
	for _, outcome := range []string{"invalid", "dead_lettered", "ignored"} {
		t.Run(outcome, func(t *testing.T) {
			server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
				_ = r
				runtimeIntentOutcomeResponse(t, w, outcome)
			}))
			defer server.Close()

			inner := &stubInnerRuntimeIntentPublisher{}
			publisher := newBackendAckPublisherForTest(t, server.URL, inner, 50*time.Millisecond)
			err := publisher.Publish(context.Background(), &port.RuntimeIntentEnvelope{
				IntentID:   "intent-" + outcome,
				IntentType: "ack_run_resumed",
				RunID:      "run-1",
			})
			if err == nil {
				t.Fatal("expected terminal outcome error")
			}
			var outcomeErr *RuntimeIntentOutcomeError
			if !errors.As(err, &outcomeErr) {
				t.Fatalf("expected RuntimeIntentOutcomeError, got %T", err)
			}
			if outcomeErr.Outcome != outcome {
				t.Fatalf("outcome = %q, want %q", outcomeErr.Outcome, outcome)
			}
		})
	}
}

func TestBackendAcknowledgedRuntimeIntentPublisherWaitsForPendingOutcome(t *testing.T) {
	var calls int32
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		_ = r
		if atomic.AddInt32(&calls, 1) < 3 {
			w.WriteHeader(http.StatusNotFound)
			return
		}
		runtimeIntentOutcomeResponse(t, w, "processed")
	}))
	defer server.Close()

	inner := &stubInnerRuntimeIntentPublisher{}
	publisher := newBackendAckPublisherForTest(t, server.URL, inner, 100*time.Millisecond)
	err := publisher.Publish(context.Background(), &port.RuntimeIntentEnvelope{
		IntentID:   "intent-eventually-processed",
		IntentType: "store_checkpoint",
		RunID:      "run-1",
	})
	if err != nil {
		t.Fatalf("Publish() error = %v", err)
	}
	if atomic.LoadInt32(&calls) < 3 {
		t.Fatalf("expected pending poll retries, got %d call(s)", calls)
	}
}

func TestBackendAcknowledgedRuntimeIntentPublisherFailsClosedOnOutcomeTimeout(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		_ = r
		w.WriteHeader(http.StatusNotFound)
	}))
	defer server.Close()

	inner := &stubInnerRuntimeIntentPublisher{}
	publisher := newBackendAckPublisherForTest(t, server.URL, inner, 5*time.Millisecond)
	err := publisher.Publish(context.Background(), &port.RuntimeIntentEnvelope{
		IntentID:   "intent-timeout",
		IntentType: "store_checkpoint",
		RunID:      "run-1",
	})
	if err == nil {
		t.Fatal("expected timeout")
	}
	if !strings.Contains(err.Error(), "outcome wait timed out") {
		t.Fatalf("unexpected error: %v", err)
	}
}

func TestBackendAcknowledgedRuntimeIntentPublisherFailsClosedWhenBackendUnavailable(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		_ = w
		_ = r
	}))
	baseURL := server.URL
	server.Close()

	inner := &stubInnerRuntimeIntentPublisher{}
	publisher := newBackendAckPublisherForTest(t, baseURL, inner, 50*time.Millisecond)
	err := publisher.Publish(context.Background(), &port.RuntimeIntentEnvelope{
		IntentID:   "intent-backend-down",
		IntentType: "set_run_status",
		RunID:      "run-1",
	})
	if err == nil {
		t.Fatal("expected backend unavailable error")
	}
}
