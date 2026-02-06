package gateway

import (
	"context"
	"fmt"
	"strings"

	"github.com/forgegraph/engine/adapter/executor"
	"github.com/forgegraph/engine/application/port"
)

// MultiProviderClient routes LLM requests to provider-specific clients.
type MultiProviderClient struct {
	resolver          CredentialResolver
	fallbackOpenAIKey string
}

// NewMultiProviderClient creates a new multi-provider client.
func NewMultiProviderClient(resolver CredentialResolver, fallbackOpenAIKey string) *MultiProviderClient {
	return &MultiProviderClient{resolver: resolver, fallbackOpenAIKey: fallbackOpenAIKey}
}

// Complete routes the request based on provider and credential info.
func (c *MultiProviderClient) Complete(ctx context.Context, request *executor.LLMRequest) (*executor.LLMResponse, error) {
	provider := strings.ToLower(request.Provider)

	apiKey := request.APIKey
	if apiKey == "" && request.CredentialID != "" && c.resolver != nil {
		tenantID := request.TenantID
		if tenantID == "" {
			tenantID = port.TenantIDFrom(ctx)
		}
		resolvedProvider, resolvedKey, err := c.resolver.Resolve(ctx, request.CredentialID, tenantID)
		if err != nil {
			return nil, err
		}
		if resolvedProvider != "" {
			resolvedProvider = strings.ToLower(resolvedProvider)
			if provider == "" {
				provider = resolvedProvider
			} else if provider != resolvedProvider {
				return nil, fmt.Errorf("credential provider mismatch: expected %s, got %s", provider, resolvedProvider)
			}
		}
		apiKey = resolvedKey
	}

	if provider == "" {
		provider = "openai"
	}

	switch provider {
	case "openai":
		if apiKey == "" {
			apiKey = c.fallbackOpenAIKey
		}
		if apiKey == "" {
			return nil, fmt.Errorf("openai api key missing")
		}
		client := NewOpenAIClientWithKey(apiKey)
		return client.Complete(ctx, request)
	case "anthropic":
		if apiKey == "" {
			return nil, fmt.Errorf("anthropic api key missing")
		}
		client := NewAnthropicClientWithKey(apiKey)
		return client.Complete(ctx, request)
	default:
		return nil, fmt.Errorf("unsupported provider: %s", provider)
	}
}

// StreamComplete routes streaming requests to provider-specific clients when available.
func (c *MultiProviderClient) StreamComplete(
	ctx context.Context,
	request *executor.LLMRequest,
	onChunk func(string),
) (*executor.LLMResponse, error) {
	provider := strings.ToLower(request.Provider)

	apiKey := request.APIKey
	if apiKey == "" && request.CredentialID != "" && c.resolver != nil {
		tenantID := request.TenantID
		if tenantID == "" {
			tenantID = port.TenantIDFrom(ctx)
		}
		resolvedProvider, resolvedKey, err := c.resolver.Resolve(ctx, request.CredentialID, tenantID)
		if err != nil {
			return nil, err
		}
		if resolvedProvider != "" {
			resolvedProvider = strings.ToLower(resolvedProvider)
			if provider == "" {
				provider = resolvedProvider
			} else if provider != resolvedProvider {
				return nil, fmt.Errorf("credential provider mismatch: expected %s, got %s", provider, resolvedProvider)
			}
		}
		apiKey = resolvedKey
	}

	if provider == "" {
		provider = "openai"
	}

	switch provider {
	case "openai":
		if apiKey == "" {
			apiKey = c.fallbackOpenAIKey
		}
		if apiKey == "" {
			return nil, fmt.Errorf("openai api key missing")
		}
		client := NewOpenAIClientWithKey(apiKey)
		return client.StreamComplete(ctx, request, onChunk)
	case "anthropic":
		if apiKey == "" {
			return nil, fmt.Errorf("anthropic api key missing")
		}
		client := NewAnthropicClientWithKey(apiKey)
		return client.StreamComplete(ctx, request, onChunk)
	default:
		return nil, fmt.Errorf("unsupported provider: %s", provider)
	}
}
