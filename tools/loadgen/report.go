package main

import (
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"strings"
	"time"
)

type ArtifactPaths struct {
	Root           string `json:"root"`
	RequestsJSONL  string `json:"requests_jsonl"`
	RunsJSONL      string `json:"runs_jsonl"`
	WSEventsJSONL  string `json:"ws_events_jsonl"`
	HookTimeline   string `json:"hook_timeline"`
	MetricsSummary string `json:"metrics_summary"`
	TenantManifest string `json:"tenant_manifest"`
}

type GateRequirement struct {
	Name   string `json:"name"`
	Passed bool   `json:"passed"`
	Detail string `json:"detail"`
}

type LoadgenReport struct {
	SchemaVersion   string            `json:"schema_version"`
	Gate            string            `json:"gate,omitempty"`
	Passed          bool              `json:"passed"`
	ClaimStatus     string            `json:"claim_status"`
	StartedAt       time.Time         `json:"started_at"`
	CompletedAt     time.Time         `json:"completed_at"`
	Command         string            `json:"command"`
	Target          map[string]any    `json:"target"`
	Features        map[string]bool   `json:"features"`
	Environment     map[string]string `json:"environment"`
	Metrics         Metrics           `json:"metrics"`
	Requirements    []GateRequirement `json:"requirements"`
	BlockingReasons []string          `json:"blocking_reasons"`
	Artifacts       ArtifactPaths     `json:"artifacts"`
	ReportPaths     []string          `json:"report_paths"`
}

