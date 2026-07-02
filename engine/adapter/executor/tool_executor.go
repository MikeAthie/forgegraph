package executor

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"io"
	"log"
	"net/http"
	"os"
	"strconv"
	"strings"
	"time"

	"github.com/forgegraph/engine/adapter/metrics"
	"github.com/forgegraph/engine/adapter/tool"
	"github.com/forgegraph/engine/application/port"
	"github.com/forgegraph/engine/domain"
	"github.com/forgegraph/engine/domain/entity"
	"github.com/forgegraph/engine/domain/service"
	"github.com/forgegraph/engine/domain/value"
)

type ResolvedToolCall struct {
	Name            string
	Version         string
	Input           map[string]interface{}
	Config          map[string]interface{}
	AttemptID       string
	CallID          string
	ToolExecutionID string
	IdempotencyKey  string
	SideEffectClass string
	Definition      *tool.Definition
}

type ToolExecutor struct {
	httpClient            *http.Client
	resolver              CredentialResolver
	runtimeMode           string
	registry              *tool.Registry
	legacyNodeAdapterMode string
}

const (
	LegacyNodeAdapterModeLegacy = "legacy"
	LegacyNodeAdapterModeStrict = "strict"
)

func NormalizeLegacyNodeAdapterMode(raw string) string {
	if strings.EqualFold(strings.TrimSpace(raw), LegacyNodeAdapterModeStrict) {
		return LegacyNodeAdapterModeStrict
	}
	return LegacyNodeAdapterModeLegacy
}

func NewToolExecutor() *ToolExecutor {
	return NewToolExecutorWithModes(nil, nil, tool.RuntimeModeSelfHosted, LegacyNodeAdapterModeLegacy)
}

func NewToolExecutorWithRuntimeMode(runtimeMode string) *ToolExecutor {
	return NewToolExecutorWithModes(nil, nil, runtimeMode, LegacyNodeAdapterModeLegacy)
}

func NewToolExecutorWithResolver(resolver CredentialResolver) *ToolExecutor {
	return NewToolExecutorWithModes(nil, resolver, tool.RuntimeModeSelfHosted, LegacyNodeAdapterModeLegacy)
}

func NewToolExecutorWithResolverAndRuntimeMode(registry *tool.Registry, resolver CredentialResolver, runtimeMode string) *ToolExecutor {
	return NewToolExecutorWithModes(registry, resolver, runtimeMode, LegacyNodeAdapterModeLegacy)
}

func NewToolExecutorWithModes(
	registry *tool.Registry,
	resolver CredentialResolver,
	runtimeMode string,
	legacyNodeAdapterMode string,
) *ToolExecutor {
	return &ToolExecutor{
		httpClient:            &http.Client{},
		resolver:              resolver,
		runtimeMode:           tool.NormalizeRuntimeMode(runtimeMode),
		registry:              registry,
		legacyNodeAdapterMode: NormalizeLegacyNodeAdapterMode(legacyNodeAdapterMode),
	}
}

func (e *ToolExecutor) NodeType() string {
	return string(value.NodeTypeTool)
}

func (e *ToolExecutor) Execute(ctx context.Context, node *entity.Node, _ *entity.State) (*port.NodeExecutionResult, error) {
	if node == nil {
		return port.NewErrorResult(domain.NewValidationError("tool", "tool node is required")), nil
	}
	metrics.RecordLegacyToolAdapterHit()
	if e.legacyNodeAdapterMode == LegacyNodeAdapterModeStrict {
		return port.NewErrorResult(
			domain.NewValidationError("tool", "node-based tool execution disabled"),
		), nil
	}
	if runCtx := port.RunContextFrom(ctx); runCtx != nil && runCtx.TrackToolCall != nil {
		if err := runCtx.TrackToolCall(); err != nil {
			return port.NewErrorResult(err), nil
		}
	}
	if e.registry == nil {
		return port.NewErrorResult(
			domain.NewValidationError("tool", "tool registry not configured"),
		), nil
	}

	call, err := e.buildToolCallFromNode(node, strings.TrimSpace(port.AttemptIDFrom(ctx)))
	if err != nil {
		return port.NewErrorResult(err), nil
	}
	if strings.TrimSpace(call.Version) == "" {
		return port.NewErrorResult(
			domain.NewValidationError("tool", "tool version required"),
		), nil
	}
	log.Printf("legacy_tool_adapter used: tool=%s version=%s", call.Name, call.Version)
	return e.ExecuteToolCall(ctx, call)
}

