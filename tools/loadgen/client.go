package main

import (
	"bytes"
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"net"
	"net/http"
	"net/url"
	"strconv"
	"strings"
	"time"

	"github.com/gorilla/websocket"
)

type APIClient struct {
	baseURL string
	http    *http.Client
	writer  *ArtifactWriter
}

type HTTPResult struct {
	Method     string         `json:"method"`
	Path       string         `json:"path"`
	StatusCode int            `json:"status_code"`
	DurationMS float64        `json:"duration_ms"`
	StartedAt  time.Time      `json:"started_at"`
	EndedAt    time.Time      `json:"ended_at"`
	Error      string         `json:"error,omitempty"`
	Body       map[string]any `json:"body,omitempty"`
}

const loadgenTerminalNodeID = "final_output"

func NewAPIClient(cfg Config, writer *ArtifactWriter) *APIClient {
	return &APIClient{
		baseURL: strings.TrimRight(cfg.BaseURL, "/"),
		http: &http.Client{
			Timeout: cfg.RequestTimeout,
		},
		writer: writer,
	}
}

func (client *APIClient) doJSON(ctx context.Context, method, apiPath, token, idempotencyKey string, payload any) (HTTPResult, error) {
	var body []byte
	var err error
	if payload != nil {
		body, err = json.Marshal(payload)
		if err != nil {
			return HTTPResult{}, err
		}
	}
	result := HTTPResult{
		Method:    method,
		Path:      apiPath,
		StartedAt: time.Now().UTC(),
	}
	request, err := http.NewRequestWithContext(ctx, method, client.baseURL+apiPath, bytes.NewReader(body))
	if err != nil {
		return result, err
	}
	request.Header.Set("Content-Type", "application/json")
	if token != "" {
		request.Header.Set("Authorization", "Bearer "+token)
	}
	if idempotencyKey != "" {
		request.Header.Set("Idempotency-Key", idempotencyKey)
	}
	response, err := client.http.Do(request)
	result.EndedAt = time.Now().UTC()
	result.DurationMS = float64(result.EndedAt.Sub(result.StartedAt).Microseconds()) / 1000
	if err != nil {
		result.Error = err.Error()
		client.logRequest(result)
		return result, err
	}
	defer response.Body.Close()
	result.StatusCode = response.StatusCode
	responseBody, readErr := io.ReadAll(response.Body)
	if readErr != nil {
		result.Error = readErr.Error()
		client.logRequest(result)
		return result, readErr
	}
	if len(responseBody) > 0 {
		var decoded map[string]any
		if err := json.Unmarshal(responseBody, &decoded); err == nil {
			result.Body = decoded
		}
	}
	client.logRequest(result)
	if response.StatusCode >= 400 {
		return result, fmt.Errorf("%s %s returned %d", method, apiPath, response.StatusCode)
	}
	return result, nil
}

func (client *APIClient) logRequest(result HTTPResult) {
	if client.writer != nil {
		_ = client.writer.AppendJSONL(client.writer.Paths.RequestsJSONL, result)
	}
}

func (client *APIClient) EnsureTenant(ctx context.Context, tenant *TenantPlan) error {
	if tenant.AccessToken == "" {
		if tenant.Password == "" {
			return fmt.Errorf("tenant %s is missing password and access token", tenant.Email)
		}
		if !tenant.FromCredentials {
			registerPayload := map[string]any{"email": tenant.Email, "password": tenant.Password}
			if result, err := client.doJSON(ctx, http.MethodPost, "/api/auth/register", "", "", registerPayload); err == nil {
				if tenant.OrganizationID == "" {
					tenant.OrganizationID = firstString(result.Body, "default_organization_id", "organization_id", "org_id")
				}
			}
		}
		loginPayload := map[string]any{"email": tenant.Email, "password": tenant.Password}
		result, err := client.doJSON(ctx, http.MethodPost, "/api/auth/login", "", "", loginPayload)
		if err != nil {
			return err
		}
		tenant.AccessToken = firstString(result.Body, "access", "token")
		if tenant.AccessToken == "" {
			return errors.New("login response did not include an access token")
		}
	}
	if tenant.OrganizationID == "" {
		if orgID, err := client.fetchOrganizationID(ctx, tenant.AccessToken); err == nil {
			tenant.OrganizationID = orgID
		}
	}
	if tenant.OrganizationID == "" {
		return fmt.Errorf("tenant %s is missing organization id", tenant.Email)
	}
	if tenant.GraphVersionID == "" {
		graphVersionID, err := client.CreateGraphVersion(ctx, tenant.AccessToken)
		if err != nil {
			return err
		}
		tenant.GraphVersionID = graphVersionID
	}
	return nil
}

