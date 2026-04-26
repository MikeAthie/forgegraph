package gateway

import (
	"context"
	"fmt"
	"strings"
	"time"

	"github.com/forgegraph/engine/adapter/executor"
)

// LocalLLMClient wraps the existing engine LLM client path as the primary
// gateway provider. "Local" means the engine's configured provider path, which
// may point at a local OpenAI-compatible model or a credential-backed API.
type LocalLLMClient struct {
	base executor.LLMClient
}

func NewLocalLLMClient(base executor.LLMClient) *LocalLLMClient {
	return &LocalLLMClient{base: base}
}

func (c *LocalLLMClient) ProviderName() string {
	return "local"
}

func (c *LocalLLMClient) Generate(ctx context.Context, req LLMRequest) (LLMResponse, error) {
	start := time.Now()
	if c == nil || c.base == nil {
		provider := strings.TrimSpace(req.Provider)
		if provider == "" {
			provider = "local"
		}
		err := newLLMError(LLMErrorUnavailable, provider, "llm_gateway_local_missing", "local llm client missing", fmt.Errorf("local llm client is nil"), nil)
		response := failedLLMResponse(provider, time.Since(start), err)
		response.LLMMode = req.LLMMode
		response.CredentialSource = req.CredentialSource
		return response, err
	}

	execReq := executorRequestFromGateway(req)
	var (
		response *executor.LLMResponse
		err      error
	)
	if req.OnChunk != nil {
		if streamer, ok := c.base.(executor.LLMStreamingClient); ok {
			response, err = streamer.StreamComplete(ctx, execReq, req.OnChunk)
		} else {
			response, err = c.base.Complete(ctx, execReq)
			if err == nil && response != nil && strings.TrimSpace(response.Content) != "" {
				req.OnChunk(response.Content)
			}
		}
	} else {
		response, err = c.base.Complete(ctx, execReq)
	}
	if err != nil {
		provider := strings.TrimSpace(req.Provider)
		if provider == "" {
			provider = "local"
		}
		normalized := normalizeProviderError(err, ctx, provider)
		response := failedLLMResponse(provider, time.Since(start), normalized)
		response.LLMMode = req.LLMMode
		response.CredentialSource = req.CredentialSource
		return response, normalized
	}
	if response == nil {
		provider := strings.TrimSpace(req.Provider)
		if provider == "" {
			provider = "local"
		}
		err := newLLMError(LLMErrorInvalidResponse, provider, "llm_gateway_empty_response", "local llm returned empty response", fmt.Errorf("empty llm response"), nil)
		failed := failedLLMResponse(provider, time.Since(start), err)
		failed.LLMMode = req.LLMMode
		failed.CredentialSource = req.CredentialSource
		return failed, err
	}
	provider := strings.TrimSpace(response.Provider)
	if provider == "" {
		provider = strings.TrimSpace(req.Provider)
	}
	if provider == "" {
		provider = "local"
	}

	return LLMResponse{
		Status:           LLMStatusSuccess,
		Content:          response.Content,
		Provider:         provider,
		LLMMode:          req.LLMMode,
		CredentialSource: req.CredentialSource,
		LatencyMS:        int64(time.Since(start) / time.Millisecond),
		Model:            response.Model,
		Usage:            response.Usage,
		FinishReason:     response.FinishReason,
		ToolCalls:        response.ToolCalls,
		StructuredData:   response.StructuredData,
	}, nil
}
