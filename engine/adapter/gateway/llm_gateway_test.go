package gateway

import (
	"context"
	"errors"
	"testing"
	"time"
)

type gatewayTestProvider struct {
	name      string
	response  LLMResponse
	err       error
	started   chan struct{}
	release   chan struct{}
	callCount int
}

func (p *gatewayTestProvider) ProviderName() string {
	if p.name == "" {
		return "test"
	}
	return p.name
}

func (p *gatewayTestProvider) Generate(ctx context.Context, req LLMRequest) (LLMResponse, error) {
	p.callCount++
	if p.started != nil {
		select {
		case p.started <- struct{}{}:
		default:
		}
	}
	if p.release != nil {
		select {
		case <-p.release:
		case <-ctx.Done():
			return LLMResponse{}, ctx.Err()
		}
	}
	if p.err != nil {
		return LLMResponse{}, p.err
	}
	response := p.response
	if response.Content == "" {
		response.Content = "ok"
	}
	if response.Provider == "" {
		response.Provider = p.ProviderName()
	}
	return response, nil
}

func testGatewayConfig() LLMGatewayConfig {
	return LLMGatewayConfig{
		MaxConcurrent:               0,
		MaxQueueSize:                0,
		QueueTimeout:                20 * time.Millisecond,
		RequestTimeout:              50 * time.Millisecond,
		CircuitFailureRateThreshold: 0,
		CircuitMinRequests:          2,
		CircuitWindowSize:           2,
		CircuitCooldown:             20 * time.Millisecond,
	}
}

func TestLLMGatewayGeneratesThroughPrimaryProvider(t *testing.T) {
	primary := &gatewayTestProvider{
		name:     "local",
		response: LLMResponse{Content: "primary response", Model: "m"},
	}
	gw := NewLLMGateway(primary, nil, testGatewayConfig())

	response, err := gw.Generate(context.Background(), LLMRequest{
		Prompt:      "hello",
		Model:       "m",
		Metadata:    map[string]string{"run_id": "run-1", "node_id": "prompt-1"},
		MaxTokens:   32,
		Temperature: 0.2,
	})
	if err != nil {
		t.Fatalf("Generate() error = %v", err)
	}
	if response.Status != LLMStatusSuccess || response.Content != "primary response" {
		t.Fatalf("unexpected response: %#v", response)
	}
	if response.FallbackUsed {
		t.Fatal("fallback_used = true, want false")
	}
	if snapshot := gw.MetricsSnapshot(); snapshot.LLMRequests != 1 || snapshot.LLMFailures != 0 {
		t.Fatalf("unexpected metrics snapshot: %#v", snapshot)
	}
}

func TestLLMGatewayRecordsLLMMode(t *testing.T) {
	primary := &gatewayTestProvider{
		name:     "local",
		response: LLMResponse{Content: "primary response", Model: "m", Provider: "openai"},
	}
	gw := NewLLMGateway(primary, nil, testGatewayConfig())

	response, err := gw.Generate(context.Background(), LLMRequest{
		Prompt:   "hello",
		Model:    "m",
		LLMMode:  LLMModeBYOK,
		Provider: "openai",
		APIKey:   "sk-test-byok",
		Metadata: map[string]string{"run_id": "run-1", "node_id": "prompt-1"},
	})
	if err != nil {
		t.Fatalf("Generate() error = %v", err)
	}
	if response.LLMMode != LLMModeBYOK {
		t.Fatalf("response llm_mode = %q, want byok", response.LLMMode)
	}
	if response.CredentialSource != LLMModeBYOK {
		t.Fatalf("credential_source = %q, want byok", response.CredentialSource)
	}
	snapshot := gw.MetricsSnapshot()
	if snapshot.RequestsByMode[LLMModeBYOK] != 1 {
		t.Fatalf("unexpected requests_by_mode: %#v", snapshot.RequestsByMode)
	}
	if snapshot.RequestsByProvider["openai"] != 1 {
		t.Fatalf("unexpected requests_by_provider: %#v", snapshot.RequestsByProvider)
	}
}

func TestLLMGatewayRejectsBYOKWithoutKeyAsInvalidCredentials(t *testing.T) {
	primary := &gatewayTestProvider{name: "local"}
	gw := NewLLMGateway(primary, nil, testGatewayConfig())

	_, err := gw.Generate(context.Background(), LLMRequest{
		Prompt:   "hello",
		LLMMode:  LLMModeBYOK,
		Provider: "openai",
	})
	var llmErr *LLMError
	if !errors.As(err, &llmErr) {
		t.Fatalf("expected LLMError, got %T %v", err, err)
	}
	if llmErr.Type != LLMErrorInvalidCredentials {
		t.Fatalf("error type = %s, want %s", llmErr.Type, LLMErrorInvalidCredentials)
	}
}

