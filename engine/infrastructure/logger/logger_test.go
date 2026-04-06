package logger

import (
	"bytes"
	"encoding/json"
	"testing"
)

func TestNewUsesForgeGraphJSONKeys(t *testing.T) {
	var buffer bytes.Buffer
	log := newWithWriter(DefaultConfig(), &buffer)

	log.Info("engine_started", "run_id", "run-123")

	var payload map[string]any
	if err := json.Unmarshal(buffer.Bytes(), &payload); err != nil {
		t.Fatalf("expected valid json log, got error: %v", err)
	}

	if payload["timestamp"] == nil {
		t.Fatal("expected timestamp field")
	}
	if payload["service"] != "engine" {
		t.Fatalf("expected service=engine, got %v", payload["service"])
	}
	if payload["event_type"] != "engine_started" {
		t.Fatalf("expected event_type=engine_started, got %v", payload["event_type"])
	}
	if payload["level"] != "info" {
		t.Fatalf("expected level=info, got %v", payload["level"])
	}
	if payload["run_id"] != "run-123" {
		t.Fatalf("expected run_id=run-123, got %v", payload["run_id"])
	}
}

func TestStdlibBridgeWrapsPlainLogLines(t *testing.T) {
	var buffer bytes.Buffer
	log := newWithWriter(DefaultConfig(), &buffer)
	bridge := &stdlibBridge{logger: log.Logger}

	if _, err := bridge.Write([]byte("Warning: emitter backlog detected\n")); err != nil {
		t.Fatalf("bridge.Write() error = %v", err)
	}

	var payload map[string]any
	if err := json.Unmarshal(buffer.Bytes(), &payload); err != nil {
		t.Fatalf("expected valid json log, got error: %v", err)
	}

	if payload["event_type"] != "legacy.log" {
		t.Fatalf("expected event_type=legacy.log, got %v", payload["event_type"])
	}
	if payload["level"] != "warn" {
		t.Fatalf("expected level=warn, got %v", payload["level"])
	}
	if payload["message"] != "Warning: emitter backlog detected" {
		t.Fatalf("expected preserved message, got %v", payload["message"])
	}
}
