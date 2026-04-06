package repository

import (
	"context"
	"encoding/json"
	"errors"
	"net/http"
	"net/http/httptest"
	"testing"
	"time"

	"github.com/forgegraph/engine/domain"
	"github.com/forgegraph/engine/domain/entity"
)

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

	repo := NewHTTPRunRepository(server.URL, "test-secret", server.Client())
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

func TestHTTPRunRepositoryCheckpointRoundTrip(t *testing.T) {
	var stored map[string]any
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		switch r.Method {
		case http.MethodPut:
			if err := json.NewDecoder(r.Body).Decode(&stored); err != nil {
				t.Fatalf("Decode() error = %v", err)
			}
			_ = json.NewEncoder(w).Encode(map[string]any{"data": stored})
		case http.MethodGet:
			_ = json.NewEncoder(w).Encode(map[string]any{
				"data": map[string]any{
					"node_id":         stored["node_id"],
					"step_index":      stored["step_index"],
					"state_snapshot":  stored["state_snapshot"],
					"completed_nodes": stored["completed_nodes"],
					"skipped_nodes":   stored["skipped_nodes"],
					"graph_json":      stored["graph_json"],
				},
			})
		default:
			t.Fatalf("unexpected method %s", r.Method)
		}
	}))
	defer server.Close()

	repo := NewHTTPRunRepository(server.URL, "test-secret", server.Client())
	err := repo.SaveCheckpoint(
		context.Background(),
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

	nodeID, stepIndex, snapshot, completed, skipped, graphJSON, err := repo.LoadLatestCheckpoint(context.Background(), "run-1")
	if err != nil {
		t.Fatalf("LoadLatestCheckpoint() error = %v", err)
	}
	if nodeID != "node-1" {
		t.Fatalf("nodeID = %s, want node-1", nodeID)
	}
	if stepIndex != 3 {
		t.Fatalf("stepIndex = %d, want 3", stepIndex)
	}
	if graphJSON != `{"nodes":[],"edges":[]}` {
		t.Fatalf("graphJSON = %s", graphJSON)
	}
	if len(completed) != 1 || completed[0] != "node-1" {
		t.Fatalf("completed = %#v", completed)
	}
	if len(skipped) != 0 {
		t.Fatalf("skipped = %#v", skipped)
	}
	vars, ok := snapshot["vars"].(map[string]any)
	if !ok || vars["answer"] != float64(42) {
		t.Fatalf("snapshot = %#v", snapshot)
	}
}

func TestHTTPRunRepositoryNodeRunUpsertMutatesID(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodPut {
			t.Fatalf("unexpected method %s", r.Method)
		}
		var payload map[string]any
		if err := json.NewDecoder(r.Body).Decode(&payload); err != nil {
			t.Fatalf("Decode() error = %v", err)
		}
		_ = json.NewEncoder(w).Encode(map[string]any{
			"data": map[string]any{
				"id":         "11111111-1111-1111-1111-111111111111",
				"run_id":     "run-1",
				"node_id":    "node-1",
				"node_type":  payload["node_type"],
				"status":     payload["status"],
				"attempt":    payload["attempt"],
				"started_at": payload["started_at"],
				"ended_at":   payload["ended_at"],
				"input_json": payload["input_json"],
				"output_json": map[string]any{
					"ok": true,
				},
				"error_json": nil,
				"trace_id":   payload["trace_id"],
				"span_id":    payload["span_id"],
			},
		})
	}))
	defer server.Close()

	repo := NewHTTPRunRepository(server.URL, "test-secret", server.Client())
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

	if err := repo.CreateNodeRun(context.Background(), nodeRun); err != nil {
		t.Fatalf("CreateNodeRun() error = %v", err)
	}

	if nodeRun.ID != "11111111-1111-1111-1111-111111111111" {
		t.Fatalf("nodeRun.ID = %s", nodeRun.ID)
	}
	if nodeRun.OutputJSON["ok"] != true {
		t.Fatalf("nodeRun.OutputJSON = %#v", nodeRun.OutputJSON)
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

	repo := NewHTTPRunRepository(server.URL, "test-secret", server.Client())
	_, _, _, _, _, _, err := repo.LoadLatestCheckpoint(context.Background(), "run-missing")
	if err == nil {
		t.Fatal("expected error")
	}
	if !errors.Is(err, domain.ErrCheckpointNotFound) {
		t.Fatalf("err = %v, want ErrCheckpointNotFound", err)
	}
}
