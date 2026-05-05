//go:build legacy_timing
// +build legacy_timing

package e2e

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"os"
	"path/filepath"
	"runtime"
	"sort"
	"strings"
	"sync"
	"testing"
	"time"

	"github.com/forgegraph/engine/adapter/executor"
	"github.com/forgegraph/engine/adapter/store"
	"github.com/forgegraph/engine/adapter/tool"
	"github.com/forgegraph/engine/application/port"
	"github.com/forgegraph/engine/application/usecase"
	"github.com/forgegraph/engine/domain"
	"github.com/forgegraph/engine/domain/entity"
	"github.com/forgegraph/engine/domain/value"
)

const (
	diagnosticToolNodeID   = "diagnostic_tool"
	diagnosticOutputNodeID = "final_output"
)

func TestCrashAfterSideEffectBeforePublishDetectsDuplicateRisk(t *testing.T) {
	external := newFakeExternalSystem()
	toolExecutor := newDiagnosticToolExecutor(external)
	publisher := &recordingRuntimeIntentPublisher{}
	repo := newDiagnosticRepository()

	graphJSON := diagnosticGraphJSON(diagnosticToolConfig{
		Mode:        "fail_once_after_side_effect",
		OperationID: "charge-invoice-001",
		ExecutionID: "exec-crash-after-side-effect",
	}, 1, false)

	runID := "diagnostic-crash-after-side-effect"
	runScheduler(t, repo, toolExecutor, publisher, runID, graphJSON, string(value.RunStatusFailed))
	runScheduler(t, repo, toolExecutor, publisher, runID, graphJSON, string(value.RunStatusSucceeded))

	summary := diagnosticSummary{
		DuplicateSideEffectsDetected: external.effectCount("charge-invoice-001") > 1,
		ToolsWithoutIdempotency:      []string{},
		AmbiguousExecutionCases:      []string{},
	}
	t.Logf("tool_side_effect_diagnostic=%s", mustJSON(summary))
	t.Logf(
		"crash_after_side_effect evidence run_id=%s operation_id=%s external_call_count=%d external_effect_count=%d published_node_completed=%d calls=%s",
		runID,
		"charge-invoice-001",
		external.callCount("charge-invoice-001"),
		external.effectCount("charge-invoice-001"),
		publisher.countByNodeID(diagnosticToolNodeID),
		mustJSON(external.callsForOperation("charge-invoice-001")),
	)

	if !summary.DuplicateSideEffectsDetected {
		t.Fatalf("expected diagnostic to expose duplicate external side effects after retry/restart")
	}
	diagnosticFailIfStrict(t, "duplicate side effect detected after external success but before node_completed intent")
}

func TestRetryWithoutIdempotencyKeyIsBlockedBeforeDuplicateSideEffect(t *testing.T) {
	external := newFakeExternalSystem()
	toolExecutor := newDiagnosticToolExecutor(external)
	repo := newDiagnosticRepository()

	graphJSON := diagnosticGraphJSON(diagnosticToolConfig{
		Mode:        "retryable_once_after_side_effect",
		OperationID: "send-email-001",
		ExecutionID: "exec-retry-without-idempotency",
	}, 2, false)

	runID := "diagnostic-retry-without-idempotency"
	runScheduler(t, repo, toolExecutor, nil, runID, graphJSON, string(value.RunStatusFailed))

	summary := diagnosticSummary{
		DuplicateSideEffectsDetected: external.effectCount("send-email-001") > 1,
		ToolsWithoutIdempotency:      []string{"diagnostic:no_idempotency_key"},
		AmbiguousExecutionCases:      []string{},
	}
	t.Logf("tool_side_effect_diagnostic=%s", mustJSON(summary))
	t.Logf(
		"retry_without_idempotency evidence run_id=%s operation_id=%s external_call_count=%d external_effect_count=%d calls=%s",
		runID,
		"send-email-001",
		external.callCount("send-email-001"),
		external.effectCount("send-email-001"),
		mustJSON(external.callsForOperation("send-email-001")),
	)

	if summary.DuplicateSideEffectsDetected {
		t.Fatalf("unsafe tool retry should be blocked before duplicate side effects")
	}
}

