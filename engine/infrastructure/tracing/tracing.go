package tracing

import (
	"context"
	"fmt"

	"go.opentelemetry.io/otel"
	"go.opentelemetry.io/otel/propagation"
	"go.opentelemetry.io/otel/trace"
)

type textMapCarrier map[string]string

func (c textMapCarrier) Get(key string) string {
	return c[key]
}

func (c textMapCarrier) Set(key, value string) {
	c[key] = value
}

func (c textMapCarrier) Keys() []string {
	keys := make([]string, 0, len(c))
	for key := range c {
		keys = append(keys, key)
	}
	return keys
}

type TraceContext struct {
	TraceID     string
	SpanID      string
	Traceparent string
	Tracestate  string
}

func StartSpan(
	ctx context.Context,
	tracerName string,
	spanName string,
	traceparent string,
	tracestate string,
) (context.Context, trace.Span, TraceContext) {
	carrier := textMapCarrier{}
	if traceparent != "" {
		carrier.Set("traceparent", traceparent)
	}
	if tracestate != "" {
		carrier.Set("tracestate", tracestate)
	}
	ctx = propagation.TraceContext{}.Extract(ctx, carrier)
	ctx, span := otel.Tracer(tracerName).Start(ctx, spanName)
	return ctx, span, FromContext(ctx)
}

func FromContext(ctx context.Context) TraceContext {
	span := trace.SpanFromContext(ctx)
	if span == nil {
		return TraceContext{}
	}
	spanContext := span.SpanContext()
	if !spanContext.IsValid() {
		return TraceContext{}
	}
	traceState := spanContext.TraceState().String()
	return TraceContext{
		TraceID:     spanContext.TraceID().String(),
		SpanID:      spanContext.SpanID().String(),
		Traceparent: fmt.Sprintf("00-%s-%s-%s", spanContext.TraceID().String(), spanContext.SpanID().String(), spanContext.TraceFlags().String()),
		Tracestate:  traceState,
	}
}
