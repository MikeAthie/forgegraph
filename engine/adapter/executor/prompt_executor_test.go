package executor

import (
	"context"
	"errors"
	"strings"
	"testing"
	"time"

	"github.com/forgegraph/engine/application/port"
	"github.com/forgegraph/engine/domain"
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

type testStreamingLLMClient struct {
	response *LLMResponse
	received *LLMRequest
	chunks   []string
	calls    int
}

func (m *testStreamingLLMClient) Complete(ctx context.Context, request *LLMRequest) (*LLMResponse, error) {
	m.calls++
	m.received = request
	return m.response, nil
}

func (m *testStreamingLLMClient) StreamComplete(
	ctx context.Context,
	request *LLMRequest,
	onChunk func(string),
) (*LLMResponse, error) {
	m.calls++
	m.received = request
	for _, chunk := range m.chunks {
		if onChunk != nil {
			onChunk(chunk)
		}
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
		TenantID:  "tenant-1",
		RunID:     "run-123",
		SessionID: "session-123",
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
			"agent_id":        "agent-123",
		},
	}

	_, err := executor.Execute(ctx, node, state)
	if err != nil {
		t.Fatalf("Execute() error = %v", err)
	}

	if retriever.lastRequest == nil || retriever.lastRequest.Query == "" {
		t.Fatal("expected memory retriever to be called with query")
	}
	if retriever.lastRequest.TenantID != "tenant-1" {
		t.Fatalf("tenant_id = %q, want tenant-1", retriever.lastRequest.TenantID)
	}
	if retriever.lastRequest.RunID != "run-123" || retriever.lastRequest.SessionID != "session-123" {
		t.Fatalf("expected run/session scope in request, got %#v", retriever.lastRequest)
	}
	if retriever.lastRequest.AgentID != "agent-123" {
		t.Fatalf("agent_id = %q, want agent-123", retriever.lastRequest.AgentID)
	}

	prompt := mockClient.received.Prompt
	if !strings.Contains(prompt, "Relevant memories:") {
		t.Fatalf("expected relevant memories section, got prompt: %s", prompt)
	}
	if !strings.Contains(prompt, "We agreed to ship on Friday.") {
		t.Fatalf("expected memory content in prompt, got prompt: %s", prompt)
	}
}