func TestRetryWithIdempotencyKeyDeduplicatesExternalSideEffect(t *testing.T) {
	external := newFakeExternalSystem()
	toolExecutor := newDiagnosticToolExecutor(external)
	repo := newDiagnosticRepository()

	graphJSON := diagnosticGraphJSON(diagnosticToolConfig{
		Mode:           "retryable_once_after_side_effect",
		OperationID:    "payment-capture-001",
		IdempotencyKey: "tool-call-payment-capture-001",
		ExecutionID:    "exec-retry-with-idempotency",
	}, 2, false)

	runID := "diagnostic-retry-with-idempotency"
	runScheduler(t, repo, toolExecutor, nil, runID, graphJSON, string(value.RunStatusSucceeded))

	summary := diagnosticSummary{
		DuplicateSideEffectsDetected: false,
		ToolsWithoutIdempotency:      []string{},
		AmbiguousExecutionCases:      []string{},
	}
	t.Logf("tool_side_effect_diagnostic=%s", mustJSON(summary))
	t.Logf(
		"retry_with_idempotency evidence run_id=%s operation_id=%s idempotency_key=%s external_call_count=%d external_effect_count=%d calls=%s",
		runID,
		"payment-capture-001",
		"tool-call-payment-capture-001",
		external.callCount("payment-capture-001"),
		external.effectCount("payment-capture-001"),
		mustJSON(external.callsForOperation("payment-capture-001")),
	)

	if external.callCount("payment-capture-001") != 2 {
		t.Fatalf("expected two calls across retry boundary, got %d", external.callCount("payment-capture-001"))
	}
	if external.effectCount("payment-capture-001") != 1 {
		t.Fatalf("expected idempotent external system to execute exactly once, got %d effects", external.effectCount("payment-capture-001"))
	}
}

func TestAmbiguousOutcomeSimulationReportsUnreconciledDuplicateRisk(t *testing.T) {
	external := newFakeExternalSystem()
	toolExecutor := newDiagnosticToolExecutor(external)
	repo := newDiagnosticRepository()

	graphJSON := diagnosticGraphJSON(diagnosticToolConfig{
		Mode:        "ambiguous_timeout_once",
		OperationID: "wire-transfer-001",
		ExecutionID: "exec-ambiguous-timeout",
	}, 2, false)

	runID := "diagnostic-ambiguous-outcome"
	runScheduler(t, repo, toolExecutor, nil, runID, graphJSON, string(value.RunStatusFailed))

	summary := diagnosticSummary{
		DuplicateSideEffectsDetected: external.effectCount("wire-transfer-001") > 1,
		ToolsWithoutIdempotency:      []string{},
		AmbiguousExecutionCases:      []string{"external_success_response_timeout_without_reconciliation"},
	}
	t.Logf("tool_side_effect_diagnostic=%s", mustJSON(summary))
	t.Logf(
		"ambiguous_outcome evidence run_id=%s operation_id=%s outcome=ambiguous external_call_count=%d external_effect_count=%d calls=%s",
		runID,
		"wire-transfer-001",
		external.callCount("wire-transfer-001"),
		external.effectCount("wire-transfer-001"),
		mustJSON(external.callsForOperation("wire-transfer-001")),
	)

	if summary.DuplicateSideEffectsDetected {
		t.Fatalf("ambiguous unsafe retry should be blocked before duplicate side effects")
	}
}

