// Package usecase contains application use cases for the ForgeGraph engine.
package usecase

import (
	"context"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"errors"
	"fmt"
	"log"
	"reflect"
	"slices"
	"sort"
	"strconv"
	"strings"
	"sync"
	"sync/atomic"
	"time"

	"github.com/forgegraph/engine/application/port"
	"github.com/forgegraph/engine/domain"
	"github.com/forgegraph/engine/domain/entity"
	"github.com/forgegraph/engine/domain/service"
	"github.com/forgegraph/engine/domain/value"
	"github.com/forgegraph/engine/infrastructure/metrics"
	"github.com/forgegraph/engine/infrastructure/tracing"
	"github.com/google/uuid"
	oteltrace "go.opentelemetry.io/otel/trace"
)

// CheckpointMode controls durable checkpoint behavior.
type CheckpointMode string

const (
	CheckpointModeNone  CheckpointMode = "none"
	CheckpointModeNode  CheckpointMode = "node"
	CheckpointModeBatch CheckpointMode = "batch"
)

const (
	sessionNamespacePrefix = "session"
	sessionBufferKeyPrefix = "buffer"
	checkpointPayloadV2    = 2
)

const (
	llmAccessMetadataKey    = "llm_access"
	llmAccessEngineInputKey = "_forgegraph_llm_access"
)

const (
	RuntimeWriteModeLegacySync         = "legacy-sync"
	RuntimeWriteModePauseIntents       = "pause-intents"
	RuntimeWriteModePauseIntentsShadow = "pause-intents-shadow"
)

const (
	onErrorStrategyFail     = "fail"
	onErrorStrategyRetry    = "retry"
	onErrorStrategySkip     = "skip"
	onErrorStrategyFallback = "fallback"
)

type onErrorPolicy struct {
	Strategy           string
	NextNodes          []string
	MaxAttempts        int
	HasMaxAttempts     bool
	BackoffMs          int
	HasBackoffMs       bool
	BackoffStrategy    string
	HasBackoffStrategy bool
}

// SchedulerConfig holds scheduler configuration
type SchedulerConfig struct {
	MaxWorkers             int // Maximum concurrent node executions
	DefaultTimeoutMs       int // Default timeout for node execution
	CheckpointMode         CheckpointMode
	CheckpointBatchSize    int // Save checkpoint every N nodes when mode=batch
	CheckpointIntervalMs   int // Save checkpoint at least every N ms when mode=batch
	CacheDefaultTTLSeconds int
}

// DefaultSchedulerConfig returns sensible defaults
func DefaultSchedulerConfig() SchedulerConfig {
	return SchedulerConfig{
		MaxWorkers:             10,
		DefaultTimeoutMs:       30000, // 30 seconds
		CheckpointMode:         CheckpointModeNode,
		CheckpointBatchSize:    10,
		CheckpointIntervalMs:   0,
		CacheDefaultTTLSeconds: 3600,
	}
}

// Scheduler orchestrates workflow execution
type Scheduler struct {
	config                 SchedulerConfig
	registry               port.ExecutorRegistry
	repository             port.RunRepository
	emitter                port.EventEmitter
	runtimeIntentPublisher port.RuntimeIntentPublisher
	runtimeWriteMode       string
	clock                  schedulerClock
	conditions             *service.ConditionEvaluator
	summarizer             *SummarizationWorker
	memoryRetriever        port.MemoryRetriever
	observationClient      port.ObservationMemoryClient
	memoryStore            port.MemoryStore
	hooks                  schedulerHooks

	// Active runs tracking
	activeRuns sync.Map // runID -> *runContext
}

// NewScheduler creates a new scheduler
func NewScheduler(
	config SchedulerConfig,
	registry port.ExecutorRegistry,
	repository port.RunRepository,
	emitter port.EventEmitter,
	memoryStore port.MemoryStore,
) *Scheduler {
	if config.CheckpointMode == "" {
		config.CheckpointMode = CheckpointModeNode
	}
	if config.CheckpointMode == CheckpointModeBatch {
		if config.CheckpointBatchSize <= 0 {
			config.CheckpointBatchSize = 10
		}
		if config.CheckpointIntervalMs < 0 {
			config.CheckpointIntervalMs = 0
		}
	}
	if config.CacheDefaultTTLSeconds == 0 {
		config.CacheDefaultTTLSeconds = 3600
	}
	return &Scheduler{
		config:           config,
		registry:         registry,
		repository:       repository,
		emitter:          emitter,
		runtimeWriteMode: RuntimeWriteModeLegacySync,
		clock:            systemClock{},
		conditions:       service.NewConditionEvaluator(),
		memoryStore:      memoryStore,
	}
}

// SetSummarizationWorker attaches an async summarization worker.
func (s *Scheduler) SetSummarizationWorker(worker *SummarizationWorker) {
	s.summarizer = worker
}

// SetMemoryRetriever attaches the memory retriever used for Tier 3 lookups.
func (s *Scheduler) SetMemoryRetriever(retriever port.MemoryRetriever) {
	s.memoryRetriever = retriever
}

// SetObservationClient attaches the curated-memory client used by observation nodes.
func (s *Scheduler) SetObservationClient(client port.ObservationMemoryClient) {
	s.observationClient = client
}

// SetRuntimeIntentPublisher configures durable backend write-intent publishing.
func (s *Scheduler) SetRuntimeIntentPublisher(
	publisher port.RuntimeIntentPublisher,
	mode string,
) {
	s.runtimeIntentPublisher = publisher
	s.runtimeWriteMode = normalizeRuntimeWriteMode(mode)
}

func normalizeRuntimeWriteMode(mode string) string {
	switch strings.TrimSpace(strings.ToLower(mode)) {
	case "", RuntimeWriteModeLegacySync:
		return RuntimeWriteModeLegacySync
	case RuntimeWriteModePauseIntents:
		return RuntimeWriteModePauseIntents
	case RuntimeWriteModePauseIntentsShadow:
		return RuntimeWriteModePauseIntentsShadow
	default:
		return RuntimeWriteModeLegacySync
	}
}

func (s *Scheduler) pauseIntentPublishingEnabled() bool {
	return s.runtimeIntentPublisher != nil && (s.runtimeWriteMode == RuntimeWriteModePauseIntents || s.runtimeWriteMode == RuntimeWriteModePauseIntentsShadow)
}

func (s *Scheduler) pauseIntentActiveMode() bool {
	return s.runtimeIntentPublisher != nil && s.runtimeWriteMode == RuntimeWriteModePauseIntents
}

// runContext holds runtime state for a single run
type runContext struct {
	runID                string
	ctx                  context.Context
	cancel               context.CancelFunc
	clock                schedulerClock
	runSpan              oteltrace.Span
	startedAt            time.Time
	plan                 *service.ExecutionPlan
	allowCycles          bool
	defaultMaxVisits     int
	backEdges            map[*entity.Edge]bool
	state                *entity.State
	callbackURL          string
	graphJSON            string // Original graph JSON for pause/resume
	initialNodes         []string
	tenantID             string
	sessionID            string
	attemptID            string
	traceID              string
	traceparent          string
	tracestate           string
	messageBuffer        *entity.MessageBuffer
	memoryConfig         *entity.MemoryConfig
	currentSummary       *entity.Summary
	memoryCtx            *port.RunContext
	summaryMu            sync.Mutex
	messagesSinceSummary int
	cooldownRemaining    int
	summaryInFlight      bool
	pauseIntentPublished bool

	// Synchronization
	pendingMu       sync.Mutex
	pending         map[string]int  // nodeID -> remaining dependencies
	completed       map[string]bool // nodeID -> completed successfully
	skipped         map[string]bool // nodeID -> skipped (branch not taken)
	running         map[string]bool // nodeID -> currently running
	visitCounts     map[string]int  // nodeID -> number of successful executions started
	resumeRetryNode string          // snapshot next_node allowed one re-entry after a failed pre-snapshot attempt

	// Worker coordination
	workChan chan string
	wg       sync.WaitGroup

	// Error tracking (first error wins)
	errMu sync.Mutex
	err   error

	// Current node being executed (for status queries)
	currentNodeMu sync.RWMutex
	currentNodeID string

	checkpointSeq    int64
	checkpointMu     sync.Mutex
	lastCheckpointAt time.Time

	stateSchema   *service.SchemaValidator
	schemaMode    string
	runtimeLimits runtimeLimits
	llmCallCount  atomic.Int64
	toolCallCount atomic.Int64
}

type runtimeLimits struct {
	MaxRunDurationMs int64
	MaxToolCalls     int64
	MaxLLMCalls      int64
}

type resumeCheckpoint struct {
	stepIndex      int
	stateSnapshot  map[string]any
	completedNodes []string
	skippedNodes   []string
	visitCounts    map[string]int
	nextNode       string
	attemptID      string
}

func (rc *runContext) newEvent(eventType port.EventType) *port.ExecutionEvent {
	event := port.NewEvent(eventType, rc.runID)
	if rc.clock != nil {
		event.Timestamp = rc.clock.Now().UnixMilli()
	}
	return event.
		WithTenantID(rc.tenantID).
		WithTrace(rc.traceparent, rc.tracestate, rc.traceID, "")
}

func (rc *runContext) intentContext(ctx context.Context) context.Context {
	if ctx == nil {
		ctx = context.Background()
	}
	return port.WithAttemptID(ctx, rc.attemptID)
}

func (rc *runContext) newEventFromContext(ctx context.Context, eventType port.EventType) *port.ExecutionEvent {
	event := rc.newEvent(eventType)
	traceCtx := tracing.FromContext(ctx)
	if traceCtx.TraceID != "" {
		event.WithTrace(traceCtx.Traceparent, traceCtx.Tracestate, traceCtx.TraceID, traceCtx.SpanID)
	}
	return event
}

func (s *Scheduler) flushEmitter(reason string) {
	ctx, cancel := context.WithTimeout(context.Background(), 2*time.Second)
	defer cancel()
	if err := s.emitter.Flush(ctx); err != nil {
		log.Printf("event_flush_failed (%s): %v", reason, err)
	}
}

func (rc *runContext) trackMessages(count int) {
	if count <= 0 {
		return
	}
	rc.summaryMu.Lock()
	defer rc.summaryMu.Unlock()
	rc.messagesSinceSummary += count
	if rc.cooldownRemaining > 0 {
		rc.cooldownRemaining -= count
		if rc.cooldownRemaining < 0 {
			rc.cooldownRemaining = 0
		}
	}
}

func (rc *runContext) trackLLMCall() error {
	if rc.runtimeLimits.MaxLLMCalls <= 0 {
		return nil
	}
	count := rc.llmCallCount.Add(1)
	if count > rc.runtimeLimits.MaxLLMCalls {
		return domain.NewValidationError("runtime_limits", "run exceeded max_llm_calls_total")
	}
	return nil
}

func (rc *runContext) trackToolCall() error {
	if rc.runtimeLimits.MaxToolCalls <= 0 {
		return nil
	}
	count := rc.toolCallCount.Add(1)
	if count > rc.runtimeLimits.MaxToolCalls {
		return domain.NewValidationError("runtime_limits", "run exceeded max_tool_calls_total")
	}
	return nil
}

func (rc *runContext) validateRuntimeBudget() error {
	if rc.runtimeLimits.MaxRunDurationMs <= 0 {
		return nil
	}
	if rc.startedAt.IsZero() {
		return nil
	}
	if rc.clock.Now().Sub(rc.startedAt).Milliseconds() > rc.runtimeLimits.MaxRunDurationMs {
		return domain.NewValidationError("runtime_limits", "run exceeded max_run_duration_ms")
	}
	return nil
}

func (rc *runContext) canSummarize(cfg entity.SummarizationConfig) bool {
	rc.summaryMu.Lock()
	defer rc.summaryMu.Unlock()
	if rc.summaryInFlight {
		return false
	}
	if rc.cooldownRemaining > 0 {
		return false
	}
	return rc.messagesSinceSummary >= cfg.TriggerThreshold
}

func (rc *runContext) markSummaryInFlight() {
	rc.summaryMu.Lock()
	rc.summaryInFlight = true
	rc.summaryMu.Unlock()
}

func (rc *runContext) applySummary(summary *entity.Summary, cfg entity.SummarizationConfig) {
	rc.summaryMu.Lock()
	rc.currentSummary = summary
	rc.memoryCtx.CurrentSummary = summary
	rc.messagesSinceSummary = 0
	rc.cooldownRemaining = cfg.CooldownMessages
	rc.summaryInFlight = false
	rc.summaryMu.Unlock()
}

func (rc *runContext) clearSummaryInFlight() {
	rc.summaryMu.Lock()
	rc.summaryInFlight = false
	rc.summaryMu.Unlock()
}

func seedSimulationExecutionState(graph *entity.Graph, state *entity.State) {
	if graph == nil || state == nil {
		return
	}
	if _, exists := state.Get("vars.execution_state"); exists {
		return
	}
	if existing, exists := state.Get("input.execution_state"); exists {
		state.SetVar("execution_state", existing)
		return
	}

	defaultGoal := ""
	usesSimulationState := false
	for _, node := range graph.Nodes {
		if node.Type != string(value.NodeTypeTransform) {
			continue
		}
		expressionType := strings.TrimSpace(node.GetConfigString("expression_type"))
		if expressionType != "simulation_step" {
			continue
		}
		usesSimulationState = true
		if defaultGoal == "" {
			defaultGoal = strings.TrimSpace(node.GetConfigString("default_goal"))
		}
	}
	if !usesSimulationState {
		return
	}

	goal := defaultGoal
	if rawGoal, exists := state.Get("input.goal"); exists {
		if candidate := strings.TrimSpace(fmt.Sprintf("%v", rawGoal)); candidate != "" {
			goal = candidate
		}
	}
	if goal == "" {
		goal = "Launch a deterministic digital marketing campaign."
	}

	state.SetVar(
		"execution_state",
		map[string]any{
			"goal":              goal,
			"strategy":          nil,
			"content_assets":    []any{},
			"distribution_plan": nil,
			"analytics":         nil,
			"iteration":         0,
		},
	)
}

