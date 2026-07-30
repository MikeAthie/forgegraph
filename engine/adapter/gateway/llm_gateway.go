package gateway

import (
	"context"
	"errors"
	"fmt"
	"log/slog"
	"math"
	"os"
	"strconv"
	"strings"
	"sync"
	"sync/atomic"
	"time"

	"github.com/forgegraph/engine/adapter/executor"
	"github.com/forgegraph/engine/application/port"
	"github.com/forgegraph/engine/domain"
	"github.com/forgegraph/engine/infrastructure/metrics"
)

const (
	LLMStatusSuccess = "success"
	LLMStatusFailed  = "failed"

	LLMModeManaged = "managed"
	LLMModeBYOK    = "byok"

	LLMErrorTimeout            = "timeout"
	LLMErrorRateLimit          = "rate_limit"
	LLMErrorUnavailable        = "unavailable"
	LLMErrorInternal           = "internal"
	LLMErrorInvalidResponse    = "invalid_response"
	LLMErrorInvalidCredentials = "invalid_credentials"
)

// LLMClient is the single gateway interface for all LLM calls.
type LLMClient interface {
	Generate(ctx context.Context, req LLMRequest) (LLMResponse, error)
}

type llmProvider interface {
	LLMClient
	ProviderName() string
}

// LLMRequest is the gateway request shape. It preserves the existing executor
// request fields so changing the call path does not change prompts or models.
type LLMRequest struct {
	Prompt           string            `json:"prompt"`
	MaxTokens        int               `json:"max_tokens"`
	Temperature      float64           `json:"temperature"`
	Metadata         map[string]string `json:"metadata,omitempty"`
	LLMMode          string            `json:"llm_mode,omitempty"`
	CredentialSource string            `json:"credential_source,omitempty"`
	Provider         string            `json:"provider,omitempty"`
	Model            string            `json:"model,omitempty"`
	SystemPrompt     string            `json:"system_prompt,omitempty"`
	Messages         []executor.LLMMessage
	CredentialID     string
	TenantID         string
	APIKey           string

	Tools            []executor.ToolSpec
	ToolChoice       string
	StructuredOutput *executor.StructuredOutputSpec

	OnChunk func(string) `json:"-"`
}

// LLMResponse is the standardized gateway response envelope.
type LLMResponse struct {
	Status           string                 `json:"status"`
	Content          string                 `json:"content"`
	Provider         string                 `json:"provider"`
	LLMMode          string                 `json:"llm_mode"`
	CredentialSource string                 `json:"credential_source"`
	LatencyMS        int64                  `json:"latency_ms"`
	FallbackUsed     bool                   `json:"fallback_used"`
	ErrorType        string                 `json:"error_type,omitempty"`
	Model            string                 `json:"model,omitempty"`
	Usage            *executor.LLMUsage     `json:"usage,omitempty"`
	FinishReason     string                 `json:"finish_reason,omitempty"`
	ToolCalls        []executor.LLMToolCall `json:"tool_calls,omitempty"`
	StructuredData   any                    `json:"structured_data,omitempty"`
}

type LLMError struct {
	Type         string
	Provider     string
	Code         string
	Message      string
	RetryAfterMs int
	Err          error
	Details      map[string]any
}

func (e *LLMError) Error() string {
	message := e.Message
	if message == "" {
		message = "llm gateway error"
	}
	if e.Type != "" {
		message = fmt.Sprintf("%s %s", message, e.Type)
	}
	if e.Err != nil {
		return fmt.Sprintf("%s: %v", message, e.Err)
	}
	return message
}

func (e *LLMError) Unwrap() error {
	return e.Err
}

func (e *LLMError) retryable() bool {
	switch e.Type {
	case LLMErrorTimeout, LLMErrorRateLimit, LLMErrorUnavailable:
		return true
	default:
		return false
	}
}

type LLMGatewayConfig struct {
	MaxConcurrent               int
	MaxQueueSize                int
	QueueTimeout                time.Duration
	RequestTimeout              time.Duration
	CircuitFailureRateThreshold float64
	CircuitMinRequests          int
	CircuitWindowSize           int
	CircuitCooldown             time.Duration
}

type LLMMetricsSnapshot struct {
	LLMRequests        int64            `json:"llm_requests"`
	LLMFailures        int64            `json:"llm_failures"`
	AvgLatency         float64          `json:"avg_latency"`
	AvgLatencyMS       float64          `json:"avg_latency_ms"`
	QueueDepth         int64            `json:"queue_depth"`
	FallbackCount      int64            `json:"fallback_count"`
	CircuitOpen        bool             `json:"circuit_open"`
	CircuitOpenUntil   string           `json:"circuit_open_until,omitempty"`
	RequestsByMode     map[string]int64 `json:"requests_by_mode"`
	RequestsByProvider map[string]int64 `json:"requests_by_provider"`
	FailuresByMode     map[string]int64 `json:"failures_by_mode"`
}

