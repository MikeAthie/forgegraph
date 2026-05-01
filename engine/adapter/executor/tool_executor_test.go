package executor

import (
	"context"
	"fmt"
	"net/http"
	"net/http/httptest"
	"strings"
	"sync/atomic"
	"testing"

	"github.com/forgegraph/engine/adapter/tool"
	"github.com/forgegraph/engine/application/port"
	"github.com/forgegraph/engine/domain"
	"github.com/forgegraph/engine/domain/entity"
	"github.com/forgegraph/engine/domain/value"
)

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

type mockToolCredentialResolver struct {
	provider string
	apiKey   string
	err      error
}

func (m *mockToolCredentialResolver) Resolve(_ context.Context, _ string, _ string) (string, string, error) {
	return m.provider, m.apiKey, m.err
}

// getResultInt safely coerces numeric map values to int for assertions.
func getResultInt(v any) int {
	switch x := v.(type) {
	case int:
		return x
	case int64:
		return int(x)
	case float64:
		return int(x)
	}
	return 0
}

// httpToolCall builds a minimal ToolCall for an HTTP tool definition.
func httpToolCall(def tool.Definition, config map[string]any) ResolvedToolCall {
	d := def
	return ResolvedToolCall{
		Name:            def.Name,
		Version:         def.Version,
		Input:           map[string]any{},
		Config:          config,
		CallID:          "test-call-id",
		AttemptID:       "test-attempt-id",
		ToolExecutionID: "11111111-1111-1111-1111-111111111111",
		IdempotencyKey:  "test-idempotency-key",
		SideEffectClass: "idempotent",
		Definition:      &d,
	}
}

// localToolCall builds a minimal ToolCall for a local tool definition.
func localToolCall(def tool.Definition, input map[string]any, config map[string]any, callID string) ResolvedToolCall {
	d := def
	return ResolvedToolCall{
		Name:            def.Name,
		Version:         def.Version,
		Input:           input,
		Config:          config,
		CallID:          callID,
		AttemptID:       "test-attempt-id",
		ToolExecutionID: "11111111-1111-1111-1111-111111111111",
		IdempotencyKey:  "test-idempotency-key",
		SideEffectClass: "idempotent",
		Definition:      &d,
	}
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

func TestToolExecutor_NodeType(t *testing.T) {
	// Constructor no longer takes a registry.
	ex := NewToolExecutor()
	if ex.NodeType() != string(value.NodeTypeTool) {
		t.Fatalf("NodeType() = %s, want %s", ex.NodeType(), string(value.NodeTypeTool))
	}
}

func TestToolExecutor_StrictModeRejectsNodePath(t *testing.T) {
	registry := tool.NewRegistry()
	registry.Register(tool.Definition{
		Name:    "test.strict.adapter",
		Version: "1.0.0",
		Execution: tool.ExecutionConfig{
			Type:  "local",
			Local: &tool.LocalToolConfig{Handler: "noop"},
		},
		SideEffects: tool.SideEffectConfig{Type: "read", Idempotent: true},
	})

	ex := NewToolExecutorWithModes(registry, nil, tool.RuntimeModeCloud, LegacyNodeAdapterModeStrict)
	node := &entity.Node{
		ID:   "tool-1",
		Type: "tool",
		Config: map[string]any{
			"tool":    "test.strict.adapter",
			"version": "1.0.0",
			"input":   map[string]any{},
		},
	}

	result, err := ex.Execute(context.Background(), node, entity.NewState())
	if err != nil {
		t.Fatalf("Execute() error = %v", err)
	}
	if result.Error == nil {
		t.Fatal("expected strict mode to reject node-based execution")
	}
	if !strings.Contains(result.Error.Error(), "node-based tool execution disabled") {
		t.Fatalf("unexpected error: %v", result.Error)
	}
}

func TestToolExecutor_HTTPRetrySucceeds(t *testing.T) {
	var attempts int32
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		current := atomic.AddInt32(&attempts, 1)
		if current == 1 {
			http.Error(w, "temporary", http.StatusServiceUnavailable)
			return
		}
		w.Header().Set("Content-Type", "application/json")
		_, _ = fmt.Fprint(w, `{"ok":true}`)
	}))
	defer server.Close()

	def := tool.Definition{
		Name:    "test.http.retry",
		Version: "1.0.0",
		Execution: tool.ExecutionConfig{
			Type: "http",
			HTTP: &tool.HTTPToolConfig{
				URL:    server.URL,
				Method: http.MethodPost,
			},
		},
		SideEffects: tool.SideEffectConfig{Type: "read", Idempotent: true},
	}

	call := httpToolCall(def, map[string]any{
		"retry_attempts":   2,
		"retry_backoff_ms": 1,
	})

	result, err := NewToolExecutor().ExecuteToolCall(context.Background(), call)
	if err != nil {
		t.Fatalf("ExecuteToolCall() error = %v", err)
	}
	if result.Error != nil {
		t.Fatalf("result.Error = %v", result.Error)
	}

	output, ok := result.Output.(map[string]any)
	if !ok {
		t.Fatalf("expected output map, got %T", result.Output)
	}
	if output["status"] != http.StatusOK {
		t.Fatalf("status = %v, want %d", output["status"], http.StatusOK)
	}
	if output["attempts"] != 2 {
		t.Fatalf("attempts = %v, want 2", output["attempts"])
	}
	if got := atomic.LoadInt32(&attempts); got != 2 {
		t.Fatalf("server attempts = %d, want 2", got)
	}
}

