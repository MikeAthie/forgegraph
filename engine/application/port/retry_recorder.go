package port

import (
	"context"
)

type retryRecorderContextKey struct{}

// RetryRecord describes a bounded retry loop that must be visible to the backend.
type RetryRecord struct {
	OperationType    string
	AttemptNumber    int
	MaxAttempts      int
	RetryDelayMs     int
	RetryReason      string
	LastError        error
	RetryClass       string
	TerminalFallback string
	Metadata         map[string]any
}

type RetryRecorder func(context.Context, RetryRecord) error

func WithRetryRecorder(ctx context.Context, recorder RetryRecorder) context.Context {
	if ctx == nil || recorder == nil {
		return ctx
	}
	return context.WithValue(ctx, retryRecorderContextKey{}, recorder)
}

func RecordRetry(ctx context.Context, record RetryRecord) error {
	if ctx == nil {
		return nil
	}
	recorder, _ := ctx.Value(retryRecorderContextKey{}).(RetryRecorder)
	if recorder == nil {
		return nil
	}
	return recorder(ctx, record)
}
