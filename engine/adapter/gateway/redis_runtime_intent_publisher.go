package gateway

import (
	"context"
	"encoding/json"
	"fmt"
	"strings"
	"time"

	"github.com/forgegraph/engine/application/port"
	redis "github.com/redis/go-redis/v9"
)

const DefaultRuntimeIntentStream = "forgegraph:runtime:intents"

// RedisRuntimeIntentPublisher writes backend-owned runtime intents to a Redis stream.
type RedisRuntimeIntentPublisher struct {
	client     *redis.Client
	streamName string
}

// NewRedisRuntimeIntentPublisher creates a Redis-backed runtime intent publisher.
func NewRedisRuntimeIntentPublisher(client *redis.Client, streamName string) (*RedisRuntimeIntentPublisher, error) {
	if client == nil {
		return nil, fmt.Errorf("redis runtime intent publisher requires a client")
	}
	streamName = strings.TrimSpace(streamName)
	if streamName == "" {
		streamName = DefaultRuntimeIntentStream
	}
	return &RedisRuntimeIntentPublisher{
		client:     client,
		streamName: streamName,
	}, nil
}

// Publish publishes a runtime intent to the configured Redis stream.
func (p *RedisRuntimeIntentPublisher) Publish(ctx context.Context, intent *port.RuntimeIntentEnvelope) error {
	if intent == nil {
		return fmt.Errorf("runtime intent is required")
	}
	if strings.TrimSpace(intent.IntentID) == "" {
		return fmt.Errorf("runtime intent intent_id is required")
	}
	if strings.TrimSpace(intent.RunID) == "" {
		return fmt.Errorf("runtime intent run_id is required")
	}
	if strings.TrimSpace(intent.IntentType) == "" {
		return fmt.Errorf("runtime intent intent_type is required")
	}
	if strings.TrimSpace(intent.Timestamp) == "" {
		intent.Timestamp = time.Now().UTC().Format(time.RFC3339Nano)
	}

	body, err := json.Marshal(intent)
	if err != nil {
		return fmt.Errorf("marshal runtime intent: %w", err)
	}

	return p.client.XAdd(ctx, &redis.XAddArgs{
		Stream: p.streamName,
		Values: map[string]any{
			"intent": string(body),
		},
	}).Err()
}