func (client *APIClient) fetchOrganizationID(ctx context.Context, token string) (string, error) {
	result, err := client.doJSON(ctx, http.MethodGet, "/api/auth/me", token, "", nil)
	if err == nil {
		if value := firstString(result.Body, "default_organization_id", "organization_id", "org_id"); value != "" {
			return value, nil
		}
	}
	result, err = client.doJSON(ctx, http.MethodGet, "/api/orgs/me", token, "", nil)
	if err != nil {
		return "", err
	}
	data := dataObject(result.Body)
	if org, ok := data["organization"].(map[string]any); ok {
		return firstString(org, "id", "organization_id"), nil
	}
	return firstString(data, "id", "organization_id"), nil
}

func (client *APIClient) CreateGraphVersion(ctx context.Context, token string) (string, error) {
	result, err := client.doJSON(ctx, http.MethodPost, "/api/graphs/", token, "", map[string]any{
		"name":        "Loadgen capacity graph",
		"description": "Generated by tools/loadgen through backend APIs.",
	})
	if err != nil {
		return "", err
	}
	graphID := firstString(dataObject(result.Body), "id")
	if graphID == "" {
		return "", errors.New("graph create response did not include id")
	}
	result, err = client.doJSON(ctx, http.MethodPost, "/api/graphs/"+graphID+"/versions", token, "", map[string]any{
		"graph_json": loadgenGraphJSON(),
	})
	if err != nil {
		return "", err
	}
	graphVersionID := firstString(dataObject(result.Body), "id")
	if graphVersionID == "" {
		return "", errors.New("graph version response did not include id")
	}
	return graphVersionID, nil
}

func loadgenGraphJSON() map[string]any {
	return map[string]any{
		"nodes": []map[string]any{
			{
				"id":   loadgenTerminalNodeID,
				"type": "output",
				"name": "Final Output",
				"config": map[string]any{
					"output_mapping": map[string]any{
						"loadgen":      "input.loadgen",
						"tenant_index": "input.tenant_index",
						"run_index":    "input.run_index",
						"agent_index":  "input.agent_index",
					},
				},
			},
		},
		"edges": []map[string]any{
			{"id": "start-final", "from": "START", "to": loadgenTerminalNodeID},
			{"id": "final-end", "from": loadgenTerminalNodeID, "to": "END"},
		},
		"metadata": map[string]any{
			"name":                    "Loadgen capacity graph",
			"description":             "Output-only loadgen graph; no LLM calls are expected.",
			"engine_contract_version": "2",
		},
	}
}

func (client *APIClient) StartRun(ctx context.Context, tenant TenantPlan, run RunPlan) (string, float64, error) {
	result, err := client.doJSON(ctx, http.MethodPost, "/api/runs/start", tenant.AccessToken, run.CommandID, map[string]any{
		"graph_version_id": tenant.GraphVersionID,
		"input_json": map[string]any{
			"loadgen":      true,
			"tenant_index": tenant.Index,
			"run_index":    run.Index,
			"agent_index":  run.AgentIndex,
		},
	})
	if err != nil {
		return "", result.DurationMS, err
	}
	runID := firstString(dataObject(result.Body), "id")
	if runID == "" {
		return "", result.DurationMS, errors.New("run start response did not include id")
	}
	return runID, result.DurationMS, nil
}

