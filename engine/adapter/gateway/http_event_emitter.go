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
	"io"
	"log"
	"net/http"
	"os"
	"path/filepath"
	"strings"
	"sync"
	"time"

	"github.com/forgegraph/engine/adapter/metrics"
	"github.com/forgegraph/engine/application/port"
	"github.com/google/uuid"
)

var ErrEventCallbackNotConfigured = errors.New("event callback URL is required")

type eventDeliveryError struct {
	err        error
	retryable  bool
	deadLetter bool
}

func (e *eventDeliveryError) Error() string {
	return e.err.Error()
}

func (e *eventDeliveryError) Unwrap() error {
	return e.err
}

func isRetryableEventDeliveryError(err error) bool {
	var deliveryErr *eventDeliveryError
	if errors.As(err, &deliveryErr) {
		return deliveryErr.retryable
	}
	return true
}

func isDeadLetterEventDeliveryError(err error) bool {
	var deliveryErr *eventDeliveryError
	return errors.As(err, &deliveryErr) && deliveryErr.deadLetter
}

func isRetryableEventHTTPStatus(statusCode int) bool {
	switch {
	case statusCode == http.StatusRequestTimeout:
		return true
	case statusCode == http.StatusTooEarly:
		return true
	case statusCode == http.StatusTooManyRequests:
		return true
	case statusCode >= http.StatusInternalServerError:
		return true
	default:
		return false
	}
}

func fallbackRetryableEventHTTPStatus(statusCode int) bool {
	switch statusCode {
	case http.StatusUnauthorized, http.StatusForbidden, http.StatusBadRequest:
		return false
	case http.StatusNotFound, http.StatusConflict:
		return true
	default:
		return isRetryableEventHTTPStatus(statusCode)
	}
}

type callbackDecisionEnvelope struct {
	Decision       string `json:"decision"`
	Reason         string `json:"reason"`
	BackendEventID string `json:"backend_event_id"`
	SafeToDiscard  bool   `json:"safe_to_discard"`
	RetryAfterMS   int    `json:"retry_after_ms,omitempty"`
	ConflictCode   string `json:"conflict_code,omitempty"`
}

func normalizeCallbackDecision(raw string) string {
	return strings.ToLower(strings.TrimSpace(raw))
}

// HTTPEventEmitter sends execution events to the control plane via HTTP POST.
type HTTPEventEmitter struct {
	client           *http.Client
	callbackURL      string
	secret           string
	eventVerbosity   string
	engineInstanceID string
	sequenceMu       sync.Mutex
	sequences        map[string]int64

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
	spoolPath      string
	deadLetterPath string
	spoolMu        sync.Mutex
	flushMu        sync.Mutex
	spoolFlushCh   chan struct{}
	stopCh         chan struct{}
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

	// DeadLetterPath stores callback events rejected as invalid by the backend.
	DeadLetterPath string

	// SpoolFlushInterval controls how often the emitter retries spooled events.
	SpoolFlushInterval time.Duration
	// EventVerbosity controls which classes of events are emitted.
	EventVerbosity string
	// EngineInstanceID stamps every emitted event with the engine instance identity.
	EngineInstanceID string
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
	deadLetterPath := config.DeadLetterPath
	if deadLetterPath == "" {
		deadLetterPath = spoolPath + ".dead.jsonl"
	}

	emitter := &HTTPEventEmitter{
		client:             client,
		callbackURL:        config.CallbackURL,
		secret:             config.SignatureSecret,
		eventVerbosity:     normalizeEventVerbosity(config.EventVerbosity),
		engineInstanceID:   config.EngineInstanceID,
		sequences:          make(map[string]int64),
		eventChan:          make(chan *port.ExecutionEvent, bufferSize),
		maxRetries:         maxRetries,
		retryDelay:         retryDelay,
		spoolFlushInterval: spoolFlushInterval,
		spoolPath:          spoolPath,
		deadLetterPath:     deadLetterPath,
		spoolFlushCh:       make(chan struct{}, 1),
		stopCh:             make(chan struct{}),
	}

	// Start background worker for async events
	emitter.wg.Add(2)
	go emitter.worker()
	go emitter.spoolWorker()

	return emitter, nil
}

