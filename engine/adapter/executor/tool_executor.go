package executor

import (
	"bytes"
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"net/http"
	"os"
	"os/exec"
	"strconv"
	"strings"
	"time"

	"github.com/forgegraph/engine/adapter/tool"
	"github.com/forgegraph/engine/application/port"
	"github.com/forgegraph/engine/domain"
	"github.com/forgegraph/engine/domain/entity"
	"github.com/forgegraph/engine/domain/service"
	"github.com/forgegraph/engine/domain/value"
)

// ToolExecutor runs tools defined in the tool registry.
type ToolExecutor struct {
	registry   *tool.Registry
	httpClient *http.Client
}

// NewToolExecutor creates a tool executor with a registry.
func NewToolExecutor(registry *tool.Registry) *ToolExecutor {
	return &ToolExecutor{
		registry:   registry,
		httpClient: &http.Client{},
	}
}

// NodeType returns the node type this executor handles.
func (e *ToolExecutor) NodeType() string {
	return string(value.NodeTypeTool)
}

// Execute runs a tool by name/version.
//
// Config options:
//   - tool: string (required)
//   - version: string (optional, defaults to latest)
//   - input: any (optional)
//   - input_path: string (optional)
//   - input_template: string (optional)
//   - config: object (optional) tool-specific config overrides
//
// Output:
//   - tool, version, status/result/metadata
func (e *ToolExecutor) Execute(ctx context.Context, node *entity.Node, state *entity.State) (*port.NodeExecutionResult, error) {
	if e.registry == nil {
		return port.NewErrorResult(domain.NewValidationError("tool", "tool registry not configured")), nil
	}

	toolName := strings.TrimSpace(node.GetConfigString("tool"))
	if toolName == "" {
		toolName = strings.TrimSpace(node.GetConfigString("name"))
	}
	if toolName == "" {
		return port.NewErrorResult(domain.NewValidationError("tool", "tool node requires tool name")), nil
	}

	version := strings.TrimSpace(node.GetConfigString("version"))
	def, ok := e.registry.Resolve(toolName, version)
	if !ok {
		return port.NewErrorResult(domain.NewValidationError("tool", fmt.Sprintf("tool not found: %s@%s", toolName, version))), nil
	}

	input, err := resolveToolInput(node, state)
	if err != nil {
		return port.NewErrorResult(err), nil
	}

	toolConfig := map[string]any{}
	if def.DefaultConfig != nil {
		for k, v := range def.DefaultConfig {
			toolConfig[k] = v
		}
	}
	if overrides, ok := node.Config["config"].(map[string]any); ok {
		for k, v := range overrides {
			toolConfig[k] = v
		}
	}

	if def.ConfigSchema != nil {
		validator, err := service.CompileSchema(def.ConfigSchema)
		if err != nil {
			return port.NewErrorResult(domain.NewValidationError("config_schema", err.Error())), nil
		}
		if issues, err := validator.Validate(toolConfig); err != nil {
			return port.NewErrorResult(domain.NewValidationError("config_schema", err.Error())), nil
		} else if len(issues) > 0 {
			return port.NewErrorResult(domain.NewValidationError("config", fmt.Sprintf("tool config invalid: %v", issues[0]["message"]))), nil
		}
	}

	payload := map[string]any{
		"input":  input,
		"config": toolConfig,
	}

	switch strings.ToLower(def.Kind) {
	case "http":
		result, err := e.executeHTTPTool(ctx, def, payload, node, toolConfig)
		if err != nil {
			return port.NewErrorResult(err), nil
		}
		return port.NewSuccessResult(result), nil
	case "exec":
		result, err := e.executeExecTool(ctx, def, payload, node, toolConfig)
		if err != nil {
			return port.NewErrorResult(err), nil
		}
		return port.NewSuccessResult(result), nil
	default:
		return port.NewErrorResult(domain.NewValidationError("kind", "unsupported tool kind")), nil
	}
}

