package executor

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"os"
	"os/exec"
	"strconv"
	"strings"

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
		result, err := e.executeHTTPTool(ctx, def, payload, node)
		if err != nil {
			return port.NewErrorResult(err), nil
		}
		return port.NewSuccessResult(result), nil
	case "exec":
		result, err := e.executeExecTool(ctx, def, payload)
		if err != nil {
			return port.NewErrorResult(err), nil
		}
		return port.NewSuccessResult(result), nil
	default:
		return port.NewErrorResult(domain.NewValidationError("kind", "unsupported tool kind")), nil
	}
}

func (e *ToolExecutor) executeHTTPTool(ctx context.Context, def *tool.Definition, payload map[string]any, node *entity.Node) (map[string]any, error) {
	if def.HTTP == nil {
		return nil, fmt.Errorf("tool missing http configuration")
	}

	urlStr := os.ExpandEnv(def.HTTP.URL)
	if urlStr == "" {
		return nil, fmt.Errorf("tool URL not configured")
	}

	method := def.HTTP.Method
	if method == "" {
		method = "POST"
	}

	bodyBytes, err := json.Marshal(payload)
	if err != nil {
		return nil, err
	}

	req, err := http.NewRequestWithContext(ctx, method, urlStr, bytes.NewReader(bodyBytes))
	if err != nil {
		return nil, err
	}
	req.Header.Set("Content-Type", "application/json")

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
		req.Header.Set(k, v)
	}

	resp, err := e.httpClient.Do(req)
	if err != nil {
		return nil, err
	}
	defer resp.Body.Close()

	body, err := io.ReadAll(resp.Body)
	if err != nil {
		return nil, err
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

	return map[string]any{
		"tool":    def.Name,
		"version": def.Version,
		"status":  resp.StatusCode,
		"result":  parsed,
	}, nil
}

func (e *ToolExecutor) executeExecTool(ctx context.Context, def *tool.Definition, payload map[string]any) (map[string]any, error) {
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

	cmd := exec.CommandContext(ctx, command, args...)
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

	inputBytes, err := json.Marshal(payload)
	if err != nil {
		return nil, err
	}
	cmd.Stdin = bytes.NewReader(inputBytes)

	var stdout bytes.Buffer
	var stderr bytes.Buffer
	cmd.Stdout = &stdout
	cmd.Stderr = &stderr

	if err := cmd.Run(); err != nil {
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
		"tool":    def.Name,
		"version": def.Version,
		"result":  parsed,
	}
	if stderr.Len() > 0 {
		result["stderr"] = strings.TrimSpace(stderr.String())
	}

	return result, nil
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
