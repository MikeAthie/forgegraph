package executor

import (
	"context"
	"encoding/json"
	"fmt"
	"net/http"
	"net/http/httptest"
	"os"
	"strings"
	"sync/atomic"
	"testing"
	"time"

	"github.com/forgegraph/engine/adapter/tool"
	"github.com/forgegraph/engine/application/port"
	"github.com/forgegraph/engine/domain"
	"github.com/forgegraph/engine/domain/entity"
	"github.com/forgegraph/engine/domain/value"
)

type mockToolCredentialResolver struct {
	provider string
	apiKey   string
	err      error
}

func (m *mockToolCredentialResolver) Resolve(ctx context.Context, credentialID string, tenantID string) (string, string, error) {
	return m.provider, m.apiKey, m.err
}

func TestToolExecutor_NodeType(t *testing.T) {
	executor := NewToolExecutor(tool.NewRegistry())
	if executor.NodeType() != string(value.NodeTypeTool) {
		t.Fatalf("NodeType() = %s, want %s", executor.NodeType(), string(value.NodeTypeTool))
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

	registry := tool.NewRegistry()
	registry.Register(tool.Definition{
		Name:    "test.http.retry",
		Version: "1.0.0",
		Kind:    "http",
		HTTP: &tool.HTTPToolConfig{
			URL:    server.URL,
			Method: http.MethodPost,
		},
	})

	executor := NewToolExecutor(registry)
	node := &entity.Node{
		ID:   "tool_1",
		Type: string(value.NodeTypeTool),
		Config: map[string]any{
			"tool":             "test.http.retry",
			"retry_attempts":   2,
			"retry_backoff_ms": 1,
			"input": map[string]any{
				"query": "hello",
			},
		},
	}

	result, err := executor.Execute(context.Background(), node, entity.NewState())
	if err != nil {
		t.Fatalf("Execute() error = %v", err)
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

func TestToolExecutor_AcceptsLegacyToolNameKey(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		_, _ = fmt.Fprint(w, `{"ok":true}`)
	}))
	defer server.Close()

	registry := tool.NewRegistry()
	registry.Register(tool.Definition{
		Name:    "test.http.legacy-tool-name",
		Version: "1.0.0",
		Kind:    "http",
		HTTP: &tool.HTTPToolConfig{
			URL:    server.URL,
			Method: http.MethodPost,
		},
	})

	executor := NewToolExecutor(registry)
	node := &entity.Node{
		ID:   "tool_legacy_name",
		Type: string(value.NodeTypeTool),
		Config: map[string]any{
			"tool_name": "test.http.legacy-tool-name",
		},
	}

	result, err := executor.Execute(context.Background(), node, entity.NewState())
	if err != nil {
		t.Fatalf("Execute() error = %v", err)
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

	registry := tool.NewRegistry()
	registry.Register(tool.Definition{
		Name:    "test.http.params",
		Version: "1.0.0",
		Kind:    "http",
		DefaultConfig: map[string]any{
			"max_results": 5,
		},
		HTTP: &tool.HTTPToolConfig{
			URL:    server.URL + "/messages?max={{config.max_results}}",
			Method: http.MethodGet,
		},
	})

	executor := NewToolExecutor(registry)
	node := &entity.Node{
		ID:   "tool_params",
		Type: string(value.NodeTypeTool),
		Config: map[string]any{
			"tool": "test.http.params",
			"parameters": map[string]any{
				"max_results": 12,
			},
		},
	}

	result, err := executor.Execute(context.Background(), node, entity.NewState())
	if err != nil {
		t.Fatalf("Execute() error = %v", err)
	}
	if result.Error != nil {
		t.Fatalf("result.Error = %v", result.Error)
	}
	if !strings.Contains(receivedQuery, "max=12") {
		t.Fatalf("query = %s, expected max=12", receivedQuery)
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

	registry := tool.NewRegistry()
	registry.Register(tool.Definition{
		Name:    "test.http.auth",
		Version: "1.0.0",
		Kind:    "http",
		DefaultConfig: map[string]any{
			"provider": "gmail",
		},
		HTTP: &tool.HTTPToolConfig{
			URL:    server.URL,
			Method: http.MethodGet,
		},
	})

	resolver := &mockToolCredentialResolver{provider: "gmail", apiKey: "token-abc"}
	executor := NewToolExecutorWithResolver(registry, resolver)
	node := &entity.Node{
		ID:   "tool_auth",
		Type: string(value.NodeTypeTool),
		Config: map[string]any{
			"tool":          "test.http.auth",
			"provider":      "gmail",
			"credential_id": "cred-123",
		},
	}

	ctx := port.WithTenantID(context.Background(), "tenant-1")
	result, err := executor.Execute(ctx, node, entity.NewState())
	if err != nil {
		t.Fatalf("Execute() error = %v", err)
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

	registry := tool.NewRegistry()
	registry.Register(tool.Definition{
		Name:    "test.http.fail",
		Version: "1.0.0",
		Kind:    "http",
		HTTP: &tool.HTTPToolConfig{
			URL:    server.URL,
			Method: http.MethodPost,
		},
	})

	executor := NewToolExecutor(registry)
	node := &entity.Node{
		ID:   "tool_1",
		Type: string(value.NodeTypeTool),
		Config: map[string]any{
			"tool":             "test.http.fail",
			"retry_attempts":   2,
			"retry_backoff_ms": 1,
		},
	}

	result, err := executor.Execute(context.Background(), node, entity.NewState())
	if err != nil {
		t.Fatalf("Execute() error = %v", err)
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

	registry := tool.NewRegistry()
	registry.Register(tool.Definition{
		Name:    "test.http.4xx",
		Version: "1.0.0",
		Kind:    "http",
		HTTP: &tool.HTTPToolConfig{
			URL:    server.URL,
			Method: http.MethodPost,
		},
	})

	executor := NewToolExecutor(registry)
	node := &entity.Node{
		ID:   "tool_1",
		Type: string(value.NodeTypeTool),
		Config: map[string]any{
			"tool": "test.http.4xx",
		},
	}

	result, err := executor.Execute(context.Background(), node, entity.NewState())
	if err != nil {
		t.Fatalf("Execute() error = %v", err)
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

	registry := tool.NewRegistry()
	registry.Register(tool.Definition{
		Name:    "test.http.rate-limit",
		Version: "1.0.0",
		Kind:    "http",
		HTTP: &tool.HTTPToolConfig{
			URL:    server.URL,
			Method: http.MethodPost,
		},
	})

	executor := NewToolExecutor(registry)
	node := &entity.Node{
		ID:   "tool_rate_1",
		Type: string(value.NodeTypeTool),
		Config: map[string]any{
			"tool":             "test.http.rate-limit",
			"retry_attempts":   2,
			"retry_backoff_ms": 1,
		},
	}

	result, err := executor.Execute(context.Background(), node, entity.NewState())
	if err != nil {
		t.Fatalf("Execute() error = %v", err)
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

	registry := tool.NewRegistry()
	registry.Register(tool.Definition{
		Name:    "test.http.quota",
		Version: "1.0.0",
		Kind:    "http",
		HTTP: &tool.HTTPToolConfig{
			URL:    server.URL,
			Method: http.MethodPost,
		},
	})

	executor := NewToolExecutor(registry)
	node := &entity.Node{
		ID:   "tool_quota_1",
		Type: string(value.NodeTypeTool),
		Config: map[string]any{
			"tool":             "test.http.quota",
			"retry_attempts":   3,
			"retry_backoff_ms": 1,
		},
	}

	result, err := executor.Execute(context.Background(), node, entity.NewState())
	if err != nil {
		t.Fatalf("Execute() error = %v", err)
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

func TestToolExecutor_ExecToolUserFunctionPath(t *testing.T) {
	t.Setenv("GO_WANT_HELPER_PROCESS", "1")

	registry := tool.NewRegistry()
	registry.Register(tool.Definition{
		Name:    "test.exec.success",
		Version: "1.0.0",
		Kind:    "exec",
		Exec: &tool.ExecToolConfig{
			Command: os.Args[0],
			Args:    []string{"-test.run=TestToolExecutorHelperProcess", "--", "success"},
		},
	})

	executor := NewToolExecutor(registry)
	node := &entity.Node{
		ID:   "tool_exec_1",
		Type: string(value.NodeTypeTool),
		Config: map[string]any{
			"tool": "test.exec.success",
			"input": map[string]any{
				"value": 123,
			},
		},
	}

	result, err := executor.Execute(context.Background(), node, entity.NewState())
	if err != nil {
		t.Fatalf("Execute() error = %v", err)
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
	if payload["message"] != "ok" {
		t.Fatalf("unexpected exec payload: %#v", payload)
	}
}

func TestToolExecutor_ExecTimeoutRetryable(t *testing.T) {
	t.Setenv("GO_WANT_HELPER_PROCESS", "1")

	registry := tool.NewRegistry()
	registry.Register(tool.Definition{
		Name:    "test.exec.timeout",
		Version: "1.0.0",
		Kind:    "exec",
		Exec: &tool.ExecToolConfig{
			Command: os.Args[0],
			Args:    []string{"-test.run=TestToolExecutorHelperProcess", "--", "sleep"},
		},
	})

	executor := NewToolExecutor(registry)
	node := &entity.Node{
		ID:   "tool_exec_1",
		Type: string(value.NodeTypeTool),
		Config: map[string]any{
			"tool":           "test.exec.timeout",
			"timeout_ms":     25,
			"retry_attempts": 1,
		},
	}

	result, err := executor.Execute(context.Background(), node, entity.NewState())
	if err != nil {
		t.Fatalf("Execute() error = %v", err)
	}
	if result.Error == nil {
		t.Fatal("expected timeout error")
	}
	if !domain.IsRetryable(result.Error) {
		t.Fatalf("expected retryable timeout error, got %T (%v)", result.Error, result.Error)
	}
}

func TestToolExecutorHelperProcess(t *testing.T) {
	if os.Getenv("GO_WANT_HELPER_PROCESS") != "1" {
		return
	}

	mode := ""
	for i, arg := range os.Args {
		if arg == "--" && i+1 < len(os.Args) {
			mode = os.Args[i+1]
			break
		}
	}
	if mode == "" {
		os.Exit(2)
	}

	switch mode {
	case "success":
		decoder := json.NewDecoder(os.Stdin)
		var payload map[string]any
		_ = decoder.Decode(&payload)
		_, _ = fmt.Fprint(os.Stdout, `{"message":"ok"}`)
		os.Exit(0)
	case "sleep":
		time.Sleep(150 * time.Millisecond)
		_, _ = fmt.Fprint(os.Stdout, `{"message":"late"}`)
		os.Exit(0)
	default:
		_, _ = fmt.Fprintf(os.Stderr, "unknown helper mode %s", mode)
		os.Exit(1)
	}
}

func TestToolExecutor_HTTPToolBlocksEgressByPolicy(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		_, _ = fmt.Fprint(w, `{"ok":true}`)
	}))
	defer server.Close()

	registry := tool.NewRegistry()
	registry.Register(tool.Definition{
		Name:    "test.http.policy",
		Version: "1.0.0",
		Kind:    "http",
		HTTP: &tool.HTTPToolConfig{
			URL: server.URL,
		},
	})

	ctx := context.Background()
	ctx = port.WithRunContext(ctx, &port.RunContext{
		Policy: &entity.ExecutionPolicy{
			HTTPAllowlist:   []string{"example.com"},
			HTTPDefaultDeny: true,
		},
	})

	executor := NewToolExecutor(registry)
	node := &entity.Node{
		ID:   "tool_policy",
		Type: string(value.NodeTypeTool),
		Config: map[string]any{
			"tool": "test.http.policy",
		},
	}

	result, err := executor.Execute(ctx, node, entity.NewState())
	if err != nil {
		t.Fatalf("Execute() error = %v", err)
	}
	if result.Error == nil {
		t.Fatal("expected policy validation error")
	}
	if !strings.Contains(result.Error.Error(), "policy denied: egress blocked by policy") {
		t.Fatalf("unexpected error message: %v", result.Error)
	}
}

func TestToolExecutor_ExecToolBlockedInCloudMode(t *testing.T) {
	registry := tool.NewRegistry()
	registry.Register(tool.Definition{
		Name:    "test.exec.cloud-blocked",
		Version: "1.0.0",
		Kind:    "exec",
		Exec: &tool.ExecToolConfig{
			Command: os.Args[0],
			Args:    []string{"-test.run=TestToolExecutorHelperProcess", "--", "success"},
		},
	})

	executor := NewToolExecutorWithRuntimeMode(registry, tool.RuntimeModeCloud)
	node := &entity.Node{
		ID:   "tool_exec_cloud",
		Type: string(value.NodeTypeTool),
		Config: map[string]any{
			"tool": "test.exec.cloud-blocked",
		},
	}

	result, err := executor.Execute(context.Background(), node, entity.NewState())
	if err != nil {
		t.Fatalf("Execute() error = %v", err)
	}
	if result.Error == nil {
		t.Fatal("expected cloud-mode exec policy error")
	}
	if !strings.Contains(result.Error.Error(), "policy denied: exec tools are disabled in cloud mode") {
		t.Fatalf("unexpected error message: %v", result.Error)
	}
}

func TestToolExecutor_TruncatesOversizedToolResults(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "text/plain")
		_, _ = fmt.Fprint(w, strings.Repeat("A", 80))
	}))
	defer server.Close()

	registry := tool.NewRegistry()
	registry.Register(tool.Definition{
		Name:          "test.http.large-result",
		Version:       "1.0.0",
		Kind:          "http",
		MaxResultSize: 20,
		HTTP: &tool.HTTPToolConfig{
			URL:    server.URL,
			Method: http.MethodGet,
		},
	})

	executor := NewToolExecutor(registry)
	node := &entity.Node{
		ID:   "tool_large_result",
		Type: string(value.NodeTypeTool),
		Config: map[string]any{
			"tool": "test.http.large-result",
		},
	}

	result, err := executor.Execute(context.Background(), node, entity.NewState())
	if err != nil {
		t.Fatalf("Execute() error = %v", err)
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
	if got := getConfigInt(output["result_original_chars"]); got != 80 {
		t.Fatalf("result_original_chars = %d, want 80", got)
	}
	if got := getConfigInt(output["result_limit_chars"]); got != 20 {
		t.Fatalf("result_limit_chars = %d, want 20", got)
	}
}
