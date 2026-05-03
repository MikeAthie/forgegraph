package repository

import (
	"bytes"
	"context"
	"crypto/hmac"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"net/http"
	"net/url"
	"path"
	"strings"
	"time"

	"github.com/forgegraph/engine/application/port"
	"github.com/forgegraph/engine/domain"
	"github.com/forgegraph/engine/domain/entity"
	"github.com/google/uuid"
)

// HTTPRunRepository persists run state through signed control-plane HTTP APIs.
type HTTPRunRepository struct {
	baseURL         string
	secret          string
	client          *http.Client
	intentPublisher port.RuntimeIntentPublisher
}

type controlPlaneEnvelope[T any] struct {
	Data T `json:"data"`
}

type controlPlaneErrorEnvelope struct {
	Error struct {
		Code    string `json:"code"`
		Message string `json:"message"`
	} `json:"error"`
}

type controlPlaneError struct {
	Status  int
	Code    string
	Message string
}

func (e *controlPlaneError) Error() string {
	if e == nil {
		return ""
	}
	if e.Code != "" && e.Message != "" {
		return fmt.Sprintf("%s: %s", e.Code, e.Message)
	}
	if e.Message != "" {
		return e.Message
	}
	return fmt.Sprintf("control plane request failed with status %d", e.Status)
}

type controlPlaneCheckpoint struct {
	NodeID         string         `json:"node_id"`
	StepIndex      int            `json:"step_index"`
	StateSnapshot  map[string]any `json:"state_snapshot"`
	CompletedNodes []string       `json:"completed_nodes"`
	SkippedNodes   []string       `json:"skipped_nodes"`
	GraphJSON      string         `json:"graph_json"`
}

type controlPlaneSnapshot struct {
	RunID             string    `json:"run_id"`
	LastCompletedNode string    `json:"last_completed_node"`
	NextNode          string    `json:"next_node"`
	AttemptID         string    `json:"attempt_id"`
	UpdatedAt         time.Time `json:"updated_at"`
}

type controlPlanePauseState struct {
	PausedNodeID   string         `json:"paused_node_id"`
	StateSnapshot  map[string]any `json:"state_snapshot"`
	CompletedNodes []string       `json:"completed_nodes"`
	SkippedNodes   []string       `json:"skipped_nodes"`
	GraphJSON      string         `json:"graph_json"`
	TenantID       string         `json:"tenant_id"`
}

type controlPlaneCacheEntry struct {
	CacheKey  string    `json:"cache_key"`
	Output    any       `json:"output"`
	ExpiresAt time.Time `json:"expires_at"`
}

// NewHTTPRunRepository creates a control-plane-backed run repository.
func NewHTTPRunRepository(
	baseURL,
	secret string,
	client *http.Client,
	intentPublisher port.RuntimeIntentPublisher,
) *HTTPRunRepository {
	if client == nil {
		client = &http.Client{Timeout: 10 * time.Second}
	}
	return &HTTPRunRepository{
		baseURL:         strings.TrimRight(baseURL, "/"),
		secret:          secret,
		client:          client,
		intentPublisher: intentPublisher,
	}
}

func (r *HTTPRunRepository) GetRun(ctx context.Context, runID string) (*entity.Run, error) {
	var run entity.Run
	err := r.do(ctx, http.MethodGet, r.runPath(runID), nil, &run)
	if err != nil {
		var apiErr *controlPlaneError
		if errors.As(err, &apiErr) && apiErr.Status == http.StatusNotFound {
			return nil, domain.ErrRunNotFound
		}
		return nil, err
	}
	return &run, nil
}

func (r *HTTPRunRepository) UpdateRunStatus(ctx context.Context, runID string, status string) error {
	return r.publishIntent(ctx, "set_run_status", runID, "", "", map[string]any{"status": status})
}

func (r *HTTPRunRepository) UpdateRunOutput(ctx context.Context, runID string, output map[string]any) error {
	return r.publishIntent(ctx, "set_run_status", runID, "", "", map[string]any{"output_json": output})
}

func (r *HTTPRunRepository) UpdateRunError(ctx context.Context, runID string, errorMsg string) error {
	return r.publishIntent(
		ctx,
		"set_run_status",
		runID,
		"",
		"",
		map[string]any{"error_message": errorMsg},
	)
}