func TestToolExecutor_SendsExecutionIdentityHeaders(t *testing.T) {
	var idempotencyHeader string
	var executionHeader string
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		idempotencyHeader = r.Header.Get("Idempotency-Key")
		executionHeader = r.Header.Get("X-ForgeGraph-Tool-Execution-ID")
		w.Header().Set("Content-Type", "application/json")
		_, _ = fmt.Fprint(w, `{"ok":true}`)
	}))
	defer server.Close()

	def := tool.Definition{
		Name:    "test.http.identity",
		Version: "1.0.0",
		Execution: tool.ExecutionConfig{
			Type: "http",
			HTTP: &tool.HTTPToolConfig{
				URL:    server.URL,
				Method: http.MethodPost,
			},
		},
		SideEffects: tool.SideEffectConfig{Type: "external", Idempotent: true},
	}

	result, err := NewToolExecutor().ExecuteToolCall(context.Background(), httpToolCall(def, nil))
	if err != nil {
		t.Fatalf("ExecuteToolCall() error = %v", err)
	}
	if result.Error != nil {
		t.Fatalf("result.Error = %v", result.Error)
	}
	if idempotencyHeader != "test-idempotency-key" {
		t.Fatalf("Idempotency-Key = %q", idempotencyHeader)
	}
	if executionHeader != "11111111-1111-1111-1111-111111111111" {
		t.Fatalf("X-ForgeGraph-Tool-Execution-ID = %q", executionHeader)
	}
}

func TestToolExecutor_MissingExecutionIdentityDisablesAutomaticRetry(t *testing.T) {
	var attempts int32
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		atomic.AddInt32(&attempts, 1)
		http.Error(w, "temporary", http.StatusServiceUnavailable)
	}))
	defer server.Close()

	def := tool.Definition{
		Name:    "test.http.unsafe-missing-identity",
		Version: "1.0.0",
		Execution: tool.ExecutionConfig{
			Type: "http",
			HTTP: &tool.HTTPToolConfig{
				URL:    server.URL,
				Method: http.MethodPost,
			},
		},
		SideEffects: tool.SideEffectConfig{Type: "external", Idempotent: true},
	}
	call := httpToolCall(def, map[string]any{"retry_attempts": 3, "retry_backoff_ms": 1})
	call.ToolExecutionID = ""
	call.IdempotencyKey = ""

	result, err := NewToolExecutor().ExecuteToolCall(context.Background(), call)
	if err != nil {
		t.Fatalf("ExecuteToolCall() error = %v", err)
	}
	if result.Error == nil {
		t.Fatalf("expected error")
	}
	if got := atomic.LoadInt32(&attempts); got != 1 {
		t.Fatalf("server attempts = %d, want 1", got)
	}
}