// LEGACY COMPATIBILITY ADAPTER
// WARNING: This path bypasses backend-prepared execution contracts.
// DO NOT extend. DO NOT add logic here.
// No new features may be implemented in Execute(ctx, node, state).
// All new behavior MUST go through ExecuteToolCall.
// Remove after full dispatch_graph_json migration.
func (e *ToolExecutor) buildToolCallFromNode(node *entity.Node, attemptID string) (ResolvedToolCall, error) {
	def, err := e.resolveToolForLegacy(node)
	if err != nil {
		return ResolvedToolCall{}, err
	}

	input := map[string]any{}
	if rawInput, ok := node.Config["input"]; ok && rawInput != nil {
		typed, ok := rawInput.(map[string]any)
		if !ok {
			return ResolvedToolCall{}, domain.NewValidationError(
				"input",
				"tool node input must be an object",
			)
		}
		input = typed
	}

	config := make(map[string]any, len(node.Config))
	for key, value := range node.Config {
		switch key {
		case "tool", "tool_name", "version", "input":
			continue
		default:
			config[key] = value
		}
	}

	callID := strings.TrimSpace(node.GetConfigString("call_id"))
	if callID == "" {
		callID = node.ID
	}

	return ResolvedToolCall{
		Name:            def.Name,
		Version:         def.Version,
		Input:           input,
		Config:          config,
		AttemptID:       attemptID,
		CallID:          callID,
		ToolExecutionID: strings.TrimSpace(node.GetConfigString("tool_execution_id")),
		IdempotencyKey:  strings.TrimSpace(node.GetConfigString("idempotency_key")),
		SideEffectClass: normalizeSideEffectClass(node.GetConfigString("side_effect_class")),
		Definition:      def,
	}, nil
}

func (e *ToolExecutor) resolveToolForLegacy(node *entity.Node) (*tool.Definition, error) {
	toolName := strings.TrimSpace(node.GetConfigString("tool"))
	if toolName == "" {
		toolName = strings.TrimSpace(node.GetConfigString("tool_name"))
	}
	if toolName == "" {
		return nil, domain.NewValidationError("tool", "tool node requires tool")
	}

	version := strings.TrimSpace(node.GetConfigString("version"))
	def, ok := e.registry.Resolve(toolName, version)
	if !ok || def == nil {
		return nil, domain.NewValidationError(
			"tool",
			fmt.Sprintf("tool definition not found: %s", toolName),
		)
	}
	if strings.TrimSpace(def.Version) == "" {
		return nil, domain.NewValidationError("tool", "tool version required")
	}
	return def, nil
}

