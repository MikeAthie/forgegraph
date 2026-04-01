package entity

import "time"

// Run represents a workflow execution instance
type Run struct {
	ID             string         `json:"id"`
	GraphVersionID string         `json:"graph_version_id"`
	Status         string         `json:"status"`
	StartedAt      time.Time      `json:"started_at"`
	EndedAt        *time.Time     `json:"ended_at,omitempty"`
	InputJSON      map[string]any `json:"input_json,omitempty"`
	OutputJSON     map[string]any `json:"output_json,omitempty"`
	ErrorMessage   string         `json:"error_message,omitempty"`
	TraceID        string         `json:"trace_id,omitempty"`
}

// NodeRun represents a single node's execution trace
type NodeRun struct {
	ID         string         `json:"id"`
	RunID      string         `json:"run_id"`
	NodeID     string         `json:"node_id"`
	NodeType   string         `json:"node_type"`
	Status     string         `json:"status"`
	Attempt    int            `json:"attempt"`
	StartedAt  time.Time      `json:"started_at"`
	EndedAt    *time.Time     `json:"ended_at,omitempty"`
	DurationMs int64          `json:"duration_ms,omitempty"`
	InputJSON  map[string]any `json:"input_json,omitempty"`
	OutputJSON map[string]any `json:"output_json,omitempty"`
	ErrorJSON  map[string]any `json:"error_json,omitempty"`
	TraceID    string         `json:"trace_id,omitempty"`
	SpanID     string         `json:"span_id,omitempty"`
}

// SetEnded marks the node run as ended and calculates duration
func (nr *NodeRun) SetEnded(endTime time.Time) {
	nr.EndedAt = &endTime
	nr.DurationMs = endTime.Sub(nr.StartedAt).Milliseconds()
}

// IsTerminal returns true if the run is in a terminal state
func (r *Run) IsTerminal() bool {
	switch r.Status {
	case "succeeded", "failed", "canceled":
		return true
	default:
		return false
	}
}

// IsRunning returns true if the run is currently executing
func (r *Run) IsRunning() bool {
	return r.Status == "running"
}

// IsPaused returns true if the run is paused (e.g., at human gate)
func (r *Run) IsPaused() bool {
	return r.Status == "paused"
}
