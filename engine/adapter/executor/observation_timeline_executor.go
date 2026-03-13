package executor

import (
	"context"
	"strings"

	"github.com/forgegraph/engine/application/port"
	"github.com/forgegraph/engine/domain/entity"
	"github.com/forgegraph/engine/domain/value"
)

// ObservationTimelineExecutor retrieves recent curated observations within a scope.
type ObservationTimelineExecutor struct {
	client port.ObservationMemoryClient
}

// NewObservationTimelineExecutor creates a new observation timeline executor.
func NewObservationTimelineExecutor(client port.ObservationMemoryClient) *ObservationTimelineExecutor {
	return &ObservationTimelineExecutor{client: client}
}

// NodeType returns the node type handled by this executor.
func (e *ObservationTimelineExecutor) NodeType() string {
	return string(value.NodeTypeObservationTimeline)
}

// Execute returns recent curated observations for the requested runtime scope.
func (e *ObservationTimelineExecutor) Execute(ctx context.Context, node *entity.Node, state *entity.State) (*port.NodeExecutionResult, error) {
	client, runCtx, err := resolveObservationClient(ctx, e.client)
	if err != nil {
		return port.NewErrorResult(err), nil
	}

	scope := strings.TrimSpace(strings.ToLower(node.GetConfigString("scope")))
	graphID, runID, sessionID, err := scopedObservationFilters(runCtx, scope)
	if err != nil {
		return port.NewErrorResult(err), nil
	}
	agentID, err := resolveOptionalStringSource(node, state, "agent_id")
	if err != nil {
		return port.NewErrorResult(err), nil
	}

	limit := getConfigInt(node.Config["limit"])
	if limit <= 0 {
		limit = 20
	}

	observations, err := client.GetTimeline(ctx, port.ObservationTimelineRequest{
		TenantID:       observationTenantID(ctx, runCtx),
		GraphID:        graphID,
		RunID:          runID,
		SessionID:      sessionID,
		AgentID:        agentID,
		Scope:          scope,
		Limit:          limit,
		IncludeDeleted: getConfigBool(node.Config["include_deleted"]),
	})
	if err != nil {
		return port.NewErrorResult(err), nil
	}

	return port.NewSuccessResult(map[string]any{
		"scope":        scope,
		"count":        len(observations),
		"observations": observationsToMaps(observations),
	}), nil
}