type llmGatewayMetrics struct {
	requests           atomic.Int64
	failures           atomic.Int64
	totalLatencyMs     atomic.Int64
	queueDepth         atomic.Int64
	fallbackCount      atomic.Int64
	managedRequests    atomic.Int64
	byokRequests       atomic.Int64
	mu                 sync.Mutex
	requestsByProvider map[string]int64
	failuresByMode     map[string]int64
}

type LLMGateway struct {
	primary  llmProvider
	fallback llmProvider
	cfg      LLMGatewayConfig
	tokens   chan struct{}
	queued   atomic.Int64
	metrics  llmGatewayMetrics
	circuit  *llmCircuitBreaker
}

func NewLLMGatewayFromEnv(primary llmProvider, fallback llmProvider) *LLMGateway {
	return NewLLMGateway(primary, fallback, LoadLLMGatewayConfigFromEnv())
}

func NewLLMGateway(primary llmProvider, fallback llmProvider, cfg LLMGatewayConfig) *LLMGateway {
	if cfg.CircuitWindowSize <= 0 {
		cfg.CircuitWindowSize = 20
	}
	if cfg.CircuitMinRequests <= 0 {
		cfg.CircuitMinRequests = cfg.CircuitWindowSize
	}
	if cfg.CircuitMinRequests > cfg.CircuitWindowSize {
		cfg.CircuitMinRequests = cfg.CircuitWindowSize
	}

	g := &LLMGateway{
		primary:  primary,
		fallback: fallback,
		cfg:      cfg,
		metrics: llmGatewayMetrics{
			requestsByProvider: map[string]int64{},
			failuresByMode:     map[string]int64{},
		},
		circuit: newLLMCircuitBreaker(cfg),
	}
	if cfg.MaxConcurrent > 0 {
		g.tokens = make(chan struct{}, cfg.MaxConcurrent)
	}
	return g
}

func LoadLLMGatewayConfigFromEnv() LLMGatewayConfig {
	return LLMGatewayConfig{
		MaxConcurrent: getEnvIntWithAliases(4, "ENGINE_LLM_MAX_CONCURRENCY", "FORGEGRAPH_LLM_MAX_CONCURRENCY"),
		MaxQueueSize:  getEnvIntWithAliases(32, "ENGINE_LLM_MAX_QUEUE_SIZE", "FORGEGRAPH_LLM_MAX_QUEUE_SIZE"),
		QueueTimeout: time.Duration(
			getEnvIntWithAliases(5000, "ENGINE_LLM_QUEUE_TIMEOUT_MS", "FORGEGRAPH_LLM_QUEUE_TIMEOUT_MS"),
		) * time.Millisecond,
		RequestTimeout: time.Duration(
			getEnvIntWithAliases(45000, "ENGINE_LLM_REQUEST_TIMEOUT_MS", "FORGEGRAPH_LLM_REQUEST_TIMEOUT_MS"),
		) * time.Millisecond,
		CircuitFailureRateThreshold: getEnvFloatWithAliases(
			0.75,
			"ENGINE_LLM_CIRCUIT_FAILURE_RATE_THRESHOLD",
			"FORGEGRAPH_LLM_CIRCUIT_FAILURE_RATE_THRESHOLD",
		),
		CircuitMinRequests: getEnvIntWithAliases(
			20,
			"ENGINE_LLM_CIRCUIT_MIN_REQUESTS",
			"FORGEGRAPH_LLM_CIRCUIT_MIN_REQUESTS",
		),
		CircuitWindowSize: getEnvIntWithAliases(
			20,
			"ENGINE_LLM_CIRCUIT_WINDOW_SIZE",
			"FORGEGRAPH_LLM_CIRCUIT_WINDOW_SIZE",
		),
		CircuitCooldown: time.Duration(
			getEnvIntWithAliases(15000, "ENGINE_LLM_CIRCUIT_COOLDOWN_MS", "FORGEGRAPH_LLM_CIRCUIT_COOLDOWN_MS"),
		) * time.Millisecond,
	}
}