func TestResumeAfterPartialExecutionReexecutesToolFromSnapshotBoundary(t *testing.T) {
	external := newFakeExternalSystem()
	toolExecutor := newDiagnosticToolExecutor(external)
	publisher := &recordingRuntimeIntentPublisher{}
	repo := newDiagnosticRepository()

	graphJSON := diagnosticGraphJSON(diagnosticToolConfig{
		Mode:        "fail_once_after_side_effect",
		OperationID: "provision-account-001",
		ExecutionID: "exec-resume-partial",
	}, 1, true)

	runID := "diagnostic-resume-after-partial-execution"
	runScheduler(t, repo, toolExecutor, publisher, runID, graphJSON, string(value.RunStatusFailed))
	if repo.latestCheckpointNode(runID) != "checkpoint_start" {
		t.Fatalf("expected checkpoint at checkpoint_start before failed tool, got %q", repo.latestCheckpointNode(runID))
	}
	if publisher.countByNodeID(diagnosticToolNodeID) != 0 {
		t.Fatalf("tool node_completed intent should not be published when crash occurs before completion")
	}

	runScheduler(t, repo, toolExecutor, publisher, runID, graphJSON, string(value.RunStatusSucceeded))

	summary := diagnosticSummary{
		DuplicateSideEffectsDetected: external.effectCount("provision-account-001") > 1,
		ToolsWithoutIdempotency:      []string{},
		AmbiguousExecutionCases:      []string{"resume_after_side_effect_before_completion_intent"},
	}
	t.Logf("tool_side_effect_diagnostic=%s", mustJSON(summary))
	t.Logf(
		"resume_after_partial_execution evidence run_id=%s operation_id=%s external_call_count=%d external_effect_count=%d tool_node_completed_intents=%d calls=%s",
		runID,
		"provision-account-001",
		external.callCount("provision-account-001"),
		external.effectCount("provision-account-001"),
		publisher.countByNodeID(diagnosticToolNodeID),
		mustJSON(external.callsForOperation("provision-account-001")),
	)

	if !summary.DuplicateSideEffectsDetected {
		t.Fatalf("expected resume after partial execution to re-execute tool and expose duplicate side effect risk")
	}
	diagnosticFailIfStrict(t, "resume re-executed tool after external side effect but before completion intent")
}

func TestAdapterCapabilityAuditProducesStructuredReport(t *testing.T) {
	registry := tool.NewRegistry()
	if err := registry.LoadManifests(enginePath(t, "tool-manifests")); err != nil {
		t.Fatalf("load tool manifests: %v", err)
	}

	report := adapterCapabilityReport{
		GeneratedAt: time.Now().UTC().Format(time.RFC3339Nano),
		Tools:       make([]adapterCapability, 0),
		Summary: diagnosticSummary{
			ToolsWithoutIdempotency: []string{},
			AmbiguousExecutionCases: []string{},
		},
	}
	for _, def := range registry.List() {
		capability := adapterCapability{
			Name:                         def.Name,
			Version:                      def.Version,
			SideEffectType:               def.SideEffects.Type,
			SupportsIdempotencyKey:       def.SideEffects.Idempotent,
			SupportsCorrelationID:        true,
			SupportsReconciliationLookup: supportsReconciliationLookup(def),
		}
		report.Tools = append(report.Tools, capability)
		if !capability.SupportsIdempotencyKey {
			report.Summary.ToolsWithoutIdempotency = append(report.Summary.ToolsWithoutIdempotency, def.Name+"@"+def.Version)
		}
	}
	sort.Slice(report.Tools, func(i, j int) bool {
		if report.Tools[i].Name == report.Tools[j].Name {
			return report.Tools[i].Version < report.Tools[j].Version
		}
		return report.Tools[i].Name < report.Tools[j].Name
	})
	sort.Strings(report.Summary.ToolsWithoutIdempotency)

	t.Logf("adapter_capability_audit=%s", mustJSON(report))
	if len(report.Tools) == 0 {
		t.Fatalf("expected adapter capability audit to inspect at least one tool")
	}
}

type diagnosticToolConfig struct {
	Mode           string
	OperationID    string
	IdempotencyKey string
	ExecutionID    string
}

