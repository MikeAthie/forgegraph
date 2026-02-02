package metrics

import (
	"github.com/prometheus/client_golang/prometheus"
	"github.com/prometheus/client_golang/prometheus/promauto"
)

var (
	memoryCostTrackingFailures = promauto.NewCounterVec(
		prometheus.CounterOpts{
			Name: "forgegraph_memory_cost_tracking_failures_total",
			Help: "Total cost tracking failures by type",
		},
		[]string{"operation", "error_type"},
	)

	memoryCostTrackingRetries = promauto.NewCounter(
		prometheus.CounterOpts{
			Name: "forgegraph_memory_cost_tracking_retries_total",
			Help: "Total cost tracking retry attempts",
		},
	)

	memoryBufferEvictions = promauto.NewCounterVec(
		prometheus.CounterOpts{
			Name: "forgegraph_memory_buffer_evictions_total",
			Help: "Total message evictions from buffer",
		},
		[]string{"reason", "tenant_id"},
	)

	memoryBufferEvictedMessages = promauto.NewCounterVec(
		prometheus.CounterOpts{
			Name: "forgegraph_memory_buffer_evicted_messages_total",
			Help: "Total messages evicted from buffer",
		},
		[]string{"reason", "tenant_id"},
	)

	memoryBufferEvictedTokens = promauto.NewCounterVec(
		prometheus.CounterOpts{
			Name: "forgegraph_memory_buffer_evicted_tokens_total",
			Help: "Total tokens evicted from buffer",
		},
		[]string{"tenant_id"},
	)
)

func RecordCostTrackingFailures(operation, errorType string) {
	memoryCostTrackingFailures.WithLabelValues(operation, errorType).Inc()
}

func RecordCostTrackingRetry() {
	memoryCostTrackingRetries.Inc()
}

// RecordBufferEviction records message eviction metrics.
func RecordBufferEviction(reason, tenantID string, messageCount, tokenCount int) {
	memoryBufferEvictions.WithLabelValues(reason, tenantID).Inc()
	if messageCount > 0 {
		memoryBufferEvictedMessages.WithLabelValues(reason, tenantID).Add(float64(messageCount))
	}
	if tokenCount > 0 {
		memoryBufferEvictedTokens.WithLabelValues(tenantID).Add(float64(tokenCount))
	}
}