func TestLLMGatewayNormalizesProviderAuthAndRateLimitErrors(t *testing.T) {
	cases := []struct {
		name string
		err  error
		want string
	}{
		{
			name: "invalid credentials",
			err:  errors.New("openai error: status 401: invalid api key"),
			want: LLMErrorInvalidCredentials,
		},
		{
			name: "rate limit",
			err:  errors.New("openai error: status 429: rate limit"),
			want: LLMErrorRateLimit,
		},
	}

	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			primary := &gatewayTestProvider{name: "local", err: tc.err}
			gw := NewLLMGateway(primary, nil, testGatewayConfig())

			_, err := gw.Generate(context.Background(), LLMRequest{
				Prompt:   "hello",
				Provider: "openai",
			})
			var llmErr *LLMError
			if !errors.As(err, &llmErr) {
				t.Fatalf("expected LLMError, got %T %v", err, err)
			}
			if llmErr.Type != tc.want {
				t.Fatalf("error type = %s, want %s", llmErr.Type, tc.want)
			}
			snapshot := gw.MetricsSnapshot()
			if snapshot.FailuresByMode[LLMModeManaged] != 1 {
				t.Fatalf("unexpected failures_by_mode: %#v", snapshot.FailuresByMode)
			}
		})
	}
}

func TestLLMGatewayUsesFallbackOnceAfterPrimaryFailure(t *testing.T) {
	primary := &gatewayTestProvider{name: "local", err: context.DeadlineExceeded}
	fallback := NewMockFallbackLLMClient("fallback response")
	gw := NewLLMGateway(primary, fallback, testGatewayConfig())

	response, err := gw.Generate(context.Background(), LLMRequest{Prompt: "hello", Model: "m"})
	if err != nil {
		t.Fatalf("Generate() error = %v", err)
	}
	if !response.FallbackUsed || response.Provider != "fallback" || response.Content != "fallback response" {
		t.Fatalf("expected fallback response, got %#v", response)
	}
	if primary.callCount != 1 {
		t.Fatalf("primary calls = %d, want 1", primary.callCount)
	}
	if snapshot := gw.MetricsSnapshot(); snapshot.FallbackCount != 1 || snapshot.LLMFailures != 0 {
		t.Fatalf("unexpected metrics snapshot: %#v", snapshot)
	}
}

func TestLLMGatewayRejectsWhenQueueIsFull(t *testing.T) {
	primary := &gatewayTestProvider{
		name:    "local",
		started: make(chan struct{}, 1),
		release: make(chan struct{}),
	}
	cfg := testGatewayConfig()
	cfg.MaxConcurrent = 1
	cfg.MaxQueueSize = 0
	cfg.RequestTimeout = time.Second
	gw := NewLLMGateway(primary, nil, cfg)

	done := make(chan error, 1)
	go func() {
		_, err := gw.Generate(context.Background(), LLMRequest{Prompt: "first"})
		done <- err
	}()
	<-primary.started

	_, err := gw.Generate(context.Background(), LLMRequest{Prompt: "second"})
	var llmErr *LLMError
	if !errors.As(err, &llmErr) {
		t.Fatalf("expected LLMError, got %T %v", err, err)
	}
	if llmErr.Type != LLMErrorRateLimit || llmErr.Code != "llm_gateway_queue_full" {
		t.Fatalf("unexpected llm error: %#v", llmErr)
	}

	close(primary.release)
	if err := <-done; err != nil {
		t.Fatalf("first Generate() error = %v", err)
	}
}

func TestLLMGatewayAppliesRequestTimeout(t *testing.T) {
	primary := &gatewayTestProvider{
		name:    "local",
		release: make(chan struct{}),
	}
	cfg := testGatewayConfig()
	cfg.MaxConcurrent = 1
	cfg.RequestTimeout = 10 * time.Millisecond
	gw := NewLLMGateway(primary, nil, cfg)

	_, err := gw.Generate(context.Background(), LLMRequest{Prompt: "slow"})
	var llmErr *LLMError
	if !errors.As(err, &llmErr) {
		t.Fatalf("expected LLMError, got %T %v", err, err)
	}
	if llmErr.Type != LLMErrorTimeout {
		t.Fatalf("error type = %s, want %s", llmErr.Type, LLMErrorTimeout)
	}
}

func TestLLMGatewayCircuitOpensAndCloses(t *testing.T) {
	primary := &gatewayTestProvider{name: "local", err: context.DeadlineExceeded}
	cfg := testGatewayConfig()
	cfg.CircuitFailureRateThreshold = 0.5
	cfg.CircuitMinRequests = 2
	cfg.CircuitWindowSize = 2
	cfg.CircuitCooldown = 15 * time.Millisecond
	gw := NewLLMGateway(primary, nil, cfg)

	for i := 0; i < 2; i++ {
		_, _ = gw.Generate(context.Background(), LLMRequest{Prompt: "fail"})
	}
	if snapshot := gw.MetricsSnapshot(); !snapshot.CircuitOpen {
		t.Fatalf("expected circuit open, got %#v", snapshot)
	}

	_, err := gw.Generate(context.Background(), LLMRequest{Prompt: "rejected"})
	var llmErr *LLMError
	if !errors.As(err, &llmErr) || llmErr.Code != "llm_gateway_circuit_open" {
		t.Fatalf("expected circuit-open LLMError, got %T %v", err, err)
	}

	time.Sleep(20 * time.Millisecond)
	primary.err = nil
	response, err := gw.Generate(context.Background(), LLMRequest{Prompt: "after cooldown"})
	if err != nil {
		t.Fatalf("Generate() after cooldown error = %v", err)
	}
	if response.Status != LLMStatusSuccess {
		t.Fatalf("response status = %s, want success", response.Status)
	}
}
