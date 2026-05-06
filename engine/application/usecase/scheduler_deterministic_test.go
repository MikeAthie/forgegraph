package usecase

import (
	"context"
	"fmt"
	"slices"
	"sync"
	"testing"
	"time"

	"github.com/forgegraph/engine/application/port"
	"github.com/forgegraph/engine/domain"
	"github.com/forgegraph/engine/domain/entity"
	"github.com/forgegraph/engine/domain/value"
)

// Description: Linear dependency chain with explicit state propagation.
// Invariants: downstream nodes do not start before prerequisites complete; node outputs propagate through state; final output is correct.
// Edge cases: snapshot inspection happens between steps while the run is still active.
func TestSchedulerDeterministicExecutionCorrectness(t *testing.T) {
	engine := NewTestEngine(t, 4)

	engine.RegisterExecutor(string(value.NodeTypeTransform), func(ctx context.Context, node *entity.Node, state *entity.State) (*port.NodeExecutionResult, error) {
		switch node.ID {
		case "seed":
			return port.NewSuccessResult(map[string]any{"value": "alpha"}), nil
		case "compose":
			seedOutput, ok := state.GetNodeOutput("seed")
			if !ok {
				return nil, fmt.Errorf("seed output missing")
			}
			value := seedOutput.(map[string]any)["value"].(string)
			return port.NewSuccessResult(map[string]any{"value": value + "-beta"}), nil
		default:
			return nil, fmt.Errorf("unexpected transform node %s", node.ID)
		}
	})
	engine.RegisterExecutor(string(value.NodeTypeOutput), func(ctx context.Context, node *entity.Node, state *entity.State) (*port.NodeExecutionResult, error) {
		composed, ok := state.GetNodeOutput("compose")
		if !ok {
			return nil, fmt.Errorf("compose output missing")
		}
		return port.NewSuccessResult(map[string]any{"final": composed.(map[string]any)["value"]}), nil
	})

	runID := "run-deterministic-execution"
	graphJSON := makeGraphJSON(
		[]entity.Node{
			{ID: "seed", Type: string(value.NodeTypeTransform), Name: "Seed", Config: map[string]any{}},
			{ID: "compose", Type: string(value.NodeTypeTransform), Name: "Compose", Config: map[string]any{}},
			{ID: "output", Type: string(value.NodeTypeOutput), Name: "Output", Config: map[string]any{}},
		},
		[]entity.Edge{
			{From: "seed", To: "compose"},
			{From: "compose", To: "output"},
		},
	)

	engine.StartRun(runID, graphJSON, "{}")

	engine.AwaitBlockedAttempt(runID, "seed", 1)
	snapshot := engine.Snapshot(runID)
	if !slices.Equal(snapshot.Running, []string{"seed"}) {
		t.Fatalf("expected only seed to be running, got %v", snapshot.Running)
	}
	if engine.Stepper.AttemptCount(runID, "compose") != 0 {
		t.Fatalf("compose should not start before seed completes")
	}

	engine.Release(runID, "seed")
	engine.AwaitBlockedAttempt(runID, "compose", 1)

	snapshot = engine.Snapshot(runID)
	seedOutput := snapshot.State["node.seed.output"].(map[string]any)
	if seedOutput["value"] != "alpha" {
		t.Fatalf("expected propagated seed output, got %#v", seedOutput)
	}

	engine.Release(runID, "compose")
	engine.AwaitBlockedAttempt(runID, "output", 1)

	snapshot = engine.Snapshot(runID)
	composedOutput := snapshot.State["node.compose.output"].(map[string]any)
	if composedOutput["value"] != "alpha-beta" {
		t.Fatalf("expected composed output, got %#v", composedOutput)
	}

	engine.Release(runID, "output")
	snapshot = engine.AwaitRunStatus(runID, string(value.RunStatusSucceeded))
	if snapshot.Output["final"] != "alpha-beta" {
		t.Fatalf("expected final output alpha-beta, got %#v", snapshot.Output)
	}
}