func EvaluateGate(cfg Config, metrics Metrics, hooks []HookRecord, startedAt, completedAt time.Time) ([]GateRequirement, bool, []string) {
	if cfg.Gate == "" {
		req := []GateRequirement{{Name: "ungated smoke", Passed: true, Detail: "No capacity gate requested."}}
		return req, true, nil
	}
	spec := gateSpecs[cfg.Gate]
	requirements := []GateRequirement{
		requirement("target agent count", cfg.Agents >= spec.TargetAgents, fmt.Sprintf("agents=%d target=%d", cfg.Agents, spec.TargetAgents)),
		requirement("tenant count", cfg.Tenants >= spec.MinTenants, fmt.Sprintf("tenants=%d minimum=%d", cfg.Tenants, spec.MinTenants)),
		requirement("runs per tenant", cfg.RunsPerTenant >= spec.RunsPerTenant, fmt.Sprintf("runs_per_tenant=%d minimum=%d", cfg.RunsPerTenant, spec.RunsPerTenant)),
		requirement("duration", completedAt.Sub(startedAt) >= spec.Duration, fmt.Sprintf("observed=%s required=%s", completedAt.Sub(startedAt).Round(time.Second), spec.Duration)),
		requirement("backend API p95", metrics.BackendAPILatencyMS.P95 > 0 && metrics.BackendAPILatencyMS.P95 < 300, fmt.Sprintf("p95=%.2fms target<300ms", metrics.BackendAPILatencyMS.P95)),
		requirement("event ingestion p95", metrics.EventIngestionMS.P95 > 0 && metrics.EventIngestionMS.P95 < 500, fmt.Sprintf("p95=%.2fms target<500ms", metrics.EventIngestionMS.P95)),
		requirement("projection lag p95", metrics.ProjectionLagSeconds.P95 > 0 && metrics.ProjectionLagSeconds.P95 < 2, fmt.Sprintf("p95=%.2fs target<2s", metrics.ProjectionLagSeconds.P95)),
		requirement("websocket delivery p95", metrics.WSDeliveryLatencyMS.P95 == 0 || metrics.WSDeliveryLatencyMS.P95 < 1000, fmt.Sprintf("p95=%.2fms target<1000ms", metrics.WSDeliveryLatencyMS.P95)),
		requirement("dead-letter rate", deadLetterRate(metrics) < 0.001, fmt.Sprintf("rate=%.5f target<0.001", deadLetterRate(metrics))),
		requirement("silent drops", metrics.SilentDrops == 0, fmt.Sprintf("silent_drops=%d", metrics.SilentDrops)),
		requirement("tenant isolation", metrics.TenantIsolationFailures == 0, fmt.Sprintf("failures=%d checks=%d", metrics.TenantIsolationFailures, metrics.TenantIsolationChecks)),
		requirement("cost duplicate drift", metrics.DuplicateCostDrift == 0, fmt.Sprintf("duplicate_cost_drift=%d", metrics.DuplicateCostDrift)),
	}
	if spec.RequireHITL {
		requirements = append(requirements, requirement("HITL coverage", cfg.WithHITL, "--with-hitl"))
	}
	if spec.RequireMemory {
		requirements = append(requirements, requirement("memory coverage", cfg.WithMemory, "--with-memory"))
		requirements = append(requirements, requirement("memory duplicate drift", metrics.MemoryDuplicateDrift == 0, fmt.Sprintf("memory_duplicate_drift=%d", metrics.MemoryDuplicateDrift)))
	}
	if spec.RequireAccounting {
		requirements = append(requirements, requirement("accounting coverage", cfg.WithAccounting, "--with-accounting"))
	}
	if spec.RequireDuplicates {
		requirements = append(requirements, requirement("duplicate callback storm", cfg.DuplicateEventStorm, "--duplicate-event-storm"))
		requirements = append(requirements, requirement("duplicate callback attempts", metrics.DuplicateCallbackAttempts > 0, fmt.Sprintf("duplicate_callback_attempts=%d", metrics.DuplicateCallbackAttempts)))
	}
	if spec.RequireReconnects {
		requirements = append(requirements, requirement("reconnect storm", cfg.ReconnectStorm, "--reconnect-storm"))
		requirements = append(requirements, requirement("reconnect attempts", metrics.ReconnectCount > 0, fmt.Sprintf("reconnect_count=%d", metrics.ReconnectCount)))
		requirements = append(requirements, requirement("websocket delivery samples", metrics.WSDeliveryLatencyMS.Count > 0, fmt.Sprintf("ws_delivery_samples=%d", metrics.WSDeliveryLatencyMS.Count)))
	}
	if spec.RequireLLMThrottling {
		requirements = append(requirements, requirement("LLM throttling coverage", cfg.LLMThrottling, "--llm-throttling"))
	}
	if spec.RequireDisruptions {
		requirements = append(requirements, requiredHookRequirements(hooks)...)
	}

	var reasons []string
	passed := true
	for _, req := range requirements {
		if !req.Passed {
			passed = false
			reasons = append(reasons, req.Name+": "+req.Detail)
		}
	}
	return requirements, passed, reasons
}

func requirement(name string, passed bool, detail string) GateRequirement {
	return GateRequirement{Name: name, Passed: passed, Detail: detail}
}

func deadLetterRate(metrics Metrics) float64 {
	if metrics.AcceptedMutations == 0 {
		if metrics.DeadLetters == 0 {
			return 0
		}
		return 1
	}
	return float64(metrics.DeadLetters) / float64(metrics.AcceptedMutations)
}

func requiredHookRequirements(hooks []HookRecord) []GateRequirement {
	required := map[string]bool{
		"engine-restart":         false,
		"backend-worker-restart": false,
		"redis-degrade":          false,
		"redis-recover":          false,
		"llm-throttle-on":        false,
		"llm-throttle-off":       false,
	}
	for _, hook := range hooks {
		if _, ok := required[hook.Name]; ok && hook.ExitCode == 0 {
			required[hook.Name] = true
		}
	}
	names := make([]string, 0, len(required))
	for name := range required {
		names = append(names, name)
	}
	sortStrings(names)
	requirements := make([]GateRequirement, 0, len(names))
	for _, name := range names {
		requirements = append(requirements, requirement("disruption hook "+name, required[name], "Gate E requires explicit successful disruption hook evidence"))
	}
	return requirements
}

func sortStrings(values []string) {
	for i := 1; i < len(values); i++ {
		for j := i; j > 0 && values[j] < values[j-1]; j-- {
			values[j], values[j-1] = values[j-1], values[j]
		}
	}
}

