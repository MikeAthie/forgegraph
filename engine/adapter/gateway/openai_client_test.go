package gateway

import (
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"

	"github.com/forgegraph/engine/adapter/executor"
)

func TestResolveOpenAIBaseURLDefaultsToOpenAI(t *testing.T) {
	t.Setenv("OPENAI_BASE_URL", "")
	t.Setenv("OPENAI_API_BASE_URL", "")

	if got := resolveOpenAIBaseURL(); got != "https://api.openai.com/v1" {
		t.Fatalf("expected default base URL, got %q", got)
	}
}

func TestResolveOpenAIBaseURLUsesOverride(t *testing.T) {
	t.Setenv("OPENAI_BASE_URL", "http://127.0.0.1:8011/v1/")
	t.Setenv("OPENAI_API_BASE_URL", "")

	if got := resolveOpenAIBaseURL(); got != "http://127.0.0.1:8011/v1" {
		t.Fatalf("expected env override, got %q", got)
	}
}

func TestOpenRouterClientUsesOpenAICompatibleChatCompletions(t *testing.T) {
	var gotPath string
	var gotAuth string
	var gotReferer string
	var gotTitle string
	var gotPayload map[string]any
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		gotPath = r.URL.Path
		gotAuth = r.Header.Get("Authorization")
		gotReferer = r.Header.Get("HTTP-Referer")
		gotTitle = r.Header.Get("X-Title")
		if err := json.NewDecoder(r.Body).Decode(&gotPayload); err != nil {
			t.Fatalf("decode request: %v", err)
		}
		w.Header().Set("Content-Type", "application/json")
		_, _ = w.Write([]byte(`{
			"choices": [{
				"message": {"content": "OpenRouter response"},
				"finish_reason": "stop"
			}],
			"model": "google/gemini-2.5-flash",
			"usage": {"prompt_tokens": 4, "completion_tokens": 3, "total_tokens": 7}
		}`))
	}))
	defer server.Close()
	t.Setenv("OPENROUTER_API_BASE_URL", server.URL)
	t.Setenv("OPENROUTER_HTTP_REFERER", "https://forgegraph.test")
	t.Setenv("OPENROUTER_APP_TITLE", "ForgeGraph Test")

	response, err := NewOpenRouterClientWithKey("openrouter-key").Complete(
		context.Background(),
		&executor.LLMRequest{
			Provider: "openrouter",
			Prompt:   "hello",
			Model:    "google/gemini-2.5-flash",
			LLMMode:  "byok",
		},
	)

	if err != nil {
		t.Fatalf("Complete() error = %v", err)
	}
	if gotPath != "/chat/completions" {
		t.Fatalf("path = %q", gotPath)
	}
	if gotAuth != "Bearer openrouter-key" {
		t.Fatalf("authorization = %q", gotAuth)
	}
	if gotReferer != "https://forgegraph.test" || gotTitle != "ForgeGraph Test" {
		t.Fatalf("OpenRouter headers referer=%q title=%q", gotReferer, gotTitle)
	}
	if gotPayload["model"] != "google/gemini-2.5-flash" {
		t.Fatalf("model = %#v", gotPayload["model"])
	}
	if response.Provider != "openrouter" || response.Content != "OpenRouter response" {
		t.Fatalf("response = %#v", response)
	}
	if response.Usage == nil || response.Usage.TotalTokens != 7 {
		t.Fatalf("usage = %#v", response.Usage)
	}
}

func TestOpenAIClientUsesMaxCompletionTokensForGPT5Family(t *testing.T) {
	var gotPayload map[string]any
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if err := json.NewDecoder(r.Body).Decode(&gotPayload); err != nil {
			t.Fatalf("decode request: %v", err)
		}
		w.Header().Set("Content-Type", "application/json")
		_, _ = w.Write([]byte(`{
			"choices": [{
				"message": {"content": "OK"},
				"finish_reason": "stop"
			}],
			"model": "gpt-5.4-mini-2026-03-17",
			"usage": {"prompt_tokens": 4, "completion_tokens": 3, "total_tokens": 7}
		}`))
	}))
	defer server.Close()
	t.Setenv("OPENAI_BASE_URL", server.URL)

	_, err := NewOpenAIClientWithKey("openai-key").Complete(
		context.Background(),
		&executor.LLMRequest{
			Provider:  "openai",
			Prompt:    "hello",
			Model:     "gpt-5.4-mini",
			MaxTokens: 32,
			LLMMode:   "system",
		},
	)

	if err != nil {
		t.Fatalf("Complete() error = %v", err)
	}
	if gotPayload["max_completion_tokens"] != float64(32) {
		t.Fatalf("max_completion_tokens = %#v", gotPayload["max_completion_tokens"])
	}
	if _, exists := gotPayload["max_tokens"]; exists {
		t.Fatalf("max_tokens should be omitted for GPT-5 family, payload=%#v", gotPayload)
	}
}

func TestOpenAIClientKeepsMaxTokensForGPT41Family(t *testing.T) {
	var gotPayload map[string]any
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if err := json.NewDecoder(r.Body).Decode(&gotPayload); err != nil {
			t.Fatalf("decode request: %v", err)
		}
		w.Header().Set("Content-Type", "application/json")
		_, _ = w.Write([]byte(`{
			"choices": [{
				"message": {"content": "OK"},
				"finish_reason": "stop"
			}],
			"model": "gpt-4.1-mini-2025-04-14",
			"usage": {"prompt_tokens": 4, "completion_tokens": 3, "total_tokens": 7}
		}`))
	}))
	defer server.Close()
	t.Setenv("OPENAI_BASE_URL", server.URL)

	_, err := NewOpenAIClientWithKey("openai-key").Complete(
		context.Background(),
		&executor.LLMRequest{
			Provider:  "openai",
			Prompt:    "hello",
			Model:     "gpt-4.1-mini",
			MaxTokens: 32,
			LLMMode:   "system",
		},
	)

	if err != nil {
		t.Fatalf("Complete() error = %v", err)
	}
	if gotPayload["max_tokens"] != float64(32) {
		t.Fatalf("max_tokens = %#v", gotPayload["max_tokens"])
	}
	if _, exists := gotPayload["max_completion_tokens"]; exists {
		t.Fatalf("max_completion_tokens should be omitted for GPT-4.1 family, payload=%#v", gotPayload)
	}
}

func TestOpenRouterClientReportsNumericErrorCode(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		w.WriteHeader(http.StatusPaymentRequired)
		_, _ = w.Write([]byte(`{
			"error": {
				"message": "Insufficient credits.",
				"code": 402
			}
		}`))
	}))
	defer server.Close()
	t.Setenv("OPENROUTER_API_BASE_URL", server.URL)

	_, err := NewOpenRouterClientWithKey("openrouter-key").Complete(
		context.Background(),
		&executor.LLMRequest{
			Provider: "openrouter",
			Prompt:   "hello",
			Model:    "google/gemini-2.5-flash",
			LLMMode:  "byok",
		},
	)

	if err == nil {
		t.Fatal("Complete() error = nil")
	}
	if got := err.Error(); got != "OpenRouter API error: Insufficient credits. (type: , code: 402)" {
		t.Fatalf("error = %q", got)
	}
}