// Description: Two sibling tasks are allowed to run at the same time after their shared dependency completes.
// Invariants: multiple nodes can be concurrently running; downstream fan-in does not start early; run reaches terminal success without deadlock.
// Edge cases: both sibling nodes are blocked before either is released.
func TestSchedulerDeterministicConcurrency(t *testing.T) {
	engine := NewTestEngine(t, 8)

	engine.RegisterExecutor(string(value.NodeTypeTransform), func(ctx context.Context, node *entity.Node, state *entity.State) (*port.NodeExecutionResult, error) {
		return port.NewSuccessResult(map[string]any{"node": node.ID}), nil
	})
	agentExec := engine.RegisterExecutor(string(value.NodeTypeAgent), func(ctx context.Context, node *entity.Node, state *entity.State) (*port.NodeExecutionResult, error) {
		return port.NewSuccessResult(map[string]any{"agent": node.ID}), nil
	})
	engine.RegisterExecutor(string(value.NodeTypeOutput), func(ctx context.Context, node *entity.Node, state *entity.State) (*port.NodeExecutionResult, error) {
		return port.NewSuccessResult(map[string]any{"done": true}), nil
	})

	runID := "run-deterministic-concurrency"
	graphJSON := makeGraphJSON(
		[]entity.Node{
			{ID: "root", Type: string(value.NodeTypeTransform), Name: "Root", Config: map[string]any{}},
			{ID: "agent_a", Type: string(value.NodeTypeAgent), Name: "Agent A", Config: map[string]any{}},
			{ID: "agent_b", Type: string(value.NodeTypeAgent), Name: "Agent B", Config: map[string]any{}},
			{ID: "output", Type: string(value.NodeTypeOutput), Name: "Output", Config: map[string]any{}},
		},
		[]entity.Edge{
			{From: "root", To: "agent_a"},
			{From: "root", To: "agent_b"},
			{From: "agent_a", To: "output"},
			{From: "agent_b", To: "output"},
		},
	)

	engine.StartRun(runID, graphJSON, "{}")
	engine.AwaitBlockedAttempt(runID, "root", 1)
	engine.Release(runID, "root")

	blocked := engine.AwaitBlockedCount(runID, 2)
	if !slices.Equal(blocked, []string{"agent_a", "agent_b"}) {
		t.Fatalf("expected sibling agents to block together, got %v", blocked)
	}
	if agentExec.getExecuteCount() != 0 {
		t.Fatalf("agents should still be blocked before release")
	}

	snapshot := engine.Snapshot(runID)
	if !slices.Equal(snapshot.Running, []string{"agent_a", "agent_b"}) {
		t.Fatalf("expected concurrent running agents, got %v", snapshot.Running)
	}
	if engine.Stepper.AttemptCount(runID, "output") != 0 {
		t.Fatalf("output should not start before both agents complete")
	}

	engine.Release(runID, "agent_a")
	engine.Release(runID, "agent_b")
	engine.AwaitBlockedAttempt(runID, "output", 1)
	engine.Release(runID, "output")

	engine.AwaitRunStatus(runID, string(value.RunStatusSucceeded))
	if agentExec.getExecuteCount() != 2 {
		t.Fatalf("expected both agents to execute once, got %d", agentExec.getExecuteCount())
	}
}

// Description: Human-gate pause persists snapshot state and resume continues from the backend-provided decision.
// Invariants: pause emits a durable snapshot; the paused node is recorded; resume continues downstream without re-running the gate.
// Edge cases: snapshot is inspected after the run leaves the active set.
func TestSchedulerDeterministicPauseResumeSnapshot(t *testing.T) {
	engine := NewTestEngine(t, 4)

	engine.RegisterExecutor(string(value.NodeTypeTransform), func(ctx context.Context, node *entity.Node, state *entity.State) (*port.NodeExecutionResult, error) {
		switch node.ID {
		case "start":
			return port.NewSuccessResult(map[string]any{"prepared": "ready"}), nil
		case "after":
			decision, ok := state.GetNodeOutput("gate")
			if !ok {
				return nil, fmt.Errorf("gate decision missing")
			}
			return port.NewSuccessResult(map[string]any{"decision": decision}), nil
		default:
			return nil, fmt.Errorf("unexpected transform node %s", node.ID)
		}
	})
	engine.RegisterExecutor(string(value.NodeTypeHumanGate), func(ctx context.Context, node *entity.Node, state *entity.State) (*port.NodeExecutionResult, error) {
		return port.NewPauseResult(map[string]any{"prompt": "approve deployment"}), nil
	})
	engine.RegisterExecutor(string(value.NodeTypeOutput), func(ctx context.Context, node *entity.Node, state *entity.State) (*port.NodeExecutionResult, error) {
		after, ok := state.GetNodeOutput("after")
		if !ok {
			return nil, fmt.Errorf("after output missing")
		}
		return port.NewSuccessResult(map[string]any{"result": after}), nil
	})

	runID := "run-deterministic-pause"
	graphJSON := makeGraphJSON(
		[]entity.Node{
			{ID: "start", Type: string(value.NodeTypeTransform), Name: "Start", Config: map[string]any{}},
			{ID: "gate", Type: string(value.NodeTypeHumanGate), Name: "Gate", Config: map[string]any{}},
			{ID: "after", Type: string(value.NodeTypeTransform), Name: "After", Config: map[string]any{}},
			{ID: "output", Type: string(value.NodeTypeOutput), Name: "Output", Config: map[string]any{}},
		},
		[]entity.Edge{
			{From: "start", To: "gate"},
			{From: "gate", To: "after"},
			{From: "after", To: "output"},
		},
	)

	engine.StartRun(runID, graphJSON, "{}")
	engine.AwaitBlockedAttempt(runID, "start", 1)
	engine.Release(runID, "start")
	engine.AwaitBlockedAttempt(runID, "gate", 1)
	engine.Release(runID, "gate")

	snapshot := engine.AwaitRunStatus(runID, string(value.RunStatusPaused))
	if snapshot.PausedNodeID != "gate" {
		t.Fatalf("expected paused node gate, got %q", snapshot.PausedNodeID)
	}
	if snapshot.State["node.start.output"].(map[string]any)["prepared"] != "ready" {
		t.Fatalf("expected start output in pause snapshot, got %#v", snapshot.State["node.start.output"])
	}
	if !slices.Contains(snapshot.Completed, "start") {
		t.Fatalf("expected completed nodes to contain start, got %v", snapshot.Completed)
	}

	engine.ResumeRun(runID, "gate", `{"approved":true,"feedback":"ship it","fields":{"ticket":"A-1"}}`)
	engine.AwaitBlockedAttempt(runID, "after", 1)
	engine.Release(runID, "after")
	engine.AwaitBlockedAttempt(runID, "output", 1)
	engine.Release(runID, "output")

	snapshot = engine.AwaitRunStatus(runID, string(value.RunStatusSucceeded))
	if snapshot.Output["result"] == nil {
		t.Fatalf("expected resumed run to produce output, got %#v", snapshot.Output)
	}

	events := engine.AwaitEvents("run_resumed event", func(events []ObservedEvent) bool {
		return countEvents(events, port.EventTypeRunResumed) >= 1
	})
	if countEvents(events, port.EventTypeRunResumed) < 1 {
		t.Fatalf("expected run_resumed event")
	}
}

