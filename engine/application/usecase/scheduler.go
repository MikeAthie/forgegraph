// Package usecase contains application use cases for the ForgeGraph engine.
package usecase

import (
	"context"
	"encoding/json"
	"fmt"
	"log"
	"sync"
	"time"

	"github.com/forgegraph/engine/application/port"
	"github.com/forgegraph/engine/domain"
	"github.com/forgegraph/engine/domain/entity"
	"github.com/forgegraph/engine/domain/service"
	"github.com/forgegraph/engine/domain/value"
)

// SchedulerConfig holds scheduler configuration
type SchedulerConfig struct {
	MaxWorkers       int // Maximum concurrent node executions
	DefaultTimeoutMs int // Default timeout for node execution
}

// DefaultSchedulerConfig returns sensible defaults
func DefaultSchedulerConfig() SchedulerConfig {
	return SchedulerConfig{
		MaxWorkers:       10,
		DefaultTimeoutMs: 30000, // 30 seconds
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
	return &Scheduler{
		config:     config,
		registry:   registry,
		repository: repository,
		emitter:    emitter,
	}
}

// runContext holds runtime state for a single run
type runContext struct {
	runID      string
	ctx        context.Context
	cancel     context.CancelFunc
	plan       *service.ExecutionPlan
	state      *entity.State
	callbackURL string

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
}

// StartRun begins executing a workflow
func (s *Scheduler) StartRun(ctx context.Context, runID string, graphJSON string, inputJSON string, callbackURL string) error {
	// Parse graph JSON
	var graph entity.Graph
	if err := json.Unmarshal([]byte(graphJSON), &graph); err != nil {
		return fmt.Errorf("invalid graph JSON: %w", err)
	}

	// Parse input JSON
	var input map[string]any
	if inputJSON != "" {
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

	// Initialize state with input
	state := entity.NewStateWithInput(input)

	// Create run context
	runCtx, cancel := context.WithCancel(ctx)
	rc := &runContext{
		runID:       runID,
		ctx:         runCtx,
		cancel:      cancel,
		plan:        plan,
		state:       state,
		callbackURL: callbackURL,
		pending:     plan.CloneIndegree(),
		completed:   make(map[string]bool),
		skipped:     make(map[string]bool),
		running:     make(map[string]bool),
		workChan:    make(chan string, len(plan.NodeMap)),
	}

	// Store active run
	s.activeRuns.Store(runID, rc)

	// Update run status to running
	if err := s.repository.UpdateRunStatus(ctx, runID, string(value.RunStatusRunning)); err != nil {
		log.Printf("Failed to update run status: %v", err)
	}

	// Emit run started event
	s.emitter.EmitAsync(port.NewEvent(port.EventTypeRunStarted, runID))

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
	for _, nodeID := range rc.plan.StartNodes {
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
		nodeRun.Status = string(value.NodeRunStatusSucceeded)
		nodeRun.SetEnded(time.Now())
		if result.Output != nil {
			nodeRun.OutputJSON = map[string]any{"output": result.Output}
		}
		s.repository.UpdateNodeRun(rc.ctx, nodeRun)

		s.repository.UpdateRunStatus(context.Background(), rc.runID, string(value.RunStatusPaused))
		s.emitter.EmitAsync(
			port.NewEvent(port.EventTypeRunPaused, rc.runID).
				WithNode(nodeID, node.Type, node.Name),
		)
		rc.cancel() // Stop further processing
		return
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
			WithDuration(duration),
	)

	// Mark completed
	rc.pendingMu.Lock()
	rc.completed[nodeID] = true
	rc.pendingMu.Unlock()

	// Determine next nodes and enqueue them
	s.enqueueNextNodes(rc, node, result)
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
		nextSet := make(map[string]bool)
		for _, n := range result.NextNodes {
			nextSet[n] = true
		}

		// Mark non-taken branches as skipped
		for _, edge := range edges {
			if !nextSet[edge.To] {
				s.markSkipped(rc, edge.To)
			}
		}

		// Enqueue taken branches
		for _, nextID := range result.NextNodes {
			s.decrementAndEnqueue(rc, nextID)
		}
		return
	}

	// For all other nodes, enqueue all children
	for _, edge := range edges {
		s.decrementAndEnqueue(rc, edge.To)
	}
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
		// Only auto-skip if this is the only incoming edge
		if rc.plan.GetIndegree(edge.To) == 1 {
			s.markSkipped(rc, edge.To)
		}
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