func (g *LLMGateway) Generate(ctx context.Context, req LLMRequest) (LLMResponse, error) {
	start := time.Now()
	req = normalizeGatewayLLMAccess(req)
	provider := effectiveRequestProvider(req, g.primary, "local")
	queueWait := time.Duration(0)
	if g.primary == nil {
		err := newLLMError(LLMErrorUnavailable, provider, "llm_gateway_primary_missing", "llm gateway primary provider missing", errors.New("primary provider is nil"), nil)
		response := failedLLMResponse(provider, time.Since(start), err)
		response = g.finalizeCall(req, response, queueWait)
		return response, err
	}
	if err := validateGatewayRequest(req, provider); err != nil {
		err.Provider = provider
		response := failedLLMResponse(provider, time.Since(start), err)
		response = g.finalizeCall(req, response, queueWait)
		return response, err
	}

	if err := g.circuit.beforeRequest(time.Now()); err != nil {
		normalized := normalizeProviderError(err, ctx, provider)
		if g.fallback != nil {
			fallbackCtx := ctx
			cancel := func() {}
			if g.cfg.RequestTimeout > 0 {
				fallbackCtx, cancel = context.WithTimeout(ctx, g.cfg.RequestTimeout)
			}
			defer cancel()
			return g.attemptFallback(fallbackCtx, req, provider, normalized, start, queueWait)
		}
		response := failedLLMResponse(provider, time.Since(start), normalized)
		response = g.finalizeCall(req, response, queueWait)
		return response, normalized
	}

	release, wait, err := g.acquire(ctx, req, provider)
	queueWait = wait
	if err != nil {
		g.circuit.recordFailure(time.Now())
		normalized := normalizeProviderError(err, ctx, provider)
		response := failedLLMResponse(provider, time.Since(start), normalized)
		response = g.finalizeCall(req, response, queueWait)
		return response, normalized
	}
	defer release()

	callCtx := ctx
	cancel := func() {}
	if g.cfg.RequestTimeout > 0 {
		callCtx, cancel = context.WithTimeout(ctx, g.cfg.RequestTimeout)
	}
	defer cancel()

	response, primaryErr := g.primary.Generate(callCtx, req)
	if primaryErr == nil && response.Status != LLMStatusFailed {
		response.Status = LLMStatusSuccess
		if response.Provider == "" {
			response.Provider = provider
		}
		response.LatencyMS = int64(time.Since(start) / time.Millisecond)
		g.circuit.recordSuccess(time.Now())
		response = g.finalizeCall(req, response, queueWait)
		return response, nil
	}

	normalizedPrimary := normalizeProviderError(primaryErr, callCtx, provider)
	if response.ErrorType != "" {
		normalizedPrimary.Type = response.ErrorType
	}
	g.circuit.recordFailure(time.Now())

	if g.fallback != nil {
		return g.attemptFallback(callCtx, req, provider, normalizedPrimary, start, queueWait)
	}

	failed := failedLLMResponse(provider, time.Since(start), normalizedPrimary)
	failed = g.finalizeCall(req, failed, queueWait)
	return failed, normalizedPrimary
}

func (g *LLMGateway) attemptFallback(
	callCtx context.Context,
	req LLMRequest,
	provider string,
	normalizedPrimary *LLMError,
	start time.Time,
	queueWait time.Duration,
) (LLMResponse, error) {
	g.metrics.fallbackCount.Add(1)
	fallbackResponse, fallbackErr := g.fallback.Generate(callCtx, req)
	fallbackProvider := providerName(g.fallback, "fallback")
	if fallbackErr == nil && fallbackResponse.Status != LLMStatusFailed {
		fallbackResponse.Status = LLMStatusSuccess
		fallbackResponse.FallbackUsed = true
		if fallbackResponse.Provider == "" {
			fallbackResponse.Provider = fallbackProvider
		}
		fallbackResponse.LatencyMS = int64(time.Since(start) / time.Millisecond)
		metrics.RecordLLMFallback(fallbackProvider, LLMStatusSuccess)
		fallbackResponse = g.finalizeCall(req, fallbackResponse, queueWait)
		return fallbackResponse, nil
	}

	metrics.RecordLLMFallback(fallbackProvider, LLMStatusFailed)
	normalizedFallback := normalizeProviderError(fallbackErr, callCtx, fallbackProvider)
	if fallbackResponse.ErrorType != "" {
		normalizedFallback.Type = fallbackResponse.ErrorType
	}
	normalizedFallback.Details = mergeLLMDetails(
		normalizedFallback.Details,
		map[string]any{
			"primary_provider":   provider,
			"primary_error_type": normalizedPrimary.Type,
		},
	)
	response := failedLLMResponse(fallbackProvider, time.Since(start), normalizedFallback)
	response.FallbackUsed = true
	response = g.finalizeCall(req, response, queueWait)
	return response, normalizedFallback
}

func validateGatewayRequest(req LLMRequest, provider string) *LLMError {
	if req.LLMMode == LLMModeBYOK {
		if strings.TrimSpace(req.Provider) == "" {
			return newLLMError(
				LLMErrorUnavailable,
				provider,
				"llm_gateway_byok_provider_missing",
				"BYOK provider missing",
				fmt.Errorf("byok provider missing"),
				map[string]any{
					"run_id":   req.Metadata["run_id"],
					"node_id":  req.Metadata["node_id"],
					"llm_mode": req.LLMMode,
				},
			)
		}
		if strings.TrimSpace(req.APIKey) == "" {
			return newLLMError(
				LLMErrorInvalidCredentials,
				provider,
				"llm_gateway_byok_key_missing",
				"BYOK API key missing",
				fmt.Errorf("byok api key missing"),
				map[string]any{
					"run_id":   req.Metadata["run_id"],
					"node_id":  req.Metadata["node_id"],
					"llm_mode": req.LLMMode,
				},
			)
		}
		return nil
	}
	if strings.TrimSpace(provider) == "" || provider == "unknown" {
		return newLLMError(
			LLMErrorUnavailable,
			provider,
			"llm_gateway_managed_provider_missing",
			"managed LLM provider missing",
			fmt.Errorf("managed provider missing"),
			map[string]any{
				"run_id":   req.Metadata["run_id"],
				"node_id":  req.Metadata["node_id"],
				"llm_mode": req.LLMMode,
			},
		)
	}
	return nil
}

