package executor

import (
	"context"
	"encoding/json"
	"fmt"
	"log"
	"strings"
	"time"

	"github.com/forgegraph/engine/application/port"
	"github.com/forgegraph/engine/domain"
	"github.com/forgegraph/engine/domain/entity"
	"github.com/forgegraph/engine/domain/service"
	"github.com/forgegraph/engine/domain/value"
)

// LLMClient defines the interface for LLM API calls.
// Implementations can use OpenAI, Anthropic, or other providers.
type LLMClient interface {
	// Complete sends a prompt to the LLM and returns the response.
	Complete(ctx context.Context, request *LLMRequest) (*LLMResponse, error)
}

// LLMRequest represents a completion request to an LLM
type LLMRequest struct {
	// Prompt is the text prompt to send
	Prompt string

	// Provider is the LLM provider (e.g., "openai", "anthropic")
	Provider string

	// Model is the model identifier (e.g., "gpt-4", "claude-3-opus")
	Model string

	// Temperature controls randomness (0.0-1.0)
	Temperature float64

	// MaxTokens limits the response length
	MaxTokens int

	// SystemPrompt is an optional system message
	SystemPrompt string

	// Messages is for chat-style APIs (optional, overrides Prompt)
	Messages []LLMMessage

	// CredentialID is the control-plane credential identifier (optional)
	CredentialID string

	// TenantID identifies the tenant for credential resolution (optional)
	TenantID string

	// APIKey is an optional direct key override (rare; prefer CredentialID)
	APIKey string
}

// LLMMessage represents a single message in a chat conversation
type LLMMessage struct {
	Role    string // "system", "user", "assistant"
	Content string
}

// LLMResponse represents the response from an LLM
type LLMResponse struct {
	// Content is the generated text
	Content string

	// Model is the model that generated the response
	Model string

	// Usage contains token usage information
	Usage *LLMUsage

	// FinishReason indicates why generation stopped
	FinishReason string
}

// LLMUsage tracks token usage
type LLMUsage struct {
	PromptTokens     int
	CompletionTokens int
	TotalTokens      int
}

// PromptExecutor handles prompt nodes that call LLMs.
type PromptExecutor struct {
	client LLMClient
}

// NewPromptExecutor creates a new prompt executor with the given LLM client
func NewPromptExecutor(client LLMClient) *PromptExecutor {
	return &PromptExecutor{
		client: client,
	}
}

// NodeType returns the node type this executor handles
func (e *PromptExecutor) NodeType() string {
	return string(value.NodeTypePrompt)
}

