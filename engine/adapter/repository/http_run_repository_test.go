package repository

import (
	"context"
	"encoding/json"
	"errors"
	"net/http"
	"net/http/httptest"
	"testing"
	"time"

	"github.com/forgegraph/engine/application/port"
	"github.com/forgegraph/engine/domain"
	"github.com/forgegraph/engine/domain/entity"
)

type recordingIntentPublisher struct {
	intents []*port.RuntimeIntentEnvelope
}

func (p *recordingIntentPublisher) Publish(ctx context.Context, intent *port.RuntimeIntentEnvelope) error {
	_ = ctx
	cloned := *intent
	cloned.Payload = cloneMap(intent.Payload)
	p.intents = append(p.intents, &cloned)
	return nil
}

func cloneMap(input map[string]any) map[string]any {
	if input == nil {
		return nil
	}
	output := make(map[string]any, len(input))
	for key, value := range input {
		output[key] = value
	}
	return output
}

func TestHTTPRunRepositoryGetRun(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path != "/api/engine/runs/run-1" {
			t.Fatalf("path = %s", r.URL.Path)
		}
		_ = json.NewEncoder(w).Encode(map[string]any{
			"data": map[string]any{
				"id":               "run-1",
				"graph_version_id": "graph-version-1",
				"status":           "running",
				"started_at":       "2026-04-05T12:00:00Z",
				"ended_at":         nil,
				"input_json":       map[string]any{"ticket": "FG-1"},
				"output_json":      nil,
				"error_message":    "",
				"trace_id":         "trace-1",
			},
		})
	}))
	defer server.Close()

	repo := NewHTTPRunRepository(server.URL, "test-secret", server.Client(), nil)
	run, err := repo.GetRun(context.Background(), "run-1")
	if err != nil {
		t.Fatalf("GetRun() error = %v", err)
	}
	if run.ID != "run-1" {
		t.Fatalf("run.ID = %s, want run-1", run.ID)
	}
	if run.GraphVersionID != "graph-version-1" {
		t.Fatalf("run.GraphVersionID = %s, want graph-version-1", run.GraphVersionID)
	}
	if run.Status != "running" {
		t.Fatalf("run.Status = %s, want running", run.Status)
	}
	if run.TraceID != "trace-1" {
		t.Fatalf("run.TraceID = %s, want trace-1", run.TraceID)
	}
}

func TestHTTPRunRepositorySaveCheckpointPublishesRuntimeIntent(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		t.Fatalf("unexpected HTTP call %s %s", r.Method, r.URL.Path)
	}))
	defer server.Close()

	publisher := &recordingIntentPublisher{}
	repo := NewHTTPRunRepository(server.URL, "test-secret", server.Client(), publisher)
	ctx := port.WithAttemptID(context.Background(), "attempt-7")
	err := repo.SaveCheckpoint(
		ctx,
		"run-1",
		"node-1",
		3,
		map[string]any{"vars": map[string]any{"answer": 42}},
		[]string{"node-1"},
		[]string{},
		`{"nodes":[],"edges":[]}`,
	)
	if err != nil {
		t.Fatalf("SaveCheckpoint() error = %v", err)
	}
	if len(publisher.intents) != 1 {
		t.Fatalf("expected 1 intent, got %d", len(publisher.intents))
	}
	intent := publisher.intents[0]
	if intent.IntentType != "store_checkpoint" {
		t.Fatalf("intent.IntentType = %s", intent.IntentType)
	}
	if intent.RunID != "run-1" {
		t.Fatalf("intent.RunID = %s", intent.RunID)
	}
	if intent.AttemptID != "attempt-7" {
		t.Fatalf("intent.AttemptID = %s", intent.AttemptID)
	}
	if intent.Payload["node_id"] != "node-1" {
		t.Fatalf("intent.Payload[node_id] = %#v", intent.Payload["node_id"])
	}
	if intent.Payload["step_index"] != 3 {
		t.Fatalf("intent.Payload[step_index] = %#v", intent.Payload["step_index"])
	}
}

