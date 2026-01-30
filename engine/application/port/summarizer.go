package port

import (
	"context"

	"github.com/forgegraph/engine/domain/entity"
)

// Summarizer defines a pluggable interface for generating summaries and facts.
type Summarizer interface {
	Summarize(ctx context.Context, messages []entity.Message, opts SummarizeOptions) (*entity.Summary, error)
	ExtractFacts(ctx context.Context, messages []entity.Message) ([]entity.Fact, error)
}

// SummarizeOptions tunes how summaries are produced.
type SummarizeOptions struct {
	MaxOutputTokens int
	PreserveFacts   bool
	Model           string
}

// SummaryStore persists summaries and facts for later retrieval.
type SummaryStore interface {
	StoreSummary(ctx context.Context, tenantID, runID string, summary *entity.Summary, ttlSeconds int) error
	StoreFacts(ctx context.Context, tenantID, runID string, facts []entity.Fact, ttlSeconds int) error
	GetSummary(ctx context.Context, tenantID, runID string) (*entity.Summary, bool, error)
	GetFact(ctx context.Context, tenantID, runID, factKey string) (*entity.Fact, bool, error)
}