func (e *ToolExecutor) ExecuteToolCall(
	ctx context.Context,
	call ResolvedToolCall,
) (*port.NodeExecutionResult, error) {

	log.Printf("tool_execute start: tool=%s version=%s call_id=%s attempt_id=%s tool_execution_id=%s side_effect_class=%s",
		call.Name, call.Version, call.CallID, call.AttemptID, call.ToolExecutionID, call.SideEffectClass)

	if call.Definition == nil {
		return port.NewErrorResult(
			domain.NewValidationError("tool", "tool definition missing (must be pre-resolved)"),
		), nil
	}

	def := call.Definition
	call.SideEffectClass = effectiveSideEffectClass(call.SideEffectClass, def)

	if strings.TrimSpace(call.ToolExecutionID) == "" || strings.TrimSpace(call.IdempotencyKey) == "" {
		log.Printf("tool_execution_identity_missing: tool=%s version=%s call_id=%s attempt_id=%s side_effect_class=non_idempotent",
			call.Name, call.Version, call.CallID, call.AttemptID)
		call.SideEffectClass = "non_idempotent"
	}
	if call.Config == nil {
		call.Config = map[string]any{}
	}
	if boolFromAny(call.Config["skip_tool_execution"]) {
		log.Printf("tool_execute skipped: tool=%s version=%s tool_execution_id=%s reason=backend_marked_succeeded",
			call.Name, call.Version, call.ToolExecutionID)
		return port.NewSuccessResult(map[string]any{
			"tool":              call.Name,
			"version":           call.Version,
			"tool_execution_id": call.ToolExecutionID,
			"idempotency_key":   call.IdempotencyKey,
			"skipped":           true,
			"skip_reason":       "tool_execution_already_succeeded",
		}), nil
	}
	delete(call.Config, "tool_execution_id")
	delete(call.Config, "idempotency_key")
	delete(call.Config, "side_effect_class")
	delete(call.Config, "skip_tool_execution")

	if strings.TrimSpace(call.Name) == "" {
		return port.NewErrorResult(
			domain.NewValidationError("tool", "tool name required"),
		), nil
	}

	if strings.TrimSpace(call.Version) == "" {
		return port.NewErrorResult(
			domain.NewValidationError("tool", "tool version required"),
		), nil
	}

	// 🔒 Enforce idempotency contract
	if !def.SideEffects.Idempotent {
		if strings.TrimSpace(call.CallID) == "" {
			return port.NewErrorResult(
				domain.NewValidationError("tool", "non-idempotent tool requires call_id"),
			), nil
		}
	}

	// ✅ Validate input
	if def.InputSchema != nil {
		validator, err := service.CompileSchema(def.InputSchema)
		if err != nil {
			return port.NewErrorResult(
				domain.NewValidationError("input_schema", err.Error()),
			), nil
		}
		if issues, err := validator.Validate(call.Input); err != nil {
			return port.NewErrorResult(
				domain.NewValidationError("input_schema", err.Error()),
			), nil
		} else if len(issues) > 0 {
			return port.NewErrorResult(
				domain.NewValidationError("input", fmt.Sprintf("invalid: %v", issues[0]["message"])),
			), nil
		}
	}

	// ✅ Validate config (already resolved by backend)
	if def.ConfigSchema != nil {
		validator, err := service.CompileSchema(def.ConfigSchema)
		if err != nil {
			return port.NewErrorResult(
				domain.NewValidationError("config_schema", err.Error()),
			), nil
		}
		if issues, err := validator.Validate(call.Config); err != nil {
			return port.NewErrorResult(
				domain.NewValidationError("config_schema", err.Error()),
			), nil
		} else if len(issues) > 0 {
			return port.NewErrorResult(
				domain.NewValidationError("config", fmt.Sprintf("invalid: %v", issues[0]["message"])),
			), nil
		}
	}

	payload := map[string]any{
		"input":  call.Input,
		"config": call.Config,
		"execution": map[string]any{
			"tool_execution_id": call.ToolExecutionID,
			"idempotency_key":   call.IdempotencyKey,
			"side_effect_class": call.SideEffectClass,
			"attempt_id":        call.AttemptID,
			"call_id":           call.CallID,
		},
	}

	execType := strings.ToLower(strings.TrimSpace(def.Execution.Type))
	if execType == "" {
		return port.NewErrorResult(
			domain.NewValidationError("execution.type", "execution.type is required"),
		), nil
	}

	switch execType {

	case "http":
		result, err := e.executeHTTPTool(ctx, def, payload, call)
		if err != nil {
			return port.NewErrorResult(err), nil
		}
		if err := validateToolOutput(def, result); err != nil {
			return port.NewErrorResult(err), nil
		}
		result = applyToolResultLimits(def, result)
		return port.NewSuccessResult(result), nil

	case "local":
		result, err := e.executeLocalTool(ctx, def, payload, call)
		if err != nil {
			return port.NewErrorResult(err), nil
		}
		if err := validateToolOutput(def, result); err != nil {
			return port.NewErrorResult(err), nil
		}
		result = applyToolResultLimits(def, result)
		return port.NewSuccessResult(result), nil

	default:
		return port.NewErrorResult(
			domain.NewValidationError("execution.type", "unsupported"),
		), nil
	}
}

func validateToolOutput(def *tool.Definition, result map[string]any) error {
	if def == nil || def.OutputSchema == nil {
		return nil
	}
	validator, err := service.CompileSchema(def.OutputSchema)
	if err != nil {
		return domain.NewValidationError("output_schema", err.Error())
	}
	issues, err := validator.Validate(result)
	if err != nil {
		return domain.NewValidationError("output_schema", err.Error())
	}
	if len(issues) > 0 {
		return domain.NewValidationError(
			"output_schema",
			fmt.Sprintf("tool output invalid: %v", issues[0]["message"]),
		)
	}
	return nil
}

