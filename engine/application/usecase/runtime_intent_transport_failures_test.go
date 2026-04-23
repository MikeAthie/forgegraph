package usecase

import (
	"bytes"
	"context"
	"log/slog"
	"net"
	"strings"
	"testing"
	"time"

	"github.com/forgegraph/engine/adapter/gateway"
	"github.com/forgegraph/engine/application/port"
	"github.com/forgegraph/engine/domain/entity"
	"github.com/forgegraph/engine/domain/value"
	redis "github.com/redis/go-redis/v9"
)

func TestPauseIntentPublishFailsClosedWhenRedisIsUnavailable(t *testing.T) {
	engine := NewTestEngine(t, 2)

	publisher, client := newUnavailableRedisRuntimeIntentPublisher(t)
	defer func() {
		_ = client.Close()
	}()
	engine.Scheduler.SetRuntimeIntentPublisher(publisher, RuntimeWriteModePauseIntents)

	engine.RegisterExecutor(string(value.NodeTypeTransform), func(ctx context.Context, node *entity.Node, state *entity.State) (*port.NodeExecutionResult, error) {
		return port.NewSuccessResult(map[string]any{"prepared": true}), nil
	})
	engine.RegisterExecutor(string(value.NodeTypeHumanGate), func(ctx context.Context, node *entity.Node, state *entity.State) (*port.NodeExecutionResult, error) {
		return port.NewPauseResult(map[string]any{"prompt_message": "approve"}), nil
	})
	engine.RegisterExecutor(string(value.NodeTypeOutput), func(ctx context.Context, node *entity.Node, state *entity.State) (*port.NodeExecutionResult, error) {
		return port.NewSuccessResult(map[string]any{"done": true}), nil
	})

	runID := "run-redis-publish-down"
	graphJSON := makeGraphJSON(
		[]entity.Node{
			{ID: "start", Type: string(value.NodeTypeTransform), Name: "Start", Config: map[string]any{}},
			{ID: "gate", Type: string(value.NodeTypeHumanGate), Name: "Gate", Config: map[string]any{}},
			{ID: "output", Type: string(value.NodeTypeOutput), Name: "Output", Config: map[string]any{}},
		},
		[]entity.Edge{
			{From: "start", To: "gate"},
			{From: "gate", To: "output"},
		},
	)

	var snapshot *RunSnapshot
	logOutput := captureStdlibLog(t, func() {
		engine.StartRun(runID, graphJSON, "{}")
		engine.AwaitBlockedAttempt(runID, "start", 1)
		engine.Release(runID, "start")
		engine.AwaitBlockedAttempt(runID, "gate", 1)
		engine.Release(runID, "gate")
		snapshot = engine.AwaitRunStatus(runID, string(value.RunStatusFailed))
	})

	if snapshot == nil {
		t.Fatal("expected failed run snapshot")
	}
	if !strings.Contains(snapshot.Error, "failed to publish pause_run intent") {
		t.Fatalf("expected publish failure in run error, got %q", snapshot.Error)
	}
	if _, ok := engine.Repo.pauses[runID]; ok {
		t.Fatalf("expected no persisted pause state when publish fails")
	}
	if countEvents(engine.Bus.All(), port.EventTypeRunPaused) != 0 {
		t.Fatalf("expected no run_paused event when pause intent publish fails")
	}
	if countEvents(engine.Bus.All(), port.EventTypeRunFailed) != 1 {
		t.Fatalf("expected one run_failed event, got %d", countEvents(engine.Bus.All(), port.EventTypeRunFailed))
	}
	if !strings.Contains(logOutput, "intent_publish_start") {
		t.Fatalf("expected intent_publish_start log, got %q", logOutput)
	}
	if !strings.Contains(logOutput, "intent_publish_failed") {
		t.Fatalf("expected intent_publish_failed log, got %q", logOutput)
	}
	if strings.Contains(logOutput, "intent_publish_success") {
		t.Fatalf("did not expect intent_publish_success log, got %q", logOutput)
	}
}

func newUnavailableRedisRuntimeIntentPublisher(t *testing.T) (*gateway.RedisRuntimeIntentPublisher, *redis.Client) {
	t.Helper()

	listener, err := net.Listen("tcp", "127.0.0.1:0")
	if err != nil {
		t.Fatalf("Listen() error = %v", err)
	}
	addr := listener.Addr().String()
	_ = listener.Close()

	client := redis.NewClient(&redis.Options{
		Addr:         addr,
		DialTimeout:  20 * time.Millisecond,
		ReadTimeout:  20 * time.Millisecond,
		WriteTimeout: 20 * time.Millisecond,
	})
	publisher, err := gateway.NewRedisRuntimeIntentPublisherWithConfig(
		client,
		"forgegraph:test:runtime:intents",
		gateway.RuntimeIntentPublisherConfig{
			InitialBackoff: 5 * time.Millisecond,
			MaxBackoff:     10 * time.Millisecond,
			MaxElapsedTime: 30 * time.Millisecond,
		},
	)
	if err != nil {
		t.Fatalf("NewRedisRuntimeIntentPublisher() error = %v", err)
	}
	return publisher, client
}

func captureStdlibLog(t *testing.T, fn func()) string {
	t.Helper()

	var buffer bytes.Buffer
	originalLogger := slog.Default()
	logger := slog.New(slog.NewTextHandler(&buffer, &slog.HandlerOptions{Level: slog.LevelInfo}))
	slog.SetDefault(logger)
	defer func() {
		slog.SetDefault(originalLogger)
	}()

	fn()
	return buffer.String()
}