// StartRun begins executing a workflow
func (s *Scheduler) StartRun(
	ctx context.Context,
	runID string,
	graphJSON string,
	inputJSON string,
	callbackURL string,
	memoryConfigJSON string,
	tenantID string,
	sessionID string,
	traceContext ...string,
) error {
	traceparent := ""
	tracestate := ""
	if len(traceContext) > 0 {
		traceparent = traceContext[0]
	}
	if len(traceContext) > 1 {
		tracestate = traceContext[1]
	}
	type checkpointData struct {
		stepIndex       int
		stateSnapshot   map[string]any
		pendingSnapshot map[string]int
		visitCounts     map[string]int
		completedNodes  []string
		skippedNodes    []string
		messageBuffer   []entity.Message
		memoryConfig    *entity.MemoryConfig
		currentSummary  *entity.Summary
		nextNode        string
		attemptID       string
	}

	var checkpoint *checkpointData
	if s.isCheckpointingEnabled() {
		resumeState, err := s.loadResumeCheckpoint(ctx, runID)
		if err == nil {
			checkpoint = &checkpointData{
				stepIndex:       resumeState.stepIndex,
				stateSnapshot:   resumeState.stateSnapshot,
				pendingSnapshot: nil,
				visitCounts:     resumeState.visitCounts,
				completedNodes:  resumeState.completedNodes,
				skippedNodes:    resumeState.skippedNodes,
				nextNode:        resumeState.nextNode,
				attemptID:       resumeState.attemptID,
			}
		} else if !errors.Is(err, domain.ErrCheckpointNotFound) && !errors.Is(err, domain.ErrRunNotFound) {
			log.Printf("Ignoring invalid resume snapshot for run %s and starting clean: %v", runID, err)
		}
	}

	currentAttemptID := uuid.NewString()
	if checkpoint != nil && strings.TrimSpace(checkpoint.attemptID) != "" {
		currentAttemptID = strings.TrimSpace(checkpoint.attemptID)
	}

	// Parse graph JSON
	var graph entity.Graph
	if err := json.Unmarshal([]byte(graphJSON), &graph); err != nil {
		return fmt.Errorf("invalid graph JSON: %w", err)
	}
	hydrateGraphIdentifiers(graphJSON, &graph)
	engineContractVersion := ""
	if graph.Metadata != nil {
		if rawVersion, ok := graph.Metadata["engine_contract_version"].(string); ok {
			engineContractVersion = strings.TrimSpace(rawVersion)
		}
		if checkpoint == nil {
			if rawAttemptID, ok := graph.Metadata["backend_attempt_id"].(string); ok && strings.TrimSpace(rawAttemptID) != "" {
				currentAttemptID = strings.TrimSpace(rawAttemptID)
			}
		}
	}
	if engineContractVersion != "" && engineContractVersion != "2" {
		return fmt.Errorf("unsupported engine_contract_version: %s", engineContractVersion)
	}
	llmAccess := extractLLMAccessFromMetadata(graph.Metadata)

	// Parse input JSON. Private dispatch fields are consumed before state is built.
	var input map[string]any
	if inputJSON != "" {
		if err := json.Unmarshal([]byte(inputJSON), &input); err != nil {
			return fmt.Errorf("invalid input JSON: %w", err)
		}
	}
	llmAccess = mergeLLMAccess(llmAccess, extractLLMAccessFromInput(input))

	// Validate graph
	validator := service.NewGraphValidator()
	if err := validator.Validate(&graph); err != nil {
		return fmt.Errorf("graph validation failed: %w", err)
	}

	// Check all node types have executors
	for _, node := range graph.Nodes {
		if !s.registry.Has(node.Type) {
			return fmt.Errorf("%w: %s", domain.ErrExecutorNotFound, node.Type)
		}
	}

	// Build execution plan
	planner := service.NewExecutionPlanner()
	plan := planner.Plan(&graph)
	allowCycles, defaultMaxVisits := extractLoopMetadata(graph.Metadata)
	backEdges := s.detectBackEdges(plan, allowCycles)

	// Initialize state
	var state *entity.State
	if checkpoint != nil {
		if checkpoint.stateSnapshot == nil {
			checkpoint.stateSnapshot = map[string]any{}
		}
		state = entity.NewStateFromSnapshot(checkpoint.stateSnapshot)
	} else {
		state = entity.NewStateWithInput(input)
	}
	seedSimulationExecutionState(&graph, state)

	// Extract optional state schema validation metadata
	stateSchemaRaw, schemaMode := extractStateSchemaMetadata(graph.Metadata)
	stateSchema, err := service.CompileSchema(stateSchemaRaw)
	if err != nil {
		return fmt.Errorf("invalid state_schema: %w", err)
	}

	// Parse memory configuration
	parsedMemoryConfig := parseMemoryConfig(memoryConfigJSON)
	if checkpoint != nil && checkpoint.memoryConfig != nil {
		parsedMemoryConfig = checkpoint.memoryConfig
	}
	runtimeLimits := extractRuntimeLimits(graph.Metadata)

	// Initialize buffer with configured size
	var messageBuffer *entity.MessageBuffer
	if parsedMemoryConfig.Tier1.Enabled {
		bufferSize := parsedMemoryConfig.Tier1.BufferSize
		if bufferSize <= 0 {
			bufferSize = 20
		}
		messageBuffer = entity.NewMessageBuffer(bufferSize)
		if strings.EqualFold(parsedMemoryConfig.Tier1.LimitMode, "tokens") && parsedMemoryConfig.Tier1.MaxTokens > 0 {
			counter, err := service.NewDefaultTokenCounter()
			if err != nil {
				log.Printf("Failed to initialize token counter: %v (falling back to message count)", err)
			} else {
				safeCounter := service.NewSafeTokenCounter(counter, service.NaiveTokenCounter{})
				messageBuffer.ConfigureTokenLimit(parsedMemoryConfig.Tier1.MaxTokens, safeCounter.CountMessage)
			}
		}
		if checkpoint != nil && len(checkpoint.messageBuffer) > 0 {
			messageBuffer.Restore(checkpoint.messageBuffer)
		} else if sessionID != "" && s.shouldUseSessionMemory(parsedMemoryConfig) {
			if sessionMessages := s.loadSessionBuffer(ctx, tenantID, sessionID); len(sessionMessages) > 0 {
				messageBuffer.Restore(sessionMessages)
			}
		}
	}

	// Create a detached run context.
	// Do not derive from request-scoped gRPC context, which is canceled as soon as StartRun returns.
	runCtx, runSpan, traceCtx := tracing.StartSpan(
		context.Background(),
		"forgegraph-engine",
		"forgegraph.run",
		traceparent,
		tracestate,
	)
	runCtx, cancel := context.WithCancel(runCtx)
	rc := &runContext{
		runID:            runID,
		ctx:              runCtx,
		cancel:           cancel,
		clock:            s.clock,
		runSpan:          runSpan,
		startedAt:        s.clock.Now(),
		plan:             plan,
		allowCycles:      allowCycles,
		defaultMaxVisits: defaultMaxVisits,
		backEdges:        backEdges,
		state:            state,
		callbackURL:      callbackURL,
		graphJSON:        graphJSON,
		tenantID:         tenantID,
		sessionID:        sessionID,
		attemptID:        currentAttemptID,
		traceID:          traceCtx.TraceID,
		traceparent:      traceCtx.Traceparent,
		tracestate:       traceCtx.Tracestate,
		messageBuffer:    messageBuffer,
		memoryConfig:     parsedMemoryConfig,
		currentSummary: func() *entity.Summary {
			if checkpoint != nil {
				return checkpoint.currentSummary
			}
			return nil
		}(),
		stateSchema:   stateSchema,
		schemaMode:    schemaMode,
		runtimeLimits: runtimeLimits,
		pending:       s.initializePending(plan, backEdges),
		completed:     make(map[string]bool),
		skipped:       make(map[string]bool),
		running:       make(map[string]bool),
		visitCounts:   make(map[string]int),
		workChan:      make(chan string, len(plan.NodeMap)),
	}
	rc.memoryCtx = &port.RunContext{
		TenantID:          rc.tenantID,
		GraphID:           graph.ID,
		RunID:             rc.runID,
		SessionID:         rc.sessionID,
		TraceID:           rc.traceID,
		Traceparent:       rc.traceparent,
		Tracestate:        rc.tracestate,
		MemoryBuffer:      rc.messageBuffer,
		MemoryConfig:      rc.memoryConfig,
		CurrentSummary:    rc.currentSummary,
		TrackMessage:      rc.trackMessages,
		TrackLLMCall:      rc.trackLLMCall,
		TrackToolCall:     rc.trackToolCall,
		MemoryRetriever:   s.memoryRetriever,
		ObservationClient: s.observationClient,
		Policy:            entity.PolicyFromMetadata(graph.Metadata),
		LLMAccess:         llmAccess,
	}
	rc.ctx = port.WithRunContext(rc.ctx, rc.memoryCtx)
	rc.ctx = port.WithTenantID(rc.ctx, rc.tenantID)
	rc.ctx = port.WithAttemptID(rc.ctx, rc.attemptID)

	if checkpoint != nil {
		rc.checkpointSeq = int64(checkpoint.stepIndex)
		for _, completedID := range checkpoint.completedNodes {
			rc.completed[completedID] = true
		}
		for _, skippedID := range checkpoint.skippedNodes {
			rc.skipped[skippedID] = true
		}
		if len(checkpoint.visitCounts) > 0 {
			for nodeID, count := range checkpoint.visitCounts {
				if _, exists := rc.plan.NodeMap[nodeID]; !exists {
					continue
				}
				if count > 0 {
					rc.visitCounts[nodeID] = count
				}
			}
		}
		for completedID := range rc.completed {
			if rc.visitCounts[completedID] < 1 {
				rc.visitCounts[completedID] = 1
			}
		}
		if len(checkpoint.pendingSnapshot) > 0 {
			rc.pending = s.restorePendingSnapshot(plan, checkpoint.pendingSnapshot, backEdges)
		} else {
			s.applyCheckpointToPending(rc)
		}
		if checkpoint.nextNode != "" && !rc.completed[checkpoint.nextNode] && !rc.skipped[checkpoint.nextNode] {
			rc.resumeRetryNode = checkpoint.nextNode
		}
		rc.initialNodes = s.computeReadyNodes(rc)
		if checkpoint.nextNode != "" && slices.Contains(rc.initialNodes, checkpoint.nextNode) {
			ordered := []string{checkpoint.nextNode}
			for _, nodeID := range rc.initialNodes {
				if nodeID == checkpoint.nextNode {
					continue
				}
				ordered = append(ordered, nodeID)
			}
			rc.initialNodes = ordered
		}
	} else {
		rc.initialNodes = s.computeReadyNodes(rc)
	}

	// Store active run
	s.activeRuns.Store(runID, rc)

	s.preloadMemory(rc)

	// Update run status to running
	if err := s.repository.UpdateRunStatus(rc.intentContext(ctx), runID, string(value.RunStatusRunning)); err != nil {
		log.Printf("Failed to update run status: %v", err)
	}

	// Emit run started/resumed event
	if checkpoint != nil {
		resumedEvent := rc.newEvent(port.EventTypeRunResumed)
		if rc.attemptID != "" {
			resumedEvent = resumedEvent.WithOutput(map[string]any{"resume_attempt_id": rc.attemptID})
		}
		s.emitter.EmitAsync(resumedEvent)
	} else {
		s.emitter.EmitAsync(rc.newEvent(port.EventTypeRunStarted))
	}

	// Start execution in background
	go s.executeRun(rc)

	return nil
}

// executeRun runs the workflow to completion
func (s *Scheduler) executeRun(rc *runContext) {
	defer func() {
		// Cleanup
		s.activeRuns.Delete(rc.runID)
		if rc.runSpan != nil {
			rc.runSpan.End()
		}
		rc.cancel()
		close(rc.workChan)
	}()

	// Start workers (they exit when context is cancelled)
	for i := 0; i < s.config.MaxWorkers; i++ {
		go s.worker(rc)
	}

	// Enqueue start nodes (add to WaitGroup for each)
	startNodes := rc.initialNodes
	if len(startNodes) == 0 {
		startNodes = rc.plan.StartNodes
	}
	for _, nodeID := range startNodes {
		rc.wg.Add(1)
		rc.workChan <- nodeID
	}

	// Wait for all work to complete
	rc.wg.Wait()

	// Determine final status
	s.finalizeRun(rc)
}

// worker processes nodes from the work channel
func (s *Scheduler) worker(rc *runContext) {
	for {
		select {
		case <-rc.ctx.Done():
			return
		case nodeID, ok := <-rc.workChan:
			if !ok {
				return
			}
			s.executeNode(rc, nodeID)
		}
	}
}

// executeNode runs a single node with retries
func (s *Scheduler) executeNode(rc *runContext, nodeID string) {
	defer rc.wg.Done() // Mark this work item as complete

	node := rc.plan.GetNode(nodeID)
	if node == nil {
		log.Printf("Node %s not found in plan", nodeID)
		return
	}

	// Debug: log incoming data types for this node
	incomingTypes := rc.plan.GetIncomingDataTypes(nodeID)
	if len(incomingTypes) > 0 {
		for fromNode, dataType := range incomingTypes {
			log.Printf("[DEBUG] Node %s receiving %s data from %s", nodeID, dataType, fromNode)
		}
	}

	// Check if node is disabled - skip execution
	if node.Disabled {
		s.markSkipped(rc, nodeID)
		return
	}

	maxVisits := s.maxVisitsForNode(rc, node)
	currentVisitCount := 0

	// Mark as running
	rc.pendingMu.Lock()
	if rc.skipped[nodeID] {
		rc.pendingMu.Unlock()
		return
	}
	if rc.running[nodeID] {
		rc.pendingMu.Unlock()
		return
	}
	if rc.completed[nodeID] && rc.visitCounts[nodeID] >= maxVisits {
		rc.pendingMu.Unlock()
		return
	}
	allowResumeRetry := rc.resumeRetryNode == nodeID
	if rc.visitCounts[nodeID] >= maxVisits && !allowResumeRetry {
		rc.pendingMu.Unlock()
		s.setError(
			rc,
			domain.NewValidationError(
				"max_visits",
				fmt.Sprintf("node %s exceeded max_visits=%d", nodeID, maxVisits),
			),
		)
		return
	}
	if allowResumeRetry {
		rc.resumeRetryNode = ""
	}
	rc.visitCounts[nodeID]++
	currentVisitCount = rc.visitCounts[nodeID]
	rc.running[nodeID] = true
	rc.pendingMu.Unlock()

	rc.currentNodeMu.Lock()
	rc.currentNodeID = nodeID
	rc.currentNodeMu.Unlock()

	// Get executor for this node type
	executor, ok := s.registry.Get(node.Type)
	if !ok {
		s.setError(rc, fmt.Errorf("%w: %s", domain.ErrExecutorNotFound, node.Type))
		return
	}

	// Inject metadata for branch and merge nodes
	s.injectNodeMetadata(rc, node)

	if err := rc.validateRuntimeBudget(); err != nil {
		s.setError(rc, err)
		return
	}
	nodeCtx, nodeSpan, nodeTrace := tracing.StartSpan(
		rc.ctx,
		"forgegraph-engine",
		"forgegraph.node",
		"",
		"",
	)
	defer nodeSpan.End()

	// Create node run record
	baseAttempt := s.baseAttemptForVisit(node, currentVisitCount)
	nodeRun := &entity.NodeRun{
		ID:        fmt.Sprintf("%s-%s-%d", rc.runID, nodeID, baseAttempt),
		RunID:     rc.runID,
		NodeID:    nodeID,
		NodeType:  node.Type,
		Status:    string(value.NodeRunStatusRunning),
		Attempt:   baseAttempt,
		StartedAt: s.clock.Now(),
		InputJSON: rc.state.Snapshot(),
		TraceID:   nodeTrace.TraceID,
		SpanID:    nodeTrace.SpanID,
	}
	if err := s.repository.CreateNodeRun(nodeCtx, nodeRun); err != nil {
		log.Printf("Failed to create node run: %v", err)
	}
	if node.Type == string(value.NodeTypeTool) {
		if err := s.publishToolExecutionStatusIntent(rc.intentContext(context.Background()), rc, node, "tool_execution_started", "", nil); err != nil {
			s.setError(rc, fmt.Errorf("failed to publish tool_execution_started intent: %w", err))
			return
		}
	}

	// Emit node started
	s.emitter.EmitAsync(
		rc.newEventFromContext(nodeCtx, port.EventTypeNodeStarted).
			WithNode(nodeID, node.Type, node.Name).
			WithAttempt(nodeRun.Attempt).
			WithAttemptID(rc.attemptID).
			WithInput(nodeRun.InputJSON),
	)

	// Try cache before execution
	cacheEnabled, cacheTTLSeconds := s.getCacheConfig(node)
	cacheKey := ""
	if cacheEnabled {
		key, err := s.computeCacheKey(node, nodeRun.InputJSON)
		if err != nil {
			log.Printf("Failed to compute cache key for node %s: %v", nodeID, err)
		} else {
			cacheKey = key
			if cachedOutput, found, err := s.repository.GetCachedNodeResult(nodeCtx, cacheKey); err != nil {
				log.Printf("Failed to read cache for node %s: %v", nodeID, err)
			} else if found {
				result := &port.NodeExecutionResult{Output: cachedOutput}
				s.handleNodeSuccess(nodeCtx, rc, node, nodeRun, result, 0)
				return
			}
		}
	}

	// Execute with timeout and retries
	startTime := s.clock.Now()
	result, err := s.executeWithRetries(nodeCtx, rc, node, executor, nodeRun)
	duration := s.clock.Now().Sub(startTime).Milliseconds()

	// Mark as no longer running
	rc.pendingMu.Lock()
	delete(rc.running, nodeID)
	rc.pendingMu.Unlock()

	if err != nil {
		// Check if this is a context cancellation (graceful shutdown)
		if rc.ctx.Err() != nil {
			// Context was cancelled - this is not a node failure, just graceful termination
			return
		}

		if s.handleNodeFailure(nodeCtx, rc, node, nodeRun, err, duration) {
			return
		}
		s.setError(rc, domain.NewNodeError(nodeID, node.Type, err))
		return
	}

	// Handle human gate pause
	if result.Pause {
		pausePayload := map[string]any{}
		if result.Output != nil {
			if typed, ok := result.Output.(map[string]any); ok {
				pausePayload = typed
			}
		}

		if s.pauseIntentPublishingEnabled() {
			if err := s.publishPauseRunIntent(rc.intentContext(context.Background()), rc, node, nodeRun, pausePayload); err != nil {
				s.setError(rc, fmt.Errorf("failed to publish pause_run intent: %w", err))
				return
			}
		}

		if !s.pauseIntentActiveMode() {
			// Set node to "waiting" status - do NOT set ended_at since the node is still pending human input
			nodeRun.Status = string(value.NodeRunStatusWaiting)
			if len(pausePayload) > 0 {
				nodeRun.OutputJSON = map[string]any{"pause_payload": pausePayload}
			}
			s.repository.UpdateNodeRun(nodeCtx, nodeRun)

			// Save state snapshot for durable resume
			stateSnapshot := rc.state.Snapshot()
			completedNodes := make([]string, 0, len(rc.completed))
			skippedNodes := make([]string, 0, len(rc.skipped))
			rc.pendingMu.Lock()
			for id := range rc.completed {
				completedNodes = append(completedNodes, id)
			}
			for id := range rc.skipped {
				skippedNodes = append(skippedNodes, id)
			}
			rc.pendingMu.Unlock()

			s.repository.SavePauseState(
				rc.intentContext(context.Background()),
				rc.runID,
				nodeID,
				stateSnapshot,
				completedNodes,
				skippedNodes,
				rc.graphJSON,
				rc.tenantID,
			)
			s.repository.UpdateRunStatus(rc.intentContext(context.Background()), rc.runID, string(value.RunStatusPaused))

			// Emit pause event with the pause payload
			pauseEvent := rc.newEventFromContext(nodeCtx, port.EventTypeRunPaused).
				WithNode(nodeID, node.Type, node.Name)
			if len(pausePayload) > 0 {
				pauseEvent = pauseEvent.WithOutput(pausePayload)
			}
			s.emitter.EmitAsync(pauseEvent)
			s.flushEmitter("run_paused")
		}

		rc.cancel() // Stop further processing
		return
	}

	s.handleNodeSuccess(nodeCtx, rc, node, nodeRun, result, duration)

	if cacheEnabled && cacheKey != "" && result.Output != nil {
		if err := s.repository.SaveCachedNodeResult(context.Background(), cacheKey, result.Output, cacheTTLSeconds); err != nil {
			log.Printf("Failed to save cache for node %s: %v", nodeID, err)
		}
	}
}

