package executor

import (
	"context"
	"errors"
	"strings"
	"testing"
	"time"

	"github.com/forgegraph/engine/application/port"
	"github.com/forgegraph/engine/domain/entity"
	"github.com/forgegraph/engine/domain/value"
)

// testMockLLMClient is a simple mock for testing
type testMockLLMClient struct {
	response *LLMResponse
	err      error
	received *LLMRequest
	calls    int
}

func (m *testMockLLMClient) Complete(ctx context.Context, request *LLMRequest) (*LLMResponse, error) {
	m.calls++
	m.received = request
	if m.err != nil {
		return nil, m.err
	}
	return m.response, nil
}

type testMemoryRetriever struct {
	lastRequest *port.MemoryRetrieveRequest
	response    port.MemoryRetrieveResponse
	err         error
}

func (m *testMemoryRetriever) Retrieve(ctx context.Context, request port.MemoryRetrieveRequest) (port.MemoryRetrieveResponse, error) {
	m.lastRequest = &request
	if m.err != nil {
		return port.MemoryRetrieveResponse{}, m.err
	}
	return m.response, nil
}

func TestPromptExecutor_NodeType(t *testing.T) {
	executor := NewPromptExecutor(nil)
	if executor.NodeType() != string(value.NodeTypePrompt) {
		t.Errorf("NodeType() = %v, want %v", executor.NodeType(), string(value.NodeTypePrompt))
	}
}

func TestPromptExecutor_Execute_Success(t *testing.T) {
	mockClient := &testMockLLMClient{
		response: &LLMResponse{
			Content:      "Hello, Alice! How can I help you today?",
			Model:        "gpt-4",
			FinishReason: "stop",
			Usage: &LLMUsage{
				PromptTokens:     10,
				CompletionTokens: 8,
				TotalTokens:      18,
			},
		},
	}

	executor := NewPromptExecutor(mockClient)
	state := entity.NewState()
	state.SetVar("user_name", "Alice")

	node := &entity.Node{
		ID:   "prompt_1",
		Type: string(value.NodeTypePrompt),
		Config: map[string]any{
			"prompt_template": "Hello, my name is {{vars.user_name}}. Please greet me.",
			"model":           "gpt-4",
			"temperature":     0.5,
			"max_tokens":      100,
		},
	}

	result, err := executor.Execute(context.Background(), node, state)
	if err != nil {
		t.Fatalf("Execute() error = %v", err)
	}
	if result.Error != nil {
		t.Fatalf("result.Error = %v", result.Error)
	}

	// Check request was formed correctly
	if mockClient.received == nil {
		t.Fatal("Expected request to be received")
	}
	if mockClient.received.Prompt != "Hello, my name is Alice. Please greet me." {
		t.Errorf("Prompt = %v, want substituted prompt", mockClient.received.Prompt)
	}
	if mockClient.received.Model != "gpt-4" {
		t.Errorf("Model = %v, want 'gpt-4'", mockClient.received.Model)
	}
	if mockClient.received.Temperature != 0.5 {
		t.Errorf("Temperature = %v, want 0.5", mockClient.received.Temperature)
	}
	if mockClient.received.MaxTokens != 100 {
		t.Errorf("MaxTokens = %v, want 100", mockClient.received.MaxTokens)
	}

	// Check output
	output, ok := result.Output.(map[string]any)
	if !ok {
		t.Fatalf("Output is not map[string]any")
	}

	if output["response"] != "Hello, Alice! How can I help you today?" {
		t.Errorf("response = %v, want greeting", output["response"])
	}
	if output["model"] != "gpt-4" {
		t.Errorf("model = %v, want 'gpt-4'", output["model"])
	}

	usage, ok := output["usage"].(map[string]any)
	if !ok {
		t.Fatal("Expected usage in output")
	}
	if usage["total_tokens"] != 18 {
		t.Errorf("total_tokens = %v, want 18", usage["total_tokens"])
	}
}

