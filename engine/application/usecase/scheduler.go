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
)

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
	config          SchedulerConfig
	registry        port.ExecutorRegistry
	repository      port.RunRepository
	emitter         port.EventEmitter
	conditions      *service.ConditionEvaluator
	summarizer      *SummarizationWorker
	memoryRetriever port.MemoryRetriever
	memoryStore     port.MemoryStore

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
		config:      config,
		registry:    registry,
		repository:  repository,
		emitter:     emitter,
		conditions:  service.NewConditionEvaluator(),
		memoryStore: memoryStore,
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

// runContext holds runtime state for a single run
type runContext struct {
	runID                string
	ctx                  context.Context
	cancel               context.CancelFunc
	plan                 *service.ExecutionPlan
	state                *entity.State
	callbackURL          string
	graphJSON            string // Original graph JSON for pause/resume
	initialNodes         []string
	tenantID             string
	sessionID            string
	messageBuffer        *entity.MessageBuffer
	memoryConfig         *entity.MemoryConfig
	currentSummary       *entity.Summary
	memoryCtx            *port.RunContext
	summaryMu            sync.Mutex
	messagesSinceSummary int
	cooldownRemaining    int
	summaryInFlight      bool

	// Synchronization
	pendingMu sync.Mutex
	pending   map[string]int  // nodeID -> remaining dependencies
	completed map[string]bool // nodeID -> completed successfully
	skipped   map[string]bool // nodeID -> skipped (branch not taken)
	running   map[string]bool // nodeID -> currently running

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
	lastCheckpointAt time.Time

	stateSchema *service.SchemaValidator
	schemaMode  string
}