// Description: A fresh scheduler start resumes from the backend-owned snapshot instead of re-running completed work.
// Invariants: snapshot state is loaded before execution begins; completed nodes from durable node runs are skipped; resume emits a resumed lifecycle event.
// Edge cases: the engine starts with no active in-memory run context and reconstructs progress from snapshot + durable node runs alone.
func TestSchedulerDeterministicStartRunResumesFromRepositorySnapshot(t *testing.T) {
	engine := NewTestEngine(t, 4)

	startExec := engine.RegisterExecutor(string(value.NodeTypeTransform), func(ctx context.Context, node *entity.Node, state *entity.State) (*port.NodeExecutionResult, error) {
		return port.NewSuccessResult(map[string]any{"unexpected": true}), nil
	})
	engine.RegisterExecutor(string(value.NodeTypeOutput), func(ctx context.Context, node *entity.Node, state *entity.State) (*port.NodeExecutionResult, error) {
		startOutput, ok := state.GetNodeOutput("start")
		if !ok {
			return nil, fmt.Errorf("missing checkpointed start output")
		}
		prepared, _ := startOutput.(map[string]any)["prepared"].(string)
		return port.NewSuccessResult(map[string]any{"result": prepared + "-resumed"}), nil
	})

	runID := "run-deterministic-snapshot-resume"
	graphJSON := makeGraphJSON(
		[]entity.Node{
			{ID: "start", Type: string(value.NodeTypeTransform), Name: "Start", Config: map[string]any{}},
			{ID: "finish", Type: string(value.NodeTypeOutput), Name: "Finish", Config: map[string]any{}},
		},
		[]entity.Edge{
			{From: "start", To: "finish"},
		},
	)

	engine.Repo.runs[runID] = &entity.Run{
		ID:        runID,
		Status:    "pending",
		InputJSON: map[string]any{"query": "authoritative"},
	}
	now := time.Date(2026, time.January, 1, 0, 0, 1, 0, time.UTC)
	engine.Repo.nodeRuns["run-deterministic-snapshot-resume-start"] = &entity.NodeRun{
		ID:        "run-deterministic-snapshot-resume-start",
		RunID:     runID,
		NodeID:    "start",
		NodeType:  string(value.NodeTypeTransform),
		Status:    string(value.NodeRunStatusSucceeded),
		Attempt:   1,
		StartedAt: now,
		EndedAt:   func() *time.Time { ended := now.Add(10 * time.Millisecond); return &ended }(),
		InputJSON: map[string]any{"input.query": "authoritative"},
		OutputJSON: map[string]any{
			"output": map[string]any{"prepared": "ready"},
			"state_delta": map[string]any{
				"node.start.output": map[string]any{"prepared": "ready"},
			},
		},
	}
	engine.Repo.snapshots[runID] = &port.RunResumeSnapshot{
		RunID:             runID,
		LastCompletedNode: "start",
		NextNode:          "finish",
		AttemptID:         "attempt-1",
		UpdatedAt:         now.Add(10 * time.Millisecond),
	}

	engine.StartRun(runID, graphJSON, `{"query":"ignored because checkpoint is authoritative"}`)
	engine.AwaitBlockedAttempt(runID, "finish", 1)

	if startExec.getExecuteCount() != 0 {
		t.Fatalf("expected completed checkpointed node to be skipped, got %d executions", startExec.getExecuteCount())
	}
	if engine.Stepper.AttemptCount(runID, "start") != 0 {
		t.Fatalf("expected no attempt for checkpointed node, got %d", engine.Stepper.AttemptCount(runID, "start"))
	}

	snapshot := engine.Snapshot(runID)
	if snapshot.State["node.start.output"].(map[string]any)["prepared"] != "ready" {
		t.Fatalf("expected checkpoint state to seed resumed run, got %#v", snapshot.State["node.start.output"])
	}

	engine.Release(runID, "finish")
	snapshot = engine.AwaitRunStatus(runID, string(value.RunStatusSucceeded))
	if snapshot.Output["result"] != "ready-resumed" {
		t.Fatalf("expected resumed snapshot output, got %#v", snapshot.Output)
	}

	events := engine.AwaitEvents("run_resumed event from snapshot start", func(events []ObservedEvent) bool {
		return countEvents(events, port.EventTypeRunResumed) >= 1
	})
	if countEvents(events, port.EventTypeRunResumed) < 1 {
		t.Fatalf("expected run_resumed event for snapshot-based start")
	}
}