func diagnosticGraphJSON(config diagnosticToolConfig, maxAttempts int, includeCheckpointStart bool) string {
	if maxAttempts <= 0 {
		maxAttempts = 1
	}
	nodes := []entity.Node{}
	edges := []entity.Edge{}

	if includeCheckpointStart {
		nodes = append(nodes, entity.Node{
			ID:     "checkpoint_start",
			Type:   string(value.NodeTypeTransform),
			Name:   "Checkpoint Start",
			Config: map[string]any{"marker": "before_tool"},
		})
		edges = append(edges, entity.Edge{ID: "edge-start-tool", From: "checkpoint_start", To: diagnosticToolNodeID})
	}

	nodes = append(nodes,
		entity.Node{
			ID:   diagnosticToolNodeID,
			Type: string(value.NodeTypeTool),
			Name: "Diagnostic Tool",
			Config: map[string]any{
				"mode":            config.Mode,
				"operation_id":    config.OperationID,
				"idempotency_key": config.IdempotencyKey,
				"execution_id":    config.ExecutionID,
			},
			RetryPolicy: &entity.RetryPolicy{
				MaxAttempts:     maxAttempts,
				BackoffMs:       1,
				BackoffStrategy: "fixed",
			},
		},
		entity.Node{
			ID:     diagnosticOutputNodeID,
			Type:   string(value.NodeTypeOutput),
			Name:   "Final Output",
			Config: map[string]any{"include_all": true},
		},
	)
	if config.IdempotencyKey != "" {
		nodes[len(nodes)-2].Config["tool_execution_id"] = "11111111-1111-1111-1111-111111111111"
		nodes[len(nodes)-2].Config["side_effect_class"] = "idempotent"
	}
	edges = append(edges, entity.Edge{ID: "edge-tool-output", From: diagnosticToolNodeID, To: diagnosticOutputNodeID})

	graph := entity.Graph{
		ID:       "tool-side-effect-diagnostic",
		Name:     "Tool Side Effect Diagnostic",
		Nodes:    nodes,
		Edges:    edges,
		Metadata: map[string]any{"engine_contract_version": "2"},
	}
	data, _ := json.Marshal(graph)
	return string(data)
}

func runScheduler(
	t *testing.T,
	repo *diagnosticRepository,
	toolExecutor *diagnosticToolExecutor,
	publisher port.RuntimeIntentPublisher,
	runID string,
	graphJSON string,
	expectedStatus string,
) {
	t.Helper()

	registry := port.NewExecutorRegistry()
	registry.Register(toolExecutor)
	registry.Register(&diagnosticTransformExecutor{})
	registry.Register(executor.NewOutputExecutor())

	config := usecase.DefaultSchedulerConfig()
	config.MaxWorkers = 1
	config.DefaultTimeoutMs = 1000
	config.CheckpointMode = usecase.CheckpointModeNode

	scheduler := usecase.NewScheduler(config, registry, repo, port.NewNoOpEventEmitter(), store.NewInMemoryMemoryStore())
	if publisher != nil {
		scheduler.SetRuntimeIntentPublisher(publisher, usecase.RuntimeWriteModeLegacySync)
	}

	if err := scheduler.StartRun(context.Background(), runID, graphJSON, `{}`, "", "", "tenant-diagnostic", "session-diagnostic"); err != nil {
		t.Fatalf("StartRun(%s): %v", runID, err)
	}

	deadline := time.Now().Add(3 * time.Second)
	for time.Now().Before(deadline) {
		run, err := repo.GetRun(context.Background(), runID)
		if err == nil && run.IsTerminal() {
			if run.Status != expectedStatus {
				t.Fatalf("run %s status = %s, expected %s; error=%s", runID, run.Status, expectedStatus, run.ErrorMessage)
			}
			return
		}
		time.Sleep(10 * time.Millisecond)
	}
	run, _ := repo.GetRun(context.Background(), runID)
	if run == nil {
		t.Fatalf("run %s did not finish; no run record", runID)
	}
	t.Fatalf("run %s did not finish; last status=%s error=%s", runID, run.Status, run.ErrorMessage)
}

type diagnosticTransformExecutor struct{}

func (e *diagnosticTransformExecutor) NodeType() string {
	return string(value.NodeTypeTransform)
}

func (e *diagnosticTransformExecutor) Execute(ctx context.Context, node *entity.Node, state *entity.State) (*port.NodeExecutionResult, error) {
	return port.NewSuccessResult(map[string]any{"checkpoint_marker": node.GetConfigString("marker")}), nil
}

type diagnosticToolExecutor struct {
	external *fakeExternalSystem
	mu       sync.Mutex
	attempts map[string]int
}

func newDiagnosticToolExecutor(external *fakeExternalSystem) *diagnosticToolExecutor {
	return &diagnosticToolExecutor{
		external: external,
		attempts: make(map[string]int),
	}
}

func (e *diagnosticToolExecutor) NodeType() string {
	return string(value.NodeTypeTool)
}

