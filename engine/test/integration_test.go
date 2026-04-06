//go:build legacy_engine_tests
// +build legacy_engine_tests

package test

import (
	"context"
	"encoding/json"
	"fmt"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
	"time"

	"github.com/forgegraph/engine/adapter/executor"
	"github.com/forgegraph/engine/adapter/gateway"
	"github.com/forgegraph/engine/adapter/repository"
	"github.com/forgegraph/engine/adapter/store"
	"github.com/forgegraph/engine/adapter/tool"
	"github.com/forgegraph/engine/application/port"
	"github.com/forgegraph/engine/application/usecase"
	"github.com/forgegraph/engine/domain/entity"
)

type integrationSequenceLLMClient struct {
	responses []*executor.LLMResponse
	calls     int
}

func (m *integrationSequenceLLMClient) Complete(ctx context.Context, request *executor.LLMRequest) (*executor.LLMResponse, error) {
	if len(m.responses) == 0 {
		return &executor.LLMResponse{Content: `{"action":"final_answer","final_answer":"done"}`, Model: request.Model}, nil
	}
	index := m.calls
	if index >= len(m.responses) {
		index = len(m.responses) - 1
	}
	m.calls++
	return m.responses[index], nil
}

func (m *integrationSequenceLLMClient) StreamComplete(
	ctx context.Context,
	request *executor.LLMRequest,
	onChunk func(string),
) (*executor.LLMResponse, error) {
	response, err := m.Complete(ctx, request)
	if err != nil {
		return nil, err
	}
	if onChunk != nil && response != nil && response.Content != "" {
		onChunk(response.Content)
	}
	return response, nil
}

type integrationToolInvoker struct {
	calls  int
	output any
}

func (m *integrationToolInvoker) Execute(ctx context.Context, node *entity.Node, state *entity.State) (*port.NodeExecutionResult, error) {
	m.calls++
	return port.NewSuccessResult(m.output), nil
}

type integrationObservationMemoryClient struct {
	observations []port.Observation
	saveRequests []port.ObservationSaveRequest
}

func (m *integrationObservationMemoryClient) SaveObservation(ctx context.Context, request port.ObservationSaveRequest) (port.Observation, error) {
	observation := port.Observation{
		ID:         fmt.Sprintf("obs-%d", len(m.observations)+1),
		TenantID:   request.TenantID,
		GraphID:    request.GraphID,
		RunID:      request.RunID,
		SessionID:  request.SessionID,
		AgentID:    request.AgentID,
		Type:       request.Type,
		Title:      request.Title,
		Content:    request.Content,
		Scope:      request.Scope,
		TopicKey:   request.TopicKey,
		ToolName:   request.ToolName,
		CreatedAt:  time.Now().UTC(),
		UpdatedAt:  time.Now().UTC(),
		LastSeenAt: time.Now().UTC(),
	}
	m.saveRequests = append(m.saveRequests, request)
	m.observations = append(m.observations, observation)
	return observation, nil
}

func (m *integrationObservationMemoryClient) SearchObservations(ctx context.Context, request port.ObservationSearchRequest) ([]port.Observation, error) {
	results := make([]port.Observation, 0)
	for _, observation := range m.observations {
		if request.Scope != "" && observation.Scope != request.Scope {
			continue
		}
		if request.GraphID != "" && observation.GraphID != request.GraphID {
			continue
		}
		if request.RunID != "" && observation.RunID != request.RunID {
			continue
		}
		if request.SessionID != "" && observation.SessionID != request.SessionID {
			continue
		}
		if request.Query != "" && !strings.Contains(strings.ToLower(observation.Content), strings.ToLower(request.Query)) {
			continue
		}
		results = append(results, observation)
	}
	return results, nil
}

func (m *integrationObservationMemoryClient) GetContext(ctx context.Context, request port.ObservationContextRequest) (port.ObservationContextResponse, error) {
	return port.ObservationContextResponse{Observations: m.observations}, nil
}

func (m *integrationObservationMemoryClient) GetTimeline(ctx context.Context, request port.ObservationTimelineRequest) ([]port.Observation, error) {
	return append([]port.Observation(nil), m.observations...), nil
}

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

