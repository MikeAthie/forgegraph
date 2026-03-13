package executor

import (
	"context"
	"testing"
	"time"

	"github.com/forgegraph/engine/application/port"
	"github.com/forgegraph/engine/domain/entity"
)

type testObservationClient struct {
	saveRequest     *port.ObservationSaveRequest
	searchRequest   *port.ObservationSearchRequest
	contextRequest  *port.ObservationContextRequest
	timelineRequest *port.ObservationTimelineRequest

	saveResponse     port.Observation
	searchResponse   []port.Observation
	contextResponse  port.ObservationContextResponse
	timelineResponse []port.Observation
	err              error
}

func (c *testObservationClient) SaveObservation(ctx context.Context, request port.ObservationSaveRequest) (port.Observation, error) {
	c.saveRequest = &request
	if c.err != nil {
		return port.Observation{}, c.err
	}
	return c.saveResponse, nil
}

func (c *testObservationClient) SearchObservations(ctx context.Context, request port.ObservationSearchRequest) ([]port.Observation, error) {
	c.searchRequest = &request
	if c.err != nil {
		return nil, c.err
	}
	return c.searchResponse, nil
}

func (c *testObservationClient) GetContext(ctx context.Context, request port.ObservationContextRequest) (port.ObservationContextResponse, error) {
	c.contextRequest = &request
	if c.err != nil {
		return port.ObservationContextResponse{}, c.err
	}
	return c.contextResponse, nil
}

func (c *testObservationClient) GetTimeline(ctx context.Context, request port.ObservationTimelineRequest) ([]port.Observation, error) {
	c.timelineRequest = &request
	if c.err != nil {
		return nil, c.err
	}
	return c.timelineResponse, nil
}

func makeObservationRunContext() *port.RunContext {
	return &port.RunContext{
		TenantID:  "tenant-1",
		GraphID:   "graph-1",
		RunID:     "run-1",
		SessionID: "session-1",
	}
}

func TestObservationSaveExecutor_Execute_Success(t *testing.T) {
	now := time.Date(2026, 3, 13, 12, 0, 0, 0, time.UTC)
	client := &testObservationClient{
		saveResponse: port.Observation{
			ID:         "obs-1",
			TenantID:   "tenant-1",
			GraphID:    "graph-1",
			RunID:      "run-1",
			SessionID:  "session-1",
			AgentID:    "agent-123",
			Type:       "fact",
			Title:      "Customer preference",
			Content:    "Prefers SMS",
			Scope:      "session",
			LastSeenAt: now,
			CreatedAt:  now,
			UpdatedAt:  now,
		},
	}
	exec := NewObservationSaveExecutor(client)
	state := entity.NewStateWithInput(map[string]any{"channel": "SMS"})
	state.SetVar("observation_text", "Prefers SMS")

	node := &entity.Node{
		ID:   "obs_save_1",
		Type: "observation_save",
		Name: "Save Observation",
		Config: map[string]any{
			"type":           "fact",
			"scope":          "session",
			"title_template": "Customer preference",
			"content_path":   "vars.observation_text",
			"agent_id":       "agent-123",
			"dedupe":         false,
		},
	}

	ctx := port.WithRunContext(context.Background(), makeObservationRunContext())
	result, err := exec.Execute(ctx, node, state)
	if err != nil {
		t.Fatalf("Execute() error = %v", err)
	}
	if result.Error != nil {
		t.Fatalf("result.Error = %v", result.Error)
	}

	if client.saveRequest == nil {
		t.Fatal("expected save request")
	}
	if client.saveRequest.Scope != "session" {
		t.Fatalf("scope = %s, want session", client.saveRequest.Scope)
	}
	if client.saveRequest.GraphID != "graph-1" || client.saveRequest.RunID != "run-1" || client.saveRequest.SessionID != "session-1" {
		t.Fatalf("unexpected runtime identifiers: %#v", client.saveRequest)
	}
	if client.saveRequest.Content != "Prefers SMS" {
		t.Fatalf("content = %q, want Prefers SMS", client.saveRequest.Content)
	}
	if client.saveRequest.Dedupe == nil || *client.saveRequest.Dedupe {
		t.Fatalf("expected dedupe pointer set to false")
	}

	output, ok := result.Output.(map[string]any)
	if !ok {
		t.Fatalf("expected map output, got %T", result.Output)
	}
	if output["saved"] != true {
		t.Fatalf("saved = %v, want true", output["saved"])
	}
	observation, ok := output["observation"].(map[string]any)
	if !ok {
		t.Fatalf("expected observation map, got %T", output["observation"])
	}
	if observation["id"] != "obs-1" {
		t.Fatalf("observation id = %v, want obs-1", observation["id"])
	}
}

