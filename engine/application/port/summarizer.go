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