func (client *APIClient) CreateMemoryObservation(ctx context.Context, tenant TenantPlan, runID string, index int) (float64, error) {
	payload := map[string]any{
		"idempotency_key": fmt.Sprintf("loadgen:memory:%s:%d", runID, index),
		"type":            "fact",
		"title":           "Loadgen capacity observation",
		"content":         fmt.Sprintf("Loadgen fact for run %s attempt %d", runID, index),
		"scope":           "run",
		"run_id":          runID,
		"dedupe":          true,
	}
	result, err := client.doJSON(ctx, http.MethodPost, "/api/memory/observations", tenant.AccessToken, fmt.Sprintf("loadgen:memory:%s:%d", runID, index), payload)
	return result.DurationMS, err
}

func (client *APIClient) ResumeRun(ctx context.Context, tenant TenantPlan, runID string, index int) (float64, error) {
	result, err := client.doJSON(ctx, http.MethodPost, "/api/runs/"+runID+"/resume", tenant.AccessToken, fmt.Sprintf("loadgen:resume:%s:%d", runID, index), map[string]any{
		"submit_id": fmt.Sprintf("loadgen:resume:%s:%d", runID, index),
		"input": map[string]any{
			"approved": true,
			"source":   "loadgen",
		},
	})
	return result.DurationMS, err
}

func (client *APIClient) PauseRunForHITL(ctx context.Context, tenant TenantPlan, runID string, index int) (float64, error) {
	result, err := client.doJSON(ctx, http.MethodPost, "/api/runs/"+runID+"/events", tenant.AccessToken, fmt.Sprintf("loadgen:hitl-pause:%s:%d", runID, index), map[string]any{
		"event_type": "run.updated",
		"run": map[string]any{
			"status":           "paused",
			"paused_node_id":   "human_gate_1",
			"pause_state_json": map[string]any{"loadgen": true, "run_index": index},
			"pause_payload": map[string]any{
				"node_id":         "human_gate_1",
				"prompt_message":  "Loadgen approval gate",
				"required_fields": []string{"approved"},
			},
		},
	})
	return result.DurationMS, err
}

func (client *APIClient) PostEngineNodeCompleted(ctx context.Context, cfg Config, tenant TenantPlan, runID string, eventID string) (float64, error) {
	requestTimestamp := engineEventTimestamp(time.Now().UTC())
	occurredAt := deterministicEventTime(eventID).Format(time.RFC3339Nano)
	payload := map[string]any{
		"node_id":     loadgenTerminalNodeID,
		"node_type":   "output",
		"node_name":   "Final Output",
		"attempt":     1,
		"attempt_id":  eventID + ":attempt",
		"duration_ms": 25,
		"output": map[string]any{
			"final_output":      "loadgen accounting sample",
			"stop_reason":       "stop",
			"provider":          "openai",
			"model":             "loadgen-simulated",
			"usage":             map[string]any{"prompt_tokens": 12, "completion_tokens": 8, "total_tokens": 20},
			"loadgen_generated": true,
		},
	}
	envelope := map[string]any{
		"schema_version":  2,
		"source":          "engine",
		"type":            "node.completed",
		"event_id":        eventID,
		"idempotency_key": eventID,
		"run_id":          runID,
		"tenant_id":       tenant.OrganizationID,
		"org_id":          tenant.OrganizationID,
		"agent_id":        loadgenTerminalNodeID,
		"task_id":         loadgenTerminalNodeID,
		"sequence":        1,
		"correlation_id":  eventID,
		"occurred_at":     occurredAt,
		"payload":         payload,
	}
	checksum, err := canonicalEventChecksum(envelope)
	if err != nil {
		return 0, err
	}
	envelope["checksum"] = checksum
	body, err := json.Marshal(envelope)
	if err != nil {
		return 0, err
	}
	startedAt := time.Now().UTC()
	request, err := http.NewRequestWithContext(ctx, http.MethodPost, client.baseURL+"/api/runs/engine-events", bytes.NewReader(body))
	if err != nil {
		return 0, err
	}
	request.Header.Set("Content-Type", "application/json")
	request.Header.Set("X-ForgeGraph-Timestamp", requestTimestamp)
	request.Header.Set("X-ForgeGraph-Signature", signEngineEvent(cfg.EngineCallbackSecret, requestTimestamp, body))
	response, err := client.http.Do(request)
	endedAt := time.Now().UTC()
	durationMS := float64(endedAt.Sub(startedAt).Microseconds()) / 1000
	result := HTTPResult{
		Method:     http.MethodPost,
		Path:       "/api/runs/engine-events",
		StatusCode: 0,
		DurationMS: durationMS,
		StartedAt:  startedAt,
		EndedAt:    endedAt,
	}
	if err != nil {
		result.Error = err.Error()
		client.logRequest(result)
		return durationMS, err
	}
	defer response.Body.Close()
	result.StatusCode = response.StatusCode
	responseBody, _ := io.ReadAll(response.Body)
	if len(responseBody) > 0 {
		var decoded map[string]any
		if err := json.Unmarshal(responseBody, &decoded); err == nil {
			result.Body = decoded
		}
	}
	client.logRequest(result)
	if response.StatusCode >= 400 {
		return durationMS, fmt.Errorf("POST /api/runs/engine-events returned %d", response.StatusCode)
	}
	return durationMS, nil
}

