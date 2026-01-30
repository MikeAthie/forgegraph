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
	)
	redisCircuitState.WithLabelValues("open").Set(0)
	redisCircuitState.WithLabelValues("closed").Set(1)
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