func (g *LLMGateway) finalizeCall(req LLMRequest, response LLMResponse, queueWait time.Duration) LLMResponse {
	response.LLMMode = normalizeLLMMode(firstNonEmpty(response.LLMMode, req.LLMMode))
	response.CredentialSource = normalizeCredentialSource(
		firstNonEmpty(response.CredentialSource, req.CredentialSource),
		response.LLMMode,
	)
	if strings.TrimSpace(response.Provider) == "" {
		response.Provider = effectiveRequestProvider(req, g.primary, "unknown")
	}
	if response.Status == "" {
		response.Status = LLMStatusFailed
	}
	g.recordFinal(response)
	g.logLLMCall(req, response, queueWait)
	return response
}

func (g *LLMGateway) logLLMCall(req LLMRequest, response LLMResponse, queueWait time.Duration) {
	errorType := response.ErrorType
	if errorType == "" {
		errorType = "none"
	}
	slog.Info(
		"llm_call",
		"event", "llm_call",
		"llm_mode", response.LLMMode,
		"provider", response.Provider,
		"credential_source", response.CredentialSource,
		"queue_wait_ms", int64(queueWait/time.Millisecond),
		"latency_ms", response.LatencyMS,
		"fallback_used", response.FallbackUsed,
		"error_type", errorType,
		"status", response.Status,
		"model", req.Model,
		"run_id", req.Metadata["run_id"],
		"node_id", req.Metadata["node_id"],
	)
}

func firstNonEmpty(values ...string) string {
	for _, value := range values {
		if strings.TrimSpace(value) != "" {
			return value
		}
	}
	return ""
}

func copyInt64Map(source map[string]int64) map[string]int64 {
	copied := make(map[string]int64, len(source))
	for key, value := range source {
		copied[key] = value
	}
	return copied
}

func (g *LLMGateway) acquire(ctx context.Context, req LLMRequest, provider string) (func(), time.Duration, error) {
	if g.tokens == nil {
		return func() {}, 0, nil
	}

	select {
	case g.tokens <- struct{}{}:
		return g.release, 0, nil
	default:
	}

	queueStart := time.Now()
	queued := g.queued.Add(1)
	g.metrics.queueDepth.Store(queued)
	metrics.RecordLLMQueueDepth(queued)
	if g.cfg.MaxQueueSize >= 0 && queued > int64(g.cfg.MaxQueueSize) {
		queued = g.queued.Add(-1)
		g.metrics.queueDepth.Store(queued)
		metrics.RecordLLMQueueDepth(queued)
		err := newLLMError(
			LLMErrorRateLimit,
			provider,
			"llm_gateway_queue_full",
			"llm gateway queue full",
			fmt.Errorf("llm queue full"),
			map[string]any{
				"max_queue_size": g.cfg.MaxQueueSize,
				"queued":         queued + 1,
				"run_id":         req.Metadata["run_id"],
				"node_id":        req.Metadata["node_id"],
				"llm_mode":       req.LLMMode,
			},
		)
		slog.Warn(
			"llm_gateway_queue_full",
			"provider", provider,
			"llm_mode", req.LLMMode,
			"model", req.Model,
			"max_queue_size", g.cfg.MaxQueueSize,
			"run_id", req.Metadata["run_id"],
			"node_id", req.Metadata["node_id"],
		)
		return nil, time.Since(queueStart), err
	}
	defer func() {
		queued := g.queued.Add(-1)
		g.metrics.queueDepth.Store(queued)
		metrics.RecordLLMQueueDepth(queued)
	}()

	timer := time.NewTimer(g.cfg.QueueTimeout)
	defer timer.Stop()

	select {
	case g.tokens <- struct{}{}:
		return g.release, time.Since(queueStart), nil
	case <-ctx.Done():
		return nil, time.Since(queueStart), newLLMError(
			LLMErrorTimeout,
			provider,
			"llm_gateway_queue_context_cancelled",
			"llm gateway queue interrupted",
			ctx.Err(),
			nil,
		)
	case <-timer.C:
		err := newLLMError(
			LLMErrorTimeout,
			provider,
			"llm_gateway_queue_timeout",
			"llm gateway queue timeout",
			fmt.Errorf("timed out waiting for llm capacity"),
			map[string]any{
				"queue_timeout_ms": int(g.cfg.QueueTimeout / time.Millisecond),
				"run_id":           req.Metadata["run_id"],
				"node_id":          req.Metadata["node_id"],
				"llm_mode":         req.LLMMode,
			},
		)
		slog.Warn(
			"llm_gateway_queue_timeout",
			"provider", provider,
			"llm_mode", req.LLMMode,
			"model", req.Model,
			"queue_timeout_ms", int(g.cfg.QueueTimeout/time.Millisecond),
			"run_id", req.Metadata["run_id"],
			"node_id", req.Metadata["node_id"],
		)
		return nil, time.Since(queueStart), err
	}
}