// Description: Snapshot resume restarts from the last successful boundary and re-executes the failed node.
// Invariants: completed nodes before the snapshot are skipped; failed nodes are not treated as completed; resume continues from snapshot.NextNode.
// Edge cases: a prior failed attempt exists durably, but the snapshot still points at the previous successful node.
func TestSchedulerDeterministicStartRunReexecutesFailedNodeAfterSnapshotBoundary(t *testing.T) {
	engine := NewTestEngine(t, 4)

	transformExec := engine.RegisterExecutor(string(value.NodeTypeTransform), func(ctx context.Context, node *entity.Node, state *entity.State) (*port.NodeExecutionResult, error) {
		switch node.ID {
		case "start":
			return port.NewSuccessResult(map[string]any{"unexpected": true}), nil
		case "process":
			startOutput, ok := state.GetNodeOutput("start")
			if !ok {
				return nil, fmt.Errorf("missing resumed start output")
			}
			prepared, _ := startOutput.(map[string]any)["prepared"].(string)
			return port.NewSuccessResult(map[string]any{"processed": prepared + "-again"}), nil
		default:
			return nil, fmt.Errorf("unexpected transform node %s", node.ID)
		}
	})
	engine.RegisterExecutor(string(value.NodeTypeOutput), func(ctx context.Context, node *entity.Node, state *entity.State) (*port.NodeExecutionResult, error) {
		processOutput, ok := state.GetNodeOutput("process")
		if !ok {
			return nil, fmt.Errorf("missing process output")
		}
		return port.NewSuccessResult(map[string]any{"result": processOutput.(map[string]any)["processed"]}), nil
	})

	runID := "run-deterministic-resume-reexecutes-failed-node"
	graphJSON := makeGraphJSON(
		[]entity.Node{
			{ID: "start", Type: string(value.NodeTypeTransform), Name: "Start", Config: map[string]any{}},
			{ID: "process", Type: string(value.NodeTypeTransform), Name: "Process", Config: map[string]any{}},
			{ID: "finish", Type: string(value.NodeTypeOutput), Name: "Finish", Config: map[string]any{}},
		},
		[]entity.Edge{
			{From: "start", To: "process"},
			{From: "process", To: "finish"},
		},
	)

	engine.Repo.runs[runID] = &entity.Run{
		ID:        runID,
		Status:    "pending",
		InputJSON: map[string]any{"query": "resume"},
	}
	now := time.Date(2026, time.January, 1, 0, 0, 2, 0, time.UTC)
	engine.Repo.nodeRuns["run-deterministic-resume-reexecutes-failed-node-start"] = &entity.NodeRun{
		ID:        "run-deterministic-resume-reexecutes-failed-node-start",
		RunID:     runID,
		NodeID:    "start",
		NodeType:  string(value.NodeTypeTransform),
		Status:    string(value.NodeRunStatusSucceeded),
		Attempt:   1,
		StartedAt: now,
		EndedAt:   func() *time.Time { ended := now.Add(10 * time.Millisecond); return &ended }(),
		InputJSON: map[string]any{"input.query": "resume"},
		OutputJSON: map[string]any{
			"output": map[string]any{"prepared": "ready"},
			"state_delta": map[string]any{
				"node.start.output": map[string]any{"prepared": "ready"},
			},
		},
	}
	engine.Repo.nodeRuns["run-deterministic-resume-reexecutes-failed-node-process-attempt-1"] = &entity.NodeRun{
		ID:        "run-deterministic-resume-reexecutes-failed-node-process-attempt-1",
		RunID:     runID,
		NodeID:    "process",
		NodeType:  string(value.NodeTypeTransform),
		Status:    string(value.NodeRunStatusFailed),
		Attempt:   1,
		StartedAt: now.Add(20 * time.Millisecond),
		EndedAt:   func() *time.Time { ended := now.Add(30 * time.Millisecond); return &ended }(),
		InputJSON: map[string]any{"input.query": "resume"},
		ErrorJSON: map[string]any{"error": "boom"},
	}
	engine.Repo.snapshots[runID] = &port.RunResumeSnapshot{
		RunID:             runID,
		LastCompletedNode: "start",
		NextNode:          "process",
		AttemptID:         "attempt-1",
		UpdatedAt:         now.Add(10 * time.Millisecond),
	}

	engine.StartRun(runID, graphJSON, `{"query":"ignored because checkpoint is authoritative"}`)
	engine.AwaitBlockedAttempt(runID, "process", 1)

	if transformExec.getNodeExecuteCount("start") != 0 {
		t.Fatalf("expected completed node before snapshot to be skipped, got %d executions", transformExec.getNodeExecuteCount("start"))
	}

	engine.Release(runID, "process")
	engine.AwaitBlockedAttempt(runID, "finish", 1)

	if transformExec.getNodeExecuteCount("process") != 1 {
		t.Fatalf("expected failed node to be re-executed exactly once, got %d", transformExec.getNodeExecuteCount("process"))
	}

	engine.Release(runID, "finish")
	snapshot := engine.AwaitRunStatus(runID, string(value.RunStatusSucceeded))
	if snapshot.Output["result"] != "ready-again" {
		t.Fatalf("expected resumed output from re-executed failed node, got %#v", snapshot.Output)
	}

	nodeRuns, err := engine.Repo.GetNodeRunsByRunID(context.Background(), runID)
	if err != nil {
		t.Fatalf("GetNodeRunsByRunID failed: %v", err)
	}
	processRuns := 0
	foundSucceededProcess := false
	for _, nodeRun := range nodeRuns {
		if nodeRun.NodeID != "process" {
			continue
		}
		processRuns++
		if nodeRun.Status == string(value.NodeRunStatusSucceeded) {
			foundSucceededProcess = true
		}
	}
	if processRuns < 2 || !foundSucceededProcess {
		t.Fatalf("expected failed node history plus a succeeded resumed execution, got %d process node runs", processRuns)
	}
}

