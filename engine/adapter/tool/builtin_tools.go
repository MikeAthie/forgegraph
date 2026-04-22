package tool

func BuiltinTools() []Definition {
	return []Definition{
		{
			Name:        "vector.search",
			Version:     "1.0.0",
			Category:    "internal",
			Description: "Vector database search (HTTP)",
			Visibility:  VisibilityInternal,
			InputSchema: map[string]any{
				"type":                 "object",
				"additionalProperties": true,
			},
			Execution: ExecutionConfig{
				Type:           "http",
				TimeoutSeconds: 30,
				HTTP: &HTTPToolConfig{
					URL:    "${VECTOR_SEARCH_URL}",
					Method: "POST",
				},
			},
			SideEffects: SideEffectConfig{Type: "read", Idempotent: true},
		},
		{
			Name:        "search.web",
			Version:     "1.0.0",
			Category:    "web",
			Description: "Web search API (HTTP)",
			Visibility:  VisibilityInternal,
			InputSchema: map[string]any{
				"type":                 "object",
				"additionalProperties": true,
			},
			Execution: ExecutionConfig{
				Type:           "http",
				TimeoutSeconds: 30,
				HTTP: &HTTPToolConfig{
					URL:    "${WEB_SEARCH_URL}",
					Method: "POST",
				},
			},
			SideEffects: SideEffectConfig{Type: "read", Idempotent: true},
		},
		{
			Name:        "internal.http",
			Version:     "1.0.0",
			Category:    "internal",
			Description: "Internal service adapter (HTTP)",
			Visibility:  VisibilityInternal,
			InputSchema: map[string]any{
				"type":                 "object",
				"additionalProperties": true,
			},
			Execution: ExecutionConfig{
				Type:           "http",
				TimeoutSeconds: 30,
				HTTP: &HTTPToolConfig{
					URL:    "${INTERNAL_SERVICE_URL}",
					Method: "POST",
				},
			},
			SideEffects: SideEffectConfig{Type: "external", Idempotent: true},
		},
	}
}
