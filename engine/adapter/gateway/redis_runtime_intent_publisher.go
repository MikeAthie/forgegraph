package gateway

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"log/slog"
	"math/rand"
	"net"
	"strings"
	"time"

	"github.com/forgegraph/engine/application/port"
	"github.com/forgegraph/engine/infrastructure/metrics"
	redis "github.com/redis/go-redis/v9"
)

const DefaultRuntimeIntentStream = "forgegraph:runtime:intents"

// RuntimeIntentStreamClient is the Redis client surface required for publishing intents.
type RuntimeIntentStreamClient interface {
	XAdd(ctx context.Context, a *redis.XAddArgs) *redis.StringCmd
}

// RuntimeIntentPublisherConfig controls publish retry and retention behavior.
type RuntimeIntentPublisherConfig struct {
	InitialBackoff time.Duration
	MaxBackoff     time.Duration
	MaxElapsedTime time.Duration
	StreamMaxLen   int64
}

// DefaultRuntimeIntentPublisherConfig returns production-oriented defaults.
func DefaultRuntimeIntentPublisherConfig() RuntimeIntentPublisherConfig {
	return RuntimeIntentPublisherConfig{
		InitialBackoff: 100 * time.Millisecond,
		MaxBackoff:     2 * time.Second,
		MaxElapsedTime: 20 * time.Second,
		StreamMaxLen:   0,
	}
}

// RuntimeIntentPublishError surfaces transport failures to the scheduler.
type RuntimeIntentPublishError struct {
	IntentID   string
	IntentType string
	RunID      string
	Attempts   int
	Elapsed    time.Duration
	Retryable  bool
	Kind       string
	Cause      error
}

func (e *RuntimeIntentPublishError) Error() string {
	if e == nil {
		return ""
	}
	return fmt.Sprintf(
		"runtime intent publish failed kind=%s retryable=%t attempts=%d elapsed=%s: %v",
		e.Kind,
		e.Retryable,
		e.Attempts,
		e.Elapsed,
		e.Cause,
	)
}

func (e *RuntimeIntentPublishError) Unwrap() error {
	if e == nil {
		return nil
	}
	return e.Cause
}

// RedisRuntimeIntentPublisher writes backend-owned runtime intents to a Redis stream.
type RedisRuntimeIntentPublisher struct {
	client     RuntimeIntentStreamClient
	streamName string
	config     RuntimeIntentPublisherConfig
	sleep      func(context.Context, time.Duration) error
	now        func() time.Time
}

// NewRedisRuntimeIntentPublisher creates a Redis-backed runtime intent publisher.
func NewRedisRuntimeIntentPublisher(
	client RuntimeIntentStreamClient,
	streamName string,
) (*RedisRuntimeIntentPublisher, error) {
	return NewRedisRuntimeIntentPublisherWithConfig(
		client,
		streamName,
		DefaultRuntimeIntentPublisherConfig(),
	)
}

// NewRedisRuntimeIntentPublisherWithConfig creates a Redis-backed publisher with explicit config.
func NewRedisRuntimeIntentPublisherWithConfig(
	client RuntimeIntentStreamClient,
	streamName string,
	config RuntimeIntentPublisherConfig,
) (*RedisRuntimeIntentPublisher, error) {
	if client == nil {
		return nil, fmt.Errorf("redis runtime intent publisher requires a client")
	}
	streamName = strings.TrimSpace(streamName)
	if streamName == "" {
		streamName = DefaultRuntimeIntentStream
	}
	config = normalizeRuntimeIntentPublisherConfig(config)
	return &RedisRuntimeIntentPublisher{
		client:     client,
		streamName: streamName,
		config:     config,
		sleep:      sleepWithContext,
		now:        time.Now,
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
		intent.Timestamp = p.now().UTC().Format(time.RFC3339Nano)
	}

	body, err := json.Marshal(intent)
	if err != nil {
		return fmt.Errorf("marshal runtime intent: %w", err)
	}

	startedAt := p.now()
	slog.Default().Info(
		"intent_publish_start",
		"intent_id", intent.IntentID,
		"intent_type", intent.IntentType,
		"run_id", intent.RunID,
		"stream", p.streamName,
	)

	attempts := 0
	for {
		attempts++
		attemptStartedAt := p.now()
		xaddArgs := &redis.XAddArgs{
			Stream: p.streamName,
			Values: map[string]any{
				"intent": string(body),
			},
		}
		if p.config.StreamMaxLen > 0 {
			xaddArgs.MaxLen = p.config.StreamMaxLen
			xaddArgs.Approx = true
		}
		messageID, publishErr := p.client.XAdd(ctx, xaddArgs).Result()
		attemptDuration := p.now().Sub(attemptStartedAt)
		if publishErr == nil {
			metrics.RecordRuntimeIntentPublish(intent.IntentType, "success", attemptDuration)
			slog.Default().Info(
				"intent_publish_success",
				"intent_id", intent.IntentID,
				"intent_type", intent.IntentType,
				"run_id", intent.RunID,
				"stream", p.streamName,
				"message_id", messageID,
				"attempt", attempts,
				"elapsed_ms", p.now().Sub(startedAt).Milliseconds(),
			)
			return nil
		}

		elapsed := p.now().Sub(startedAt)
		retryable, kind := classifyPublishError(publishErr)
		metrics.RecordRuntimeIntentPublish(intent.IntentType, "failure", attemptDuration)

		if !retryable || elapsed >= p.config.MaxElapsedTime || ctx.Err() != nil {
			slog.Default().Error(
				"intent_publish_failed",
				"intent_id", intent.IntentID,
				"intent_type", intent.IntentType,
				"run_id", intent.RunID,
				"stream", p.streamName,
				"attempt", attempts,
				"elapsed_ms", elapsed.Milliseconds(),
				"retryable", retryable,
				"failure_kind", kind,
				"error", publishErr.Error(),
			)
			return &RuntimeIntentPublishError{
				IntentID:   intent.IntentID,
				IntentType: intent.IntentType,
				RunID:      intent.RunID,
				Attempts:   attempts,
				Elapsed:    elapsed,
				Retryable:  retryable,
				Kind:       kind,
				Cause:      publishErr,
			}
		}

		backoff := jitterDuration(exponentialBackoff(p.config.InitialBackoff, p.config.MaxBackoff, attempts-1))
		if remaining := p.config.MaxElapsedTime - elapsed; backoff > remaining {
			backoff = remaining
		}
		if backoff <= 0 {
			backoff = time.Millisecond
		}
		metrics.RecordRuntimeIntentPublishRetry(intent.IntentType)
		slog.Default().Warn(
			"intent_publish_retry",
			"intent_id", intent.IntentID,
			"intent_type", intent.IntentType,
			"run_id", intent.RunID,
			"stream", p.streamName,
			"attempt", attempts,
			"elapsed_ms", elapsed.Milliseconds(),
			"retryable", retryable,
			"failure_kind", kind,
			"next_backoff_ms", backoff.Milliseconds(),
			"error", publishErr.Error(),
		)
		if err := p.sleep(ctx, backoff); err != nil {
			return &RuntimeIntentPublishError{
				IntentID:   intent.IntentID,
				IntentType: intent.IntentType,
				RunID:      intent.RunID,
				Attempts:   attempts,
				Elapsed:    p.now().Sub(startedAt),
				Retryable:  false,
				Kind:       "context_canceled",
				Cause:      err,
			}
		}
	}
}

