package main

import (
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"os"
	"path/filepath"
	"runtime"
	"strings"
	"testing"
	"time"
)

func TestParseConfigExpandsGateEDefaults(t *testing.T) {
	cfg, err := ParseConfig([]string{"--dry-run", "--gate", "E"})
	if err != nil {
		t.Fatalf("ParseConfig returned error: %v", err)
	}
	if cfg.Tenants != 25 {
		t.Fatalf("tenants = %d, want 25", cfg.Tenants)
	}
	if cfg.Agents != 500 {
		t.Fatalf("agents = %d, want 500", cfg.Agents)
	}
	if cfg.RunsPerTenant != 20 {
		t.Fatalf("runs per tenant = %d, want 20", cfg.RunsPerTenant)
	}
	if cfg.WSClients != 500 {
		t.Fatalf("ws clients = %d, want 500", cfg.WSClients)
	}
	if !cfg.WithHITL || !cfg.WithMemory || !cfg.WithAccounting || !cfg.DuplicateEventStorm || !cfg.ReconnectStorm || !cfg.LLMThrottling {
		t.Fatalf("gate E did not enable required feature coverage: %+v", cfg)
	}
}

func TestBuildWorkloadPlanDistributesAgentsAndRuns(t *testing.T) {
	startedAt := time.Date(2026, 5, 5, 12, 0, 0, 0, time.UTC)
	cfg := Config{
		Tenants:           25,
		Agents:            500,
		RunsPerTenant:     20,
		TenantEmailDomain: defaultTenantEmailDomain,
		Password:          defaultPassword,
	}
	plan, err := BuildWorkloadPlan(cfg, nil, startedAt)
	if err != nil {
		t.Fatalf("BuildWorkloadPlan returned error: %v", err)
	}
	if len(plan.Tenants) != 25 || len(plan.Agents) != 500 || len(plan.Runs) != 500 {
		t.Fatalf("unexpected sizes: tenants=%d agents=%d runs=%d", len(plan.Tenants), len(plan.Agents), len(plan.Runs))
	}
	if strings.Contains(plan.Tenants[0].Email, "T") {
		t.Fatalf("generated tenant email must be lowercase for auth replay: %s", plan.Tenants[0].Email)
	}
	for _, tenant := range plan.Tenants {
		if tenant.AgentCount != 20 {
			t.Fatalf("tenant %d agent count = %d, want 20", tenant.Index, tenant.AgentCount)
		}
		if tenant.RunCount != 20 {
			t.Fatalf("tenant %d run count = %d, want 20", tenant.Index, tenant.RunCount)
		}
	}
}

func TestWriteTenantManifestDoesNotMutateCredentials(t *testing.T) {
	startedAt := time.Date(2026, 5, 5, 12, 0, 0, 0, time.UTC)
	plan, err := BuildWorkloadPlan(Config{
		Tenants:           1,
		Agents:            1,
		RunsPerTenant:     1,
		TenantEmailDomain: defaultTenantEmailDomain,
		Password:          defaultPassword,
	}, nil, startedAt)
	if err != nil {
		t.Fatalf("BuildWorkloadPlan returned error: %v", err)
	}
	writer, err := NewArtifactWriter(t.TempDir(), startedAt)
	if err != nil {
		t.Fatalf("NewArtifactWriter returned error: %v", err)
	}
	if err := writer.WriteTenantManifest(plan); err != nil {
		t.Fatalf("WriteTenantManifest returned error: %v", err)
	}
	if plan.Tenants[0].Password != defaultPassword {
		t.Fatalf("plan password was mutated by manifest redaction")
	}
	data, err := os.ReadFile(writer.Paths.TenantManifest)
	if err != nil {
		t.Fatalf("read tenant manifest: %v", err)
	}
	var manifest WorkloadPlan
	if err := json.Unmarshal(data, &manifest); err != nil {
		t.Fatalf("decode tenant manifest: %v", err)
	}
	if manifest.Tenants[0].Password != "" || manifest.Tenants[0].AccessToken != "" {
		t.Fatalf("tenant manifest leaked credentials: %+v", manifest.Tenants[0])
	}
}

