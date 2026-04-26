package metrics

import (
	"time"

	"github.com/prometheus/client_golang/prometheus"
)

var (
	redisOpsTotal = prometheus.NewCounterVec(
		prometheus.CounterOpts{
			Name: "forgegraph_memory_tier2_operations_total",
			Help: "Total Redis memory operations.",
		},
		[]string{"operation", "status"},
	)
	redisLatency = prometheus.NewHistogramVec(
		prometheus.HistogramOpts{
			Name:    "forgegraph_memory_tier2_latency_seconds",
			Help:    "Redis operation latency.",
			Buckets: prometheus.DefBuckets,
		},
		[]string{"operation"},
	)
	redisCircuitState = prometheus.NewGaugeVec(
		prometheus.GaugeOpts{
			Name: "forgegraph_memory_tier2_circuit_state",
			Help: "Redis circuit state (1=open, 0=closed).",
		},
		[]string{"state"},
	)
	redisFallbackTotal = prometheus.NewCounter(
		prometheus.CounterOpts{
			Name: "forgegraph_memory_tier2_fallback_total",
			Help: "Total Redis fallback activations.",
		},
	)
	tier1OpsTotal = prometheus.NewCounterVec(
		prometheus.CounterOpts{
			Name: "forgegraph_memory_tier1_operations_total",
			Help: "Total tier1 memory operations.",
		},
		[]string{"operation"},
	)
	tier1BufferSize = prometheus.NewGaugeVec(
		prometheus.GaugeOpts{
			Name: "forgegraph_memory_tier1_buffer_size",
			Help: "Current tier1 buffer size.",
		},
		[]string{"run_id"},
	)
	summarizationTriggers = prometheus.NewCounterVec(
		prometheus.CounterOpts{
			Name: "forgegraph_memory_summarization_triggers_total",
			Help: "Total summarization trigger events.",
		},
		[]string{"status"},
	)
	summarizationCostTotal = prometheus.NewCounterVec(
		prometheus.CounterOpts{
			Name: "forgegraph_memory_summarization_cost_total",
			Help: "Total summarization cost in USD.",
		},
		[]string{"model"},
	)
	preloadOpsTotal = prometheus.NewCounterVec(
		prometheus.CounterOpts{
			Name: "forgegraph_memory_preload_operations_total",
			Help: "Total memory preload operations.",
		},
		[]string{"operation", "status"},
	)
	preloadLatency = prometheus.NewHistogramVec(
		prometheus.HistogramOpts{
			Name:    "forgegraph_memory_preload_latency_seconds",
			Help:    "Memory preload latency.",
			Buckets: prometheus.DefBuckets,
		},
		[]string{"operation"},
	)
	runtimeIntentPublishTotal = prometheus.NewCounterVec(
		prometheus.CounterOpts{
			Name: "forgegraph_runtime_intent_publish_total",
			Help: "Total runtime intent publish attempts by result and intent type.",
		},
		[]string{"result", "intent_type"},
	)
	runtimeIntentPublishRetries = prometheus.NewCounterVec(
		prometheus.CounterOpts{
			Name: "forgegraph_runtime_intent_publish_retries_total",
			Help: "Total runtime intent publish retries by intent type.",
		},
		[]string{"intent_type"},
	)
	runtimeIntentPublishLatency = prometheus.NewHistogramVec(
		prometheus.HistogramOpts{
			Name:    "forgegraph_runtime_intent_publish_latency_seconds",
			Help:    "Runtime intent publish latency.",
			Buckets: prometheus.DefBuckets,
		},
		[]string{"intent_type"},
	)
	llmRequestsTotal = prometheus.NewCounterVec(
		prometheus.CounterOpts{
			Name: "forgegraph_llm_requests_total",
			Help: "Total LLM gateway requests.",
		},
		[]string{"provider", "status", "error_type", "fallback_used"},
	)
	llmLatency = prometheus.NewHistogramVec(
		prometheus.HistogramOpts{
			Name:    "forgegraph_llm_latency_seconds",
			Help:    "LLM gateway request latency.",
			Buckets: prometheus.DefBuckets,
		},
		[]string{"provider", "status"},
	)
	llmQueueDepth = prometheus.NewGauge(
		prometheus.GaugeOpts{
			Name: "forgegraph_llm_queue_depth",
			Help: "Current LLM gateway queue depth.",
		},
	)
	llmFallbackTotal = prometheus.NewCounterVec(
		prometheus.CounterOpts{
			Name: "forgegraph_llm_fallback_total",
			Help: "Total LLM gateway fallback attempts.",
		},
		[]string{"provider", "status"},
	)
	llmCircuitState = prometheus.NewGaugeVec(
		prometheus.GaugeOpts{
			Name: "forgegraph_llm_circuit_state",
			Help: "LLM gateway circuit breaker state (1=open, 0=closed).",
		},
		[]string{"state"},
	)
)

