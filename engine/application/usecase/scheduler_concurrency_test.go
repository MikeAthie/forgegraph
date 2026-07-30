package usecase

import (
	"context"
	"errors"
	"strings"
	"sync/atomic"
	"testing"
	"time"

	"github.com/forgegraph/engine/application/port"
	"github.com/forgegraph/engine/domain"
	"github.com/forgegraph/engine/domain/entity"
	"github.com/forgegraph/engine/domain/service"
	"github.com/forgegraph/engine/domain/value"
)

func TestSchedulerRejectsDuplicateActiveRun(t *testing.T) {
	engine := NewTestEngine(t, 2)
	engine.Scheduler.hooks = schedulerHooks{}
	started := make(chan struct{})
	release := make(chan struct{})
	exec := engine.RegisterExecutor(string(value.NodeTypeOutput), func(ctx context.Context, _ *entity.Node, _ *entity.State) (*port.NodeExecutionResult, error) {
		select {
		case <-started:
		default:
			close(started)
		}
		select {
		case <-release:
			return port.NewSuccessResult(map[string]any{"ok": true}), nil
		case <-ctx.Done():
			return nil, ctx.Err()
		}
	})

	const runID = "duplicate-active-run"
	graphJSON := makeGraphJSONWithMetadata(
		[]entity.Node{{ID: "output", Type: string(value.NodeTypeOutput), Name: "Output", Config: map[string]any{}}},
		nil,
		map[string]any{"backend_attempt_id": "attempt-1"},
	)
	if err := engine.Scheduler.StartRun(context.Background(), runID, graphJSON, "{}", "", "", "", ""); err != nil {
		t.Fatalf("first StartRun() error = %v", err)
	}
	select {
	case <-started:
	case <-time.After(2 * time.Second):
		t.Fatal("first run did not start")
	}

	err := engine.Scheduler.StartRun(context.Background(), runID, graphJSON, "{}", "", "", "", "")
	if !errors.Is(err, domain.ErrRunAlreadyActive) {
		t.Fatalf("duplicate StartRun() error = %v, want %v", err, domain.ErrRunAlreadyActive)
	}

	close(release)
	waitForSchedulerInactive(t, engine.Scheduler, runID)
	if got := exec.getExecuteCount(); got != 1 {
		t.Fatalf("executor calls = %d, want 1", got)
	}
}

func TestSchedulerShutdownCancelsRunsAndRejectsNewWork(t *testing.T) {
	engine := NewTestEngine(t, 1)
	engine.Scheduler.hooks = schedulerHooks{}
	started := make(chan struct{})
	engine.RegisterExecutor(string(value.NodeTypeOutput), func(ctx context.Context, _ *entity.Node, _ *entity.State) (*port.NodeExecutionResult, error) {
		select {
		case <-started:
		default:
			close(started)
		}
		<-ctx.Done()
		return nil, ctx.Err()
	})

	const runID = "shutdown-active-run"
	graphJSON := makeGraphJSONWithMetadata(
		[]entity.Node{{ID: "output", Type: string(value.NodeTypeOutput), Name: "Output", Config: map[string]any{}}},
		nil,
		map[string]any{"backend_attempt_id": "attempt-shutdown"},
	)
	if err := engine.Scheduler.StartRun(context.Background(), runID, graphJSON, "{}", "", "", "", ""); err != nil {
		t.Fatalf("StartRun() error = %v", err)
	}
	select {
	case <-started:
	case <-time.After(2 * time.Second):
		t.Fatal("run did not start")
	}

	shutdownCtx, cancel := context.WithTimeout(context.Background(), 2*time.Second)
	defer cancel()
	if err := engine.Scheduler.Shutdown(shutdownCtx); err != nil {
		t.Fatalf("Shutdown() error = %v", err)
	}
	if engine.Scheduler.IsRunActive(runID) {
		t.Fatal("run remained active after shutdown")
	}

	err := engine.Scheduler.StartRun(context.Background(), "after-shutdown", graphJSON, "{}", "", "", "", "")
	if !errors.Is(err, domain.ErrSchedulerStopping) {
		t.Fatalf("StartRun() after shutdown error = %v, want %v", err, domain.ErrSchedulerStopping)
	}
}