func normalizeEventVerbosity(raw string) string {
	switch strings.ToLower(strings.TrimSpace(raw)) {
	case "", "default":
		return "default"
	case "minimal":
		return "minimal"
	case "verbose":
		return "verbose"
	default:
		return "default"
	}
}

func eventAllowedForVerbosity(verbosity string, event *port.ExecutionEvent) bool {
	if event == nil {
		return false
	}
	switch normalizeEventVerbosity(verbosity) {
	case "minimal":
		return event.Category == port.EventCategoryState
	case "default", "verbose":
		return true
	default:
		return true
	}
}

func (e *HTTPEventEmitter) prepareEvent(event *port.ExecutionEvent) *port.ExecutionEvent {
	if event == nil {
		return nil
	}
	prepared := *event
	if strings.TrimSpace(prepared.EventID) == "" {
		prepared.EventID = uuid.NewString()
	}
	if prepared.Sequence <= 0 {
		prepared.Sequence = e.nextSequence(prepared.RunID)
	}
	if prepared.Category == "" {
		prepared.Category = port.EventCategory(port.InferEventCategory(prepared.Type))
	}
	if prepared.EngineInstanceID == "" && strings.TrimSpace(e.engineInstanceID) != "" {
		prepared.EngineInstanceID = strings.TrimSpace(e.engineInstanceID)
	}
	prepared.Input = cloneEventMap(event.Input)
	prepared.Output = cloneEventMap(event.Output)
	if strings.TrimSpace(prepared.IdempotencyKey) == "" {
		prepared.IdempotencyKey = buildEventIdempotencyKey(&prepared)
	}
	return &prepared
}

func (e *HTTPEventEmitter) nextSequence(runID string) int64 {
	e.sequenceMu.Lock()
	defer e.sequenceMu.Unlock()
	if e.sequences == nil {
		e.sequences = make(map[string]int64)
	}
	key := strings.TrimSpace(runID)
	if key == "" {
		key = "__unknown_run__"
	}
	e.sequences[key]++
	return e.sequences[key]
}

func cloneEventMap(input map[string]any) map[string]any {
	if len(input) == 0 {
		return nil
	}
	cloned := make(map[string]any, len(input))
	for key, value := range input {
		cloned[key] = cloneEventValue(value)
	}
	return cloned
}

func cloneEventValue(value any) any {
	switch typed := value.(type) {
	case map[string]any:
		return cloneEventMap(typed)
	case []any:
		cloned := make([]any, len(typed))
		for index, item := range typed {
			cloned[index] = cloneEventValue(item)
		}
		return cloned
	default:
		return value
	}
}

// Emit sends an event to the control plane synchronously
func (e *HTTPEventEmitter) Emit(ctx context.Context, event *port.ExecutionEvent) error {
	if e.callbackURL == "" {
		return ErrEventCallbackNotConfigured
	}
	event = e.prepareEvent(event)
	if !eventAllowedForVerbosity(e.eventVerbosity, event) {
		return nil
	}

	return e.sendWithRetry(ctx, event, true)
}

