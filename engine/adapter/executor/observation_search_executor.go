package executor

import (
	"context"
	"strings"

	"github.com/forgegraph/engine/application/port"
	"github.com/forgegraph/engine/domain/entity"
	"github.com/forgegraph/engine/domain/value"
)

// ObservationSearchExecutor retrieves curated observations by explicit query.
type ObservationSearchExecutor struct {
	client port.ObservationMemoryClient
}

// NewObservationSearchExecutor creates a new observation search executor.
func NewObservationSearchExecutor(client port.ObservationMemoryClient) *ObservationSearchExecutor {
	return &ObservationSearchExecutor{client: client}
}

// NodeType returns the node type handled by this executor.
func (e *ObservationSearchExecutor) NodeType() string {
	return string(value.NodeTypeObservationSearch)
}

// Execute searches curated observations within the requested scope.
func (e *ObservationSearchExecutor) Execute(ctx context.Context, node *entity.Node, state *entity.State) (*port.NodeExecutionResult, error) {
	client, runCtx, err := resolveObservationClient(ctx, e.client)
	if err != nil {
		return port.NewErrorResult(err), nil
	}

	scope := strings.TrimSpace(strings.ToLower(node.GetConfigString("scope")))
	graphID, runID, sessionID, err := scopedObservationFilters(runCtx, scope)
	if err != nil {
		return port.NewErrorResult(err), nil
	}

	query, err := requireStringSource(node, state, "query")
	if err != nil {
		return port.NewErrorResult(err), nil
	}
	topicKey, err := resolveOptionalStringSource(node, state, "topic_key")
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

	observations, err := client.SearchObservations(ctx, port.ObservationSearchRequest{
		TenantID:       observationTenantID(ctx, runCtx),
		Query:          query,
		GraphID:        graphID,
		RunID:          runID,
		SessionID:      sessionID,
		AgentID:        agentID,
		Scope:          scope,
		Type:           strings.TrimSpace(node.GetConfigString("type")),
		TopicKey:       topicKey,
		Limit:          limit,
		IncludeDeleted: getConfigBool(node.Config["include_deleted"]),
	})
	if err != nil {
		return port.NewErrorResult(err), nil
	}

	return port.NewSuccessResult(map[string]any{
		"query":        query,
		"scope":        scope,
		"count":        len(observations),
		"observations": observationsToMaps(observations),
	}), nil
}
