package usecase

import (
	"context"
	"fmt"
	"sort"
	"sync"
	"testing"
	"time"

	"github.com/forgegraph/engine/adapter/store"
	"github.com/forgegraph/engine/application/port"
	"github.com/forgegraph/engine/domain/entity"
)

type ManualClock struct {
	mu      sync.Mutex
	now     time.Time
	nextID  int
	waiters []manualClockWaiter
}

type manualClockWaiter struct {
	id       int
	deadline time.Time
	ch       chan time.Time
}

func NewManualClock(start time.Time) *ManualClock {
	return &ManualClock{now: start}
}

func (c *ManualClock) Now() time.Time {
	c.mu.Lock()
	defer c.mu.Unlock()
	return c.now
}

func (c *ManualClock) After(d time.Duration) <-chan time.Time {
	c.mu.Lock()
	defer c.mu.Unlock()

	ch := make(chan time.Time, 1)
	deadline := c.now.Add(d)
	if !deadline.After(c.now) {
		ch <- c.now
		return ch
	}

	c.nextID++
	c.waiters = append(c.waiters, manualClockWaiter{
		id:       c.nextID,
		deadline: deadline,
		ch:       ch,
	})
	return ch
}

func (c *ManualClock) Advance(d time.Duration) time.Time {
	c.mu.Lock()
	target := c.now.Add(d)
	c.mu.Unlock()
	return c.AdvanceTo(target)
}

func (c *ManualClock) AdvanceTo(target time.Time) time.Time {
	c.mu.Lock()
	if target.Before(c.now) {
		target = c.now
	}
	c.now = target

	ready := make([]manualClockWaiter, 0)
	pending := c.waiters[:0]
	for _, waiter := range c.waiters {
		if !waiter.deadline.After(c.now) {
			ready = append(ready, waiter)
			continue
		}
		pending = append(pending, waiter)
	}
	c.waiters = pending
	now := c.now
	c.mu.Unlock()

	sort.Slice(ready, func(i, j int) bool {
		if ready[i].deadline.Equal(ready[j].deadline) {
			return ready[i].id < ready[j].id
		}
		return ready[i].deadline.Before(ready[j].deadline)
	})

	for _, waiter := range ready {
		waiter.ch <- now
	}
	return now
}

type ObservedEvent struct {
	Sequence int
	Event    *port.ExecutionEvent
}

type DeterministicEventBus struct {
	mu     sync.Mutex
	seq    int
	events []ObservedEvent
	notify chan struct{}
}

func NewDeterministicEventBus() *DeterministicEventBus {
	return &DeterministicEventBus{
		events: make([]ObservedEvent, 0),
		notify: make(chan struct{}, 1),
	}
}

func (b *DeterministicEventBus) Emit(ctx context.Context, event *port.ExecutionEvent) error {
	_ = ctx
	b.mu.Lock()
	b.seq++
	cloned := cloneExecutionEvent(event)
	b.events = append(b.events, ObservedEvent{
		Sequence: b.seq,
		Event:    cloned,
	})
	b.mu.Unlock()
	select {
	case b.notify <- struct{}{}:
	default:
	}
	return nil
}

func (b *DeterministicEventBus) EmitAsync(event *port.ExecutionEvent) {
	_ = b.Emit(context.Background(), event)
}

func (b *DeterministicEventBus) Flush(ctx context.Context) error {
	_ = ctx
	return nil
}

func (b *DeterministicEventBus) All() []ObservedEvent {
	b.mu.Lock()
	defer b.mu.Unlock()
	result := make([]ObservedEvent, len(b.events))
	copy(result, b.events)
	return result
}

func (b *DeterministicEventBus) Notify() <-chan struct{} {
	return b.notify
}

func cloneExecutionEvent(event *port.ExecutionEvent) *port.ExecutionEvent {
	if event == nil {
		return nil
	}
	cloned := *event
	cloned.Input = cloneMapAny(event.Input)
	cloned.Output = cloneMapAny(event.Output)
	return &cloned
}

type StepController struct {
	mu       sync.Mutex
	active   map[string]*stepGate
	attempts map[string]int
	notify   chan struct{}
}

type stepGate struct {
	runID   string
	nodeID  string
	attempt int
	release chan struct{}
}

func NewStepController() *StepController {
	return &StepController{
		active:   make(map[string]*stepGate),
		attempts: make(map[string]int),
		notify:   make(chan struct{}, 1),
	}
}

