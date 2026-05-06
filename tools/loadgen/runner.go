package main

import (
	"context"
	"fmt"
	"net/http"
	"sync"
	"time"
)

type runRecord struct {
	RunID       string    `json:"run_id"`
	TenantIndex int       `json:"tenant_index"`
	AgentIndex  int       `json:"agent_index"`
	StartedAt   time.Time `json:"started_at"`
	Status      string    `json:"status"`
	Error       string    `json:"error,omitempty"`
}

func Run(ctx context.Context, cfg Config, command []string) (LoadgenReport, error) {
	startedAt := time.Now().UTC()
	credentials, err := LoadTenantCredentials(cfg.TenantCredentialsFile)
	if err != nil {
		return LoadgenReport{}, err
	}
	plan, err := BuildWorkloadPlan(cfg, credentials, startedAt)
	if err != nil {
		return LoadgenReport{}, err
	}
	writer, err := NewArtifactWriter(cfg.OutputDir, startedAt)
	if err != nil {
		return LoadgenReport{}, err
	}
	if err := writer.WriteTenantManifest(plan); err != nil {
		return LoadgenReport{}, err
	}

	var hooks []HookRecord
	var metrics Metrics
	if cfg.DryRun {
		metrics = syntheticDryRunMetrics(cfg)
		completedAt := time.Now().UTC()
		report := NewReport(cfg, command, startedAt, completedAt, metrics, hooks, writer.Paths)
		return WriteReports(report, cfg)
	}

	runCtx, cancel := context.WithCancel(ctx)
	defer cancel()
	client := NewAPIClient(cfg, writer)
	apiSamples := make([]float64, 0)
	ingestionSamples := make([]float64, 0)
	projectionLagSamples := make([]float64, 0)
	wsSamples := make([]float64, 0)
	startedRuns := make([]struct {
		runID  string
		tenant TenantPlan
	}, 0, len(plan.Runs))

	for index := range plan.Tenants {
		if err := client.EnsureTenant(runCtx, &plan.Tenants[index]); err != nil {
			return LoadgenReport{}, fmt.Errorf("tenant setup failed for %s: %w", plan.Tenants[index].Email, err)
		}
	}
	if err := writer.WriteTenantManifest(plan); err != nil {
		return LoadgenReport{}, err
	}

	deadLetterBaseline := 0
	for _, tenant := range plan.Tenants {
		_, _, deadLetters := client.PollReadAPIs(runCtx, tenant)
		deadLetterBaseline += deadLetters
	}

	hooks = append(hooks, RunNamedHooks(runCtx, cfg, writer, "llm-throttle-on")...)

	var wsWG sync.WaitGroup
	var wsMu sync.Mutex
	wsClients := cfg.WSClients
	wsReady := make(chan struct{}, max(wsClients, 1))
	for i := 0; i < wsClients; i++ {
		tenant := plan.Tenants[i%len(plan.Tenants)]
		wsWG.Add(1)
		go func(index int, tenant TenantPlan) {
			defer wsWG.Done()
			signaledReady := false
			ready := func() {
				if signaledReady {
					return
				}
				signaledReady = true
				wsReady <- struct{}{}
			}
			samples, reconnects, err := client.ConnectOrganizationWS(runCtx, tenant, 0, cfg.ReconnectStorm, ready, writer)
			if !signaledReady {
				ready()
			}
			wsMu.Lock()
			defer wsMu.Unlock()
			wsSamples = append(wsSamples, samples...)
			metrics.ReconnectCount += reconnects
			if err != nil {
				_ = writer.AppendJSONL(writer.Paths.WSEventsJSONL, map[string]any{
					"client": index,
					"error":  err.Error(),
				})
			}
		}(i, tenant)
	}
	if wsClients > 0 {
		deadline := time.NewTimer(minDuration(10*time.Second, cfg.RequestTimeout))
		readyCount := 0
	waitForWS:
		for readyCount < wsClients {
			select {
			case <-wsReady:
				readyCount++
			case <-deadline.C:
				break waitForWS
			case <-runCtx.Done():
				break waitForWS
			}
		}
		deadline.Stop()
	}

	for _, run := range plan.Runs {
		tenant := plan.Tenants[run.TenantIndex]
		runID, durationMS, err := client.StartRun(runCtx, tenant, run)
		apiSamples = append(apiSamples, durationMS)
		record := runRecord{
			RunID:       runID,
			TenantIndex: tenant.Index,
			AgentIndex:  run.AgentIndex,
			StartedAt:   time.Now().UTC(),
			Status:      "started",
		}
		if err != nil {
			record.Status = "failed"
			record.Error = err.Error()
			metrics.RunsFailed++
			_ = writer.AppendJSONL(writer.Paths.RunsJSONL, record)
			continue
		}
		metrics.AcceptedMutations++
		metrics.RunsStarted++
		startedRuns = append(startedRuns, struct {
			runID  string
			tenant TenantPlan
		}{runID: runID, tenant: tenant})
		_ = writer.AppendJSONL(writer.Paths.RunsJSONL, record)

		if cfg.WithMemory {
			durationMS, err := client.CreateMemoryObservation(runCtx, tenant, runID, run.Index)
			apiSamples = append(apiSamples, durationMS)
			if err == nil {
				metrics.AcceptedMutations++
			}
		}
		if cfg.WithHITL {
			durationMS, err := client.PauseRunForHITL(runCtx, tenant, runID, run.Index)
			apiSamples = append(apiSamples, durationMS)
			if err == nil {
				metrics.AcceptedMutations++
			}
			durationMS, err = client.ResumeRun(runCtx, tenant, runID, run.Index)
			apiSamples = append(apiSamples, durationMS)
			if err == nil {
				metrics.AcceptedMutations++
			}
		}
		if cfg.WithAccounting {
			eventID := fmt.Sprintf("loadgen-accounting-%s-%04d", runID, run.Index)
			durationMS, err := client.PostEngineNodeCompleted(runCtx, cfg, tenant, runID, eventID)
			ingestionSamples = append(ingestionSamples, durationMS)
			if err == nil {
				metrics.AcceptedMutations++
			}
			if cfg.DuplicateEventStorm {
				metrics.DuplicateCallbackAttempts++
				durationMS, _ = client.PostEngineNodeCompleted(runCtx, cfg, tenant, runID, eventID)
				ingestionSamples = append(ingestionSamples, durationMS)
			}
		}
	}

	hooks = append(hooks, RunNamedHooks(runCtx, cfg, writer, "engine-restart", "backend-worker-restart", "redis-degrade", "redis-recover")...)

	observeDeadline := time.Now().Add(minDuration(cfg.ObservationDeadline, cfg.Duration))
	for time.Now().Before(observeDeadline) {
		currentDeadLetters := 0
		for _, tenant := range plan.Tenants {
			latencies, lag, deadLetters := client.PollReadAPIs(runCtx, tenant)
			apiSamples = append(apiSamples, latencies...)
			projectionLagSamples = append(projectionLagSamples, lag...)
			currentDeadLetters += deadLetters
		}
		if currentDeadLetters > deadLetterBaseline {
			metrics.DeadLetters = currentDeadLetters - deadLetterBaseline
		}
		if len(startedRuns) > 0 {
			break
		}
		time.Sleep(500 * time.Millisecond)
	}

	if len(startedRuns) > 0 {
		for _, startedRun := range startedRuns {
			if visibleRun(runCtx, client, startedRun.tenant, startedRun.runID) {
				metrics.VisibleMutations++
			}
		}
		if len(plan.Tenants) > 1 {
			metrics.TenantIsolationChecks++
			if !client.CheckTenantIsolation(runCtx, plan.Tenants[1].AccessToken, startedRuns[0].runID) {
				metrics.TenantIsolationFailures++
			}
		}
	}
	if metrics.VisibleMutations < metrics.RunsStarted {
		metrics.SilentDrops += metrics.RunsStarted - metrics.VisibleMutations
	}

	hooks = append(hooks, RunNamedHooks(runCtx, cfg, writer, "llm-throttle-off")...)

	if cfg.Duration > time.Since(startedAt) {
		timer := time.NewTimer(cfg.Duration - time.Since(startedAt))
		select {
		case <-ctx.Done():
			timer.Stop()
		case <-timer.C:
		}
	}
	cancel()
	wsWG.Wait()

	metrics.BackendAPILatencyMS = SummarizeSamples(apiSamples)
	metrics.EventIngestionMS = SummarizeSamples(ingestionSamples)
	metrics.ProjectionLagSeconds = SummarizeSamples(projectionLagSamples)
	metrics.WSDeliveryLatencyMS = SummarizeSamples(wsSamples)
	completedAt := time.Now().UTC()
	report := NewReport(cfg, command, startedAt, completedAt, metrics, hooks, writer.Paths)
	return WriteReports(report, cfg)
}

func visibleRun(ctx context.Context, client *APIClient, tenant TenantPlan, runID string) bool {
	result, err := client.doJSON(ctx, http.MethodGet, "/api/runs/"+runID, tenant.AccessToken, "", nil)
	return err == nil && result.StatusCode == http.StatusOK
}

func syntheticDryRunMetrics(cfg Config) Metrics {
	metrics := BuildMetrics(
		[]float64{50, 75, 100},
		[]float64{100, 150, 200},
		[]float64{0.25, 0.5, 0.75},
		[]float64{100, 250, 500},
	)
	metrics.AcceptedMutations = cfg.Tenants * cfg.RunsPerTenant
	metrics.VisibleMutations = metrics.AcceptedMutations
	if cfg.DuplicateEventStorm {
		metrics.DuplicateCallbackAttempts = max(1, cfg.Agents/10)
	}
	if cfg.ReconnectStorm {
		metrics.ReconnectCount = max(1, cfg.WSClients)
	}
	return metrics
}

func minDuration(a, b time.Duration) time.Duration {
	if a < b {
		return a
	}
	return b
}