// Description: Retry-safe side effects remain correct when a failed node is re-executed from the last successful snapshot.
// Invariants: the failed node runs again; the external side effect stays single-apply when guarded by a stable side_effect_id.
// Edge cases: the first attempt already applied the side effect before failing and leaving the snapshot unchanged.
func TestSchedulerDeterministicResumeKeepsSideEffectIdempotentOnFailedNodeRetry(t *testing.T) {
	engine := NewTestEngine(t, 4)

	var mu sync.Mutex
	appliedSideEffects := map[string]int{"email-42": 1}
	dedupeHits := 0

	transformExec := engine.RegisterExecutor(string(value.NodeTypeTransform), func(ctx context.Context, node *entity.Node, state *entity.State) (*port.NodeExecutionResult, error) {
		if node.ID == "start" {
			return port.NewSuccessResult(map[string]any{"unexpected": true}), nil
		}
		if node.ID != "side_effect" {
			return nil, fmt.Errorf("unexpected transform node %s", node.ID)
		}
		sideEffectID := state.GetString("input.side_effect_id")
		if sideEffectID == "" {
			return nil, fmt.Errorf("missing side_effect_id")
		}

		mu.Lock()
		if appliedSideEffects[sideEffectID] > 0 {
			dedupeHits++
			mu.Unlock()
			return port.NewSuccessResult(map[string]any{"side_effect_id": sideEffectID, "applied": false}), nil
		}
		appliedSideEffects[sideEffectID]++
		mu.Unlock()
		return port.NewSuccessResult(map[string]any{"side_effect_id": sideEffectID, "applied": true}), nil
	})
	engine.RegisterExecutor(string(value.NodeTypeOutput), func(ctx context.Context, node *entity.Node, state *entity.State) (*port.NodeExecutionResult, error) {
		sideEffectOutput, ok := state.GetNodeOutput("side_effect")
		if !ok {
			return nil, fmt.Errorf("missing side effect output")
		}
		return port.NewSuccessResult(map[string]any{"result": sideEffectOutput}), nil
	})

	runID := "run-deterministic-resume-side-effect-idempotent"
	graphJSON := makeGraphJSON(
		[]entity.Node{
			{ID: "start", Type: string(value.NodeTypeTransform), Name: "Start", Config: map[string]any{}},
			{ID: "side_effect", Type: string(value.NodeTypeTransform), Name: "Side Effect", Config: map[string]any{}},
			{ID: "finish", Type: string(value.NodeTypeOutput), Name: "Finish", Config: map[string]any{}},
		},
		[]entity.Edge{
			{From: "start", To: "side_effect"},
			{From: "side_effect", To: "finish"},
		},
	)

	engine.Repo.runs[runID] = &entity.Run{
		ID:        runID,
		Status:    "pending",
		InputJSON: map[string]any{"side_effect_id": "email-42"},
	}
	now := time.Date(2026, time.January, 1, 0, 0, 3, 0, time.UTC)
	engine.Repo.nodeRuns["run-deterministic-resume-side-effect-idempotent-start"] = &entity.NodeRun{
		ID:        "run-deterministic-resume-side-effect-idempotent-start",
		RunID:     runID,
		NodeID:    "start",
		NodeType:  string(value.NodeTypeTransform),
		Status:    string(value.NodeRunStatusSucceeded),
		Attempt:   1,
		StartedAt: now,
		EndedAt:   func() *time.Time { ended := now.Add(10 * time.Millisecond); return &ended }(),
		InputJSON: map[string]any{"input.side_effect_id": "email-42"},
		OutputJSON: map[string]any{
			"output": map[string]any{"prepared": true},
			"state_delta": map[string]any{
				"node.start.output": map[string]any{"prepared": true},
			},
		},
	}
	engine.Repo.nodeRuns["run-deterministic-resume-side-effect-idempotent-side-effect-attempt-1"] = &entity.NodeRun{
		ID:        "run-deterministic-resume-side-effect-idempotent-side-effect-attempt-1",
		RunID:     runID,
		NodeID:    "side_effect",
		NodeType:  string(value.NodeTypeTransform),
		Status:    string(value.NodeRunStatusFailed),
		Attempt:   1,
		StartedAt: now.Add(20 * time.Millisecond),
		EndedAt:   func() *time.Time { ended := now.Add(30 * time.Millisecond); return &ended }(),
		InputJSON: map[string]any{"input.side_effect_id": "email-42"},
		ErrorJSON: map[string]any{"error": "post-side-effect failure"},
	}
	engine.Repo.snapshots[runID] = &port.RunResumeSnapshot{
		RunID:             runID,
		LastCompletedNode: "start",
		NextNode:          "side_effect",
		AttemptID:         "attempt-1",
		UpdatedAt:         now.Add(10 * time.Millisecond),
	}

	engine.StartRun(runID, graphJSON, `{"side_effect_id":"ignored because checkpoint is authoritative"}`)
	engine.AwaitBlockedAttempt(runID, "side_effect", 1)

	if transformExec.getNodeExecuteCount("start") != 0 {
		t.Fatalf("expected completed node before snapshot to be skipped, got %d executions", transformExec.getNodeExecuteCount("start"))
	}

	engine.Release(runID, "side_effect")
	engine.AwaitBlockedAttempt(runID, "finish", 1)
	engine.Release(runID, "finish")
	engine.AwaitRunStatus(runID, string(value.RunStatusSucceeded))

	if transformExec.getNodeExecuteCount("side_effect") != 1 {
		t.Fatalf("expected failed side-effect node to be re-executed once, got %d", transformExec.getNodeExecuteCount("side_effect"))
	}

	mu.Lock()
	defer mu.Unlock()
	if appliedSideEffects["email-42"] != 1 {
		t.Fatalf("expected side effect to remain single-apply, got %d applications", appliedSideEffects["email-42"])
	}
	if dedupeHits != 1 {
		t.Fatalf("expected resumed execution to observe one idempotent dedupe hit, got %d", dedupeHits)
	}
}

