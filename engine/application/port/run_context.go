package port

import (
	"context"

	"github.com/forgegraph/engine/domain/entity"
)

// RunContext provides execution-scoped memory context to executors.
type RunContext struct {
	MemoryBuffer    *entity.MessageBuffer
	MemoryConfig    *entity.MemoryConfig
	CurrentSummary  *entity.Summary
	TrackMessage    func(count int)
	MemoryRetriever MemoryRetriever
}

type runContextKey struct{}

// WithRunContext attaches a RunContext to the context.
func WithRunContext(ctx context.Context, rc *RunContext) context.Context {
	if rc == nil {
		return ctx
	}
	return context.WithValue(ctx, runContextKey{}, rc)
}

// RunContextFrom extracts a RunContext from the context, if present.
func RunContextFrom(ctx context.Context) *RunContext {
	if ctx == nil {
		return nil
	}
	if value := ctx.Value(runContextKey{}); value != nil {
		if rc, ok := value.(*RunContext); ok {
			return rc
		}
	}
	return nil
}

type tenantIDKey struct{}

// WithTenantID attaches a tenant ID to the context.
func WithTenantID(ctx context.Context, tenantID string) context.Context {
	if tenantID == "" {
		return ctx
	}
	return context.WithValue(ctx, tenantIDKey{}, tenantID)
}

// TenantIDFrom extracts the tenant ID from the context.
func TenantIDFrom(ctx context.Context) string {
	if ctx == nil {
		return ""
	}
	if value := ctx.Value(tenantIDKey{}); value != nil {
		if tenantID, ok := value.(string); ok {
			return tenantID
		}
	}
	return ""
}
