package executor

import (
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"

	"github.com/forgegraph/engine/application/port"
	"github.com/forgegraph/engine/domain/entity"
	"github.com/forgegraph/engine/domain/value"
)

type mockCredentialResolver struct {
	provider string
	apiKey   string
	err      error
}

func (m *mockCredentialResolver) Resolve(ctx context.Context, credentialID string, tenantID string) (string, string, error) {
	if m.err != nil {
		return "", "", m.err
	}
	return m.provider, m.apiKey, nil
}

func TestHTTPExecutor_NodeType(t *testing.T) {
	executor := NewHTTPExecutor()
	if executor.NodeType() != string(value.NodeTypeHTTP) {
		t.Errorf("NodeType() = %v, want %v", executor.NodeType(), string(value.NodeTypeHTTP))
	}
}

func TestHTTPExecutor_Execute_GET(t *testing.T) {
	// Create mock server
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.Method != "GET" {
			t.Errorf("Expected GET, got %s", r.Method)
		}
		w.Header().Set("Content-Type", "application/json")
		json.NewEncoder(w).Encode(map[string]any{
			"message": "success",
			"data":    42,
		})
	}))
	defer server.Close()

	executor := NewHTTPExecutorWithClient(server.Client())
	state := entity.NewState()

	node := &entity.Node{
		ID:   "http_1",
		Type: string(value.NodeTypeHTTP),
		Config: map[string]any{
			"method": "GET",
			"url":    server.URL,
		},
	}

	result, err := executor.Execute(context.Background(), node, state)
	if err != nil {
		t.Fatalf("Execute() error = %v", err)
	}
	if result.Error != nil {
		t.Fatalf("result.Error = %v", result.Error)
	}

	output, ok := result.Output.(map[string]any)
	if !ok {
		t.Fatalf("Output is not map[string]any")
	}

	if output["status_code"] != 200 {
		t.Errorf("status_code = %v, want 200", output["status_code"])
	}

	body, ok := output["body"].(map[string]any)
	if !ok {
		t.Fatalf("body is not map[string]any: %T", output["body"])
	}

	if body["message"] != "success" {
		t.Errorf("body.message = %v, want 'success'", body["message"])
	}
}

func TestHTTPExecutor_Execute_POST(t *testing.T) {
	var receivedBody map[string]any

	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.Method != "POST" {
			t.Errorf("Expected POST, got %s", r.Method)
		}
		if r.Header.Get("Content-Type") != "application/json" {
			t.Errorf("Expected Content-Type application/json, got %s", r.Header.Get("Content-Type"))
		}

		json.NewDecoder(r.Body).Decode(&receivedBody)

		w.WriteHeader(http.StatusCreated)
		json.NewEncoder(w).Encode(map[string]any{"id": 123})
	}))
	defer server.Close()

	executor := NewHTTPExecutorWithClient(server.Client())
	state := entity.NewState()
	state.SetVar("user_name", "Alice")

	node := &entity.Node{
		ID:   "http_1",
		Type: string(value.NodeTypeHTTP),
		Config: map[string]any{
			"method": "POST",
			"url":    server.URL,
			"body": map[string]any{
				"name":  "{{vars.user_name}}",
				"email": "alice@example.com",
			},
		},
	}

	result, err := executor.Execute(context.Background(), node, state)
	if err != nil {
		t.Fatalf("Execute() error = %v", err)
	}
	if result.Error != nil {
		t.Fatalf("result.Error = %v", result.Error)
	}

	// Check received body had variable substituted
	if receivedBody["name"] != "Alice" {
		t.Errorf("Received name = %v, want 'Alice'", receivedBody["name"])
	}

	output := result.Output.(map[string]any)
	if output["status_code"] != 201 {
		t.Errorf("status_code = %v, want 201", output["status_code"])
	}
}

