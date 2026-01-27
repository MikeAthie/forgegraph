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
)

// CheckpointMode controls durable checkpoint behavior.
type CheckpointMode string

const (
	CheckpointModeNone CheckpointMode = "none"
	CheckpointModeNode CheckpointMode = "node"
)

// SchedulerConfig holds scheduler configuration
type SchedulerConfig struct {
	MaxWorkers       int // Maximum concurrent node executions
	DefaultTimeoutMs int // Default timeout for node execution
	CheckpointMode   CheckpointMode
	CacheDefaultTTLSeconds int
}

// DefaultSchedulerConfig returns sensible defaults
func DefaultSchedulerConfig() SchedulerConfig {
	return SchedulerConfig{
		MaxWorkers:       10,
		DefaultTimeoutMs: 30000, // 30 seconds
		CheckpointMode:   CheckpointModeNode,
		CacheDefaultTTLSeconds: 3600,
	}
}

// Scheduler orchestrates workflow execution
type Scheduler struct {
	config     SchedulerConfig
	registry   port.ExecutorRegistry
	repository port.RunRepository
	emitter    port.EventEmitter

	// Active runs tracking
	activeRuns sync.Map // runID -> *runContext
}

// NewScheduler creates a new scheduler
func NewScheduler(
	config SchedulerConfig,
	registry port.ExecutorRegistry,
	repository port.RunRepository,
	emitter port.EventEmitter,
) *Scheduler {
	if config.CheckpointMode == "" {
		config.CheckpointMode = CheckpointModeNode
	}
	if config.CacheDefaultTTLSeconds == 0 {
		config.CacheDefaultTTLSeconds = 3600
	}
	return &Scheduler{
		config:     config,
		registry:   registry,
		repository: repository,
		emitter:    emitter,
	}
}

// runContext holds runtime state for a single run
type runContext struct {
	runID       string
	ctx         context.Context
	cancel      context.CancelFunc
	plan        *service.ExecutionPlan
	state       *entity.State
	callbackURL string
	graphJSON   string // Original graph JSON for pause/resume
	initialNodes []string

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

	checkpointSeq int64
}