func TestPromptExecutor_Execute_DisableMemoryContextSkipsAugmentationAndCapture(t *testing.T) {
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
	}

	ctx := port.WithRunContext(context.Background(), runCtx)
	node := &entity.Node{
		ID:   "prompt_no_memory",
		Type: string(value.NodeTypePrompt),
		Config: map[string]any{
			"prompt_template":        "Current question?",
			"disable_memory_context": true,
		},
	}

	_, err := executor.Execute(ctx, node, state)
	if err != nil {
		t.Fatalf("Execute() error = %v", err)
	}

	if strings.Contains(mockClient.received.Prompt, "Recent messages:") {
		t.Fatalf("expected prompt to skip memory augmentation, got: %s", mockClient.received.Prompt)
	}
	if buffer.Count() != 2 {
		t.Fatalf("expected memory buffer to remain unchanged, got %d messages", buffer.Count())
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

func TestPromptExecutor_Execute_WithExplicitCuratedContextOrdersSections(t *testing.T) {
	mockClient := &testMockLLMClient{
		response: &LLMResponse{Content: "response", Model: "gpt-4"},
	}
	retriever := &testMemoryRetriever{
		response: port.MemoryRetrieveResponse{
			Chunks: []port.MemoryChunk{
				{Content: "Semantic memory about the contract"},
			},
		},
	}

	executor := NewPromptExecutor(mockClient)
	state := entity.NewState()
	state.SetNodeOutput("obs_ctx", map[string]any{
		"observations": []any{
			map[string]any{
				"id":      "obs-1",
				"type":    "fact",
				"title":   "Contract note",
				"content": "Customer signed the agreement yesterday.",
				"scope":   "session",
			},
		},
		"degraded":   true,
		"strategies": []any{"fts", "vector_unavailable"},
	})

	buffer := entity.NewMessageBuffer(5)
	buffer.Push(entity.Message{Role: "user", Content: "Earlier question"})
	buffer.Push(entity.Message{Role: "assistant", Content: "Earlier answer"})

	runCtx := &port.RunContext{
		MemoryBuffer: buffer,
		MemoryConfig: &entity.MemoryConfig{
			Tier1: entity.Tier1Config{Enabled: true, AutoPrepend: true},
			Tier3: entity.Tier3Config{Enabled: true, TopK: 5, Threshold: 0.7, RecencyWeight: 0.2},
		},
		CurrentSummary: &entity.Summary{
			Content: "We discussed the contract timeline.",
			FactsExtracted: []entity.Fact{
				{Key: "owner", Value: "Ada"},
			},
		},
		MemoryRetriever: retriever,
	}

	ctx := port.WithRunContext(context.Background(), runCtx)
	ctx = port.WithTenantID(ctx, "tenant-1")

	node := &entity.Node{
		ID:   "prompt_1",
		Type: string(value.NodeTypePrompt),
		Config: map[string]any{
			"prompt_template":           "What should I know before replying?",
			"observation_context_paths": []any{"node.obs_ctx.output"},
		},
	}

	result, err := executor.Execute(ctx, node, state)
	if err != nil {
		t.Fatalf("Execute() error = %v", err)
	}
	if result.Error != nil {
		t.Fatalf("result.Error = %v", result.Error)
	}

	prompt := mockClient.received.Prompt
	curatedIndex := strings.Index(prompt, "Curated observations:")
	summaryIndex := strings.Index(prompt, "Summary of earlier conversation:")
	vectorIndex := strings.Index(prompt, "Relevant memories:")
	bufferIndex := strings.Index(prompt, "Recent messages:")
	currentIndex := strings.Index(prompt, "Current input:")

	if curatedIndex < 0 || summaryIndex < 0 || vectorIndex < 0 || bufferIndex < 0 || currentIndex < 0 {
		t.Fatalf("expected all memory sections in prompt, got: %s", prompt)
	}
	if !(curatedIndex < summaryIndex && summaryIndex < vectorIndex && vectorIndex < bufferIndex && bufferIndex < currentIndex) {
		t.Fatalf("unexpected section order in prompt: %s", prompt)
	}

	output := result.Output.(map[string]any)
	memoryContext, ok := output["memory_context"].(map[string]any)
	if !ok {
		t.Fatalf("expected memory_context output, got %T", output["memory_context"])
	}
	if memoryContext["curated_observation_count"] != 1 {
		t.Fatalf("curated_observation_count = %v, want 1", memoryContext["curated_observation_count"])
	}
	if memoryContext["curated_degraded"] != true {
		t.Fatalf("curated_degraded = %v, want true", memoryContext["curated_degraded"])
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

func TestPromptExecutor_Execute_PreservesRetryableDiagnostics(t *testing.T) {
	mockClient := &testMockLLMClient{
		err: domain.NewRetryableErrorWithDetails(
			errors.New("rate limited"),
			"LLM API error",
			"rate_limited",
			1500,
			map[string]any{"provider": "openai"},
		),
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
		t.Fatal("Expected result.Error for retryable client error")
	}
	if !domain.IsRetryable(result.Error) {
		t.Fatalf("Expected retryable error, got %T (%v)", result.Error, result.Error)
	}
	if got := domain.RetryAfterMsFromError(result.Error); got != 1500 {
		t.Fatalf("RetryAfterMs = %d, want 1500", got)
	}
	if code := domain.RetryCodeFromError(result.Error); code != "rate_limited" {
		t.Fatalf("RetryCode = %s, want rate_limited", code)
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

func TestPromptExecutor_Execute_StreamsChunksToContextEmitter(t *testing.T) {
	streamClient := &testStreamingLLMClient{
		response: &LLMResponse{
			Content: "Hello world",
			Model:   "gpt-4",
		},
		chunks: []string{"Hello", " ", "world"},
	}

	executor := NewPromptExecutor(streamClient)
	state := entity.NewState()
	node := &entity.Node{
		ID:   "prompt_1",
		Type: string(value.NodeTypePrompt),
		Config: map[string]any{
			"prompt_template": "Say hello",
			"stream":          true,
		},
	}

	var streamed strings.Builder
	ctx := port.WithStreamChunkEmitter(context.Background(), func(chunk string) {
		streamed.WriteString(chunk)
	})

	result, err := executor.Execute(ctx, node, state)
	if err != nil {
		t.Fatalf("Execute() error = %v", err)
	}
	if result.Error != nil {
		t.Fatalf("result.Error = %v", result.Error)
	}
	if streamed.String() != "Hello world" {
		t.Fatalf("streamed chunks = %q, want %q", streamed.String(), "Hello world")
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
			"prompt_template":   "Hello cache",
			"cache_enabled":     true,
			"cache_ttl_seconds": 60,
			"temperature":       0.2,
			"max_tokens":        50,
			"provider":          "openai",
			"model":             "gpt-4",
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

func TestPromptExecutor_Execute_BlocksProviderByPolicy(t *testing.T) {
	mockClient := &testMockLLMClient{
		response: &LLMResponse{Content: "response", Model: "gpt-4"},
	}

	executor := NewPromptExecutor(mockClient)
	node := &entity.Node{
		ID:   "prompt_policy",
		Type: string(value.NodeTypePrompt),
		Config: map[string]any{
			"prompt_template": "Hello",
			"provider":        "openai",
			"model":           "gpt-4",
		},
	}

	ctx := port.WithRunContext(context.Background(), &port.RunContext{
		Policy: &entity.ExecutionPolicy{
			AllowedProviders: []string{"anthropic"},
		},
	})

	result, err := executor.Execute(ctx, node, entity.NewState())
	if err != nil {
		t.Fatalf("Execute() error = %v", err)
	}
	if result.Error == nil {
		t.Fatal("expected provider policy denial")
	}
	if !strings.Contains(result.Error.Error(), "policy denied: provider blocked by policy") {
		t.Fatalf("unexpected error: %v", result.Error)
	}
}

func TestPromptExecutor_Execute_StoresStructuredResponseInStateOutputKey(t *testing.T) {
	mockClient := &testMockLLMClient{
		response: &LLMResponse{
			Content: `{"goal":"Launch","iteration":1}`,
			Model:   "gpt-4",
			StructuredData: map[string]any{
				"goal":      "Launch",
				"iteration": 1,
			},
		},
	}

	executor := NewPromptExecutor(mockClient)
	state := entity.NewState()

	node := &entity.Node{
		ID:   "prompt_state_store",
		Type: string(value.NodeTypePrompt),
		Config: map[string]any{
			"prompt_template": "Return state JSON.",
			"output_key":      "execution_state",
			"provider":        "openai",
		},
	}

	result, err := executor.Execute(context.Background(), node, state)
	if err != nil {
		t.Fatalf("Execute() error = %v", err)
	}
	if result.Error != nil {
		t.Fatalf("result.Error = %v", result.Error)
	}

	stored, exists := state.Get("vars.execution_state")
	if !exists {
		t.Fatal("expected vars.execution_state to be stored")
	}
	storedMap, ok := stored.(map[string]any)
	if !ok {
		t.Fatalf("stored state type = %T, want map[string]any", stored)
	}
	if storedMap["goal"] != "Launch" {
		t.Fatalf("stored goal = %v, want Launch", storedMap["goal"])
	}
	if storedMap["iteration"] != 1 {
		t.Fatalf("stored iteration = %v, want 1", storedMap["iteration"])
	}

	output := result.Output.(map[string]any)
	if output["state_output_key"] != "execution_state" {
		t.Fatalf("state_output_key = %v, want execution_state", output["state_output_key"])
	}
}

func TestPromptExecutor_Execute_OnlyFailsWhenSimulationFailureConfigured(t *testing.T) {
	mockClient := &testMockLLMClient{
		response: &LLMResponse{
			Content: `{"ok":true}`,
			Model:   "gpt-4",
		},
	}

	executor := NewPromptExecutor(mockClient)
	state := entity.NewStateWithInput(map[string]any{
		"force_content_failure": true,
	})

	strategyNode := &entity.Node{
		ID:   "strategy_agent",
		Type: string(value.NodeTypePrompt),
		Config: map[string]any{
			"prompt_template": "Return JSON.",
			"provider":        "openai",
		},
	}

	result, err := executor.Execute(context.Background(), strategyNode, state)
	if err != nil {
		t.Fatalf("Execute() error = %v", err)
	}
	if result.Error != nil {
		t.Fatalf("unexpected prompt failure without simulate_failure config: %v", result.Error)
	}

	contentNode := &entity.Node{
		ID:   "content_copywriter_specialist",
		Type: string(value.NodeTypePrompt),
		Config: map[string]any{
			"prompt_template":               "Return JSON.",
			"provider":                      "openai",
			"simulate_failure_input_key":    "force_content_failure",
			"simulate_failure_on_iteration": 1,
		},
	}

	result, err = executor.Execute(context.Background(), contentNode, state)
	if err != nil {
		t.Fatalf("Execute() error = %v", err)
	}
	if result.Error == nil {
		t.Fatal("expected simulated content failure")
	}
	if !strings.Contains(result.Error.Error(), "simulated content_copywriter_specialist failure") {
		t.Fatalf("unexpected simulated failure error: %v", result.Error)
	}
}
