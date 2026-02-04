package entity

import "strings"

// ExecutionPolicy defines guardrails for egress and LLM usage.
type ExecutionPolicy struct {
	HTTPAllowlist    []string
	HTTPDenylist     []string
	HTTPDefaultDeny  bool
	AllowedProviders []string
	AllowedModels    []string
}

func PolicyFromMetadata(metadata map[string]any) *ExecutionPolicy {
	if metadata == nil {
		return nil
	}
	rawPolicy, ok := metadata["policy"].(map[string]any)
	if !ok {
		return nil
	}

	policy := &ExecutionPolicy{}
	if httpRaw, ok := rawPolicy["http"].(map[string]any); ok {
		policy.HTTPAllowlist = extractStringList(httpRaw["allowlist"])
		policy.HTTPDenylist = extractStringList(httpRaw["denylist"])
		if val, ok := httpRaw["default_deny"].(bool); ok {
			policy.HTTPDefaultDeny = val
		}
	}
	if llmRaw, ok := rawPolicy["llm"].(map[string]any); ok {
		policy.AllowedProviders = normalizeLower(extractStringList(llmRaw["allowed_providers"]))
		policy.AllowedModels = extractStringList(llmRaw["allowed_models"])
	}

	if len(policy.HTTPAllowlist) == 0 &&
		len(policy.HTTPDenylist) == 0 &&
		!policy.HTTPDefaultDeny &&
		len(policy.AllowedProviders) == 0 &&
		len(policy.AllowedModels) == 0 {
		return nil
	}

	return policy
}

func extractStringList(value any) []string {
	rawList, ok := value.([]any)
	if !ok {
		if castList, ok := value.([]string); ok {
			return castList
		}
		return nil
	}
	result := make([]string, 0, len(rawList))
	for _, item := range rawList {
		if str, ok := item.(string); ok {
			result = append(result, str)
		}
	}
	return result
}

func normalizeLower(items []string) []string {
	if len(items) == 0 {
		return nil
	}
	normalized := make([]string, 0, len(items))
	for _, item := range items {
		trimmed := strings.TrimSpace(strings.ToLower(item))
		if trimmed == "" {
			continue
		}
		normalized = append(normalized, trimmed)
	}
	return normalized
}