func (r *HTTPRunRepository) SetRunEnded(ctx context.Context, runID string, status string, output map[string]any, errorMsg string) error {
	payload := map[string]any{
		"status":            status,
		"output_json":       output,
		"error_message":     errorMsg,
		"ended_at":          time.Now().UTC().Format(time.RFC3339Nano),
		"clear_pause_state": true,
	}
	return r.publishIntent(ctx, "set_run_status", runID, "", "", payload)
}

func (r *HTTPRunRepository) SavePauseState(
	ctx context.Context,
	runID,
	pausedNodeID string,
	stateSnapshot map[string]any,
	completedNodes []string,
	skippedNodes []string,
	graphJSON string,
	tenantID string,
) error {
	if r.intentPublisher != nil {
		return fmt.Errorf("direct pause-state writes are disabled when runtime intents are enabled")
	}
	payload := controlPlanePauseState{
		PausedNodeID:   pausedNodeID,
		StateSnapshot:  stateSnapshot,
		CompletedNodes: append([]string(nil), completedNodes...),
		SkippedNodes:   append([]string(nil), skippedNodes...),
		GraphJSON:      graphJSON,
		TenantID:       tenantID,
	}
	return r.do(ctx, http.MethodPut, r.runPauseStatePath(runID), payload, nil)
}

func (r *HTTPRunRepository) LoadPauseState(
	ctx context.Context,
	runID string,
) (
	pausedNodeID string,
	stateSnapshot map[string]any,
	completedNodes []string,
	skippedNodes []string,
	graphJSON string,
	tenantID string,
	err error,
) {
	var pause controlPlanePauseState
	err = r.do(ctx, http.MethodGet, r.runPauseStatePath(runID), nil, &pause)
	if err != nil {
		var apiErr *controlPlaneError
		if errors.As(err, &apiErr) && apiErr.Status == http.StatusNotFound {
			return "", nil, nil, nil, "", "", domain.ErrRunNotFound
		}
		return "", nil, nil, nil, "", "", err
	}
	return pause.PausedNodeID, pause.StateSnapshot, pause.CompletedNodes, pause.SkippedNodes, pause.GraphJSON, pause.TenantID, nil
}

func (r *HTTPRunRepository) ClearPauseState(ctx context.Context, runID string) error {
	if r.intentPublisher != nil {
		return fmt.Errorf("direct pause-state clears are disabled when runtime intents are enabled")
	}
	err := r.do(ctx, http.MethodDelete, r.runPauseStatePath(runID), nil, nil)
	if err != nil {
		var apiErr *controlPlaneError
		if errors.As(err, &apiErr) && apiErr.Status == http.StatusNotFound {
			return domain.ErrRunNotFound
		}
		return err
	}
	return nil
}

func (r *HTTPRunRepository) SaveCheckpoint(ctx context.Context, runID, nodeID string, stepIndex int, stateSnapshot map[string]any, completedNodes []string, skippedNodes []string, graphJSON string) error {
	payload := controlPlaneCheckpoint{
		NodeID:         nodeID,
		StepIndex:      stepIndex,
		StateSnapshot:  stateSnapshot,
		CompletedNodes: append([]string(nil), completedNodes...),
		SkippedNodes:   append([]string(nil), skippedNodes...),
		GraphJSON:      graphJSON,
	}
	return r.publishIntent(
		ctx,
		"store_checkpoint",
		runID,
		"",
		"",
		map[string]any{
			"node_id":         payload.NodeID,
			"step_index":      payload.StepIndex,
			"state_snapshot":  payload.StateSnapshot,
			"completed_nodes": payload.CompletedNodes,
			"skipped_nodes":   payload.SkippedNodes,
			"graph_json":      payload.GraphJSON,
		},
	)
}

func (r *HTTPRunRepository) LoadLatestCheckpoint(ctx context.Context, runID string) (nodeID string, stepIndex int, stateSnapshot map[string]any, completedNodes []string, skippedNodes []string, graphJSON string, err error) {
	var checkpoint controlPlaneCheckpoint
	err = r.do(ctx, http.MethodGet, r.runCheckpointPath(runID), nil, &checkpoint)
	if err != nil {
		var apiErr *controlPlaneError
		if errors.As(err, &apiErr) && apiErr.Status == http.StatusNotFound {
			return "", 0, nil, nil, nil, "", domain.ErrCheckpointNotFound
		}
		return "", 0, nil, nil, nil, "", err
	}
	return checkpoint.NodeID, checkpoint.StepIndex, checkpoint.StateSnapshot, checkpoint.CompletedNodes, checkpoint.SkippedNodes, checkpoint.GraphJSON, nil
}