func (client *APIClient) PollReadAPIs(ctx context.Context, tenant TenantPlan) (apiLatencies []float64, projectionLag []float64, deadLetters int) {
	for _, apiPath := range []string{
		"/api/system-state/overview",
		"/api/ops/projection-lag",
		"/api/ops/dead-letters",
		"/api/ops/event-spool",
		"/api/ops/runtime-intent-lag",
		"/api/accounting/",
	} {
		result, err := client.doJSON(ctx, http.MethodGet, apiPath, tenant.AccessToken, "", nil)
		if err == nil {
			apiLatencies = append(apiLatencies, result.DurationMS)
			if lag := extractProjectionLag(result.Body); lag > 0 {
				projectionLag = append(projectionLag, lag)
			}
			if apiPath == "/api/ops/dead-letters" {
				deadLetters += countCollection(result.Body)
			}
		}
	}
	return apiLatencies, projectionLag, deadLetters
}

func (client *APIClient) CheckTenantIsolation(ctx context.Context, token, runID string) bool {
	if runID == "" {
		return true
	}
	result, err := client.doJSON(ctx, http.MethodGet, "/api/runs/"+runID, token, "", nil)
	if err == nil && result.StatusCode == http.StatusOK {
		return false
	}
	return result.StatusCode == http.StatusForbidden || result.StatusCode == http.StatusNotFound
}

func (client *APIClient) AcquireWSTicket(ctx context.Context, token string) (string, error) {
	result, err := client.doJSON(ctx, http.MethodPost, "/api/auth/ws-ticket", token, "", map[string]any{})
	if err != nil {
		return "", err
	}
	data := dataObject(result.Body)
	if ticket := firstString(data, "ticket", "token"); ticket != "" {
		return ticket, nil
	}
	return firstString(result.Body, "ticket", "token"), nil
}

