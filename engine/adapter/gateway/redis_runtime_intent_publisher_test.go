package gateway

import (
	"context"
	"errors"
	"testing"
	"time"

	"github.com/forgegraph/engine/application/port"
	redis "github.com/redis/go-redis/v9"
)

type stubRuntimeIntentStreamClient struct {
	callCount int
	results   []stubXAddResult
}

type stubXAddResult struct {
	messageID string
	err       error
}

func (s *stubRuntimeIntentStreamClient) XAdd(ctx context.Context, a *redis.XAddArgs) *redis.StringCmd {
	_ = a
	cmd := redis.NewStringCmd(ctx)
	if s.callCount >= len(s.results) {
		cmd.SetVal("1-0")
		s.callCount++
		return cmd
	}
	result := s.results[s.callCount]
	s.callCount++
	if result.err != nil {
		cmd.SetErr(result.err)
		return cmd
	}
	cmd.SetVal(result.messageID)
	return cmd
}

func TestRedisRuntimeIntentPublisherRetriesTransientFailures(t *testing.T) {
	client := &stubRuntimeIntentStreamClient{
		results: []stubXAddResult{
			{err: errors.New("READONLY You can't write against a read only replica.")},
			{err: errors.New("i/o timeout")},
			{messageID: "3-0"},
		},
	}
	publisher, err := NewRedisRuntimeIntentPublisherWithConfig(
		client,
		"forgegraph:test:runtime:intents",
		RuntimeIntentPublisherConfig{
			InitialBackoff: time.Millisecond,
			MaxBackoff:     2 * time.Millisecond,
			MaxElapsedTime: time.Second,
		},
	)
	if err != nil {
		t.Fatalf("NewRedisRuntimeIntentPublisherWithConfig() error = %v", err)
	}
	publisher.sleep = func(ctx context.Context, delay time.Duration) error {
		_ = ctx
		_ = delay
		return nil
	}

	intent := &port.RuntimeIntentEnvelope{
		IntentID:   "intent-1",
		IntentType: "pause_run",
		RunID:      "run-1",
		AttemptID:  "attempt-1",
		Payload:    map[string]any{"node_id": "gate"},
	}
	if err := publisher.Publish(context.Background(), intent); err != nil {
		t.Fatalf("Publish() error = %v", err)
	}
	if client.callCount != 3 {
		t.Fatalf("expected 3 publish attempts, got %d", client.callCount)
	}
}

func TestRedisRuntimeIntentPublisherFailsFastOnFatalAuthError(t *testing.T) {
	client := &stubRuntimeIntentStreamClient{
		results: []stubXAddResult{
			{err: errors.New("WRONGPASS invalid username-password pair")},
		},
	}
	publisher, err := NewRedisRuntimeIntentPublisherWithConfig(
		client,
		"forgegraph:test:runtime:intents",
		RuntimeIntentPublisherConfig{
			InitialBackoff: time.Millisecond,
			MaxBackoff:     time.Millisecond,
			MaxElapsedTime: time.Second,
		},
	)
	if err != nil {
		t.Fatalf("NewRedisRuntimeIntentPublisherWithConfig() error = %v", err)
	}
	publisher.sleep = func(ctx context.Context, delay time.Duration) error {
		_ = ctx
		_ = delay
		return nil
	}

	intent := &port.RuntimeIntentEnvelope{
		IntentID:   "intent-1",
		IntentType: "pause_run",
		RunID:      "run-1",
		AttemptID:  "attempt-1",
		Payload:    map[string]any{"node_id": "gate"},
	}
	err = publisher.Publish(context.Background(), intent)
	if err == nil {
		t.Fatal("expected publish error")
	}
	var publishErr *RuntimeIntentPublishError
	if !errors.As(err, &publishErr) {
		t.Fatalf("expected RuntimeIntentPublishError, got %T", err)
	}
	if publishErr.Retryable {
		t.Fatalf("expected fatal auth error to be non-retryable")
	}
	if client.callCount != 1 {
		t.Fatalf("expected one publish attempt, got %d", client.callCount)
	}
}
