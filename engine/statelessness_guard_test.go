package main

import (
	"os"
	"path/filepath"
	"strings"
	"testing"
)

func TestEngineStatelessnessGuardMatchesDurableMemoryPolicy(t *testing.T) {
	forbiddenPatterns := []string{
		"RedisMemoryStore",
		"SaveSummary",
		"SaveFact",
		"PersistMemory",
		"MemoryUsage",
		"summarization_worker",
	}
	allowlist := loadEngineStatelessnessAllowlist(t)

	root := engineRoot(t)
	err := filepath.WalkDir(root, func(path string, entry os.DirEntry, walkErr error) error {
		if walkErr != nil {
			return walkErr
		}
		if entry.IsDir() {
			switch entry.Name() {
			case ".git", "tmp", "vendor":
				return filepath.SkipDir
			}
			if strings.HasSuffix(filepath.ToSlash(path), "testsprite_tests/tmp") {
				return filepath.SkipDir
			}
			return nil
		}
		if entry.Name() == "engine.exe" {
			return nil
		}

		sourceBytes, readErr := os.ReadFile(path)
		if readErr != nil {
			return readErr
		}
		source := string(sourceBytes)
		rel := filepath.ToSlash(relativeEnginePath(t, path))
		for _, pattern := range forbiddenPatterns {
			if strings.Contains(source, pattern) && !allowlist[pattern+"\t"+"engine/"+rel] {
				t.Fatalf(
					"engine statelessness violation: %s appears in engine/%s without scripts/engine_statelessness_allowlist.txt approval",
					pattern,
					rel,
				)
			}
		}
		return nil
	})
	if err != nil {
		t.Fatalf("walk engine source: %v", err)
	}
}

func loadEngineStatelessnessAllowlist(t *testing.T) map[string]bool {
	t.Helper()
	root := filepath.Dir(engineRoot(t))
	allowlistPath := filepath.Join(root, "scripts", "engine_statelessness_allowlist.txt")
	sourceBytes, err := os.ReadFile(allowlistPath)
	if err != nil {
		t.Fatalf("read statelessness allowlist: %v", err)
	}

	allowlist := make(map[string]bool)
	for _, line := range strings.Split(string(sourceBytes), "\n") {
		trimmed := strings.TrimSpace(line)
		if trimmed == "" || strings.HasPrefix(trimmed, "#") {
			continue
		}
		fields := strings.Split(trimmed, "\t")
		if len(fields) < 2 {
			t.Fatalf("malformed statelessness allowlist row: %q", line)
		}
		allowlist[fields[0]+"\t"+filepath.ToSlash(fields[1])] = true
	}
	return allowlist
}