func (g *LLMGateway) release() {
	<-g.tokens
}

func (g *LLMGateway) recordFinal(response LLMResponse) {
	if response.Status == "" {
		response.Status = LLMStatusFailed
	}
	response.LLMMode = normalizeLLMMode(response.LLMMode)
	g.metrics.requests.Add(1)
	switch response.LLMMode {
	case LLMModeBYOK:
		g.metrics.byokRequests.Add(1)
	default:
		g.metrics.managedRequests.Add(1)
	}
	if response.Status == LLMStatusFailed {
		g.metrics.failures.Add(1)
	}
	g.metrics.totalLatencyMs.Add(response.LatencyMS)
	provider := strings.ToLower(strings.TrimSpace(response.Provider))
	if provider == "" {
		provider = "unknown"
	}
	g.metrics.mu.Lock()
	g.metrics.requestsByProvider[provider]++
	if response.Status == LLMStatusFailed {
		g.metrics.failuresByMode[response.LLMMode]++
	}
	g.metrics.mu.Unlock()
	errorType := response.ErrorType
	if errorType == "" {
		errorType = "none"
	}
	metrics.RecordLLMRequest(
		response.Provider,
		response.Status,
		errorType,
		response.FallbackUsed,
		time.Duration(response.LatencyMS)*time.Millisecond,
	)
}

func (g *LLMGateway) MetricsSnapshot() LLMMetricsSnapshot {
	requests := g.metrics.requests.Load()
	totalLatency := g.metrics.totalLatencyMs.Load()
	avg := 0.0
	if requests > 0 {
		avg = float64(totalLatency) / float64(requests)
	}
	open, openUntil := g.circuit.snapshot(time.Now())
	g.metrics.mu.Lock()
	requestsByProvider := copyInt64Map(g.metrics.requestsByProvider)
	failuresByMode := copyInt64Map(g.metrics.failuresByMode)
	g.metrics.mu.Unlock()
	snapshot := LLMMetricsSnapshot{
		LLMRequests:   requests,
		LLMFailures:   g.metrics.failures.Load(),
		AvgLatency:    avg,
		AvgLatencyMS:  avg,
		QueueDepth:    g.metrics.queueDepth.Load(),
		FallbackCount: g.metrics.fallbackCount.Load(),
		CircuitOpen:   open,
		RequestsByMode: map[string]int64{
			LLMModeManaged: g.metrics.managedRequests.Load(),
			LLMModeBYOK:    g.metrics.byokRequests.Load(),
		},
		RequestsByProvider: requestsByProvider,
		FailuresByMode:     failuresByMode,
	}
	if !openUntil.IsZero() {
		snapshot.CircuitOpenUntil = openUntil.UTC().Format(time.RFC3339Nano)
	}
	return snapshot
}

type llmCircuitBreaker struct {
	cfg       LLMGatewayConfig
	mu        sync.Mutex
	outcomes  []bool
	openUntil time.Time
	open      bool
}

func newLLMCircuitBreaker(cfg LLMGatewayConfig) *llmCircuitBreaker {
	return &llmCircuitBreaker{cfg: cfg}
}

func (b *llmCircuitBreaker) beforeRequest(now time.Time) error {
	b.mu.Lock()
	defer b.mu.Unlock()
	if !b.open {
		return nil
	}
	if !b.openUntil.IsZero() && now.After(b.openUntil) {
		b.open = false
		b.openUntil = time.Time{}
		metrics.RecordLLMCircuitState(false)
		slog.Info("llm_gateway_circuit_closed")
		return nil
	}
	return newLLMError(
		LLMErrorUnavailable,
		"local",
		"llm_gateway_circuit_open",
		"llm gateway circuit open",
		fmt.Errorf("llm gateway circuit open"),
		map[string]any{
			"cooldown_until": b.openUntil.UTC().Format(time.RFC3339Nano),
		},
	)
}

func (b *llmCircuitBreaker) recordSuccess(now time.Time) {
	b.record(now, false)
}

func (b *llmCircuitBreaker) recordFailure(now time.Time) {
	b.record(now, true)
}

