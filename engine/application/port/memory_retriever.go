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

// Observation represents a curated memory observation returned from the memory service.
type Observation struct {
	ID             string
	TenantID       string
	GraphID        string
	RunID          string
	SessionID      string
	AgentID        string
	Type           string
	Title          string
	Content        string
	Scope          string
	TopicKey       string
	ToolName       string
	RevisionCount  int
	DuplicateCount int
	LastSeenAt     time.Time
	CreatedAt      time.Time
	UpdatedAt      time.Time
	DeletedAt      *time.Time
	IsDeleted      bool
}

// ObservationSaveRequest creates or updates a curated observation.
type ObservationSaveRequest struct {
	TenantID      string
	ObservationID string
	GraphID       string
	RunID         string
	SessionID     string
	AgentID       string
	Type          string
	Title         string
	Content       string
	Scope         string
	TopicKey      string
	ToolName      string
	Dedupe        *bool
	UpdateTopic   *bool
}

// ObservationSearchRequest searches curated observations within a runtime scope.
type ObservationSearchRequest struct {
	TenantID       string
	Query          string
	GraphID        string
	RunID          string
	SessionID      string
	AgentID        string
	Scope          string
	Type           string
	TopicKey       string
	Limit          int
	IncludeDeleted bool
}

// ObservationContextRequest retrieves context-ready curated observations.
type ObservationContextRequest struct {
	TenantID  string
	GraphID   string
	RunID     string
	SessionID string
	AgentID   string
	Query     string
	Limit     int
}

// ObservationTimelineRequest retrieves recent curated observations for a scope.
type ObservationTimelineRequest struct {
	TenantID       string
	GraphID        string
	RunID          string
	SessionID      string
	AgentID        string
	Scope          string
	Limit          int
	IncludeDeleted bool
}

// ObservationContextResponse includes observations plus retrieval metadata.
type ObservationContextResponse struct {
	Observations []Observation
	Degraded     bool
	Strategies   []string
}

// ObservationMemoryClient provides curated-memory operations for runtime nodes.
type ObservationMemoryClient interface {
	SaveObservation(ctx context.Context, request ObservationSaveRequest) (Observation, error)
	SearchObservations(ctx context.Context, request ObservationSearchRequest) ([]Observation, error)
	GetContext(ctx context.Context, request ObservationContextRequest) (ObservationContextResponse, error)
	GetTimeline(ctx context.Context, request ObservationTimelineRequest) ([]Observation, error)
}