// Description: Retryable failures are retried only when the manual clock advances; final failure occurs after the configured max attempts.
// Invariants: retries do not happen early; retry count is capped at three; terminal failure is emitted with the final attempt number.
// Edge cases: downstream nodes never start when the retried node exhausts its policy.
func TestSchedulerDeterministicRetryFailure(t *testing.T) {
	engine := NewTestEngine(t, 2)

	retryExec := engine.RegisterExecutor(string(value.NodeTypeTransform), func(ctx context.Context, node *entity.Node, state *entity.State) (*port.NodeExecutionResult, error) {
		return nil, domain.NewRetryableErrorWithDetails(
			fmt.Errorf("temporary failure"),
			"temporary failure",
			"rate_limited",
			10,
			map[string]any{"retry_after_ms": 10},
		)
	})
	engine.RegisterExecutor(string(value.NodeTypeOutput), func(ctx context.Context, node *entity.Node, state *entity.State) (*port.NodeExecutionResult, error) {
		return port.NewSuccessResult(map[string]any{"unexpected": true}), nil
	})

	runID := "run-deterministic-retry-failure"
	graphJSON := makeGraphJSON(
		[]entity.Node{
			{
				ID:     "retry",
				Type:   string(value.NodeTypeTransform),
				Name:   "Retry",
				Config: map[string]any{},
				RetryPolicy: &entity.RetryPolicy{
					MaxAttempts:     3,
					BackoffMs:       10,
					BackoffStrategy: "fixed",
				},
			},
			{ID: "output", Type: string(value.NodeTypeOutput), Name: "Output", Config: map[string]any{}},
		},
		[]entity.Edge{{From: "retry", To: "output"}},
	)

	engine.StartRun(runID, graphJSON, "{}")

	engine.AwaitBlockedAttempt(runID, "retry", 1)
	engine.Release(runID, "retry")
	engine.AwaitEvents("first retry event", func(events []ObservedEvent) bool {
		return countEvents(events, port.EventTypeNodeRetrying) == 1
	})
	if retryExec.getExecuteCount() != 1 {
		t.Fatalf("expected one executed attempt after first release, got %d", retryExec.getExecuteCount())
	}

	engine.AwaitClockWaiters(1)
	engine.Advance(9 * time.Millisecond)
	if engine.Stepper.AttemptCount(runID, "retry") != 1 {
		t.Fatalf("retry attempt advanced before backoff elapsed")
	}

	engine.Advance(1 * time.Millisecond)
	engine.AwaitBlockedAttempt(runID, "retry", 2)
	engine.Release(runID, "retry")
	engine.AwaitEvents("second retry event", func(events []ObservedEvent) bool {
		return countEvents(events, port.EventTypeNodeRetrying) == 2
	})

	engine.AwaitClockWaiters(1)
	engine.Advance(10 * time.Millisecond)
	engine.AwaitBlockedAttempt(runID, "retry", 3)
	engine.Release(runID, "retry")

	snapshot := engine.AwaitRunStatus(runID, string(value.RunStatusFailed))
	if snapshot.Error == "" {
		t.Fatalf("expected terminal failure error")
	}
	if engine.Stepper.AttemptCount(runID, "output") != 0 {
		t.Fatalf("output should never start when retries are exhausted")
	}

	events := engine.Bus.All()
	if retryExec.getExecuteCount() != 3 {
		t.Fatalf("expected exactly three attempts, got %d", retryExec.getExecuteCount())
	}
	if finalAttempt := finalAttemptFor(events, port.EventTypeNodeFailed, "retry"); finalAttempt != 3 {
		t.Fatalf("expected node_failed attempt=3, got %d", finalAttempt)
	}
}