// StartRun begins executing a workflow
func (s *Scheduler) StartRun(ctx context.Context, runID string, graphJSON string, inputJSON string, callbackURL string) error {
	type checkpointData struct {
		nodeID         string
		stepIndex      int
		stateSnapshot  map[string]any
		completedNodes []string
		skippedNodes   []string
		graphJSON      string
	}

	var checkpoint *checkpointData
	if s.isCheckpointingEnabled() {
		nodeID, stepIndex, snapshot, completedNodes, skippedNodes, checkpointGraphJSON, err := s.repository.LoadLatestCheckpoint(ctx, runID)
		if err == nil {
			if checkpointGraphJSON != "" {
				graphJSON = checkpointGraphJSON
			}
			checkpoint = &checkpointData{
				nodeID:         nodeID,
				stepIndex:      stepIndex,
				stateSnapshot:  snapshot,
				completedNodes: completedNodes,
				skippedNodes:   skippedNodes,
				graphJSON:      checkpointGraphJSON,
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

	// Create run context
	runCtx, cancel := context.WithCancel(ctx)
	rc := &runContext{
		runID:       runID,
		ctx:         runCtx,
		cancel:      cancel,
		plan:        plan,
		state:       state,
		callbackURL: callbackURL,
		graphJSON:   graphJSON,
		pending:     plan.CloneIndegree(),
		completed:   make(map[string]bool),
		skipped:     make(map[string]bool),
		running:     make(map[string]bool),
		workChan:    make(chan string, len(plan.NodeMap)),
	}

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

	// Update run status to running
	if err := s.repository.UpdateRunStatus(ctx, runID, string(value.RunStatusRunning)); err != nil {
		log.Printf("Failed to update run status: %v", err)
	}

	// Emit run started/resumed event
	if checkpoint != nil {
		s.emitter.EmitAsync(port.NewEvent(port.EventTypeRunResumed, runID))
	} else {
		s.emitter.EmitAsync(port.NewEvent(port.EventTypeRunStarted, runID))
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
		port.NewEvent(port.EventTypeNodeStarted, rc.runID).
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
			port.NewEvent(port.EventTypeNodeFailed, rc.runID).
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
		rc.pendingMu.Lock()
		for id := range rc.completed {
			completedNodes = append(completedNodes, id)
		}
		rc.pendingMu.Unlock()

		s.repository.SavePauseState(context.Background(), rc.runID, nodeID, stateSnapshot, completedNodes, rc.graphJSON)
		s.repository.UpdateRunStatus(context.Background(), rc.runID, string(value.RunStatusPaused))

		// Emit pause event with the pause payload
		pauseEvent := port.NewEvent(port.EventTypeRunPaused, rc.runID).
			WithNode(nodeID, node.Type, node.Name)
		if result.Output != nil {
			pauseEvent = pauseEvent.WithOutput(map[string]any{"pause_payload": result.Output})
		}
		s.emitter.EmitAsync(pauseEvent)

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
				port.NewEvent(port.EventTypeNodeRetrying, rc.runID).
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
				port.NewEvent(port.EventTypeNodeFailed, rc.runID).
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

	// Update node run as completed
	nodeRun.Status = string(value.NodeRunStatusSucceeded)
	nodeRun.SetEnded(time.Now())
	if result.Output != nil {
		nodeRun.OutputJSON = map[string]any{"output": result.Output}
	}
	s.repository.UpdateNodeRun(rc.ctx, nodeRun)

	// Emit node completed
	s.emitter.EmitAsync(
		port.NewEvent(port.EventTypeNodeCompleted, rc.runID).
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

	s.saveCheckpoint(rc, nodeID)
}

func (s *Scheduler) isCheckpointingEnabled() bool {
	return s.config.CheckpointMode != CheckpointModeNone
}

func (s *Scheduler) saveCheckpoint(rc *runContext, nodeID string) {
	if !s.isCheckpointingEnabled() {
		return
	}

	stepIndex := int(atomic.AddInt64(&rc.checkpointSeq, 1))
	stateSnapshot := rc.state.Snapshot()

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

	if err := s.repository.SaveCheckpoint(context.Background(), rc.runID, nodeID, stepIndex, stateSnapshot, completedNodes, skippedNodes, rc.graphJSON); err != nil {
		log.Printf("Failed to save checkpoint for run %s: %v", rc.runID, err)
	}
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
			port.NewEvent(port.EventTypeNodeSkipped, rc.runID).
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

	// Keep the latest checkpoint to enable threaded run continuation.

	// Emit final event
	var event *port.ExecutionEvent
	switch finalStatus {
	case value.RunStatusSucceeded:
		event = port.NewEvent(port.EventTypeRunCompleted, rc.runID).WithOutput(output)
	case value.RunStatusFailed:
		event = port.NewEvent(port.EventTypeRunFailed, rc.runID).WithError(errorMsg)
	case value.RunStatusCanceled:
		event = port.NewEvent(port.EventTypeRunCanceled, rc.runID)
	}
	if event != nil {
		s.emitter.EmitAsync(event)
	}
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
	s.emitter.EmitAsync(port.NewEvent(port.EventTypeRunCanceled, runID))

	return nil
}

// ResumeRun resumes a paused run after human gate approval/rejection
func (s *Scheduler) ResumeRun(ctx context.Context, runID, nodeID, inputJSON string) error {
	// Load pause state
	pausedNodeID, stateSnapshot, completedNodes, graphJSON, err := s.repository.LoadPauseState(ctx, runID)
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
		s.emitter.EmitAsync(port.NewEvent(port.EventTypeRunFailed, runID).WithError(errorMsg))
		return nil
	}

	// Parse graph JSON
	var graph entity.Graph
	if err := json.Unmarshal([]byte(graphJSON), &graph); err != nil {
		return fmt.Errorf("invalid stored graph JSON: %w", err)
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
	rc := &runContext{
		runID:     runID,
		ctx:       runCtx,
		cancel:    cancel,
		plan:      plan,
		state:     state,
		graphJSON: graphJSON,
		pending:   plan.CloneIndegree(),
		completed: make(map[string]bool),
		skipped:   make(map[string]bool),
		running:   make(map[string]bool),
		workChan:  make(chan string, len(plan.NodeMap)),
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
	// Also mark the human gate node as completed
	rc.completed[nodeID] = true

	// Store active run
	s.activeRuns.Store(runID, rc)

	// Clear pause state and update run status
	s.repository.ClearPauseState(ctx, runID)
	s.repository.UpdateRunStatus(ctx, runID, string(value.RunStatusRunning))

	// Emit run resumed event
	s.emitter.EmitAsync(port.NewEvent(port.EventTypeRunResumed, runID))

	// Start execution in background - resume from the human gate node's successors
	go s.executeResumedRun(rc, nodeID)

	return nil
}

// executeResumedRun continues execution from a resumed run
func (s *Scheduler) executeResumedRun(rc *runContext, resumedNodeID string) {
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

	// Get the node we resumed from
	resumedNode := rc.plan.GetNode(resumedNodeID)
	if resumedNode == nil {
		log.Printf("Resumed node %s not found in plan", resumedNodeID)
		return
	}

	// Enqueue downstream nodes of the resumed human gate
	for _, edge := range rc.plan.GetOutgoingEdges(resumedNodeID) {
		rc.wg.Add(1)
		// Decrement pending count for downstream nodes
		rc.pendingMu.Lock()
		rc.pending[edge.To]--
		if rc.pending[edge.To] == 0 {
			rc.pendingMu.Unlock()
			rc.workChan <- edge.To
		} else {
			rc.pendingMu.Unlock()
			rc.wg.Done() // Not ready yet
		}
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