// executeWithRetries handles retry logic
func (s *Scheduler) executeWithRetries(ctx context.Context, rc *runContext, node *entity.Node, executor port.NodeExecutor, nodeRun *entity.NodeRun) (*port.NodeExecutionResult, error) {
	policy := s.resolveRetryPolicy(node)
	baseAttempt := nodeRun.Attempt

	timeout := node.TimeoutMs
	if timeout == 0 {
		timeout = s.config.DefaultTimeoutMs
	}

	var lastErr error
	for attempt := 1; attempt <= policy.MaxAttempts; attempt++ {
		nodeRun.Attempt = baseAttempt + attempt - 1

		// Create timeout context
		execCtx, cancel := context.WithTimeout(ctx, time.Duration(timeout)*time.Millisecond)
		if node.Type == string(value.NodeTypePrompt) || node.Type == string(value.NodeTypeAgent) {
			var chunkIndex int64
			execCtx = port.WithStreamChunkEmitter(execCtx, func(chunk string) {
				if strings.TrimSpace(chunk) == "" {
					return
				}
				index := atomic.AddInt64(&chunkIndex, 1)
				s.emitter.EmitAsync(
					rc.newEventFromContext(execCtx, port.EventTypeNodeStreamChunk).
						WithNode(node.ID, node.Type, node.Name).
						WithAttempt(attempt).
						WithOutput(
							map[string]any{
								"chunk":       chunk,
								"chunk_index": index,
							},
						),
				)
			})
		}

		s.hooks.beforeNodeExecute(rc.runID, node.ID)
		result, err := executor.Execute(execCtx, node, rc.state)
		cancel()

		if err == nil && result.Error == nil {
			return result, nil
		}

		// Use result.Error if set
		if err == nil && result.Error != nil {
			err = result.Error
		}

		lastErr = err

		if node.Type == string(value.NodeTypeTool) && !toolNodeAllowsSchedulerRetry(node) {
			return nil, err
		}

		// Check if error is retryable
		if !domain.IsRetryable(err) {
			return nil, err
		}

		// Emit retry event
		if attempt < policy.MaxAttempts {
			s.emitter.EmitAsync(
				rc.newEventFromContext(execCtx, port.EventTypeNodeRetrying).
					WithNode(node.ID, node.Type, node.Name).
					WithAttempt(baseAttempt + attempt).
					WithAttemptID(rc.attemptID).
					WithError(err.Error()),
			)

			// Calculate backoff
			backoff := s.calculateBackoff(policy, attempt)
			if retryAfterMs := domain.RetryAfterMsFromError(err); retryAfterMs > backoff {
				backoff = retryAfterMs
			}
			select {
			case <-rc.ctx.Done():
				return nil, rc.ctx.Err()
			case <-s.clock.After(time.Duration(backoff) * time.Millisecond):
			}
		}
	}

	return nil, fmt.Errorf("max retries exceeded: %w", lastErr)
}

func (s *Scheduler) baseAttemptForVisit(node *entity.Node, visitCount int) int {
	if visitCount <= 1 {
		return 1
	}
	maxAttempts := 1
	if node != nil {
		policy := s.resolveRetryPolicy(node)
		if policy != nil && policy.MaxAttempts > 0 {
			maxAttempts = policy.MaxAttempts
		}
	}
	return ((visitCount - 1) * maxAttempts) + 1
}

func (s *Scheduler) handleNodeFailure(ctx context.Context, rc *runContext, node *entity.Node, nodeRun *entity.NodeRun, err error, durationMs int64) bool {
	if node.Type == string(value.NodeTypeTool) {
		intentType := "tool_execution_failed"
		if domain.IsAmbiguousOutcome(err) {
			intentType = "tool_execution_ambiguous"
		}
		if publishErr := s.publishToolExecutionStatusIntent(
			rc.intentContext(context.Background()),
			rc,
			node,
			intentType,
			err.Error(),
			err,
		); publishErr != nil {
			s.setError(rc, fmt.Errorf("failed to publish %s intent: %w", intentType, publishErr))
			return false
		}
	}
	onError := parseOnErrorPolicy(node)
	retryPolicy := s.resolveRetryPolicy(node)

	nextNodes, skippedNodes, continueRun, routeErr := s.resolveOnErrorRouting(rc, node, onError)
	if routeErr != nil {
		continueRun = false
	}

	errorPayload := s.buildNodeErrorPayload(err, nodeRun.Attempt, retryPolicy, onError, nextNodes, routeErr)

	nodeRun.Status = string(value.NodeRunStatusFailed)
	nodeRun.SetEnded(s.clock.Now())
	nodeRun.ErrorJSON = errorPayload
	s.repository.UpdateNodeRun(ctx, nodeRun)

	failedEvent := rc.newEventFromContext(ctx, port.EventTypeNodeFailed).
		WithNode(node.ID, node.Type, node.Name).
		WithAttempt(nodeRun.Attempt).
		WithAttemptID(rc.attemptID).
		WithError(err.Error()).
		WithDuration(durationMs).
		WithOutput(map[string]any{"error": errorPayload})
	s.emitter.EmitAsync(failedEvent)

	if !continueRun {
		return false
	}

	rc.pendingMu.Lock()
	rc.completed[node.ID] = true
	rc.pendingMu.Unlock()

	stateError := map[string]any{
		"status":          "failed",
		"on_error_action": onError.Strategy,
		"error":           errorPayload,
	}
	if len(nextNodes) > 0 {
		stateError["next_nodes"] = append([]string(nil), nextNodes...)
	}
	rc.state.SetNodeOutput(node.ID, stateError)
	stateDelta, deletedKeys := computeStateDelta(nodeRun.InputJSON, rc.state.Snapshot())
	if len(stateDelta) > 0 {
		if nodeRun.OutputJSON == nil {
			nodeRun.OutputJSON = map[string]any{}
		}
		nodeRun.OutputJSON["state_delta"] = stateDelta
	}
	if len(deletedKeys) > 0 {
		if nodeRun.OutputJSON == nil {
			nodeRun.OutputJSON = map[string]any{}
		}
		nodeRun.OutputJSON["deleted_state_keys"] = deletedKeys
	}

	if !rc.allowCycles {
		for _, skippedNodeID := range skippedNodes {
			s.markSkipped(rc, skippedNodeID)
		}
	}

	s.repository.UpdateNodeRun(ctx, nodeRun)

	for _, nextNodeID := range nextNodes {
		s.decrementAndEnqueue(rc, nextNodeID)
	}

	s.saveCheckpoint(rc, node.ID, nextNodes, nodeRun.Attempt)
	return true
}

// calculateBackoff computes the backoff duration
func (s *Scheduler) calculateBackoff(policy *entity.RetryPolicy, attempt int) int {
	if policy.BackoffStrategy == "exponential" {
		return policy.BackoffMs * (1 << (attempt - 1))
	}
	return policy.BackoffMs
}

// determineNextNodes selects which nodes should run next.
// It may mark untaken branches as skipped, but it does not schedule execution.
func (s *Scheduler) determineNextNodes(rc *runContext, node *entity.Node, result *port.NodeExecutionResult) ([]string, string) {
	edges := rc.plan.GetOutgoingEdges(node.ID)
	if len(edges) == 0 {
		return nil, "terminal"
	}

	// For branch nodes, only enqueue specified next nodes
	if result.HasNextNodes() {
		outgoingSet := make(map[string]bool)
		for _, edge := range edges {
			outgoingSet[edge.To] = true
		}

		validNext := make([]string, 0, len(result.NextNodes))
		var invalid []string
		for _, nextID := range result.NextNodes {
			if outgoingSet[nextID] {
				validNext = append(validNext, nextID)
			} else {
				invalid = append(invalid, nextID)
			}
		}

		if len(invalid) > 0 {
			s.setError(rc, domain.NewValidationError("next_nodes", fmt.Sprintf("invalid next_nodes: %v", invalid)))
			return nil, "routing_error"
		}

		if !rc.allowCycles {
			nextSet := make(map[string]bool)
			for _, n := range validNext {
				nextSet[n] = true
			}

			// Mark non-taken branches as skipped
			for _, edge := range edges {
				if !nextSet[edge.To] {
					s.markSkipped(rc, edge.To)
				}
			}
		}

		return validNext, "next_nodes"
	}

	// Edge-level conditional routing for any node (when no explicit next_nodes set)
	if len(edges) > 0 {
		nextIDs, skippedIDs, usedConditions, err := s.evaluateEdgeConditions(rc, edges)
		if err != nil {
			s.setError(rc, domain.NewValidationError("edge_condition", err.Error()))
			return nil, "condition_error"
		}
		if usedConditions {
			if !rc.allowCycles {
				for _, skippedID := range skippedIDs {
					s.markSkipped(rc, skippedID)
				}
			}
			if len(nextIDs) == 0 {
				return nil, "condition_no_match"
			}
			return nextIDs, "condition_routing"
		}
	}

	// For all other nodes, enqueue all children
	nextIDs := make([]string, 0, len(edges))
	for _, edge := range edges {
		nextIDs = append(nextIDs, edge.To)
	}
	return nextIDs, "fan_out"
}

func (s *Scheduler) enqueueNodeIDs(rc *runContext, nextNodeIDs []string) {
	for _, nextNodeID := range nextNodeIDs {
		s.decrementAndEnqueue(rc, nextNodeID)
	}
}

func extractNextNodesFromOutput(output any) ([]string, bool, error) {
	outputMap, ok := output.(map[string]any)
	if !ok {
		return nil, false, nil
	}

	var raw any
	if value, ok := outputMap["next_nodes"]; ok {
		raw = value
	} else if value, ok := outputMap["next_node"]; ok {
		raw = value
	} else {
		return nil, false, nil
	}

	switch typed := raw.(type) {
	case string:
		if typed == "" {
			return nil, true, domain.NewValidationError("next_nodes", "next_node cannot be empty")
		}
		return []string{typed}, true, nil
	case []string:
		return typed, true, nil
	case []any:
		parsed := make([]string, 0, len(typed))
		for _, item := range typed {
			value, ok := item.(string)
			if !ok || value == "" {
				return nil, true, domain.NewValidationError("next_nodes", "next_nodes must contain non-empty strings")
			}
			parsed = append(parsed, value)
		}
		return parsed, true, nil
	default:
		return nil, true, domain.NewValidationError("next_nodes", "next_nodes must be a string or list of strings")
	}
}

func (s *Scheduler) handleNodeSuccess(ctx context.Context, rc *runContext, node *entity.Node, nodeRun *entity.NodeRun, result *port.NodeExecutionResult, durationMs int64) {
	nodeID := node.ID
	if node.Type == string(value.NodeTypeTool) {
		if err := s.publishToolExecutionStatusIntent(
			rc.intentContext(context.Background()),
			rc,
			node,
			"tool_execution_succeeded",
			"",
			nil,
		); err != nil {
			s.setError(rc, fmt.Errorf("failed to publish tool_execution_succeeded intent: %w", err))
			return
		}
	}

	// Allow any node to emit routing directives via output.next_nodes / output.next_node
	if !result.HasNextNodes() {
		nextNodes, hasDirective, directiveErr := extractNextNodesFromOutput(result.Output)
		if directiveErr != nil {
			// Treat invalid routing directive as node failure
			nodeRun.Status = string(value.NodeRunStatusFailed)
			nodeRun.SetEnded(s.clock.Now())
			nodeRun.ErrorJSON = map[string]any{"error": directiveErr.Error()}
			s.repository.UpdateNodeRun(ctx, nodeRun)

			s.emitter.EmitAsync(
				rc.newEventFromContext(ctx, port.EventTypeNodeFailed).
					WithNode(nodeID, node.Type, node.Name).
					WithError(directiveErr.Error()).
					WithDuration(durationMs),
			)
			s.setError(rc, domain.NewNodeError(nodeID, node.Type, directiveErr))
			return
		}
		if hasDirective && len(nextNodes) > 0 {
			result.NextNodes = nextNodes
			if outputMap, ok := result.Output.(map[string]any); ok {
				delete(outputMap, "next_nodes")
				delete(outputMap, "next_node")
			}
		}
	}

	// Store output in state
	if result.Output != nil {
		rc.state.SetNodeOutput(nodeID, result.Output)
	}

	if !s.validateStateSchema(ctx, rc, node, nodeRun, durationMs) {
		return
	}

	// Update node run as completed
	nodeRun.Status = string(value.NodeRunStatusSucceeded)
	nodeRun.SetEnded(s.clock.Now())

	// Mark completed
	rc.pendingMu.Lock()
	rc.completed[nodeID] = true
	rc.pendingMu.Unlock()

	// Determine next nodes before emitting completion so the completion event is
	// always observed before any downstream node can start.
	nextNodes, exitReason := s.determineNextNodes(rc, node, result)

	loopDiagnostics := s.buildLoopDiagnostics(rc, nodeID, exitReason, nextNodes)
	nodeOutput := map[string]any{}
	if result.Output != nil {
		nodeOutput["output"] = result.Output
	}
	if len(loopDiagnostics) > 0 {
		nodeOutput["loop"] = loopDiagnostics
	}
	if len(nodeOutput) > 0 {
		nodeRun.OutputJSON = nodeOutput
	}
	s.repository.UpdateNodeRun(ctx, nodeRun)

	// Emit node completed
	completedEvent := rc.newEventFromContext(ctx, port.EventTypeNodeCompleted).
		WithNode(nodeID, node.Type, node.Name).
		WithAttempt(nodeRun.Attempt).
		WithAttemptID(rc.attemptID).
		WithDuration(durationMs)
	if len(nodeRun.OutputJSON) > 0 {
		completedEvent = completedEvent.WithOutput(nodeRun.OutputJSON)
	}
	s.emitter.EmitAsync(completedEvent)

	s.enqueueNodeIDs(rc, nextNodes)

	// Trigger summarization if configured
	s.maybeTriggerSummarization(rc, node)

	stateDelta, deletedKeys := computeStateDelta(nodeRun.InputJSON, rc.state.Snapshot())
	if len(stateDelta) > 0 {
		if nodeRun.OutputJSON == nil {
			nodeRun.OutputJSON = map[string]any{}
		}
		nodeRun.OutputJSON["state_delta"] = stateDelta
	}
	if len(deletedKeys) > 0 {
		if nodeRun.OutputJSON == nil {
			nodeRun.OutputJSON = map[string]any{}
		}
		nodeRun.OutputJSON["deleted_state_keys"] = deletedKeys
	}
	s.repository.UpdateNodeRun(ctx, nodeRun)

	s.saveCheckpoint(rc, nodeID, nextNodes, nodeRun.Attempt)
}