func TestToolExecutor_HTTPConnectionDropAfterSendIsAmbiguous(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		hijacker, ok := w.(http.Hijacker)
		if !ok {
			t.Fatalf("response writer does not support hijacking")
		}
		conn, _, err := hijacker.Hijack()
		if err != nil {
			t.Fatalf("hijack: %v", err)
		}
		_ = conn.Close()
	}))
	defer server.Close()

	def := tool.Definition{
		Name:    "test.http.ambiguous",
		Version: "1.0.0",
		Execution: tool.ExecutionConfig{
			Type: "http",
			HTTP: &tool.HTTPToolConfig{
				URL:    server.URL,
				Method: http.MethodPost,
			},
		},
		SideEffects: tool.SideEffectConfig{Type: "external", Idempotent: true},
	}

	result, err := NewToolExecutor().ExecuteToolCall(context.Background(), httpToolCall(def, nil))
	if err != nil {
		t.Fatalf("ExecuteToolCall() error = %v", err)
	}
	if result.Error == nil {
		t.Fatalf("expected ambiguous result error")
	}
	if !domain.IsAmbiguousOutcome(result.Error) {
		t.Fatalf("expected ambiguous outcome, got %T: %v", result.Error, result.Error)
	}
}

// TestToolExecutor_ExplicitNameOnCall replaces the old "AcceptsLegacyToolNameKey" test.
// In the new API, the tool name is always explicit on the ToolCall — there is no fallback
// key lookup. This test verifies a basic named execution works end-to-end.
func TestToolExecutor_ExplicitNameOnCall(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		_, _ = fmt.Fprint(w, `{"ok":true}`)
	}))
	defer server.Close()

	def := tool.Definition{
		Name:    "test.http.named",
		Version: "1.0.0",
		Execution: tool.ExecutionConfig{
			Type: "http",
			HTTP: &tool.HTTPToolConfig{
				URL:    server.URL,
				Method: http.MethodPost,
			},
		},
		SideEffects: tool.SideEffectConfig{Type: "read", Idempotent: true},
	}

	result, err := NewToolExecutor().ExecuteToolCall(context.Background(), httpToolCall(def, nil))
	if err != nil {
		t.Fatalf("ExecuteToolCall() error = %v", err)
	}
	if result.Error != nil {
		t.Fatalf("result.Error = %v", result.Error)
	}
}

func TestToolExecutor_HTTPToolSubstitutesConfigParametersInURL(t *testing.T) {
	var receivedQuery string
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		receivedQuery = r.URL.RawQuery
		w.Header().Set("Content-Type", "application/json")
		_, _ = fmt.Fprint(w, `{"ok":true}`)
	}))
	defer server.Close()

	def := tool.Definition{
		Name:    "test.http.params",
		Version: "1.0.0",
		Execution: tool.ExecutionConfig{
			Type: "http",
			HTTP: &tool.HTTPToolConfig{
				// Backend pre-resolves config; {{config.max_results}} is substituted
				// from call.Config at execution time via flattenToolConfigTemplateValues.
				URL:    server.URL + "/messages?max={{config.max_results}}",
				Method: http.MethodGet,
			},
		},
		SideEffects: tool.SideEffectConfig{Type: "read", Idempotent: true},
	}

	// Config is fully resolved by the backend before reaching the executor.
	call := httpToolCall(def, map[string]any{
		"max_results": 12,
	})

	result, err := NewToolExecutor().ExecuteToolCall(context.Background(), call)
	if err != nil {
		t.Fatalf("ExecuteToolCall() error = %v", err)
	}
	if result.Error != nil {
		t.Fatalf("result.Error = %v", result.Error)
	}
	if !strings.Contains(receivedQuery, "max=12") {
		t.Fatalf("query = %s, expected max=12", receivedQuery)
	}
}

func TestToolExecutor_HTTPToolExpandsEnvironmentVariablesInHeaders(t *testing.T) {
	t.Setenv("RUNTIME_TOOL_SECRET", "runtime-tool-secret")

	var receivedAuth string
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		receivedAuth = r.Header.Get("Authorization")
		w.Header().Set("Content-Type", "application/json")
		_, _ = fmt.Fprint(w, `{"ok":true}`)
	}))
	defer server.Close()

	def := tool.Definition{
		Name:    "test.http.header.env",
		Version: "1.0.0",
		Execution: tool.ExecutionConfig{
			Type: "http",
			HTTP: &tool.HTTPToolConfig{
				URL:    server.URL,
				Method: http.MethodGet,
				Headers: map[string]string{
					"Authorization": "Bearer ${RUNTIME_TOOL_SECRET}",
				},
			},
		},
		SideEffects: tool.SideEffectConfig{Type: "read", Idempotent: true},
	}

	result, err := NewToolExecutor().ExecuteToolCall(context.Background(), httpToolCall(def, nil))
	if err != nil {
		t.Fatalf("ExecuteToolCall() error = %v", err)
	}
	if result.Error != nil {
		t.Fatalf("result.Error = %v", result.Error)
	}
	if receivedAuth != "Bearer runtime-tool-secret" {
		t.Fatalf("Authorization = %s, want Bearer runtime-tool-secret", receivedAuth)
	}
}