func (e *diagnosticToolExecutor) Execute(ctx context.Context, node *entity.Node, state *entity.State) (*port.NodeExecutionResult, error) {
	operationID := strings.TrimSpace(node.GetConfigString("operation_id"))
	if operationID == "" {
		operationID = node.ID
	}
	mode := node.GetConfigString("mode")
	idempotencyKey := strings.TrimSpace(node.GetConfigString("idempotency_key"))
	executionID := strings.TrimSpace(node.GetConfigString("execution_id"))
	if executionID == "" {
		executionID = "execution-" + operationID
	}
	attemptID := port.AttemptIDFrom(ctx)

	e.mu.Lock()
	e.attempts[operationID]++
	attemptNumber := e.attempts[operationID]
	e.mu.Unlock()

	call := e.external.performAction(operationID, idempotencyKey, attemptID, executionID, attemptNumber)

	switch mode {
	case "fail_once_after_side_effect":
		if attemptNumber == 1 {
			return nil, fmt.Errorf("simulated engine crash after external side effect before publish for operation %s", operationID)
		}
	case "retryable_once_after_side_effect":
		if attemptNumber == 1 {
			return nil, domain.NewRetryableErrorWithDetails(
				errors.New("simulated publish/transport failure after side effect"),
				"retryable diagnostic failure after external side effect",
				"diagnostic_after_side_effect",
				0,
				map[string]any{
					"operation_id":     operationID,
					"idempotency_key":  idempotencyKey,
					"external_call_no": call.Sequence,
				},
			)
		}
	case "ambiguous_timeout_once":
		if attemptNumber == 1 {
			return nil, domain.NewRetryableErrorWithDetails(
				errors.New("external response timeout after action was applied"),
				"ambiguous external outcome",
				"diagnostic_ambiguous_timeout",
				0,
				map[string]any{
					"operation_id":     operationID,
					"external_call_no": call.Sequence,
					"reconciliation":   "not_supported",
				},
			)
		}
	}

	return port.NewSuccessResult(map[string]any{
		"operation_id":      operationID,
		"attempt_id":        attemptID,
		"execution_id":      executionID,
		"idempotency_key":   idempotencyKey,
		"external_sequence": call.Sequence,
		"external_deduped":  call.Deduped,
	}), nil
}

type fakeExternalSystem struct {
	mu             sync.Mutex
	calls          []externalCall
	effectsByOp    map[string]int
	seenIdemKeys   map[string]bool
	nextCallNumber int
}

type externalCall struct {
	Sequence       int    `json:"sequence"`
	OperationID    string `json:"operation_id"`
	IdempotencyKey string `json:"idempotency_key,omitempty"`
	AttemptID      string `json:"attempt_id,omitempty"`
	ExecutionID    string `json:"execution_id,omitempty"`
	AttemptNumber  int    `json:"attempt_number"`
	Deduped        bool   `json:"deduped"`
}

func newFakeExternalSystem() *fakeExternalSystem {
	return &fakeExternalSystem{
		effectsByOp:  make(map[string]int),
		seenIdemKeys: make(map[string]bool),
	}
}

func (s *fakeExternalSystem) performAction(operationID, idempotencyKey, attemptID, executionID string, attemptNumber int) externalCall {
	s.mu.Lock()
	defer s.mu.Unlock()

	s.nextCallNumber++
	call := externalCall{
		Sequence:       s.nextCallNumber,
		OperationID:    operationID,
		IdempotencyKey: idempotencyKey,
		AttemptID:      attemptID,
		ExecutionID:    executionID,
		AttemptNumber:  attemptNumber,
	}
	if idempotencyKey != "" && s.seenIdemKeys[idempotencyKey] {
		call.Deduped = true
	} else {
		s.effectsByOp[operationID]++
		if idempotencyKey != "" {
			s.seenIdemKeys[idempotencyKey] = true
		}
	}
	s.calls = append(s.calls, call)
	return call
}

func (s *fakeExternalSystem) callCount(operationID string) int {
	s.mu.Lock()
	defer s.mu.Unlock()
	count := 0
	for _, call := range s.calls {
		if call.OperationID == operationID {
			count++
		}
	}
	return count
}

func (s *fakeExternalSystem) effectCount(operationID string) int {
	s.mu.Lock()
	defer s.mu.Unlock()
	return s.effectsByOp[operationID]
}

func (s *fakeExternalSystem) callsForOperation(operationID string) []externalCall {
	s.mu.Lock()
	defer s.mu.Unlock()
	result := make([]externalCall, 0)
	for _, call := range s.calls {
		if call.OperationID == operationID {
			result = append(result, call)
		}
	}
	return result
}