// Description: Merge fan-in observes valid happens-before relationships rather than brittle total ordering.
// Invariants: merge cannot start before both parents complete; event sequences preserve dependency causality.
// Edge cases: one branch completes while the other remains blocked.
func TestSchedulerDeterministicCausality(t *testing.T) {
	engine := NewTestEngine(t, 8)

	engine.RegisterExecutor(string(value.NodeTypeTransform), func(ctx context.Context, node *entity.Node, state *entity.State) (*port.NodeExecutionResult, error) {
		return port.NewSuccessResult(map[string]any{"node": node.ID}), nil
	})
	engine.RegisterExecutor(string(value.NodeTypeMerge), func(ctx context.Context, node *entity.Node, state *entity.State) (*port.NodeExecutionResult, error) {
		return port.NewSuccessResult(map[string]any{"merged": true}), nil
	})
	engine.RegisterExecutor(string(value.NodeTypeOutput), func(ctx context.Context, node *entity.Node, state *entity.State) (*port.NodeExecutionResult, error) {
		return port.NewSuccessResult(map[string]any{"done": true}), nil
	})

	runID := "run-deterministic-causality"
	graphJSON := makeGraphJSON(
		[]entity.Node{
			{ID: "start", Type: string(value.NodeTypeTransform), Name: "Start", Config: map[string]any{}},
			{ID: "left", Type: string(value.NodeTypeTransform), Name: "Left", Config: map[string]any{}},
			{ID: "right", Type: string(value.NodeTypeTransform), Name: "Right", Config: map[string]any{}},
			{ID: "merge", Type: string(value.NodeTypeMerge), Name: "Merge", Config: map[string]any{}},
			{ID: "output", Type: string(value.NodeTypeOutput), Name: "Output", Config: map[string]any{}},
		},
		[]entity.Edge{
			{From: "start", To: "left"},
			{From: "start", To: "right"},
			{From: "left", To: "merge"},
			{From: "right", To: "merge"},
			{From: "merge", To: "output"},
		},
	)

	engine.StartRun(runID, graphJSON, "{}")
	engine.AwaitBlockedAttempt(runID, "start", 1)
	engine.Release(runID, "start")
	engine.AwaitBlockedCount(runID, 2)

	engine.Release(runID, "left")
	engine.AwaitEvents("left completion", func(events []ObservedEvent) bool {
		return sequenceFor(events, port.EventTypeNodeCompleted, "left") > 0
	})
	if engine.Stepper.AttemptCount(runID, "merge") != 0 {
		t.Fatalf("merge must not start until right also completes")
	}

	engine.Release(runID, "right")
	engine.AwaitBlockedAttempt(runID, "merge", 1)

	events := engine.Bus.All()
	leftCompleted := sequenceFor(events, port.EventTypeNodeCompleted, "left")
	rightCompleted := sequenceFor(events, port.EventTypeNodeCompleted, "right")
	mergeStarted := sequenceFor(events, port.EventTypeNodeStarted, "merge")
	if leftCompleted == 0 || rightCompleted == 0 || mergeStarted == 0 {
		t.Fatalf("expected causal events, got %v", summarizeEvents(events))
	}
	if leftCompleted >= mergeStarted || rightCompleted >= mergeStarted {
		t.Fatalf("merge started before dependencies completed: left=%d right=%d merge=%d", leftCompleted, rightCompleted, mergeStarted)
	}

	engine.Release(runID, "merge")
	engine.AwaitBlockedAttempt(runID, "output", 1)
	engine.Release(runID, "output")
	engine.AwaitRunStatus(runID, string(value.RunStatusSucceeded))
}

