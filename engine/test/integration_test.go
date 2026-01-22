package test

import (
	"context"
	"encoding/json"
	"testing"
	"time"

	"github.com/forgegraph/engine/adapter/executor"
	"github.com/forgegraph/engine/adapter/gateway"
	"github.com/forgegraph/engine/adapter/repository"
	"github.com/forgegraph/engine/application/port"
	"github.com/forgegraph/engine/application/usecase"
	"github.com/forgegraph/engine/domain/entity"
)

// waitForRunCompletion polls for run completion with a timeout
func waitForRunCompletion(t *testing.T, scheduler *usecase.Scheduler, repo *repository.MemoryRunRepository, runID string, timeout time.Duration) string {
	ctx, cancel := context.WithTimeout(context.Background(), timeout)
	defer cancel()

	for {
		select {
		case <-ctx.Done():
			// Timeout - check repo directly as fallback
			run, err := repo.GetRun(context.Background(), runID)
			if err == nil && run != nil {
				t.Logf("Final status from repo: %s", run.Status)
				return run.Status
			}
			t.Fatalf("Timeout waiting for run to complete. Last repo check error: %v", err)
			return ""
		default:
			// First try scheduler (active runs)
			status, _, err := scheduler.GetRunStatus(runID)
			if err == nil {
				if status == "succeeded" || status == "failed" || status == "canceled" {
					return status
				}
			}

			// Also check repo directly
			run, err := repo.GetRun(context.Background(), runID)
			if err == nil && run != nil {
				if run.Status == "succeeded" || run.Status == "failed" || run.Status == "canceled" {
					return run.Status
				}
			}

			time.Sleep(50 * time.Millisecond)
		}
	}
}

// TestSimpleTransformToOutput tests a simple workflow: Transform → Output
func TestSimpleTransformToOutput(t *testing.T) {
	// Setup
	repo := repository.NewMemoryRunRepository()
	emitter := gateway.NewRecordingEventEmitter()

	registry := port.NewExecutorRegistry()
	registry.RegisterAll(
		executor.NewOutputExecutor(),
		executor.NewTransformExecutor(),
	)

	config := usecase.SchedulerConfig{
		MaxWorkers:       2,
		DefaultTimeoutMs: 5000,
	}
	scheduler := usecase.NewScheduler(config, registry, repo, emitter)

	// Create a simple graph: Transform → Output
	graph := map[string]any{
		"nodes": []map[string]any{
			{
				"id":   "transform-1",
				"type": "transform",
				"name": "Set Greeting",
				"config": map[string]any{
					"expression_type": "static",
					"expression":      "Hello, World!",
					"output_key":      "greeting",
				},
			},
			{
				"id":   "output-1",
				"type": "output",
				"name": "Final Output",
				"config": map[string]any{
					"output_keys": []string{"greeting"},
				},
			},
		},
		"edges": []map[string]any{
			{
				"id":   "edge-1",
				"from": "transform-1",
				"to":   "output-1",
			},
		},
	}

	graphJSON, err := json.Marshal(graph)
	if err != nil {
		t.Fatalf("Failed to marshal graph: %v", err)
	}

	inputJSON := "{}"
	runID := "test-run-001"

	// Seed the run record (simulating control plane creating it)
	repo.AddRun(&entity.Run{
		ID:        runID,
		Status:    "pending",
		StartedAt: time.Now(),
	})

	// Execute
	err = scheduler.StartRun(context.Background(), runID, string(graphJSON), inputJSON, "")
	if err != nil {
		t.Fatalf("Failed to start run: %v", err)
	}

	// Wait for completion
	status := waitForRunCompletion(t, scheduler, repo, runID, 10*time.Second)

	// Verify
	if status != "succeeded" {
		t.Errorf("Expected status 'succeeded', got '%s'", status)
	}

	// Check events were emitted
	events := emitter.GetEvents()
	if len(events) == 0 {
		t.Error("Expected events to be emitted")
	}

	// Verify run_started event
	startedEvents := emitter.GetEventsByType(port.EventTypeRunStarted)
	if len(startedEvents) != 1 {
		t.Errorf("Expected 1 run_started event, got %d", len(startedEvents))
	}

	// Verify run_completed event
	completedEvents := emitter.GetEventsByType(port.EventTypeRunCompleted)
	if len(completedEvents) != 1 {
		t.Errorf("Expected 1 run_completed event, got %d", len(completedEvents))
	}

	// Verify node events
	nodeStartedEvents := emitter.GetEventsByType(port.EventTypeNodeStarted)
	if len(nodeStartedEvents) != 2 {
		t.Errorf("Expected 2 node_started events, got %d", len(nodeStartedEvents))
	}

	nodeCompletedEvents := emitter.GetEventsByType(port.EventTypeNodeCompleted)
	if len(nodeCompletedEvents) != 2 {
		t.Errorf("Expected 2 node_completed events, got %d", len(nodeCompletedEvents))
	}
}

