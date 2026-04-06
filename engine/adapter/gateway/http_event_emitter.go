package gateway

import (
	"bufio"
	"bytes"
	"context"
	"crypto/hmac"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"errors"
	"fmt"
	"log"
	"net/http"
	"os"
	"path/filepath"
	"sync"
	"time"

	"github.com/forgegraph/engine/adapter/metrics"
	"github.com/forgegraph/engine/application/port"
)

var ErrEventCallbackNotConfigured = errors.New("event callback URL is required")

// HTTPEventEmitter sends execution events to the control plane via HTTP POST.
type HTTPEventEmitter struct {
	client      *http.Client
	callbackURL string
	secret      string

	// Async event handling
	eventChan chan *port.ExecutionEvent
	wg        sync.WaitGroup
	pending   sync.WaitGroup
	closed    bool
	closeMu   sync.Mutex

	// Configuration
	maxRetries         int
	retryDelay         time.Duration
	spoolFlushInterval time.Duration

	// Disk spool for undelivered events
	spoolPath    string
	spoolMu      sync.Mutex
	flushMu      sync.Mutex
	spoolFlushCh chan struct{}
	stopCh       chan struct{}
}

// HTTPEventEmitterConfig holds configuration for the event emitter
type HTTPEventEmitterConfig struct {
	// CallbackURL is the URL to POST events to
	CallbackURL string

	// Client is the HTTP client to use (optional, uses default if nil)
	Client *http.Client

	// MaxRetries is the number of times to retry failed requests (default: 3)
	MaxRetries int

	// RetryDelay is the delay between retries (default: 100ms)
	RetryDelay time.Duration

	// BufferSize is the size of the async event buffer (default: 100)
	BufferSize int

	// SignatureSecret is the shared secret for S2S callback signing (optional)
	SignatureSecret string

	// SpoolPath enables disk persistence for undelivered events (JSONL)
	SpoolPath string

	// SpoolFlushInterval controls how often the emitter retries spooled events.
	SpoolFlushInterval time.Duration
}

// DefaultHTTPEventEmitterConfig returns sensible defaults
func DefaultHTTPEventEmitterConfig(callbackURL string) HTTPEventEmitterConfig {
	return HTTPEventEmitterConfig{
		CallbackURL: callbackURL,
		MaxRetries:  3,
		RetryDelay:  100 * time.Millisecond,
		BufferSize:  100,
	}
}

// NewHTTPEventEmitter creates a new HTTP event emitter
func NewHTTPEventEmitter(config HTTPEventEmitterConfig) (*HTTPEventEmitter, error) {
	if config.CallbackURL == "" {
		return nil, ErrEventCallbackNotConfigured
	}

	client := config.Client
	if client == nil {
		client = &http.Client{
			Timeout: 10 * time.Second,
		}
	}

	maxRetries := config.MaxRetries
	if maxRetries == 0 {
		maxRetries = 3
	}

	retryDelay := config.RetryDelay
	if retryDelay == 0 {
		retryDelay = 100 * time.Millisecond
	}

	bufferSize := config.BufferSize
	if bufferSize == 0 {
		bufferSize = 100
	}

	spoolFlushInterval := config.SpoolFlushInterval
	if spoolFlushInterval <= 0 {
		spoolFlushInterval = 5 * time.Second
	}

	spoolPath := config.SpoolPath
	if spoolPath == "" {
		spoolPath = defaultSpoolPath(config.CallbackURL)
	}

	emitter := &HTTPEventEmitter{
		client:             client,
		callbackURL:        config.CallbackURL,
		secret:             config.SignatureSecret,
		eventChan:          make(chan *port.ExecutionEvent, bufferSize),
		maxRetries:         maxRetries,
		retryDelay:         retryDelay,
		spoolFlushInterval: spoolFlushInterval,
		spoolPath:          spoolPath,
		spoolFlushCh:       make(chan struct{}, 1),
		stopCh:             make(chan struct{}),
	}

	// Start background worker for async events
	emitter.wg.Add(2)
	go emitter.worker()
	go emitter.spoolWorker()

	return emitter, nil
}

// Emit sends an event to the control plane synchronously
func (e *HTTPEventEmitter) Emit(ctx context.Context, event *port.ExecutionEvent) error {
	if e.callbackURL == "" {
		return ErrEventCallbackNotConfigured
	}

	return e.sendWithRetry(ctx, event, true)
}

