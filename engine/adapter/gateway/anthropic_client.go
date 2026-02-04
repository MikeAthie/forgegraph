package gateway

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"net/http"
	"time"

	"github.com/forgegraph/engine/adapter/executor"
)

type AnthropicClient struct {
	apiKey     string
	baseURL    string
	httpClient *http.Client
}

type anthropicMessage struct {
	Role    string `json:"role"`
	Content string `json:"content"`
}

type anthropicRequest struct {
	Model       string             `json:"model"`
	MaxTokens   int                `json:"max_tokens"`
	Messages    []anthropicMessage `json:"messages"`
	System      string             `json:"system,omitempty"`
	Temperature float64            `json:"temperature,omitempty"`
}

type anthropicResponse struct {
	Content []struct {
		Type string `json:"type"`
		Text string `json:"text"`
	} `json:"content"`
	Model string `json:"model"`
	Usage struct {
		InputTokens  int `json:"input_tokens"`
		OutputTokens int `json:"output_tokens"`
	} `json:"usage"`
	Error *struct {
		Message string `json:"message"`
	} `json:"error,omitempty"`
}

// NewAnthropicClientWithKey creates a new Anthropic client with a specific API key.
func NewAnthropicClientWithKey(apiKey string) *AnthropicClient {
	return &AnthropicClient{
		apiKey:  apiKey,
		baseURL: "https://api.anthropic.com/v1",
		httpClient: &http.Client{
			Timeout: 120 * time.Second,
		},
	}
}

// Complete sends a prompt to the Anthropic Messages API and returns the response.
func (c *AnthropicClient) Complete(ctx context.Context, request *executor.LLMRequest) (*executor.LLMResponse, error) {
	messages := make([]anthropicMessage, 0, 2)
	if len(request.Messages) > 0 {
		for _, msg := range request.Messages {
			messages = append(messages, anthropicMessage{Role: msg.Role, Content: msg.Content})
		}
	} else {
		messages = append(messages, anthropicMessage{Role: "user", Content: request.Prompt})
	}

	payload := anthropicRequest{
		Model:       request.Model,
		MaxTokens:   request.MaxTokens,
		Messages:    messages,
		System:      request.SystemPrompt,
		Temperature: request.Temperature,
	}

	body, err := json.Marshal(payload)
	if err != nil {
		return nil, fmt.Errorf("marshal request: %w", err)
	}

	req, err := http.NewRequestWithContext(ctx, http.MethodPost, c.baseURL+"/messages", bytes.NewReader(body))
	if err != nil {
		return nil, fmt.Errorf("create request: %w", err)
	}
	req.Header.Set("Content-Type", "application/json")
	req.Header.Set("x-api-key", c.apiKey)
	req.Header.Set("anthropic-version", "2023-06-01")

	resp, err := c.httpClient.Do(req)
	if err != nil {
		return nil, fmt.Errorf("request failed: %w", err)
	}
	defer resp.Body.Close()

	if resp.StatusCode >= 400 {
		return nil, fmt.Errorf("anthropic error: status %d", resp.StatusCode)
	}

	var parsed anthropicResponse
	if err := json.NewDecoder(resp.Body).Decode(&parsed); err != nil {
		return nil, fmt.Errorf("decode response: %w", err)
	}
	if parsed.Error != nil {
		return nil, fmt.Errorf("anthropic error: %s", parsed.Error.Message)
	}

	content := ""
	if len(parsed.Content) > 0 {
		content = parsed.Content[0].Text
	}

	usage := &executor.LLMUsage{
		PromptTokens:     parsed.Usage.InputTokens,
		CompletionTokens: parsed.Usage.OutputTokens,
		TotalTokens:      parsed.Usage.InputTokens + parsed.Usage.OutputTokens,
	}

	return &executor.LLMResponse{
		Content: content,
		Model:   parsed.Model,
		Usage:   usage,
	}, nil
}