type recordingRuntimeIntentPublisher struct {
	mu      sync.Mutex
	intents []*port.RuntimeIntentEnvelope
}

func (p *recordingRuntimeIntentPublisher) Publish(ctx context.Context, intent *port.RuntimeIntentEnvelope) error {
	p.mu.Lock()
	defer p.mu.Unlock()
	copied := *intent
	if intent.Payload != nil {
		copied.Payload = cloneMapAny(intent.Payload)
	}
	p.intents = append(p.intents, &copied)
	return nil
}

func (p *recordingRuntimeIntentPublisher) countByNodeID(nodeID string) int {
	p.mu.Lock()
	defer p.mu.Unlock()
	count := 0
	for _, intent := range p.intents {
		if intent.IntentType == "node_completed" && intent.Payload["node_id"] == nodeID {
			count++
		}
	}
	return count
}

type diagnosticRepository struct {
	mu          sync.Mutex
	runs        map[string]*entity.Run
	nodeRuns    map[string]*entity.NodeRun
	checkpoints map[string]diagnosticCheckpoint
	cache       map[string]diagnosticCacheEntry
}

type diagnosticCheckpoint struct {
	nodeID         string
	stepIndex      int
	stateSnapshot  map[string]any
	completedNodes []string
	skippedNodes   []string
	graphJSON      string
}

type diagnosticCacheEntry struct {
	output    any
	expiresAt time.Time
}

func newDiagnosticRepository() *diagnosticRepository {
	return &diagnosticRepository{
		runs:        make(map[string]*entity.Run),
		nodeRuns:    make(map[string]*entity.NodeRun),
		checkpoints: make(map[string]diagnosticCheckpoint),
		cache:       make(map[string]diagnosticCacheEntry),
	}
}

func (r *diagnosticRepository) GetRun(ctx context.Context, runID string) (*entity.Run, error) {
	r.mu.Lock()
	defer r.mu.Unlock()
	run := r.runs[runID]
	if run == nil {
		return nil, domain.ErrRunNotFound
	}
	return cloneRun(run), nil
}

func (r *diagnosticRepository) UpdateRunStatus(ctx context.Context, runID string, status string) error {
	r.mu.Lock()
	defer r.mu.Unlock()
	run := r.ensureRunLocked(runID)
	run.Status = status
	run.ErrorMessage = ""
	run.EndedAt = nil
	return nil
}

func (r *diagnosticRepository) UpdateRunOutput(ctx context.Context, runID string, output map[string]any) error {
	r.mu.Lock()
	defer r.mu.Unlock()
	r.ensureRunLocked(runID).OutputJSON = cloneMapAny(output)
	return nil
}

func (r *diagnosticRepository) UpdateRunError(ctx context.Context, runID string, errorMsg string) error {
	r.mu.Lock()
	defer r.mu.Unlock()
	r.ensureRunLocked(runID).ErrorMessage = errorMsg
	return nil
}

func (r *diagnosticRepository) SetRunEnded(ctx context.Context, runID string, status string, output map[string]any, errorMsg string) error {
	r.mu.Lock()
	defer r.mu.Unlock()
	now := time.Now()
	run := r.ensureRunLocked(runID)
	run.Status = status
	run.OutputJSON = cloneMapAny(output)
	run.ErrorMessage = errorMsg
	run.EndedAt = &now
	return nil
}

func (r *diagnosticRepository) SavePauseState(ctx context.Context, runID, pausedNodeID string, stateSnapshot map[string]any, completedNodes []string, skippedNodes []string, graphJSON string, tenantID string) error {
	return nil
}

func (r *diagnosticRepository) LoadPauseState(ctx context.Context, runID string) (string, map[string]any, []string, []string, string, string, error) {
	return "", nil, nil, nil, "", "", fmt.Errorf("pause state not found")
}

func (r *diagnosticRepository) ClearPauseState(ctx context.Context, runID string) error {
	return nil
}