func (b *llmCircuitBreaker) record(now time.Time, failed bool) {
	if b.cfg.CircuitFailureRateThreshold <= 0 || b.cfg.CircuitCooldown <= 0 {
		return
	}

	b.mu.Lock()
	defer b.mu.Unlock()
	if b.open {
		return
	}
	b.outcomes = append(b.outcomes, failed)
	if len(b.outcomes) > b.cfg.CircuitWindowSize {
		b.outcomes = b.outcomes[len(b.outcomes)-b.cfg.CircuitWindowSize:]
	}
	if len(b.outcomes) < b.cfg.CircuitMinRequests {
		return
	}

	failures := 0
	for _, outcome := range b.outcomes {
		if outcome {
			failures++
		}
	}
	rate := float64(failures) / float64(len(b.outcomes))
	if rate <= b.cfg.CircuitFailureRateThreshold {
		return
	}

	b.open = true
	b.openUntil = now.Add(b.cfg.CircuitCooldown)
	metrics.RecordLLMCircuitState(true)
	slog.Warn(
		"llm_gateway_circuit_opened",
		"failure_rate", math.Round(rate*1000)/1000,
		"threshold", b.cfg.CircuitFailureRateThreshold,
		"window_size", len(b.outcomes),
		"cooldown_ms", int(b.cfg.CircuitCooldown/time.Millisecond),
	)
}

func (b *llmCircuitBreaker) snapshot(now time.Time) (bool, time.Time) {
	b.mu.Lock()
	defer b.mu.Unlock()
	if b.open && !b.openUntil.IsZero() && now.After(b.openUntil) {
		return false, time.Time{}
	}
	return b.open, b.openUntil
}

func failedLLMResponse(provider string, latency time.Duration, err *LLMError) LLMResponse {
	errorType := LLMErrorInternal
	if err != nil && err.Type != "" {
		errorType = err.Type
	}
	return LLMResponse{
		Status:    LLMStatusFailed,
		Provider:  provider,
		LatencyMS: int64(latency / time.Millisecond),
		ErrorType: errorType,
	}
}

func normalizeProviderError(err error, ctx context.Context, provider string) *LLMError {
	if err == nil {
		err = fmt.Errorf("llm provider returned failed response")
	}
	var llmErr *LLMError
	if errors.As(err, &llmErr) {
		return llmErr
	}
	errorType := NormalizeLLMError(err, ctx)
	code := "llm_gateway_" + errorType
	if retryCode := domain.RetryCodeFromError(err); retryCode != "" {
		code = retryCode
	}
	return newLLMError(errorType, provider, code, "llm gateway provider failure", err, retryDetails(err))
}

func NormalizeLLMError(err error, ctx context.Context) string {
	if err == nil {
		return LLMErrorInternal
	}
	if ctx != nil && errors.Is(ctx.Err(), context.DeadlineExceeded) {
		return LLMErrorTimeout
	}
	if errors.Is(err, context.DeadlineExceeded) || errors.Is(err, context.Canceled) {
		return LLMErrorTimeout
	}
	code := strings.ToLower(strings.TrimSpace(domain.RetryCodeFromError(err)))
	switch code {
	case "rate_limited", "llm_gateway_queue_full", "llm_backpressure_queue_full":
		return LLMErrorRateLimit
	case "invalid_credentials", "authentication_error", "unauthorized":
		return LLMErrorInvalidCredentials
	case "llm_gateway_queue_timeout", "llm_gateway_request_timeout", "llm_chaos_timeout", "llm_backpressure_queue_timeout", "llm_backpressure_request_timeout":
		return LLMErrorTimeout
	case "network_error", "transient_http_5xx", "llm_chaos_unavailable", "llm_gateway_circuit_open":
		return LLMErrorUnavailable
	}

	normalized := strings.ToLower(err.Error())
	switch {
	case strings.Contains(normalized, "status 401"),
		strings.Contains(normalized, "status code: 401"),
		strings.Contains(normalized, "http 401"),
		strings.Contains(normalized, "401 unauthorized"),
		strings.Contains(normalized, "unauthorized"),
		strings.Contains(normalized, "invalid api key"),
		strings.Contains(normalized, "invalid_api_key"),
		strings.Contains(normalized, "authentication"):
		return LLMErrorInvalidCredentials
	case strings.Contains(normalized, "timeout"),
		strings.Contains(normalized, "deadline exceeded"),
		strings.Contains(normalized, "timed out"):
		return LLMErrorTimeout
	case strings.Contains(normalized, "rate limit"),
		strings.Contains(normalized, "429"),
		strings.Contains(normalized, "too many requests"),
		strings.Contains(normalized, "queue full"):
		return LLMErrorRateLimit
	case strings.Contains(normalized, "connection refused"),
		strings.Contains(normalized, "connection reset"),
		strings.Contains(normalized, "temporarily unavailable"),
		strings.Contains(normalized, "unavailable"),
		strings.Contains(normalized, "upstream server error"),
		strings.Contains(normalized, "network"):
		return LLMErrorUnavailable
	case strings.Contains(normalized, "parse response"),
		strings.Contains(normalized, "decode response"),
		strings.Contains(normalized, "no choices"),
		strings.Contains(normalized, "invalid response"):
		return LLMErrorInvalidResponse
	default:
		return LLMErrorInternal
	}
}

