// Package gateway contains adapter implementations for external services.
package gateway

import (
	"bufio"
	"bytes"
	"context"
	"encoding/json"
	"errors"
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
	apiKey      string
	baseURL     string
	provider    string
	extraHeader map[string]string
	httpClient  *http.Client
}

// OpenAI API request/response structures
type openAIRequest struct {
	Model          string                `json:"model"`
	Messages       []openAIMessage       `json:"messages"`
	Temperature    float64               `json:"temperature,omitempty"`
	MaxTokens      int                   `json:"max_tokens,omitempty"`
	Stream         bool                  `json:"stream,omitempty"`
	StreamOptions  *openAIStreamOptions  `json:"stream_options,omitempty"`
	Tools          []openAITool          `json:"tools,omitempty"`
	ToolChoice     any                   `json:"tool_choice,omitempty"`
	ResponseFormat *openAIResponseFormat `json:"response_format,omitempty"`
}

type openAIStreamOptions struct {
	IncludeUsage bool `json:"include_usage,omitempty"`
}

type openAIMessage struct {
	Role    string `json:"role"`
	Content string `json:"content"`
}

type openAIResponseMessage struct {
	Content   string           `json:"content"`
	ToolCalls []openAIToolCall `json:"tool_calls,omitempty"`
}

type openAITool struct {
	Type     string             `json:"type"`
	Function openAIFunctionTool `json:"function"`
}

type openAIFunctionTool struct {
	Name        string         `json:"name"`
	Description string         `json:"description,omitempty"`
	Parameters  map[string]any `json:"parameters"`
	Strict      bool           `json:"strict,omitempty"`
}

type openAIToolCall struct {
	ID       string                `json:"id"`
	Type     string                `json:"type"`
	Function openAIToolCallDetails `json:"function"`
}

type openAIToolCallDetails struct {
	Name      string `json:"name"`
	Arguments string `json:"arguments"`
}

type openAIResponseFormat struct {
	Type       string                    `json:"type"`
	JSONSchema *openAIResponseJSONSchema `json:"json_schema,omitempty"`
}

type openAIResponseJSONSchema struct {
	Name   string         `json:"name"`
	Schema map[string]any `json:"schema"`
	Strict bool           `json:"strict,omitempty"`
}