func (rc *runContext) newEvent(eventType port.EventType) *port.ExecutionEvent {
	return port.NewEvent(eventType, rc.runID).WithTenantID(rc.tenantID)
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

// StartRun begins executing a workflow
func (s *Scheduler) StartRun(ctx context.Context, runID string, graphJSON string, inputJSON string, callbackURL string, memoryConfigJSON string, tenantID string, sessionID string) error {
	type checkpointData struct {
		nodeID         string
		stepIndex      int
		stateSnapshot  map[string]any
		completedNodes []string
		skippedNodes   []string
		graphJSON      string
		messageBuffer  []entity.Message
		memoryConfig   *entity.MemoryConfig
		currentSummary *entity.Summary
	}

	var checkpoint *checkpointData
	if s.isCheckpointingEnabled() {
		nodeID, stepIndex, snapshot, completedNodes, skippedNodes, checkpointGraphJSON, err := s.repository.LoadLatestCheckpoint(ctx, runID)
		if err == nil {
			if checkpointGraphJSON != "" {
				graphJSON = checkpointGraphJSON
			}
			stateSnapshot, bufferSnapshot, memoryConfig, summary, completed, skipped := parseCheckpointPayload(snapshot, completedNodes, skippedNodes)
			checkpoint = &checkpointData{
				nodeID:         nodeID,
				stepIndex:      stepIndex,
				stateSnapshot:  stateSnapshot,
				completedNodes: completed,
				skippedNodes:   skipped,
				graphJSON:      checkpointGraphJSON,
				messageBuffer:  bufferSnapshot,
				memoryConfig:   memoryConfig,
				currentSummary: summary,
			}
		} else if !errors.Is(err, domain.ErrCheckpointNotFound) && !errors.Is(err, domain.ErrRunNotFound) {
			return fmt.Errorf("failed to load checkpoint: %w", err)
		}
	}

	// Parse graph JSON
	var graph entity.Graph
	if err := json.Unmarshal([]byte(graphJSON), &graph); err != nil {
		return fmt.Errorf("invalid graph JSON: %w", err)
	}

	// Parse input JSON when starting fresh
	var input map[string]any
	if checkpoint == nil && inputJSON != "" {
		if err := json.Unmarshal([]byte(inputJSON), &input); err != nil {
			return fmt.Errorf("invalid input JSON: %w", err)
		}
	}

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

	// Create run context
	runCtx, cancel := context.WithCancel(ctx)
	rc := &runContext{
		runID:         runID,
		ctx:           runCtx,
		cancel:        cancel,
		plan:          plan,
		state:         state,
		callbackURL:   callbackURL,
		graphJSON:     graphJSON,
		tenantID:      tenantID,
		sessionID:     sessionID,
		messageBuffer: messageBuffer,
		memoryConfig:  parsedMemoryConfig,
		currentSummary: func() *entity.Summary {
			if checkpoint != nil {
				return checkpoint.currentSummary
			}
			return nil
		}(),
		stateSchema: stateSchema,
		schemaMode:  schemaMode,
		pending:     plan.CloneIndegree(),
		completed:   make(map[string]bool),
		skipped:     make(map[string]bool),
		running:     make(map[string]bool),
		workChan:    make(chan string, len(plan.NodeMap)),
	}
	rc.memoryCtx = &port.RunContext{
		MemoryBuffer:    rc.messageBuffer,
		MemoryConfig:    rc.memoryConfig,
		CurrentSummary:  rc.currentSummary,
		TrackMessage:    rc.trackMessages,
		MemoryRetriever: s.memoryRetriever,
		Policy:          entity.PolicyFromMetadata(graph.Metadata),
	}
	rc.ctx = port.WithRunContext(rc.ctx, rc.memoryCtx)
	rc.ctx = port.WithTenantID(rc.ctx, rc.tenantID)

	if checkpoint != nil {
		rc.checkpointSeq = int64(checkpoint.stepIndex)
		for _, completedID := range checkpoint.completedNodes {
			rc.completed[completedID] = true
		}
		for _, skippedID := range checkpoint.skippedNodes {
			rc.skipped[skippedID] = true
		}
		s.applyCheckpointToPending(rc)
		rc.initialNodes = s.computeReadyNodes(rc)
	}

	// Store active run
	s.activeRuns.Store(runID, rc)

	s.preloadMemory(rc)

	// Update run status to running
	if err := s.repository.UpdateRunStatus(ctx, runID, string(value.RunStatusRunning)); err != nil {
		log.Printf("Failed to update run status: %v", err)
	}

	// Emit run started/resumed event
	if checkpoint != nil {
		s.emitter.EmitAsync(rc.newEvent(port.EventTypeRunResumed))
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

	// Mark as running
	rc.pendingMu.Lock()
	if rc.completed[nodeID] || rc.skipped[nodeID] {
		rc.pendingMu.Unlock()
		return
	}
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

	// Create node run record
	nodeRun := &entity.NodeRun{
		ID:        fmt.Sprintf("%s-%s", rc.runID, nodeID),
		RunID:     rc.runID,
		NodeID:    nodeID,
		NodeType:  node.Type,
		Status:    string(value.NodeRunStatusRunning),
		Attempt:   1,
		StartedAt: time.Now(),
		InputJSON: rc.state.Snapshot(),
	}
	if err := s.repository.CreateNodeRun(rc.ctx, nodeRun); err != nil {
		log.Printf("Failed to create node run: %v", err)
	}

	// Emit node started
	s.emitter.EmitAsync(
		rc.newEvent(port.EventTypeNodeStarted).
			WithNode(nodeID, node.Type, node.Name).
			WithAttempt(1),
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
			if cachedOutput, found, err := s.repository.GetCachedNodeResult(rc.ctx, cacheKey); err != nil {
				log.Printf("Failed to read cache for node %s: %v", nodeID, err)
			} else if found {
				result := &port.NodeExecutionResult{Output: cachedOutput}
				s.handleNodeSuccess(rc, node, nodeRun, result, 0)
				return
			}
		}
	}

	// Execute with timeout and retries
	startTime := time.Now()
	result, err := s.executeWithRetries(rc, node, executor, nodeRun)
	duration := time.Since(startTime).Milliseconds()

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

		// Node failed
		nodeRun.Status = string(value.NodeRunStatusFailed)
		nodeRun.SetEnded(time.Now())
		nodeRun.ErrorJSON = map[string]any{"error": err.Error()}
		s.repository.UpdateNodeRun(rc.ctx, nodeRun)

		s.emitter.EmitAsync(
			rc.newEvent(port.EventTypeNodeFailed).
				WithNode(nodeID, node.Type, node.Name).
				WithError(err.Error()).
				WithDuration(duration),
		)
		s.setError(rc, domain.NewNodeError(nodeID, node.Type, err))
		return
	}

	// Handle human gate pause
	if result.Pause {
		// Set node to "waiting" status - do NOT set ended_at since the node is still pending human input
		nodeRun.Status = string(value.NodeRunStatusWaiting)
		if result.Output != nil {
			nodeRun.OutputJSON = map[string]any{"pause_payload": result.Output}
		}
		s.repository.UpdateNodeRun(rc.ctx, nodeRun)

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
			context.Background(),
			rc.runID,
			nodeID,
			stateSnapshot,
			completedNodes,
			skippedNodes,
			rc.graphJSON,
			rc.tenantID,
		)
		s.repository.UpdateRunStatus(context.Background(), rc.runID, string(value.RunStatusPaused))

		// Emit pause event with the pause payload
		pauseEvent := rc.newEvent(port.EventTypeRunPaused).
			WithNode(nodeID, node.Type, node.Name)
		if result.Output != nil {
			pauseEvent = pauseEvent.WithOutput(map[string]any{"pause_payload": result.Output})
		}
		s.emitter.EmitAsync(pauseEvent)
		s.flushEmitter("run_paused")

		rc.cancel() // Stop further processing
		return
	}

	s.handleNodeSuccess(rc, node, nodeRun, result, duration)

	if cacheEnabled && cacheKey != "" && result.Output != nil {
		if err := s.repository.SaveCachedNodeResult(context.Background(), cacheKey, result.Output, cacheTTLSeconds); err != nil {
			log.Printf("Failed to save cache for node %s: %v", nodeID, err)
		}
	}
}

