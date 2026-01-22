package port

import (
	"context"
	"time"
)

// EventType defines the type of execution event
type EventType string

const (
	// Run-level events
	EventTypeRunStarted   EventType = "run_started"
	EventTypeRunCompleted EventType = "run_completed"
	EventTypeRunFailed    EventType = "run_failed"
	EventTypeRunPaused    EventType = "run_paused"
	EventTypeRunResumed   EventType = "run_resumed"
	EventTypeRunCanceled  EventType = "run_canceled"

	// Node-level events
	EventTypeNodeStarted   EventType = "node_started"
	EventTypeNodeCompleted EventType = "node_completed"
	EventTypeNodeFailed    EventType = "node_failed"
	EventTypeNodeSkipped   EventType = "node_skipped"
	EventTypeNodeRetrying  EventType = "node_retrying"
)

// String returns the string representation of the event type
func (t EventType) String() string {
	return string(t)
}

// IsRunEvent returns true if this is a run-level event
func (t EventType) IsRunEvent() bool {
	switch t {
	case EventTypeRunStarted, EventTypeRunCompleted, EventTypeRunFailed,
		EventTypeRunPaused, EventTypeRunResumed, EventTypeRunCanceled:
		return true
	}
	return false
}

// IsNodeEvent returns true if this is a node-level event
func (t EventType) IsNodeEvent() bool {
	switch t {
	case EventTypeNodeStarted, EventTypeNodeCompleted, EventTypeNodeFailed,
		EventTypeNodeSkipped, EventTypeNodeRetrying:
		return true
	}
	return false
}

// ExecutionEvent represents an event during workflow execution.
// Events are sent to the control plane for real-time tracking.
type ExecutionEvent struct {
	// Type is the event type
	Type EventType `json:"type"`

	// RunID is the run this event belongs to
	RunID string `json:"run_id"`

	// NodeID is the node this event relates to (empty for run-level events)
	NodeID string `json:"node_id,omitempty"`

	// NodeType is the type of node (empty for run-level events)
	NodeType string `json:"node_type,omitempty"`

	// NodeName is the display name of the node
	NodeName string `json:"node_name,omitempty"`

	// Attempt is the retry attempt number (1-based)
	Attempt int `json:"attempt,omitempty"`

	// Input is the node's input data (for node_started events)
	Input map[string]any `json:"input,omitempty"`

	// Output is the node's output data (for node_completed events)
	Output map[string]any `json:"output,omitempty"`

	// Error is the error message (for failed events)
	Error string `json:"error,omitempty"`

	// Timestamp is when the event occurred (Unix milliseconds)
	Timestamp int64 `json:"timestamp"`

	// Duration is the execution time in milliseconds (for completed events)
	DurationMs int64 `json:"duration_ms,omitempty"`
}

// NewEvent creates a new execution event with the current timestamp
func NewEvent(eventType EventType, runID string) *ExecutionEvent {
	return &ExecutionEvent{
		Type:      eventType,
		RunID:     runID,
		Timestamp: time.Now().UnixMilli(),
	}
}

// WithNode adds node information to the event
func (e *ExecutionEvent) WithNode(nodeID, nodeType, nodeName string) *ExecutionEvent {
	e.NodeID = nodeID
	e.NodeType = nodeType
	e.NodeName = nodeName
	return e
}

// WithAttempt adds attempt number to the event
func (e *ExecutionEvent) WithAttempt(attempt int) *ExecutionEvent {
	e.Attempt = attempt
	return e
}

// WithInput adds input data to the event
func (e *ExecutionEvent) WithInput(input map[string]any) *ExecutionEvent {
	e.Input = input
	return e
}

// WithOutput adds output data to the event
func (e *ExecutionEvent) WithOutput(output map[string]any) *ExecutionEvent {
	e.Output = output
	return e
}

// WithError adds an error message to the event
func (e *ExecutionEvent) WithError(err string) *ExecutionEvent {
	e.Error = err
	return e
}

// WithDuration adds duration to the event
func (e *ExecutionEvent) WithDuration(durationMs int64) *ExecutionEvent {
	e.DurationMs = durationMs
	return e
}

// EventEmitter sends execution events to the control plane.
// The implementation typically makes HTTP POST requests to the callback URL.
type EventEmitter interface {
	// Emit sends an event to the control plane
	// Returns an error if the event could not be delivered
	Emit(ctx context.Context, event *ExecutionEvent) error

	// EmitAsync sends an event without waiting for delivery confirmation
	// Errors are logged but not returned
	EmitAsync(event *ExecutionEvent)

	// Flush waits for all pending async events to be sent
	Flush(ctx context.Context) error
}

// NoOpEventEmitter is an event emitter that does nothing (for testing)
type NoOpEventEmitter struct{}

func (e *NoOpEventEmitter) Emit(ctx context.Context, event *ExecutionEvent) error {
	return nil
}

func (e *NoOpEventEmitter) EmitAsync(event *ExecutionEvent) {}

func (e *NoOpEventEmitter) Flush(ctx context.Context) error {
	return nil
}

// NewNoOpEventEmitter creates a no-op event emitter
func NewNoOpEventEmitter() *NoOpEventEmitter {
	return &NoOpEventEmitter{}
}