// TestLinearWorkflow tests: Transform → Transform → Output
func TestLinearWorkflow(t *testing.T) {
	// Setup
	repo := repository.NewMemoryRunRepository()
	emitter := gateway.NewRecordingEventEmitter()

	registry := port.NewExecutorRegistry()
	registry.RegisterAll(
		executor.NewOutputExecutor(),
		executor.NewTransformExecutor(),
	)

	config := usecase.SchedulerConfig{
		MaxWorkers:       2,
		DefaultTimeoutMs: 5000,
	}
	scheduler := usecase.NewScheduler(config, registry, repo, emitter)

	// Create a workflow with chained transforms
	graph := map[string]any{
		"nodes": []map[string]any{
			{
				"id":   "transform-1",
				"type": "transform",
				"name": "Simulate API Response",
				"config": map[string]any{
					"expression_type": "static",
					"expression":      `{"data": "test value"}`,
					"output_key":      "api_response",
				},
			},
			{
				"id":   "transform-2",
				"type": "transform",
				"name": "Extract Data",
				"config": map[string]any{
					"expression_type": "key_lookup",
					"expression":      "vars.api_response",
					"output_key":      "extracted",
				},
			},
			{
				"id":   "output-1",
				"type": "output",
				"name": "Final Output",
				"config": map[string]any{
					"include_all": true,
				},
			},
		},
		"edges": []map[string]any{
			{
				"id":   "edge-1",
				"from": "transform-1",
				"to":   "transform-2",
			},
			{
				"id":   "edge-2",
				"from": "transform-2",
				"to":   "output-1",
			},
		},
	}

	graphJSON, err := json.Marshal(graph)
	if err != nil {
		t.Fatalf("Failed to marshal graph: %v", err)
	}

	inputJSON := "{}"
	runID := "test-run-002"

	// Seed the run record
	repo.AddRun(&entity.Run{
		ID:        runID,
		Status:    "pending",
		StartedAt: time.Now(),
	})

	// Execute
	err = scheduler.StartRun(context.Background(), runID, string(graphJSON), inputJSON, "")
	if err != nil {
		t.Fatalf("Failed to start run: %v", err)
	}

	// Wait for completion
	status := waitForRunCompletion(t, scheduler, repo, runID, 10*time.Second)

	// Verify
	if status != "succeeded" {
		t.Errorf("Expected status 'succeeded', got '%s'", status)
	}

	// Should have 3 node_completed events
	nodeCompletedEvents := emitter.GetEventsByType(port.EventTypeNodeCompleted)
	if len(nodeCompletedEvents) != 3 {
		t.Errorf("Expected 3 node_completed events, got %d", len(nodeCompletedEvents))
	}
}

// TestCancelRun tests run cancellation
func TestCancelRun(t *testing.T) {
	// Setup
	repo := repository.NewMemoryRunRepository()
	emitter := gateway.NewRecordingEventEmitter()

	registry := port.NewExecutorRegistry()
	registry.RegisterAll(
		executor.NewOutputExecutor(),
		executor.NewTransformExecutor(),
	)

	config := usecase.SchedulerConfig{
		MaxWorkers:       1,
		DefaultTimeoutMs: 30000, // Long timeout
	}
	scheduler := usecase.NewScheduler(config, registry, repo, emitter)

	// Create a simple graph
	graph := map[string]any{
		"nodes": []map[string]any{
			{
				"id":   "transform-1",
				"type": "transform",
				"name": "Step 1",
				"config": map[string]any{
					"expression_type": "static",
					"expression":      "value1",
					"output_key":      "step1",
				},
			},
			{
				"id":   "output-1",
				"type": "output",
				"name": "Output",
				"config": map[string]any{
					"include_all": true,
				},
			},
		},
		"edges": []map[string]any{
			{
				"id":   "edge-1",
				"from": "transform-1",
				"to":   "output-1",
			},
		},
	}

	graphJSON, err := json.Marshal(graph)
	if err != nil {
		t.Fatalf("Failed to marshal graph: %v", err)
	}

	runID := "test-run-003"

	// Seed the run record
	repo.AddRun(&entity.Run{
		ID:        runID,
		Status:    "pending",
		StartedAt: time.Now(),
	})

	// Start the run
	err = scheduler.StartRun(context.Background(), runID, string(graphJSON), "{}", "")
	if err != nil {
		t.Fatalf("Failed to start run: %v", err)
	}

	// Wait a bit for run to start
	time.Sleep(50 * time.Millisecond)

	// Cancel the run
	err = scheduler.CancelRun(runID)
	// Note: May return error if run already completed
	_ = err

	// Wait a bit for cancellation to process
	time.Sleep(200 * time.Millisecond)

	// Check that we got either succeeded (completed before cancel) or canceled
	status, _, _ := scheduler.GetRunStatus(runID)
	if status == "" {
		// Fallback to repo
		run, _ := repo.GetRun(context.Background(), runID)
		if run != nil {
			status = run.Status
		}
	}
	if status != "succeeded" && status != "canceled" {
		t.Errorf("Expected status 'succeeded' or 'canceled', got '%s'", status)
	}
}