func waitForRunInactive(t *testing.T, scheduler *usecase.Scheduler, runID string, timeout time.Duration) {
	t.Helper()
	deadline := time.Now().Add(timeout)
	for time.Now().Before(deadline) {
		if !scheduler.IsRunActive(runID) {
			return
		}
		time.Sleep(25 * time.Millisecond)
	}
	t.Fatalf("timeout waiting for run %s to become inactive", runID)
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
	scheduler := usecase.NewScheduler(config, registry, repo, emitter, store.NewInMemoryMemoryStore())

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
	err = scheduler.StartRun(context.Background(), runID, string(graphJSON), inputJSON, "", "", "", "")
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
	scheduler := usecase.NewScheduler(config, registry, repo, emitter, store.NewInMemoryMemoryStore())

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
	err = scheduler.StartRun(context.Background(), runID, string(graphJSON), inputJSON, "", "", "", "")
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

func TestObservationSaveThenSearchWorkflow(t *testing.T) {
	repo := repository.NewMemoryRunRepository()
	emitter := gateway.NewRecordingEventEmitter()
	memoryStore := store.NewInMemoryMemoryStore()
	observationClient := &integrationObservationMemoryClient{}

	registry := port.NewExecutorRegistry()
	registry.RegisterAll(
		executor.NewOutputExecutor(),
		executor.NewObservationSaveExecutor(observationClient),
		executor.NewObservationSearchExecutor(observationClient),
	)

	scheduler := usecase.NewScheduler(usecase.SchedulerConfig{
		MaxWorkers:       2,
		DefaultTimeoutMs: 5000,
	}, registry, repo, emitter, memoryStore)

	graph := map[string]any{
		"graph_id": "graph-obs-integration",
		"nodes": []map[string]any{
			{
				"id":   "save_1",
				"type": "observation_save",
				"name": "Save Observation",
				"config": map[string]any{
					"type":    "fact",
					"scope":   "session",
					"content": "Renewal closes on Friday",
				},
			},
			{
				"id":   "search_1",
				"type": "observation_search",
				"name": "Search Observation",
				"config": map[string]any{
					"scope": "session",
					"query": "renewal",
				},
			},
			{
				"id":   "output_1",
				"type": "output",
				"name": "Output",
				"config": map[string]any{
					"output_mapping": map[string]any{
						"search_results": "node.search_1.output",
					},
				},
			},
		},
		"edges": []map[string]any{
			{"id": "e1", "from": "save_1", "to": "search_1"},
			{"id": "e2", "from": "search_1", "to": "output_1"},
		},
	}

	graphJSON, err := json.Marshal(graph)
	if err != nil {
		t.Fatalf("Failed to marshal graph: %v", err)
	}

	runID := "observation-workflow-run"
	repo.AddRun(&entity.Run{
		ID:        runID,
		Status:    "pending",
		StartedAt: time.Now(),
	})

	if err := scheduler.StartRun(
		context.Background(),
		runID,
		string(graphJSON),
		"{}",
		"",
		"",
		"tenant-obs",
		"session-obs",
	); err != nil {
		t.Fatalf("Failed to start run: %v", err)
	}

	status := waitForRunCompletion(t, scheduler, repo, runID, 10*time.Second)
	if status != "succeeded" {
		t.Fatalf("Expected status succeeded, got %s", status)
	}

	if len(observationClient.saveRequests) != 1 {
		t.Fatalf("expected 1 saved observation, got %d", len(observationClient.saveRequests))
	}
	if observationClient.saveRequests[0].GraphID != "graph-obs-integration" {
		t.Fatalf("graph_id = %q, want graph-obs-integration", observationClient.saveRequests[0].GraphID)
	}

	run, err := repo.GetRun(context.Background(), runID)
	if err != nil {
		t.Fatalf("Failed to fetch run: %v", err)
	}
	searchOutput, ok := run.OutputJSON["search_results"].(map[string]any)
	if !ok {
		t.Fatalf("Expected search_results map, got %T", run.OutputJSON["search_results"])
	}
	if searchOutput["count"] != 1 {
		t.Fatalf("Expected count=1, got %v", searchOutput["count"])
	}
	items, ok := searchOutput["observations"].([]map[string]any)
	if !ok {
		t.Fatalf("Expected observations slice, got %T", searchOutput["observations"])
	}
	if len(items) != 1 || items[0]["content"] != "Renewal closes on Friday" {
		t.Fatalf("Unexpected observations payload: %#v", items)
	}
}

func TestRuntimeBackedToolCanExecuteAfterRemoteLoad(t *testing.T) {
	toolServer := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		_, _ = fmt.Fprint(w, `{"customer_status":"active"}`)
	}))
	defer toolServer.Close()

	controlPlane := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if got := r.URL.Query().Get("tenant_id"); got != "tenant-1" {
			t.Fatalf("tenant_id = %s, want tenant-1", got)
		}
		w.Header().Set("Content-Type", "application/json")
		_, _ = fmt.Fprintf(
			w,
			`{"data":{"tenant_id":"tenant-1","manifest_version":1,"checksum":"manifest-1","generated_at":"2026-03-12T00:00:00Z","tools":[{"name":"crm_lookup","version":"1.0.0","kind":"http","input_schema":{"type":"object"},"http":{"url":"%s","method":"POST"}}],"packages":[]}}`,
			toolServer.URL,
		)
	}))
	defer controlPlane.Close()

	manifestClient := gateway.NewMarketplaceManifestClient(controlPlane.URL, "test-secret")
	payload, unchanged, err := manifestClient.Fetch(context.Background(), "tenant-1", "")
	if err != nil {
		t.Fatalf("Fetch() error = %v", err)
	}
	if unchanged {
		t.Fatal("expected changed manifest")
	}

	registry := tool.NewRegistry()
	if err := registry.LoadDefinitions(payload.Tools); err != nil {
		t.Fatalf("LoadDefinitions() error = %v", err)
	}

	exec := executor.NewToolExecutor(registry)
	node := &entity.Node{
		ID:   "tool_1",
		Type: "tool",
		Config: map[string]any{
			"tool": "crm_lookup",
			"input": map[string]any{
				"customer_id": "cust_123",
			},
		},
	}

	result, err := exec.Execute(context.Background(), node, entity.NewState())
	if err != nil {
		t.Fatalf("Execute() error = %v", err)
	}
	if result.Error != nil {
		t.Fatalf("result.Error = %v", result.Error)
	}

	output, ok := result.Output.(map[string]any)
	if !ok {
		t.Fatalf("result.Output = %T, want map[string]any", result.Output)
	}
	body, ok := output["result"].(map[string]any)
	if !ok {
		t.Fatalf("output[result] = %#v, want map[string]any", output["result"])
	}
	if body["customer_status"] != "active" {
		t.Fatalf("customer_status = %v, want active", body["customer_status"])
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
	scheduler := usecase.NewScheduler(config, registry, repo, emitter, store.NewInMemoryMemoryStore())

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
	err = scheduler.StartRun(context.Background(), runID, string(graphJSON), "{}", "", "", "", "")
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

func TestToolNode_HTTPCallIntegration(t *testing.T) {
	repo := repository.NewMemoryRunRepository()
	emitter := gateway.NewRecordingEventEmitter()
	memoryStore := store.NewInMemoryMemoryStore()

	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		_, _ = fmt.Fprint(w, `{"ok":true,"provider":"tool-http"}`)
	}))
	defer server.Close()

	toolRegistry := tool.NewRegistry()
	toolRegistry.Register(tool.Definition{
		Name:        "test.http.integration",
		Version:     "1.0.0",
		Kind:        "http",
		InputSchema: map[string]any{"type": "object"},
		HTTP: &tool.HTTPToolConfig{
			URL:    server.URL,
			Method: "POST",
		},
	})

	registry := port.NewExecutorRegistry()
	registry.RegisterAll(
		executor.NewOutputExecutor(),
		executor.NewToolExecutor(toolRegistry),
	)

	scheduler := usecase.NewScheduler(usecase.SchedulerConfig{
		MaxWorkers:       2,
		DefaultTimeoutMs: 5000,
	}, registry, repo, emitter, memoryStore)

	graph := map[string]any{
		"nodes": []map[string]any{
			{
				"id":   "tool-1",
				"type": "tool",
				"name": "HTTP Tool",
				"config": map[string]any{
					"tool": "test.http.integration",
					"input": map[string]any{
						"query": "hello",
					},
				},
			},
			{
				"id":   "output-1",
				"type": "output",
				"name": "Output",
				"config": map[string]any{
					"output_mapping": map[string]any{
						"tool_output": "node.tool-1.output",
					},
				},
			},
		},
		"edges": []map[string]any{
			{"id": "e1", "from": "tool-1", "to": "output-1"},
		},
	}

	graphJSON, err := json.Marshal(graph)
	if err != nil {
		t.Fatalf("Failed to marshal graph: %v", err)
	}

	runID := "tool-http-run"
	repo.AddRun(&entity.Run{ID: runID, Status: "pending", StartedAt: time.Now()})

	if err := scheduler.StartRun(context.Background(), runID, string(graphJSON), "{}", "", "", "", ""); err != nil {
		t.Fatalf("Failed to start run: %v", err)
	}

	status := waitForRunCompletion(t, scheduler, repo, runID, 10*time.Second)
	if status != "succeeded" {
		t.Fatalf("Expected status succeeded, got %s", status)
	}

	run, err := repo.GetRun(context.Background(), runID)
	if err != nil {
		t.Fatalf("Failed to fetch run: %v", err)
	}
	output, ok := run.OutputJSON["tool_output"].(map[string]any)
	if !ok {
		t.Fatalf("Expected tool_output map, got %T", run.OutputJSON["tool_output"])
	}
	if output["status"] != float64(http.StatusOK) && output["status"] != http.StatusOK {
		t.Fatalf("Expected status 200, got %v", output["status"])
	}
}