func (e *ToolExecutor) executeHTTPTool(
	ctx context.Context,
	def *tool.Definition,
	payload map[string]any,
	call ResolvedToolCall,
) (map[string]any, error) {
	httpConfig := def.Execution.HTTP
	if httpConfig == nil {
		return nil, fmt.Errorf("tool missing execution.http configuration")
	}

	// Resolve credentials using the ToolCall-aware overload.
	provider, apiKey, err := e.resolveToolCredentialContext(ctx, call, def)
	if err != nil {
		return nil, err
	}

	toolConfig := call.Config

	templateValues := credentialTemplateValues(provider, apiKey)
	for k, v := range flattenToolConfigTemplateValues(toolConfig) {
		templateValues[k] = v
	}

	urlStr := os.ExpandEnv(httpConfig.URL)
	urlStr = SubstituteTemplateWithExtras(urlStr, nil, templateValues)
	if urlStr == "" {
		return nil, fmt.Errorf("tool URL not configured")
	}
	if !isHTTPAllowed(port.PolicyFromContext(ctx), urlStr) {
		return nil, newPolicyDeniedValidationError("url", "egress blocked by policy")
	}

	method := httpConfig.Method
	if method == "" {
		method = http.MethodPost
	}

	var bodyBytes []byte
	if method == http.MethodPost || method == http.MethodPut || method == http.MethodPatch {
		bodyBytes, err = json.Marshal(payload)
		if err != nil {
			return nil, err
		}
	}

	headers := map[string]string{}
	for k, v := range httpConfig.Headers {
		headers[k] = v
	}
	if h, ok := call.Config["headers"].(map[string]any); ok {
		for k, v := range h {
			headers[k] = fmt.Sprintf("%v", v)
		}
	}
	for k, v := range headers {
		headers[k] = SubstituteTemplateWithExtras(os.ExpandEnv(v), nil, templateValues)
	}
	if strings.TrimSpace(apiKey) != "" && strings.TrimSpace(headers["Authorization"]) == "" {
		headers["Authorization"] = "Bearer " + apiKey
	}

	timeoutMs := resolveToolTimeoutMs(toolConfig, def.Execution.TimeoutSeconds)
	retryAttempts := resolveToolRetryAttempts(toolConfig, def, call)
	retryBackoffMs := resolveToolRetryBackoffMs(toolConfig)
	throttleProvider := provider
	if throttleProvider == "" {
		throttleProvider = strings.TrimSpace(strings.ToLower(def.Name))
	}
	throttleMs := resolveTenantProviderThrottleMs(ctx, throttleProvider, toolConfig)

	var lastErr error
	for attempt := 1; attempt <= retryAttempts; attempt++ {
		if throttleMs > 0 {
			if throttleErr := throttleTenantProvider(ctx, port.TenantIDFrom(ctx), throttleProvider, throttleMs); throttleErr != nil {
				return nil, domain.NewRetryableErrorWithDetails(
					throttleErr,
					"tenant provider throttle interrupted",
					"tenant_throttle",
					0,
					map[string]any{
						"provider":         throttleProvider,
						"throttle_ms":      throttleMs,
						"tenant_throttled": true,
						"tool":             def.Name,
					},
				)
			}
		}

		attemptCtx, cancel := context.WithTimeout(ctx, time.Duration(timeoutMs)*time.Millisecond)

		var bodyReader io.Reader
		if len(bodyBytes) > 0 {
			bodyReader = bytes.NewReader(bodyBytes)
		}
		req, err := http.NewRequestWithContext(attemptCtx, method, urlStr, bodyReader)
		if err != nil {
			cancel()
			return nil, err
		}
		if len(bodyBytes) > 0 {
			req.Header.Set("Content-Type", "application/json")
		}
		for k, v := range headers {
			req.Header.Set(k, v)
		}
		req.Header.Set("X-ForgeGraph-Tool-Execution-ID", call.ToolExecutionID)
		req.Header.Set("X-ForgeGraph-Attempt-ID", call.AttemptID)
		if strings.TrimSpace(call.IdempotencyKey) != "" && def.SideEffects.Idempotent {
			req.Header.Set("Idempotency-Key", call.IdempotencyKey)
			req.Header.Set("X-Idempotency-Key", call.IdempotencyKey)
			log.Printf("tool_idempotency_applied: tool=%s tool_execution_id=%s idempotency_key=%s adapter=http",
				def.Name, call.ToolExecutionID, call.IdempotencyKey)
		} else {
			log.Printf("tool_idempotency_not_applied: tool=%s tool_execution_id=%s supported=%t has_key=%t adapter=http",
				def.Name, call.ToolExecutionID, def.SideEffects.Idempotent, strings.TrimSpace(call.IdempotencyKey) != "")
		}

		resp, err := e.httpClient.Do(req)
		if err != nil {
			cancel()
			if ctx.Err() != nil {
				return nil, ctx.Err()
			}
			if requestMayHaveReachedUpstream(method, len(bodyBytes)) {
				return nil, domain.NewAmbiguousExecutionError(
					err,
					"tool http outcome ambiguous after request send",
					"http_request_outcome_unknown",
					map[string]any{
						"tool":              def.Name,
						"tool_execution_id": call.ToolExecutionID,
						"idempotency_key":   call.IdempotencyKey,
						"attempt":           attempt,
					},
				)
			}
			lastErr = domain.NewRetryableErrorWithDetails(
				err,
				"tool http request failed",
				"network_error",
				0,
				map[string]any{
					"tool": def.Name,
				},
			)
			if attempt < retryAttempts {
				delayMs := computeProviderRetryDelayMs(retryBackoffMs, attempt, 0)
				if recordErr := port.RecordRetry(ctx, port.RetryRecord{
					OperationType:    "tool_http_request",
					AttemptNumber:    attempt + 1,
					MaxAttempts:      retryAttempts,
					RetryDelayMs:     delayMs,
					RetryReason:      "tool http request failed",
					LastError:        lastErr,
					RetryClass:       "transport",
					TerminalFallback: "return_retryable_error",
					Metadata: map[string]any{
						"tool":              def.Name,
						"tool_execution_id": call.ToolExecutionID,
						"idempotency_key":   call.IdempotencyKey,
					},
				}); recordErr != nil {
					return nil, recordErr
				}
				if backoffErr := sleepWithContext(ctx, delayMs); backoffErr != nil {
					return nil, backoffErr
				}
				continue
			}
			return nil, lastErr
		}

		body, err := io.ReadAll(resp.Body)
		resp.Body.Close()
		cancel()
		if err != nil {
			return nil, domain.NewAmbiguousExecutionError(
				err,
				"tool http outcome ambiguous while reading response",
				"http_response_read_unknown",
				map[string]any{
					"tool":              def.Name,
					"tool_execution_id": call.ToolExecutionID,
					"idempotency_key":   call.IdempotencyKey,
					"status_code":       resp.StatusCode,
					"attempt":           attempt,
				},
			)
		}
		var parsed any
		contentType := resp.Header.Get("Content-Type")
		if strings.Contains(contentType, "application/json") {
			if err := json.Unmarshal(body, &parsed); err != nil {
				parsed = string(body)
			}
		} else {
			parsed = string(body)
		}

		if resp.StatusCode == http.StatusTooManyRequests || resp.StatusCode >= 500 {
			bodyText := strings.TrimSpace(string(body))
			retryAfterMs := parseRetryAfterMs(resp.Header.Get("Retry-After"), time.Now())
			if resp.StatusCode == http.StatusTooManyRequests && isQuotaExhaustedRateLimit(bodyText) {
				return nil, fmt.Errorf(
					"rate limit quota exhausted (HTTP 429) for tool %s. Increase provider quota/billing and retry: %s",
					def.Name,
					bodyText,
				)
			}

			details := map[string]any{
				"status_code":    resp.StatusCode,
				"retry_after_ms": retryAfterMs,
				"tool":           def.Name,
			}
			code := "transient_http_5xx"
			if resp.StatusCode == http.StatusTooManyRequests {
				code = "rate_limited"
				details["rate_limit_type"] = "throttled"
			}

			lastErr = domain.NewRetryableErrorWithDetails(
				fmt.Errorf("HTTP %d: %s", resp.StatusCode, bodyText),
				"tool upstream unavailable",
				code,
				retryAfterMs,
				details,
			)
			if attempt < retryAttempts {
				delayMs := computeProviderRetryDelayMs(retryBackoffMs, attempt, retryAfterMs)
				if recordErr := port.RecordRetry(ctx, port.RetryRecord{
					OperationType:    "tool_upstream_http",
					AttemptNumber:    attempt + 1,
					MaxAttempts:      retryAttempts,
					RetryDelayMs:     delayMs,
					RetryReason:      "tool upstream returned retryable status",
					LastError:        lastErr,
					RetryClass:       "transport",
					TerminalFallback: "return_retryable_error",
					Metadata: map[string]any{
						"tool":              def.Name,
						"tool_execution_id": call.ToolExecutionID,
						"idempotency_key":   call.IdempotencyKey,
						"status_code":       resp.StatusCode,
						"retry_after_ms":    retryAfterMs,
					},
				}); recordErr != nil {
					return nil, recordErr
				}
				if backoffErr := sleepWithContext(ctx, delayMs); backoffErr != nil {
					return nil, backoffErr
				}
				continue
			}
			return nil, lastErr
		}
		if resp.StatusCode >= 400 {
			return nil, fmt.Errorf("HTTP %d: %s", resp.StatusCode, strings.TrimSpace(string(body)))
		}

		result := map[string]any{
			"tool":              def.Name,
			"version":           def.Version,
			"status":            resp.StatusCode,
			"result":            parsed,
			"attempts":          attempt,
			"call_id":           call.CallID,
			"attempt_id":        call.AttemptID,
			"tool_execution_id": call.ToolExecutionID,
			"idempotency_key":   call.IdempotencyKey,
		}
		log.Printf("tool_execute success: tool=%s attempts=%d call_id=%s tool_execution_id=%s", def.Name, attempt, call.CallID, call.ToolExecutionID)
		return result, nil
	}

	if lastErr != nil {
		return nil, lastErr
	}
	return nil, fmt.Errorf("tool request failed")
}

