package metrics

import (
	"github.com/prometheus/client_golang/prometheus"
	"github.com/prometheus/client_golang/prometheus/promauto"
)

var (
	eventDeliveryTotals = promauto.NewCounterVec(
		prometheus.CounterOpts{
			Name: "forgegraph_event_delivery_total",
			Help: "Total event delivery attempts by result and type",
		},
		[]string{"result", "event_type"},
	)

	eventDeliveryRetries = promauto.NewCounterVec(
		prometheus.CounterOpts{
			Name: "forgegraph_event_delivery_retries_total",
			Help: "Total event delivery retry attempts by event type",
		},
		[]string{"event_type"},
	)

	eventDeliveryDropped = promauto.NewCounterVec(
		prometheus.CounterOpts{
			Name: "forgegraph_event_delivery_dropped_total",
			Help: "Total events dropped before delivery",
		},
		[]string{"reason", "event_type"},
	)

	eventDeliverySpooled = promauto.NewCounterVec(
		prometheus.CounterOpts{
			Name: "forgegraph_event_delivery_spooled_total",
			Help: "Total events persisted to the spool",
		},
		[]string{"event_type"},
	)
)

func RecordEventDeliverySuccess(eventType string) {
	eventDeliveryTotals.WithLabelValues("success", eventType).Inc()
}

func RecordEventDeliveryFailure(eventType string) {
	eventDeliveryTotals.WithLabelValues("failure", eventType).Inc()
}

func RecordEventDeliveryRetry(eventType string) {
	eventDeliveryRetries.WithLabelValues(eventType).Inc()
}

func RecordEventDrop(reason, eventType string) {
	eventDeliveryDropped.WithLabelValues(reason, eventType).Inc()
}

func RecordEventSpooled(eventType string) {
	eventDeliverySpooled.WithLabelValues(eventType).Inc()
}