type openAIResponse struct {
	ID      string `json:"id"`
	Object  string `json:"object"`
	Created int64  `json:"created"`
	Model   string `json:"model"`
	Choices []struct {
		Index        int                   `json:"index"`
		Message      openAIResponseMessage `json:"message"`
		FinishReason string                `json:"finish_reason"`
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
	Code    any    `json:"code"`
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

func resolveOpenRouterBaseURL() string {
	for _, key := range []string{"OPENROUTER_API_BASE_URL", "OPENROUTER_BASE_URL"} {
		value := strings.TrimSpace(os.Getenv(key))
		if value != "" {
			return strings.TrimRight(value, "/")
		}
	}
	return "https://openrouter.ai/api/v1"
}

func resolveOpenRouterModel() string {
	for _, key := range []string{"OPENROUTER_MODEL", "OPENROUTER_TEXT_MODEL"} {
		value := strings.TrimSpace(os.Getenv(key))
		if value != "" {
			return value
		}
	}
	return "google/gemini-2.5-flash"
}

// NewOpenAIClient creates a new OpenAI client.
// It reads the API key from the OPENAI_API_KEY environment variable.
func NewOpenAIClient() (*OpenAIClient, error) {
	apiKey := os.Getenv("OPENAI_API_KEY")
	if apiKey == "" {
		return nil, fmt.Errorf("OPENAI_API_KEY environment variable is not set")
	}

	return &OpenAIClient{
		apiKey:   apiKey,
		baseURL:  resolveOpenAIBaseURL(),
		provider: "openai",
		httpClient: &http.Client{
			Timeout: 120 * time.Second, // LLM calls can be slow
		},
	}, nil
}

// NewOpenAIClientWithKey creates a new OpenAI client with a specific API key.
func NewOpenAIClientWithKey(apiKey string) *OpenAIClient {
	return &OpenAIClient{
		apiKey:   apiKey,
		baseURL:  resolveOpenAIBaseURL(),
		provider: "openai",
		httpClient: &http.Client{
			Timeout: 120 * time.Second,
		},
	}
}

// NewOpenRouterClientWithKey creates an OpenRouter client using its
// OpenAI-compatible Chat Completions endpoint.
func NewOpenRouterClientWithKey(apiKey string) *OpenAIClient {
	extraHeader := map[string]string{}
	if referer := strings.TrimSpace(os.Getenv("OPENROUTER_HTTP_REFERER")); referer != "" {
		extraHeader["HTTP-Referer"] = referer
	}
	if title := strings.TrimSpace(os.Getenv("OPENROUTER_APP_TITLE")); title != "" {
		extraHeader["X-Title"] = title
	}
	return &OpenAIClient{
		apiKey:      apiKey,
		baseURL:     resolveOpenRouterBaseURL(),
		provider:    "openrouter",
		extraHeader: extraHeader,
		httpClient: &http.Client{
			Timeout: 120 * time.Second,
		},
	}
}

func (c *OpenAIClient) providerName() string {
	if c == nil || strings.TrimSpace(c.provider) == "" {
		return "openai"
	}
	return strings.ToLower(strings.TrimSpace(c.provider))
}

func (c *OpenAIClient) defaultModel() string {
	if c.providerName() == "openrouter" {
		return resolveOpenRouterModel()
	}
	return "gpt-4"
}

func (c *OpenAIClient) applyHeaders(req *http.Request) {
	req.Header.Set("Content-Type", "application/json")
	req.Header.Set("Authorization", "Bearer "+c.apiKey)
	for key, value := range c.extraHeader {
		if strings.TrimSpace(key) != "" && strings.TrimSpace(value) != "" {
			req.Header.Set(key, value)
		}
	}
}

func (c *OpenAIClient) apiLabel() string {
	if c.providerName() == "openrouter" {
		return "OpenRouter"
	}
	return "OpenAI"
}

// Complete sends a prompt to the OpenAI API and returns the response.
func (c *OpenAIClient) Complete(ctx context.Context, request *executor.LLMRequest) (*executor.LLMResponse, error) {
	provider := c.providerName()
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
		model = c.defaultModel()
	}

	apiReq := openAIRequest{
		Model:       model,
		Messages:    messages,
		Temperature: request.Temperature,
		MaxTokens:   request.MaxTokens,
	}
	if len(request.Tools) > 0 {
		apiReq.Tools = buildOpenAITools(request.Tools)
		if toolChoice := strings.TrimSpace(request.ToolChoice); toolChoice != "" {
			if toolChoice == "required" || toolChoice == "auto" || toolChoice == "none" {
				apiReq.ToolChoice = toolChoice
			}
		}
	}
	if request.StructuredOutput != nil && len(request.StructuredOutput.Schema) > 0 {
		apiReq.ResponseFormat = &openAIResponseFormat{
			Type: "json_schema",
			JSONSchema: &openAIResponseJSONSchema{
				Name:   request.StructuredOutput.Name,
				Schema: request.StructuredOutput.Schema,
				Strict: request.StructuredOutput.Strict,
			},
		}
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

	c.applyHeaders(httpReq)

	// Execute request
	resp, err := c.httpClient.Do(httpReq)
	if err != nil {
		return nil, domain.NewRetryableErrorWithDetails(
			err,
			"request failed",
			"network_error",
			0,
			map[string]any{"provider": provider},
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
			map[string]any{"provider": provider},
		)
	}

	// Parse response
	var apiResp openAIResponse
	if err := json.Unmarshal(body, &apiResp); err != nil {
		return nil, fmt.Errorf("failed to parse response: %w", err)
	}

	// Check for API errors
	if apiResp.Error != nil {
		errorCode := openAIErrorCodeString(apiResp.Error.Code)
		errMsg := fmt.Sprintf("%s API error: %s (type: %s, code: %s)",
			c.apiLabel(), apiResp.Error.Message, apiResp.Error.Type, errorCode)

		// Rate limit and server errors are retryable
		if resp.StatusCode == http.StatusTooManyRequests {
			if isOpenAIQuotaExhausted(errorCode, apiResp.Error.Message) {
				return nil, fmt.Errorf("%s. Increase OpenAI quota/billing and retry", errMsg)
			}
			retryAfterMs := parseRetryAfterMs(resp.Header.Get("Retry-After"), time.Now())
			return nil, domain.NewRetryableErrorWithDetails(
				errors.New(errMsg),
				"rate limited",
				"rate_limited",
				retryAfterMs,
				map[string]any{
					"provider":        provider,
					"status_code":     resp.StatusCode,
					"retry_after_ms":  retryAfterMs,
					"rate_limit_type": "throttled",
				},
			)
		}
		if resp.StatusCode >= 500 {
			return nil, domain.NewRetryableErrorWithDetails(
				errors.New(errMsg),
				"upstream server error",
				"transient_http_5xx",
				0,
				map[string]any{
					"provider":    provider,
					"status_code": resp.StatusCode,
				},
			)
		}

		return nil, errors.New(errMsg)
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
				errors.New(errMsg),
				"rate limited",
				"rate_limited",
				retryAfterMs,
				map[string]any{
					"provider":        provider,
					"status_code":     resp.StatusCode,
					"retry_after_ms":  retryAfterMs,
					"rate_limit_type": "throttled",
				},
			)
		}
		if resp.StatusCode >= 500 {
			return nil, domain.NewRetryableErrorWithDetails(
				errors.New(errMsg),
				"upstream server error",
				"transient_http_5xx",
				0,
				map[string]any{
					"provider":    provider,
					"status_code": resp.StatusCode,
				},
			)
		}

		return nil, errors.New(errMsg)
	}

	// Extract response content
	if len(apiResp.Choices) == 0 {
		return nil, fmt.Errorf("no choices in response")
	}

	choice := apiResp.Choices[0]

	return &executor.LLMResponse{
		Content:          choice.Message.Content,
		Model:            apiResp.Model,
		Provider:         provider,
		LLMMode:          request.LLMMode,
		CredentialSource: request.CredentialSource,
		Usage: &executor.LLMUsage{
			PromptTokens:     apiResp.Usage.PromptTokens,
			CompletionTokens: apiResp.Usage.CompletionTokens,
			TotalTokens:      apiResp.Usage.TotalTokens,
		},
		FinishReason: choice.FinishReason,
		ToolCalls:    parseOpenAIToolCalls(choice.Message.ToolCalls),
		StructuredData: parseStructuredResponse(
			choice.Message.Content,
			request.StructuredOutput != nil,
		),
	}, nil
}

