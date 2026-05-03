package main

import (
	"os"
	"path/filepath"
	"regexp"
	"strings"
	"testing"
)

func TestEngineDoesNotImportDirectDurablePersistenceClients(t *testing.T) {
	forbiddenImports := []string{
		`"database/sql"`,
		`"gorm.io/`,
		`"github.com/jackc/pgx`,
		`"github.com/lib/pq"`,
		`"github.com/jmoiron/sqlx"`,
		`"go.mongodb.org/mongo-driver`,
		`"github.com/dgraph-io/badger`,
		`"go.etcd.io/bbolt"`,
	}

	forEachGoSource(t, func(path string, source string) {
		if strings.HasSuffix(path, ".pb.go") {
			return
		}
		if filepath.Base(path) == "architecture_enforcement_test.go" {
			return
		}
		for _, pattern := range forbiddenImports {
			if strings.Contains(source, pattern) {
				t.Fatalf("engine source %s imports durable persistence client %s; durable state is backend-owned", path, pattern)
			}
		}
	})
}

func TestEngineKeepsCheckpointStateOnlyInApprovedInMemoryScopes(t *testing.T) {
	checkpointMapPattern := regexp.MustCompile(`(?m)\bcheckpoints\s+map\[string\]`)
	allowed := []string{
		filepath.FromSlash("adapter/repository/memory_run_repository.go"),
		filepath.FromSlash("application/usecase/scheduler_test_helpers_test.go"),
		filepath.FromSlash("application/usecase/scheduler_test.go"),
		filepath.FromSlash("tests/e2e/tool_side_effect_diagnostics_test.go"),
	}

	forEachGoSource(t, func(path string, source string) {
		if !checkpointMapPattern.MatchString(source) {
			return
		}
		rel := relativeEnginePath(t, path)
		for _, allowedPath := range allowed {
			if rel == allowedPath {
				return
			}
		}
		t.Fatalf("engine source %s stores checkpoint state outside approved in-memory/test scopes", rel)
	})
}

func TestCriticalStateMutationEventsHaveRuntimeIntentPaths(t *testing.T) {
	schedulerPath := filepath.Join(engineRoot(t), "application", "usecase", "scheduler.go")
	sourceBytes, err := os.ReadFile(schedulerPath)
	if err != nil {
		t.Fatalf("read scheduler: %v", err)
	}
	source := string(sourceBytes)

	requiredRuntimeIntentPaths := []string{
		"publishPauseRunIntent",
		"publishAckRunResumedIntent",
		"publishNodeCompletedIntent",
		"publishRetryOperationIntent",
		"publishToolExecutionStatusIntent",
	}
	for _, symbol := range requiredRuntimeIntentPaths {
		if !strings.Contains(source, "func (s *Scheduler) "+symbol+"(") {
			t.Fatalf("scheduler is missing backend-owned runtime intent path %s", symbol)
		}
	}

	for _, plainEvent := range []string{
		"EventTypeRunPaused",
		"EventTypeRunResumed",
		"EventTypeRunCompleted",
		"EventTypeRunFailed",
	} {
		if !strings.Contains(source, plainEvent) {
			t.Fatalf("scheduler no longer exposes %s; update architecture enforcement test with the new state boundary", plainEvent)
		}
	}
}

func TestHttpRepositoryCriticalWritesPublishRuntimeIntents(t *testing.T) {
	repositoryPath := filepath.Join(engineRoot(t), "adapter", "repository", "http_run_repository.go")
	sourceBytes, err := os.ReadFile(repositoryPath)
	if err != nil {
		t.Fatalf("read http repository: %v", err)
	}
	source := string(sourceBytes)

	for _, intentType := range []string{
		`"set_run_status"`,
		`"store_checkpoint"`,
	} {
		if !strings.Contains(source, intentType) {
			t.Fatalf("http run repository missing runtime intent %s; critical writes must go through backend-owned outcomes", intentType)
		}
	}
	if strings.Contains(source, "ENGINE_DIRECT_RUNTIME_WRITES_ENABLED") {
		t.Fatalf("engine repository must not contain a direct durable write escape hatch")
	}
}

func forEachGoSource(t *testing.T, visit func(path string, source string)) {
	t.Helper()
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
			return nil
		}
		if !strings.HasSuffix(entry.Name(), ".go") {
			return nil
		}
		sourceBytes, readErr := os.ReadFile(path)
		if readErr != nil {
			return readErr
		}
		visit(path, string(sourceBytes))
		return nil
	})
	if err != nil {
		t.Fatalf("walk engine source: %v", err)
	}
}

func relativeEnginePath(t *testing.T, path string) string {
	t.Helper()
	rel, err := filepath.Rel(engineRoot(t), path)
	if err != nil {
		t.Fatalf("relative path for %s: %v", path, err)
	}
	return rel
}

func engineRoot(t *testing.T) string {
	t.Helper()
	wd, err := os.Getwd()
	if err != nil {
		t.Fatalf("get working directory: %v", err)
	}
	return wd
}