func (r *diagnosticRepository) SaveCheckpoint(ctx context.Context, runID, nodeID string, stepIndex int, stateSnapshot map[string]any, completedNodes []string, skippedNodes []string, graphJSON string) error {
	r.mu.Lock()
	defer r.mu.Unlock()
	r.checkpoints[runID] = diagnosticCheckpoint{
		nodeID:         nodeID,
		stepIndex:      stepIndex,
		stateSnapshot:  cloneMapAny(stateSnapshot),
		completedNodes: append([]string(nil), completedNodes...),
		skippedNodes:   append([]string(nil), skippedNodes...),
		graphJSON:      graphJSON,
	}
	return nil
}

func (r *diagnosticRepository) LoadLatestCheckpoint(ctx context.Context, runID string) (string, int, map[string]any, []string, []string, string, error) {
	r.mu.Lock()
	defer r.mu.Unlock()
	checkpoint, ok := r.checkpoints[runID]
	if !ok {
		return "", 0, nil, nil, nil, "", domain.ErrCheckpointNotFound
	}
	return checkpoint.nodeID,
		checkpoint.stepIndex,
		cloneMapAny(checkpoint.stateSnapshot),
		append([]string(nil), checkpoint.completedNodes...),
		append([]string(nil), checkpoint.skippedNodes...),
		checkpoint.graphJSON,
		nil
}

func (r *diagnosticRepository) ClearCheckpoints(ctx context.Context, runID string) error {
	r.mu.Lock()
	defer r.mu.Unlock()
	delete(r.checkpoints, runID)
	return nil
}

func (r *diagnosticRepository) LoadRunSnapshot(ctx context.Context, runID string) (*port.RunResumeSnapshot, error) {
	r.mu.Lock()
	defer r.mu.Unlock()
	checkpoint, ok := r.checkpoints[runID]
	if !ok {
		return nil, domain.ErrCheckpointNotFound
	}
	nextNode := ""
	if checkpoint.nodeID == "checkpoint_start" {
		nextNode = diagnosticToolNodeID
	}
	return &port.RunResumeSnapshot{
		RunID:             runID,
		LastCompletedNode: checkpoint.nodeID,
		NextNode:          nextNode,
		AttemptID:         "resume-attempt-" + runID,
		UpdatedAt:         time.Now(),
	}, nil
}

func (r *diagnosticRepository) GetCachedNodeResult(ctx context.Context, cacheKey string) (any, bool, error) {
	r.mu.Lock()
	defer r.mu.Unlock()
	entry, ok := r.cache[cacheKey]
	if !ok || time.Now().After(entry.expiresAt) {
		return nil, false, nil
	}
	return entry.output, true, nil
}

func (r *diagnosticRepository) SaveCachedNodeResult(ctx context.Context, cacheKey string, output any, ttlSeconds int) error {
	if ttlSeconds <= 0 {
		return nil
	}
	r.mu.Lock()
	defer r.mu.Unlock()
	r.cache[cacheKey] = diagnosticCacheEntry{output: output, expiresAt: time.Now().Add(time.Duration(ttlSeconds) * time.Second)}
	return nil
}

func (r *diagnosticRepository) CreateNodeRun(ctx context.Context, nodeRun *entity.NodeRun) error {
	r.mu.Lock()
	defer r.mu.Unlock()
	r.nodeRuns[nodeRun.ID] = cloneNodeRun(nodeRun)
	return nil
}

func (r *diagnosticRepository) UpdateNodeRun(ctx context.Context, nodeRun *entity.NodeRun) error {
	r.mu.Lock()
	defer r.mu.Unlock()
	r.nodeRuns[nodeRun.ID] = cloneNodeRun(nodeRun)
	return nil
}

func (r *diagnosticRepository) GetNodeRun(ctx context.Context, runID, nodeID string) (*entity.NodeRun, error) {
	r.mu.Lock()
	defer r.mu.Unlock()
	nodeRun := r.nodeRuns[runID+"-"+nodeID]
	if nodeRun == nil {
		return nil, fmt.Errorf("node run not found")
	}
	return cloneNodeRun(nodeRun), nil
}

func (r *diagnosticRepository) GetNodeRunsByRunID(ctx context.Context, runID string) ([]*entity.NodeRun, error) {
	r.mu.Lock()
	defer r.mu.Unlock()
	result := make([]*entity.NodeRun, 0)
	for _, nodeRun := range r.nodeRuns {
		if nodeRun.RunID == runID {
			result = append(result, cloneNodeRun(nodeRun))
		}
	}
	return result, nil
}

