package executor

import (
	"context"
	"encoding/json"
	"fmt"
	"strings"

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

	// Get prompt template (required)
	promptTemplate, ok := node.Config["prompt_template"].(string)
	if !ok || promptTemplate == "" {
		return port.NewErrorResult(domain.NewValidationError("prompt_template", "prompt node requires prompt_template")), nil
	}

	// Substitute variables in prompt
	prompt := SubstituteTemplate(promptTemplate, state)

	// Get optional system prompt
	systemPrompt, _ := node.Config["system_prompt"].(string)
	if systemPrompt != "" {
		systemPrompt = SubstituteTemplate(systemPrompt, state)
	}

	// Get model (default: gpt-4)
	model, _ := node.Config["model"].(string)
	if model == "" {
		model = "gpt-4"
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
		Model:        model,
		Temperature:  temperature,
		MaxTokens:    maxTokens,
		SystemPrompt: systemPrompt,
	}

	// Call LLM
	response, err := e.client.Complete(ctx, request)
	if err != nil {
		// Network/API errors are typically retryable
		return port.NewErrorResult(domain.NewRetryableError(fmt.Errorf("LLM call failed: %w", err), "LLM API error")), nil
	}

	// Build output
	output := map[string]any{
		"prompt":   prompt,
		"response": response.Content,
		"model":    response.Model,
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