func (s *Scheduler) maybeTriggerSummarization(rc *runContext, node *entity.Node) {
	if s.summarizer == nil || rc == nil || rc.memoryConfig == nil || rc.messageBuffer == nil {
		return
	}
	if node == nil || node.Type != string(value.NodeTypePrompt) {
		return
	}

	cfg := rc.memoryConfig.Summarization
	if !cfg.Enabled || cfg.TriggerThreshold <= 0 {
		return
	}

	if !rc.canSummarize(cfg) {
		return
	}

	messages := rc.messageBuffer.Snapshot()
	if len(messages) == 0 {
		return
	}

	rc.markSummaryInFlight()

	req := SummarizationRequest{
		RunID:             rc.runID,
		TenantID:          rc.tenantID,
		Messages:          messages,
		Options:           port.SummarizeOptions{Model: cfg.Model, PreserveFacts: true},
		SummaryTTLSeconds: rc.memoryConfig.Tier2.SummaryTTL,
		FactsTTLSeconds:   rc.memoryConfig.Tier2.FactsTTL,
		Callback: func(summary *entity.Summary, err error) {
			if err != nil {
				rc.clearSummaryInFlight()
				metrics.RecordSummarizationTrigger("error")
				log.Printf("Summarization failed for run %s: %v", rc.runID, err)
				return
			}

			rc.applySummary(summary, cfg)
			s.trimMemoryBuffer(rc, cfg.KeepRecentCount)
			metrics.RecordSummarizationTrigger("success")
		},
	}

	if err := s.summarizer.Submit(req); err != nil {
		rc.clearSummaryInFlight()
		metrics.RecordSummarizationTrigger("queue_full")
		log.Printf("Summarization queue full for run %s: %v", rc.runID, err)
		return
	}
	metrics.RecordSummarizationTrigger("submitted")
}

func (s *Scheduler) trimMemoryBuffer(rc *runContext, keepRecent int) {
	if rc == nil || rc.messageBuffer == nil {
		return
	}

	if keepRecent <= 0 {
		rc.messageBuffer.Clear()
		return
	}

	messages := rc.messageBuffer.GetAll()
	if len(messages) <= keepRecent {
		return
	}

	rc.messageBuffer.RemoveFirst(len(messages) - keepRecent)
}

func (s *Scheduler) isCheckpointingEnabled() bool {
	return s.config.CheckpointMode != CheckpointModeNone
}

func (s *Scheduler) buildCheckpointSnapshot(rc *runContext, stepIndex int) (map[string]any, []string, []string) {
	rc.pendingMu.Lock()
	completedNodes := make([]string, 0, len(rc.completed))
	for id := range rc.completed {
		completedNodes = append(completedNodes, id)
	}
	skippedNodes := make([]string, 0, len(rc.skipped))
	for id := range rc.skipped {
		skippedNodes = append(skippedNodes, id)
	}
	pendingSnapshot := make(map[string]int, len(rc.pending))
	for id, count := range rc.pending {
		pendingSnapshot[id] = count
	}
	visitCounts := make(map[string]int, len(rc.visitCounts))
	for id, count := range rc.visitCounts {
		visitCounts[id] = count
	}
	rc.pendingMu.Unlock()

	checkpointPayload := map[string]any{
		"checkpoint_version": checkpointPayloadV2,
		"state":              rc.state.Snapshot(),
		"completed":          completedNodes,
		"skipped":            skippedNodes,
		"pending":            pendingSnapshot,
		"visit_counts":       visitCounts,
	}
	if rc.messageBuffer != nil {
		bufferSnapshot := rc.messageBuffer.Snapshot()
		checkpointPayload["message_buffer"] = bufferSnapshot
		s.persistSessionBuffer(rc, bufferSnapshot)
	}
	if rc.memoryConfig != nil {
		checkpointPayload["memory_config"] = rc.memoryConfig
	}
	if rc.currentSummary != nil {
		checkpointPayload["current_summary"] = rc.currentSummary
	}

	_ = stepIndex
	return checkpointPayload, completedNodes, skippedNodes
}

func (s *Scheduler) saveCheckpoint(rc *runContext, nodeID string, nextNodes []string, attempt int) {
	if !s.isCheckpointingEnabled() {
		return
	}

	stepIndex := int(atomic.AddInt64(&rc.checkpointSeq, 1))
	if s.config.CheckpointMode == CheckpointModeBatch {
		if !s.shouldSaveBatchCheckpoint(rc, stepIndex) {
			return
		}
	}
	checkpointPayload, completedNodes, skippedNodes := s.buildCheckpointSnapshot(rc, stepIndex)

	if err := s.repository.SaveCheckpoint(rc.intentContext(context.Background()), rc.runID, nodeID, stepIndex, checkpointPayload, completedNodes, skippedNodes, rc.graphJSON); err != nil {
		log.Printf("Failed to save checkpoint for run %s: %v", rc.runID, err)
	}
	if err := s.publishNodeCompletedIntent(rc.intentContext(context.Background()), rc, nodeID, nextNodes, attempt); err != nil {
		log.Printf("Failed to publish node_completed intent for run %s: %v", rc.runID, err)
		return
	}
	rc.checkpointMu.Lock()
	rc.lastCheckpointAt = s.clock.Now()
	rc.checkpointMu.Unlock()
}

func (s *Scheduler) publishNodeCompletedIntent(
	ctx context.Context,
	rc *runContext,
	nodeID string,
	nextNodes []string,
	attempt int,
) error {
	if s.runtimeIntentPublisher == nil {
		return nil
	}

	nextNode := ""
	if len(nextNodes) > 0 {
		nextNode = nextNodes[0]
	}
	intent := &port.RuntimeIntentEnvelope{
		IntentID:   uuid.NewString(),
		IntentType: "node_completed",
		RunID:      rc.runID,
		AttemptID:  rc.attemptID,
		TraceID:    rc.traceID,
		Timestamp:  s.clock.Now().UTC().Format(time.RFC3339Nano),
		Payload: map[string]any{
			"node_id":   nodeID,
			"attempt":   attempt,
			"next_node": nextNode,
		},
	}
	return s.runtimeIntentPublisher.Publish(ctx, intent)
}

func (s *Scheduler) publishToolExecutionStatusIntent(
	ctx context.Context,
	rc *runContext,
	node *entity.Node,
	intentType string,
	reason string,
	execErr error,
) error {
	if s.runtimeIntentPublisher == nil || node == nil {
		return nil
	}
	toolExecutionID := strings.TrimSpace(node.GetConfigString("tool_execution_id"))
	idempotencyKey := strings.TrimSpace(node.GetConfigString("idempotency_key"))
	sideEffectClass := strings.TrimSpace(node.GetConfigString("side_effect_class"))
	if toolExecutionID == "" {
		log.Printf("tool_execution_identity_missing: run_id=%s node_id=%s intent_type=%s", rc.runID, node.ID, intentType)
		return nil
	}
	payload := map[string]any{
		"tool_execution_id": toolExecutionID,
		"node_id":           node.ID,
		"tool_name":         strings.TrimSpace(node.GetConfigString("tool")),
		"tool_version":      strings.TrimSpace(node.GetConfigString("version")),
		"idempotency_key":   idempotencyKey,
		"side_effect_class": sideEffectClass,
		"reason":            reason,
	}
	if payload["tool_name"] == "" {
		payload["tool_name"] = strings.TrimSpace(node.GetConfigString("tool_name"))
	}
	if strings.TrimSpace(idempotencyKey) != "" {
		payload["idempotency_applied"] = true
	}
	if execErr != nil {
		payload["error_class"] = fmt.Sprintf("%T", execErr)
		if domain.IsAmbiguousOutcome(execErr) {
			payload["ambiguous_code"] = domain.AmbiguousCodeFromError(execErr)
			if details := domain.AmbiguousDetailsFromError(execErr); len(details) > 0 {
				payload["ambiguous_details"] = details
			}
		}
	}
	intent := &port.RuntimeIntentEnvelope{
		IntentID:   uuid.NewString(),
		IntentType: intentType,
		RunID:      rc.runID,
		AttemptID:  rc.attemptID,
		TraceID:    rc.traceID,
		Timestamp:  s.clock.Now().UTC().Format(time.RFC3339Nano),
		Payload:    payload,
	}
	log.Printf("tool_execution_intent_publish: run_id=%s node_id=%s tool_execution_id=%s intent_type=%s idempotency_key=%s",
		rc.runID, node.ID, toolExecutionID, intentType, idempotencyKey)
	return s.runtimeIntentPublisher.Publish(ctx, intent)
}

func (s *Scheduler) publishPauseRunIntent(
	ctx context.Context,
	rc *runContext,
	node *entity.Node,
	nodeRun *entity.NodeRun,
	pausePayload map[string]any,
) error {
	if !s.pauseIntentPublishingEnabled() {
		return nil
	}

	stepIndex := int(atomic.AddInt64(&rc.checkpointSeq, 1))
	checkpointPayload, completedNodes, skippedNodes := s.buildCheckpointSnapshot(rc, stepIndex)

	intent := &port.RuntimeIntentEnvelope{
		IntentID:   uuid.NewString(),
		IntentType: "pause_run",
		RunID:      rc.runID,
		AttemptID:  rc.attemptID,
		TraceID:    rc.traceID,
		Timestamp:  s.clock.Now().UTC().Format(time.RFC3339Nano),
		Payload: map[string]any{
			"node_id":       node.ID,
			"node_type":     node.Type,
			"node_name":     node.Name,
			"node_attempt":  nodeRun.Attempt,
			"pause_payload": pausePayload,
			"checkpoint": map[string]any{
				"node_id":         node.ID,
				"step_index":      stepIndex,
				"state_snapshot":  checkpointPayload,
				"completed_nodes": completedNodes,
				"skipped_nodes":   skippedNodes,
				"graph_json":      rc.graphJSON,
			},
			"pause_state": map[string]any{
				"state_snapshot":  rc.state.Snapshot(),
				"completed_nodes": completedNodes,
				"skipped_nodes":   skippedNodes,
				"graph_json":      rc.graphJSON,
				"tenant_id":       rc.tenantID,
			},
		},
	}
	if err := s.runtimeIntentPublisher.Publish(ctx, intent); err != nil {
		atomic.AddInt64(&rc.checkpointSeq, -1)
		return err
	}
	rc.pauseIntentPublished = true
	rc.checkpointMu.Lock()
	rc.lastCheckpointAt = s.clock.Now()
	rc.checkpointMu.Unlock()
	return nil
}

func (s *Scheduler) publishAckRunResumedIntent(
	ctx context.Context,
	rc *runContext,
	nodeID string,
	resumeAttemptID string,
	resolution map[string]any,
) error {
	if s.runtimeIntentPublisher == nil {
		return fmt.Errorf("runtime intent publisher is not configured")
	}
	activeAttemptID := strings.TrimSpace(resumeAttemptID)
	if activeAttemptID == "" {
		activeAttemptID = rc.attemptID
	}
	intent := &port.RuntimeIntentEnvelope{
		IntentID:   uuid.NewString(),
		IntentType: "ack_run_resumed",
		RunID:      rc.runID,
		AttemptID:  activeAttemptID,
		Timestamp:  s.clock.Now().UTC().Format(time.RFC3339Nano),
		TraceID:    rc.traceID,
		Payload: map[string]any{
			"node_id":    nodeID,
			"resolution": resolution,
		},
	}
	return s.runtimeIntentPublisher.Publish(ctx, intent)
}

func (s *Scheduler) shouldSaveBatchCheckpoint(rc *runContext, stepIndex int) bool {
	if s.config.CheckpointBatchSize > 0 && stepIndex%s.config.CheckpointBatchSize == 0 {
		return true
	}

	if s.config.CheckpointIntervalMs > 0 {
		rc.checkpointMu.Lock()
		lastCheckpointAt := rc.lastCheckpointAt
		rc.checkpointMu.Unlock()
		if lastCheckpointAt.IsZero() {
			return true
		}
		if s.clock.Now().Sub(lastCheckpointAt) >= time.Duration(s.config.CheckpointIntervalMs)*time.Millisecond {
			return true
		}
	}

	return false
}

func (s *Scheduler) applyCheckpointToPending(rc *runContext) {
	for nodeID := range rc.completed {
		s.decrementPendingForCheckpoint(rc, nodeID)
	}
	for nodeID := range rc.skipped {
		s.decrementPendingForCheckpoint(rc, nodeID)
	}
}

func (s *Scheduler) decrementPendingForCheckpoint(rc *runContext, nodeID string) {
	for _, edge := range rc.plan.GetOutgoingEdges(nodeID) {
		rc.pending[edge.To]--
	}
}

func (s *Scheduler) computeReadyNodes(rc *runContext) []string {
	ready := make([]string, 0, len(rc.plan.NodeMap))
	for nodeID := range rc.plan.NodeMap {
		if rc.skipped[nodeID] {
			continue
		}
		maxVisits := s.maxVisitsForNode(rc, rc.plan.GetNode(nodeID))
		if rc.completed[nodeID] && (!rc.allowCycles || rc.visitCounts[nodeID] >= maxVisits) {
			continue
		}
		if rc.visitCounts[nodeID] >= maxVisits && rc.resumeRetryNode != nodeID {
			continue
		}
		if rc.pending[nodeID] <= 0 {
			ready = append(ready, nodeID)
		}
	}
	return ready
}

func (s *Scheduler) initializePending(plan *service.ExecutionPlan, backEdges map[*entity.Edge]bool) map[string]int {
	pending := plan.CloneIndegree()
	if len(backEdges) == 0 {
		return pending
	}

	for _, edges := range plan.EdgeMap {
		for _, edge := range edges {
			if !backEdges[edge] {
				continue
			}
			pending[edge.To]--
			if pending[edge.To] < 0 {
				pending[edge.To] = 0
			}
		}
	}
	return pending
}

