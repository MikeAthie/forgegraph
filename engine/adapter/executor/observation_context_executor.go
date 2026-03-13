package executor

import (
	"context"

	"github.com/forgegraph/engine/application/port"
	"github.com/forgegraph/engine/domain/entity"
	"github.com/forgegraph/engine/domain/value"
)

// ObservationContextExecutor retrieves context-ready curated observations.
type ObservationContextExecutor struct {
	client port.ObservationMemoryClient
}

// NewObservationContextExecutor creates a new observation context executor.
func NewObservationContextExecutor(client port.ObservationMemoryClient) *ObservationContextExecutor {
	return &ObservationContextExecutor{client: client}
}

// NodeType returns the node type handled by this executor.
func (e *ObservationContextExecutor) NodeType() string {
	return string(value.NodeTypeObservationContext)
}

// Execute retrieves context-ready curated observations for the current runtime.
func (e *ObservationContextExecutor) Execute(ctx context.Context, node *entity.Node, state *entity.State) (*port.NodeExecutionResult, error) {
	client, runCtx, err := resolveObservationClient(ctx, e.client)
	if err != nil {
		return port.NewErrorResult(err), nil
	}

	query, err := requireStringSource(node, state, "query")
	if err != nil {
		return port.NewErrorResult(err), nil
	}
	agentID, err := resolveOptionalStringSource(node, state, "agent_id")
	if err != nil {
		return port.NewErrorResult(err), nil
	}

	limit := getConfigInt(node.Config["limit"])
	if limit <= 0 {
		limit = 10
	}

	response, err := client.GetContext(ctx, port.ObservationContextRequest{
		TenantID:  observationTenantID(ctx, runCtx),
		GraphID:   runCtx.GraphID,
		RunID:     runCtx.RunID,
		SessionID: runCtx.SessionID,
		AgentID:   agentID,
		Query:     query,
		Limit:     limit,
	})
	if err != nil {
		return port.NewErrorResult(err), nil
	}

	return port.NewSuccessResult(map[string]any{
		"query":        query,
		"count":        len(response.Observations),
		"observations": observationsToMaps(response.Observations),
		"degraded":     response.Degraded,
		"strategies":   append([]string(nil), response.Strategies...),
	}), nil
}