func TestToolExecutor_HTTPToolInjectsCredentialAuthorization(t *testing.T) {
	var receivedAuth string
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		receivedAuth = r.Header.Get("Authorization")
		w.Header().Set("Content-Type", "application/json")
		_, _ = fmt.Fprint(w, `{"ok":true}`)
	}))
	defer server.Close()

	def := tool.Definition{
		Name:    "test.http.auth",
		Version: "1.0.0",
		Execution: tool.ExecutionConfig{
			Type: "http",
			HTTP: &tool.HTTPToolConfig{
				URL:    server.URL,
				Method: http.MethodGet,
			},
		},
		SideEffects: tool.SideEffectConfig{Type: "read", Idempotent: true},
	}

	resolver := &mockToolCredentialResolver{provider: "gmail", apiKey: "token-abc"}
	call := httpToolCall(def, map[string]any{
		"provider":      "gmail",
		"credential_id": "cred-123",
	})

	ctx := port.WithTenantID(context.Background(), "tenant-1")
	result, err := NewToolExecutorWithResolver(resolver).ExecuteToolCall(ctx, call)
	if err != nil {
		t.Fatalf("ExecuteToolCall() error = %v", err)
	}
	if result.Error != nil {
		t.Fatalf("result.Error = %v", result.Error)
	}
	if receivedAuth != "Bearer token-abc" {
		t.Fatalf("Authorization = %s, want Bearer token-abc", receivedAuth)
	}
}

func TestToolExecutor_HTTPRetryableErrorOnExhaustedRetries(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		http.Error(w, "temporary", http.StatusServiceUnavailable)
	}))
	defer server.Close()

	def := tool.Definition{
		Name:    "test.http.fail",
		Version: "1.0.0",
		Execution: tool.ExecutionConfig{
			Type: "http",
			HTTP: &tool.HTTPToolConfig{
				URL:    server.URL,
				Method: http.MethodPost,
			},
		},
		SideEffects: tool.SideEffectConfig{Type: "read", Idempotent: true},
	}

	call := httpToolCall(def, map[string]any{
		"retry_attempts":   2,
		"retry_backoff_ms": 1,
	})

	result, err := NewToolExecutor().ExecuteToolCall(context.Background(), call)
	if err != nil {
		t.Fatalf("ExecuteToolCall() error = %v", err)
	}
	if result.Error == nil {
		t.Fatal("expected result.Error for exhausted retries")
	}
	if !domain.IsRetryable(result.Error) {
		t.Fatalf("expected retryable error, got %T (%v)", result.Error, result.Error)
	}
}

func TestToolExecutor_HTTPClientErrorNonRetryable(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		http.Error(w, "bad request", http.StatusBadRequest)
	}))
	defer server.Close()

	def := tool.Definition{
		Name:    "test.http.4xx",
		Version: "1.0.0",
		Execution: tool.ExecutionConfig{
			Type: "http",
			HTTP: &tool.HTTPToolConfig{
				URL:    server.URL,
				Method: http.MethodPost,
			},
		},
		SideEffects: tool.SideEffectConfig{Type: "read", Idempotent: true},
	}

	result, err := NewToolExecutor().ExecuteToolCall(context.Background(), httpToolCall(def, nil))
	if err != nil {
		t.Fatalf("ExecuteToolCall() error = %v", err)
	}
	if result.Error == nil {
		t.Fatal("expected result.Error for 4xx response")
	}
	if domain.IsRetryable(result.Error) {
		t.Fatalf("expected non-retryable error for 4xx, got %T (%v)", result.Error, result.Error)
	}
}