func (s *Scheduler) restorePendingSnapshot(plan *service.ExecutionPlan, snapshot map[string]int, backEdges map[*entity.Edge]bool) map[string]int {
	pending := s.initializePending(plan, backEdges)
	if len(snapshot) == 0 {
		return pending
	}

	for nodeID := range pending {
		value, ok := snapshot[nodeID]
		if !ok {
			continue
		}
		if value < 0 {
			pending[nodeID] = 0
			continue
		}
		pending[nodeID] = value
	}

	return pending
}

func (s *Scheduler) detectBackEdges(plan *service.ExecutionPlan, allowCycles bool) map[*entity.Edge]bool {
	if !allowCycles {
		return nil
	}

	backEdges := make(map[*entity.Edge]bool)
	color := make(map[string]int, len(plan.NodeMap))

	var dfs func(nodeID string)
	dfs = func(nodeID string) {
		color[nodeID] = 1 // gray
		for _, edge := range plan.GetOutgoingEdges(nodeID) {
			nextID := edge.To
			switch color[nextID] {
			case 0:
				dfs(nextID)
			case 1:
				backEdges[edge] = true
			}
		}
		color[nodeID] = 2 // black
	}

	for _, node := range plan.Graph.Nodes {
		if color[node.ID] == 0 {
			dfs(node.ID)
		}
	}
	for nodeID := range plan.NodeMap {
		if color[nodeID] == 0 {
			dfs(nodeID)
		}
	}

	return backEdges
}

func (s *Scheduler) maxVisitsForNode(rc *runContext, node *entity.Node) int {
	if node != nil && node.Config != nil {
		if maxVisits := coerceInt(node.Config["max_visits"]); maxVisits > 0 {
			return maxVisits
		}
	}
	if rc != nil && rc.allowCycles {
		if rc.defaultMaxVisits > 0 {
			return rc.defaultMaxVisits
		}
		return 25
	}
	return 1
}

func (s *Scheduler) buildLoopDiagnostics(rc *runContext, nodeID, exitReason string, nextNodes []string) map[string]any {
	if rc == nil || nodeID == "" {
		return nil
	}

	rc.pendingMu.Lock()
	iteration := rc.visitCounts[nodeID]
	rc.pendingMu.Unlock()

	if !rc.allowCycles && iteration <= 1 {
		return nil
	}

	diagnostics := map[string]any{
		"iteration_index": iteration,
	}
	if exitReason != "" {
		diagnostics["exit_reason"] = exitReason
	}
	if len(nextNodes) > 0 {
		diagnostics["next_nodes"] = nextNodes
	}
	return diagnostics
}

func (s *Scheduler) getCacheConfig(node *entity.Node) (enabled bool, ttlSeconds int) {
	if node.Config == nil {
		return false, 0
	}
	cacheRaw, ok := node.Config["cache"].(map[string]any)
	if !ok {
		return false, 0
	}
	enabled, _ = cacheRaw["enabled"].(bool)
	if !enabled {
		return false, 0
	}

	ttlSeconds = coerceInt(cacheRaw["ttl_seconds"])
	if ttlSeconds <= 0 {
		ttlSeconds = s.config.CacheDefaultTTLSeconds
	}
	if ttlSeconds <= 0 {
		return false, 0
	}

	return true, ttlSeconds
}

func (s *Scheduler) computeCacheKey(node *entity.Node, inputSnapshot map[string]any) (string, error) {
	payload := map[string]any{
		"node_type": node.Type,
		"config":    sanitizeConfig(node.Config),
		"input":     inputSnapshot,
	}
	encoded, err := json.Marshal(payload)
	if err != nil {
		return "", err
	}
	sum := sha256.Sum256(encoded)
	return hex.EncodeToString(sum[:]), nil
}

func sanitizeConfig(config map[string]any) map[string]any {
	if config == nil {
		return nil
	}
	sanitized := make(map[string]any, len(config))
	for key, value := range config {
		if key == "cache" || strings.HasPrefix(key, "_") {
			continue
		}
		sanitized[key] = value
	}
	return sanitized
}

func coerceInt(value any) int {
	switch v := value.(type) {
	case int:
		return v
	case int64:
		return int(v)
	case float64:
		return int(v)
	case float32:
		return int(v)
	case json.Number:
		if parsed, err := v.Int64(); err == nil {
			return int(parsed)
		}
	case string:
		if parsed, err := strconv.Atoi(v); err == nil {
			return parsed
		}
	}
	return 0
}

func coerceBool(value any) (bool, bool) {
	switch v := value.(type) {
	case bool:
		return v, true
	case string:
		if v == "true" || v == "1" {
			return true, true
		}
		if v == "false" || v == "0" {
			return false, true
		}
	}
	return false, false
}

func coerceFloat(value any) (float64, bool) {
	switch v := value.(type) {
	case float64:
		return v, true
	case float32:
		return float64(v), true
	case int:
		return float64(v), true
	case int64:
		return float64(v), true
	case json.Number:
		if parsed, err := v.Float64(); err == nil {
			return parsed, true
		}
	case string:
		if parsed, err := strconv.ParseFloat(v, 64); err == nil {
			return parsed, true
		}
	}
	return 0, false
}

func defaultMemoryConfig() *entity.MemoryConfig {
	return &entity.MemoryConfig{
		Tier1: entity.Tier1Config{
			Enabled:     true,
			BufferSize:  20,
			LimitMode:   "messages",
			MaxTokens:   4000,
			AutoPrepend: true,
		},
		Tier2: entity.Tier2Config{
			Enabled:    false,
			Namespace:  "",
			SummaryTTL: 86400,
			FactsTTL:   604800,
		},
		Tier3: entity.Tier3Config{
			Enabled:        false,
			TopK:           5,
			Threshold:      0.7,
			RecencyWeight:  0.2,
			EmbeddingModel: "text-embedding-ada-002",
		},
		Summarization: entity.SummarizationConfig{
			Enabled:          false,
			TriggerThreshold: 30,
			KeepRecentCount:  10,
			CooldownMessages: 10,
			Model:            "gpt-4",
		},
		CrossSession: entity.CrossSessionConfig{
			Enabled:         false,
			SessionTTLHours: 24,
			ShareWithAgent:  false,
		},
	}
}

func parseMemoryConfig(memoryConfigJSON string) *entity.MemoryConfig {
	cfg := defaultMemoryConfig()
	if memoryConfigJSON == "" {
		return cfg
	}

	var raw map[string]any
	if err := json.Unmarshal([]byte(memoryConfigJSON), &raw); err != nil {
		log.Printf("Invalid memory config JSON, using defaults: %v", err)
		return cfg
	}

	if tier1Raw, ok := raw["tier1"].(map[string]any); ok {
		if v, ok := coerceBool(tier1Raw["enabled"]); ok {
			cfg.Tier1.Enabled = v
		}
		if v := coerceInt(tier1Raw["buffer_size"]); v > 0 {
			cfg.Tier1.BufferSize = v
		}
		if v, ok := tier1Raw["limit_mode"].(string); ok {
			switch strings.ToLower(v) {
			case "tokens", "messages":
				cfg.Tier1.LimitMode = strings.ToLower(v)
			}
		}
		if v := coerceInt(tier1Raw["max_tokens"]); v > 0 {
			cfg.Tier1.MaxTokens = v
		}
		if v, ok := coerceBool(tier1Raw["auto_prepend"]); ok {
			cfg.Tier1.AutoPrepend = v
		}
	}

	if tier2Raw, ok := raw["tier2"].(map[string]any); ok {
		if v, ok := coerceBool(tier2Raw["enabled"]); ok {
			cfg.Tier2.Enabled = v
		}
		if v, ok := tier2Raw["namespace"].(string); ok {
			cfg.Tier2.Namespace = v
		}
		if v := coerceInt(tier2Raw["summary_ttl_seconds"]); v > 0 {
			cfg.Tier2.SummaryTTL = v
		}
		if v := coerceInt(tier2Raw["facts_ttl_seconds"]); v > 0 {
			cfg.Tier2.FactsTTL = v
		}
	}

	if tier3Raw, ok := raw["tier3"].(map[string]any); ok {
		if v, ok := coerceBool(tier3Raw["enabled"]); ok {
			cfg.Tier3.Enabled = v
		}
		if v := coerceInt(tier3Raw["top_k"]); v > 0 {
			cfg.Tier3.TopK = v
		}
		if v, ok := coerceFloat(tier3Raw["threshold"]); ok && v > 0 {
			cfg.Tier3.Threshold = v
		}
		if v, ok := coerceFloat(tier3Raw["recency_weight"]); ok && v >= 0 {
			cfg.Tier3.RecencyWeight = v
		}
		if v, ok := tier3Raw["embedding_model"].(string); ok && v != "" {
			cfg.Tier3.EmbeddingModel = v
		}
	}

	if summarizationRaw, ok := raw["summarization"].(map[string]any); ok {
		if v, ok := coerceBool(summarizationRaw["enabled"]); ok {
			cfg.Summarization.Enabled = v
		}
		if v := coerceInt(summarizationRaw["trigger_threshold"]); v > 0 {
			cfg.Summarization.TriggerThreshold = v
		}
		if v := coerceInt(summarizationRaw["keep_recent_count"]); v > 0 {
			cfg.Summarization.KeepRecentCount = v
		}
		if v := coerceInt(summarizationRaw["cooldown_messages"]); v > 0 {
			cfg.Summarization.CooldownMessages = v
		}
		if v, ok := summarizationRaw["model"].(string); ok && v != "" {
			cfg.Summarization.Model = v
		}
	}

	if crossSessionRaw, ok := raw["cross_session"].(map[string]any); ok {
		if v, ok := coerceBool(crossSessionRaw["enabled"]); ok {
			cfg.CrossSession.Enabled = v
		}
		if v := coerceInt(crossSessionRaw["session_ttl_hours"]); v > 0 {
			cfg.CrossSession.SessionTTLHours = v
		}
		if v, ok := coerceBool(crossSessionRaw["share_with_agent"]); ok {
			cfg.CrossSession.ShareWithAgent = v
		}
	}

	return cfg
}

func parseCheckpointPayload(stateSnapshot map[string]any, completedNodes []string, skippedNodes []string) (map[string]any, []entity.Message, *entity.MemoryConfig, *entity.Summary, []string, []string, map[string]int, map[string]int, int) {
	if stateSnapshot == nil {
		return map[string]any{}, nil, nil, nil, completedNodes, skippedNodes, nil, nil, 0
	}

	payloadVersion := coerceInt(stateSnapshot["checkpoint_version"])
	rawState, hasState := stateSnapshot["state"].(map[string]any)
	if !hasState {
		// Legacy payload format where the raw map is the state snapshot.
		return stateSnapshot, nil, nil, nil, completedNodes, skippedNodes, nil, nil, 1
	}

	parsedCompleted := completedNodes
	if rawCompleted, ok := stateSnapshot["completed"].([]any); ok {
		parsedCompleted = toStringSlice(rawCompleted)
	}

	parsedSkipped := skippedNodes
	if rawSkipped, ok := stateSnapshot["skipped"].([]any); ok {
		parsedSkipped = toStringSlice(rawSkipped)
	}

	var bufferSnapshot []entity.Message
	if rawBuffer, ok := stateSnapshot["message_buffer"]; ok {
		bufferSnapshot = decodeMessages(rawBuffer)
	}

	var memoryConfig *entity.MemoryConfig
	if rawConfig, ok := stateSnapshot["memory_config"]; ok {
		memoryConfig = decodeMemoryConfig(rawConfig)
	}

	var summary *entity.Summary
	if rawSummary, ok := stateSnapshot["current_summary"]; ok {
		summary = decodeSummary(rawSummary)
	}

	var pendingSnapshot map[string]int
	if rawPending, ok := stateSnapshot["pending"]; ok {
		pendingSnapshot = decodeStringIntMap(rawPending)
	}

	var visitCounts map[string]int
	if rawVisitCounts, ok := stateSnapshot["visit_counts"]; ok {
		visitCounts = decodeStringIntMap(rawVisitCounts)
	}

	if payloadVersion <= 0 {
		payloadVersion = 1
	}

	return rawState, bufferSnapshot, memoryConfig, summary, parsedCompleted, parsedSkipped, pendingSnapshot, visitCounts, payloadVersion
}

func (s *Scheduler) loadResumeCheckpoint(ctx context.Context, runID string) (*resumeCheckpoint, error) {
	snapshot, err := s.repository.LoadRunSnapshot(ctx, runID)
	if err != nil {
		return nil, err
	}
	if snapshot == nil || strings.TrimSpace(snapshot.LastCompletedNode) == "" {
		return nil, domain.ErrCheckpointNotFound
	}

	run, err := s.repository.GetRun(ctx, runID)
	if err != nil {
		return nil, err
	}
	nodeRuns, err := s.repository.GetNodeRunsByRunID(ctx, runID)
	if err != nil {
		return nil, err
	}

	state := entity.NewStateWithInput(run.InputJSON)
	sort.Slice(nodeRuns, func(i, j int) bool {
		leftEndedAt := time.Time{}
		rightEndedAt := time.Time{}
		if nodeRuns[i].EndedAt != nil {
			leftEndedAt = *nodeRuns[i].EndedAt
		}
		if nodeRuns[j].EndedAt != nil {
			rightEndedAt = *nodeRuns[j].EndedAt
		}
		if !leftEndedAt.Equal(rightEndedAt) {
			return leftEndedAt.Before(rightEndedAt)
		}
		if !nodeRuns[i].StartedAt.Equal(nodeRuns[j].StartedAt) {
			return nodeRuns[i].StartedAt.Before(nodeRuns[j].StartedAt)
		}
		if nodeRuns[i].Attempt != nodeRuns[j].Attempt {
			return nodeRuns[i].Attempt < nodeRuns[j].Attempt
		}
		return nodeRuns[i].NodeID < nodeRuns[j].NodeID
	})

	completedSet := make(map[string]bool)
	skippedSet := make(map[string]bool)
	visitCounts := make(map[string]int)

	for _, nodeRun := range nodeRuns {
		if nodeRun == nil {
			continue
		}
		if nodeRun.Attempt > visitCounts[nodeRun.NodeID] {
			visitCounts[nodeRun.NodeID] = nodeRun.Attempt
		}

		switch nodeRun.Status {
		case string(value.NodeRunStatusSucceeded):
			completedSet[nodeRun.NodeID] = true
			applyStoredNodeStateDelta(state, nodeRun)
		case string(value.NodeRunStatusSkipped):
			skippedSet[nodeRun.NodeID] = true
		case string(value.NodeRunStatusFailed):
			if shouldTreatFailedNodeAsCompleted(nodeRun) {
				completedSet[nodeRun.NodeID] = true
				applyStoredNodeStateDelta(state, nodeRun)
			}
		}
	}

	if !completedSet[snapshot.LastCompletedNode] {
		return nil, fmt.Errorf("snapshot last_completed_node %s has no durable completed node run", snapshot.LastCompletedNode)
	}

	completedNodes := make([]string, 0, len(completedSet))
	for nodeID := range completedSet {
		completedNodes = append(completedNodes, nodeID)
	}
	sort.Strings(completedNodes)

	skippedNodes := make([]string, 0, len(skippedSet))
	for nodeID := range skippedSet {
		skippedNodes = append(skippedNodes, nodeID)
	}
	sort.Strings(skippedNodes)

	return &resumeCheckpoint{
		stepIndex:      max(len(completedNodes), 1),
		stateSnapshot:  state.Snapshot(),
		completedNodes: completedNodes,
		skippedNodes:   skippedNodes,
		visitCounts:    visitCounts,
		nextNode:       snapshot.NextNode,
		attemptID:      snapshot.AttemptID,
	}, nil
}