// EmitAsync queues an event for asynchronous delivery
func (e *HTTPEventEmitter) EmitAsync(event *port.ExecutionEvent) {
	if event == nil {
		return
	}

	e.closeMu.Lock()
	if e.closed {
		e.closeMu.Unlock()
		if err := e.enqueueDurably(event, "closed"); err != nil {
			log.Printf("Critical: failed to durably enqueue closed event %s for run %s: %v", event.Type, event.RunID, err)
		}
		return
	}

	e.pending.Add(1)
	select {
	case e.eventChan <- event:
		e.closeMu.Unlock()
		return
	default:
		e.pending.Done()
	}
	e.closeMu.Unlock()

	if err := e.enqueueDurably(event, "buffer_full"); err != nil {
		log.Printf("Critical: failed to durably enqueue overflow event %s for run %s: %v", event.Type, event.RunID, err)
	}
}

// Flush waits for all pending async events to be sent
func (e *HTTPEventEmitter) Flush(ctx context.Context) error {
	done := make(chan struct{})
	go func() {
		e.pending.Wait()
		close(done)
	}()

	select {
	case <-done:
	case <-ctx.Done():
		return ctx.Err()
	}

	for {
		remaining, err := e.flushSpool(ctx)
		if err != nil {
			return err
		}
		if remaining == 0 {
			return nil
		}

		select {
		case <-time.After(e.retryDelay):
		case <-ctx.Done():
			return ctx.Err()
		}
	}
}

// worker processes events from the async channel
func (e *HTTPEventEmitter) worker() {
	defer e.wg.Done()

	for event := range e.eventChan {
		ctx, cancel := context.WithTimeout(context.Background(), 30*time.Second)
		if err := e.sendWithRetry(ctx, event, true); err != nil {
			log.Printf("Failed to send event %s for run %s: %v", event.Type, event.RunID, err)
		}
		cancel()
		e.pending.Done()
	}
}

func (e *HTTPEventEmitter) spoolWorker() {
	defer e.wg.Done()

	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()

	go func() {
		<-e.stopCh
		cancel()
	}()

	if _, err := e.flushSpool(ctx); err != nil && !errors.Is(err, context.Canceled) {
		log.Printf("Warning: failed to flush event spool on startup: %v", err)
	}

	ticker := time.NewTicker(e.spoolFlushInterval)
	defer ticker.Stop()

	for {
		select {
		case <-ticker.C:
			if _, err := e.flushSpool(ctx); err != nil && !errors.Is(err, context.Canceled) {
				log.Printf("Warning: failed to flush event spool: %v", err)
			}
		case <-e.spoolFlushCh:
			if _, err := e.flushSpool(ctx); err != nil && !errors.Is(err, context.Canceled) {
				log.Printf("Warning: failed to flush event spool: %v", err)
			}
		case <-e.stopCh:
			return
		}
	}
}

// sendWithRetry sends an event with retry logic
func (e *HTTPEventEmitter) sendWithRetry(ctx context.Context, event *port.ExecutionEvent, spoolOnFailure bool) error {
	var lastErr error

	for attempt := 1; attempt <= e.maxRetries; attempt++ {
		err := e.send(ctx, event)
		if err == nil {
			metrics.RecordEventDeliverySuccess(event.Type.String())
			return nil
		}

		lastErr = err
		if attempt > 1 {
			metrics.RecordEventDeliveryRetry(event.Type.String())
		}

		// Don't retry on context cancellation
		if ctx.Err() != nil {
			return ctx.Err()
		}

		// Wait before retry
		if attempt < e.maxRetries {
			select {
			case <-time.After(e.retryDelay):
			case <-ctx.Done():
				return ctx.Err()
			}
		}
	}

	metrics.RecordEventDeliveryFailure(event.Type.String())
	if spoolOnFailure {
		if err := e.appendToSpool(event); err != nil {
			return fmt.Errorf("failed after %d retries and could not spool event: %w", e.maxRetries, err)
		}
	}
	return fmt.Errorf("failed after %d retries: %w", e.maxRetries, lastErr)
}