func (e *ToolExecutor) executeLocalTool(
	ctx context.Context,
	def *tool.Definition,
	payload map[string]any,
	call ResolvedToolCall,
) (map[string]any, error) {
	localConfig := def.Execution.Local
	if localConfig == nil {
		return nil, fmt.Errorf("tool missing execution.local configuration")
	}

	timeoutMs := resolveToolTimeoutMs(call.Config, def.Execution.TimeoutSeconds)
	attemptCtx, cancel := context.WithTimeout(ctx, time.Duration(timeoutMs)*time.Millisecond)
	defer cancel()

	handlerResult, err := executeBuiltinLocalHandler(attemptCtx, strings.TrimSpace(localConfig.Handler), payload)
	if err != nil {
		return nil, err
	}
	if strings.TrimSpace(call.IdempotencyKey) != "" && def.SideEffects.Idempotent {
		log.Printf("tool_idempotency_applied: tool=%s tool_execution_id=%s idempotency_key=%s adapter=local",
			def.Name, call.ToolExecutionID, call.IdempotencyKey)
	} else {
		log.Printf("tool_idempotency_not_applied: tool=%s tool_execution_id=%s supported=%t has_key=%t adapter=local",
			def.Name, call.ToolExecutionID, def.SideEffects.Idempotent, strings.TrimSpace(call.IdempotencyKey) != "")
	}

	result := map[string]any{
		"tool":              def.Name,
		"version":           def.Version,
		"result":            handlerResult,
		"attempts":          1,
		"call_id":           call.CallID,
		"attempt_id":        call.AttemptID,
		"tool_execution_id": call.ToolExecutionID,
		"idempotency_key":   call.IdempotencyKey,
	}
	log.Printf("tool_execute success: tool=%s attempts=1 call_id=%s tool_execution_id=%s", def.Name, call.CallID, call.ToolExecutionID)
	return result, nil
}