func NewReport(cfg Config, command []string, startedAt, completedAt time.Time, metrics Metrics, hooks []HookRecord, artifacts ArtifactPaths) LoadgenReport {
	requirements, passed, reasons := EvaluateGate(cfg, metrics, hooks, startedAt, completedAt)
	claimStatus := "not capacity evidence"
	if cfg.Gate != "" {
		claimStatus = "claim blocked"
		if passed && cfg.Gate == "E" {
			claimStatus = "eligible for one Gate E evidence slot; public claim still needs three consecutive passing checked-in Gate E reports"
		} else if passed {
			claimStatus = "gate passed; 500-agent claim remains blocked until three Gate E passes"
		}
	}
	if cfg.DryRun {
		passed = cfg.Gate == ""
		claimStatus = "dry run only; not release evidence"
		if cfg.Gate != "" {
			reasons = append(reasons, "dry run does not count as capacity evidence")
		}
	}
	return LoadgenReport{
		SchemaVersion: "forgegraph.loadgen.report.v1",
		Gate:          cfg.Gate,
		Passed:        passed,
		ClaimStatus:   claimStatus,
		StartedAt:     startedAt,
		CompletedAt:   completedAt,
		Command:       sanitizeCommand(command),
		Target: map[string]any{
			"tenants":          cfg.Tenants,
			"agents":           cfg.Agents,
			"runs_per_tenant":  cfg.RunsPerTenant,
			"ws_clients":       cfg.WSClients,
			"duration_seconds": int64(cfg.Duration.Seconds()),
		},
		Features: map[string]bool{
			"hitl":                  cfg.WithHITL,
			"memory":                cfg.WithMemory,
			"accounting":            cfg.WithAccounting,
			"duplicate_event_storm": cfg.DuplicateEventStorm,
			"reconnect_storm":       cfg.ReconnectStorm,
			"llm_throttling":        cfg.LLMThrottling,
		},
		Environment: map[string]string{
			"base_url": cfg.BaseURL,
		},
		Metrics:         metrics,
		Requirements:    requirements,
		BlockingReasons: reasons,
		Artifacts:       artifacts,
	}
}

func sanitizeCommand(command []string) string {
	if len(command) == 0 {
		return ""
	}
	redacted := make([]string, 0, len(command))
	sensitiveFlags := map[string]bool{
		"--engine-callback-secret": true,
		"--password":               true,
	}
	for i := 0; i < len(command); i++ {
		part := command[i]
		if sensitiveFlags[part] {
			redacted = append(redacted, part)
			if i+1 < len(command) {
				redacted = append(redacted, "[REDACTED]")
				i++
			}
			continue
		}
		replaced := false
		for flag := range sensitiveFlags {
			prefix := flag + "="
			if strings.HasPrefix(part, prefix) {
				redacted = append(redacted, prefix+"[REDACTED]")
				replaced = true
				break
			}
		}
		if replaced {
			continue
		}
		redacted = append(redacted, part)
	}
	return strings.Join(redacted, " ")
}

func WriteReports(report LoadgenReport, cfg Config) (LoadgenReport, error) {
	if err := os.MkdirAll(report.Artifacts.Root, 0o755); err != nil {
		return report, err
	}
	summaryPath := filepath.Join(report.Artifacts.Root, "metrics-summary.json")
	if err := writeJSON(summaryPath, report); err != nil {
		return report, err
	}
	report.ReportPaths = append(report.ReportPaths, summaryPath)
	if cfg.Gate != "" {
		date := report.CompletedAt.UTC().Format("2006-01-02")
		base := fmt.Sprintf("gate-%s-%s", strings.ToLower(cfg.Gate), date)
		if err := os.MkdirAll(cfg.CapacityReportDir, 0o755); err != nil {
			return report, err
		}
		jsonPath := filepath.Join(cfg.CapacityReportDir, base+".json")
		mdPath := filepath.Join(cfg.CapacityReportDir, base+".md")
		if err := writeJSON(jsonPath, report); err != nil {
			return report, err
		}
		if err := os.WriteFile(mdPath, []byte(renderMarkdownReport(report)), 0o644); err != nil {
			return report, err
		}
		report.ReportPaths = append(report.ReportPaths, jsonPath, mdPath)
	}
	if len(report.ReportPaths) > 0 {
		if err := writeJSON(summaryPath, report); err != nil {
			return report, err
		}
	}
	return report, nil
}

