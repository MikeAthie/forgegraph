package executor

import (
	"context"
	"strings"

	"github.com/forgegraph/engine/application/port"
	"github.com/forgegraph/engine/domain/entity"
	"github.com/forgegraph/engine/domain/value"
)

// ObservationSaveExecutor persists curated observations through the memory gRPC API.
type ObservationSaveExecutor struct {
	client port.ObservationMemoryClient
}

// NewObservationSaveExecutor creates a new observation save executor.
func NewObservationSaveExecutor(client port.ObservationMemoryClient) *ObservationSaveExecutor {
	return &ObservationSaveExecutor{client: client}
}

// NodeType returns the node type handled by this executor.
func (e *ObservationSaveExecutor) NodeType() string {
	return string(value.NodeTypeObservationSave)
}

// Execute saves a curated observation and returns the persisted payload.
func (e *ObservationSaveExecutor) Execute(ctx context.Context, node *entity.Node, state *entity.State) (*port.NodeExecutionResult, error) {
	client, runCtx, err := resolveObservationClient(ctx, e.client)
	if err != nil {
		return port.NewErrorResult(err), nil
	}

	scope := strings.TrimSpace(strings.ToLower(node.GetConfigString("scope")))
	if err := validateObservationScopeAvailability(runCtx, scope); err != nil {
		return port.NewErrorResult(err), nil
	}

	content, err := requireStringSource(node, state, "content")
	if err != nil {
		return port.NewErrorResult(err), nil
	}
	title, err := resolveOptionalStringSource(node, state, "title")
	if err != nil {
		return port.NewErrorResult(err), nil
	}
	topicKey, err := resolveOptionalStringSource(node, state, "topic_key")
	if err != nil {
		return port.NewErrorResult(err), nil
	}
	toolName, err := resolveOptionalStringSource(node, state, "tool_name")
	if err != nil {
		return port.NewErrorResult(err), nil
	}
	agentID, err := resolveOptionalStringSource(node, state, "agent_id")
	if err != nil {
		return port.NewErrorResult(err), nil
	}

	observation, err := client.SaveObservation(ctx, port.ObservationSaveRequest{
		TenantID:      observationTenantID(ctx, runCtx),
		ObservationID: strings.TrimSpace(node.GetConfigString("observation_id")),
		GraphID:       strings.TrimSpace(runCtx.GraphID),
		RunID:         strings.TrimSpace(runCtx.RunID),
		SessionID:     strings.TrimSpace(runCtx.SessionID),
		AgentID:       agentID,
		Type:          strings.TrimSpace(node.GetConfigString("type")),
		Title:         title,
		Content:       content,
		Scope:         scope,
		TopicKey:      topicKey,
		ToolName:      toolName,
		Dedupe:        optionalBoolPointer(node.Config, "dedupe"),
		UpdateTopic:   optionalBoolPointer(node.Config, "update_topic"),
	})
	if err != nil {
		return port.NewErrorResult(err), nil
	}

	return port.NewSuccessResult(map[string]any{
		"saved":       true,
		"scope":       scope,
		"observation": observationToMap(observation),
	}), nil
}
