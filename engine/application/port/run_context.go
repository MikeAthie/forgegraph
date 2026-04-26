package port

import (
	"context"
	"strings"

	"github.com/forgegraph/engine/domain/entity"
)

const (
	LLMModeManaged = "managed"
	LLMModeBYOK    = "byok"
)

type LLMAccessConfig struct {
	Mode         string
	Provider     string
	CredentialID string
	APIKey       string
}

func (c LLMAccessConfig) Normalized() LLMAccessConfig {
	mode := strings.ToLower(strings.TrimSpace(c.Mode))
	if mode != LLMModeBYOK {
		mode = LLMModeManaged
	}
	provider := strings.ToLower(strings.TrimSpace(c.Provider))
	if provider == "" {
		provider = "openai"
	}
	apiKey := strings.TrimSpace(c.APIKey)
	credentialID := strings.TrimSpace(c.CredentialID)
	if mode != LLMModeBYOK {
		credentialID = ""
		apiKey = ""
	}
	return LLMAccessConfig{
		Mode:         mode,
		Provider:     provider,
		CredentialID: credentialID,
		APIKey:       apiKey,
	}
}

// RunContext provides execution-scoped memory context to executors.
type RunContext struct {
	TenantID          string
	GraphID           string
	RunID             string
	SessionID         string
	TraceID           string
	Traceparent       string
	Tracestate        string
	MemoryBuffer      *entity.MessageBuffer
	MemoryConfig      *entity.MemoryConfig
	CurrentSummary    *entity.Summary
	TrackMessage      func(count int)
	TrackLLMCall      func() error
	TrackToolCall     func() error
	MemoryRetriever   MemoryRetriever
	ObservationClient ObservationMemoryClient
	Policy            *entity.ExecutionPolicy
	LLMAccess         LLMAccessConfig
}

// StreamChunkEmitter receives incremental LLM response chunks.
type StreamChunkEmitter func(chunk string)

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

// PolicyFromContext extracts an execution policy from context.
func PolicyFromContext(ctx context.Context) *entity.ExecutionPolicy {
	rc := RunContextFrom(ctx)
	if rc == nil {
		return nil
	}
	return rc.Policy
}

type tenantIDKey struct{}

type streamChunkEmitterKey struct{}

type attemptIDKey struct{}

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

// WithStreamChunkEmitter attaches a callback for incremental LLM output chunks.
func WithStreamChunkEmitter(ctx context.Context, emitter StreamChunkEmitter) context.Context {
	if emitter == nil {
		return ctx
	}
	return context.WithValue(ctx, streamChunkEmitterKey{}, emitter)
}

// StreamChunkEmitterFrom extracts the stream chunk callback from context.
func StreamChunkEmitterFrom(ctx context.Context) StreamChunkEmitter {
	if ctx == nil {
		return nil
	}
	if value := ctx.Value(streamChunkEmitterKey{}); value != nil {
		if emitter, ok := value.(StreamChunkEmitter); ok {
			return emitter
		}
	}
	return nil
}

// WithAttemptID attaches the current execution attempt ID to the context.
func WithAttemptID(ctx context.Context, attemptID string) context.Context {
	if attemptID == "" {
		return ctx
	}
	return context.WithValue(ctx, attemptIDKey{}, attemptID)
}

// AttemptIDFrom extracts the current execution attempt ID from the context.
func AttemptIDFrom(ctx context.Context) string {
	if ctx == nil {
		return ""
	}
	if value := ctx.Value(attemptIDKey{}); value != nil {
		if attemptID, ok := value.(string); ok {
			return attemptID
		}
	}
	return ""
}