// send makes the actual HTTP POST request
func (e *HTTPEventEmitter) send(ctx context.Context, event *port.ExecutionEvent) error {
	body, err := json.Marshal(toCloudEventEnvelope(event))
	if err != nil {
		return fmt.Errorf("failed to marshal event: %w", err)
	}

	req, err := http.NewRequestWithContext(ctx, "POST", e.callbackURL, bytes.NewReader(body))
	if err != nil {
		return fmt.Errorf("failed to create request: %w", err)
	}

	req.Header.Set("Content-Type", "application/json")
	if e.secret != "" {
		timestamp := fmt.Sprintf("%d", time.Now().UnixMilli())
		signature := signPayload(e.secret, timestamp, body)
		req.Header.Set("X-Forgegraph-Timestamp", timestamp)
		req.Header.Set("X-Forgegraph-Signature", signature)
	}
	if event.Traceparent != "" {
		req.Header.Set("traceparent", event.Traceparent)
	}
	if event.Tracestate != "" {
		req.Header.Set("tracestate", event.Tracestate)
	}

	resp, err := e.client.Do(req)
	if err != nil {
		return fmt.Errorf("request failed: %w", err)
	}
	defer resp.Body.Close()

	if resp.StatusCode >= 400 {
		return fmt.Errorf("server returned status %d", resp.StatusCode)
	}

	return nil
}

func signPayload(secret string, timestamp string, body []byte) string {
	message := append([]byte(timestamp+"."), body...)
	mac := hmac.New(sha256.New, []byte(secret))
	mac.Write(message)
	return hex.EncodeToString(mac.Sum(nil))
}

func toCloudEventEnvelope(event *port.ExecutionEvent) map[string]any {
	if event == nil {
		return map[string]any{}
	}
	eventType := map[string]string{
		"run_started":           "forgegraph.run.started",
		"run_completed":         "forgegraph.run.completed",
		"run_failed":            "forgegraph.run.failed",
		"run_paused":            "forgegraph.run.paused",
		"run_resumed":           "forgegraph.run.resumed",
		"run_canceled":          "forgegraph.run.canceled",
		"run.schema_validation": "forgegraph.run.schema_validation",
		"node_started":          "forgegraph.node.started",
		"node_completed":        "forgegraph.node.completed",
		"node_failed":           "forgegraph.node.failed",
		"node_skipped":          "forgegraph.node.skipped",
		"node_retrying":         "forgegraph.node.retrying",
		"node_stream_chunk":     "forgegraph.node.stream_chunk",
	}[event.Type.String()]
	if eventType == "" {
		eventType = event.Type.String()
	}
	envelope := map[string]any{
		"specversion":     "1.0",
		"id":              event.EventID,
		"source":          "forgegraph-engine",
		"type":            eventType,
		"subject":         event.RunID,
		"time":            time.UnixMilli(event.Timestamp).UTC().Format(time.RFC3339Nano),
		"datacontenttype": "application/json",
		"data":            event,
	}
	if event.Traceparent != "" {
		envelope["traceparent"] = event.Traceparent
	}
	if event.Tracestate != "" {
		envelope["tracestate"] = event.Tracestate
	}
	return envelope
}

func (e *HTTPEventEmitter) appendToSpool(event *port.ExecutionEvent) error {
	if e.spoolPath == "" {
		return errors.New("event spool path is not configured")
	}

	e.spoolMu.Lock()
	defer e.spoolMu.Unlock()

	if err := os.MkdirAll(filepath.Dir(e.spoolPath), 0o755); err != nil {
		log.Printf("Warning: failed to create event spool directory: %v", err)
		return err
	}

	file, err := os.OpenFile(e.spoolPath, os.O_CREATE|os.O_WRONLY|os.O_APPEND, 0o600)
	if err != nil {
		log.Printf("Warning: failed to open event spool: %v", err)
		return err
	}
	defer file.Close()

	payload, err := json.Marshal(event)
	if err != nil {
		log.Printf("Warning: failed to marshal event for spool: %v", err)
		return err
	}

	if _, err := file.Write(append(payload, '\n')); err != nil {
		log.Printf("Warning: failed to write event to spool: %v", err)
		return err
	}
	if err := file.Sync(); err != nil {
		log.Printf("Warning: failed to fsync event spool: %v", err)
		return err
	}

	metrics.RecordEventSpooled(event.Type.String())
	return nil
}

