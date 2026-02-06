// Package gateway contains adapter implementations for external services.
package gateway

import (
	"context"
	"fmt"
	"time"

	"github.com/forgegraph/engine/adapter/executor"
)

// MockLLMClient is a mock implementation of LLMClient for testing.
// It can be configured to return specific responses or simulate errors.
type MockLLMClient struct {
	// DefaultResponse is returned when no specific response is configured
	DefaultResponse string

	// Responses maps prompt substrings to specific responses
	Responses map[string]string

	// Error causes all calls to return this error
	Error error

	// Delay simulates network latency
	Delay time.Duration

	// CallCount tracks how many times Complete was called
	CallCount int

	// LastRequest stores the most recent request
	LastRequest *executor.LLMRequest

	// AllRequests stores all requests made
	AllRequests []*executor.LLMRequest
}

// NewMockLLMClient creates a new mock LLM client with a default response
func NewMockLLMClient(defaultResponse string) *MockLLMClient {
	return &MockLLMClient{
		DefaultResponse: defaultResponse,
		Responses:       make(map[string]string),
		AllRequests:     make([]*executor.LLMRequest, 0),
	}
}

// WithResponse configures a specific response for prompts containing the given substring
func (m *MockLLMClient) WithResponse(promptContains, response string) *MockLLMClient {
	m.Responses[promptContains] = response
	return m
}

// WithError configures the client to return an error
func (m *MockLLMClient) WithError(err error) *MockLLMClient {
	m.Error = err
	return m
}

// WithDelay configures a delay to simulate network latency
func (m *MockLLMClient) WithDelay(d time.Duration) *MockLLMClient {
	m.Delay = d
	return m
}

// Complete implements LLMClient.Complete
func (m *MockLLMClient) Complete(ctx context.Context, request *executor.LLMRequest) (*executor.LLMResponse, error) {
	m.CallCount++
	m.LastRequest = request
	m.AllRequests = append(m.AllRequests, request)

	// Check for cancellation
	select {
	case <-ctx.Done():
		return nil, ctx.Err()
	default:
	}

	// Simulate delay
	if m.Delay > 0 {
		select {
		case <-time.After(m.Delay):
		case <-ctx.Done():
			return nil, ctx.Err()
		}
	}

	// Return error if configured
	if m.Error != nil {
		return nil, m.Error
	}

	// Find matching response
	response := m.DefaultResponse
	for substring, resp := range m.Responses {
		if containsString(request.Prompt, substring) {
			response = resp
			break
		}
	}

	// Estimate token counts (rough approximation)
	promptTokens := len(request.Prompt) / 4
	completionTokens := len(response) / 4

	return &executor.LLMResponse{
		Content: response,
		Model:   request.Model,
		Usage: &executor.LLMUsage{
			PromptTokens:     promptTokens,
			CompletionTokens: completionTokens,
			TotalTokens:      promptTokens + completionTokens,
		},
		FinishReason: "stop",
	}, nil
}

// StreamComplete emits the full mock response as one chunk.
func (m *MockLLMClient) StreamComplete(
	ctx context.Context,
	request *executor.LLMRequest,
	onChunk func(string),
) (*executor.LLMResponse, error) {
	response, err := m.Complete(ctx, request)
	if err != nil {
		return nil, err
	}
	if onChunk != nil && response != nil && response.Content != "" {
		onChunk(response.Content)
	}
	return response, nil
}

// Reset clears call counts and request history
func (m *MockLLMClient) Reset() {
	m.CallCount = 0
	m.LastRequest = nil
	m.AllRequests = make([]*executor.LLMRequest, 0)
}

// containsString checks if a string contains a substring
func containsString(s, substr string) bool {
	return len(s) >= len(substr) && (s == substr || len(substr) == 0 ||
		(len(s) > 0 && len(substr) > 0 && findSubstring(s, substr)))
}

func findSubstring(s, substr string) bool {
	for i := 0; i <= len(s)-len(substr); i++ {
		if s[i:i+len(substr)] == substr {
			return true
		}
	}
	return false
}

// EchoLLMClient is a simple mock that echoes back the prompt with a prefix
type EchoLLMClient struct {
	Prefix string
}

// NewEchoLLMClient creates a new echo LLM client
func NewEchoLLMClient(prefix string) *EchoLLMClient {
	return &EchoLLMClient{Prefix: prefix}
}

// Complete echoes back the prompt
func (e *EchoLLMClient) Complete(ctx context.Context, request *executor.LLMRequest) (*executor.LLMResponse, error) {
	return &executor.LLMResponse{
		Content:      fmt.Sprintf("%s%s", e.Prefix, request.Prompt),
		Model:        request.Model,
		FinishReason: "stop",
	}, nil
}

// StreamComplete emits the echoed response as one chunk.
func (e *EchoLLMClient) StreamComplete(
	ctx context.Context,
	request *executor.LLMRequest,
	onChunk func(string),
) (*executor.LLMResponse, error) {
	response, err := e.Complete(ctx, request)
	if err != nil {
		return nil, err
	}
	if onChunk != nil && response != nil && response.Content != "" {
		onChunk(response.Content)
	}
	return response, nil
}

// FailingLLMClient always returns an error (useful for retry testing)
type FailingLLMClient struct {
	FailCount    int // Number of times to fail before succeeding
	currentCount int
	SuccessAfter *executor.LLMResponse
	Error        error
}

// NewFailingLLMClient creates a client that fails a specified number of times
func NewFailingLLMClient(failCount int, err error) *FailingLLMClient {
	return &FailingLLMClient{
		FailCount: failCount,
		Error:     err,
	}
}

// WithSuccessAfter configures the response to return after failures
func (f *FailingLLMClient) WithSuccessAfter(response *executor.LLMResponse) *FailingLLMClient {
	f.SuccessAfter = response
	return f
}

// Complete fails the first N times, then succeeds
func (f *FailingLLMClient) Complete(ctx context.Context, request *executor.LLMRequest) (*executor.LLMResponse, error) {
	f.currentCount++
	if f.currentCount <= f.FailCount {
		return nil, f.Error
	}

	if f.SuccessAfter != nil {
		return f.SuccessAfter, nil
	}

	return &executor.LLMResponse{
		Content:      "success after retries",
		Model:        request.Model,
		FinishReason: "stop",
	}, nil
}

// StreamComplete mirrors Complete and emits the returned content as one chunk.
func (f *FailingLLMClient) StreamComplete(
	ctx context.Context,
	request *executor.LLMRequest,
	onChunk func(string),
) (*executor.LLMResponse, error) {
	response, err := f.Complete(ctx, request)
	if err != nil {
		return nil, err
	}
	if onChunk != nil && response != nil && response.Content != "" {
		onChunk(response.Content)
	}
	return response, nil
}

// Reset resets the failure counter
func (f *FailingLLMClient) Reset() {
	f.currentCount = 0
}
