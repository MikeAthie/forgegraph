package executor

import (
	"bytes"
	"context"
	"encoding/base64"
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
	client   *http.Client
	resolver CredentialResolver
}

// CredentialResolver resolves provider credentials from the control plane.
type CredentialResolver interface {
	Resolve(ctx context.Context, credentialID string, tenantID string) (string, string, error)
}

// NewHTTPExecutor creates a new HTTP executor with default client
func NewHTTPExecutor() *HTTPExecutor {
	return NewHTTPExecutorWithClientAndResolver(nil, nil)
}

// NewHTTPExecutorWithClient creates a new HTTP executor with a custom client
func NewHTTPExecutorWithClient(client *http.Client) *HTTPExecutor {
	return NewHTTPExecutorWithClientAndResolver(client, nil)
}

// NewHTTPExecutorWithResolver creates a new HTTP executor with a credential resolver.
func NewHTTPExecutorWithResolver(resolver CredentialResolver) *HTTPExecutor {
	return NewHTTPExecutorWithClientAndResolver(nil, resolver)
}

// NewHTTPExecutorWithClientAndResolver creates a new HTTP executor with custom dependencies.
func NewHTTPExecutorWithClientAndResolver(client *http.Client, resolver CredentialResolver) *HTTPExecutor {
	if client == nil {
		client = &http.Client{
			Timeout: 30 * time.Second,
		}
	}
	return &HTTPExecutor{
		client:   client,
		resolver: resolver,
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
	provider, apiKey, credentialErr := e.resolveCredentialContext(ctx, node)
	if credentialErr != nil {
		return port.NewErrorResult(credentialErr), nil
	}
	templateValues := credentialTemplateValues(provider, apiKey)

	// Get URL (required)
	urlStr, ok := node.Config["url"].(string)
	if !ok || urlStr == "" {
		return port.NewErrorResult(domain.NewValidationError("url", "http node requires url")), nil
	}

	// Substitute variables in URL
	urlStr = SubstituteTemplateWithExtras(urlStr, state, templateValues)

	if !isHTTPAllowed(port.PolicyFromContext(ctx), urlStr) {
		return port.NewErrorResult(domain.NewValidationError("url", "egress blocked by policy")), nil
	}

	// Get method (default: GET)
	method, _ := node.Config["method"].(string)
	if method == "" {
		method = "GET"
	}
	method = strings.ToUpper(method)

	throttleMs := resolveTenantProviderThrottleMs(ctx, provider, node.Config)
	if throttleMs > 0 {
		if err := throttleTenantProvider(ctx, port.TenantIDFrom(ctx), provider, throttleMs); err != nil {
			return port.NewErrorResult(
				domain.NewRetryableErrorWithDetails(
					err,
					"tenant provider throttle interrupted",
					"tenant_throttle",
					0,
					map[string]any{
						"provider":         provider,
						"throttle_ms":      throttleMs,
						"tenant_throttled": true,
					},
				),
			), nil
		}
	}

	// Build request body
	var bodyReader io.Reader
	if method == "POST" || method == "PUT" || method == "PATCH" {
		body, err := e.buildRequestBody(node, state, templateValues)
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
				strVal = SubstituteTemplateWithExtras(strVal, state, templateValues)
				req.Header.Set(key, strVal)
			}
		}
	}

	e.injectCredentialAuthHeader(req, node, state, provider, apiKey, templateValues)

	// Set Content-Type if not specified and we have a body
	if bodyReader != nil && req.Header.Get("Content-Type") == "" {
		req.Header.Set("Content-Type", "application/json")
	}

	// Execute request
	resp, err := e.client.Do(req)
	if err != nil {
		// Network errors are retryable
		return port.NewErrorResult(
			domain.NewRetryableErrorWithDetails(
				err,
				"network error",
				"network_error",
				0,
				map[string]any{
					"provider": provider,
				},
			),
		), nil
	}
	defer resp.Body.Close()

	// Read response body
	respBody, err := io.ReadAll(resp.Body)
	if err != nil {
		return port.NewErrorResult(
			domain.NewRetryableErrorWithDetails(
				err,
				"failed to read response",
				"read_error",
				0,
				map[string]any{
					"provider": provider,
				},
			),
		), nil
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
	bodyText := strings.TrimSpace(string(respBody))
	if resp.StatusCode == http.StatusTooManyRequests {
		retryAfterMs := parseRetryAfterMs(resp.Header.Get("Retry-After"), time.Now())
		if isQuotaExhaustedRateLimit(bodyText) {
			return port.NewErrorResult(
				fmt.Errorf(
					"rate limit quota exhausted (HTTP 429). Increase provider quota/billing and retry: %s",
					bodyText,
				),
			), nil
		}

		return port.NewErrorResult(
			domain.NewRetryableErrorWithDetails(
				fmt.Errorf("HTTP %d: %s", resp.StatusCode, bodyText),
				"rate limited",
				"rate_limited",
				retryAfterMs,
				map[string]any{
					"status_code":     resp.StatusCode,
					"retry_after_ms":  retryAfterMs,
					"rate_limit_type": "throttled",
					"provider":        provider,
				},
			),
		), nil
	}

	if resp.StatusCode >= 500 {
		// 5xx errors are retryable
		return port.NewErrorResult(
			domain.NewRetryableErrorWithDetails(
				fmt.Errorf("HTTP %d: %s", resp.StatusCode, string(respBody)),
				"server error",
				"transient_http_5xx",
				0,
				map[string]any{
					"status_code": resp.StatusCode,
					"provider":    provider,
				},
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
func (e *HTTPExecutor) buildRequestBody(node *entity.Node, state *entity.State, templateValues map[string]string) ([]byte, error) {
	// Check for body_template first (string template with substitution)
	if bodyTemplate, ok := node.Config["body_template"].(string); ok {
		substituted := SubstituteTemplateWithExtras(bodyTemplate, state, templateValues)
		return []byte(substituted), nil
	}

	// Check for body (can be map or string)
	if body, ok := node.Config["body"]; ok {
		switch v := body.(type) {
		case string:
			return []byte(SubstituteTemplateWithExtras(v, state, templateValues)), nil
		case map[string]any:
			// Substitute variables in map values
			substitutedBody := e.substituteMapValues(v, state, templateValues)
			return json.Marshal(substitutedBody)
		default:
			return json.Marshal(v)
		}
	}

	return nil, nil
}

// substituteMapValues recursively substitutes template values in a map
func (e *HTTPExecutor) substituteMapValues(m map[string]any, state *entity.State, templateValues map[string]string) map[string]any {
	result := make(map[string]any)
	for k, v := range m {
		switch val := v.(type) {
		case string:
			result[k] = SubstituteTemplateWithExtras(val, state, templateValues)
		case map[string]any:
			result[k] = e.substituteMapValues(val, state, templateValues)
		default:
			result[k] = v
		}
	}
	return result
}

func (e *HTTPExecutor) resolveCredentialContext(ctx context.Context, node *entity.Node) (string, string, error) {
	provider, _ := node.Config["provider"].(string)
	provider = strings.ToLower(strings.TrimSpace(provider))
	credentialID, _ := node.Config["credential_id"].(string)
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

func credentialTemplateValues(provider string, apiKey string) map[string]string {
	values := map[string]string{}
	if strings.TrimSpace(apiKey) == "" {
		return values
	}
	values["credential.api_key"] = apiKey
	values["credentials.api_key"] = apiKey
	values["credential.token"] = apiKey
	values["credentials.token"] = apiKey

	normalizedProvider := strings.ToLower(strings.TrimSpace(provider))
	if normalizedProvider != "" {
		values[fmt.Sprintf("credentials.%s_api_key", normalizedProvider)] = apiKey
		values[fmt.Sprintf("credentials.%s_token", normalizedProvider)] = apiKey
	}
	if normalizedProvider == "twilio" {
		values["credentials.twilio_auth_token"] = apiKey
	}
	return values
}

func (e *HTTPExecutor) injectCredentialAuthHeader(
	req *http.Request,
	node *entity.Node,
	state *entity.State,
	provider string,
	apiKey string,
	templateValues map[string]string,
) {
	if req == nil || strings.TrimSpace(apiKey) == "" {
		return
	}
	if strings.TrimSpace(req.Header.Get("Authorization")) != "" {
		return
	}

	normalizedProvider := strings.ToLower(strings.TrimSpace(provider))
	if normalizedProvider == "telegram" {
		// Telegram Bot API tokens are usually included in URL path.
		return
	}

	if normalizedProvider == "twilio" {
		accountSID, _ := node.Config["account_sid"].(string)
		accountSID = SubstituteTemplateWithExtras(accountSID, state, templateValues)
		accountSID = strings.TrimSpace(accountSID)
		if accountSID != "" {
			basic := base64.StdEncoding.EncodeToString([]byte(fmt.Sprintf("%s:%s", accountSID, apiKey)))
			req.Header.Set("Authorization", "Basic "+basic)
			return
		}
	}

	req.Header.Set("Authorization", "Bearer "+apiKey)
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