func (c *StepController) BeforeNodeExecute(runID string, nodeID string) {
	key := stepKey(runID, nodeID)
	gate := &stepGate{
		runID:   runID,
		nodeID:  nodeID,
		release: make(chan struct{}),
	}

	c.mu.Lock()
	c.attempts[key]++
	gate.attempt = c.attempts[key]
	c.active[key] = gate
	c.mu.Unlock()

	select {
	case c.notify <- struct{}{}:
	default:
	}

	<-gate.release
}

func (c *StepController) Notify() <-chan struct{} {
	return c.notify
}

func (c *StepController) AttemptCount(runID string, nodeID string) int {
	c.mu.Lock()
	defer c.mu.Unlock()
	return c.attempts[stepKey(runID, nodeID)]
}

func (c *StepController) ActiveNodes(runID string) []string {
	c.mu.Lock()
	defer c.mu.Unlock()

	nodes := make([]string, 0)
	for _, gate := range c.active {
		if gate.runID == runID {
			nodes = append(nodes, gate.nodeID)
		}
	}
	sort.Strings(nodes)
	return nodes
}

func (c *StepController) WaitForAttempt(ctx context.Context, runID string, nodeID string, attempt int) bool {
	key := stepKey(runID, nodeID)
	for {
		c.mu.Lock()
		gate, ok := c.active[key]
		currentAttempt := c.attempts[key]
		c.mu.Unlock()

		if ok && gate.attempt >= attempt && currentAttempt >= attempt {
			return true
		}

		select {
		case <-ctx.Done():
			return false
		case <-c.notify:
		}
	}
}

func (c *StepController) WaitForBlockedCount(ctx context.Context, runID string, count int) bool {
	for {
		if len(c.ActiveNodes(runID)) >= count {
			return true
		}
		select {
		case <-ctx.Done():
			return false
		case <-c.notify:
		}
	}
}

func (c *StepController) Release(runID string, nodeID string) bool {
	key := stepKey(runID, nodeID)

	c.mu.Lock()
	gate, ok := c.active[key]
	if ok {
		delete(c.active, key)
	}
	c.mu.Unlock()

	if !ok {
		return false
	}
	close(gate.release)
	return true
}

func (c *StepController) ReleaseAll(runID string) int {
	c.mu.Lock()
	toRelease := make([]*stepGate, 0)
	for key, gate := range c.active {
		if gate.runID != runID {
			continue
		}
		toRelease = append(toRelease, gate)
		delete(c.active, key)
	}
	c.mu.Unlock()

	for _, gate := range toRelease {
		close(gate.release)
	}
	return len(toRelease)
}

func stepKey(runID string, nodeID string) string {
	return fmt.Sprintf("%s::%s", runID, nodeID)
}

type TestEngine struct {
	t         *testing.T
	Clock     *ManualClock
	Bus       *DeterministicEventBus
	Stepper   *StepController
	Repo      *mockRepository
	Registry  *port.DefaultExecutorRegistry
	Scheduler *Scheduler
}

func NewTestEngine(t *testing.T, maxWorkers int) *TestEngine {
	t.Helper()

	if maxWorkers <= 0 {
		maxWorkers = 8
	}

	clock := NewManualClock(time.Date(2026, time.January, 1, 0, 0, 0, 0, time.UTC))
	bus := NewDeterministicEventBus()
	stepper := NewStepController()
	repo := newMockRepository()
	registry := port.NewExecutorRegistry()

	scheduler := NewScheduler(
		SchedulerConfig{
			MaxWorkers:       maxWorkers,
			DefaultTimeoutMs: 30_000,
		},
		registry,
		repo,
		bus,
		store.NewInMemoryMemoryStore(),
	)
	scheduler.clock = clock
	scheduler.hooks = schedulerHooks{
		beforeNodeExecuteFn: stepper.BeforeNodeExecute,
	}

	return &TestEngine{
		t:         t,
		Clock:     clock,
		Bus:       bus,
		Stepper:   stepper,
		Repo:      repo,
		Registry:  registry,
		Scheduler: scheduler,
	}
}

func (e *TestEngine) RegisterExecutor(
	nodeType string,
	fn func(ctx context.Context, node *entity.Node, state *entity.State) (*port.NodeExecutionResult, error),
) *mockExecutor {
	e.t.Helper()
	exec := newMockExecutor(nodeType, fn)
	e.Registry.Register(exec)
	return exec
}

