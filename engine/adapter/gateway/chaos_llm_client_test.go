package gateway

import (
	"context"
	"errors"
	"testing"
	"time"

	"github.com/forgegraph/engine/adapter/executor"
	"github.com/forgegraph/engine/domain"
)

type stubLLMClient struct {
	completeCalls int
	streamCalls   int
	response      *executor.LLMResponse
	err           error
}

func (s *stubLLMClient) Complete(ctx context.Context, request *executor.LLMRequest) (*executor.LLMResponse, error) {
	s.completeCalls++
	return s.response, s.err
}

func (s *stubLLMClient) StreamComplete(
	ctx context.Context,
	request *executor.LLMRequest,
	onChunk func(string),
) (*executor.LLMResponse, error) {
	s.streamCalls++
	if onChunk != nil && s.response != nil && s.response.Content != "" {
		onChunk(s.response.Content)
	}
	return s.response, s.err
}

func TestNewLLMChaosClientFromEnvReturnsBaseWhenDisabled(t *testing.T) {
	t.Setenv("FORGEGRAPH_LLM_CHAOS_MODE", "")
	base := &stubLLMClient{}

	got := NewLLMChaosClientFromEnv(base)

	if got != base {
		t.Fatal("expected disabled chaos wrapper to return base client")
	}
}

func TestChaosLLMClientDelayDelegatesAfterDelay(t *testing.T) {
	client := &chaosLLMClient{
		base: &stubLLMClient{
			response: &executor.LLMResponse{Content: "ok"},
		},
		cfg: llmChaosConfig{
			Mode:  llmChaosModeDelay,
			Delay: 20 * time.Millisecond,
		},
	}

	start := time.Now()
	resp, err := client.Complete(context.Background(), &executor.LLMRequest{Provider: "openai"})
	elapsed := time.Since(start)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if resp == nil || resp.Content != "ok" {
		t.Fatalf("unexpected response: %#v", resp)
	}
	if elapsed < 20*time.Millisecond {
		t.Fatalf("expected delay >= 20ms, got %v", elapsed)
	}
}

func TestChaosLLMClientTimeoutReturnsRetryableError(t *testing.T) {
	client := &chaosLLMClient{
		base: &stubLLMClient{},
		cfg: llmChaosConfig{
			Mode:         llmChaosModeTimeout,
			ErrorMessage: "simulated timeout",
		},
	}

	_, err := client.Complete(context.Background(), &executor.LLMRequest{Provider: "openai"})
	if err == nil {
		t.Fatal("expected timeout error")
	}
	if !domain.IsRetryable(err) {
		t.Fatalf("expected retryable error, got %T", err)
	}
	if code := domain.RetryCodeFromError(err); code != "llm_chaos_timeout" {
		t.Fatalf("unexpected retry code: %s", code)
	}
}

func TestChaosLLMClientUnavailableDoesNotCallBase(t *testing.T) {
	base := &stubLLMClient{
		response: &executor.LLMResponse{Content: "unexpected"},
	}
	client := &chaosLLMClient{
		base: base,
		cfg: llmChaosConfig{
			Mode:         llmChaosModeUnavailable,
			ErrorMessage: "provider offline",
		},
	}

	_, err := client.Complete(context.Background(), &executor.LLMRequest{Provider: "openai"})
	if err == nil {
		t.Fatal("expected unavailable error")
	}
	if base.completeCalls != 0 {
		t.Fatalf("expected base client not to be called, got %d calls", base.completeCalls)
	}
	if code := domain.RetryCodeFromError(err); code != "llm_chaos_unavailable" {
		t.Fatalf("unexpected retry code: %s", code)
	}
}

func TestChaosLLMClientHangWaitsForContextCancellation(t *testing.T) {
	base := &stubLLMClient{}
	client := &chaosLLMClient{
		base: base,
		cfg: llmChaosConfig{
			Mode:         llmChaosModeHang,
			ErrorMessage: "simulated hang",
		},
	}

	ctx, cancel := context.WithTimeout(context.Background(), 20*time.Millisecond)
	defer cancel()

	start := time.Now()
	_, err := client.Complete(ctx, &executor.LLMRequest{Provider: "openai"})
	elapsed := time.Since(start)
	if err == nil {
		t.Fatal("expected hang to end with context error")
	}
	if !errors.Is(err, context.DeadlineExceeded) {
		t.Fatalf("expected deadline exceeded, got %v", err)
	}
	if elapsed < 20*time.Millisecond {
		t.Fatalf("expected hang to block until context timeout, got %v", elapsed)
	}
	if base.completeCalls != 0 {
		t.Fatalf("expected base client not to be called, got %d calls", base.completeCalls)
	}
}
