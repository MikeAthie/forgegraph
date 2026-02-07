package entity

import "testing"

func TestPolicyFromMetadata_ParsesProviderThrottleSettings(t *testing.T) {
	metadata := map[string]any{
		"policy": map[string]any{
			"providers": map[string]any{
				"default_min_interval_ms": 150,
				"min_interval_ms_by_provider": map[string]any{
					"openai":    80,
					"anthropic": 120,
				},
			},
		},
	}

	policy := PolicyFromMetadata(metadata)
	if policy == nil {
		t.Fatal("expected policy to be parsed")
	}
	if policy.ProviderMinIntervalMs != 150 {
		t.Fatalf("ProviderMinIntervalMs = %d, want 150", policy.ProviderMinIntervalMs)
	}
	if policy.ProviderMinIntervalByNameMs["openai"] != 80 {
		t.Fatalf("openai provider interval = %d, want 80", policy.ProviderMinIntervalByNameMs["openai"])
	}
	if policy.ProviderMinIntervalByNameMs["anthropic"] != 120 {
		t.Fatalf("anthropic provider interval = %d, want 120", policy.ProviderMinIntervalByNameMs["anthropic"])
	}
}

func TestPolicyFromMetadata_NoPolicyReturnsNil(t *testing.T) {
	if policy := PolicyFromMetadata(nil); policy != nil {
		t.Fatalf("expected nil policy for nil metadata, got %#v", policy)
	}
}