func normalizeRuntimeIntentPublisherConfig(config RuntimeIntentPublisherConfig) RuntimeIntentPublisherConfig {
	defaults := DefaultRuntimeIntentPublisherConfig()
	if config.InitialBackoff <= 0 {
		config.InitialBackoff = defaults.InitialBackoff
	}
	if config.MaxBackoff <= 0 {
		config.MaxBackoff = defaults.MaxBackoff
	}
	if config.MaxBackoff < config.InitialBackoff {
		config.MaxBackoff = config.InitialBackoff
	}
	if config.MaxElapsedTime <= 0 {
		config.MaxElapsedTime = defaults.MaxElapsedTime
	}
	return config
}

func sleepWithContext(ctx context.Context, delay time.Duration) error {
	timer := time.NewTimer(delay)
	defer timer.Stop()
	select {
	case <-ctx.Done():
		return ctx.Err()
	case <-timer.C:
		return nil
	}
}

func exponentialBackoff(initial time.Duration, maxBackoff time.Duration, retryIndex int) time.Duration {
	backoff := initial
	for i := 0; i < retryIndex; i++ {
		backoff *= 2
		if backoff >= maxBackoff {
			return maxBackoff
		}
	}
	if backoff > maxBackoff {
		return maxBackoff
	}
	return backoff
}

func jitterDuration(value time.Duration) time.Duration {
	if value <= 1 {
		return value
	}
	jitterRange := int64(value / 2)
	if jitterRange <= 0 {
		return value
	}
	return value/2 + time.Duration(rand.Int63n(jitterRange+1))
}

func classifyPublishError(err error) (bool, string) {
	if err == nil {
		return false, ""
	}
	if errors.Is(err, context.Canceled) || errors.Is(err, context.DeadlineExceeded) {
		return false, "context_canceled"
	}

	var netErr net.Error
	if errors.As(err, &netErr) {
		if netErr.Timeout() {
			return true, "timeout"
		}
		return true, "connection_error"
	}

	message := strings.ToLower(strings.TrimSpace(err.Error()))
	switch {
	case strings.Contains(message, "wrongpass"),
		strings.Contains(message, "noauth"),
		strings.Contains(message, "invalid password"),
		strings.Contains(message, "invalid username-password pair"),
		strings.Contains(message, "sentinel master name"),
		strings.Contains(message, "unknown command"):
		return false, "auth_or_config"
	case strings.Contains(message, "readonly"),
		strings.Contains(message, "loading"),
		strings.Contains(message, "masterdown"),
		strings.Contains(message, "tryagain"),
		strings.Contains(message, "failover"),
		strings.Contains(message, "connection refused"),
		strings.Contains(message, "connection reset"),
		strings.Contains(message, "broken pipe"),
		strings.Contains(message, "eof"),
		strings.Contains(message, "timeout"),
		strings.Contains(message, "i/o timeout"):
		return true, "redis_unavailable"
	default:
		return false, "unknown"
	}
}