func TestObservationSearchExecutor_Execute_UsesScopedRuntimeFilter(t *testing.T) {
	client := &testObservationClient{
		searchResponse: []port.Observation{
			{ID: "obs-1", Scope: "run", Content: "Renewal closes Friday"},
		},
	}
	exec := NewObservationSearchExecutor(client)
	state := entity.NewStateWithInput(map[string]any{"topic": "renewal"})
	node := &entity.Node{
		ID:   "obs_search_1",
		Type: "observation_search",
		Name: "Search Observations",
		Config: map[string]any{
			"scope":           "run",
			"query_template":  "renewal {{input.topic}}",
			"type":            "fact",
			"include_deleted": true,
			"limit":           4,
		},
	}

	ctx := port.WithRunContext(context.Background(), makeObservationRunContext())
	result, err := exec.Execute(ctx, node, state)
	if err != nil {
		t.Fatalf("Execute() error = %v", err)
	}
	if result.Error != nil {
		t.Fatalf("result.Error = %v", result.Error)
	}

	if client.searchRequest == nil {
		t.Fatal("expected search request")
	}
	if client.searchRequest.RunID != "run-1" {
		t.Fatalf("run_id = %q, want run-1", client.searchRequest.RunID)
	}
	if client.searchRequest.GraphID != "" || client.searchRequest.SessionID != "" {
		t.Fatalf("expected only run scope filter, got %#v", client.searchRequest)
	}
	if client.searchRequest.Query != "renewal renewal" {
		t.Fatalf("query = %q, want resolved template", client.searchRequest.Query)
	}

	output := result.Output.(map[string]any)
	if output["count"] != 1 {
		t.Fatalf("count = %v, want 1", output["count"])
	}
}

func TestObservationContextExecutor_Execute_PassesRuntimeContext(t *testing.T) {
	client := &testObservationClient{
		contextResponse: port.ObservationContextResponse{
			Observations: []port.Observation{
				{ID: "obs-ctx-1", Scope: "session", Content: "Customer wants concise updates"},
			},
			Degraded:   true,
			Strategies: []string{"fts", "vector_unavailable"},
		},
	}
	exec := NewObservationContextExecutor(client)
	state := entity.NewState()
	node := &entity.Node{
		ID:   "obs_context_1",
		Type: "observation_context",
		Name: "Observation Context",
		Config: map[string]any{
			"query": "What should I remember?",
			"limit": 3,
		},
	}

	ctx := port.WithRunContext(context.Background(), makeObservationRunContext())
	result, err := exec.Execute(ctx, node, state)
	if err != nil {
		t.Fatalf("Execute() error = %v", err)
	}
	if result.Error != nil {
		t.Fatalf("result.Error = %v", result.Error)
	}

	if client.contextRequest == nil {
		t.Fatal("expected context request")
	}
	if client.contextRequest.GraphID != "graph-1" || client.contextRequest.RunID != "run-1" || client.contextRequest.SessionID != "session-1" {
		t.Fatalf("unexpected context identifiers: %#v", client.contextRequest)
	}

	output := result.Output.(map[string]any)
	if output["degraded"] != true {
		t.Fatalf("degraded = %v, want true", output["degraded"])
	}
}

func TestObservationTimelineExecutor_Execute_RequiresScopeRuntimeIdentifier(t *testing.T) {
	client := &testObservationClient{}
	exec := NewObservationTimelineExecutor(client)
	node := &entity.Node{
		ID:   "obs_timeline_1",
		Type: "observation_timeline",
		Name: "Timeline",
		Config: map[string]any{
			"scope": "session",
		},
	}
	ctx := port.WithRunContext(context.Background(), &port.RunContext{
		TenantID: "tenant-1",
		GraphID:  "graph-1",
		RunID:    "run-1",
	})

	result, err := exec.Execute(ctx, node, entity.NewState())
	if err != nil {
		t.Fatalf("Execute() error = %v", err)
	}
	if result.Error == nil {
		t.Fatal("expected validation error for missing session_id")
	}
}
