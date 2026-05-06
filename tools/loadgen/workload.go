package main

import (
	"fmt"
	"math"
	"strings"
	"time"
)

type WorkloadPlan struct {
	Tenants []TenantPlan `json:"tenants"`
	Agents  []AgentPlan  `json:"agents"`
	Runs    []RunPlan    `json:"runs"`
}

type TenantPlan struct {
	Index           int    `json:"index"`
	Email           string `json:"email"`
	Password        string `json:"-"`
	AccessToken     string `json:"-"`
	FromCredentials bool   `json:"-"`
	OrganizationID  string `json:"organization_id,omitempty"`
	GraphVersionID  string `json:"graph_version_id,omitempty"`
	AgentCount      int    `json:"agent_count"`
	RunCount        int    `json:"run_count"`
}

type AgentPlan struct {
	Index       int `json:"index"`
	TenantIndex int `json:"tenant_index"`
}

type RunPlan struct {
	Index       int    `json:"index"`
	TenantIndex int    `json:"tenant_index"`
	AgentIndex  int    `json:"agent_index"`
	CommandID   string `json:"command_id"`
}

func BuildWorkloadPlan(cfg Config, credentials []TenantCredential, startedAt time.Time) (WorkloadPlan, error) {
	if len(credentials) > 0 && len(credentials) < cfg.Tenants {
		return WorkloadPlan{}, fmt.Errorf("tenant credentials file contains %d tenants, but --tenants requires %d", len(credentials), cfg.Tenants)
	}

	plan := WorkloadPlan{
		Tenants: make([]TenantPlan, cfg.Tenants),
		Agents:  make([]AgentPlan, cfg.Agents),
		Runs:    make([]RunPlan, 0, cfg.Tenants*cfg.RunsPerTenant),
	}
	for tenantIndex := 0; tenantIndex < cfg.Tenants; tenantIndex++ {
		tenant := TenantPlan{
			Index:    tenantIndex,
			Email:    generatedTenantEmail(tenantIndex, cfg.TenantEmailDomain, startedAt),
			Password: cfg.Password,
		}
		if len(credentials) > tenantIndex {
			credential := credentials[tenantIndex]
			tenant.Email = credential.Email
			tenant.Password = credential.Password
			tenant.AccessToken = credential.AccessToken
			tenant.FromCredentials = true
			tenant.OrganizationID = credential.OrganizationID
			tenant.GraphVersionID = credential.GraphVersionID
		}
		plan.Tenants[tenantIndex] = tenant
	}

	for agentIndex := 0; agentIndex < cfg.Agents; agentIndex++ {
		tenantIndex := agentIndex % cfg.Tenants
		plan.Agents[agentIndex] = AgentPlan{
			Index:       agentIndex,
			TenantIndex: tenantIndex,
		}
		plan.Tenants[tenantIndex].AgentCount++
	}

	totalRuns := cfg.Tenants * cfg.RunsPerTenant
	for runIndex := 0; runIndex < totalRuns; runIndex++ {
		tenantIndex := runIndex % cfg.Tenants
		agentIndex := runIndex % max(cfg.Agents, 1)
		plan.Runs = append(plan.Runs, RunPlan{
			Index:       runIndex,
			TenantIndex: tenantIndex,
			AgentIndex:  agentIndex,
			CommandID:   fmt.Sprintf("loadgen:run-start:%s:%04d", startedAt.UTC().Format("20060102T150405"), runIndex),
		})
		plan.Tenants[tenantIndex].RunCount++
	}
	return plan, nil
}

func generatedTenantEmail(index int, domain string, startedAt time.Time) string {
	return strings.ToLower(
		fmt.Sprintf(
			"loadgen-%s-tenant-%03d@%s",
			startedAt.UTC().Format("20060102T150405"),
			index+1,
			domain,
		),
	)
}

func max(a, b int) int {
	if a > b {
		return a
	}
	return b
}

type Metrics struct {
	BackendAPILatencyMS       LatencySummary `json:"backend_api_latency_ms"`
	EventIngestionMS          LatencySummary `json:"event_ingestion_latency_ms"`
	ProjectionLagSeconds      LatencySummary `json:"projection_lag_seconds"`
	WSDeliveryLatencyMS       LatencySummary `json:"ws_delivery_latency_ms"`
	AcceptedMutations         int            `json:"accepted_mutations"`
	VisibleMutations          int            `json:"visible_mutations"`
	DeadLetters               int            `json:"dead_letters"`
	SilentDrops               int            `json:"silent_drops"`
	TenantIsolationChecks     int            `json:"tenant_isolation_checks"`
	TenantIsolationFailures   int            `json:"tenant_isolation_failures"`
	DuplicateCallbackAttempts int            `json:"duplicate_callback_attempts"`
	DuplicateCostDrift        int            `json:"duplicate_cost_drift"`
	MemoryDuplicateDrift      int            `json:"memory_duplicate_drift"`
	ReconnectCount            int            `json:"reconnect_count"`
	RunsStarted               int            `json:"runs_started"`
	RunsCompleted             int            `json:"runs_completed"`
	RunsFailed                int            `json:"runs_failed"`
}

type LatencySummary struct {
	Count int     `json:"count"`
	P50   float64 `json:"p50"`
	P95   float64 `json:"p95"`
	Max   float64 `json:"max"`
}

func SummarizeSamples(samples []float64) LatencySummary {
	if len(samples) == 0 {
		return LatencySummary{}
	}
	values := append([]float64(nil), samples...)
	sortFloat64s(values)
	return LatencySummary{
		Count: len(values),
		P50:   percentile(values, 50),
		P95:   percentile(values, 95),
		Max:   values[len(values)-1],
	}
}

func percentile(sorted []float64, p float64) float64 {
	if len(sorted) == 0 {
		return 0
	}
	if p <= 0 {
		return sorted[0]
	}
	if p >= 100 {
		return sorted[len(sorted)-1]
	}
	rank := int(math.Ceil((p / 100) * float64(len(sorted))))
	if rank < 1 {
		rank = 1
	}
	if rank > len(sorted) {
		rank = len(sorted)
	}
	return sorted[rank-1]
}

func sortFloat64s(values []float64) {
	for i := 1; i < len(values); i++ {
		for j := i; j > 0 && values[j] < values[j-1]; j-- {
			values[j], values[j-1] = values[j-1], values[j]
		}
	}
}

func BuildMetrics(apiLatency, ingestionLatency, projectionLag, wsLatency []float64) Metrics {
	return Metrics{
		BackendAPILatencyMS:  SummarizeSamples(apiLatency),
		EventIngestionMS:     SummarizeSamples(ingestionLatency),
		ProjectionLagSeconds: SummarizeSamples(projectionLag),
		WSDeliveryLatencyMS:  SummarizeSamples(wsLatency),
	}
}