func (client *APIClient) ConnectOrganizationWS(ctx context.Context, tenant TenantPlan, lastSeen int64, reconnect bool, ready func(), writer *ArtifactWriter) (samples []float64, reconnects int, err error) {
	ticket, err := client.AcquireWSTicket(ctx, tenant.AccessToken)
	if err != nil {
		return nil, 0, err
	}
	wsURL, err := client.organizationWSURL(tenant.OrganizationID, ticket)
	if err != nil {
		return nil, 0, err
	}
	dialer := websocket.Dialer{}
	conn, _, err := dialer.DialContext(ctx, wsURL, nil)
	if err != nil {
		return nil, 0, err
	}
	defer conn.Close()
	connectedAt := time.Now().UTC()
	readDone := make(chan struct{})
	go func() {
		select {
		case <-ctx.Done():
			_ = conn.Close()
		case <-readDone:
		}
	}()
	defer close(readDone)
	if ready != nil {
		ready()
	}
	if lastSeen > 0 {
		_ = conn.WriteJSON(map[string]any{"type": "resume", "last_seen_state_version": lastSeen})
	}
	for {
		select {
		case <-ctx.Done():
			return samples, reconnects, ctx.Err()
		default:
			if reconnect {
				_ = conn.SetReadDeadline(time.Now().Add(250 * time.Millisecond))
			} else {
				_ = conn.SetReadDeadline(time.Time{})
			}
			var message map[string]any
			if err := conn.ReadJSON(&message); err != nil {
				var netErr net.Error
				if errors.As(err, &netErr) && netErr.Timeout() {
					if reconnect {
						reconnects++
						return samples, reconnects, nil
					}
					continue
				}
				if websocket.IsCloseError(err, websocket.CloseNormalClosure) {
					if reconnect {
						reconnects++
					}
					return samples, reconnects, nil
				}
				return samples, reconnects, err
			}
			if message["type"] == "ping" || message["type"] == "heartbeat" {
				_ = conn.WriteJSON(map[string]any{"type": "pong"})
			}
			receivedAt := time.Now().UTC()
			message["received_at"] = receivedAt.Format(time.RFC3339Nano)
			if occurredAt := stringFromAny(message["occurred_at"]); occurredAt != "" {
				if parsed, err := time.Parse(time.RFC3339Nano, occurredAt); err == nil {
					deliveryMS := float64(receivedAt.Sub(parsed).Microseconds()) / 1000
					message["delivery_latency_ms"] = deliveryMS
					if !parsed.Before(connectedAt.Add(-1 * time.Second)) {
						samples = append(samples, deliveryMS)
					}
				}
			}
			if writer != nil {
				_ = writer.AppendJSONL(writer.Paths.WSEventsJSONL, message)
			}
		}
	}
}

func (client *APIClient) organizationWSURL(organizationID, ticket string) (string, error) {
	parsed, err := url.Parse(client.baseURL)
	if err != nil {
		return "", err
	}
	switch parsed.Scheme {
	case "https":
		parsed.Scheme = "wss"
	default:
		parsed.Scheme = "ws"
	}
	parsed.Path = "/ws/organizations/" + url.PathEscape(organizationID) + "/state/"
	values := parsed.Query()
	values.Set("ticket", ticket)
	parsed.RawQuery = values.Encode()
	return parsed.String(), nil
}

func dataObject(payload map[string]any) map[string]any {
	if payload == nil {
		return map[string]any{}
	}
	if data, ok := payload["data"].(map[string]any); ok {
		return data
	}
	return payload
}

func firstString(payload map[string]any, keys ...string) string {
	for _, key := range keys {
		if value := stringFromAny(payload[key]); value != "" {
			return value
		}
	}
	if data, ok := payload["data"].(map[string]any); ok {
		return firstString(data, keys...)
	}
	return ""
}

func stringFromAny(value any) string {
	switch typed := value.(type) {
	case string:
		return typed
	case fmt.Stringer:
		return typed.String()
	case float64:
		if typed == float64(int64(typed)) {
			return strconv.FormatInt(int64(typed), 10)
		}
		return strconv.FormatFloat(typed, 'f', -1, 64)
	default:
		return ""
	}
}

func extractProjectionLag(payload map[string]any) float64 {
	for _, candidate := range []map[string]any{payload, dataObject(payload)} {
		if projection, ok := candidate["projection"].(map[string]any); ok {
			if lag := floatFromAny(projection["lag_seconds"]); lag > 0 {
				return lag
			}
		}
		if lag := floatFromAny(candidate["lag_seconds"]); lag > 0 {
			return lag
		}
	}
	return 0
}

func floatFromAny(value any) float64 {
	switch typed := value.(type) {
	case float64:
		return typed
	case int:
		return float64(typed)
	case json.Number:
		result, _ := typed.Float64()
		return result
	case string:
		result, _ := strconv.ParseFloat(typed, 64)
		return result
	default:
		return 0
	}
}

func countCollection(payload map[string]any) int {
	if items, ok := payload["data"].([]any); ok {
		return len(items)
	}
	data := dataObject(payload)
	for _, key := range []string{"items", "results", "dead_letters"} {
		if items, ok := data[key].([]any); ok {
			return len(items)
		}
	}
	if items, ok := data["data"].([]any); ok {
		return len(items)
	}
	return 0
}
