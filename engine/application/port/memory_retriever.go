package port

import (
	"context"
	"time"
)

// MemoryRetrieveRequest describes a vector memory lookup.
type MemoryRetrieveRequest struct {
	TenantID       string
	Query          string
	AgentID        string
	RunID          string
	SessionID      string
	TopK           int
	Threshold      float64
	RecencyWeight  float64
	EmbeddingModel string
}

// MemoryChunk represents a retrieved memory chunk.
type MemoryChunk struct {
	Content         string
	Score           float64
	SourceTimestamp time.Time
	Metadata        map[string]any
}

// MemoryRetrieveResponse contains retrieved chunks.
type MemoryRetrieveResponse struct {
	Chunks []MemoryChunk
}

// MemoryRetriever provides vector memory retrieval for a run.
type MemoryRetriever interface {
	Retrieve(ctx context.Context, request MemoryRetrieveRequest) (MemoryRetrieveResponse, error)
}
