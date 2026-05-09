package gateway

import (
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"

	"github.com/forgegraph/engine/adapter/executor"
	"github.com/forgegraph/engine/domain"
)

func TestGeminiClientCompleteParsesResponse(t *testing.T) {
	var gotKey string
	var gotPath string
	var gotPayload map[string]any
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		gotKey = r.Header.Get("x-goog-api-key")
		gotPath = r.URL.Path
		if err := json.NewDecoder(r.Body).Decode(&gotPayload); err != nil {
			t.Fatalf("decode request: %v", err)
		}
		w.Header().Set("Content-Type", "application/json")
		_, _ = w.Write([]byte(`{
			"candidates": [{
				"content": {"parts": [{"text": "Legacy can run on Gemini."}]},
				"finishReason": "STOP"
			}],
			"modelVersion": "gemini-2.5-flash",
			"usageMetadata": {
				"promptTokenCount": 7,
				"candidatesTokenCount": 5,
				"totalTokenCount": 12
			}
		}`))
	}))
	defer server.Close()
	t.Setenv("GEMINI_API_BASE_URL", server.URL)

	client := NewGeminiClientWithKey("gemini-key")
	response, err := client.Complete(context.Background(), &executor.LLMRequest{
		Provider:     "google",
		Model:        "gemini-2.5-flash",
		Prompt:       "Run Legacy.",
		SystemPrompt: "System.",
		Temperature:  0.25,
		MaxTokens:    128,
		LLMMode:      "byok",
	})

	if err != nil {
		t.Fatalf("Complete() error = %v", err)
	}
	if gotKey != "gemini-key" {
		t.Fatalf("x-goog-api-key = %q, want gemini-key", gotKey)
	}
	if gotPath != "/models/gemini-2.5-flash:generateContent" {
		t.Fatalf("path = %q", gotPath)
	}
	if response.Provider != "google" || response.Content != "Legacy can run on Gemini." {
		t.Fatalf("response = %#v", response)
	}
	if response.Usage == nil || response.Usage.TotalTokens != 12 {
		t.Fatalf("usage = %#v", response.Usage)
	}
	if response.FinishReason != "STOP" {
		t.Fatalf("finish reason = %q", response.FinishReason)
	}
	if _, ok := gotPayload["systemInstruction"].(map[string]any); !ok {
		t.Fatalf("systemInstruction missing from payload: %#v", gotPayload)
	}
}

func TestGeminiClientRateLimitIsRetryable(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		w.Header().Set("Retry-After", "2")
		w.WriteHeader(http.StatusTooManyRequests)
		_, _ = w.Write([]byte(`{"error":{"message":"slow down","status":"RESOURCE_EXHAUSTED"}}`))
	}))
	defer server.Close()
	t.Setenv("GEMINI_API_BASE_URL", server.URL)

	_, err := NewGeminiClientWithKey("key").Complete(context.Background(), &executor.LLMRequest{
		Model:  "gemini-2.5-flash",
		Prompt: "hello",
	})

	if err == nil {
		t.Fatal("expected error")
	}
	if !domain.IsRetryable(err) {
		t.Fatalf("expected retryable error, got %T %v", err, err)
	}
	if domain.RetryCodeFromError(err) != "rate_limited" {
		t.Fatalf("retry code = %q", domain.RetryCodeFromError(err))
	}
}

func TestMultiProviderRoutesGoogle(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.Header.Get("x-goog-api-key") != "resolved-google-key" {
			t.Fatalf("missing resolved google key")
		}
		_, _ = w.Write([]byte(`{"candidates":[{"content":{"parts":[{"text":"done"}]}}]}`))
	}))
	defer server.Close()
	t.Setenv("GEMINI_API_BASE_URL", server.URL)

	resolver := &staticCredentialResolver{provider: "google", apiKey: "resolved-google-key"}
	client := NewMultiProviderClient(resolver, "")
	response, err := client.Complete(context.Background(), &executor.LLMRequest{
		Provider:     "google",
		CredentialID: "credential-1",
		TenantID:     "tenant-1",
		Model:        "gemini-2.5-flash",
		Prompt:       "hello",
	})

	if err != nil {
		t.Fatalf("Complete() error = %v", err)
	}
	if response.Provider != "google" || strings.TrimSpace(response.Content) != "done" {
		t.Fatalf("response = %#v", response)
	}
}

type staticCredentialResolver struct {
	provider string
	apiKey   string
}

func (r *staticCredentialResolver) Resolve(_ context.Context, _ string, _ string) (string, string, error) {
	return r.provider, r.apiKey, nil
}