func TestEnsureTenantWithCredentialsSkipsRegister(t *testing.T) {
	registerCalls := 0
	server := httptest.NewServer(http.HandlerFunc(func(writer http.ResponseWriter, request *http.Request) {
		switch request.URL.Path {
		case "/api/auth/register":
			registerCalls++
			http.Error(writer, "register should not be called", http.StatusTeapot)
		case "/api/auth/login":
			writer.Header().Set("Content-Type", "application/json")
			_, _ = writer.Write([]byte(`{"access":"tenant-token"}`))
		default:
			http.NotFound(writer, request)
		}
	}))
	defer server.Close()

	client := NewAPIClient(Config{BaseURL: server.URL, RequestTimeout: time.Second}, nil)
	tenant := TenantPlan{
		Email:           "existing@example.com",
		Password:        "password",
		FromCredentials: true,
		OrganizationID:  "org-1",
		GraphVersionID:  "version-1",
	}

	if err := client.EnsureTenant(context.Background(), &tenant); err != nil {
		t.Fatalf("EnsureTenant returned error: %v", err)
	}
	if registerCalls != 0 {
		t.Fatalf("register calls = %d, want 0", registerCalls)
	}
	if tenant.AccessToken != "tenant-token" {
		t.Fatalf("access token = %q, want tenant-token", tenant.AccessToken)
	}
}

func TestPercentilesUseNearestRank(t *testing.T) {
	summary := SummarizeSamples([]float64{400, 100, 200, 300})
	if summary.P50 != 200 {
		t.Fatalf("p50 = %.0f, want 200", summary.P50)
	}
	if summary.P95 != 400 {
		t.Fatalf("p95 = %.0f, want 400", summary.P95)
	}
	if summary.Max != 400 {
		t.Fatalf("max = %.0f, want 400", summary.Max)
	}
}

func TestEvaluateGateERequiresDisruptionHooksAndNoCostDrift(t *testing.T) {
	cfg, err := ParseConfig([]string{
		"--dry-run",
		"--gate", "E",
		"--engine-restart-hook", "echo engine",
		"--backend-worker-restart-hook", "echo worker",
		"--redis-degrade-hook", "echo degrade",
		"--redis-recover-hook", "echo recover",
		"--llm-throttle-on-hook", "echo throttle-on",
		"--llm-throttle-off-hook", "echo throttle-off",
	})
	if err != nil {
		t.Fatalf("ParseConfig returned error: %v", err)
	}
	metrics := BuildMetrics(
		[]float64{100, 120, 140},
		[]float64{150, 160, 170},
		[]float64{0.4, 0.5, 0.6},
		[]float64{200, 250, 300},
	)
	metrics.AcceptedMutations = 100
	metrics.DuplicateCallbackAttempts = 25
	metrics.ReconnectCount = 500
	metrics.DuplicateCostDrift = 1
	hooks := []HookRecord{
		{Name: "engine-restart", ExitCode: 0},
		{Name: "backend-worker-restart", ExitCode: 0},
		{Name: "redis-degrade", ExitCode: 0},
		{Name: "redis-recover", ExitCode: 0},
		{Name: "llm-throttle-on", ExitCode: 0},
		{Name: "llm-throttle-off", ExitCode: 0},
	}
	startedAt := time.Date(2026, 5, 5, 0, 0, 0, 0, time.UTC)
	_, passed, reasons := EvaluateGate(cfg, metrics, hooks, startedAt, startedAt.Add(8*time.Hour))
	if passed {
		t.Fatal("Gate E passed despite duplicate cost drift")
	}
	if !strings.Contains(strings.Join(reasons, "\n"), "cost duplicate drift") {
		t.Fatalf("missing cost drift reason: %v", reasons)
	}
	metrics.DuplicateCostDrift = 0
	_, passed, reasons = EvaluateGate(cfg, metrics, hooks, startedAt, startedAt.Add(8*time.Hour))
	if !passed {
		t.Fatalf("Gate E did not pass with all requirements satisfied: %v", reasons)
	}
}

func TestSignEngineEventMatchesHMACContract(t *testing.T) {
	signature := signEngineEvent("secret", "1710000000000", []byte(`{"type":"node_completed"}`))
	if signature != "39a7e5417c41d71f70ea3aba0dbb6f5a8733107737bd82db04e16fe2f4f6805c" {
		t.Fatalf("signature = %s", signature)
	}
}

