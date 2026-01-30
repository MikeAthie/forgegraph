package store

import (
	"context"
	"sync"
	"time"
)

// HealthStatus represents Redis health state.
type HealthStatus struct {
	Healthy   bool      `json:"healthy"`
	LatencyMs int64     `json:"latency_ms"`
	CheckedAt time.Time `json:"checked_at"`
	Error     string    `json:"error,omitempty"`
}

type redisPinger interface {
	Ping(ctx context.Context) error
}

// RedisHealthChecker checks Redis connectivity with caching.
type RedisHealthChecker struct {
	pinger     redisPinger
	lastCheck  time.Time
	lastStatus HealthStatus
	cacheFor   time.Duration
	mu         sync.Mutex
}

// NewRedisHealthChecker creates a health checker with default cache duration.
func NewRedisHealthChecker(pinger redisPinger) *RedisHealthChecker {
	return &RedisHealthChecker{
		pinger:   pinger,
		cacheFor: 5 * time.Second,
	}
}

// Check returns cached health status or executes a new ping.
func (h *RedisHealthChecker) Check(ctx context.Context) HealthStatus {
	h.mu.Lock()
	defer h.mu.Unlock()

	if !h.lastCheck.IsZero() && time.Since(h.lastCheck) < h.cacheFor {
		return h.lastStatus
	}

	status := HealthStatus{CheckedAt: time.Now()}
	if h.pinger == nil {
		status.Healthy = false
		status.Error = "redis not configured"
		h.lastStatus = status
		h.lastCheck = status.CheckedAt
		return status
	}

	start := time.Now()
	healthCtx, cancel := context.WithTimeout(ctx, time.Second)
	defer cancel()

	if err := h.pinger.Ping(healthCtx); err != nil {
		status.Healthy = false
		status.Error = err.Error()
	} else {
		status.Healthy = true
	}
	status.LatencyMs = time.Since(start).Milliseconds()

	h.lastStatus = status
	h.lastCheck = status.CheckedAt
	return status
}
