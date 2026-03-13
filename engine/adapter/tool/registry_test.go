package tool

import (
	"os"
	"path/filepath"
	"testing"
)

func TestRegistryLoadDefinitionsRejectsInvalidRuntimeTool(t *testing.T) {
	reg := NewRegistry()

	err := reg.LoadDefinitions([]Definition{
		{
			Name:    "broken.tool",
			Version: "1.0.0",
			Kind:    "http",
		},
	})
	if err == nil {
		t.Fatal("expected invalid definition to fail")
	}
}

func TestRegistryRegisterOrderIsDeterministic(t *testing.T) {
	reg := NewRegistry()

	reg.Register(Definition{
		Name:    "search.web",
		Version: "1.0.0",
		Kind:    "http",
		HTTP: &HTTPToolConfig{
			URL:    "https://local.example.com/search",
			Method: "POST",
		},
	})
	reg.Register(Definition{
		Name:    "search.web",
		Version: "1.0.0",
		Kind:    "http",
		HTTP: &HTTPToolConfig{
			URL:    "https://remote.example.com/search",
			Method: "POST",
		},
	})

	def, ok := reg.Resolve("search.web", "1.0.0")
	if !ok {
		t.Fatal("expected search.web to resolve")
	}
	if def.HTTP == nil || def.HTTP.URL != "https://remote.example.com/search" {
		t.Fatalf("expected later registration to win, got %#v", def.HTTP)
	}
}

func TestRegistryLoadManifestsValidatesDefinitions(t *testing.T) {
	tmpDir := t.TempDir()
	manifestPath := filepath.Join(tmpDir, "broken.json")
	content := []byte(`{"tools":[{"name":"broken.tool","version":"1.0.0","kind":"http"}]}`)
	if err := os.WriteFile(manifestPath, content, 0o644); err != nil {
		t.Fatalf("write manifest: %v", err)
	}

	reg := NewRegistry()
	err := reg.LoadManifests(tmpDir)
	if err == nil {
		t.Fatal("expected manifest load to fail")
	}
}

func TestValidateDefinitionForRuntimeMode_BlocksExecInCloud(t *testing.T) {
	err := ValidateDefinitionForRuntimeMode(Definition{
		Name:    "danger.exec",
		Version: "1.0.0",
		Kind:    "exec",
		Exec: &ExecToolConfig{
			Command: "python",
		},
	}, RuntimeModeCloud)
	if err == nil {
		t.Fatal("expected exec definition to fail in cloud mode")
	}
}

func TestValidateDefinitionForRuntimeMode_AllowsExecInSelfHosted(t *testing.T) {
	err := ValidateDefinitionForRuntimeMode(Definition{
		Name:    "danger.exec",
		Version: "1.0.0",
		Kind:    "exec",
		Exec: &ExecToolConfig{
			Command: "python",
		},
	}, RuntimeModeSelfHosted)
	if err != nil {
		t.Fatalf("expected exec definition to be allowed in self-hosted mode, got %v", err)
	}
}