func newLLMError(errorType, provider, code, message string, err error, details map[string]any) *LLMError {
	if errorType == "" {
		errorType = LLMErrorInternal
	}
	if provider == "" {
		provider = "unknown"
	}
	if code == "" {
		code = "llm_gateway_" + errorType
	}
	return &LLMError{
		Type:         errorType,
		Provider:     provider,
		Code:         code,
		Message:      message,
		RetryAfterMs: domain.RetryAfterMsFromError(err),
		Err:          err,
		Details:      details,
	}
}

func retryDetails(err error) map[string]any {
	details := domain.RetryDetailsFromError(err)
	if len(details) == 0 {
		return nil
	}
	return details
}

func mergeLLMDetails(base map[string]any, extra map[string]any) map[string]any {
	merged := make(map[string]any, len(base)+len(extra))
	for key, value := range base {
		merged[key] = value
	}
	for key, value := range extra {
		merged[key] = value
	}
	return merged
}

func normalizeGatewayLLMAccess(req LLMRequest) LLMRequest {
	mode := normalizeLLMMode(req.LLMMode)
	if req.Metadata != nil {
		if rawMode := strings.TrimSpace(req.Metadata["llm_mode"]); rawMode != "" {
			mode = normalizeLLMMode(rawMode)
		}
	}
	metadata := make(map[string]string, len(req.Metadata)+2)
	for key, value := range req.Metadata {
		metadata[key] = value
	}
	req.Metadata = metadata
	credentialSource := normalizeCredentialSource(req.CredentialSource, mode)
	if rawSource := strings.TrimSpace(req.Metadata["credential_source"]); rawSource != "" {
		credentialSource = normalizeCredentialSource(rawSource, mode)
	}
	req.LLMMode = mode
	req.CredentialSource = credentialSource
	req.Metadata["llm_mode"] = mode
	req.Metadata["credential_source"] = credentialSource
	if req.Provider == "" && req.CredentialID == "" {
		req.Provider = "openai"
	}
	return req
}

func normalizeLLMMode(mode string) string {
	switch strings.ToLower(strings.TrimSpace(mode)) {
	case LLMModeBYOK:
		return LLMModeBYOK
	default:
		return LLMModeManaged
	}
}

func normalizeCredentialSource(source string, mode string) string {
	source = strings.ToLower(strings.TrimSpace(source))
	switch source {
	case LLMModeBYOK:
		return LLMModeBYOK
	case LLMModeManaged:
		return LLMModeManaged
	default:
		if normalizeLLMMode(mode) == LLMModeBYOK {
			return LLMModeBYOK
		}
		return LLMModeManaged
	}
}

func effectiveRequestProvider(req LLMRequest, provider llmProvider, fallback string) string {
	if requestProvider := strings.ToLower(strings.TrimSpace(req.Provider)); requestProvider != "" {
		return requestProvider
	}
	return providerName(provider, fallback)
}

func providerName(provider llmProvider, fallback string) string {
	if provider == nil {
		return fallback
	}
	name := strings.TrimSpace(provider.ProviderName())
	if name == "" {
		return fallback
	}
	return name
}

func getEnvFloatWithAliases(defaultValue float64, keys ...string) float64 {
	for _, key := range keys {
		raw := strings.TrimSpace(os.Getenv(key))
		if raw == "" {
			continue
		}
		value, err := strconv.ParseFloat(raw, 64)
		if err != nil {
			return defaultValue
		}
		return value
	}
	return defaultValue
}

func getEnvIntWithAliases(defaultValue int, keys ...string) int {
	for _, key := range keys {
		raw := strings.TrimSpace(os.Getenv(key))
		if raw == "" {
			continue
		}
		value, err := strconv.Atoi(raw)
		if err != nil {
			return defaultValue
		}
		return value
	}
	return defaultValue
}

func executorRequestFromGateway(req LLMRequest) *executor.LLMRequest {
	return &executor.LLMRequest{
		Prompt:           req.Prompt,
		Provider:         req.Provider,
		Model:            req.Model,
		Temperature:      req.Temperature,
		MaxTokens:        req.MaxTokens,
		SystemPrompt:     req.SystemPrompt,
		Messages:         req.Messages,
		CredentialID:     req.CredentialID,
		TenantID:         req.TenantID,
		APIKey:           req.APIKey,
		Tools:            req.Tools,
		ToolChoice:       req.ToolChoice,
		StructuredOutput: req.StructuredOutput,
		Metadata:         req.Metadata,
		LLMMode:          req.LLMMode,
		CredentialSource: req.CredentialSource,
	}
}