// Description: High-concurrency fan-out with more than one hundred agent tasks and a single fan-in output.
// Invariants: all tasks execute exactly once; the engine reaches success under load; the output starts only after every worker finishes.
// Edge cases: all worker goroutines are simultaneously blocked and then released.
func TestSchedulerDeterministicStress(t *testing.T) {
	const workerCount = 128

	engine := NewTestEngine(t, workerCount+2)

	rootExec := engine.RegisterExecutor(string(value.NodeTypeTransform), func(ctx context.Context, node *entity.Node, state *entity.State) (*port.NodeExecutionResult, error) {
		return port.NewSuccessResult(map[string]any{"root": true}), nil
	})
	agentExec := engine.RegisterExecutor(string(value.NodeTypeAgent), func(ctx context.Context, node *entity.Node, state *entity.State) (*port.NodeExecutionResult, error) {
		return port.NewSuccessResult(map[string]any{"agent": node.ID}), nil
	})
	outputExec := engine.RegisterExecutor(string(value.NodeTypeOutput), func(ctx context.Context, node *entity.Node, state *entity.State) (*port.NodeExecutionResult, error) {
		return port.NewSuccessResult(map[string]any{"workers": workerCount}), nil
	})

	nodes := []entity.Node{
		{ID: "root", Type: string(value.NodeTypeTransform), Name: "Root", Config: map[string]any{}},
	}
	edges := make([]entity.Edge, 0, workerCount+workerCount)
	for index := 0; index < workerCount; index++ {
		workerID := fmt.Sprintf("agent_%03d", index)
		nodes = append(nodes, entity.Node{ID: workerID, Type: string(value.NodeTypeAgent), Name: workerID, Config: map[string]any{}})
		edges = append(edges, entity.Edge{From: "root", To: workerID})
		edges = append(edges, entity.Edge{From: workerID, To: "output"})
	}
	nodes = append(nodes, entity.Node{ID: "output", Type: string(value.NodeTypeOutput), Name: "Output", Config: map[string]any{}})

	runID := "run-deterministic-stress"
	engine.StartRun(runID, makeGraphJSON(nodes, edges), "{}")
	engine.AwaitBlockedAttempt(runID, "root", 1)
	engine.Release(runID, "root")

	blocked := engine.AwaitBlockedCount(runID, workerCount)
	if len(blocked) != workerCount {
		t.Fatalf("expected %d blocked agents, got %d", workerCount, len(blocked))
	}

	snapshot := engine.Snapshot(runID)
	if len(snapshot.Running) != workerCount {
		t.Fatalf("expected %d running agents, got %d", workerCount, len(snapshot.Running))
	}

	if released := engine.ReleaseAll(runID); released != workerCount {
		t.Fatalf("expected to release %d workers, released %d", workerCount, released)
	}
	engine.AwaitBlockedAttempt(runID, "output", 1)
	engine.Release(runID, "output")

	snapshot = engine.AwaitRunStatus(runID, string(value.RunStatusSucceeded))
	if snapshot.Output["workers"] != float64(workerCount) && snapshot.Output["workers"] != workerCount {
		t.Fatalf("expected worker count output, got %#v", snapshot.Output)
	}

	events := engine.Bus.All()
	if rootExec.getExecuteCount() != 1 {
		t.Fatalf("expected root to execute once, got %d", rootExec.getExecuteCount())
	}
	if agentExec.getExecuteCount() != workerCount {
		t.Fatalf("expected %d agent executions, got %d", workerCount, agentExec.getExecuteCount())
	}
	if outputExec.getExecuteCount() != 1 {
		t.Fatalf("expected output to execute once, got %d", outputExec.getExecuteCount())
	}
	if countEvents(events, port.EventTypeNodeStarted) != workerCount+2 {
		t.Fatalf("expected %d node_started events, got %d", workerCount+2, countEvents(events, port.EventTypeNodeStarted))
	}
	if countEvents(events, port.EventTypeNodeCompleted) != workerCount+2 {
		t.Fatalf("expected %d node_completed events, got %d", workerCount+2, countEvents(events, port.EventTypeNodeCompleted))
	}
}

func countEvents(events []ObservedEvent, eventType port.EventType) int {
	count := 0
	for _, observed := range events {
		if observed.Event.Type == eventType {
			count++
		}
	}
	return count
}

func finalAttemptFor(events []ObservedEvent, eventType port.EventType, nodeID string) int {
	attempt := 0
	for _, observed := range events {
		if observed.Event.Type == eventType && observed.Event.NodeID == nodeID {
			attempt = observed.Event.Attempt
		}
	}
	return attempt
}
