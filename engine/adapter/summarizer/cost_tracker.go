package summarizer

import (
	"context"
	"database/sql"
	"fmt"
	"time"

	"github.com/forgegraph/engine/adapter/executor"
	"github.com/forgegraph/engine/infrastructure/metrics"
	"github.com/google/uuid"
)

// Pricing defines per-1K token pricing.
type Pricing struct {
	InputPer1K  float64
	OutputPer1K float64
}

// CostTracker records summarization usage in the shared database.
type CostTracker struct {
	db      *sql.DB
	pricing map[string]Pricing
}

// NewCostTracker creates a new tracker.
func NewCostTracker(db *sql.DB) *CostTracker {
	return &CostTracker{
		db: db,
		pricing: map[string]Pricing{
			"claude-haiku": {InputPer1K: 0.00025, OutputPer1K: 0.00125},
		},
	}
}

// RecordSummarizationUsage updates daily usage totals for a tenant.
func (c *CostTracker) RecordSummarizationUsage(ctx context.Context, tenantID, model string, usage *executor.LLMUsage) error {
	if c == nil || c.db == nil || usage == nil || tenantID == "" {
		return nil
	}

	cost := c.CalculateCost(model, usage)
	metrics.RecordSummarizationCost(model, cost)

	usageDate := time.Now().UTC().Format("2006-01-02")
	id := uuid.NewString()

	query := `
		INSERT INTO memory_usage (
			id,
			tenant_id,
			usage_date,
			summarization_prompt_tokens,
			summarization_completion_tokens,
			summarization_total_tokens,
			summarization_cost_usd,
			created_at,
			updated_at
		) VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$8)
		ON CONFLICT (tenant_id, usage_date) DO UPDATE SET
			summarization_prompt_tokens = memory_usage.summarization_prompt_tokens + EXCLUDED.summarization_prompt_tokens,
			summarization_completion_tokens = memory_usage.summarization_completion_tokens + EXCLUDED.summarization_completion_tokens,
			summarization_total_tokens = memory_usage.summarization_total_tokens + EXCLUDED.summarization_total_tokens,
			summarization_cost_usd = memory_usage.summarization_cost_usd + EXCLUDED.summarization_cost_usd,
			updated_at = EXCLUDED.updated_at
	`

	_, err := c.db.ExecContext(
		ctx,
		query,
		id,
		tenantID,
		usageDate,
		usage.PromptTokens,
		usage.CompletionTokens,
		usage.TotalTokens,
		cost,
		time.Now().UTC(),
	)
	if err != nil {
		return fmt.Errorf("record summarization usage: %w", err)
	}
	return nil
}

// CalculateCost computes cost for a usage record.
func (c *CostTracker) CalculateCost(model string, usage *executor.LLMUsage) float64 {
	if c == nil || usage == nil {
		return 0
	}
	price := c.pricing[model]
	return (float64(usage.PromptTokens)/1000.0)*price.InputPer1K +
		(float64(usage.CompletionTokens)/1000.0)*price.OutputPer1K
}
