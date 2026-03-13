package gateway

import "testing"

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