func (e *HTTPEventEmitter) enqueueDurably(event *port.ExecutionEvent, reason string) error {
	if err := e.appendToSpool(event); err == nil {
		e.signalSpoolFlush()
		return nil
	} else {
		ctx, cancel := context.WithTimeout(context.Background(), 30*time.Second)
		defer cancel()

		sendErr := e.sendWithRetry(ctx, event, false)
		if sendErr == nil {
			log.Printf("Warning: event spill to durable queue failed for %s; delivered synchronously instead", reason)
			return nil
		}
		return fmt.Errorf(
			"durable enqueue failed (%s): spool=%v send=%w",
			reason,
			err,
			sendErr,
		)
	}
}

func (e *HTTPEventEmitter) signalSpoolFlush() {
	select {
	case e.spoolFlushCh <- struct{}{}:
	default:
	}
}

func (e *HTTPEventEmitter) flushSpool(ctx context.Context) (int, error) {
	if e.spoolPath == "" {
		return 0, nil
	}

	e.flushMu.Lock()
	defer e.flushMu.Unlock()

	processingPath, err := e.claimSpoolFile()
	if err != nil {
		return 0, err
	}
	if processingPath == "" {
		return 0, nil
	}

	file, err := os.Open(processingPath)
	if err != nil {
		e.restoreClaimedSpool(processingPath)
		if os.IsNotExist(err) {
			return 0, nil
		}
		return 0, err
	}
	scanner := bufio.NewScanner(file)
	scanner.Buffer(make([]byte, 0, 64*1024), 10*1024*1024)
	var remaining []string
	for scanner.Scan() {
		select {
		case <-ctx.Done():
			remaining = append(remaining, scanner.Text())
			for scanner.Scan() {
				remaining = append(remaining, scanner.Text())
			}
			if err := file.Close(); err != nil {
				return len(remaining), err
			}
			if appendErr := e.requeueRemaining(processingPath, remaining); appendErr != nil {
				return len(remaining), appendErr
			}
			return len(remaining), ctx.Err()
		default:
		}

		line := scanner.Text()
		if line == "" {
			continue
		}
		var event port.ExecutionEvent
		if err := json.Unmarshal([]byte(line), &event); err != nil {
			log.Printf("Warning: failed to parse spooled event: %v", err)
			continue
		}
		if err := e.sendWithRetry(ctx, &event, false); err != nil {
			remaining = append(remaining, line)
		}
	}

	if err := scanner.Err(); err != nil {
		log.Printf("Warning: failed to read event spool: %v", err)
		if closeErr := file.Close(); closeErr != nil {
			return len(remaining), closeErr
		}
		if appendErr := e.requeueRemaining(processingPath, remaining); appendErr != nil {
			return len(remaining), appendErr
		}
		return len(remaining), err
	}

	if err := file.Close(); err != nil {
		return len(remaining), err
	}
	if err := e.requeueRemaining(processingPath, remaining); err != nil {
		return len(remaining), err
	}
	return len(remaining), nil
}

func (e *HTTPEventEmitter) claimSpoolFile() (string, error) {
	if e.spoolPath == "" {
		return "", nil
	}

	e.spoolMu.Lock()
	defer e.spoolMu.Unlock()

	processingPath := fmt.Sprintf("%s.processing", e.spoolPath)
	if _, err := os.Stat(processingPath); err == nil {
		return processingPath, nil
	} else if !os.IsNotExist(err) {
		return "", err
	}

	if err := os.Rename(e.spoolPath, processingPath); err != nil {
		if os.IsNotExist(err) {
			return "", nil
		}
		return "", err
	}

	return processingPath, nil
}

func (e *HTTPEventEmitter) restoreClaimedSpool(processingPath string) {
	e.spoolMu.Lock()
	defer e.spoolMu.Unlock()

	if _, err := os.Stat(processingPath); err != nil {
		return
	}
	if _, err := os.Stat(e.spoolPath); err == nil {
		return
	}
	if err := os.Rename(processingPath, e.spoolPath); err != nil && !os.IsNotExist(err) {
		log.Printf("Warning: failed to restore claimed event spool: %v", err)
	}
}