func TestPromptExecutor_Execute_WithVectorMemories(t *testing.T) {
	mockClient := &testMockLLMClient{
		response: &LLMResponse{Content: "response", Model: "gpt-4"},
	}
	retriever := &testMemoryRetriever{
		response: port.MemoryRetrieveResponse{
			Chunks: []port.MemoryChunk{
				{
					Content:         "We agreed to ship on Friday.",
					Score:           0.9,
					SourceTimestamp: time.Now().UTC(),
				},
			},
		},
	}

	executor := NewPromptExecutor(mockClient)
	state := entity.NewState()

	runCtx := &port.RunContext{
		MemoryConfig: &entity.MemoryConfig{
			Tier1: entity.Tier1Config{Enabled: true, AutoPrepend: false},
			Tier3: entity.Tier3Config{Enabled: true, TopK: 5, Threshold: 0.7, RecencyWeight: 0.2},
		},
		MemoryRetriever: retriever,
	}

	ctx := port.WithRunContext(context.Background(), runCtx)
	ctx = port.WithTenantID(ctx, "tenant-1")

	node := &entity.Node{
		ID:   "prompt_1",
		Type: string(value.NodeTypePrompt),
		Config: map[string]any{
			"prompt_template": "What is our timeline?",
		},
	}

	_, err := executor.Execute(ctx, node, state)
	if err != nil {
		t.Fatalf("Execute() error = %v", err)
	}

	if retriever.lastRequest == nil || retriever.lastRequest.Query == "" {
		t.Fatal("expected memory retriever to be called with query")
	}

	prompt := mockClient.received.Prompt
	if !strings.Contains(prompt, "Relevant memories:") {
		t.Fatalf("expected relevant memories section, got prompt: %s", prompt)
	}
	if !strings.Contains(prompt, "We agreed to ship on Friday.") {
		t.Fatalf("expected memory content in prompt, got prompt: %s", prompt)
	}
}

func TestPromptExecutor_Execute_WithSystemPrompt(t *testing.T) {
	mockClient := &testMockLLMClient{
		response: &LLMResponse{
			Content: "I am Claude.",
			Model:   "claude-3-opus",
		},
	}

	executor := NewPromptExecutor(mockClient)
	state := entity.NewState()
	state.SetVar("assistant_name", "Claude")

	node := &entity.Node{
		ID:   "prompt_1",
		Type: string(value.NodeTypePrompt),
		Config: map[string]any{
			"prompt_template": "Who are you?",
			"system_prompt":   "You are {{vars.assistant_name}}, a helpful assistant.",
			"model":           "claude-3-opus",
		},
	}

	result, err := executor.Execute(context.Background(), node, state)
	if err != nil {
		t.Fatalf("Execute() error = %v", err)
	}
	if result.Error != nil {
		t.Fatalf("result.Error = %v", result.Error)
	}

	if mockClient.received.SystemPrompt != "You are Claude, a helpful assistant." {
		t.Errorf("SystemPrompt = %v, want substituted system prompt", mockClient.received.SystemPrompt)
	}
}

func TestPromptExecutor_Execute_DefaultValues(t *testing.T) {
	mockClient := &testMockLLMClient{
		response: &LLMResponse{
			Content: "Default response",
			Model:   "gpt-4",
		},
	}

	executor := NewPromptExecutor(mockClient)
	state := entity.NewState()

	node := &entity.Node{
		ID:   "prompt_1",
		Type: string(value.NodeTypePrompt),
		Config: map[string]any{
			"prompt_template": "Hello",
			// No model, temperature, or max_tokens specified
		},
	}

	result, err := executor.Execute(context.Background(), node, state)
	if err != nil {
		t.Fatalf("Execute() error = %v", err)
	}
	if result.Error != nil {
		t.Fatalf("result.Error = %v", result.Error)
	}

	// Check defaults were used
	if mockClient.received.Model != "gpt-4" {
		t.Errorf("Model = %v, want 'gpt-4' (default)", mockClient.received.Model)
	}
	if mockClient.received.Temperature != 0.7 {
		t.Errorf("Temperature = %v, want 0.7 (default)", mockClient.received.Temperature)
	}
	if mockClient.received.MaxTokens != 1000 {
		t.Errorf("MaxTokens = %v, want 1000 (default)", mockClient.received.MaxTokens)
	}
}

