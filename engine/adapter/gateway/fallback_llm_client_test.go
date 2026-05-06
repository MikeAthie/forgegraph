package gateway

import (
	"context"
	"testing"
)

func TestFallbackLLMClientFromEnvAcceptsFallbackAlias(t *testing.T) {
	t.Setenv("ENGINE_LLM_FALLBACK_MODE", "fallback")
	t.Setenv("ENGINE_LLM_FALLBACK_CONTENT", "fallback response")

	client := NewFallbackLLMClientFromEnv()
	if client == nil {
		t.Fatal("expected fallback client")
	}

	response, err := client.Generate(context.Background(), LLMRequest{})
	if err != nil {
		t.Fatalf("Generate returned error: %v", err)
	}
	if !response.FallbackUsed {
		t.Fatal("FallbackUsed = false, want true")
	}
	if response.Content != "fallback response" {
		t.Fatalf("Content = %q, want fallback response", response.Content)
	}
}