func (r *HTTPRunRepository) ClearCheckpoints(ctx context.Context, runID string) error {
	err := r.do(ctx, http.MethodDelete, r.runCheckpointPath(runID), nil, nil)
	if err != nil {
		var apiErr *controlPlaneError
		if errors.As(err, &apiErr) && apiErr.Status == http.StatusNotFound {
			return domain.ErrCheckpointNotFound
		}
		return err
	}
	return nil
}

func (r *HTTPRunRepository) LoadRunSnapshot(ctx context.Context, runID string) (*port.RunResumeSnapshot, error) {
	var snapshot controlPlaneSnapshot
	err := r.do(ctx, http.MethodGet, r.runSnapshotPath(runID), nil, &snapshot)
	if err != nil {
		var apiErr *controlPlaneError
		if errors.As(err, &apiErr) && apiErr.Status == http.StatusNotFound {
			return nil, domain.ErrCheckpointNotFound
		}
		return nil, err
	}
	return &port.RunResumeSnapshot{
		RunID:             snapshot.RunID,
		LastCompletedNode: snapshot.LastCompletedNode,
		NextNode:          snapshot.NextNode,
		AttemptID:         snapshot.AttemptID,
		UpdatedAt:         snapshot.UpdatedAt,
	}, nil
}

func (r *HTTPRunRepository) GetCachedNodeResult(ctx context.Context, cacheKey string) (output any, found bool, err error) {
	var entry controlPlaneCacheEntry
	err = r.do(ctx, http.MethodGet, r.cachePath(cacheKey), nil, &entry)
	if err != nil {
		var apiErr *controlPlaneError
		if errors.As(err, &apiErr) && apiErr.Status == http.StatusNotFound {
			return nil, false, nil
		}
		return nil, false, err
	}
	return entry.Output, true, nil
}

func (r *HTTPRunRepository) SaveCachedNodeResult(ctx context.Context, cacheKey string, output any, ttlSeconds int) error {
	if ttlSeconds <= 0 {
		return nil
	}
	payload := map[string]any{
		"output":      output,
		"ttl_seconds": ttlSeconds,
	}
	return r.do(ctx, http.MethodPut, r.cachePath(cacheKey), payload, nil)
}

func (r *HTTPRunRepository) CreateNodeRun(ctx context.Context, nodeRun *entity.NodeRun) error {
	if nodeRun == nil {
		return nil
	}
	return r.publishNodeRunIntent(ctx, nodeRun)
}

func (r *HTTPRunRepository) UpdateNodeRun(ctx context.Context, nodeRun *entity.NodeRun) error {
	if nodeRun == nil {
		return nil
	}
	return r.publishNodeRunIntent(ctx, nodeRun)
}

func (r *HTTPRunRepository) GetNodeRun(ctx context.Context, runID, nodeID string) (*entity.NodeRun, error) {
	var nodeRun entity.NodeRun
	err := r.do(ctx, http.MethodGet, r.runNodeRunPath(runID, nodeID), nil, &nodeRun)
	if err != nil {
		var apiErr *controlPlaneError
		if errors.As(err, &apiErr) && apiErr.Status == http.StatusNotFound {
			return nil, domain.ErrNodeNotFound
		}
		return nil, err
	}
	return &nodeRun, nil
}

func (r *HTTPRunRepository) GetNodeRunsByRunID(ctx context.Context, runID string) ([]*entity.NodeRun, error) {
	var nodeRuns []*entity.NodeRun
	err := r.do(ctx, http.MethodGet, r.runNodeRunListPath(runID), nil, &nodeRuns)
	if err != nil {
		var apiErr *controlPlaneError
		if errors.As(err, &apiErr) && apiErr.Status == http.StatusNotFound {
			return nil, domain.ErrRunNotFound
		}
		return nil, err
	}
	return nodeRuns, nil
}

