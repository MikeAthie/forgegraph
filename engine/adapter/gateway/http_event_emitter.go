package gateway

import (
	"bytes"
	"context"
	"crypto/hmac"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"log"
	"net/http"
	"sync"
	"time"

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
	}

	// Start background worker for async events
	go emitter.worker()

	return emitter
}

// Emit sends an event to the control plane synchronously
func (e *HTTPEventEmitter) Emit(ctx context.Context, event *port.ExecutionEvent) error {
	if e.callbackURL == "" {
		return nil // No callback URL configured, skip silently
	}

	return e.sendWithRetry(ctx, event)
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
		log.Printf("Warning: Event channel full, dropping event: %s for run %s", event.Type, event.RunID)
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
		if err := e.sendWithRetry(ctx, event); err != nil {
			log.Printf("Failed to send event %s for run %s: %v", event.Type, event.RunID, err)
		}
		cancel()
		e.pending.Done()
	}
}

// sendWithRetry sends an event with retry logic
func (e *HTTPEventEmitter) sendWithRetry(ctx context.Context, event *port.ExecutionEvent) error {
	var lastErr error

	for attempt := 1; attempt <= e.maxRetries; attempt++ {
		err := e.send(ctx, event)
		if err == nil {
			return nil
		}

		lastErr = err

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

	return fmt.Errorf("failed after %d retries: %w", e.maxRetries, lastErr)
}

// send makes the actual HTTP POST request
func (e *HTTPEventEmitter) send(ctx context.Context, event *port.ExecutionEvent) error {
	body, err := json.Marshal(event)
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