// executeWithRetries handles retry logic
func (s *Scheduler) executeWithRetries(rc *runContext, node *entity.Node, executor port.NodeExecutor, nodeRun *entity.NodeRun) (*port.NodeExecutionResult, error) {
	policy := node.RetryPolicy
	if policy == nil {
		policy = entity.DefaultRetryPolicy()
	}

	timeout := node.TimeoutMs
	if timeout == 0 {
		timeout = s.config.DefaultTimeoutMs
	}

	var lastErr error
	for attempt := 1; attempt <= policy.MaxAttempts; attempt++ {
		nodeRun.Attempt = attempt

		// Create timeout context
		execCtx, cancel := context.WithTimeout(rc.ctx, time.Duration(timeout)*time.Millisecond)

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

		// Check if error is retryable
		if !domain.IsRetryable(err) {
			return nil, err
		}

		// Emit retry event
		if attempt < policy.MaxAttempts {
			s.emitter.EmitAsync(
				rc.newEvent(port.EventTypeNodeRetrying).
					WithNode(node.ID, node.Type, node.Name).
					WithAttempt(attempt + 1).
					WithError(err.Error()),
			)

			// Calculate backoff
			backoff := s.calculateBackoff(policy, attempt)
			select {
			case <-rc.ctx.Done():
				return nil, rc.ctx.Err()
			case <-time.After(time.Duration(backoff) * time.Millisecond):
			}
		}
	}

	return nil, fmt.Errorf("max retries exceeded: %w", lastErr)
}

// calculateBackoff computes the backoff duration
func (s *Scheduler) calculateBackoff(policy *entity.RetryPolicy, attempt int) int {
	if policy.BackoffStrategy == "exponential" {
		return policy.BackoffMs * (1 << (attempt - 1))
	}
	return policy.BackoffMs
}