func init() {
	prometheus.MustRegister(
		redisOpsTotal,
		redisLatency,
		redisCircuitState,
		redisFallbackTotal,
		tier1OpsTotal,
		tier1BufferSize,
		summarizationTriggers,
		summarizationCostTotal,
		preloadOpsTotal,
		preloadLatency,
		runtimeIntentPublishTotal,
		runtimeIntentPublishRetries,
		runtimeIntentPublishLatency,
		llmRequestsTotal,
		llmLatency,
		llmQueueDepth,
		llmFallbackTotal,
		llmCircuitState,
	)
	redisCircuitState.WithLabelValues("open").Set(0)
	redisCircuitState.WithLabelValues("closed").Set(1)
	llmCircuitState.WithLabelValues("open").Set(0)
	llmCircuitState.WithLabelValues("closed").Set(1)
}

// RecordRedisOperation tracks Redis operation metrics.
func RecordRedisOperation(operation string, duration time.Duration, err error) {
	status := "success"
	if err != nil {
		status = "error"
	}
	redisOpsTotal.WithLabelValues(operation, status).Inc()
	redisLatency.WithLabelValues(operation).Observe(duration.Seconds())
}

// RecordFallback increments fallback counter.
func RecordFallback() {
	redisFallbackTotal.Inc()
}

// RecordCircuitState updates circuit breaker gauge.
func RecordCircuitState(open bool) {
	if open {
		redisCircuitState.WithLabelValues("open").Set(1)
		redisCircuitState.WithLabelValues("closed").Set(0)
		return
	}
	redisCircuitState.WithLabelValues("open").Set(0)
	redisCircuitState.WithLabelValues("closed").Set(1)
}

// RecordTier1Operation increments tier1 operation counter.
func RecordTier1Operation(operation string) {
	tier1OpsTotal.WithLabelValues(operation).Inc()
}

// RecordTier1BufferSize sets the buffer size gauge.
func RecordTier1BufferSize(runID string, size int) {
	if runID == "" {
		runID = "unknown"
	}
	tier1BufferSize.WithLabelValues(runID).Set(float64(size))
}

// RecordSummarizationTrigger increments summarization trigger metrics.
func RecordSummarizationTrigger(status string) {
	if status == "" {
		status = "unknown"
	}
	summarizationTriggers.WithLabelValues(status).Inc()
}

// RecordSummarizationCost increments summarization cost metrics.
func RecordSummarizationCost(model string, cost float64) {
	if model == "" {
		model = "unknown"
	}
	if cost <= 0 {
		return
	}
	summarizationCostTotal.WithLabelValues(model).Add(cost)
}

// RecordPreloadOperation tracks preload operation metrics.
func RecordPreloadOperation(operation string, status string, duration time.Duration) {
	if operation == "" {
		operation = "unknown"
	}
	if status == "" {
		status = "success"
	}
	preloadOpsTotal.WithLabelValues(operation, status).Inc()
	preloadLatency.WithLabelValues(operation).Observe(duration.Seconds())
}

// RecordRuntimeIntentPublish tracks runtime intent publishing outcomes.
func RecordRuntimeIntentPublish(intentType string, result string, duration time.Duration) {
	if intentType == "" {
		intentType = "unknown"
	}
	if result == "" {
		result = "success"
	}
	runtimeIntentPublishTotal.WithLabelValues(result, intentType).Inc()
	runtimeIntentPublishLatency.WithLabelValues(intentType).Observe(duration.Seconds())
}

// RecordRuntimeIntentPublishRetry increments runtime intent retry metrics.
func RecordRuntimeIntentPublishRetry(intentType string) {
	if intentType == "" {
		intentType = "unknown"
	}
	runtimeIntentPublishRetries.WithLabelValues(intentType).Inc()
}

func RecordLLMRequest(provider string, status string, errorType string, fallbackUsed bool, duration time.Duration) {
	if provider == "" {
		provider = "unknown"
	}
	if status == "" {
		status = "unknown"
	}
	if errorType == "" {
		errorType = "none"
	}
	fallbackValue := "false"
	if fallbackUsed {
		fallbackValue = "true"
	}
	llmRequestsTotal.WithLabelValues(provider, status, errorType, fallbackValue).Inc()
	llmLatency.WithLabelValues(provider, status).Observe(duration.Seconds())
}

func RecordLLMQueueDepth(depth int64) {
	if depth < 0 {
		depth = 0
	}
	llmQueueDepth.Set(float64(depth))
}

func RecordLLMFallback(provider string, status string) {
	if provider == "" {
		provider = "unknown"
	}
	if status == "" {
		status = "unknown"
	}
	llmFallbackTotal.WithLabelValues(provider, status).Inc()
}

func RecordLLMCircuitState(open bool) {
	if open {
		llmCircuitState.WithLabelValues("open").Set(1)
		llmCircuitState.WithLabelValues("closed").Set(0)
		return
	}
	llmCircuitState.WithLabelValues("open").Set(0)
	llmCircuitState.WithLabelValues("closed").Set(1)
}