func shouldTreatFailedNodeAsCompleted(nodeRun *entity.NodeRun) bool {
	if nodeRun == nil {
		return false
	}
	if nodeRun.OutputJSON != nil {
		if _, ok := nodeRun.OutputJSON["state_delta"]; ok {
			return true
		}
	}
	action, _ := nodeRun.ErrorJSON["on_error_action"].(string)
	switch strings.ToLower(strings.TrimSpace(action)) {
	case onErrorStrategySkip, onErrorStrategyFallback:
		return true
	default:
		return false
	}
}

func applyStoredNodeStateDelta(state *entity.State, nodeRun *entity.NodeRun) {
	if state == nil || nodeRun == nil {
		return
	}
	if delta, ok := nodeRun.OutputJSON["state_delta"].(map[string]any); ok && len(delta) > 0 {
		for key, value := range delta {
			state.Set(key, value)
		}
	}
	if rawDeleted, ok := nodeRun.OutputJSON["deleted_state_keys"].([]any); ok {
		for _, item := range rawDeleted {
			if key, ok := item.(string); ok && key != "" {
				state.Delete(key)
			}
		}
	}
	if rawDeleted, ok := nodeRun.OutputJSON["deleted_state_keys"].([]string); ok {
		for _, key := range rawDeleted {
			if key != "" {
				state.Delete(key)
			}
		}
	}
	if _, ok := nodeRun.OutputJSON["state_delta"]; ok {
		return
	}
	if output, ok := nodeRun.OutputJSON["output"]; ok {
		state.SetNodeOutput(nodeRun.NodeID, output)
	}
}

func computeStateDelta(before map[string]any, after map[string]any) (map[string]any, []string) {
	delta := make(map[string]any)
	deleted := make([]string, 0)

	for key, nextValue := range after {
		if previousValue, ok := before[key]; ok && reflect.DeepEqual(previousValue, nextValue) {
			continue
		}
		delta[key] = nextValue
	}
	for key := range before {
		if _, ok := after[key]; !ok {
			deleted = append(deleted, key)
		}
	}
	sort.Strings(deleted)
	return delta, deleted
}

func toStringSlice(raw []any) []string {
	out := make([]string, 0, len(raw))
	for _, value := range raw {
		if str, ok := value.(string); ok && str != "" {
			out = append(out, str)
		}
	}
	return out
}

func decodeMessages(raw any) []entity.Message {
	bytes, err := json.Marshal(raw)
	if err != nil {
		return nil
	}
	var msgs []entity.Message
	if err := json.Unmarshal(bytes, &msgs); err != nil {
		return nil
	}
	return msgs
}

func decodeMemoryConfig(raw any) *entity.MemoryConfig {
	bytes, err := json.Marshal(raw)
	if err != nil {
		return nil
	}
	var cfg entity.MemoryConfig
	if err := json.Unmarshal(bytes, &cfg); err != nil {
		return nil
	}
	// Ensure defaults for missing numeric fields.
	if cfg.Tier1.BufferSize <= 0 {
		cfg.Tier1.BufferSize = 20
	}
	if cfg.Tier1.LimitMode == "" {
		cfg.Tier1.LimitMode = "messages"
	}
	if cfg.Tier1.MaxTokens <= 0 {
		cfg.Tier1.MaxTokens = 4000
	}
	if cfg.Tier2.SummaryTTL <= 0 {
		cfg.Tier2.SummaryTTL = 86400
	}
	if cfg.Tier2.FactsTTL <= 0 {
		cfg.Tier2.FactsTTL = 604800
	}
	if cfg.Tier3.TopK <= 0 {
		cfg.Tier3.TopK = 5
	}
	if cfg.Tier3.Threshold <= 0 {
		cfg.Tier3.Threshold = 0.7
	}
	if cfg.Tier3.RecencyWeight < 0 {
		cfg.Tier3.RecencyWeight = 0.2
	}
	if cfg.Tier3.EmbeddingModel == "" {
		cfg.Tier3.EmbeddingModel = "text-embedding-ada-002"
	}
	if cfg.CrossSession.SessionTTLHours <= 0 {
		cfg.CrossSession.SessionTTLHours = 24
	}
	return &cfg
}

func decodeSummary(raw any) *entity.Summary {
	bytes, err := json.Marshal(raw)
	if err != nil {
		return nil
	}
	var summary entity.Summary
	if err := json.Unmarshal(bytes, &summary); err != nil {
		return nil
	}
	return &summary
}

func decodeStringIntMap(raw any) map[string]int {
	bytes, err := json.Marshal(raw)
	if err != nil {
		return nil
	}

	decoded := make(map[string]any)
	if err := json.Unmarshal(bytes, &decoded); err != nil {
		return nil
	}

	out := make(map[string]int, len(decoded))
	for key, value := range decoded {
		if key == "" {
			continue
		}
		out[key] = coerceInt(value)
	}
	return out
}

func (s *Scheduler) shouldUseSessionMemory(cfg *entity.MemoryConfig) bool {
	if cfg == nil {
		return false
	}
	return cfg.CrossSession.Enabled
}

func (s *Scheduler) loadSessionBuffer(ctx context.Context, tenantID, sessionID string) []entity.Message {
	if s.memoryStore == nil || sessionID == "" {
		return nil
	}
	namespace := sessionNamespace(tenantID)
	key := sessionBufferKey(sessionID)
	value, found, err := s.memoryStore.Get(ctx, namespace, key)
	if err != nil || !found {
		if err != nil {
			log.Printf("Failed to load session buffer for %s: %v", sessionID, err)
		}
		return nil
	}
	return decodeMessages(value)
}

func (s *Scheduler) persistSessionBuffer(rc *runContext, snapshot []entity.Message) {
	if s.memoryStore == nil || rc == nil || rc.sessionID == "" || !s.shouldUseSessionMemory(rc.memoryConfig) {
		return
	}
	ttlSeconds := 24 * 3600
	if rc.memoryConfig != nil && rc.memoryConfig.CrossSession.SessionTTLHours > 0 {
		ttlSeconds = rc.memoryConfig.CrossSession.SessionTTLHours * 3600
	}
	if err := s.memoryStore.Set(context.Background(), sessionNamespace(rc.tenantID), sessionBufferKey(rc.sessionID), snapshot, ttlSeconds); err != nil {
		log.Printf("Failed to persist session buffer for %s: %v", rc.sessionID, err)
	}
}

func sessionNamespace(tenantID string) string {
	if tenantID == "" {
		return sessionNamespacePrefix
	}
	return fmt.Sprintf("%s:%s", sessionNamespacePrefix, tenantID)
}

func sessionBufferKey(sessionID string) string {
	return fmt.Sprintf("%s:%s", sessionBufferKeyPrefix, sessionID)
}

// decrementAndEnqueue reduces pending count and enqueues if ready
func (s *Scheduler) decrementAndEnqueue(rc *runContext, nodeID string) {
	rc.pendingMu.Lock()

	node := rc.plan.GetNode(nodeID)
	maxVisits := s.maxVisitsForNode(rc, node)

	// Skip if already completed, skipped, or running
	if rc.skipped[nodeID] || rc.running[nodeID] {
		rc.pendingMu.Unlock()
		return
	}
	if rc.completed[nodeID] && rc.visitCounts[nodeID] >= maxVisits {
		rc.pendingMu.Unlock()
		return
	}
	if rc.visitCounts[nodeID] >= maxVisits && rc.resumeRetryNode != nodeID {
		rc.pendingMu.Unlock()
		s.setError(
			rc,
			domain.NewValidationError(
				"max_visits",
				fmt.Sprintf("node %s exceeded max_visits=%d", nodeID, maxVisits),
			),
		)
		return
	}

	rc.pending[nodeID]--
	if rc.pending[nodeID] <= 0 {
		// Ready to execute - add work item to WaitGroup and send to channel
		rc.wg.Add(1)
		// Non-blocking send using goroutine to prevent deadlock
		go func() {
			select {
			case rc.workChan <- nodeID:
				// Successfully enqueued, wg.Done() will be called in executeNode
			case <-rc.ctx.Done():
				// Context cancelled, mark work as done since it won't be processed
				rc.wg.Done()
			}
		}()
	}
	rc.pendingMu.Unlock()
}

// markSkipped marks a node and its descendants as skipped
func (s *Scheduler) markSkipped(rc *runContext, nodeID string) {
	rc.pendingMu.Lock()
	if rc.skipped[nodeID] || rc.completed[nodeID] {
		rc.pendingMu.Unlock()
		return
	}
	rc.skipped[nodeID] = true
	rc.pendingMu.Unlock()

	// Create skipped node run record
	node := rc.plan.GetNode(nodeID)
	if node != nil {
		nodeCtx, span, nodeTrace := tracing.StartSpan(
			rc.ctx,
			"scheduler.node",
			fmt.Sprintf("node.%s.skip", node.Type),
			rc.traceparent,
			rc.tracestate,
		)
		defer span.End()
		nodeRun := &entity.NodeRun{
			ID:        fmt.Sprintf("%s-%s", rc.runID, nodeID),
			RunID:     rc.runID,
			NodeID:    nodeID,
			NodeType:  node.Type,
			Status:    string(value.NodeRunStatusSkipped),
			StartedAt: s.clock.Now(),
			TraceID:   nodeTrace.TraceID,
			SpanID:    nodeTrace.SpanID,
		}
		nodeRun.SetEnded(s.clock.Now())
		s.repository.CreateNodeRun(nodeCtx, nodeRun)

		// Emit skipped event
		skippedEvent := rc.newEventFromContext(nodeCtx, port.EventTypeNodeSkipped).
			WithNode(nodeID, node.Type, node.Name)
		if diagnostics := s.buildLoopDiagnostics(rc, nodeID, "skipped", nil); len(diagnostics) > 0 {
			skippedEvent = skippedEvent.WithOutput(map[string]any{"loop": diagnostics})
		}
		s.emitter.EmitAsync(skippedEvent)
	}

	// Recursively skip children that have only this as parent
	for _, edge := range rc.plan.GetOutgoingEdges(nodeID) {
		// Only auto-skip if this is the only incoming edge.
		// Otherwise, treat this skipped node as "logically complete" for dependency tracking.
		if rc.plan.GetIndegree(edge.To) == 1 {
			s.markSkipped(rc, edge.To)
			continue
		}
		s.decrementAndEnqueue(rc, edge.To)
	}
}

// finalizeRun determines and sets the final run status
func (s *Scheduler) finalizeRun(rc *runContext) {
	var finalStatus value.RunStatus
	var output map[string]any
	var errorMsg string

	if rc.err != nil {
		finalStatus = value.RunStatusFailed
		errorMsg = rc.err.Error()
	} else if rc.ctx.Err() != nil {
		// Context was cancelled but no error - likely paused or cancelled
		if rc.pauseIntentPublished {
			return
		}
		// Check current status
		run, _ := s.repository.GetRun(context.Background(), rc.runID)
		if run != nil && run.Status == string(value.RunStatusPaused) {
			return // Already set to paused
		}
		finalStatus = value.RunStatusCanceled
	} else {
		finalStatus = value.RunStatusSucceeded
		output = s.extractFinalOutput(rc)
	}

	// Update run in database
	s.repository.SetRunEnded(rc.intentContext(context.Background()), rc.runID, string(finalStatus), output, errorMsg)

	// Persist session memory snapshot on completion/cancel.
	if rc.messageBuffer != nil && rc.sessionID != "" {
		s.persistSessionBuffer(rc, rc.messageBuffer.Snapshot())
	}

	// Keep the latest checkpoint to enable threaded run continuation.

	// Emit final event
	var event *port.ExecutionEvent
	switch finalStatus {
	case value.RunStatusSucceeded:
		event = rc.newEvent(port.EventTypeRunCompleted).WithOutput(output)
	case value.RunStatusFailed:
		event = rc.newEvent(port.EventTypeRunFailed).WithError(errorMsg)
	case value.RunStatusCanceled:
		event = rc.newEvent(port.EventTypeRunCanceled)
	}
	if event != nil {
		s.emitter.EmitAsync(event)
		s.flushEmitter("run_final")
	}
}

func (s *Scheduler) preloadMemory(rc *runContext) {
	if rc == nil || rc.messageBuffer == nil || rc.memoryConfig == nil {
		return
	}
	if !s.shouldUseSessionMemory(rc.memoryConfig) && !(rc.memoryConfig.Tier3.Enabled && s.memoryRetriever != nil) {
		return
	}

	go func() {
		if s.shouldUseSessionMemory(rc.memoryConfig) && rc.sessionID != "" && s.memoryStore != nil && rc.messageBuffer.Count() == 0 {
			start := time.Now()
			namespace := sessionNamespace(rc.tenantID)
			key := sessionBufferKey(rc.sessionID)
			value, found, err := s.memoryStore.Get(context.Background(), namespace, key)
			if err != nil {
				log.Printf("Failed to load session buffer for %s: %v", rc.sessionID, err)
				metrics.RecordPreloadOperation("session_restore", "error", time.Since(start))
			} else if found {
				messages := decodeMessages(value)
				if len(messages) > 0 {
					rc.messageBuffer.Restore(messages)
					metrics.RecordPreloadOperation("session_restore", "hit", time.Since(start))
				} else {
					metrics.RecordPreloadOperation("session_restore", "miss", time.Since(start))
				}
			} else {
				metrics.RecordPreloadOperation("session_restore", "miss", time.Since(start))
			}
		}

		if rc.memoryConfig.Tier3.Enabled && s.memoryRetriever != nil && rc.currentSummary != nil {
			s.warmupVectorCache(rc)
		}
	}()
}

func (s *Scheduler) warmupVectorCache(rc *runContext) {
	if rc == nil || s.memoryRetriever == nil || rc.memoryConfig == nil || rc.currentSummary == nil {
		return
	}

	req := port.MemoryRetrieveRequest{
		TenantID:       rc.tenantID,
		Query:          rc.currentSummary.Content,
		AgentID:        "",
		RunID:          rc.runID,
		SessionID:      rc.sessionID,
		TopK:           rc.memoryConfig.Tier3.TopK,
		Threshold:      rc.memoryConfig.Tier3.Threshold,
		RecencyWeight:  rc.memoryConfig.Tier3.RecencyWeight,
		EmbeddingModel: rc.memoryConfig.Tier3.EmbeddingModel,
	}

	start := time.Now()
	if _, err := s.memoryRetriever.Retrieve(context.Background(), req); err != nil {
		log.Printf("Vector cache warmup failed for run %s: %v", rc.runID, err)
		metrics.RecordPreloadOperation("vector_warmup", "error", time.Since(start))
		return
	}
	metrics.RecordPreloadOperation("vector_warmup", "success", time.Since(start))
}

// extractFinalOutput collects output from Output node(s)
func (s *Scheduler) extractFinalOutput(rc *runContext) map[string]any {
	output := make(map[string]any)
	for _, node := range rc.plan.Graph.Nodes {
		if node.Type == string(value.NodeTypeOutput) {
			if nodeOutput, ok := rc.state.GetNodeOutput(node.ID); ok {
				output[node.ID] = nodeOutput
			}
		}
	}
	// If only one output node, flatten
	if len(output) == 1 {
		for _, v := range output {
			if m, ok := v.(map[string]any); ok {
				return m
			}
		}
	}
	return output
}

// setError sets the run error (thread-safe, first error wins)
func (s *Scheduler) setError(rc *runContext, err error) {
	rc.errMu.Lock()
	defer rc.errMu.Unlock()
	if rc.err == nil {
		rc.err = err
		rc.cancel() // Cancel all other work
	}
}