func (r *HTTPRunRepository) publishNodeRunIntent(ctx context.Context, nodeRun *entity.NodeRun) error {
	if nodeRun == nil {
		return nil
	}
	payload := map[string]any{
		"id":         nodeRun.ID,
		"node_id":    nodeRun.NodeID,
		"node_type":  nodeRun.NodeType,
		"status":     nodeRun.Status,
		"attempt":    nodeRun.Attempt,
		"started_at": nodeRun.StartedAt.UTC().Format(time.RFC3339Nano),
		"trace_id":   nodeRun.TraceID,
		"span_id":    nodeRun.SpanID,
	}
	if nodeRun.EndedAt != nil {
		payload["ended_at"] = nodeRun.EndedAt.UTC().Format(time.RFC3339Nano)
	}
	if nodeRun.InputJSON != nil {
		payload["input_json"] = nodeRun.InputJSON
	}
	if nodeRun.OutputJSON != nil {
		payload["output_json"] = nodeRun.OutputJSON
	}
	if nodeRun.ErrorJSON != nil {
		payload["error_json"] = nodeRun.ErrorJSON
	}
	return r.publishIntent(
		ctx,
		"upsert_node_run",
		nodeRun.RunID,
		"",
		nodeRun.TraceID,
		payload,
	)
}

func (r *HTTPRunRepository) publishIntent(
	ctx context.Context,
	intentType string,
	runID string,
	attemptID string,
	traceID string,
	payload map[string]any,
) error {
	if r.intentPublisher == nil {
		return fmt.Errorf("runtime intent publisher is not configured")
	}
	if attemptID == "" {
		attemptID = port.AttemptIDFrom(ctx)
	}
	if attemptID == "" {
		return fmt.Errorf("runtime intent attempt_id is required")
	}
	intent := &port.RuntimeIntentEnvelope{
		IntentID:   deterministicIntentID(intentType, runID, attemptID, payload),
		IntentType: intentType,
		RunID:      runID,
		AttemptID:  attemptID,
		Timestamp:  time.Now().UTC().Format(time.RFC3339Nano),
		TraceID:    traceID,
		Payload:    payload,
	}
	return r.intentPublisher.Publish(ctx, intent)
}

func deterministicIntentID(intentType string, runID string, attemptID string, payload map[string]any) string {
	body, err := json.Marshal(payload)
	if err != nil {
		body = []byte(fmt.Sprintf("%v", payload))
	}
	seed := strings.Join([]string{intentType, runID, attemptID, string(body)}, "\x00")
	return uuid.NewSHA1(uuid.NameSpaceOID, []byte(seed)).String()
}

func (r *HTTPRunRepository) updateRun(ctx context.Context, runID string, payload map[string]any) error {
	err := r.do(ctx, http.MethodPatch, r.runPath(runID), payload, nil)
	if err != nil {
		var apiErr *controlPlaneError
		if errors.As(err, &apiErr) && apiErr.Status == http.StatusNotFound {
			return domain.ErrRunNotFound
		}
		return err
	}
	return nil
}

func (r *HTTPRunRepository) upsertNodeRun(ctx context.Context, nodeRun *entity.NodeRun) (*entity.NodeRun, error) {
	payload := map[string]any{
		"id":         nodeRun.ID,
		"node_type":  nodeRun.NodeType,
		"status":     nodeRun.Status,
		"attempt":    nodeRun.Attempt,
		"started_at": nodeRun.StartedAt.UTC().Format(time.RFC3339Nano),
		"trace_id":   nodeRun.TraceID,
		"span_id":    nodeRun.SpanID,
	}
	if nodeRun.EndedAt != nil {
		payload["ended_at"] = nodeRun.EndedAt.UTC().Format(time.RFC3339Nano)
	}
	if nodeRun.InputJSON != nil {
		payload["input_json"] = nodeRun.InputJSON
	}
	if nodeRun.OutputJSON != nil {
		payload["output_json"] = nodeRun.OutputJSON
	}
	if nodeRun.ErrorJSON != nil {
		payload["error_json"] = nodeRun.ErrorJSON
	}

	var persisted entity.NodeRun
	err := r.do(ctx, http.MethodPut, r.runNodeRunPath(nodeRun.RunID, nodeRun.NodeID), payload, &persisted)
	if err != nil {
		var apiErr *controlPlaneError
		if errors.As(err, &apiErr) && apiErr.Status == http.StatusNotFound {
			return nil, domain.ErrRunNotFound
		}
		return nil, err
	}
	return &persisted, nil
}

