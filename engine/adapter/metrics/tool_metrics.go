package metrics

import (
	"github.com/prometheus/client_golang/prometheus"
	"github.com/prometheus/client_golang/prometheus/promauto"
)

var (
	toolExecutorLegacyAdapterHits = promauto.NewCounter(
		prometheus.CounterOpts{
			Name: "forgegraph_tool_executor_legacy_adapter_hits_total",
			Help: "Total attempts to execute tools through the legacy node-based adapter path.",
		},
	)
)

func RecordLegacyToolAdapterHit() {
	toolExecutorLegacyAdapterHits.Inc()
}