func gatewayRequestFromExecutor(ctx context.Context, request *executor.LLMRequest, onChunk func(string)) LLMRequest {
	if request == nil {
		return LLMRequest{OnChunk: onChunk}
	}
	metadata := map[string]string{}
	for key, value := range request.Metadata {
		metadata[key] = value
	}
	if _, ok := metadata["llm_mode"]; !ok && strings.TrimSpace(request.LLMMode) != "" {
		metadata["llm_mode"] = request.LLMMode
	}
	if _, ok := metadata["credential_source"]; !ok && strings.TrimSpace(request.CredentialSource) != "" {
		metadata["credential_source"] = request.CredentialSource
	}
	if runCtx := port.RunContextFrom(ctx); runCtx != nil {
		if _, ok := metadata["run_id"]; !ok && runCtx.RunID != "" {
			metadata["run_id"] = runCtx.RunID
		}
		access := runCtx.LLMAccess.Normalized()
		metadata["llm_mode"] = access.Mode
		metadata["credential_source"] = normalizeCredentialSource("", access.Mode)
		if access.CredentialID != "" {
			metadata["credential_id"] = access.CredentialID
		}
		if access.Mode == port.LLMModeBYOK {
			request.APIKey = access.APIKey
			request.CredentialID = ""
			if access.Provider != "" {
				request.Provider = access.Provider
			}
		} else if request.Provider == "" && access.Provider != "" {
			request.Provider = access.Provider
		}
	}
	llmMode := normalizeLLMMode(metadata["llm_mode"])
	credentialSource := normalizeCredentialSource(metadata["credential_source"], llmMode)
	if len(metadata) == 0 {
		metadata = nil
	}
	return LLMRequest{
		Prompt:           request.Prompt,
		Provider:         request.Provider,
		Model:            request.Model,
		Temperature:      request.Temperature,
		MaxTokens:        request.MaxTokens,
		SystemPrompt:     request.SystemPrompt,
		Messages:         request.Messages,
		CredentialID:     request.CredentialID,
		TenantID:         request.TenantID,
		APIKey:           request.APIKey,
		LLMMode:          llmMode,
		CredentialSource: credentialSource,
		Tools:            request.Tools,
		ToolChoice:       request.ToolChoice,
		StructuredOutput: request.StructuredOutput,
		Metadata:         metadata,
		OnChunk:          onChunk,
	}
}

// ExecutorLLMClient adapts the gateway Generate interface to existing executors.
type ExecutorLLMClient struct {
	gateway LLMClient
}

func NewExecutorLLMClient(gateway LLMClient) *ExecutorLLMClient {
	return &ExecutorLLMClient{gateway: gateway}
}

func (c *ExecutorLLMClient) Complete(ctx context.Context, request *executor.LLMRequest) (*executor.LLMResponse, error) {
	return c.complete(ctx, request, nil)
}

func (c *ExecutorLLMClient) StreamComplete(
	ctx context.Context,
	request *executor.LLMRequest,
	onChunk func(string),
) (*executor.LLMResponse, error) {
	return c.complete(ctx, request, onChunk)
}

func (c *ExecutorLLMClient) complete(
	ctx context.Context,
	request *executor.LLMRequest,
	onChunk func(string),
) (*executor.LLMResponse, error) {
	if c == nil || c.gateway == nil {
		return nil, fmt.Errorf("llm gateway is not configured")
	}
	response, err := c.gateway.Generate(ctx, gatewayRequestFromExecutor(ctx, request, onChunk))
	if err != nil {
		return nil, executorErrorFromGateway(err, response)
	}
	if response.Status == LLMStatusFailed {
		errType := response.ErrorType
		if errType == "" {
			errType = LLMErrorInternal
		}
		return nil, executorErrorFromGateway(
			newLLMError(errType, response.Provider, "llm_gateway_"+errType, "llm gateway request failed", nil, nil),
			response,
		)
	}
	return &executor.LLMResponse{
		Content:          response.Content,
		Model:            response.Model,
		Usage:            response.Usage,
		FinishReason:     response.FinishReason,
		ToolCalls:        response.ToolCalls,
		StructuredData:   response.StructuredData,
		Provider:         response.Provider,
		LatencyMS:        response.LatencyMS,
		FallbackUsed:     response.FallbackUsed,
		ErrorType:        response.ErrorType,
		LLMMode:          response.LLMMode,
		CredentialSource: response.CredentialSource,
	}, nil
}

func executorErrorFromGateway(err error, response LLMResponse) error {
	var llmErr *LLMError
	if !errors.As(err, &llmErr) {
		return err
	}
	details := mergeLLMDetails(llmErr.Details, map[string]any{
		"provider":          llmErr.Provider,
		"error_type":        llmErr.Type,
		"fallback_used":     response.FallbackUsed,
		"llm_mode":          normalizeLLMMode(response.LLMMode),
		"credential_source": normalizeCredentialSource(response.CredentialSource, response.LLMMode),
	})
	if llmErr.retryable() {
		return domain.NewRetryableErrorWithDetails(
			err,
			"llm gateway "+llmErr.Type,
			llmErr.Code,
			llmErr.RetryAfterMs,
			details,
		)
	}
	return err
}