func executeBuiltinLocalHandler(ctx context.Context, handler string, payload map[string]any) (any, error) {
	select {
	case <-ctx.Done():
		return nil, ctx.Err()
	default:
	}

	switch strings.ToLower(strings.TrimSpace(handler)) {
	case "echo":
		return payload["input"], nil
	case "noop":
		return map[string]any{"ok": true}, nil
	default:
		return nil, fmt.Errorf("unsupported local handler: %s", handler)
	}
}

func (e *ToolExecutor) resolveToolCredentialContext(
	ctx context.Context,
	call ResolvedToolCall,
	def *tool.Definition,
) (string, string, error) {
	provider := strings.ToLower(strings.TrimSpace(def.Name))
	if p, ok := call.Config["provider"].(string); ok && strings.TrimSpace(p) != "" {
		provider = strings.ToLower(strings.TrimSpace(p))
	}

	credentialID, _ := call.Config["credential_id"].(string)
	credentialID = strings.TrimSpace(credentialID)
	if credentialID == "" {
		return provider, "", nil
	}

	if e.resolver == nil {
		return "", "", domain.NewValidationError("credential_id", "credential resolver not configured")
	}

	tenantID := strings.TrimSpace(port.TenantIDFrom(ctx))
	if tenantID == "" {
		return "", "", domain.NewValidationError("tenant_id", "tenant_id is required for credential resolution")
	}

	resolvedProvider, apiKey, err := e.resolver.Resolve(ctx, credentialID, tenantID)
	if err != nil {
		return "", "", domain.NewValidationError("credential_id", fmt.Sprintf("credential resolution failed: %v", err))
	}
	resolvedProvider = strings.ToLower(strings.TrimSpace(resolvedProvider))
	if provider == "" {
		provider = resolvedProvider
	} else if resolvedProvider != "" && provider != resolvedProvider {
		return "", "", domain.NewValidationError(
			"credential_id",
			fmt.Sprintf("credential provider mismatch: expected %s, got %s", provider, resolvedProvider),
		)
	}

	return provider, apiKey, nil
}

