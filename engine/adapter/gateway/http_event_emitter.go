package gateway

import (
	"bufio"
	"bytes"
	"context"
	"crypto/hmac"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"log"
	"net/http"
	"os"
	"sync"
	"time"

	"github.com/forgegraph/engine/adapter/metrics"
	"github.com/forgegraph/engine/application/port"
)

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
	maxRetries int
	retryDelay time.Duration

	// Optional disk spool for undelivered events
	spoolPath string
	spoolMu   sync.Mutex
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

	// SpoolPath enables optional disk persistence for undelivered events (JSONL)
	SpoolPath string
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
func NewHTTPEventEmitter(config HTTPEventEmitterConfig) *HTTPEventEmitter {
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

	emitter := &HTTPEventEmitter{
		client:      client,
		callbackURL: config.CallbackURL,
		secret:      config.SignatureSecret,
		eventChan:   make(chan *port.ExecutionEvent, bufferSize),
		maxRetries:  maxRetries,
		retryDelay:  retryDelay,
		spoolPath:   config.SpoolPath,
	}

	// Start background worker for async events
	go emitter.worker()
	if emitter.spoolPath != "" {
		go func() {
			if err := emitter.flushSpool(context.Background()); err != nil {
				log.Printf("Warning: failed to flush event spool: %v", err)
			}
		}()
	}

	return emitter
}

// Emit sends an event to the control plane synchronously
func (e *HTTPEventEmitter) Emit(ctx context.Context, event *port.ExecutionEvent) error {
	if e.callbackURL == "" {
		return nil // No callback URL configured, skip silently
	}

	return e.sendWithRetry(ctx, event, true)
}

// EmitAsync queues an event for asynchronous delivery
func (e *HTTPEventEmitter) EmitAsync(event *port.ExecutionEvent) {
	e.closeMu.Lock()
	if e.closed {
		e.closeMu.Unlock()
		log.Printf("Warning: EmitAsync called after emitter closed, event dropped: %s", event.Type)
		return
	}
	e.pending.Add(1)

	select {
	case e.eventChan <- event:
		e.closeMu.Unlock()
		// Event queued
	default:
		// Channel full, log and drop
		e.closeMu.Unlock()
		e.pending.Done()
		metrics.RecordEventDrop("buffer_full", event.Type.String())
		log.Printf("Warning: Event channel full, dropping event: %s for run %s (event_id=%s)", event.Type, event.RunID, event.EventID)
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
		return nil
	case <-ctx.Done():
		return ctx.Err()
	}
}

// worker processes events from the async channel
func (e *HTTPEventEmitter) worker() {
	e.wg.Add(1)
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
		e.appendToSpool(event)
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
		timestamp := fmt.Sprintf("%d", event.Timestamp)
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

func (e *HTTPEventEmitter) appendToSpool(event *port.ExecutionEvent) {
	if e.spoolPath == "" {
		return
	}

	e.spoolMu.Lock()
	defer e.spoolMu.Unlock()

	file, err := os.OpenFile(e.spoolPath, os.O_CREATE|os.O_WRONLY|os.O_APPEND, 0o600)
	if err != nil {
		log.Printf("Warning: failed to open event spool: %v", err)
		return
	}
	defer file.Close()

	payload, err := json.Marshal(event)
	if err != nil {
		log.Printf("Warning: failed to marshal event for spool: %v", err)
		return
	}

	if _, err := file.Write(append(payload, '\n')); err != nil {
		log.Printf("Warning: failed to write event to spool: %v", err)
		return
	}

	metrics.RecordEventSpooled(event.Type.String())
}

func (e *HTTPEventEmitter) flushSpool(ctx context.Context) error {
	if e.spoolPath == "" {
		return nil
	}

	e.spoolMu.Lock()
	defer e.spoolMu.Unlock()

	file, err := os.Open(e.spoolPath)
	if err != nil {
		if os.IsNotExist(err) {
			return nil
		}
		return err
	}
	defer file.Close()

	scanner := bufio.NewScanner(file)
	var remaining []string
	for scanner.Scan() {
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
		return err
	}

	if len(remaining) == 0 {
		if err := os.Remove(e.spoolPath); err != nil && !os.IsNotExist(err) {
			return err
		}
		return nil
	}

	tmpPath := fmt.Sprintf("%s.tmp", e.spoolPath)
	if err := os.WriteFile(tmpPath, []byte(fmt.Sprintf("%s\n", remaining[0])), 0o600); err != nil {
		return err
	}
	if len(remaining) > 1 {
		file, err := os.OpenFile(tmpPath, os.O_WRONLY|os.O_APPEND, 0o600)
		if err != nil {
			return err
		}
		for _, line := range remaining[1:] {
			if _, err := file.Write(append([]byte(line), '\n')); err != nil {
				file.Close()
				return err
			}
		}
		file.Close()
	}
	return os.Rename(tmpPath, e.spoolPath)
}

// Close shuts down the emitter and flushes pending events
func (e *HTTPEventEmitter) Close(ctx context.Context) error {
	e.closeMu.Lock()
	if !e.closed {
		e.closed = true
		close(e.eventChan)
	}
	e.closeMu.Unlock()

	if err := e.Flush(ctx); err != nil {
		return err
	}

	done := make(chan struct{})
	go func() {
		e.wg.Wait()
		close(done)
	}()

	select {
	case <-done:
		return nil
	case <-ctx.Done():
		return ctx.Err()
	}
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