func TestPromptExecutor_Execute_WithSummaryAndFacts(t *testing.T) {
	mockClient := &testMockLLMClient{
		response: &LLMResponse{Content: "response", Model: "gpt-4"},
	}

	executor := NewPromptExecutor(mockClient)
	state := entity.NewState()

	buffer := entity.NewMessageBuffer(5)
	buffer.Push(entity.Message{Role: "user", Content: "Earlier question"})
	buffer.Push(entity.Message{Role: "assistant", Content: "Earlier answer"})

	runCtx := &port.RunContext{
		MemoryBuffer: buffer,
		MemoryConfig: &entity.MemoryConfig{
			Tier1: entity.Tier1Config{Enabled: true, AutoPrepend: true},
		},
		CurrentSummary: &entity.Summary{
			Content: "We discussed memory.",
			FactsExtracted: []entity.Fact{
				{Key: "owner", Value: "Ada"},
			},
		},
	}

	ctx := port.WithRunContext(context.Background(), runCtx)

	node := &entity.Node{
		ID:   "prompt_1",
		Type: string(value.NodeTypePrompt),
		Config: map[string]any{
			"prompt_template": "Current question?",
		},
	}

	_, err := executor.Execute(ctx, node, state)
	if err != nil {
		t.Fatalf("Execute() error = %v", err)
	}

	if mockClient.received == nil {
		t.Fatal("Expected request to be received")
	}

	prompt := mockClient.received.Prompt
	if !strings.Contains(prompt, "Summary of earlier conversation:") {
		t.Fatalf("expected summary section, got prompt: %s", prompt)
	}
	if !strings.Contains(prompt, "Key facts:") || !strings.Contains(prompt, "owner: Ada") {
		t.Fatalf("expected facts section, got prompt: %s", prompt)
	}
	if !strings.Contains(prompt, "Recent messages:") || !strings.Contains(prompt, "User: Earlier question") {
		t.Fatalf("expected recent messages section, got prompt: %s", prompt)
	}
	if !strings.Contains(prompt, "Current input:") || !strings.Contains(prompt, "Current question?") {
		t.Fatalf("expected current input section, got prompt: %s", prompt)
	}
}

func TestPromptExecutor_Execute_MissingTemplate(t *testing.T) {
	mockClient := &testMockLLMClient{
		response: &LLMResponse{Content: "response"},
	}

	executor := NewPromptExecutor(mockClient)
	state := entity.NewState()

	node := &entity.Node{
		ID:     "prompt_1",
		Type:   string(value.NodeTypePrompt),
		Config: map[string]any{},
	}

	result, err := executor.Execute(context.Background(), node, state)
	if err != nil {
		t.Fatalf("Execute() should not return error, got %v", err)
	}
	if result.Error == nil {
		t.Error("Expected result.Error for missing prompt_template")
	}
}

func TestPromptExecutor_Execute_MissingClient(t *testing.T) {
	executor := NewPromptExecutor(nil)
	state := entity.NewState()

	node := &entity.Node{
		ID:   "prompt_1",
		Type: string(value.NodeTypePrompt),
		Config: map[string]any{
			"prompt_template": "Hello",
		},
	}

	result, err := executor.Execute(context.Background(), node, state)
	if err != nil {
		t.Fatalf("Execute() should not return error, got %v", err)
	}
	if result.Error == nil {
		t.Error("Expected result.Error for missing LLM client")
	}
}

func TestPromptExecutor_Execute_ClientError(t *testing.T) {
	mockClient := &testMockLLMClient{
		err: errors.New("API rate limit exceeded"),
	}

	executor := NewPromptExecutor(mockClient)
	state := entity.NewState()

	node := &entity.Node{
		ID:   "prompt_1",
		Type: string(value.NodeTypePrompt),
		Config: map[string]any{
			"prompt_template": "Hello",
		},
	}

	result, err := executor.Execute(context.Background(), node, state)
	if err != nil {
		t.Fatalf("Execute() should not return error, got %v", err)
	}
	if result.Error == nil {
		t.Error("Expected result.Error for client error")
	}
}

