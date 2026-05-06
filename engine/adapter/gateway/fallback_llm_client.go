package gateway

import (
	"context"
	"fmt"
	"os"
	"strings"
	"time"
)

const (
	fallbackLLMModeError   = "error"
	fallbackLLMModeMock    = "mock"
	fallbackLLMModeEnabled = "fallback"
	fallbackLLMModeOff     = "off"
)

// FallbackLLMClient is a deterministic placeholder secondary provider.
// It is intentionally simple so future remote API integration can replace it
// without changing engine execution code.
type FallbackLLMClient struct {
	mode    string
	content string
}

func NewFallbackLLMClientFromEnv() *FallbackLLMClient {
	mode := strings.ToLower(strings.TrimSpace(firstEnv(
		"ENGINE_LLM_FALLBACK_MODE",
		"FORGEGRAPH_LLM_FALLBACK_MODE",
	)))
	if mode == "" {
		mode = fallbackLLMModeError
	}
	if mode == fallbackLLMModeOff {
		return nil
	}
	if mode == fallbackLLMModeEnabled {
		mode = fallbackLLMModeMock
	}
	content := strings.TrimSpace(firstEnv(
		"ENGINE_LLM_FALLBACK_CONTENT",
		"FORGEGRAPH_LLM_FALLBACK_CONTENT",
	))
	if content == "" {
		content = "LLM fallback response unavailable."
	}
	return &FallbackLLMClient{mode: mode, content: content}
}

func NewMockFallbackLLMClient(content string) *FallbackLLMClient {
	if strings.TrimSpace(content) == "" {
		content = "LLM fallback response unavailable."
	}
	return &FallbackLLMClient{mode: fallbackLLMModeMock, content: content}
}

func NewErrorFallbackLLMClient() *FallbackLLMClient {
	return &FallbackLLMClient{mode: fallbackLLMModeError}
}

func (c *FallbackLLMClient) ProviderName() string {
	return "fallback"
}

func (c *FallbackLLMClient) Generate(ctx context.Context, req LLMRequest) (LLMResponse, error) {
	start := time.Now()
	select {
	case <-ctx.Done():
		err := newLLMError(LLMErrorTimeout, "fallback", "llm_gateway_fallback_timeout", "fallback llm interrupted", ctx.Err(), nil)
		response := failedLLMResponse("fallback", time.Since(start), err)
		response.LLMMode = req.LLMMode
		response.CredentialSource = LLMModeManaged
		return response, err
	default:
	}

	if c == nil || c.mode != fallbackLLMModeMock {
		err := newLLMError(
			LLMErrorUnavailable,
			"fallback",
			"llm_gateway_fallback_unavailable",
			"fallback llm unavailable",
			fmt.Errorf("fallback provider is not configured"),
			map[string]any{
				"run_id":  req.Metadata["run_id"],
				"node_id": req.Metadata["node_id"],
			},
		)
		response := failedLLMResponse("fallback", time.Since(start), err)
		response.LLMMode = req.LLMMode
		response.CredentialSource = LLMModeManaged
		return response, err
	}

	if req.OnChunk != nil && strings.TrimSpace(c.content) != "" {
		req.OnChunk(c.content)
	}
	return LLMResponse{
		Status:           LLMStatusSuccess,
		Content:          c.content,
		Provider:         "fallback",
		LLMMode:          req.LLMMode,
		CredentialSource: LLMModeManaged,
		LatencyMS:        int64(time.Since(start) / time.Millisecond),
		FallbackUsed:     true,
		Model:            req.Model,
	}, nil
}

func firstEnv(keys ...string) string {
	for _, key := range keys {
		if value := os.Getenv(key); strings.TrimSpace(value) != "" {
			return value
		}
	}
	return ""
}