func writeJSON(path string, value any) error {
	data, err := json.MarshalIndent(value, "", "  ")
	if err != nil {
		return err
	}
	data = append(data, '\n')
	return os.WriteFile(path, data, 0o644)
}

func renderMarkdownReport(report LoadgenReport) string {
	var builder strings.Builder
	fmt.Fprintf(&builder, "# ForgeGraph Capacity Gate %s - %s\n\n", fallback(report.Gate, "Smoke"), report.CompletedAt.UTC().Format("2006-01-02"))
	fmt.Fprintf(&builder, "Status: **%s**\n\n", passFail(report.Passed))
	fmt.Fprintf(&builder, "Claim status: %s\n\n", report.ClaimStatus)
	fmt.Fprintf(&builder, "Command:\n\n```bash\n%s\n```\n\n", report.Command)
	fmt.Fprintf(&builder, "## Target\n\n")
	fmt.Fprintf(&builder, "- Tenants: %v\n", report.Target["tenants"])
	fmt.Fprintf(&builder, "- Agents: %v\n", report.Target["agents"])
	fmt.Fprintf(&builder, "- Runs per tenant: %v\n", report.Target["runs_per_tenant"])
	fmt.Fprintf(&builder, "- WebSocket clients: %v\n", report.Target["ws_clients"])
	fmt.Fprintf(&builder, "- Duration seconds: %v\n\n", report.Target["duration_seconds"])
	fmt.Fprintf(&builder, "## Environment\n\n")
	for _, key := range []string{"base_url"} {
		fmt.Fprintf(&builder, "- %s: `%s`\n", key, report.Environment[key])
	}
	fmt.Fprintf(&builder, "## Feature Coverage\n\n")
	for _, key := range []string{"hitl", "memory", "accounting", "duplicate_event_storm", "reconnect_storm", "llm_throttling"} {
		fmt.Fprintf(&builder, "- %s: %t\n", key, report.Features[key])
	}
	fmt.Fprintf(&builder, "\n## SLOs\n\n| Requirement | Status | Detail |\n| --- | --- | --- |\n")
	for _, req := range report.Requirements {
		fmt.Fprintf(&builder, "| %s | %s | %s |\n", req.Name, passFail(req.Passed), strings.ReplaceAll(req.Detail, "|", "\\|"))
	}
	if len(report.BlockingReasons) > 0 {
		fmt.Fprintf(&builder, "\n## Blocking Reasons\n\n")
		for _, reason := range report.BlockingReasons {
			fmt.Fprintf(&builder, "- %s\n", reason)
		}
	}
	fmt.Fprintf(&builder, "\n## Artifacts\n\n")
	fmt.Fprintf(&builder, "- Raw root: `%s`\n", report.Artifacts.Root)
	fmt.Fprintf(&builder, "- Per-request JSONL: `%s`\n", report.Artifacts.RequestsJSONL)
	fmt.Fprintf(&builder, "- Per-run JSONL: `%s`\n", report.Artifacts.RunsJSONL)
	fmt.Fprintf(&builder, "- WS event JSONL: `%s`\n", report.Artifacts.WSEventsJSONL)
	fmt.Fprintf(&builder, "- Hook timeline: `%s`\n", report.Artifacts.HookTimeline)
	fmt.Fprintf(&builder, "- Tenant manifest: `%s`\n", report.Artifacts.TenantManifest)
	return builder.String()
}

func passFail(passed bool) string {
	if passed {
		return "PASS"
	}
	return "FAIL"
}

func fallback(value, fallbackValue string) string {
	if value == "" {
		return fallbackValue
	}
	return value
}
