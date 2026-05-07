package main

import (
	"context"
	"net/http"
	"net/http/httptest"
	"sync/atomic"
	"testing"
	"time"
)

func TestObserveRunStatusesCountsBackendTerminalStates(t *testing.T) {
	var firstRunPolls int32
	server := httptest.NewServer(http.HandlerFunc(func(writer http.ResponseWriter, request *http.Request) {
		writer.Header().Set("Content-Type", "application/json")
		switch request.URL.Path {
		case "/api/runs/run-succeeded":
			polls := atomic.AddInt32(&firstRunPolls, 1)
			if polls == 1 {
				_, _ = writer.Write([]byte(`{"data":{"status":"running"}}`))
				return
			}
			_, _ = writer.Write([]byte(`{"data":{"status":"succeeded"}}`))
		case "/api/runs/run-failed":
			_, _ = writer.Write([]byte(`{"data":{"status":"failed"}}`))
		default:
			http.NotFound(writer, request)
		}
	}))
	defer server.Close()

	client := NewAPIClient(Config{BaseURL: server.URL, RequestTimeout: time.Second}, nil)
	startedRuns := []startedRunRecord{
		{runID: "run-succeeded", tenant: TenantPlan{Index: 0, AccessToken: "token"}, agentIndex: 0},
		{runID: "run-failed", tenant: TenantPlan{Index: 0, AccessToken: "token"}, agentIndex: 1},
	}

	visible, completed, failed := observeRunStatuses(
		context.Background(),
		client,
		nil,
		startedRuns,
		0,
		time.Now().Add(5*time.Second),
	)

	if visible != 2 || completed != 1 || failed != 1 {
		t.Fatalf("visible=%d completed=%d failed=%d, want 2/1/1", visible, completed, failed)
	}
}

func TestRunStatusClassification(t *testing.T) {
	if !isSuccessfulRunStatus("succeeded") {
		t.Fatal("succeeded should be successful")
	}
	for _, statusValue := range []string{"failed", "canceled", "cancelled"} {
		if !isFailedRunStatus(statusValue) {
			t.Fatalf("%s should be failed", statusValue)
		}
	}
	if isSuccessfulRunStatus("running") || isFailedRunStatus("running") {
		t.Fatal("running should not be terminal")
	}
}