func (e *TestEngine) StartRun(runID string, graphJSON string, inputJSON string) {
	e.t.Helper()
	if inputJSON == "" {
		inputJSON = "{}"
	}
	if err := e.Scheduler.StartRun(context.Background(), runID, graphJSON, inputJSON, "", "", "", ""); err != nil {
		e.t.Fatalf("StartRun(%s) failed: %v", runID, err)
	}
}

func (e *TestEngine) ResumeRun(runID string, nodeID string, inputJSON string) {
	e.t.Helper()
	if err := e.Scheduler.ResumeRun(context.Background(), runID, nodeID, inputJSON); err != nil {
		e.t.Fatalf("ResumeRun(%s, %s) failed: %v", runID, nodeID, err)
	}
}

func (e *TestEngine) Snapshot(runID string) *RunSnapshot {
	e.t.Helper()
	snapshot, err := e.Scheduler.SnapshotRun(context.Background(), runID)
	if err != nil {
		e.t.Fatalf("SnapshotRun(%s) failed: %v", runID, err)
	}
	return snapshot
}

func (e *TestEngine) Advance(d time.Duration) {
	e.t.Helper()
	e.Clock.Advance(d)
}

func (e *TestEngine) AwaitBlockedAttempt(runID string, nodeID string, attempt int) {
	e.t.Helper()
	ctx, cancel := e.waitContext()
	defer cancel()
	if !e.Stepper.WaitForAttempt(ctx, runID, nodeID, attempt) {
		e.t.Fatalf("node %s attempt %d did not block", nodeID, attempt)
	}
}

func (e *TestEngine) AwaitBlockedCount(runID string, count int) []string {
	e.t.Helper()
	ctx, cancel := e.waitContext()
	defer cancel()
	if !e.Stepper.WaitForBlockedCount(ctx, runID, count) {
		e.t.Fatalf("expected %d blocked nodes for %s, saw %v", count, runID, e.Stepper.ActiveNodes(runID))
	}
	return e.Stepper.ActiveNodes(runID)
}

func (e *TestEngine) Release(runID string, nodeID string) {
	e.t.Helper()
	if !e.Stepper.Release(runID, nodeID) {
		e.t.Fatalf("node %s was not blocked", nodeID)
	}
}

func (e *TestEngine) ReleaseAll(runID string) int {
	e.t.Helper()
	return e.Stepper.ReleaseAll(runID)
}

func (e *TestEngine) AwaitRunStatus(runID string, status string) *RunSnapshot {
	e.t.Helper()
	ctx, cancel := e.waitContext()
	defer cancel()

	for {
		snapshot := e.Snapshot(runID)
		if snapshot.Status == status {
			return snapshot
		}

		select {
		case <-ctx.Done():
			e.t.Fatalf("run %s did not reach status %s; last snapshot=%+v", runID, status, snapshot)
		case <-e.Bus.Notify():
		case <-e.Stepper.Notify():
		}
	}
}

func (e *TestEngine) AwaitEvents(description string, predicate func([]ObservedEvent) bool) []ObservedEvent {
	e.t.Helper()
	ctx, cancel := e.waitContext()
	defer cancel()

	for {
		events := e.Bus.All()
		if predicate(events) {
			return events
		}

		select {
		case <-ctx.Done():
			e.t.Fatalf("timed out waiting for %s; events=%v", description, summarizeEvents(events))
		case <-e.Bus.Notify():
		}
	}
}

func (e *TestEngine) waitContext() (context.Context, context.CancelFunc) {
	if deadline, ok := e.t.Deadline(); ok {
		safeDeadline := deadline.Add(-250 * time.Millisecond)
		if time.Now().Before(safeDeadline) {
			return context.WithDeadline(context.Background(), safeDeadline)
		}
	}
	return context.WithTimeout(context.Background(), 5*time.Second)
}

func summarizeEvents(events []ObservedEvent) []string {
	result := make([]string, 0, len(events))
	for _, observed := range events {
		result = append(result, fmt.Sprintf("%d:%s:%s:%d", observed.Sequence, observed.Event.Type, observed.Event.NodeID, observed.Event.Attempt))
	}
	return result
}

func sequenceFor(events []ObservedEvent, eventType port.EventType, nodeID string) int {
	for _, observed := range events {
		if observed.Event.Type == eventType && observed.Event.NodeID == nodeID {
			return observed.Sequence
		}
	}
	return 0
}