func (e *HTTPEventEmitter) requeueRemaining(processingPath string, remaining []string) error {
	e.spoolMu.Lock()
	defer e.spoolMu.Unlock()

	if len(remaining) > 0 {
		file, err := os.OpenFile(e.spoolPath, os.O_CREATE|os.O_WRONLY|os.O_APPEND, 0o600)
		if err != nil {
			return err
		}
		for _, line := range remaining {
			if _, err := file.Write(append([]byte(line), '\n')); err != nil {
				file.Close()
				return err
			}
		}
		if err := file.Sync(); err != nil {
			file.Close()
			return err
		}
		if err := file.Close(); err != nil {
			return err
		}
	}

	if err := os.Remove(processingPath); err != nil && !os.IsNotExist(err) {
		return err
	}
	return nil
}

// Close shuts down the emitter and flushes pending events
func (e *HTTPEventEmitter) Close(ctx context.Context) error {
	e.closeMu.Lock()
	if !e.closed {
		e.closed = true
		close(e.eventChan)
		close(e.stopCh)
	}
	e.closeMu.Unlock()

	pendingDone := make(chan struct{})
	go func() {
		e.pending.Wait()
		close(pendingDone)
	}()

	select {
	case <-pendingDone:
	case <-ctx.Done():
		return ctx.Err()
	}

	closeDone := make(chan struct{})
	go func() {
		e.wg.Wait()
		close(closeDone)
	}()

	select {
	case <-closeDone:
	case <-ctx.Done():
		return ctx.Err()
	}

	remaining, err := e.flushSpool(ctx)
	if err != nil && !errors.Is(err, context.DeadlineExceeded) && !errors.Is(err, context.Canceled) {
		return err
	}
	if remaining > 0 {
		log.Printf("Warning: event emitter closed with %d durably queued events remaining in spool", remaining)
	}

	return nil
}

func defaultSpoolPath(callbackURL string) string {
	sum := sha256.Sum256([]byte(callbackURL))
	return filepath.Join(
		os.TempDir(),
		fmt.Sprintf("forgegraph-engine-events-%x.jsonl", sum[:8]),
	)
}

// RecordingEventEmitter records all events for testing
type RecordingEventEmitter struct {
	mu     sync.Mutex
	events []*port.ExecutionEvent
}

// NewRecordingEventEmitter creates a new recording event emitter
func NewRecordingEventEmitter() *RecordingEventEmitter {
	return &RecordingEventEmitter{
		events: make([]*port.ExecutionEvent, 0),
	}
}

// Emit records the event
func (e *RecordingEventEmitter) Emit(ctx context.Context, event *port.ExecutionEvent) error {
	e.mu.Lock()
	defer e.mu.Unlock()
	e.events = append(e.events, event)
	return nil
}

// EmitAsync records the event
func (e *RecordingEventEmitter) EmitAsync(event *port.ExecutionEvent) {
	e.Emit(context.Background(), event)
}

// Flush does nothing
func (e *RecordingEventEmitter) Flush(ctx context.Context) error {
	return nil
}

// GetEvents returns all recorded events
func (e *RecordingEventEmitter) GetEvents() []*port.ExecutionEvent {
	e.mu.Lock()
	defer e.mu.Unlock()
	result := make([]*port.ExecutionEvent, len(e.events))
	copy(result, e.events)
	return result
}

// GetEventsByType returns events of a specific type
func (e *RecordingEventEmitter) GetEventsByType(eventType port.EventType) []*port.ExecutionEvent {
	e.mu.Lock()
	defer e.mu.Unlock()
	var result []*port.ExecutionEvent
	for _, event := range e.events {
		if event.Type == eventType {
			result = append(result, event)
		}
	}
	return result
}

// GetEventsByRunID returns events for a specific run
func (e *RecordingEventEmitter) GetEventsByRunID(runID string) []*port.ExecutionEvent {
	e.mu.Lock()
	defer e.mu.Unlock()
	var result []*port.ExecutionEvent
	for _, event := range e.events {
		if event.RunID == runID {
			result = append(result, event)
		}
	}
	return result
}

// Clear removes all recorded events
func (e *RecordingEventEmitter) Clear() {
	e.mu.Lock()
	defer e.mu.Unlock()
	e.events = make([]*port.ExecutionEvent, 0)
}

// Count returns the number of recorded events
func (e *RecordingEventEmitter) Count() int {
	e.mu.Lock()
	defer e.mu.Unlock()
	return len(e.events)
}