// EmitAsync queues an event for asynchronous delivery
func (e *HTTPEventEmitter) EmitAsync(event *port.ExecutionEvent) {
	if event == nil {
		return
	}
	event = e.prepareEvent(event)
	if !eventAllowedForVerbosity(e.eventVerbosity, event) {
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
		retryable := isRetryableEventDeliveryError(err)
		if attempt > 1 {
			metrics.RecordEventDeliveryRetry(event.Type.String())
		}

		if !retryable {
			metrics.RecordEventDeliveryFailure(event.Type.String())
			if spoolOnFailure && isDeadLetterEventDeliveryError(err) {
				if deadLetterErr := e.appendToDeadLetter(event, err.Error()); deadLetterErr != nil {
					return fmt.Errorf("event rejected and could not be dead-lettered: %w", deadLetterErr)
				}
			}
			return err
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
	body, err := json.Marshal(toCanonicalEventEnvelope(event))
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

	responseBody, readErr := io.ReadAll(io.LimitReader(resp.Body, 4096))
	if readErr != nil {
		return &eventDeliveryError{
			err:       fmt.Errorf("server returned status %d (failed to read response body: %w)", resp.StatusCode, readErr),
			retryable: fallbackRetryableEventHTTPStatus(resp.StatusCode),
		}
	}

	decision, hasDecision := parseCallbackDecision(responseBody)
	if !hasDecision {
		bodyText := strings.TrimSpace(string(responseBody))
		if bodyText == "" {
			bodyText = "missing callback decision envelope"
		}
		retryable := true
		deadLetter := false
		if resp.StatusCode >= 400 {
			retryable = fallbackRetryableEventHTTPStatus(resp.StatusCode)
			deadLetter = resp.StatusCode == http.StatusBadRequest
		}
		return &eventDeliveryError{
			err:        fmt.Errorf("server returned status %d without structured callback decision: %s", resp.StatusCode, bodyText),
			retryable:  retryable,
			deadLetter: deadLetter,
		}
	}

	return e.handleCallbackDecision(resp.StatusCode, decision, event, responseBody)
}

func parseCallbackDecision(responseBody []byte) (callbackDecisionEnvelope, bool) {
	var direct callbackDecisionEnvelope
	if err := json.Unmarshal(responseBody, &direct); err == nil && strings.TrimSpace(direct.Decision) != "" {
		return direct, true
	}

	var wrapped struct {
		Data callbackDecisionEnvelope `json:"data"`
	}
	if err := json.Unmarshal(responseBody, &wrapped); err == nil && strings.TrimSpace(wrapped.Data.Decision) != "" {
		return wrapped.Data, true
	}

	return callbackDecisionEnvelope{}, false
}

func (e *HTTPEventEmitter) handleCallbackDecision(
	statusCode int,
	decision callbackDecisionEnvelope,
	event *port.ExecutionEvent,
	responseBody []byte,
) error {
	normalizedDecision := normalizeCallbackDecision(decision.Decision)
	reason := strings.TrimSpace(decision.Reason)
	if reason == "" {
		reason = normalizedDecision
	}

	if statusCode == http.StatusUnauthorized || statusCode == http.StatusForbidden {
		return &eventDeliveryError{
			err:       fmt.Errorf("server returned authorization status %d: %s", statusCode, reason),
			retryable: false,
		}
	}

	if decision.ConflictCode != "" || statusCode == http.StatusConflict {
		conflictCode := strings.TrimSpace(decision.ConflictCode)
		if conflictCode == "" {
			conflictCode = "409_CONFLICT"
		}
		metrics.RecordEventConflict(conflictCode, event.Type.String())
	}

	switch normalizedDecision {
	case "accepted":
		if !decision.SafeToDiscard {
			return &eventDeliveryError{
				err:       fmt.Errorf("backend accepted event without safe_to_discard=true: %s", strings.TrimSpace(string(responseBody))),
				retryable: true,
			}
		}
		return nil
	case "duplicate":
		if !decision.SafeToDiscard {
			return &eventDeliveryError{
				err:       fmt.Errorf("backend duplicate response missing safe_to_discard=true: %s", strings.TrimSpace(string(responseBody))),
				retryable: true,
			}
		}
		metrics.RecordEventDiscarded("duplicate", event.Type.String())
		return nil
	case "stale_superseded":
		if !decision.SafeToDiscard {
			return &eventDeliveryError{
				err:       fmt.Errorf("backend stale response missing safe_to_discard=true: %s", strings.TrimSpace(string(responseBody))),
				retryable: true,
			}
		}
		metrics.RecordEventDiscarded("stale_superseded", event.Type.String())
		return nil
	case "retry_required":
		return &eventDeliveryError{
			err:       fmt.Errorf("backend requires retry for status %d: %s", statusCode, reason),
			retryable: true,
		}
	case "reject_invalid":
		if !decision.SafeToDiscard {
			return &eventDeliveryError{
				err:       fmt.Errorf("backend reject_invalid response missing safe_to_discard=true: %s", strings.TrimSpace(string(responseBody))),
				retryable: true,
			}
		}
		return &eventDeliveryError{
			err:        fmt.Errorf("backend rejected event as invalid for status %d: %s", statusCode, reason),
			retryable:  false,
			deadLetter: true,
		}
	default:
		return &eventDeliveryError{
			err:       fmt.Errorf("backend returned unknown callback decision %q for status %d", decision.Decision, statusCode),
			retryable: true,
		}
	}
}

func signPayload(secret string, timestamp string, body []byte) string {
	message := append([]byte(timestamp+"."), body...)
	mac := hmac.New(sha256.New, []byte(secret))
	mac.Write(message)
	return hex.EncodeToString(mac.Sum(nil))
}

func toCanonicalEventEnvelope(event *port.ExecutionEvent) map[string]any {
	if event == nil {
		return map[string]any{}
	}
	canonicalType := map[string]string{
		"run_started":            "run.started",
		"run_completed":          "run.completed",
		"run_failed":             "run.failed",
		"run_paused":             "run.paused",
		"run_resumed":            "run.resumed",
		"run_canceled":           "run.canceled",
		"run.schema_validation":  "run.schema_validation",
		"node_started":           "node.started",
		"node_completed":         "node.completed",
		"node_failed":            "node.failed",
		"node_skipped":           "node.skipped",
		"node_retrying":          "node.retrying",
		"node_stream_chunk":      "node.stream_chunk",
		"memory_write_requested": "memory.write_requested",
		"memory_fact_extracted":  "memory.fact_extracted",
		"summary_created":        "summary.created",
	}[event.Type.String()]
	if canonicalType == "" {
		canonicalType = event.Type.String()
	}
	tenantID := strings.TrimSpace(event.TenantID)
	payload := canonicalEventPayload(event)
	envelope := map[string]any{
		"event_id":        event.EventID,
		"idempotency_key": event.IdempotencyKey,
		"tenant_id":       tenantID,
		"org_id":          tenantID,
		"run_id":          event.RunID,
		"agent_id":        nil,
		"task_id":         nullableString(event.NodeID),
		"source":          "engine",
		"type":            canonicalType,
		"sequence":        event.Sequence,
		"causation_id":    nil,
		"correlation_id":  event.RunID,
		"occurred_at":     time.UnixMilli(event.Timestamp).UTC().Format(time.RFC3339Nano),
		"schema_version":  2,
		"payload":         payload,
	}
	envelope["checksum"] = checksumCanonicalEnvelope(envelope)
	return envelope
}

func canonicalEventPayload(event *port.ExecutionEvent) map[string]any {
	payload := map[string]any{
		"version":            event.Version,
		"category":           string(event.Category),
		"timestamp":          event.Timestamp,
		"engine_instance_id": event.EngineInstanceID,
	}
	if strings.TrimSpace(event.NodeID) != "" {
		payload["node_id"] = event.NodeID
	}
	if strings.TrimSpace(event.NodeType) != "" {
		payload["node_type"] = event.NodeType
	}
	if strings.TrimSpace(event.NodeName) != "" {
		payload["node_name"] = event.NodeName
	}
	if event.Attempt > 0 {
		payload["attempt"] = event.Attempt
	}
	if strings.TrimSpace(event.AttemptID) != "" {
		payload["attempt_id"] = event.AttemptID
	}
	if len(event.Input) > 0 {
		payload["input"] = event.Input
	}
	if isBackendMemoryIntentEvent(event.Type) && len(event.Output) > 0 {
		for key, value := range event.Output {
			payload[key] = value
		}
	} else if len(event.Output) > 0 {
		payload["output"] = event.Output
	}
	if strings.TrimSpace(event.Error) != "" {
		payload["error"] = event.Error
	}
	if event.DurationMs > 0 {
		payload["duration_ms"] = event.DurationMs
	}
	if strings.TrimSpace(event.Traceparent) != "" {
		payload["traceparent"] = event.Traceparent
	}
	if strings.TrimSpace(event.Tracestate) != "" {
		payload["tracestate"] = event.Tracestate
	}
	if strings.TrimSpace(event.TraceID) != "" {
		payload["trace_id"] = event.TraceID
	}
	if strings.TrimSpace(event.SpanID) != "" {
		payload["span_id"] = event.SpanID
	}
	return payload
}

func isBackendMemoryIntentEvent(eventType port.EventType) bool {
	switch eventType {
	case port.EventTypeMemoryWriteRequested, port.EventTypeMemoryFactExtracted, port.EventTypeSummaryCreated:
		return true
	default:
		return false
	}
}

func buildEventIdempotencyKey(event *port.ExecutionEvent) string {
	tenantID := strings.TrimSpace(event.TenantID)
	if tenantID == "" {
		tenantID = "unknown-tenant"
	}
	runID := strings.TrimSpace(event.RunID)
	if runID == "" {
		runID = "unknown-run"
	}
	hashInput, _ := marshalCanonicalJSON(canonicalEventPayload(event))
	sum := sha256.Sum256(hashInput)
	return fmt.Sprintf("%s/%s/engine/%d/%s", tenantID, runID, event.Sequence, hex.EncodeToString(sum[:8]))
}

func checksumCanonicalEnvelope(envelope map[string]any) string {
	copyWithoutChecksum := make(map[string]any, len(envelope))
	for key, value := range envelope {
		if key == "checksum" {
			continue
		}
		copyWithoutChecksum[key] = value
	}
	body, _ := marshalCanonicalJSON(copyWithoutChecksum)
	sum := sha256.Sum256(body)
	return hex.EncodeToString(sum[:])
}

func marshalCanonicalJSON(value any) ([]byte, error) {
	var buffer bytes.Buffer
	encoder := json.NewEncoder(&buffer)
	encoder.SetEscapeHTML(false)
	if err := encoder.Encode(value); err != nil {
		return nil, err
	}
	return bytes.TrimSpace(buffer.Bytes()), nil
}

func nullableString(value string) any {
	value = strings.TrimSpace(value)
	if value == "" {
		return nil
	}
	return value
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

func (e *HTTPEventEmitter) appendToDeadLetter(event *port.ExecutionEvent, reason string) error {
	if e.deadLetterPath == "" {
		return errors.New("event dead-letter path is not configured")
	}

	e.spoolMu.Lock()
	defer e.spoolMu.Unlock()

	if err := os.MkdirAll(filepath.Dir(e.deadLetterPath), 0o755); err != nil {
		log.Printf("Warning: failed to create event dead-letter directory: %v", err)
		return err
	}

	file, err := os.OpenFile(e.deadLetterPath, os.O_CREATE|os.O_WRONLY|os.O_APPEND, 0o600)
	if err != nil {
		log.Printf("Warning: failed to open event dead-letter file: %v", err)
		return err
	}
	defer file.Close()

	payload, err := json.Marshal(map[string]any{
		"dead_lettered_at": time.Now().UTC().Format(time.RFC3339Nano),
		"reason":           reason,
		"event":            event,
	})
	if err != nil {
		log.Printf("Warning: failed to marshal event for dead-letter: %v", err)
		return err
	}

	if _, err := file.Write(append(payload, '\n')); err != nil {
		log.Printf("Warning: failed to write event to dead-letter file: %v", err)
		return err
	}
	if err := file.Sync(); err != nil {
		log.Printf("Warning: failed to fsync event dead-letter file: %v", err)
		return err
	}

	metrics.RecordEventDiscarded("dead_letter", event.Type.String())
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
			if shouldRequeueSpooledEvent(err) {
				remaining = append(remaining, line)
				continue
			}
			if isDeadLetterEventDeliveryError(err) {
				if deadLetterErr := e.appendToDeadLetter(&event, err.Error()); deadLetterErr != nil {
					log.Printf(
						"Warning: failed to dead-letter spooled event: run_id=%s event_id=%s err=%v",
						event.RunID,
						event.EventID,
						deadLetterErr,
					)
					remaining = append(remaining, line)
					continue
				}
				log.Printf(
					"Warning: dead-lettered invalid spooled event: run_id=%s event_id=%s err=%v",
					event.RunID,
					event.EventID,
					err,
				)
				continue
			}
			log.Printf(
				"Warning: dropping non-retryable spooled event: run_id=%s event_id=%s err=%v",
				event.RunID,
				event.EventID,
				err,
			)
			continue
		}
		metrics.RecordEventReplayed(event.Type.String())
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

func shouldRequeueSpooledEvent(err error) bool {
	if err == nil {
		return false
	}
	if errors.Is(err, context.Canceled) || errors.Is(err, context.DeadlineExceeded) {
		return true
	}
	return isRetryableEventDeliveryError(err)
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
