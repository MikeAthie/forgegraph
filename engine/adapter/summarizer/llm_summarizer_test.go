package summarizer

import (
	"context"
	"errors"
	"testing"
	"time"

	"github.com/forgegraph/engine/adapter/executor"
	"github.com/forgegraph/engine/adapter/gateway"
	"github.com/forgegraph/engine/application/port"
	"github.com/forgegraph/engine/domain"
	"github.com/forgegraph/engine/domain/entity"
)

func TestLLMSummarizer_Summarize(t *testing.T) {
	client := gateway.NewMockLLMClient(`{"summary":"Short recap","facts":[{"key":"owner","value":"Ada","confidence":0.9,"source_node_id":"node-1"}]}`)
	summarizer := NewLLMSummarizer(client, "gpt-4")

	summary, err := summarizer.Summarize(context.Background(), []entity.Message{
		{Role: "user", Content: "We should store memory."},
		{Role: "assistant", Content: "Agreed."},
	}, port.SummarizeOptions{MaxOutputTokens: 128, PreserveFacts: true})
	if err != nil {
		t.Fatalf("Summarize returned error: %v", err)
	}

	if summary.Content != "Short recap" {
		t.Fatalf("summary content = %q, want %q", summary.Content, "Short recap")
	}
	if summary.SourceCount != 2 {
		t.Fatalf("summary source count = %d, want 2", summary.SourceCount)
	}
	if len(summary.FactsExtracted) != 1 || summary.FactsExtracted[0].Key != "owner" {
		t.Fatalf("facts not parsed as expected: %#v", summary.FactsExtracted)
	}
}

func TestLLMSummarizer_ExtractFacts(t *testing.T) {
	client := gateway.NewMockLLMClient(`{"facts":[{"key":"version","value":"1.0","confidence":0.8,"source_node_id":"node-2"}]}`)
	summarizer := NewLLMSummarizer(client, "gpt-4")

	facts, err := summarizer.ExtractFacts(context.Background(), []entity.Message{
		{Role: "user", Content: "Version is 1.0"},
	})
	if err != nil {
		t.Fatalf("ExtractFacts returned error: %v", err)
	}
	if len(facts) != 1 || facts[0].Key != "version" {
		t.Fatalf("facts parsed incorrectly: %#v", facts)
	}
}

func TestLLMSummarizer_RetryableErrors(t *testing.T) {
	client := &retryClient{failCount: 2}
	summarizer := NewLLMSummarizer(client, "gpt-4")
	summarizer.maxRetries = 3
	summarizer.retryDelay = 1 * time.Millisecond

	_, err := summarizer.Summarize(context.Background(), []entity.Message{
		{Role: "user", Content: "Retry test"},
	}, port.SummarizeOptions{})
	if err != nil {
		t.Fatalf("expected retry to succeed, got error: %v", err)
	}
	if client.attempts != 3 {
		t.Fatalf("expected 3 attempts, got %d", client.attempts)
	}
}

type retryClient struct {
	attempts  int
	failCount int
}

func (r *retryClient) Complete(ctx context.Context, request *executor.LLMRequest) (*executor.LLMResponse, error) {
	r.attempts++
	if r.attempts <= r.failCount {
		return nil, domain.NewRetryableError(errors.New("temporary"), "retryable")
	}

	return &executor.LLMResponse{
		Content:      `{"summary":"ok","facts":[]}`,
		Model:        request.Model,
		FinishReason: "stop",
	}, nil
}