func TestHTTPExecutor_Execute_URLSubstitution(t *testing.T) {
	var receivedPath string

	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		receivedPath = r.URL.Path
		w.WriteHeader(http.StatusOK)
	}))
	defer server.Close()

	executor := NewHTTPExecutorWithClient(server.Client())
	state := entity.NewState()
	state.SetVar("user_id", "456")

	node := &entity.Node{
		ID:   "http_1",
		Type: string(value.NodeTypeHTTP),
		Config: map[string]any{
			"url": server.URL + "/users/{{vars.user_id}}",
		},
	}

	result, err := executor.Execute(context.Background(), node, state)
	if err != nil {
		t.Fatalf("Execute() error = %v", err)
	}
	if result.Error != nil {
		t.Fatalf("result.Error = %v", result.Error)
	}

	if receivedPath != "/users/456" {
		t.Errorf("Received path = %v, want '/users/456'", receivedPath)
	}
}

func TestHTTPExecutor_Execute_HeaderSubstitution(t *testing.T) {
	var receivedAuth string

	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		receivedAuth = r.Header.Get("Authorization")
		w.WriteHeader(http.StatusOK)
	}))
	defer server.Close()

	executor := NewHTTPExecutorWithClient(server.Client())
	state := entity.NewState()
	state.SetVar("token", "secret123")

	node := &entity.Node{
		ID:   "http_1",
		Type: string(value.NodeTypeHTTP),
		Config: map[string]any{
			"url": server.URL,
			"headers": map[string]any{
				"Authorization": "Bearer {{vars.token}}",
			},
		},
	}

	result, err := executor.Execute(context.Background(), node, state)
	if err != nil {
		t.Fatalf("Execute() error = %v", err)
	}
	if result.Error != nil {
		t.Fatalf("result.Error = %v", result.Error)
	}

	if receivedAuth != "Bearer secret123" {
		t.Errorf("Received Authorization = %v, want 'Bearer secret123'", receivedAuth)
	}
}

func TestHTTPExecutor_Execute_5xxRetryable(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusInternalServerError)
		w.Write([]byte("Internal Server Error"))
	}))
	defer server.Close()

	executor := NewHTTPExecutorWithClient(server.Client())
	state := entity.NewState()

	node := &entity.Node{
		ID:   "http_1",
		Type: string(value.NodeTypeHTTP),
		Config: map[string]any{
			"url": server.URL,
		},
	}

	result, err := executor.Execute(context.Background(), node, state)
	if err != nil {
		t.Fatalf("Execute() error = %v", err)
	}
	if result.Error == nil {
		t.Fatal("Expected error for 500 response")
	}

	// Should be a retryable error
	if result.Output != nil {
		t.Error("Output should be nil for error case")
	}
}

func TestHTTPExecutor_Execute_4xxNotRetryable(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusNotFound)
		w.Write([]byte("Not Found"))
	}))
	defer server.Close()

	executor := NewHTTPExecutorWithClient(server.Client())
	state := entity.NewState()

	node := &entity.Node{
		ID:   "http_1",
		Type: string(value.NodeTypeHTTP),
		Config: map[string]any{
			"url": server.URL,
		},
	}

	result, err := executor.Execute(context.Background(), node, state)
	if err != nil {
		t.Fatalf("Execute() error = %v", err)
	}
	if result.Error == nil {
		t.Fatal("Expected error for 404 response")
	}
}

func TestHTTPExecutor_Execute_MissingURL(t *testing.T) {
	executor := NewHTTPExecutor()
	state := entity.NewState()

	node := &entity.Node{
		ID:     "http_1",
		Type:   string(value.NodeTypeHTTP),
		Config: map[string]any{},
	}

	result, err := executor.Execute(context.Background(), node, state)
	if err != nil {
		t.Fatalf("Execute() should not return error, got %v", err)
	}
	if result.Error == nil {
		t.Error("Expected result.Error for missing URL")
	}
}

func TestHTTPExecutor_Execute_BodyTemplate(t *testing.T) {
	var receivedBody string

	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		body := make([]byte, r.ContentLength)
		r.Body.Read(body)
		receivedBody = string(body)
		w.WriteHeader(http.StatusOK)
	}))
	defer server.Close()

	executor := NewHTTPExecutorWithClient(server.Client())
	state := entity.NewState()
	state.SetVar("query", "test search")

	node := &entity.Node{
		ID:   "http_1",
		Type: string(value.NodeTypeHTTP),
		Config: map[string]any{
			"method":        "POST",
			"url":           server.URL,
			"body_template": `{"query": "{{vars.query}}", "limit": 10}`,
		},
	}

	result, err := executor.Execute(context.Background(), node, state)
	if err != nil {
		t.Fatalf("Execute() error = %v", err)
	}
	if result.Error != nil {
		t.Fatalf("result.Error = %v", result.Error)
	}

	expected := `{"query": "test search", "limit": 10}`
	if receivedBody != expected {
		t.Errorf("Received body = %v, want %v", receivedBody, expected)
	}
}