func TestCanonicalEventChecksumIgnoresChecksumField(t *testing.T) {
	envelope := map[string]any{
		"schema_version": 2,
		"source":         "engine",
		"type":           "node.completed",
		"event_id":       "evt-1",
		"payload":        map[string]any{"node_id": "agent-1"},
	}
	first, err := canonicalEventChecksum(envelope)
	if err != nil {
		t.Fatalf("canonicalEventChecksum returned error: %v", err)
	}
	envelope["checksum"] = "ignored"
	second, err := canonicalEventChecksum(envelope)
	if err != nil {
		t.Fatalf("canonicalEventChecksum returned error: %v", err)
	}
	if first != second {
		t.Fatalf("checksum changed when checksum field was present")
	}
}

func TestSanitizeCommandRedactsSecrets(t *testing.T) {
	command := sanitizeCommand([]string{
		"loadgen",
		"--engine-callback-secret",
		"secret-value",
		"--password=tenant-password",
		"--tenants",
		"2",
	})
	if strings.Contains(command, "secret-value") || strings.Contains(command, "tenant-password") {
		t.Fatalf("sanitized command leaked a secret: %s", command)
	}
	if !strings.Contains(command, "--engine-callback-secret [REDACTED]") {
		t.Fatalf("sanitized command did not preserve redacted callback-secret flag: %s", command)
	}
	if !strings.Contains(command, "--password=[REDACTED]") {
		t.Fatalf("sanitized command did not preserve redacted password flag: %s", command)
	}
}

func TestRunHookRecordsSuccess(t *testing.T) {
	command := "echo loadgen-hook-ok"
	if runtime.GOOS == "windows" {
		command = "Write-Output loadgen-hook-ok"
	}
	record := RunHook(context.Background(), "test-hook", command)
	if record.ExitCode != 0 {
		t.Fatalf("hook exit code = %d, error=%s output=%s", record.ExitCode, record.Error, record.Output)
	}
	if !strings.Contains(record.Output, "loadgen-hook-ok") {
		t.Fatalf("hook output = %q", record.Output)
	}
}

func TestRunConfiguredHooksOrder(t *testing.T) {
	command := "echo ok"
	if runtime.GOOS == "windows" {
		command = "Write-Output ok"
	}
	cfg := Config{
		LLMThrottleOnHook:        command,
		EngineRestartHook:        command,
		BackendWorkerRestartHook: command,
		RedisDegradeHook:         command,
		RedisRecoverHook:         command,
		LLMThrottleOffHook:       command,
	}
	records := RunConfiguredHooks(context.Background(), cfg, nil)
	want := []string{
		"llm-throttle-on",
		"engine-restart",
		"backend-worker-restart",
		"redis-degrade",
		"redis-recover",
		"llm-throttle-off",
	}
	if len(records) != len(want) {
		t.Fatalf("records length = %d, want %d", len(records), len(want))
	}
	for index, name := range want {
		if records[index].Name != name {
			t.Fatalf("record %d name = %s, want %s", index, records[index].Name, name)
		}
		if records[index].ExitCode != 0 {
			t.Fatalf("record %s exit = %d", name, records[index].ExitCode)
		}
	}
}

func TestDryRunWritesReportArtifacts(t *testing.T) {
	outputDir := filepath.Join(t.TempDir(), "loadgen")
	cfg, err := ParseConfig([]string{
		"--dry-run",
		"--tenants", "2",
		"--agents", "4",
		"--runs-per-tenant", "2",
		"--output-dir", outputDir,
	})
	if err != nil {
		t.Fatalf("ParseConfig returned error: %v", err)
	}
	report, err := Run(context.Background(), cfg, []string{"loadgen", "--dry-run"})
	if err != nil {
		t.Fatalf("Run returned error: %v", err)
	}
	if !report.Passed {
		t.Fatalf("dry-run smoke should pass without a gate: %+v", report)
	}
	if _, err := os.Stat(report.Artifacts.TenantManifest); err != nil {
		t.Fatalf("tenant manifest missing: %v", err)
	}
	if _, err := os.Stat(report.Artifacts.MetricsSummary); err != nil {
		t.Fatalf("metrics summary missing: %v", err)
	}
}
