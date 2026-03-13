// Package gateway contains adapter implementations for external services.
package gateway

import (
	"bufio"
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"os"
	"strconv"
	"strings"
	"time"

	"github.com/forgegraph/engine/adapter/executor"
	"github.com/forgegraph/engine/domain"
)

// OpenAIClient implements LLMClient using the OpenAI Chat Completions API.
type OpenAIClient struct {
	apiKey     string
	baseURL    string
	httpClient *http.Client
}

// OpenAI API request/response structures
type openAIRequest struct {
	Model         string               `json:"model"`
	Messages      []openAIMessage      `json:"messages"`
	Temperature   float64              `json:"temperature,omitempty"`
	MaxTokens     int                  `json:"max_tokens,omitempty"`
	Stream        bool                 `json:"stream,omitempty"`
	StreamOptions *openAIStreamOptions `json:"stream_options,omitempty"`
}

type openAIStreamOptions struct {
	IncludeUsage bool `json:"include_usage,omitempty"`
}

type openAIMessage struct {
	Role    string `json:"role"`
	Content string `json:"content"`
}

type openAIResponse struct {
	ID      string `json:"id"`
	Object  string `json:"object"`
	Created int64  `json:"created"`
	Model   string `json:"model"`
	Choices []struct {
		Index        int           `json:"index"`
		Message      openAIMessage `json:"message"`
		FinishReason string        `json:"finish_reason"`
	} `json:"choices"`
	Usage struct {
		PromptTokens     int `json:"prompt_tokens"`
		CompletionTokens int `json:"completion_tokens"`
		TotalTokens      int `json:"total_tokens"`
	} `json:"usage"`
	Error *openAIError `json:"error,omitempty"`
}

type openAIStreamResponse struct {
	ID      string `json:"id"`
	Model   string `json:"model"`
	Choices []struct {
		Index int `json:"index"`
		Delta struct {
			Content string `json:"content"`
		} `json:"delta"`
		FinishReason string `json:"finish_reason"`
	} `json:"choices"`
	Usage *struct {
		PromptTokens     int `json:"prompt_tokens"`
		CompletionTokens int `json:"completion_tokens"`
		TotalTokens      int `json:"total_tokens"`
	} `json:"usage,omitempty"`
	Error *openAIError `json:"error,omitempty"`
}

type openAIError struct {
	Message string `json:"message"`
	Type    string `json:"type"`
	Code    string `json:"code"`
}

func resolveOpenAIBaseURL() string {
	for _, key := range []string{"OPENAI_BASE_URL", "OPENAI_API_BASE_URL"} {
		value := strings.TrimSpace(os.Getenv(key))
		if value != "" {
			return strings.TrimRight(value, "/")
		}
	}
	return "https://api.openai.com/v1"
}

// NewOpenAIClient creates a new OpenAI client.
// It reads the API key from the OPENAI_API_KEY environment variable.
func NewOpenAIClient() (*OpenAIClient, error) {
	apiKey := os.Getenv("OPENAI_API_KEY")
	if apiKey == "" {
		return nil, fmt.Errorf("OPENAI_API_KEY environment variable is not set")
	}

	return &OpenAIClient{
		apiKey:  apiKey,
		baseURL: resolveOpenAIBaseURL(),
		httpClient: &http.Client{
			Timeout: 120 * time.Second, // LLM calls can be slow
		},
	}, nil
}

// NewOpenAIClientWithKey creates a new OpenAI client with a specific API key.
func NewOpenAIClientWithKey(apiKey string) *OpenAIClient {
	return &OpenAIClient{
		apiKey:  apiKey,
		baseURL: resolveOpenAIBaseURL(),
		httpClient: &http.Client{
			Timeout: 120 * time.Second,
		},
	}
}