// CancelRun cancels an active run
func (s *Scheduler) CancelRun(runID string) error {
	val, ok := s.activeRuns.Load(runID)
	if !ok {
		return fmt.Errorf("run not found or already completed")
	}
	rc := val.(*runContext)
	rc.cancel()

	s.repository.UpdateRunStatus(rc.intentContext(context.Background()), runID, string(value.RunStatusCanceled))
	s.emitter.EmitAsync(rc.newEvent(port.EventTypeRunCanceled))
	s.flushEmitter("run_canceled")

	return nil
}

// ResumeRun resumes a paused run after human gate approval/rejection
func (s *Scheduler) ResumeRun(ctx context.Context, runID, nodeID, inputJSON string, traceContext ...string) error {
	traceparent := ""
	tracestate := ""
	if len(traceContext) > 0 {
		traceparent = traceContext[0]
	}
	if len(traceContext) > 1 {
		tracestate = traceContext[1]
	}
	// Load pause state
	pausedNodeID, stateSnapshot, completedNodes, skippedNodes, graphJSON, tenantID, err := s.repository.LoadPauseState(ctx, runID)
	if err != nil {
		return fmt.Errorf("failed to load pause state: %w", err)
	}

	// Validate node ID matches
	if pausedNodeID != nodeID {
		return fmt.Errorf("node_id mismatch: expected %s, got %s", pausedNodeID, nodeID)
	}

	// Parse human decision input
	var decision map[string]any
	if inputJSON != "" {
		if err := json.Unmarshal([]byte(inputJSON), &decision); err != nil {
			return fmt.Errorf("invalid input JSON: %w", err)
		}
	}
	resumeAttemptID, _ := decision["_forgegraph_resume_attempt_id"].(string)
	delete(decision, "_forgegraph_resume_attempt_id")
	activeAttemptID := strings.TrimSpace(resumeAttemptID)
	if s.pauseIntentActiveMode() && activeAttemptID == "" {
		return fmt.Errorf("resume_attempt_id is required in runtime intent mode")
	}
	resumeIntentCtx := ctx
	if activeAttemptID != "" {
		resumeIntentCtx = port.WithAttemptID(resumeIntentCtx, activeAttemptID)
	}
	llmAccessFromInput := extractLLMAccessFromInput(decision)

	// Check if approved or rejected
	approved, _ := decision["approved"].(bool)
	feedback, _ := decision["feedback"].(string)

	nodeRun, _ := s.repository.GetNodeRun(ctx, runID, nodeID)
	isAgentPause := nodeRun != nil && nodeRun.NodeType == string(value.NodeTypeAgent)

	// Handle rejection - terminate the run
	if !approved {
		errorMsg := "Rejected by user"
		if feedback != "" {
			errorMsg = fmt.Sprintf("Rejected by user: %s", feedback)
		}

		// Update node run to failed
		if nodeRun != nil {
			nodeRun.Status = string(value.NodeRunStatusFailed)
			now := s.clock.Now()
			nodeRun.EndedAt = &now
			nodeRun.ErrorJSON = map[string]any{"message": errorMsg, "rejected": true}
			if err := s.repository.UpdateNodeRun(resumeIntentCtx, nodeRun); err != nil {
				return fmt.Errorf("failed to update rejected node run: %w", err)
			}
		}

		// Mark run as failed
		if err := s.repository.SetRunEnded(resumeIntentCtx, runID, string(value.RunStatusFailed), nil, errorMsg); err != nil {
			return fmt.Errorf("failed to mark rejected run failed: %w", err)
		}
		if !s.pauseIntentActiveMode() {
			if err := s.repository.ClearPauseState(ctx, runID); err != nil {
				return fmt.Errorf("failed to clear rejected pause state: %w", err)
			}
		}
		s.emitter.EmitAsync(port.NewEvent(port.EventTypeRunFailed, runID).WithTenantID(tenantID).WithError(errorMsg))
		s.flushEmitter("run_failed")
		return nil
	}

	// Parse graph JSON
	var graph entity.Graph
	if err := json.Unmarshal([]byte(graphJSON), &graph); err != nil {
		return fmt.Errorf("invalid stored graph JSON: %w", err)
	}
	hydrateGraphIdentifiers(graphJSON, &graph)
	engineContractVersion := ""
	if graph.Metadata != nil {
		if rawVersion, ok := graph.Metadata["engine_contract_version"].(string); ok {
			engineContractVersion = strings.TrimSpace(rawVersion)
		}
	}
	if engineContractVersion != "" && engineContractVersion != "2" {
		return fmt.Errorf("unsupported engine_contract_version: %s", engineContractVersion)
	}
	llmAccess := mergeLLMAccess(extractLLMAccessFromMetadata(graph.Metadata), llmAccessFromInput)

	stateSchemaRaw, schemaMode := extractStateSchemaMetadata(graph.Metadata)
	stateSchema, err := service.CompileSchema(stateSchemaRaw)
	if err != nil {
		return fmt.Errorf("invalid state_schema: %w", err)
	}

	// Build execution plan
	planner := service.NewExecutionPlanner()
	plan := planner.Plan(&graph)
	allowCycles, defaultMaxVisits := extractLoopMetadata(graph.Metadata)
	backEdges := s.detectBackEdges(plan, allowCycles)
	runtimeLimits := extractRuntimeLimits(graph.Metadata)

	// Restore state from snapshot
	state := entity.NewStateFromSnapshot(stateSnapshot)

	// Inject human decision into state
	humanDecision := map[string]any{
		"approved":   true,
		"fields":     decision["fields"],
		"feedback":   feedback,
		"decided_at": s.clock.Now().Format(time.RFC3339),
	}
	if isAgentPause {
		state.Set("node."+nodeID+".approval_decision", humanDecision)
		if nodeRun != nil {
			nodeRun.Status = string(value.NodeRunStatusRunning)
			nodeRun.EndedAt = nil
			nodeRun.OutputJSON = nil
			nodeRun.ErrorJSON = nil
			if err := s.repository.UpdateNodeRun(resumeIntentCtx, nodeRun); err != nil {
				return fmt.Errorf("failed to update resumed agent node run: %w", err)
			}
		}
	} else {
		state.SetNodeOutput(nodeID, humanDecision)

		// Update human gate node run to succeeded
		if nodeRun != nil {
			nodeRun.Status = string(value.NodeRunStatusSucceeded)
			now := s.clock.Now()
			nodeRun.EndedAt = &now
			nodeRun.OutputJSON = map[string]any{"output": humanDecision}
			if err := s.repository.UpdateNodeRun(resumeIntentCtx, nodeRun); err != nil {
				return fmt.Errorf("failed to update resumed human gate node run: %w", err)
			}
		}
	}

	// Create a detached run context for resumed execution.
	// Resume RPC context is request-scoped and must not control background workers.
	runCtx, runSpan, traceCtx := tracing.StartSpan(
		context.Background(),
		"forgegraph-engine",
		"forgegraph.run.resume",
		traceparent,
		tracestate,
	)
	runCtx, cancel := context.WithCancel(runCtx)
	resumeMemoryConfig := defaultMemoryConfig()
	var resumeBuffer *entity.MessageBuffer
	if resumeMemoryConfig.Tier1.Enabled {
		resumeBuffer = entity.NewMessageBuffer(resumeMemoryConfig.Tier1.BufferSize)
	}
	rc := &runContext{
		runID:            runID,
		ctx:              runCtx,
		cancel:           cancel,
		clock:            s.clock,
		runSpan:          runSpan,
		startedAt:        s.clock.Now(),
		plan:             plan,
		allowCycles:      allowCycles,
		defaultMaxVisits: defaultMaxVisits,
		backEdges:        backEdges,
		state:            state,
		graphJSON:        graphJSON,
		tenantID:         tenantID,
		attemptID:        activeAttemptID,
		traceID:          traceCtx.TraceID,
		traceparent:      traceCtx.Traceparent,
		tracestate:       traceCtx.Tracestate,
		messageBuffer:    resumeBuffer,
		memoryConfig:     resumeMemoryConfig,
		stateSchema:      stateSchema,
		schemaMode:       schemaMode,
		runtimeLimits:    runtimeLimits,
		pending:          s.initializePending(plan, backEdges),
		completed:        make(map[string]bool),
		skipped:          make(map[string]bool),
		running:          make(map[string]bool),
		visitCounts:      make(map[string]int),
		workChan:         make(chan string, len(plan.NodeMap)),
	}
	rc.memoryCtx = &port.RunContext{
		TenantID:          rc.tenantID,
		GraphID:           graph.ID,
		RunID:             rc.runID,
		SessionID:         rc.sessionID,
		TraceID:           rc.traceID,
		Traceparent:       rc.traceparent,
		Tracestate:        rc.tracestate,
		MemoryBuffer:      rc.messageBuffer,
		MemoryConfig:      rc.memoryConfig,
		CurrentSummary:    rc.currentSummary,
		TrackMessage:      rc.trackMessages,
		TrackLLMCall:      rc.trackLLMCall,
		TrackToolCall:     rc.trackToolCall,
		MemoryRetriever:   s.memoryRetriever,
		ObservationClient: s.observationClient,
		Policy:            entity.PolicyFromMetadata(graph.Metadata),
		LLMAccess:         llmAccess,
	}
	rc.ctx = port.WithRunContext(rc.ctx, rc.memoryCtx)
	if rc.tenantID != "" {
		rc.ctx = port.WithTenantID(rc.ctx, rc.tenantID)
	}
	rc.ctx = port.WithAttemptID(rc.ctx, rc.attemptID)

	if s.isCheckpointingEnabled() {
		if _, stepIndex, _, _, _, _, err := s.repository.LoadLatestCheckpoint(ctx, runID); err == nil {
			rc.checkpointSeq = int64(stepIndex)
		}
	}

	// Mark previously completed nodes
	for _, completedID := range completedNodes {
		rc.completed[completedID] = true
		if rc.visitCounts[completedID] < 1 {
			rc.visitCounts[completedID] = 1
		}
	}
	// Mark skipped nodes from paused state
	for _, skippedID := range skippedNodes {
		rc.skipped[skippedID] = true
	}
	// Human gate resumes continue downstream; paused agent resumes re-enter the same node.
	if !isAgentPause {
		rc.completed[nodeID] = true
		if rc.visitCounts[nodeID] < 1 {
			rc.visitCounts[nodeID] = 1
		}
	}

	// Rebuild pending counts based on completed/skipped nodes
	s.applyCheckpointToPending(rc)
	if isAgentPause {
		rc.initialNodes = []string{nodeID}
	} else {
		rc.initialNodes = s.computeReadyNodes(rc)
	}

	// Store active run
	s.activeRuns.Store(runID, rc)

	// Clear pause state and update run status
	if s.pauseIntentActiveMode() {
		if err := s.publishAckRunResumedIntent(
			resumeIntentCtx,
			rc,
			nodeID,
			resumeAttemptID,
			humanDecision,
		); err != nil {
			return fmt.Errorf("failed to publish ack_run_resumed intent: %w", err)
		}
	} else {
		if err := s.repository.ClearPauseState(ctx, runID); err != nil {
			return fmt.Errorf("failed to clear pause state: %w", err)
		}
		if err := s.repository.UpdateRunStatus(rc.intentContext(ctx), runID, string(value.RunStatusRunning)); err != nil {
			return fmt.Errorf("failed to mark resumed run running: %w", err)
		}
	}

	// Emit run resumed event
	resumedEvent := rc.newEvent(port.EventTypeRunResumed).WithAttemptID(rc.attemptID)
	if strings.TrimSpace(resumeAttemptID) != "" {
		resumedEvent = resumedEvent.WithOutput(map[string]any{"resume_attempt_id": resumeAttemptID})
	}
	s.emitter.EmitAsync(resumedEvent)

	// Start execution in background from all ready nodes
	go s.executeResumedRun(rc, rc.initialNodes)

	return nil
}

// executeResumedRun continues execution from a resumed run
func (s *Scheduler) executeResumedRun(rc *runContext, startNodes []string) {
	defer func() {
		// Cleanup
		s.activeRuns.Delete(rc.runID)
		if rc.runSpan != nil {
			rc.runSpan.End()
		}
		rc.cancel()
		close(rc.workChan)
	}()

	// Start workers
	for i := 0; i < s.config.MaxWorkers; i++ {
		go s.worker(rc)
	}

	// Enqueue ready nodes captured at resume time
	for _, nodeID := range startNodes {
		rc.wg.Add(1)
		rc.workChan <- nodeID
	}

	// Wait for all work to complete
	rc.wg.Wait()

	// Determine final status
	s.finalizeRun(rc)
}

// GetRunStatus returns the current status of an active run
func (s *Scheduler) GetRunStatus(runID string) (status string, currentNodeID string, err error) {
	val, ok := s.activeRuns.Load(runID)
	if !ok {
		// Not active - check database
		run, dbErr := s.repository.GetRun(context.Background(), runID)
		if dbErr != nil {
			return "", "", dbErr
		}
		if run == nil {
			return "", "", domain.ErrRunNotFound
		}
		return run.Status, "", nil
	}

	rc := val.(*runContext)
	rc.currentNodeMu.RLock()
	currentNodeID = rc.currentNodeID
	rc.currentNodeMu.RUnlock()

	return string(value.RunStatusRunning), currentNodeID, nil
}

// IsRunActive returns true if the run is currently being executed
func (s *Scheduler) IsRunActive(runID string) bool {
	_, ok := s.activeRuns.Load(runID)
	return ok
}

// injectNodeMetadata adds runtime metadata to node config for branch and merge nodes.
// This allows executors to access graph structure information needed for their logic.
func (s *Scheduler) injectNodeMetadata(rc *runContext, node *entity.Node) {
	if node.Config == nil {
		node.Config = make(map[string]any)
	}

	switch node.Type {
	case string(value.NodeTypeBranch):
		// Inject outgoing edges for branch routing
		node.Config["_edges"] = rc.plan.SerializeEdgesForConfig(node.ID)

	case string(value.NodeTypeMerge):
		// Inject predecessor node IDs for merge collection
		node.Config["_input_nodes"] = rc.plan.GetPredecessors(node.ID)
	}
}

func (s *Scheduler) evaluateEdgeConditions(rc *runContext, edges []*entity.Edge) ([]string, []string, bool, error) {
	hasCondition := false
	for _, edge := range edges {
		if strings.TrimSpace(edge.Condition) != "" {
			hasCondition = true
			break
		}
	}
	if !hasCondition {
		return nil, nil, false, nil
	}

	var next []string
	var skipped []string
	var defaultEdges []string

	for _, edge := range edges {
		target := edge.To
		condition := strings.TrimSpace(edge.Condition)
		if condition == "" {
			defaultEdges = append(defaultEdges, target)
			continue
		}

		ok, err := s.conditions.EvaluateBool(condition, rc.state)
		if err != nil {
			return nil, nil, true, err
		}
		if ok {
			next = append(next, target)
		} else {
			skipped = append(skipped, target)
		}
	}

	if len(next) == 0 {
		next = defaultEdges
	} else if len(defaultEdges) > 0 {
		skipped = append(skipped, defaultEdges...)
	}

	return next, skipped, true, nil
}

func (s *Scheduler) validateStateSchema(ctx context.Context, rc *runContext, node *entity.Node, nodeRun *entity.NodeRun, durationMs int64) bool {
	if rc.stateSchema == nil {
		return true
	}

	issues, err := rc.stateSchema.Validate(rc.state.SnapshotNested())
	if err != nil {
		s.setError(rc, domain.NewValidationError("state_schema", err.Error()))
		return false
	}
	if len(issues) == 0 {
		return true
	}

	payload := map[string]any{
		"errors": issues,
		"mode":   rc.schemaMode,
	}
	s.emitter.EmitAsync(
		rc.newEvent(port.EventTypeRunSchemaValidation).
			WithNode(node.ID, node.Type, node.Name).
			WithOutput(payload),
	)

	if strings.ToLower(rc.schemaMode) == "strict" {
		errMsg := fmt.Sprintf("state schema validation failed: %v", issues[0]["message"])
		nodeRun.Status = string(value.NodeRunStatusFailed)
		nodeRun.SetEnded(s.clock.Now())
		nodeRun.ErrorJSON = map[string]any{
			"error":  errMsg,
			"issues": issues,
		}
		s.repository.UpdateNodeRun(ctx, nodeRun)

		s.emitter.EmitAsync(
			rc.newEventFromContext(ctx, port.EventTypeNodeFailed).
				WithNode(node.ID, node.Type, node.Name).
				WithError(errMsg).
				WithDuration(durationMs),
		)
		s.setError(rc, domain.NewNodeError(node.ID, node.Type, errors.New(errMsg)))
		return false
	}

	return true
}