// StreamComplete sends a streaming completion request and emits incremental chunks.
func (c *OpenAIClient) StreamComplete(
	ctx context.Context,
	request *executor.LLMRequest,
	onChunk func(string),
) (*executor.LLMResponse, error) {
	provider := c.providerName()
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
		model = c.defaultModel()
	}

	apiReq := openAIRequest{
		Model:          model,
		Messages:       messages,
		Temperature:    request.Temperature,
		MaxTokens:      request.MaxTokens,
		Stream:         true,
		StreamOptions:  &openAIStreamOptions{IncludeUsage: true},
		ResponseFormat: nil,
	}
	if len(request.Tools) > 0 {
		apiReq.Tools = buildOpenAITools(request.Tools)
		if toolChoice := strings.TrimSpace(request.ToolChoice); toolChoice != "" {
			apiReq.ToolChoice = toolChoice
		}
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
	c.applyHeaders(httpReq)

	resp, err := c.httpClient.Do(httpReq)
	if err != nil {
		return nil, domain.NewRetryableErrorWithDetails(
			err,
			"request failed",
			"network_error",
			0,
			map[string]any{"provider": provider},
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
				errors.New(errMsg),
				"rate limited",
				"rate_limited",
				retryAfterMs,
				map[string]any{
					"provider":        provider,
					"status_code":     resp.StatusCode,
					"retry_after_ms":  retryAfterMs,
					"rate_limit_type": "throttled",
				},
			)
		}
		if resp.StatusCode >= 500 {
			return nil, domain.NewRetryableErrorWithDetails(
				errors.New(errMsg),
				"upstream server error",
				"transient_http_5xx",
				0,
				map[string]any{
					"provider":    provider,
					"status_code": resp.StatusCode,
				},
			)
		}
		return nil, errors.New(errMsg)
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
				"%s API error: %s (type: %s, code: %s)",
				c.apiLabel(),
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
		Content:          content.String(),
		Model:            responseModel,
		Provider:         provider,
		LLMMode:          request.LLMMode,
		CredentialSource: request.CredentialSource,
		Usage:            usage,
		FinishReason:     finishReason,
	}, nil
}

func buildOpenAITools(specs []executor.ToolSpec) []openAITool {
	tools := make([]openAITool, 0, len(specs))
	for _, spec := range specs {
		if strings.TrimSpace(spec.Name) == "" || len(spec.InputSchema) == 0 {
			continue
		}
		tools = append(tools, openAITool{
			Type: "function",
			Function: openAIFunctionTool{
				Name:        spec.Name,
				Description: spec.Description,
				Parameters:  spec.InputSchema,
				Strict:      spec.Strict,
			},
		})
	}
	return tools
}

func parseOpenAIToolCalls(calls []openAIToolCall) []executor.LLMToolCall {
	if len(calls) == 0 {
		return nil
	}
	parsed := make([]executor.LLMToolCall, 0, len(calls))
	for _, call := range calls {
		args := map[string]any{}
		if strings.TrimSpace(call.Function.Arguments) != "" {
			_ = json.Unmarshal([]byte(call.Function.Arguments), &args)
		}
		parsed = append(parsed, executor.LLMToolCall{
			ID:           call.ID,
			Name:         call.Function.Name,
			Arguments:    args,
			RawArguments: call.Function.Arguments,
		})
	}
	return parsed
}

func parseStructuredResponse(content string, requested bool) any {
	if !requested {
		return nil
	}
	trimmed := strings.TrimSpace(content)
	if trimmed == "" {
		return nil
	}
	var parsed any
	if err := json.Unmarshal([]byte(trimmed), &parsed); err != nil {
		return nil
	}
	return parsed
}

func openAIErrorCodeString(code any) string {
	switch value := code.(type) {
	case nil:
		return ""
	case string:
		return value
	case float64:
		if value == float64(int64(value)) {
			return strconv.FormatInt(int64(value), 10)
		}
		return strconv.FormatFloat(value, 'f', -1, 64)
	case int:
		return strconv.Itoa(value)
	case int64:
		return strconv.FormatInt(value, 10)
	default:
		return fmt.Sprint(value)
	}
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
