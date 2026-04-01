package tool

// BuiltinTools returns a list of prebuilt tool definitions.
func BuiltinTools() []Definition {
	return []Definition{
		{
			Name:        "vector.search",
			Version:     "1.0.0",
			Description: "Vector database search (HTTP)",
			Kind:        "http",
			InputSchema: map[string]any{
				"type":                 "object",
				"additionalProperties": true,
			},
			HTTP: &HTTPToolConfig{
				URL:    "${VECTOR_SEARCH_URL}",
				Method: "POST",
			},
		},
		{
			Name:        "search.web",
			Version:     "1.0.0",
			Description: "Web search API (HTTP)",
			Kind:        "http",
			InputSchema: map[string]any{
				"type":                 "object",
				"additionalProperties": true,
			},
			HTTP: &HTTPToolConfig{
				URL:    "${WEB_SEARCH_URL}",
				Method: "POST",
			},
		},
		{
			Name:        "internal.http",
			Version:     "1.0.0",
			Description: "Internal service adapter (HTTP)",
			Kind:        "http",
			InputSchema: map[string]any{
				"type":                 "object",
				"additionalProperties": true,
			},
			HTTP: &HTTPToolConfig{
				URL:    "${INTERNAL_SERVICE_URL}",
				Method: "POST",
			},
		},
	}
}