func extractStateSchemaMetadata(metadata map[string]any) (map[string]any, string) {
	mode := "warn"
	if metadata == nil {
		return nil, mode
	}

	if rawMode, ok := metadata["schema_mode"].(string); ok && strings.ToLower(rawMode) == "strict" {
		mode = "strict"
	} else if rawMode, ok := metadata["validation_mode"].(string); ok && strings.ToLower(rawMode) == "strict" {
		mode = "strict"
	}

	if rawSchema, ok := metadata["state_schema"].(map[string]any); ok && rawSchema != nil {
		return rawSchema, mode
	}
	return nil, mode
}

func extractRuntimeLimits(metadata map[string]any) runtimeLimits {
	limits := runtimeLimits{}
	if metadata == nil {
		return limits
	}
	raw, ok := metadata["runtime_limits"].(map[string]any)
	if !ok {
		return limits
	}
	limits.MaxRunDurationMs = int64(getRuntimeLimitInt(raw["max_run_duration_ms"]))
	limits.MaxToolCalls = int64(getRuntimeLimitInt(raw["max_tool_calls_total"]))
	limits.MaxLLMCalls = int64(getRuntimeLimitInt(raw["max_llm_calls_total"]))
	return limits
}

func extractLLMAccessFromMetadata(metadata map[string]any) port.LLMAccessConfig {
	if metadata == nil {
		return port.LLMAccessConfig{}.Normalized()
	}
	raw, ok := metadata[llmAccessMetadataKey].(map[string]any)
	if !ok || raw == nil {
		return port.LLMAccessConfig{}.Normalized()
	}
	return port.LLMAccessConfig{
		Mode:         stringMapValue(raw, "llm_mode"),
		Provider:     stringMapValue(raw, "provider"),
		CredentialID: stringMapValue(raw, "credential_id"),
	}.Normalized()
}

func extractLLMAccessFromInput(input map[string]any) port.LLMAccessConfig {
	if input == nil {
		return port.LLMAccessConfig{}
	}
	raw := input[llmAccessEngineInputKey]
	delete(input, llmAccessEngineInputKey)
	payload, ok := raw.(map[string]any)
	if !ok || payload == nil {
		return port.LLMAccessConfig{}
	}
	return port.LLMAccessConfig{
		Mode:         stringMapValue(payload, "llm_mode"),
		Provider:     stringMapValue(payload, "provider"),
		CredentialID: stringMapValue(payload, "credential_id"),
		APIKey:       stringMapValue(payload, "api_key"),
	}.Normalized()
}

func mergeLLMAccess(base port.LLMAccessConfig, override port.LLMAccessConfig) port.LLMAccessConfig {
	base = base.Normalized()
	if strings.TrimSpace(override.Mode) == "" &&
		strings.TrimSpace(override.Provider) == "" &&
		strings.TrimSpace(override.CredentialID) == "" &&
		strings.TrimSpace(override.APIKey) == "" {
		return base
	}
	override = override.Normalized()
	if override.Provider == "" {
		override.Provider = base.Provider
	}
	if override.APIKey == "" && override.Mode == port.LLMModeBYOK {
		override.APIKey = base.APIKey
	}
	if override.CredentialID == "" && override.Mode == port.LLMModeBYOK {
		override.CredentialID = base.CredentialID
	}
	return override.Normalized()
}

func stringMapValue(payload map[string]any, key string) string {
	if payload == nil {
		return ""
	}
	value, ok := payload[key].(string)
	if !ok {
		return ""
	}
	return strings.TrimSpace(value)
}

func getRuntimeLimitInt(value any) int {
	switch typed := value.(type) {
	case int:
		return typed
	case int32:
		return int(typed)
	case int64:
		return int(typed)
	case float32:
		return int(typed)
	case float64:
		return int(typed)
	default:
		return 0
	}
}

func hydrateGraphIdentifiers(graphJSON string, graph *entity.Graph) {
	if graph == nil || graphJSON == "" {
		return
	}

	var raw struct {
		GraphID   string `json:"graph_id"`
		ID        string `json:"id"`
		VersionID string `json:"version_id"`
	}
	if err := json.Unmarshal([]byte(graphJSON), &raw); err != nil {
		return
	}
	if graph.ID == "" {
		graph.ID = strings.TrimSpace(raw.GraphID)
	}
	if graph.ID == "" {
		graph.ID = strings.TrimSpace(raw.ID)
	}
	if graph.VersionID == "" {
		graph.VersionID = strings.TrimSpace(raw.VersionID)
	}
}

func (s *Scheduler) resolveRetryPolicy(node *entity.Node) *entity.RetryPolicy {
	base := entity.DefaultRetryPolicy()
	if node != nil && node.RetryPolicy != nil {
		base = &entity.RetryPolicy{
			MaxAttempts:     node.RetryPolicy.MaxAttempts,
			BackoffMs:       node.RetryPolicy.BackoffMs,
			BackoffStrategy: node.RetryPolicy.BackoffStrategy,
		}
	}

	onError := parseOnErrorPolicy(node)
	if onError.Strategy == onErrorStrategyRetry {
		if onError.HasMaxAttempts && onError.MaxAttempts > 0 {
			base.MaxAttempts = onError.MaxAttempts
		}
		if onError.HasBackoffMs && onError.BackoffMs >= 0 {
			base.BackoffMs = onError.BackoffMs
		}
		if onError.HasBackoffStrategy {
			base.BackoffStrategy = onError.BackoffStrategy
		}
	}

	if base.MaxAttempts < 1 {
		base.MaxAttempts = 1
	}
	if base.BackoffMs < 0 {
		base.BackoffMs = 0
	}
	if base.BackoffStrategy != "fixed" && base.BackoffStrategy != "exponential" {
		base.BackoffStrategy = "exponential"
	}
	return base
}

func toolNodeAllowsSchedulerRetry(node *entity.Node) bool {
	if node == nil {
		return false
	}
	sideEffectClass := strings.ToLower(strings.TrimSpace(node.GetConfigString("side_effect_class")))
	switch sideEffectClass {
	case "pure", "idempotent":
	default:
		log.Printf("tool_retry_blocked_unsafe: node_id=%s side_effect_class=%s reason=unsafe_or_missing_contract", node.ID, sideEffectClass)
		return false
	}
	if strings.TrimSpace(node.GetConfigString("tool_execution_id")) == "" ||
		strings.TrimSpace(node.GetConfigString("idempotency_key")) == "" {
		log.Printf("tool_retry_blocked_unsafe: node_id=%s side_effect_class=%s reason=missing_execution_identity", node.ID, sideEffectClass)
		return false
	}
	return true
}

func parseOnErrorPolicy(node *entity.Node) onErrorPolicy {
	policy := onErrorPolicy{Strategy: onErrorStrategyFail}
	if node == nil || node.Config == nil {
		return policy
	}

	rawPolicy, ok := node.Config["on_error"]
	if !ok {
		rawPolicy = node.Config["onError"]
	}
	config, ok := rawPolicy.(map[string]any)
	if !ok || config == nil {
		return policy
	}

	if strategy, ok := firstStringValue(config, "strategy", "action", "mode"); ok {
		switch strings.ToLower(strings.TrimSpace(strategy)) {
		case onErrorStrategyRetry:
			policy.Strategy = onErrorStrategyRetry
		case onErrorStrategySkip:
			policy.Strategy = onErrorStrategySkip
		case onErrorStrategyFallback:
			policy.Strategy = onErrorStrategyFallback
		default:
			policy.Strategy = onErrorStrategyFail
		}
	}

	if maxAttempts, ok := firstIntValue(config, "max_attempts", "max_retries"); ok {
		policy.MaxAttempts = maxAttempts
		policy.HasMaxAttempts = true
	}
	if backoffMs, ok := firstIntValue(config, "backoff_ms", "retry_backoff_ms"); ok {
		policy.BackoffMs = backoffMs
		policy.HasBackoffMs = true
	}
	if backoffStrategy, ok := firstStringValue(
		config,
		"backoff_strategy",
		"retry_backoff_strategy",
	); ok {
		switch strings.ToLower(strings.TrimSpace(backoffStrategy)) {
		case "fixed", "exponential":
			policy.BackoffStrategy = strings.ToLower(strings.TrimSpace(backoffStrategy))
			policy.HasBackoffStrategy = true
		}
	}

	nextNodes := make([]string, 0)
	if values, ok := firstStringSliceValue(
		config,
		"next_nodes",
		"fallback_nodes",
		"nextNodes",
		"fallbackNodes",
	); ok {
		nextNodes = append(nextNodes, values...)
	} else if single, ok := firstStringValue(
		config,
		"next_node",
		"fallback_node",
		"nextNode",
		"fallbackNode",
	); ok && strings.TrimSpace(single) != "" {
		nextNodes = append(nextNodes, strings.TrimSpace(single))
	}
	if len(nextNodes) > 0 {
		policy.NextNodes = nextNodes
	}

	return policy
}

func (s *Scheduler) resolveOnErrorRouting(
	rc *runContext,
	node *entity.Node,
	onError onErrorPolicy,
) ([]string, []string, bool, error) {
	if node == nil {
		return nil, nil, false, fmt.Errorf("node is required")
	}

	if onError.Strategy != onErrorStrategySkip && onError.Strategy != onErrorStrategyFallback {
		return nil, nil, false, nil
	}

	edges := rc.plan.GetOutgoingEdges(node.ID)
	if len(edges) == 0 {
		if onError.Strategy == onErrorStrategyFallback && len(onError.NextNodes) > 0 {
			return nil, nil, false, fmt.Errorf("on_error fallback targets require outgoing edges")
		}
		return nil, nil, true, nil
	}

	allowed := make(map[string]bool, len(edges))
	defaultNext := make([]string, 0, len(edges))
	for _, edge := range edges {
		allowed[edge.To] = true
		defaultNext = append(defaultNext, edge.To)
	}

	nextNodes := make([]string, 0, len(defaultNext))
	if len(onError.NextNodes) > 0 {
		nextNodes = append(nextNodes, onError.NextNodes...)
	} else if onError.Strategy == onErrorStrategySkip {
		nextNodes = append(nextNodes, defaultNext...)
	} else {
		return nil, nil, false, fmt.Errorf("on_error fallback requires next_nodes configuration")
	}

	validNext := make([]string, 0, len(nextNodes))
	seen := make(map[string]bool, len(nextNodes))
	for _, candidate := range nextNodes {
		target := strings.TrimSpace(candidate)
		if target == "" {
			continue
		}
		if !allowed[target] {
			return nil, nil, false, fmt.Errorf("on_error target %s is not an outgoing edge from node %s", target, node.ID)
		}
		if seen[target] {
			continue
		}
		validNext = append(validNext, target)
		seen[target] = true
	}

	if onError.Strategy == onErrorStrategyFallback && len(validNext) == 0 {
		return nil, nil, false, fmt.Errorf("on_error fallback resolved no valid next nodes")
	}

	skipped := make([]string, 0)
	if !rc.allowCycles && len(validNext) > 0 {
		selected := make(map[string]bool, len(validNext))
		for _, next := range validNext {
			selected[next] = true
		}
		for _, edge := range edges {
			if !selected[edge.To] {
				skipped = append(skipped, edge.To)
			}
		}
	}

	return validNext, skipped, true, nil
}

func (s *Scheduler) buildNodeErrorPayload(
	err error,
	attempt int,
	retryPolicy *entity.RetryPolicy,
	onError onErrorPolicy,
	nextNodes []string,
	routeErr error,
) map[string]any {
	payload := map[string]any{
		"message":         err.Error(),
		"type":            classifyNodeError(err),
		"retryable":       domain.IsRetryable(err),
		"attempt":         attempt,
		"failed_at":       s.clock.Now().UTC().Format(time.RFC3339Nano),
		"on_error_action": onError.Strategy,
	}

	if retryPolicy != nil {
		payload["max_attempts"] = retryPolicy.MaxAttempts
		payload["backoff_ms"] = retryPolicy.BackoffMs
		payload["backoff_strategy"] = retryPolicy.BackoffStrategy
	}
	if retryCode := domain.RetryCodeFromError(err); retryCode != "" {
		payload["retry_code"] = retryCode
	}
	if retryAfterMs := domain.RetryAfterMsFromError(err); retryAfterMs > 0 {
		payload["retry_after_ms"] = retryAfterMs
	}
	if retryDetails := domain.RetryDetailsFromError(err); len(retryDetails) > 0 {
		payload["retry_details"] = retryDetails
	}
	if len(nextNodes) > 0 {
		payload["next_nodes"] = append([]string(nil), nextNodes...)
	}
	if routeErr != nil {
		payload["on_error_routing_error"] = routeErr.Error()
	}
	return payload
}

func classifyNodeError(err error) string {
	switch {
	case err == nil:
		return "unknown"
	case errors.Is(err, context.DeadlineExceeded):
		return "timeout"
	}

	var validationErr *domain.ValidationError
	if errors.As(err, &validationErr) {
		return "validation_error"
	}
	var nodeErr *domain.NodeError
	if errors.As(err, &nodeErr) {
		return "node_error"
	}
	if domain.IsRetryable(err) {
		if retryCode := domain.RetryCodeFromError(err); retryCode == "rate_limited" {
			return "rate_limit"
		}
		return "retryable_error"
	}
	return "runtime_error"
}

func firstStringValue(config map[string]any, keys ...string) (string, bool) {
	for _, key := range keys {
		raw, ok := config[key]
		if !ok {
			continue
		}
		if value, ok := raw.(string); ok {
			value = strings.TrimSpace(value)
			if value != "" {
				return value, true
			}
		}
	}
	return "", false
}

func firstIntValue(config map[string]any, keys ...string) (int, bool) {
	for _, key := range keys {
		raw, ok := config[key]
		if !ok {
			continue
		}
		return coerceInt(raw), true
	}
	return 0, false
}

func firstStringSliceValue(config map[string]any, keys ...string) ([]string, bool) {
	for _, key := range keys {
		raw, ok := config[key]
		if !ok {
			continue
		}

		switch typed := raw.(type) {
		case []string:
			values := make([]string, 0, len(typed))
			for _, value := range typed {
				value = strings.TrimSpace(value)
				if value != "" {
					values = append(values, value)
				}
			}
			return values, true
		case []any:
			values := make([]string, 0, len(typed))
			for _, item := range typed {
				str, ok := item.(string)
				if !ok {
					continue
				}
				str = strings.TrimSpace(str)
				if str != "" {
					values = append(values, str)
				}
			}
			return values, true
		}
	}
	return nil, false
}

func extractLoopMetadata(metadata map[string]any) (bool, int) {
	if metadata == nil {
		return false, 1
	}

	allowCycles, ok := coerceBool(metadata["allow_cycles"])
	if !ok || !allowCycles {
		return false, 1
	}

	defaultMaxVisits := 25
	if value := coerceInt(metadata["default_max_visits"]); value > 0 {
		defaultMaxVisits = value
	} else if value := coerceInt(metadata["max_node_visits"]); value > 0 {
		defaultMaxVisits = value
	}

	return true, defaultMaxVisits
}