func (r *HTTPRunRepository) do(ctx context.Context, method, relativePath string, payload any, out any) error {
	body, err := r.marshalBody(payload)
	if err != nil {
		return err
	}

	req, err := http.NewRequestWithContext(ctx, method, r.resolveURL(relativePath), bytes.NewReader(body))
	if err != nil {
		return err
	}
	if len(body) > 0 {
		req.Header.Set("Content-Type", "application/json")
	}
	r.sign(req, body)

	resp, err := r.client.Do(req)
	if err != nil {
		return err
	}
	defer resp.Body.Close()

	respBody, err := io.ReadAll(resp.Body)
	if err != nil {
		return err
	}

	if resp.StatusCode >= http.StatusBadRequest {
		return decodeControlPlaneError(resp.StatusCode, respBody)
	}
	if out == nil || len(respBody) == 0 {
		return nil
	}

	wrapper := controlPlaneEnvelope[json.RawMessage]{}
	if err := json.Unmarshal(respBody, &wrapper); err != nil {
		return err
	}
	if len(wrapper.Data) == 0 {
		return nil
	}
	return json.Unmarshal(wrapper.Data, out)
}

func (r *HTTPRunRepository) marshalBody(payload any) ([]byte, error) {
	if payload == nil {
		return nil, nil
	}
	body, err := json.Marshal(payload)
	if err != nil {
		return nil, err
	}
	return body, nil
}

func (r *HTTPRunRepository) resolveURL(relativePath string) string {
	base, err := url.Parse(r.baseURL)
	if err != nil {
		return r.baseURL + relativePath
	}
	base.Path = path.Join(base.Path, relativePath)
	return base.String()
}

func (r *HTTPRunRepository) sign(req *http.Request, body []byte) {
	if req == nil || r.secret == "" {
		return
	}
	timestamp := fmt.Sprintf("%d", time.Now().UnixMilli())
	message := append([]byte(timestamp+"."), body...)
	mac := hmac.New(sha256.New, []byte(r.secret))
	mac.Write(message)
	req.Header.Set("X-Forgegraph-Timestamp", timestamp)
	req.Header.Set("X-Forgegraph-Signature", hex.EncodeToString(mac.Sum(nil)))
}

func decodeControlPlaneError(statusCode int, body []byte) error {
	envelope := controlPlaneErrorEnvelope{}
	if err := json.Unmarshal(body, &envelope); err == nil && (envelope.Error.Code != "" || envelope.Error.Message != "") {
		return &controlPlaneError{
			Status:  statusCode,
			Code:    envelope.Error.Code,
			Message: envelope.Error.Message,
		}
	}
	message := strings.TrimSpace(string(body))
	return &controlPlaneError{
		Status:  statusCode,
		Message: message,
	}
}

func (r *HTTPRunRepository) runPath(runID string) string {
	return fmt.Sprintf("/api/engine/runs/%s", runID)
}

func (r *HTTPRunRepository) runPauseStatePath(runID string) string {
	return fmt.Sprintf("/api/engine/runs/%s/pause-state", runID)
}

func (r *HTTPRunRepository) runCheckpointPath(runID string) string {
	return fmt.Sprintf("/api/engine/runs/%s/checkpoint", runID)
}

func (r *HTTPRunRepository) runSnapshotPath(runID string) string {
	return fmt.Sprintf("/api/engine/runs/%s/snapshot", runID)
}

func (r *HTTPRunRepository) runNodeRunListPath(runID string) string {
	return fmt.Sprintf("/api/engine/runs/%s/node-runs", runID)
}

func (r *HTTPRunRepository) runNodeRunPath(runID, nodeID string) string {
	return fmt.Sprintf("/api/engine/runs/%s/node-runs/%s", runID, url.PathEscape(nodeID))
}

func (r *HTTPRunRepository) cachePath(cacheKey string) string {
	return fmt.Sprintf("/api/engine/node-cache/%s", url.PathEscape(cacheKey))
}