// enqueueNextNodes determines which nodes to run next
func (s *Scheduler) enqueueNextNodes(rc *runContext, node *entity.Node, result *port.NodeExecutionResult) {
	edges := rc.plan.GetOutgoingEdges(node.ID)

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
			return
		}

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

		// Enqueue taken branches
		for _, nextID := range validNext {
			s.decrementAndEnqueue(rc, nextID)
		}
		return
	}

	// Edge-level conditional routing for any node (when no explicit next_nodes set)
	if len(edges) > 0 {
		nextIDs, skippedIDs, usedConditions, err := s.evaluateEdgeConditions(rc, edges)
		if err != nil {
			s.setError(rc, domain.NewValidationError("edge_condition", err.Error()))
			return
		}
		if usedConditions {
			for _, skippedID := range skippedIDs {
				s.markSkipped(rc, skippedID)
			}
			for _, nextID := range nextIDs {
				s.decrementAndEnqueue(rc, nextID)
			}
			return
		}
	}

	// For all other nodes, enqueue all children
	for _, edge := range edges {
		s.decrementAndEnqueue(rc, edge.To)
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

func (s *Scheduler) handleNodeSuccess(rc *runContext, node *entity.Node, nodeRun *entity.NodeRun, result *port.NodeExecutionResult, durationMs int64) {
	nodeID := node.ID

	// Allow any node to emit routing directives via output.next_nodes / output.next_node
	if !result.HasNextNodes() {
		nextNodes, hasDirective, directiveErr := extractNextNodesFromOutput(result.Output)
		if directiveErr != nil {
			// Treat invalid routing directive as node failure
			nodeRun.Status = string(value.NodeRunStatusFailed)
			nodeRun.SetEnded(time.Now())
			nodeRun.ErrorJSON = map[string]any{"error": directiveErr.Error()}
			s.repository.UpdateNodeRun(rc.ctx, nodeRun)

			s.emitter.EmitAsync(
				rc.newEvent(port.EventTypeNodeFailed).
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

	if !s.validateStateSchema(rc, node, nodeRun, durationMs) {
		return
	}

	// Update node run as completed
	nodeRun.Status = string(value.NodeRunStatusSucceeded)
	nodeRun.SetEnded(time.Now())
	if result.Output != nil {
		nodeRun.OutputJSON = map[string]any{"output": result.Output}
	}
	s.repository.UpdateNodeRun(rc.ctx, nodeRun)

	// Emit node completed
	s.emitter.EmitAsync(
		rc.newEvent(port.EventTypeNodeCompleted).
			WithNode(nodeID, node.Type, node.Name).
			WithOutput(nodeRun.OutputJSON).
			WithDuration(durationMs),
	)

	// Mark completed
	rc.pendingMu.Lock()
	rc.completed[nodeID] = true
	rc.pendingMu.Unlock()

	// Determine next nodes and enqueue them
	s.enqueueNextNodes(rc, node, result)

	// Trigger summarization if configured
	s.maybeTriggerSummarization(rc, node)

	s.saveCheckpoint(rc, nodeID)
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

func (s *Scheduler) saveCheckpoint(rc *runContext, nodeID string) {
	if !s.isCheckpointingEnabled() {
		return
	}

	stepIndex := int(atomic.AddInt64(&rc.checkpointSeq, 1))
	if s.config.CheckpointMode == CheckpointModeBatch {
		if !s.shouldSaveBatchCheckpoint(rc, stepIndex) {
			return
		}
	}

	rc.pendingMu.Lock()
	completedNodes := make([]string, 0, len(rc.completed))
	for id := range rc.completed {
		completedNodes = append(completedNodes, id)
	}
	skippedNodes := make([]string, 0, len(rc.skipped))
	for id := range rc.skipped {
		skippedNodes = append(skippedNodes, id)
	}
	rc.pendingMu.Unlock()

	checkpointPayload := map[string]any{
		"state":     rc.state.Snapshot(),
		"completed": completedNodes,
		"skipped":   skippedNodes,
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

	if err := s.repository.SaveCheckpoint(context.Background(), rc.runID, nodeID, stepIndex, checkpointPayload, completedNodes, skippedNodes, rc.graphJSON); err != nil {
		log.Printf("Failed to save checkpoint for run %s: %v", rc.runID, err)
		return
	}
	rc.lastCheckpointAt = time.Now()
}

func (s *Scheduler) shouldSaveBatchCheckpoint(rc *runContext, stepIndex int) bool {
	if s.config.CheckpointBatchSize > 0 && stepIndex%s.config.CheckpointBatchSize == 0 {
		return true
	}

	if s.config.CheckpointIntervalMs > 0 {
		if rc.lastCheckpointAt.IsZero() {
			return true
		}
		if time.Since(rc.lastCheckpointAt) >= time.Duration(s.config.CheckpointIntervalMs)*time.Millisecond {
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
		if rc.completed[nodeID] || rc.skipped[nodeID] {
			continue
		}
		if rc.pending[nodeID] <= 0 {
			ready = append(ready, nodeID)
		}
	}
	return ready
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

func parseCheckpointPayload(stateSnapshot map[string]any, completedNodes []string, skippedNodes []string) (map[string]any, []entity.Message, *entity.MemoryConfig, *entity.Summary, []string, []string) {
	if stateSnapshot == nil {
		return map[string]any{}, nil, nil, nil, completedNodes, skippedNodes
	}

	rawState, hasState := stateSnapshot["state"].(map[string]any)
	if !hasState {
		return stateSnapshot, nil, nil, nil, completedNodes, skippedNodes
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

	return rawState, bufferSnapshot, memoryConfig, summary, parsedCompleted, parsedSkipped
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
	defer rc.pendingMu.Unlock()

	// Skip if already completed, skipped, or running
	if rc.completed[nodeID] || rc.skipped[nodeID] || rc.running[nodeID] {
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
		nodeRun := &entity.NodeRun{
			ID:        fmt.Sprintf("%s-%s", rc.runID, nodeID),
			RunID:     rc.runID,
			NodeID:    nodeID,
			NodeType:  node.Type,
			Status:    string(value.NodeRunStatusSkipped),
			StartedAt: time.Now(),
		}
		nodeRun.SetEnded(time.Now())
		s.repository.CreateNodeRun(rc.ctx, nodeRun)

		// Emit skipped event
		s.emitter.EmitAsync(
			rc.newEvent(port.EventTypeNodeSkipped).
				WithNode(nodeID, node.Type, node.Name),
		)
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
	s.repository.SetRunEnded(context.Background(), rc.runID, string(finalStatus), output, errorMsg)

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

	s.repository.UpdateRunStatus(context.Background(), runID, string(value.RunStatusCanceled))
	s.emitter.EmitAsync(rc.newEvent(port.EventTypeRunCanceled))
	s.flushEmitter("run_canceled")

	return nil
}

// ResumeRun resumes a paused run after human gate approval/rejection
func (s *Scheduler) ResumeRun(ctx context.Context, runID, nodeID, inputJSON string) error {
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

	// Check if approved or rejected
	approved, _ := decision["approved"].(bool)
	feedback, _ := decision["feedback"].(string)

	// Handle rejection - terminate the run
	if !approved {
		errorMsg := "Rejected by user"
		if feedback != "" {
			errorMsg = fmt.Sprintf("Rejected by user: %s", feedback)
		}

		// Update node run to failed
		nodeRun, _ := s.repository.GetNodeRun(ctx, runID, nodeID)
		if nodeRun != nil {
			nodeRun.Status = string(value.NodeRunStatusFailed)
			now := time.Now()
			nodeRun.EndedAt = &now
			nodeRun.ErrorJSON = map[string]any{"message": errorMsg, "rejected": true}
			s.repository.UpdateNodeRun(ctx, nodeRun)
		}

		// Mark run as failed
		s.repository.SetRunEnded(ctx, runID, string(value.RunStatusFailed), nil, errorMsg)
		s.repository.ClearPauseState(ctx, runID)
		s.emitter.EmitAsync(port.NewEvent(port.EventTypeRunFailed, runID).WithTenantID(tenantID).WithError(errorMsg))
		s.flushEmitter("run_failed")
		return nil
	}

	// Parse graph JSON
	var graph entity.Graph
	if err := json.Unmarshal([]byte(graphJSON), &graph); err != nil {
		return fmt.Errorf("invalid stored graph JSON: %w", err)
	}

	stateSchemaRaw, schemaMode := extractStateSchemaMetadata(graph.Metadata)
	stateSchema, err := service.CompileSchema(stateSchemaRaw)
	if err != nil {
		return fmt.Errorf("invalid state_schema: %w", err)
	}

	// Build execution plan
	planner := service.NewExecutionPlanner()
	plan := planner.Plan(&graph)

	// Restore state from snapshot
	state := entity.NewStateFromSnapshot(stateSnapshot)

	// Inject human decision into state
	humanDecision := map[string]any{
		"approved":   true,
		"fields":     decision["fields"],
		"feedback":   feedback,
		"decided_at": time.Now().Format(time.RFC3339),
	}
	state.SetNodeOutput(nodeID, humanDecision)

	// Update human gate node run to succeeded
	nodeRun, _ := s.repository.GetNodeRun(ctx, runID, nodeID)
	if nodeRun != nil {
		nodeRun.Status = string(value.NodeRunStatusSucceeded)
		now := time.Now()
		nodeRun.EndedAt = &now
		nodeRun.OutputJSON = map[string]any{"output": humanDecision}
		s.repository.UpdateNodeRun(ctx, nodeRun)
	}

	// Create run context for resumed execution
	runCtx, cancel := context.WithCancel(ctx)
	resumeMemoryConfig := defaultMemoryConfig()
	var resumeBuffer *entity.MessageBuffer
	if resumeMemoryConfig.Tier1.Enabled {
		resumeBuffer = entity.NewMessageBuffer(resumeMemoryConfig.Tier1.BufferSize)
	}
	rc := &runContext{
		runID:         runID,
		ctx:           runCtx,
		cancel:        cancel,
		plan:          plan,
		state:         state,
		graphJSON:     graphJSON,
		tenantID:      tenantID,
		messageBuffer: resumeBuffer,
		memoryConfig:  resumeMemoryConfig,
		stateSchema:   stateSchema,
		schemaMode:    schemaMode,
		pending:       plan.CloneIndegree(),
		completed:     make(map[string]bool),
		skipped:       make(map[string]bool),
		running:       make(map[string]bool),
		workChan:      make(chan string, len(plan.NodeMap)),
	}
	rc.memoryCtx = &port.RunContext{
		MemoryBuffer:   rc.messageBuffer,
		MemoryConfig:   rc.memoryConfig,
		CurrentSummary: rc.currentSummary,
		TrackMessage:   rc.trackMessages,
	}
	rc.ctx = port.WithRunContext(rc.ctx, rc.memoryCtx)
	if rc.tenantID != "" {
		rc.ctx = port.WithTenantID(rc.ctx, rc.tenantID)
	}

	if s.isCheckpointingEnabled() {
		if _, stepIndex, _, _, _, _, err := s.repository.LoadLatestCheckpoint(ctx, runID); err == nil {
			rc.checkpointSeq = int64(stepIndex)
		}
	}

	// Mark previously completed nodes
	for _, completedID := range completedNodes {
		rc.completed[completedID] = true
	}
	// Mark skipped nodes from paused state
	for _, skippedID := range skippedNodes {
		rc.skipped[skippedID] = true
	}
	// Also mark the human gate node as completed
	rc.completed[nodeID] = true

	// Rebuild pending counts based on completed/skipped nodes
	s.applyCheckpointToPending(rc)
	rc.initialNodes = s.computeReadyNodes(rc)

	// Store active run
	s.activeRuns.Store(runID, rc)

	// Clear pause state and update run status
	s.repository.ClearPauseState(ctx, runID)
	s.repository.UpdateRunStatus(ctx, runID, string(value.RunStatusRunning))

	// Emit run resumed event
	s.emitter.EmitAsync(rc.newEvent(port.EventTypeRunResumed))

	// Start execution in background from all ready nodes
	go s.executeResumedRun(rc, rc.initialNodes)

	return nil
}

// executeResumedRun continues execution from a resumed run
func (s *Scheduler) executeResumedRun(rc *runContext, startNodes []string) {
	defer func() {
		// Cleanup
		s.activeRuns.Delete(rc.runID)
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

func (s *Scheduler) validateStateSchema(rc *runContext, node *entity.Node, nodeRun *entity.NodeRun, durationMs int64) bool {
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
		nodeRun.SetEnded(time.Now())
		nodeRun.ErrorJSON = map[string]any{
			"error":  errMsg,
			"issues": issues,
		}
		s.repository.UpdateNodeRun(rc.ctx, nodeRun)

		s.emitter.EmitAsync(
			rc.newEvent(port.EventTypeNodeFailed).
				WithNode(node.ID, node.Type, node.Name).
				WithError(errMsg).
				WithDuration(durationMs),
		)
		s.setError(rc, domain.NewNodeError(node.ID, node.Type, fmt.Errorf(errMsg)))
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
