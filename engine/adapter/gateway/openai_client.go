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
	"strings"
	"time"

	"github.com/forgegraph/engine/adapter/executor"
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

// NewOpenAIClient creates a new OpenAI client.
// It reads the API key from the OPENAI_API_KEY environment variable.
func NewOpenAIClient() (*OpenAIClient, error) {
	apiKey := os.Getenv("OPENAI_API_KEY")
	if apiKey == "" {
		return nil, fmt.Errorf("OPENAI_API_KEY environment variable is not set")
	}

	return &OpenAIClient{
		apiKey:  apiKey,
		baseURL: "https://api.openai.com/v1",
		httpClient: &http.Client{
			Timeout: 120 * time.Second, // LLM calls can be slow
		},
	}, nil
}

// NewOpenAIClientWithKey creates a new OpenAI client with a specific API key.
func NewOpenAIClientWithKey(apiKey string) *OpenAIClient {
	return &OpenAIClient{
		apiKey:  apiKey,
		baseURL: "https://api.openai.com/v1",
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
		return nil, fmt.Errorf("request failed: %w", err)
	}
	defer resp.Body.Close()

	// Read response body
	body, err := io.ReadAll(resp.Body)
	if err != nil {
		return nil, fmt.Errorf("failed to read response: %w", err)
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
		if resp.StatusCode == 429 || resp.StatusCode >= 500 {
			return nil, &retryableError{msg: errMsg}
		}

		return nil, fmt.Errorf(errMsg)
	}

	// Check HTTP status
	if resp.StatusCode != http.StatusOK {
		errMsg := fmt.Sprintf("unexpected status code: %d, body: %s", resp.StatusCode, string(body))

		// Rate limit and server errors are retryable
		if resp.StatusCode == 429 || resp.StatusCode >= 500 {
			return nil, &retryableError{msg: errMsg}
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
		return nil, fmt.Errorf("request failed: %w", err)
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		body, _ := io.ReadAll(resp.Body)
		errMsg := fmt.Sprintf("unexpected status code: %d, body: %s", resp.StatusCode, string(body))
		if resp.StatusCode == 429 || resp.StatusCode >= 500 {
			return nil, &retryableError{msg: errMsg}
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

// retryableError indicates an error that can be retried
type retryableError struct {
	msg string
}

func (e *retryableError) Error() string {
	return e.msg
}

// IsRetryable returns true for retryable errors
func (e *retryableError) IsRetryable() bool {
	return true
}
