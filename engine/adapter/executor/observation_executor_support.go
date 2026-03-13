package executor

import (
	"context"
	"fmt"
	"strings"
	"time"

	"github.com/forgegraph/engine/application/port"
	"github.com/forgegraph/engine/domain"
	"github.com/forgegraph/engine/domain/entity"
)

func resolveObservationClient(
	ctx context.Context,
	fallback port.ObservationMemoryClient,
) (port.ObservationMemoryClient, *port.RunContext, error) {
	runCtx := port.RunContextFrom(ctx)
	if runCtx == nil {
		return nil, nil, domain.NewValidationError("runtime", "observation nodes require run context")
	}

	client := fallback
	if client == nil {
		client = runCtx.ObservationClient
	}
	if client == nil {
		return nil, runCtx, domain.NewValidationError("client", "curated memory client not configured")
	}

	if observationTenantID(ctx, runCtx) == "" {
		return nil, runCtx, domain.NewValidationError("tenant_id", "tenant_id is required for curated memory")
	}

	return client, runCtx, nil
}

func observationTenantID(ctx context.Context, runCtx *port.RunContext) string {
	if runCtx != nil && strings.TrimSpace(runCtx.TenantID) != "" {
		return strings.TrimSpace(runCtx.TenantID)
	}
	return strings.TrimSpace(port.TenantIDFrom(ctx))
}

func validateObservationScopeAvailability(runCtx *port.RunContext, scope string) error {
	scope = strings.TrimSpace(strings.ToLower(scope))
	switch scope {
	case "graph":
		if runCtx == nil || strings.TrimSpace(runCtx.GraphID) == "" {
			return domain.NewValidationError("scope", "graph scope requires graph_id in runtime context")
		}
	case "run":
		if runCtx == nil || strings.TrimSpace(runCtx.RunID) == "" {
			return domain.NewValidationError("scope", "run scope requires run_id in runtime context")
		}
	case "session":
		if runCtx == nil || strings.TrimSpace(runCtx.SessionID) == "" {
			return domain.NewValidationError("scope", "session scope requires session_id in runtime context")
		}
	default:
		return domain.NewValidationError("scope", "scope must be graph, run, or session")
	}
	return nil
}

func scopedObservationFilters(runCtx *port.RunContext, scope string) (string, string, string, error) {
	if err := validateObservationScopeAvailability(runCtx, scope); err != nil {
		return "", "", "", err
	}

	switch strings.TrimSpace(strings.ToLower(scope)) {
	case "graph":
		return strings.TrimSpace(runCtx.GraphID), "", "", nil
	case "run":
		return "", strings.TrimSpace(runCtx.RunID), "", nil
	case "session":
		return "", "", strings.TrimSpace(runCtx.SessionID), nil
	default:
		return "", "", "", domain.NewValidationError("scope", "scope must be graph, run, or session")
	}
}

func resolveOptionalStringSource(node *entity.Node, state *entity.State, field string) (string, error) {
	if node == nil {
		return "", domain.NewValidationError(field, "node is required")
	}

	staticValue := node.GetConfigString(field)
	pathValue := node.GetConfigString(field + "_path")
	templateValue := node.GetConfigString(field + "_template")

	populatedSources := 0
	if strings.TrimSpace(staticValue) != "" {
		populatedSources++
	}
	if strings.TrimSpace(pathValue) != "" {
		populatedSources++
	}
	if strings.TrimSpace(templateValue) != "" {
		populatedSources++
	}
	if populatedSources > 1 {
		return "", domain.NewValidationError(
			field,
			fmt.Sprintf("only one of %s, %s_path, or %s_template may be set", field, field, field),
		)
	}

	if strings.TrimSpace(pathValue) != "" {
		if state != nil {
			if value, ok := state.Get(pathValue); ok {
				return strings.TrimSpace(fmt.Sprintf("%v", value)), nil
			}
			if value := resolveNestedPath(pathValue, state); value != nil {
				return strings.TrimSpace(fmt.Sprintf("%v", value)), nil
			}
		}
		return "", domain.NewValidationError(field+"_path", field+"_path did not resolve to a value")
	}

	if strings.TrimSpace(templateValue) != "" {
		return strings.TrimSpace(SubstituteTemplate(templateValue, state)), nil
	}

	return strings.TrimSpace(staticValue), nil
}

func requireStringSource(node *entity.Node, state *entity.State, field string) (string, error) {
	value, err := resolveOptionalStringSource(node, state, field)
	if err != nil {
		return "", err
	}
	if strings.TrimSpace(value) == "" {
		return "", domain.NewValidationError(field, fmt.Sprintf("%s requires a non-empty value", field))
	}
	return value, nil
}

func optionalBoolPointer(config map[string]any, key string) *bool {
	raw, ok := config[key]
	if !ok {
		return nil
	}
	value := getConfigBool(raw)
	return &value
}

func observationToMap(observation port.Observation) map[string]any {
	output := map[string]any{
		"id":              observation.ID,
		"tenant_id":       observation.TenantID,
		"graph_id":        observation.GraphID,
		"run_id":          observation.RunID,
		"session_id":      observation.SessionID,
		"agent_id":        observation.AgentID,
		"type":            observation.Type,
		"title":           observation.Title,
		"content":         observation.Content,
		"scope":           observation.Scope,
		"topic_key":       observation.TopicKey,
		"tool_name":       observation.ToolName,
		"revision_count":  observation.RevisionCount,
		"duplicate_count": observation.DuplicateCount,
		"last_seen_at":    formatObservationTime(observation.LastSeenAt),
		"created_at":      formatObservationTime(observation.CreatedAt),
		"updated_at":      formatObservationTime(observation.UpdatedAt),
		"is_deleted":      observation.IsDeleted,
	}
	if observation.DeletedAt != nil {
		output["deleted_at"] = formatObservationTime(*observation.DeletedAt)
	} else {
		output["deleted_at"] = nil
	}
	return output
}

func observationsToMaps(observations []port.Observation) []map[string]any {
	if len(observations) == 0 {
		return []map[string]any{}
	}
	result := make([]map[string]any, 0, len(observations))
	for _, observation := range observations {
		result = append(result, observationToMap(observation))
	}
	return result
}

func formatObservationTime(value time.Time) string {
	if value.IsZero() {
		return ""
	}
	return value.UTC().Format(time.RFC3339)
}