func TestHTTPExecutor_Execute_PlainTextResponse(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "text/plain")
		w.Write([]byte("Hello, World!"))
	}))
	defer server.Close()

	executor := NewHTTPExecutorWithClient(server.Client())
	state := entity.NewState()

	node := &entity.Node{
		ID:   "http_1",
		Type: string(value.NodeTypeHTTP),
		Config: map[string]any{
			"url": server.URL,
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
	if output["body"] != "Hello, World!" {
		t.Errorf("body = %v, want 'Hello, World!'", output["body"])
	}
}

func TestHTTPExecutor_Execute_DefaultMethod(t *testing.T) {
	var receivedMethod string

	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		receivedMethod = r.Method
		w.WriteHeader(http.StatusOK)
	}))
	defer server.Close()

	executor := NewHTTPExecutorWithClient(server.Client())
	state := entity.NewState()

	node := &entity.Node{
		ID:   "http_1",
		Type: string(value.NodeTypeHTTP),
		Config: map[string]any{
			"url": server.URL,
			// No method specified - should default to GET
		},
	}

	result, err := executor.Execute(context.Background(), node, state)
	if err != nil {
		t.Fatalf("Execute() error = %v", err)
	}
	if result.Error != nil {
		t.Fatalf("result.Error = %v", result.Error)
	}

	if receivedMethod != "GET" {
		t.Errorf("Method = %v, want 'GET'", receivedMethod)
	}
}

func TestHTTPExecutor_Execute_ResolvesCredentialTemplateForTelegram(t *testing.T) {
	var receivedPath string

	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		receivedPath = r.URL.Path
		w.WriteHeader(http.StatusOK)
	}))
	defer server.Close()

	executor := NewHTTPExecutorWithClientAndResolver(
		server.Client(),
		&mockCredentialResolver{provider: "telegram", apiKey: "bot-token-123"},
	)
	state := entity.NewState()

	node := &entity.Node{
		ID:   "http_telegram_send",
		Type: string(value.NodeTypeHTTP),
		Config: map[string]any{
			"provider":      "telegram",
			"credential_id": "cred-telegram",
			"method":        "POST",
			"url":           server.URL + "/bot{{credentials.telegram_token}}/sendMessage",
			"body":          `{"text":"hello"}`,
		},
	}

	ctx := port.WithTenantID(context.Background(), "tenant-1")
	result, err := executor.Execute(ctx, node, state)
	if err != nil {
		t.Fatalf("Execute() error = %v", err)
	}
	if result.Error != nil {
		t.Fatalf("result.Error = %v", result.Error)
	}

	if receivedPath != "/botbot-token-123/sendMessage" {
		t.Errorf("Received path = %v, want '/botbot-token-123/sendMessage'", receivedPath)
	}
}

func TestHTTPExecutor_Execute_InferBearerAuthFromCredential(t *testing.T) {
	var receivedAuth string

	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		receivedAuth = r.Header.Get("Authorization")
		w.WriteHeader(http.StatusOK)
	}))
	defer server.Close()

	executor := NewHTTPExecutorWithClientAndResolver(
		server.Client(),
		&mockCredentialResolver{provider: "gmail", apiKey: "gmail-token-123"},
	)
	state := entity.NewState()
	node := &entity.Node{
		ID:   "http_gmail",
		Type: string(value.NodeTypeHTTP),
		Config: map[string]any{
			"provider":      "gmail",
			"credential_id": "cred-gmail",
			"url":           server.URL,
		},
	}

	ctx := port.WithTenantID(context.Background(), "tenant-1")
	result, err := executor.Execute(ctx, node, state)
	if err != nil {
		t.Fatalf("Execute() error = %v", err)
	}
	if result.Error != nil {
		t.Fatalf("result.Error = %v", result.Error)
	}
	if receivedAuth != "Bearer gmail-token-123" {
		t.Errorf("Authorization = %v, want Bearer gmail-token-123", receivedAuth)
	}
}
