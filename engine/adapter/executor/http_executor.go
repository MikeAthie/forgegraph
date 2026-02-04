package executor

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"net/url"
	"strings"
	"time"

	"github.com/forgegraph/engine/application/port"
	"github.com/forgegraph/engine/domain"
	"github.com/forgegraph/engine/domain/entity"
	"github.com/forgegraph/engine/domain/value"
)

// HTTPExecutor handles HTTP tool nodes that make external API calls.
type HTTPExecutor struct {
	client *http.Client
}

// NewHTTPExecutor creates a new HTTP executor with default client
func NewHTTPExecutor() *HTTPExecutor {
	return &HTTPExecutor{
		client: &http.Client{
			Timeout: 30 * time.Second,
		},
	}
}

// NewHTTPExecutorWithClient creates a new HTTP executor with a custom client
func NewHTTPExecutorWithClient(client *http.Client) *HTTPExecutor {
	return &HTTPExecutor{
		client: client,
	}
}

// NodeType returns the node type this executor handles
func (e *HTTPExecutor) NodeType() string {
	return string(value.NodeTypeHTTP)
}

// Execute makes an HTTP request and returns the response.
//
// Config options:
//   - method: string - HTTP method (GET, POST, PUT, DELETE, PATCH). Default: GET
//   - url: string - The URL to call (supports {{key}} substitution)
//   - headers: map[string]string - Request headers (supports {{key}} substitution)
//   - body: any - Request body (for POST/PUT/PATCH)
//   - body_template: string - JSON body template with {{key}} substitution
//   - timeout_ms: int - Request timeout in milliseconds (default: 30000)
//
// Output:
//   - status_code: int
//   - headers: map[string]string
//   - body: any (parsed JSON or string)
func (e *HTTPExecutor) Execute(ctx context.Context, node *entity.Node, state *entity.State) (*port.NodeExecutionResult, error) {
	// Get URL (required)
	urlStr, ok := node.Config["url"].(string)
	if !ok || urlStr == "" {
		return port.NewErrorResult(domain.NewValidationError("url", "http node requires url")), nil
	}

	// Substitute variables in URL
	urlStr = SubstituteTemplate(urlStr, state)

	if !isHTTPAllowed(port.PolicyFromContext(ctx), urlStr) {
		return port.NewErrorResult(domain.NewValidationError("url", "egress blocked by policy")), nil
	}

	// Get method (default: GET)
	method, _ := node.Config["method"].(string)
	if method == "" {
		method = "GET"
	}
	method = strings.ToUpper(method)

	// Build request body
	var bodyReader io.Reader
	if method == "POST" || method == "PUT" || method == "PATCH" {
		body, err := e.buildRequestBody(node, state)
		if err != nil {
			return port.NewErrorResult(err), nil
		}
		if body != nil {
			bodyReader = bytes.NewReader(body)
		}
	}

	// Create request
	req, err := http.NewRequestWithContext(ctx, method, urlStr, bodyReader)
	if err != nil {
		return port.NewErrorResult(domain.NewValidationError("request", fmt.Sprintf("invalid request: %v", err))), nil
	}

	// Set headers
	if headers, ok := node.Config["headers"].(map[string]any); ok {
		for key, val := range headers {
			if strVal, ok := val.(string); ok {
				strVal = SubstituteTemplate(strVal, state)
				req.Header.Set(key, strVal)
			}
		}
	}

	// Set Content-Type if not specified and we have a body
	if bodyReader != nil && req.Header.Get("Content-Type") == "" {
		req.Header.Set("Content-Type", "application/json")
	}

	// Execute request
	resp, err := e.client.Do(req)
	if err != nil {
		// Network errors are retryable
		return port.NewErrorResult(domain.NewRetryableError(err, "network error")), nil
	}
	defer resp.Body.Close()

	// Read response body
	respBody, err := io.ReadAll(resp.Body)
	if err != nil {
		return port.NewErrorResult(domain.NewRetryableError(err, "failed to read response")), nil
	}

	// Build output
	output := map[string]any{
		"status_code": resp.StatusCode,
		"headers":     e.extractHeaders(resp.Header),
	}

	// Try to parse response as JSON
	var jsonBody any
	if err := json.Unmarshal(respBody, &jsonBody); err == nil {
		output["body"] = jsonBody
	} else {
		output["body"] = string(respBody)
	}

	// Check for error status codes
	if resp.StatusCode >= 500 {
		// 5xx errors are retryable
		return port.NewErrorResult(
			domain.NewRetryableError(
				fmt.Errorf("HTTP %d: %s", resp.StatusCode, string(respBody)),
				"server error",
			),
		), nil
	}

	if resp.StatusCode >= 400 {
		// 4xx errors are not retryable
		return port.NewErrorResult(
			fmt.Errorf("HTTP %d: %s", resp.StatusCode, string(respBody)),
		), nil
	}

	return port.NewSuccessResult(output), nil
}

// buildRequestBody creates the request body from config
func (e *HTTPExecutor) buildRequestBody(node *entity.Node, state *entity.State) ([]byte, error) {
	// Check for body_template first (string template with substitution)
	if bodyTemplate, ok := node.Config["body_template"].(string); ok {
		substituted := SubstituteTemplate(bodyTemplate, state)
		return []byte(substituted), nil
	}

	// Check for body (can be map or string)
	if body, ok := node.Config["body"]; ok {
		switch v := body.(type) {
		case string:
			return []byte(SubstituteTemplate(v, state)), nil
		case map[string]any:
			// Substitute variables in map values
			substitutedBody := e.substituteMapValues(v, state)
			return json.Marshal(substitutedBody)
		default:
			return json.Marshal(v)
		}
	}

	return nil, nil
}

// substituteMapValues recursively substitutes template values in a map
func (e *HTTPExecutor) substituteMapValues(m map[string]any, state *entity.State) map[string]any {
	result := make(map[string]any)
	for k, v := range m {
		switch val := v.(type) {
		case string:
			result[k] = SubstituteTemplate(val, state)
		case map[string]any:
			result[k] = e.substituteMapValues(val, state)
		default:
			result[k] = v
		}
	}
	return result
}

// extractHeaders converts http.Header to a simple map
func (e *HTTPExecutor) extractHeaders(h http.Header) map[string]string {
	result := make(map[string]string)
	for key, values := range h {
		if len(values) > 0 {
			result[key] = values[0]
		}
	}
	return result
}

func isHTTPAllowed(policy *entity.ExecutionPolicy, rawURL string) bool {
	if policy == nil {
		return true
	}

	parsed, err := url.Parse(rawURL)
	if err != nil || parsed.Host == "" {
		return false
	}

	host := strings.ToLower(parsed.Hostname())
	if host == "" {
		return false
	}

	if matchesList(host, policy.HTTPDenylist) {
		return false
	}

	if len(policy.HTTPAllowlist) > 0 {
		return matchesList(host, policy.HTTPAllowlist)
	}

	if policy.HTTPDefaultDeny {
		return false
	}

	return true
}

func matchesList(host string, patterns []string) bool {
	if len(patterns) == 0 {
		return false
	}
	for _, rawPattern := range patterns {
		pattern := strings.ToLower(strings.TrimSpace(rawPattern))
		if pattern == "" {
			continue
		}
		if pattern == "*" {
			return true
		}
		if strings.HasPrefix(pattern, "*.") {
			suffix := strings.TrimPrefix(pattern, "*.")
			if host == suffix || strings.HasSuffix(host, "."+suffix) {
				return true
			}
			continue
		}
		if host == pattern {
			return true
		}
	}
	return false
}