func TestToolExecutor_HTTPRateLimitUsesRetryAfterDetails(t *testing.T) {
	var attempts int32
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		current := atomic.AddInt32(&attempts, 1)
		if current == 1 {
			w.Header().Set("Retry-After", "1")
			http.Error(w, "rate limited", http.StatusTooManyRequests)
			return
		}
		w.Header().Set("Content-Type", "application/json")
		_, _ = fmt.Fprint(w, `{"ok":true}`)
	}))
	defer server.Close()

	def := tool.Definition{
		Name:    "test.http.rate-limit",
		Version: "1.0.0",
		Execution: tool.ExecutionConfig{
			Type: "http",
			HTTP: &tool.HTTPToolConfig{
				URL:    server.URL,
				Method: http.MethodPost,
			},
		},
		SideEffects: tool.SideEffectConfig{Type: "read", Idempotent: true},
	}

	call := httpToolCall(def, map[string]any{
		"retry_attempts":   2,
		"retry_backoff_ms": 1,
	})

	result, err := NewToolExecutor().ExecuteToolCall(context.Background(), call)
	if err != nil {
		t.Fatalf("ExecuteToolCall() error = %v", err)
	}
	if result.Error != nil {
		t.Fatalf("result.Error = %v", result.Error)
	}
	if got := atomic.LoadInt32(&attempts); got != 2 {
		t.Fatalf("server attempts = %d, want 2", got)
	}
}

func TestToolExecutor_HTTPQuotaExhaustedNonRetryable(t *testing.T) {
	var attempts int32
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		atomic.AddInt32(&attempts, 1)
		w.Header().Set("Retry-After", "30")
		http.Error(w, "insufficient_quota", http.StatusTooManyRequests)
	}))
	defer server.Close()

	def := tool.Definition{
		Name:    "test.http.quota",
		Version: "1.0.0",
		Execution: tool.ExecutionConfig{
			Type: "http",
			HTTP: &tool.HTTPToolConfig{
				URL:    server.URL,
				Method: http.MethodPost,
			},
		},
		SideEffects: tool.SideEffectConfig{Type: "external", Idempotent: true},
	}

	call := httpToolCall(def, map[string]any{
		"retry_attempts":   3,
		"retry_backoff_ms": 1,
	})

	result, err := NewToolExecutor().ExecuteToolCall(context.Background(), call)
	if err != nil {
		t.Fatalf("ExecuteToolCall() error = %v", err)
	}
	if result.Error == nil {
		t.Fatal("expected non-retryable quota error")
	}
	if domain.IsRetryable(result.Error) {
		t.Fatalf("expected non-retryable error for quota exhaustion, got %T (%v)", result.Error, result.Error)
	}
	if got := atomic.LoadInt32(&attempts); got != 1 {
		t.Fatalf("server attempts = %d, want 1", got)
	}
}

func TestToolExecutor_LocalToolHandlerEcho(t *testing.T) {
	def := tool.Definition{
		Name:    "test.local.echo",
		Version: "1.0.0",
		Execution: tool.ExecutionConfig{
			Type:  "local",
			Local: &tool.LocalToolConfig{Handler: "echo"},
		},
		SideEffects: tool.SideEffectConfig{Type: "read", Idempotent: true},
	}

	call := localToolCall(def, map[string]any{"value": 123}, nil, "call-echo-1")

	result, err := NewToolExecutor().ExecuteToolCall(context.Background(), call)
	if err != nil {
		t.Fatalf("ExecuteToolCall() error = %v", err)
	}
	if result.Error != nil {
		t.Fatalf("result.Error = %v", result.Error)
	}

	output, ok := result.Output.(map[string]any)
	if !ok {
		t.Fatalf("expected output map, got %T", result.Output)
	}
	payload, ok := output["result"].(map[string]any)
	if !ok {
		t.Fatalf("expected result payload map, got %T", output["result"])
	}
	if payload["value"] != float64(123) && payload["value"] != 123 {
		t.Fatalf("unexpected local payload: %#v", payload)
	}
}