func (r *diagnosticRepository) latestCheckpointNode(runID string) string {
	r.mu.Lock()
	defer r.mu.Unlock()
	return r.checkpoints[runID].nodeID
}

func (r *diagnosticRepository) ensureRunLocked(runID string) *entity.Run {
	run := r.runs[runID]
	if run == nil {
		run = &entity.Run{ID: runID, StartedAt: time.Now(), InputJSON: map[string]any{}}
		r.runs[runID] = run
	}
	return run
}

type diagnosticSummary struct {
	DuplicateSideEffectsDetected bool     `json:"duplicate_side_effects_detected"`
	ToolsWithoutIdempotency      []string `json:"tools_without_idempotency"`
	AmbiguousExecutionCases      []string `json:"ambiguous_execution_cases"`
}

type adapterCapabilityReport struct {
	GeneratedAt string              `json:"generated_at"`
	Tools       []adapterCapability `json:"tools"`
	Summary     diagnosticSummary   `json:"summary"`
}

type adapterCapability struct {
	Name                         string `json:"name"`
	Version                      string `json:"version"`
	SideEffectType               string `json:"side_effect_type"`
	SupportsIdempotencyKey       bool   `json:"supports_idempotency_key"`
	SupportsCorrelationID        bool   `json:"supports_correlation_id"`
	SupportsReconciliationLookup bool   `json:"supports_reconciliation_lookup"`
}

func supportsReconciliationLookup(def *tool.Definition) bool {
	if def == nil {
		return false
	}
	if raw, ok := def.AgentHints["supports_reconciliation_lookup"]; ok {
		if supported, ok := raw.(bool); ok {
			return supported
		}
	}
	if raw, ok := def.DefaultConfig["reconciliation_lookup"]; ok {
		if supported, ok := raw.(bool); ok {
			return supported
		}
	}
	return false
}

func diagnosticFailIfStrict(t *testing.T, message string) {
	t.Helper()
	if os.Getenv("FORGEGRAPH_DIAGNOSTICS_STRICT") == "1" {
		t.Fatalf("diagnostic failure: %s", message)
	}
	t.Logf("diagnostic_failure_observed=%q strict_failure_disabled=true", message)
}

func enginePath(t *testing.T, elems ...string) string {
	t.Helper()
	_, file, _, ok := runtime.Caller(0)
	if !ok {
		t.Fatalf("resolve test path")
	}
	base := filepath.Clean(filepath.Join(filepath.Dir(file), "..", ".."))
	parts := append([]string{base}, elems...)
	return filepath.Join(parts...)
}

func mustJSON(value any) string {
	data, err := json.Marshal(value)
	if err != nil {
		return fmt.Sprintf(`{"json_error":%q}`, err.Error())
	}
	return string(data)
}

func cloneRun(run *entity.Run) *entity.Run {
	if run == nil {
		return nil
	}
	cloned := *run
	cloned.InputJSON = cloneMapAny(run.InputJSON)
	cloned.OutputJSON = cloneMapAny(run.OutputJSON)
	if run.EndedAt != nil {
		endedAt := *run.EndedAt
		cloned.EndedAt = &endedAt
	}
	return &cloned
}

func cloneNodeRun(nodeRun *entity.NodeRun) *entity.NodeRun {
	if nodeRun == nil {
		return nil
	}
	cloned := *nodeRun
	cloned.InputJSON = cloneMapAny(nodeRun.InputJSON)
	cloned.OutputJSON = cloneMapAny(nodeRun.OutputJSON)
	cloned.ErrorJSON = cloneMapAny(nodeRun.ErrorJSON)
	if nodeRun.EndedAt != nil {
		endedAt := *nodeRun.EndedAt
		cloned.EndedAt = &endedAt
	}
	return &cloned
}

func cloneMapAny(input map[string]any) map[string]any {
	if input == nil {
		return nil
	}
	cloned := make(map[string]any, len(input))
	for key, value := range input {
		cloned[key] = cloneValue(value)
	}
	return cloned
}

func cloneValue(value any) any {
	switch typed := value.(type) {
	case map[string]any:
		return cloneMapAny(typed)
	case []any:
		cloned := make([]any, len(typed))
		for i, item := range typed {
			cloned[i] = cloneValue(item)
		}
		return cloned
	default:
		return typed
	}
}