// Complete sends a prompt to the OpenAI API and returns the response.
func (c *OpenAIClient) Complete(ctx context.Context, request *executor.LLMRequest) (*executor.LLMResponse, error) {
	// Build messages array
	messages := make([]openAIMessage, 0, 2)

	// Add system prompt if provided
	if request.SystemPrompt != "" {
		messages = append(messages, openAIMessage{
			Role:    "system",
			Content: request.SystemPrompt,
		})
	}

	// Add user prompt (either from Messages or Prompt field)
	if len(request.Messages) > 0 {
		// Use chat-style messages if provided
		for _, msg := range request.Messages {
			messages = append(messages, openAIMessage{
				Role:    msg.Role,
				Content: msg.Content,
			})
		}
	} else {
		// Use single prompt
		messages = append(messages, openAIMessage{
			Role:    "user",
			Content: request.Prompt,
		})
	}

	// Build API request
	model := request.Model
	if model == "" {
		model = "gpt-4"
	}

	apiReq := openAIRequest{
		Model:       model,
		Messages:    messages,
		Temperature: request.Temperature,
		MaxTokens:   request.MaxTokens,
	}

	// Serialize request body
	reqBody, err := json.Marshal(apiReq)
	if err != nil {
		return nil, fmt.Errorf("failed to marshal request: %w", err)
	}

	// Create HTTP request
	httpReq, err := http.NewRequestWithContext(
		ctx,
		http.MethodPost,
		c.baseURL+"/chat/completions",
		bytes.NewReader(reqBody),
	)
	if err != nil {
		return nil, fmt.Errorf("failed to create request: %w", err)
	}

	httpReq.Header.Set("Content-Type", "application/json")
	httpReq.Header.Set("Authorization", "Bearer "+c.apiKey)

	// Execute request
	resp, err := c.httpClient.Do(httpReq)
	if err != nil {
		return nil, domain.NewRetryableErrorWithDetails(
			err,
			"request failed",
			"network_error",
			0,
			map[string]any{"provider": "openai"},
		)
	}
	defer resp.Body.Close()

	// Read response body
	body, err := io.ReadAll(resp.Body)
	if err != nil {
		return nil, domain.NewRetryableErrorWithDetails(
			err,
			"failed to read response",
			"read_error",
			0,
			map[string]any{"provider": "openai"},
		)
	}

	// Parse response
	var apiResp openAIResponse
	if err := json.Unmarshal(body, &apiResp); err != nil {
		return nil, fmt.Errorf("failed to parse response: %w", err)
	}

	// Check for API errors
	if apiResp.Error != nil {
		errMsg := fmt.Sprintf("OpenAI API error: %s (type: %s, code: %s)",
			apiResp.Error.Message, apiResp.Error.Type, apiResp.Error.Code)

		// Rate limit and server errors are retryable
		if resp.StatusCode == http.StatusTooManyRequests {
			if isOpenAIQuotaExhausted(apiResp.Error.Code, apiResp.Error.Message) {
				return nil, fmt.Errorf("%s. Increase OpenAI quota/billing and retry", errMsg)
			}
			retryAfterMs := parseRetryAfterMs(resp.Header.Get("Retry-After"), time.Now())
			return nil, domain.NewRetryableErrorWithDetails(
				fmt.Errorf(errMsg),
				"rate limited",
				"rate_limited",
				retryAfterMs,
				map[string]any{
					"provider":        "openai",
					"status_code":     resp.StatusCode,
					"retry_after_ms":  retryAfterMs,
					"rate_limit_type": "throttled",
				},
			)
		}
		if resp.StatusCode >= 500 {
			return nil, domain.NewRetryableErrorWithDetails(
				fmt.Errorf(errMsg),
				"upstream server error",
				"transient_http_5xx",
				0,
				map[string]any{
					"provider":    "openai",
					"status_code": resp.StatusCode,
				},
			)
		}

		return nil, fmt.Errorf(errMsg)
	}

	// Check HTTP status
	if resp.StatusCode != http.StatusOK {
		errMsg := fmt.Sprintf("unexpected status code: %d, body: %s", resp.StatusCode, string(body))

		// Rate limit and server errors are retryable
		if resp.StatusCode == http.StatusTooManyRequests {
			if isOpenAIQuotaExhausted("", string(body)) {
				return nil, fmt.Errorf("%s. Increase OpenAI quota/billing and retry", errMsg)
			}
			retryAfterMs := parseRetryAfterMs(resp.Header.Get("Retry-After"), time.Now())
			return nil, domain.NewRetryableErrorWithDetails(
				fmt.Errorf(errMsg),
				"rate limited",
				"rate_limited",
				retryAfterMs,
				map[string]any{
					"provider":        "openai",
					"status_code":     resp.StatusCode,
					"retry_after_ms":  retryAfterMs,
					"rate_limit_type": "throttled",
				},
			)
		}
		if resp.StatusCode >= 500 {
			return nil, domain.NewRetryableErrorWithDetails(
				fmt.Errorf(errMsg),
				"upstream server error",
				"transient_http_5xx",
				0,
				map[string]any{
					"provider":    "openai",
					"status_code": resp.StatusCode,
				},
			)
		}

		return nil, fmt.Errorf(errMsg)
	}

	// Extract response content
	if len(apiResp.Choices) == 0 {
		return nil, fmt.Errorf("no choices in response")
	}

	choice := apiResp.Choices[0]

	return &executor.LLMResponse{
		Content: choice.Message.Content,
		Model:   apiResp.Model,
		Usage: &executor.LLMUsage{
			PromptTokens:     apiResp.Usage.PromptTokens,
			CompletionTokens: apiResp.Usage.CompletionTokens,
			TotalTokens:      apiResp.Usage.TotalTokens,
		},
		FinishReason: choice.FinishReason,
	}, nil
}