func TestMemoryNode_PersistsAcrossRunsIntegration(t *testing.T) {
	repo := repository.NewMemoryRunRepository()
	emitter := gateway.NewRecordingEventEmitter()
	memoryStore := store.NewInMemoryMemoryStore()

	registry := port.NewExecutorRegistry()
	registry.RegisterAll(
		executor.NewOutputExecutor(),
		executor.NewMemoryExecutor(memoryStore),
	)

	scheduler := usecase.NewScheduler(usecase.SchedulerConfig{
		MaxWorkers:       2,
		DefaultTimeoutMs: 5000,
	}, registry, repo, emitter, memoryStore)

	setGraph := map[string]any{
		"nodes": []map[string]any{
			{
				"id":   "mem-set",
				"type": "memory",
				"name": "Memory Set",
				"config": map[string]any{
					"action":    "set",
					"namespace": "agent-demo",
					"key":       "greeting",
					"value":     "hello-world",
				},
			},
			{
				"id":   "output-1",
				"type": "output",
				"name": "Output",
				"config": map[string]any{
					"output_mapping": map[string]any{
						"memory_set": "node.mem-set.output",
					},
				},
			},
		},
		"edges": []map[string]any{
			{"id": "e1", "from": "mem-set", "to": "output-1"},
		},
	}
	getGraph := map[string]any{
		"nodes": []map[string]any{
			{
				"id":   "mem-get",
				"type": "memory",
				"name": "Memory Get",
				"config": map[string]any{
					"action":    "get",
					"namespace": "agent-demo",
					"key":       "greeting",
				},
			},
			{
				"id":   "output-1",
				"type": "output",
				"name": "Output",
				"config": map[string]any{
					"output_mapping": map[string]any{
						"memory_get": "node.mem-get.output",
					},
				},
			},
		},
		"edges": []map[string]any{
			{"id": "e1", "from": "mem-get", "to": "output-1"},
		},
	}
	deleteGraph := map[string]any{
		"nodes": []map[string]any{
			{
				"id":   "mem-delete",
				"type": "memory",
				"name": "Memory Delete",
				"config": map[string]any{
					"action":    "delete",
					"namespace": "agent-demo",
					"key":       "greeting",
				},
			},
			{
				"id":   "output-1",
				"type": "output",
				"name": "Output",
				"config": map[string]any{
					"output_mapping": map[string]any{
						"memory_delete": "node.mem-delete.output",
					},
				},
			},
		},
		"edges": []map[string]any{
			{"id": "e1", "from": "mem-delete", "to": "output-1"},
		},
	}

	marshal := func(graph map[string]any) string {
		graphJSON, err := json.Marshal(graph)
		if err != nil {
			t.Fatalf("Failed to marshal graph: %v", err)
		}
		return string(graphJSON)
	}

	runSet := "memory-set-run"
	repo.AddRun(&entity.Run{ID: runSet, Status: "pending", StartedAt: time.Now()})
	if err := scheduler.StartRun(context.Background(), runSet, marshal(setGraph), "{}", "", "", "", ""); err != nil {
		t.Fatalf("Failed to start set run: %v", err)
	}
	if status := waitForRunCompletion(t, scheduler, repo, runSet, 10*time.Second); status != "succeeded" {
		t.Fatalf("Expected set run status succeeded, got %s", status)
	}

	runGet := "memory-get-run"
	repo.AddRun(&entity.Run{ID: runGet, Status: "pending", StartedAt: time.Now()})
	if err := scheduler.StartRun(context.Background(), runGet, marshal(getGraph), "{}", "", "", "", ""); err != nil {
		t.Fatalf("Failed to start get run: %v", err)
	}
	if status := waitForRunCompletion(t, scheduler, repo, runGet, 10*time.Second); status != "succeeded" {
		t.Fatalf("Expected get run status succeeded, got %s", status)
	}

	getRun, err := repo.GetRun(context.Background(), runGet)
	if err != nil {
		t.Fatalf("Failed to fetch get run: %v", err)
	}
	getOutput, ok := getRun.OutputJSON["memory_get"].(map[string]any)
	if !ok {
		t.Fatalf("Expected memory_get output map, got %T", getRun.OutputJSON["memory_get"])
	}
	if getOutput["found"] != true || getOutput["value"] != "hello-world" {
		t.Fatalf("Expected found=true and value=hello-world, got %#v", getOutput)
	}

	runDelete := "memory-delete-run"
	repo.AddRun(&entity.Run{ID: runDelete, Status: "pending", StartedAt: time.Now()})
	if err := scheduler.StartRun(context.Background(), runDelete, marshal(deleteGraph), "{}", "", "", "", ""); err != nil {
		t.Fatalf("Failed to start delete run: %v", err)
	}
	if status := waitForRunCompletion(t, scheduler, repo, runDelete, 10*time.Second); status != "succeeded" {
		t.Fatalf("Expected delete run status succeeded, got %s", status)
	}

	runGetAfterDelete := "memory-get-after-delete-run"
	repo.AddRun(&entity.Run{ID: runGetAfterDelete, Status: "pending", StartedAt: time.Now()})
	if err := scheduler.StartRun(context.Background(), runGetAfterDelete, marshal(getGraph), "{}", "", "", "", ""); err != nil {
		t.Fatalf("Failed to start second get run: %v", err)
	}
	if status := waitForRunCompletion(t, scheduler, repo, runGetAfterDelete, 10*time.Second); status != "succeeded" {
		t.Fatalf("Expected second get run status succeeded, got %s", status)
	}

	getAfterDeleteRun, err := repo.GetRun(context.Background(), runGetAfterDelete)
	if err != nil {
		t.Fatalf("Failed to fetch second get run: %v", err)
	}
	getAfterDeleteOutput, ok := getAfterDeleteRun.OutputJSON["memory_get"].(map[string]any)
	if !ok {
		t.Fatalf("Expected memory_get output map after delete, got %T", getAfterDeleteRun.OutputJSON["memory_get"])
	}
	if getAfterDeleteOutput["found"] != false {
		t.Fatalf("Expected found=false after delete, got %#v", getAfterDeleteOutput)
	}
}