func TestToolExecutor_LocalToolUnsupportedHandlerFails(t *testing.T) {
	def := tool.Definition{
		Name:    "test.local.invalid",
		Version: "1.0.0",
		Execution: tool.ExecutionConfig{
			Type:  "local",
			Local: &tool.LocalToolConfig{Handler: "missing"},
		},
		// Idempotent: true so the executor doesn't reject it at the call_id gate,
		// letting it reach the handler and fail there as the test intends.
		SideEffects: tool.SideEffectConfig{Type: "external", Idempotent: true},
	}

	call := localToolCall(def, nil, nil, "call-invalid-1")

	result, err := NewToolExecutor().ExecuteToolCall(context.Background(), call)
	if err != nil {
		t.Fatalf("ExecuteToolCall() error = %v", err)
	}
	if result.Error == nil {
		t.Fatal("expected local handler error")
	}
}

func TestToolExecutor_HTTPToolBlocksEgressByPolicy(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		_, _ = fmt.Fprint(w, `{"ok":true}`)
	}))
	defer server.Close()

	def := tool.Definition{
		Name:    "test.http.policy",
		Version: "1.0.0",
		Execution: tool.ExecutionConfig{
			Type: "http",
			HTTP: &tool.HTTPToolConfig{URL: server.URL},
		},
		SideEffects: tool.SideEffectConfig{Type: "read", Idempotent: true},
	}

	ctx := port.WithRunContext(context.Background(), &port.RunContext{
		Policy: &entity.ExecutionPolicy{
			HTTPAllowlist:   []string{"example.com"},
			HTTPDefaultDeny: true,
		},
	})

	result, err := NewToolExecutor().ExecuteToolCall(ctx, httpToolCall(def, nil))
	if err != nil {
		t.Fatalf("ExecuteToolCall() error = %v", err)
	}
	if result.Error == nil {
		t.Fatal("expected policy validation error")
	}
	if !strings.Contains(result.Error.Error(), "policy denied: egress blocked by policy") {
		t.Fatalf("unexpected error message: %v", result.Error)
	}
}

func TestToolExecutor_LocalToolAllowedInCloudMode(t *testing.T) {
	def := tool.Definition{
		Name:    "test.local.cloud",
		Version: "1.0.0",
		Execution: tool.ExecutionConfig{
			Type:  "local",
			Local: &tool.LocalToolConfig{Handler: "noop"},
		},
		SideEffects: tool.SideEffectConfig{Type: "read", Idempotent: true},
	}

	call := localToolCall(def, nil, nil, "call-cloud-1")

	// Constructor no longer takes a registry.
	result, err := NewToolExecutorWithRuntimeMode(tool.RuntimeModeCloud).ExecuteToolCall(context.Background(), call)
	if err != nil {
		t.Fatalf("ExecuteToolCall() error = %v", err)
	}
	if result.Error != nil {
		t.Fatalf("expected local tool to be allowed in cloud mode, got %v", result.Error)
	}
}

func TestToolExecutor_TruncatesOversizedToolResults(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "text/plain")
		_, _ = fmt.Fprint(w, strings.Repeat("A", 80))
	}))
	defer server.Close()

	def := tool.Definition{
		Name:          "test.http.large-result",
		Version:       "1.0.0",
		MaxResultSize: 20,
		Execution: tool.ExecutionConfig{
			Type: "http",
			HTTP: &tool.HTTPToolConfig{
				URL:    server.URL,
				Method: http.MethodGet,
			},
		},
		SideEffects: tool.SideEffectConfig{Type: "read", Idempotent: true},
	}

	result, err := NewToolExecutor().ExecuteToolCall(context.Background(), httpToolCall(def, nil))
	if err != nil {
		t.Fatalf("ExecuteToolCall() error = %v", err)
	}
	if result.Error != nil {
		t.Fatalf("result.Error = %v", result.Error)
	}

	output, ok := result.Output.(map[string]any)
	if !ok {
		t.Fatalf("expected output map, got %T", result.Output)
	}
	if truncated, ok := output["result_truncated"].(bool); !ok || !truncated {
		t.Fatalf("expected result_truncated metadata, got %#v", output)
	}
	preview, ok := output["result"].(string)
	if !ok {
		t.Fatalf("expected truncated preview string, got %T", output["result"])
	}
	if !strings.Contains(preview, "[truncated]") {
		t.Fatalf("expected truncated preview marker, got %q", preview)
	}
	if got := getResultInt(output["result_original_chars"]); got != 80 {
		t.Fatalf("result_original_chars = %d, want 80", got)
	}
	if got := getResultInt(output["result_limit_chars"]); got != 20 {
		t.Fatalf("result_limit_chars = %d, want 20", got)
	}
}
