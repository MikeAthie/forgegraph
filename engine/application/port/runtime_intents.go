package port

import "context"

// RuntimeIntentEnvelope is the standard backend-owned durable write intent schema.
type RuntimeIntentEnvelope struct {
	IntentID   string         `json:"intent_id"`
	IntentType string         `json:"intent_type"`
	RunID      string         `json:"run_id"`
	AttemptID  string         `json:"attempt_id"`
	Timestamp  string         `json:"timestamp"`
	Payload    map[string]any `json:"payload"`
	TraceID    string         `json:"trace_id,omitempty"`
}

// RuntimeIntentPublisher publishes durable backend write intents.
type RuntimeIntentPublisher interface {
	Publish(ctx context.Context, intent *RuntimeIntentEnvelope) error
}
