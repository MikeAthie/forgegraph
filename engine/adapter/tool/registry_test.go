package tool

import (
	"os"
	"path/filepath"
	"testing"
)

func validHTTPDefinition(name string) Definition {
	return Definition{
		Name:        name,
		Version:     "1.0.0",
		Category:    "web",
		Description: "test tool",
		Visibility:  VisibilityPublic,
		InputSchema: map[string]any{"type": "object"},
		Execution: ExecutionConfig{
			Type:           "http",
			TimeoutSeconds: 10,
			HTTP: &HTTPToolConfig{
				URL:    "https://example.com/tool",
				Method: "POST",
			},
		},
		SideEffects: SideEffectConfig{Type: "read", Idempotent: true},
	}
}

func TestRegistryLoadDefinitionsRejectsInvalidRuntimeTool(t *testing.T) {
	reg := NewRegistry()

	err := reg.LoadDefinitions([]Definition{
		{
			Name:     "broken.tool",
			Version:  "1.0.0",
			Category: "web",
			Execution: ExecutionConfig{
				Type: "http",
			},
			SideEffects: SideEffectConfig{Type: "read", Idempotent: true},
		},
	})
	if err == nil {
		t.Fatal("expected invalid definition to fail")
	}
}

func TestRegistryRegisterOrderIsDeterministic(t *testing.T) {
	reg := NewRegistry()

	local := validHTTPDefinition("search.web")
	local.Execution.HTTP.URL = "https://local.example.com/search"
	reg.Register(local)

	remote := validHTTPDefinition("search.web")
	remote.Execution.HTTP.URL = "https://remote.example.com/search"
	reg.Register(remote)

	def, ok := reg.Resolve("search.web", "1.0.0")
	if !ok {
		t.Fatal("expected search.web to resolve")
	}
	if def.Execution.HTTP == nil || def.Execution.HTTP.URL != "https://remote.example.com/search" {
		t.Fatalf("expected later registration to win, got %#v", def.Execution.HTTP)
	}
}

func TestRegistryLoadManifestsValidatesDefinitions(t *testing.T) {
	tmpDir := t.TempDir()
	manifestPath := filepath.Join(tmpDir, "broken.json")
	content := []byte(`{"tools":[{"name":"broken.tool","version":"1.0.0","category":"web","execution":{"type":"http"},"side_effects":{"type":"read","idempotent":true}}]}`)
	if err := os.WriteFile(manifestPath, content, 0o644); err != nil {
		t.Fatalf("write manifest: %v", err)
	}

	reg := NewRegistry()
	err := reg.LoadManifests(tmpDir)
	if err == nil {
		t.Fatal("expected manifest load to fail")
	}
}

func TestValidateDefinitionForRuntimeMode_RejectsMissingLocalHandler(t *testing.T) {
	err := ValidateDefinitionForRuntimeMode(Definition{
		Name:        "danger.local",
		Version:     "1.0.0",
		Category:    "internal",
		InputSchema: map[string]any{"type": "object"},
		Execution: ExecutionConfig{
			Type:  "local",
			Local: &LocalToolConfig{},
		},
		SideEffects: SideEffectConfig{Type: "write", Idempotent: false},
	}, RuntimeModeCloud)
	if err == nil {
		t.Fatal("expected local definition to fail without handler")
	}
}

func TestValidateDefinitionForRuntimeMode_AllowsLocalInCloud(t *testing.T) {
	err := ValidateDefinitionForRuntimeMode(Definition{
		Name:        "safe.local",
		Version:     "1.0.0",
		Category:    "internal",
		InputSchema: map[string]any{"type": "object"},
		Execution: ExecutionConfig{
			Type:  "local",
			Local: &LocalToolConfig{Handler: "echo"},
		},
		SideEffects: SideEffectConfig{Type: "read", Idempotent: true},
	}, RuntimeModeCloud)
	if err != nil {
		t.Fatalf("expected local definition to be allowed in cloud mode, got %v", err)
	}
}

func TestValidateDefinitionForRuntimeMode_RejectsNegativeMaxResultSize(t *testing.T) {
	def := validHTTPDefinition("large.result.tool")
	def.MaxResultSize = -1
	err := ValidateDefinitionForRuntimeMode(def, RuntimeModeSelfHosted)
	if err == nil {
		t.Fatal("expected negative max_result_size_chars to fail validation")
	}
}