func TestSchedulerFailsRunWhenExecutorReturnsNilResult(t *testing.T) {
	engine := NewTestEngine(t, 1)
	engine.Scheduler.hooks = schedulerHooks{}
	engine.RegisterExecutor(string(value.NodeTypeOutput), func(context.Context, *entity.Node, *entity.State) (*port.NodeExecutionResult, error) {
		return nil, nil
	})

	const runID = "nil-executor-result"
	graphJSON := makeGraphJSONWithMetadata(
		[]entity.Node{{ID: "output", Type: string(value.NodeTypeOutput), Name: "Output", Config: map[string]any{}}},
		nil,
		map[string]any{"backend_attempt_id": "attempt-nil-result"},
	)
	engine.StartRun(runID, graphJSON, "{}")
	snapshot := engine.AwaitRunStatus(runID, string(value.RunStatusFailed))
	if !strings.Contains(snapshot.Error, "returned a nil result") {
		t.Fatalf("run error = %q, want nil-result contract failure", snapshot.Error)
	}
}

func TestSchedulerClearsRunningNodeOnPreExecutionFailure(t *testing.T) {
	engine := NewTestEngine(t, 1)
	engine.Scheduler.hooks = schedulerHooks{}
	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()

	graph := &entity.Graph{
		Nodes: []entity.Node{{ID: "missing", Type: "not-registered", Name: "Missing", Config: map[string]any{}}},
	}
	rc := &runContext{
		runID:       "pre-execution-failure",
		ctx:         ctx,
		cancel:      cancel,
		clock:       engine.Clock,
		plan:        service.NewExecutionPlanner().Plan(graph),
		state:       entity.NewState(),
		pending:     map[string]int{"missing": 0},
		completed:   make(map[string]bool),
		skipped:     make(map[string]bool),
		running:     make(map[string]bool),
		visitCounts: make(map[string]int),
	}
	rc.wg.Add(1)

	engine.Scheduler.executeNode(rc, "missing")

	rc.pendingMu.Lock()
	_, stillRunning := rc.running["missing"]
	rc.pendingMu.Unlock()
	if stillRunning {
		t.Fatal("node remained marked running after executor resolution failed")
	}
}

func TestSchedulerLoadsSessionMemoryOnlyBeforeExecution(t *testing.T) {
	engine := NewTestEngine(t, 1)
	engine.Scheduler.hooks = schedulerHooks{}
	store := &countingMemoryStore{
		value: []entity.Message{{Role: "user", Content: "persisted"}},
	}
	engine.Scheduler.memoryStore = store
	engine.RegisterExecutor(string(value.NodeTypeOutput), func(_ context.Context, _ *entity.Node, _ *entity.State) (*port.NodeExecutionResult, error) {
		return port.NewSuccessResult(map[string]any{"ok": true}), nil
	})

	const runID = "single-session-restore"
	graphJSON := makeGraphJSONWithMetadata(
		[]entity.Node{{ID: "output", Type: string(value.NodeTypeOutput), Name: "Output", Config: map[string]any{}}},
		nil,
		map[string]any{"backend_attempt_id": "attempt-session"},
	)
	memoryConfig := `{"tier1":{"enabled":true},"cross_session":{"enabled":true}}`
	if err := engine.Scheduler.StartRun(context.Background(), runID, graphJSON, "{}", "", memoryConfig, "tenant", "session"); err != nil {
		t.Fatalf("StartRun() error = %v", err)
	}
	engine.AwaitRunStatus(runID, string(value.RunStatusSucceeded))
	if got := store.getCalls.Load(); got != 1 {
		t.Fatalf("session memory Get() calls = %d, want 1", got)
	}
}

type countingMemoryStore struct {
	getCalls atomic.Int32
	value    any
}

func (s *countingMemoryStore) Get(context.Context, string, string) (any, bool, error) {
	s.getCalls.Add(1)
	return s.value, true, nil
}

func (s *countingMemoryStore) Set(context.Context, string, string, any, int) error {
	return nil
}

func (s *countingMemoryStore) Delete(context.Context, string, string) (bool, error) {
	return false, nil
}
