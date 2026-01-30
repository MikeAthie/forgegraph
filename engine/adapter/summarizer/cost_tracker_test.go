package summarizer

import "testing"

import "github.com/forgegraph/engine/adapter/executor"

func TestCostTracker_CalculateCost(t *testing.T) {
	tracker := NewCostTracker(nil)
	usage := &executor.LLMUsage{
		PromptTokens:     1000,
		CompletionTokens: 2000,
		TotalTokens:      3000,
	}

	cost := tracker.CalculateCost("claude-haiku", usage)
	expected := 0.00275
	if diff := cost - expected; diff < -1e-9 || diff > 1e-9 {
		t.Fatalf("cost = %f, want %f", cost, expected)
	}
}