// Execute sends a prompt to the LLM and returns the response.
//
// Config options:
//   - prompt_template: string - The prompt template with {{key}} placeholders
//   - system_prompt: string - Optional system prompt
//   - model: string - The model to use (e.g., "gpt-4", "claude-3-opus")
//   - temperature: float - Temperature (0.0-1.0). Default: 0.7
//   - max_tokens: int - Maximum response tokens. Default: 1000
//   - prompt_id: string - Reference to a prompt in the prompt library (future)
//
// Output:
//   - prompt: string - The final prompt sent (after substitution)
//   - response: string - The LLM response
//   - model: string - The model used
//   - usage: object - Token usage (if available)
func (e *PromptExecutor) Execute(ctx context.Context, node *entity.Node, state *entity.State) (*port.NodeExecutionResult, error) {
	if e.client == nil {
		return port.NewErrorResult(domain.NewValidationError("client", "prompt executor requires LLM client")), nil
	}

	runCtx := port.RunContextFrom(ctx)

	// Get prompt template (required)
	promptTemplate, ok := node.Config["prompt_template"].(string)
	if !ok || promptTemplate == "" {
		return port.NewErrorResult(domain.NewValidationError("prompt_template", "prompt node requires prompt_template")), nil
	}

	// Substitute variables in prompt
	basePrompt := SubstituteTemplate(promptTemplate, state)
	prompt := basePrompt

	var vectorMemories []port.MemoryChunk
	if runCtx != nil && runCtx.MemoryConfig != nil && runCtx.MemoryConfig.Tier3.Enabled && runCtx.MemoryRetriever != nil {
		tenantID := port.TenantIDFrom(ctx)
		if tenantID != "" {
			req := port.MemoryRetrieveRequest{
				TenantID:       tenantID,
				Query:          basePrompt,
				TopK:           runCtx.MemoryConfig.Tier3.TopK,
				Threshold:      runCtx.MemoryConfig.Tier3.Threshold,
				RecencyWeight:  runCtx.MemoryConfig.Tier3.RecencyWeight,
				EmbeddingModel: runCtx.MemoryConfig.Tier3.EmbeddingModel,
			}
			retrieveCtx, cancel := context.WithTimeout(ctx, 100*time.Millisecond)
			response, err := runCtx.MemoryRetriever.Retrieve(retrieveCtx, req)
			cancel()
			if err != nil {
				log.Printf("memory_retrieve_failed: %v", err)
			} else {
				vectorMemories = response.Chunks
			}
		}
	}

	shouldAugment := (runCtx != nil &&
		runCtx.MemoryConfig != nil &&
		runCtx.MemoryConfig.Tier1.AutoPrepend &&
		runCtx.MemoryBuffer != nil) || len(vectorMemories) > 0
	if shouldAugment {
		var buffer *entity.MessageBuffer
		var summary *entity.Summary
		if runCtx != nil {
			buffer = runCtx.MemoryBuffer
			summary = runCtx.CurrentSummary
		}
		prompt = buildPromptWithMemory(basePrompt, buffer, summary, vectorMemories)
	}

	// Get optional system prompt
	systemPrompt, _ := node.Config["system_prompt"].(string)
	if systemPrompt != "" {
		systemPrompt = SubstituteTemplate(systemPrompt, state)
	}

	// Get model (default based on provider)
	model, _ := node.Config["model"].(string)

	// Get provider (default: openai if no credential is supplied)
	provider, _ := node.Config["provider"].(string)
	if provider != "" {
		provider = strings.ToLower(provider)
	}

	// Get credential id (optional)
	credentialID, _ := node.Config["credential_id"].(string)
	if provider == "" && credentialID == "" {
		provider = "openai"
	}

	if model == "" {
		if provider == "anthropic" {
			model = "claude-3-sonnet"
		} else {
			model = "gpt-4"
		}
	}

	if runCtx != nil && runCtx.Policy != nil {
		if len(runCtx.Policy.AllowedProviders) > 0 {
			allowed := false
			for _, allowedProvider := range runCtx.Policy.AllowedProviders {
				if provider == allowedProvider {
					allowed = true
					break
				}
			}
			if !allowed {
				return port.NewErrorResult(
					domain.NewValidationError("provider", "provider blocked by policy"),
				), nil
			}
		}

		if len(runCtx.Policy.AllowedModels) > 0 {
			allowed := false
			for _, allowedModel := range runCtx.Policy.AllowedModels {
				if model == allowedModel {
					allowed = true
					break
				}
			}
			if !allowed {
				return port.NewErrorResult(
					domain.NewValidationError("model", "model blocked by policy"),
				), nil
			}
		}
	}

	// Get temperature (default: 0.7)
	temperature := 0.7
	if temp, ok := node.Config["temperature"].(float64); ok {
		temperature = temp
	}

	// Get max_tokens (default: 1000)
	maxTokens := 1000
	if mt, ok := node.Config["max_tokens"].(float64); ok {
		maxTokens = int(mt)
	} else if mt, ok := node.Config["max_tokens"].(int); ok {
		maxTokens = mt
	}

	// Build LLM request
	request := &LLMRequest{
		Prompt:       prompt,
		Provider:     provider,
		Model:        model,
		Temperature:  temperature,
		MaxTokens:    maxTokens,
		SystemPrompt: systemPrompt,
		CredentialID: credentialID,
		TenantID:     port.TenantIDFrom(ctx),
	}

	// Call LLM
	response, err := e.client.Complete(ctx, request)
	if err != nil {
		// Network/API errors are typically retryable
		return port.NewErrorResult(domain.NewRetryableError(fmt.Errorf("LLM call failed: %w", err), "LLM API error")), nil
	}

	// Capture messages in buffer
	if runCtx != nil && runCtx.MemoryConfig != nil && runCtx.MemoryConfig.Tier1.Enabled && runCtx.MemoryBuffer != nil {
		runCtx.MemoryBuffer.Push(entity.Message{
			Role:    "user",
			Content: basePrompt,
			NodeID:  node.ID,
		})
		runCtx.MemoryBuffer.Push(entity.Message{
			Role:    "assistant",
			Content: response.Content,
			NodeID:  node.ID,
		})
		if runCtx.TrackMessage != nil {
			runCtx.TrackMessage(2)
		}
	}

	// Build output
	output := map[string]any{
		"prompt":   prompt,
		"response": response.Content,
		"model":    response.Model,
		"provider": provider,
	}

	if response.Usage != nil {
		output["usage"] = map[string]any{
			"prompt_tokens":     response.Usage.PromptTokens,
			"completion_tokens": response.Usage.CompletionTokens,
			"total_tokens":      response.Usage.TotalTokens,
		}
	}

	if response.FinishReason != "" {
		output["finish_reason"] = response.FinishReason
	}

	if schemaRaw, ok := node.Config["output_schema"].(map[string]any); ok {
		mode := strings.ToLower(node.GetConfigString("schema_mode"))
		if mode == "" {
			mode = strings.ToLower(node.GetConfigString("validation_mode"))
		}
		if mode == "" {
			mode = "strict"
		}

		target := any(output)
		targetMode := strings.ToLower(node.GetConfigString("output_schema_target"))
		if targetMode == "" {
			targetMode = "response"
		}
		if targetMode == "response" {
			target = response.Content
			if schemaType, ok := schemaRaw["type"].(string); ok && (schemaType == "object" || schemaType == "array") {
				trimmed := strings.TrimSpace(response.Content)
				if strings.HasPrefix(trimmed, "{") || strings.HasPrefix(trimmed, "[") {
					var parsed any
					if err := json.Unmarshal([]byte(trimmed), &parsed); err == nil {
						target = parsed
					}
				}
			}
		}

		validator, err := service.CompileSchema(schemaRaw)
		if err != nil {
			return port.NewErrorResult(domain.NewValidationError("output_schema", err.Error())), nil
		}

		issues, err := validator.Validate(target)
		if err != nil {
			return port.NewErrorResult(domain.NewValidationError("output_schema", err.Error())), nil
		}
		if len(issues) > 0 {
			if mode == "warn" {
				output["schema_errors"] = issues
			} else {
				return port.NewErrorResult(domain.NewValidationError("output_schema", fmt.Sprintf("prompt output invalid: %v", issues[0]["message"]))), nil
			}
		}
	}

	return port.NewSuccessResult(output), nil
}