func (e *ToolExecutor) executeHTTPTool(
	ctx context.Context,
	def *tool.Definition,
	payload map[string]any,
	node *entity.Node,
	toolConfig map[string]any,
) (map[string]any, error) {
	if def.HTTP == nil {
		return nil, fmt.Errorf("tool missing http configuration")
	}

	urlStr := os.ExpandEnv(def.HTTP.URL)
	if urlStr == "" {
		return nil, fmt.Errorf("tool URL not configured")
	}
	if !isHTTPAllowed(port.PolicyFromContext(ctx), urlStr) {
		return nil, domain.NewValidationError("url", "tool egress blocked by policy")
	}

	method := def.HTTP.Method
	if method == "" {
		method = "POST"
	}

	bodyBytes, err := json.Marshal(payload)
	if err != nil {
		return nil, err
	}

	headers := map[string]string{}
	for k, v := range def.HTTP.Headers {
		headers[k] = v
	}
	if overrideHeaders, ok := node.Config["headers"].(map[string]any); ok {
		for k, v := range overrideHeaders {
			headers[k] = fmt.Sprintf("%v", v)
		}
	}
	for k, v := range headers {
		headers[k] = v
	}

	timeoutMs := resolveToolTimeoutMs(node, toolConfig, def.HTTP.TimeoutMs)
	retryAttempts := resolveToolRetryAttempts(node, toolConfig)
	retryBackoffMs := resolveToolRetryBackoffMs(node, toolConfig)

	var lastErr error
	for attempt := 1; attempt <= retryAttempts; attempt++ {
		attemptCtx, cancel := context.WithTimeout(ctx, time.Duration(timeoutMs)*time.Millisecond)

		req, err := http.NewRequestWithContext(attemptCtx, method, urlStr, bytes.NewReader(bodyBytes))
		if err != nil {
			cancel()
			return nil, err
		}
		req.Header.Set("Content-Type", "application/json")
		for k, v := range headers {
			req.Header.Set(k, v)
		}

		resp, err := e.httpClient.Do(req)
		if err != nil {
			cancel()
			if ctx.Err() != nil {
				return nil, ctx.Err()
			}
			lastErr = domain.NewRetryableError(err, "tool http request failed")
			if attempt < retryAttempts {
				if backoffErr := sleepWithContext(ctx, retryBackoffMs); backoffErr != nil {
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
			lastErr = domain.NewRetryableError(err, "failed to read tool response")
			if attempt < retryAttempts {
				if backoffErr := sleepWithContext(ctx, retryBackoffMs); backoffErr != nil {
					return nil, backoffErr
				}
				continue
			}
			return nil, lastErr
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
			lastErr = domain.NewRetryableError(
				fmt.Errorf("HTTP %d: %s", resp.StatusCode, strings.TrimSpace(string(body))),
				"tool upstream unavailable",
			)
			if attempt < retryAttempts {
				if backoffErr := sleepWithContext(ctx, retryBackoffMs); backoffErr != nil {
					return nil, backoffErr
				}
				continue
			}
			return nil, lastErr
		}
		if resp.StatusCode >= 400 {
			return nil, fmt.Errorf("HTTP %d: %s", resp.StatusCode, strings.TrimSpace(string(body)))
		}

		return map[string]any{
			"tool":     def.Name,
			"version":  def.Version,
			"status":   resp.StatusCode,
			"result":   parsed,
			"attempts": attempt,
		}, nil
	}

	if lastErr != nil {
		return nil, lastErr
	}
	return nil, fmt.Errorf("tool request failed")
}

func (e *ToolExecutor) executeExecTool(
	ctx context.Context,
	def *tool.Definition,
	payload map[string]any,
	node *entity.Node,
	toolConfig map[string]any,
) (map[string]any, error) {
	if def.Exec == nil {
		return nil, fmt.Errorf("tool missing exec configuration")
	}
	command := os.ExpandEnv(def.Exec.Command)
	if command == "" {
		return nil, fmt.Errorf("tool command not configured")
	}

	args := make([]string, 0, len(def.Exec.Args))
	for _, arg := range def.Exec.Args {
		args = append(args, os.ExpandEnv(arg))
	}

	inputBytes, err := json.Marshal(payload)
	if err != nil {
		return nil, err
	}
	timeoutMs := resolveToolTimeoutMs(node, toolConfig, def.Exec.TimeoutMs)
	retryAttempts := resolveToolRetryAttempts(node, toolConfig)
	retryBackoffMs := resolveToolRetryBackoffMs(node, toolConfig)

	var lastErr error
	for attempt := 1; attempt <= retryAttempts; attempt++ {
		attemptCtx, cancel := context.WithTimeout(ctx, time.Duration(timeoutMs)*time.Millisecond)
		cmd := exec.CommandContext(attemptCtx, command, args...)
		if def.Exec.WorkDir != "" {
			cmd.Dir = os.ExpandEnv(def.Exec.WorkDir)
		}
		if len(def.Exec.EnvWhitelist) > 0 {
			env := make([]string, 0, len(def.Exec.EnvWhitelist))
			for _, key := range def.Exec.EnvWhitelist {
				if val, ok := os.LookupEnv(key); ok {
					env = append(env, fmt.Sprintf("%s=%s", key, val))
				}
			}
			cmd.Env = env
		}

		cmd.Stdin = bytes.NewReader(inputBytes)
		var stdout bytes.Buffer
		var stderr bytes.Buffer
		cmd.Stdout = &stdout
		cmd.Stderr = &stderr

		err := cmd.Run()
		cancel()
		if err != nil {
			if ctx.Err() != nil {
				return nil, ctx.Err()
			}
			if errors.Is(attemptCtx.Err(), context.DeadlineExceeded) {
				lastErr = domain.NewRetryableError(err, "tool exec timed out")
				if attempt < retryAttempts {
					if backoffErr := sleepWithContext(ctx, retryBackoffMs); backoffErr != nil {
						return nil, backoffErr
					}
					continue
				}
				return nil, lastErr
			}
			return nil, fmt.Errorf("tool exec failed: %w: %s", err, strings.TrimSpace(stderr.String()))
		}

		rawOutput := stdout.Bytes()
		var parsed any
		if len(rawOutput) > 0 {
			if err := json.Unmarshal(rawOutput, &parsed); err != nil {
				parsed = strings.TrimSpace(stdout.String())
			}
		}

		result := map[string]any{
			"tool":     def.Name,
			"version":  def.Version,
			"result":   parsed,
			"attempts": attempt,
		}
		if stderr.Len() > 0 {
			result["stderr"] = strings.TrimSpace(stderr.String())
		}
		return result, nil
	}

	if lastErr != nil {
		return nil, lastErr
	}
	return nil, fmt.Errorf("tool exec failed")
}

func resolveToolInput(node *entity.Node, state *entity.State) (any, error) {
	if inputPath := strings.TrimSpace(node.GetConfigString("input_path")); inputPath != "" {
		if val, ok := state.Get(inputPath); ok {
			return val, nil
		}
		if resolved := resolveStatePath(inputPath, state); resolved != nil {
			return resolved, nil
		}
		return nil, domain.NewValidationError("input_path", "input_path did not resolve to a value")
	}

	if inputTemplate := node.GetConfigString("input_template"); inputTemplate != "" {
		return SubstituteTemplate(inputTemplate, state), nil
	}

	if val, ok := node.Config["input"]; ok {
		return val, nil
	}

	return map[string]any{}, nil
}

func resolveStatePath(path string, state *entity.State) any {
	parts := strings.Split(path, ".")
	if len(parts) < 2 {
		return nil
	}

	for i := len(parts) - 1; i >= 1; i-- {
		baseKey := strings.Join(parts[:i], ".")
		if val, exists := state.Get(baseKey); exists {
			remaining := parts[i:]
			return navigateToolValue(val, remaining)
		}
	}

	return nil
}

func navigateToolValue(val any, path []string) any {
	current := val
	for _, key := range path {
		switch v := current.(type) {
		case map[string]any:
			current = v[key]
		case []any:
			if key == "" {
				return nil
			}
			if idx := parseIndex(key); idx >= 0 && idx < len(v) {
				current = v[idx]
			} else {
				return nil
			}
		default:
			return nil
		}
	}
	return current
}

func parseIndex(val string) int {
	if val == "" {
		return -1
	}
	parsed, err := strconv.Atoi(val)
	if err != nil {
		return -1
	}
	return parsed
}

func resolveToolTimeoutMs(node *entity.Node, toolConfig map[string]any, defaultFromDefinition int) int {
	timeoutMs := node.GetConfigInt("timeout_ms")
	if timeoutMs <= 0 {
		timeoutMs = readInt(toolConfig, "timeout_ms")
	}
	if timeoutMs <= 0 {
		timeoutMs = defaultFromDefinition
	}
	if timeoutMs <= 0 {
		return 30000
	}
	return timeoutMs
}

func resolveToolRetryAttempts(node *entity.Node, toolConfig map[string]any) int {
	retryAttempts := node.GetConfigInt("retry_attempts")
	if retryAttempts <= 0 {
		retryAttempts = readInt(toolConfig, "retry_attempts")
	}
	if retryAttempts <= 0 {
		return 1
	}
	return retryAttempts
}

func resolveToolRetryBackoffMs(node *entity.Node, toolConfig map[string]any) int {
	backoffMs := node.GetConfigInt("retry_backoff_ms")
	if backoffMs <= 0 {
		backoffMs = readInt(toolConfig, "retry_backoff_ms")
	}
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