// StreamComplete sends a streaming completion request and emits incremental chunks.
func (c *OpenAIClient) StreamComplete(
	ctx context.Context,
	request *executor.LLMRequest,
	onChunk func(string),
) (*executor.LLMResponse, error) {
	messages := make([]openAIMessage, 0, 2)
	if request.SystemPrompt != "" {
		messages = append(messages, openAIMessage{
			Role:    "system",
			Content: request.SystemPrompt,
		})
	}
	if len(request.Messages) > 0 {
		for _, msg := range request.Messages {
			messages = append(messages, openAIMessage{
				Role:    msg.Role,
				Content: msg.Content,
			})
		}
	} else {
		messages = append(messages, openAIMessage{
			Role:    "user",
			Content: request.Prompt,
		})
	}

	model := request.Model
	if model == "" {
		model = "gpt-4"
	}

	apiReq := openAIRequest{
		Model:         model,
		Messages:      messages,
		Temperature:   request.Temperature,
		MaxTokens:     request.MaxTokens,
		Stream:        true,
		StreamOptions: &openAIStreamOptions{IncludeUsage: true},
	}

	reqBody, err := json.Marshal(apiReq)
	if err != nil {
		return nil, fmt.Errorf("failed to marshal request: %w", err)
	}

	httpReq, err := http.NewRequestWithContext(
		ctx,
		http.MethodPost,
		c.baseURL+"/chat/completions",
		bytes.NewReader(reqBody),
	)
	if err != nil {
		return nil, fmt.Errorf("failed to create request: %w", err)
	}
	httpReq.Header.Set("Content-Type", "application/json")
	httpReq.Header.Set("Authorization", "Bearer "+c.apiKey)

	resp, err := c.httpClient.Do(httpReq)
	if err != nil {
		return nil, domain.NewRetryableErrorWithDetails(
			err,
			"request failed",
			"network_error",
			0,
			map[string]any{"provider": "openai"},
		)
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		body, _ := io.ReadAll(resp.Body)
		errMsg := fmt.Sprintf("unexpected status code: %d, body: %s", resp.StatusCode, string(body))
		if resp.StatusCode == http.StatusTooManyRequests {
			if isOpenAIQuotaExhausted("", string(body)) {
				return nil, fmt.Errorf("%s. Increase OpenAI quota/billing and retry", errMsg)
			}
			retryAfterMs := parseRetryAfterMs(resp.Header.Get("Retry-After"), time.Now())
			return nil, domain.NewRetryableErrorWithDetails(
				fmt.Errorf(errMsg),
				"rate limited",
				"rate_limited",
				retryAfterMs,
				map[string]any{
					"provider":        "openai",
					"status_code":     resp.StatusCode,
					"retry_after_ms":  retryAfterMs,
					"rate_limit_type": "throttled",
				},
			)
		}
		if resp.StatusCode >= 500 {
			return nil, domain.NewRetryableErrorWithDetails(
				fmt.Errorf(errMsg),
				"upstream server error",
				"transient_http_5xx",
				0,
				map[string]any{
					"provider":    "openai",
					"status_code": resp.StatusCode,
				},
			)
		}
		return nil, fmt.Errorf(errMsg)
	}

	var content strings.Builder
	responseModel := ""
	finishReason := ""
	var usage *executor.LLMUsage

	scanner := bufio.NewScanner(resp.Body)
	scanner.Buffer(make([]byte, 0, 64*1024), 1024*1024)

	for scanner.Scan() {
		line := strings.TrimSpace(scanner.Text())
		if line == "" || strings.HasPrefix(line, ":") {
			continue
		}
		if !strings.HasPrefix(line, "data:") {
			continue
		}

		payload := strings.TrimSpace(strings.TrimPrefix(line, "data:"))
		if payload == "[DONE]" {
			break
		}

		var chunk openAIStreamResponse
		if err := json.Unmarshal([]byte(payload), &chunk); err != nil {
			return nil, fmt.Errorf("failed to parse stream chunk: %w", err)
		}
		if chunk.Error != nil {
			return nil, fmt.Errorf(
				"OpenAI API error: %s (type: %s, code: %s)",
				chunk.Error.Message,
				chunk.Error.Type,
				chunk.Error.Code,
			)
		}

		if responseModel == "" && chunk.Model != "" {
			responseModel = chunk.Model
		}

		if len(chunk.Choices) > 0 {
			delta := chunk.Choices[0].Delta.Content
			if delta != "" {
				content.WriteString(delta)
				if onChunk != nil {
					onChunk(delta)
				}
			}
			if chunk.Choices[0].FinishReason != "" {
				finishReason = chunk.Choices[0].FinishReason
			}
		}

		if chunk.Usage != nil {
			usage = &executor.LLMUsage{
				PromptTokens:     chunk.Usage.PromptTokens,
				CompletionTokens: chunk.Usage.CompletionTokens,
				TotalTokens:      chunk.Usage.TotalTokens,
			}
		}
	}

	if err := scanner.Err(); err != nil {
		return nil, fmt.Errorf("failed reading stream: %w", err)
	}

	if responseModel == "" {
		responseModel = model
	}

	return &executor.LLMResponse{
		Content:      content.String(),
		Model:        responseModel,
		Usage:        usage,
		FinishReason: finishReason,
	}, nil
}

func parseRetryAfterMs(headerValue string, now time.Time) int {
	trimmed := strings.TrimSpace(headerValue)
	if trimmed == "" {
		return 0
	}
	if seconds, err := strconv.Atoi(trimmed); err == nil {
		if seconds <= 0 {
			return 0
		}
		return seconds * 1000
	}
	retryAt, err := http.ParseTime(trimmed)
	if err != nil {
		return 0
	}
	delayMs := int(retryAt.Sub(now).Milliseconds())
	if delayMs < 0 {
		return 0
	}
	return delayMs
}

func isOpenAIQuotaExhausted(code, message string) bool {
	normalizedCode := strings.ToLower(strings.TrimSpace(code))
	normalizedMessage := strings.ToLower(strings.TrimSpace(message))
	if normalizedCode == "insufficient_quota" {
		return true
	}
	signatures := []string{
		"insufficient_quota",
		"quota exceeded",
		"quota exhausted",
		"billing",
		"payment required",
	}
	for _, signature := range signatures {
		if strings.Contains(normalizedMessage, signature) {
			return true
		}
	}
	return false
}