func buildPromptWithMemory(
	basePrompt string,
	buffer *entity.MessageBuffer,
	summary *entity.Summary,
	vectorMemories []port.MemoryChunk,
) string {
	if buffer == nil && summary == nil {
		if len(vectorMemories) == 0 {
			return basePrompt
		}
	}

	var messages []entity.Message
	if buffer != nil {
		messages = buffer.GetAll()
	}
	if len(messages) == 0 && (summary == nil || strings.TrimSpace(summary.Content) == "") && len(vectorMemories) == 0 {
		return basePrompt
	}

	var sb strings.Builder
	if summary != nil && strings.TrimSpace(summary.Content) != "" {
		sb.WriteString("Summary of earlier conversation:\n")
		sb.WriteString(strings.TrimSpace(summary.Content))
		sb.WriteString("\n\n")
		if len(summary.FactsExtracted) > 0 {
			sb.WriteString("Key facts:\n")
			for _, fact := range summary.FactsExtracted {
				if fact.Key == "" && fact.Value == "" {
					continue
				}
				sb.WriteString(fmt.Sprintf("- %s: %s\n", fact.Key, fact.Value))
			}
			sb.WriteString("\n")
		}
	}
	if len(messages) > 0 {
		sb.WriteString("Recent messages:\n")
		for _, msg := range messages {
			role := strings.Title(msg.Role)
			sb.WriteString(fmt.Sprintf("%s: %s\n", role, msg.Content))
		}
		sb.WriteString("\n")
	}
	if len(vectorMemories) > 0 {
		sb.WriteString("Relevant memories:\n")
		for _, memory := range vectorMemories {
			content := strings.TrimSpace(memory.Content)
			if content == "" {
				continue
			}
			sb.WriteString(fmt.Sprintf("- %s\n", content))
		}
		sb.WriteString("\n")
	}
	sb.WriteString("Current input:\n")
	sb.WriteString(basePrompt)
	return sb.String()
}