func flattenToolConfigTemplateValues(config map[string]any) map[string]string {
	values := map[string]string{}
	for k, v := range config {
		values["config."+k] = fmt.Sprintf("%v", v)
	}
	return values
}

func resolveToolTimeoutMs(toolConfig map[string]any, defaultTimeoutSeconds int) int {
	timeoutMs := readInt(toolConfig, "timeout_ms")
	if timeoutMs <= 0 && defaultTimeoutSeconds > 0 {
		timeoutMs = defaultTimeoutSeconds * 1000
	}
	if timeoutMs <= 0 {
		return 30000
	}
	return timeoutMs
}

func resolveToolRetryAttempts(toolConfig map[string]any, def *tool.Definition, call ResolvedToolCall) int {
	if def != nil && !def.SideEffects.Idempotent {
		return 1
	}
	if effectiveSideEffectClass(call.SideEffectClass, def) == "non_idempotent" || effectiveSideEffectClass(call.SideEffectClass, def) == "critical" {
		return 1
	}
	if strings.TrimSpace(call.ToolExecutionID) == "" || strings.TrimSpace(call.IdempotencyKey) == "" {
		return 1
	}
	retryAttempts := readInt(toolConfig, "retry_attempts")
	if retryAttempts <= 0 {
		return 1
	}
	return retryAttempts
}

func normalizeSideEffectClass(raw string) string {
	switch strings.ToLower(strings.TrimSpace(raw)) {
	case "pure", "idempotent", "non_idempotent", "critical":
		return strings.ToLower(strings.TrimSpace(raw))
	default:
		return ""
	}
}

func effectiveSideEffectClass(raw string, def *tool.Definition) string {
	normalized := normalizeSideEffectClass(raw)
	if normalized != "" {
		return normalized
	}
	if def != nil {
		if def.SideEffects.Type == "read" {
			return "pure"
		}
		if def.SideEffects.Idempotent {
			return "idempotent"
		}
	}
	return "non_idempotent"
}

func boolFromAny(raw any) bool {
	switch typed := raw.(type) {
	case bool:
		return typed
	case string:
		return strings.EqualFold(strings.TrimSpace(typed), "true") || strings.TrimSpace(typed) == "1"
	default:
		return false
	}
}

func requestMayHaveReachedUpstream(method string, bodyLen int) bool {
	normalized := strings.ToUpper(strings.TrimSpace(method))
	switch normalized {
	case http.MethodPost, http.MethodPut, http.MethodPatch, http.MethodDelete:
		return true
	default:
		return bodyLen > 0
	}
}

func resolveToolRetryBackoffMs(toolConfig map[string]any) int {
	backoffMs := readInt(toolConfig, "retry_backoff_ms")
	if backoffMs <= 0 {
		return 100
	}
	return backoffMs
}

func readInt(config map[string]any, key string) int {
	raw, ok := config[key]
	if !ok || raw == nil {
		return 0
	}
	switch typed := raw.(type) {
	case int:
		return typed
	case int64:
		return int(typed)
	case float64:
		return int(typed)
	case string:
		parsed, err := strconv.Atoi(strings.TrimSpace(typed))
		if err == nil {
			return parsed
		}
	}
	return 0
}

func sleepWithContext(ctx context.Context, backoffMs int) error {
	if backoffMs <= 0 {
		return nil
	}
	timer := time.NewTimer(time.Duration(backoffMs) * time.Millisecond)
	defer timer.Stop()
	select {
	case <-ctx.Done():
		return ctx.Err()
	case <-timer.C:
		return nil
	}
}