func TestPromptExecutor_Execute_TemplateSubstitution(t *testing.T) {
	mockClient := &testMockLLMClient{
		response: &LLMResponse{Content: "response"},
	}

	executor := NewPromptExecutor(mockClient)
	state := entity.NewState()
	state.SetNodeOutput("http_1", map[string]any{
		"data": map[string]any{
			"title": "Test Article",
		},
	})
	state.SetVar("task", "summarize")

	node := &entity.Node{
		ID:   "prompt_1",
		Type: string(value.NodeTypePrompt),
		Config: map[string]any{
			"prompt_template": "Please {{vars.task}} the following: {{node.http_1.output.data.title}}",
		},
	}

	result, err := executor.Execute(context.Background(), node, state)
	if err != nil {
		t.Fatalf("Execute() error = %v", err)
	}
	if result.Error != nil {
		t.Fatalf("result.Error = %v", result.Error)
	}

	expected := "Please summarize the following: Test Article"
	if mockClient.received.Prompt != expected {
		t.Errorf("Prompt = %v, want %v", mockClient.received.Prompt, expected)
	}
}

func TestPromptExecutor_Execute_NoUsage(t *testing.T) {
	mockClient := &testMockLLMClient{
		response: &LLMResponse{
			Content: "response",
			Model:   "test",
			// No Usage
		},
	}

	executor := NewPromptExecutor(mockClient)
	state := entity.NewState()

	node := &entity.Node{
		ID:   "prompt_1",
		Type: string(value.NodeTypePrompt),
		Config: map[string]any{
			"prompt_template": "Hello",
		},
	}

	result, err := executor.Execute(context.Background(), node, state)
	if err != nil {
		t.Fatalf("Execute() error = %v", err)
	}
	if result.Error != nil {
		t.Fatalf("result.Error = %v", result.Error)
	}

	output := result.Output.(map[string]any)
	if _, hasUsage := output["usage"]; hasUsage {
		t.Error("Expected no usage in output when response has no usage")
	}
}

func TestPromptExecutor_Execute_UsesPromptCache(t *testing.T) {
	oldCache := defaultPromptCache
	defaultPromptCache = NewPromptCache(128)
	defer func() {
		defaultPromptCache = oldCache
	}()

	mockClient := &testMockLLMClient{
		response: &LLMResponse{
			Content: "cached response",
			Model:   "gpt-4",
		},
	}

	executor := NewPromptExecutor(mockClient)
	state := entity.NewState()
	node := &entity.Node{
		ID:   "prompt_cache_node",
		Type: string(value.NodeTypePrompt),
		Config: map[string]any{
			"prompt_template":    "Hello cache",
			"cache_enabled":      true,
			"cache_ttl_seconds":  60,
			"temperature":        0.2,
			"max_tokens":         50,
			"provider":           "openai",
			"model":              "gpt-4",
		},
	}

	firstResult, err := executor.Execute(context.Background(), node, state)
	if err != nil {
		t.Fatalf("first Execute() error = %v", err)
	}
	if firstResult.Error != nil {
		t.Fatalf("first result.Error = %v", firstResult.Error)
	}

	secondResult, err := executor.Execute(context.Background(), node, state)
	if err != nil {
		t.Fatalf("second Execute() error = %v", err)
	}
	if secondResult.Error != nil {
		t.Fatalf("second result.Error = %v", secondResult.Error)
	}

	if mockClient.calls != 1 {
		t.Fatalf("Complete() calls = %d, want 1 (second call should hit cache)", mockClient.calls)
	}

	firstOutput := firstResult.Output.(map[string]any)
	if _, ok := firstOutput["cached"]; ok {
		t.Fatalf("expected first response to be uncached")
	}

	secondOutput := secondResult.Output.(map[string]any)
	if cached, ok := secondOutput["cached"].(bool); !ok || !cached {
		t.Fatalf("expected second response to be marked cached")
	}
}