func TestHTTPRunRepositoryNodeRunUpsertPublishesRuntimeIntent(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		t.Fatalf("unexpected HTTP call %s %s", r.Method, r.URL.Path)
	}))
	defer server.Close()

	publisher := &recordingIntentPublisher{}
	repo := NewHTTPRunRepository(server.URL, "test-secret", server.Client(), publisher)
	ctx := port.WithAttemptID(context.Background(), "attempt-9")
	startedAt := time.Date(2026, 4, 5, 12, 0, 0, 0, time.UTC)
	nodeRun := &entity.NodeRun{
		ID:        "logical-node-run-id",
		RunID:     "run-1",
		NodeID:    "node-1",
		NodeType:  "prompt",
		Status:    "running",
		Attempt:   1,
		StartedAt: startedAt,
		InputJSON: map[string]any{"prompt": "hello"},
		TraceID:   "trace-1",
		SpanID:    "span-1",
	}

	if err := repo.CreateNodeRun(ctx, nodeRun); err != nil {
		t.Fatalf("CreateNodeRun() error = %v", err)
	}
	if len(publisher.intents) != 1 {
		t.Fatalf("expected 1 intent, got %d", len(publisher.intents))
	}
	intent := publisher.intents[0]
	if intent.IntentType != "upsert_node_run" {
		t.Fatalf("intent.IntentType = %s", intent.IntentType)
	}
	if intent.AttemptID != "attempt-9" {
		t.Fatalf("intent.AttemptID = %s", intent.AttemptID)
	}
	if intent.Payload["id"] != "logical-node-run-id" {
		t.Fatalf("intent.Payload[id] = %#v", intent.Payload["id"])
	}
	if intent.Payload["node_id"] != "node-1" {
		t.Fatalf("intent.Payload[node_id] = %#v", intent.Payload["node_id"])
	}
}

func TestHTTPRunRepositoryUpdateRunStatusRequiresAttemptID(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		t.Fatalf("unexpected HTTP call %s %s", r.Method, r.URL.Path)
	}))
	defer server.Close()

	publisher := &recordingIntentPublisher{}
	repo := NewHTTPRunRepository(server.URL, "test-secret", server.Client(), publisher)

	err := repo.UpdateRunStatus(context.Background(), "run-1", "running")
	if err == nil {
		t.Fatal("expected missing attempt_id error")
	}
	if err.Error() != "runtime intent attempt_id is required" {
		t.Fatalf("unexpected error: %v", err)
	}
}

func TestHTTPRunRepositoryMapsCheckpointNotFound(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusNotFound)
		_ = json.NewEncoder(w).Encode(map[string]any{
			"error": map[string]any{
				"code":    "NO_CHECKPOINT",
				"message": "Checkpoint not found",
			},
		})
	}))
	defer server.Close()

	repo := NewHTTPRunRepository(server.URL, "test-secret", server.Client(), nil)
	_, _, _, _, _, _, err := repo.LoadLatestCheckpoint(context.Background(), "run-missing")
	if err == nil {
		t.Fatal("expected error")
	}
	if !errors.Is(err, domain.ErrCheckpointNotFound) {
		t.Fatalf("err = %v, want ErrCheckpointNotFound", err)
	}
}

func TestHTTPRunRepositoryLoadRunSnapshot(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path != "/api/engine/runs/run-1/snapshot" {
			t.Fatalf("path = %s", r.URL.Path)
		}
		_ = json.NewEncoder(w).Encode(map[string]any{
			"data": map[string]any{
				"run_id":              "run-1",
				"last_completed_node": "node-a",
				"next_node":           "node-b",
				"attempt_id":          "attempt-4",
				"updated_at":          "2026-04-14T12:00:00Z",
			},
		})
	}))
	defer server.Close()

	repo := NewHTTPRunRepository(server.URL, "test-secret", server.Client(), nil)
	snapshot, err := repo.LoadRunSnapshot(context.Background(), "run-1")
	if err != nil {
		t.Fatalf("LoadRunSnapshot() error = %v", err)
	}
	if snapshot.LastCompletedNode != "node-a" {
		t.Fatalf("snapshot.LastCompletedNode = %s", snapshot.LastCompletedNode)
	}
	if snapshot.NextNode != "node-b" {
		t.Fatalf("snapshot.NextNode = %s", snapshot.NextNode)
	}
	if snapshot.AttemptID != "attempt-4" {
		t.Fatalf("snapshot.AttemptID = %s", snapshot.AttemptID)
	}
}
