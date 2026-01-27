package repository

import (
	"context"
	"database/sql"
	"encoding/json"
	"fmt"
	"time"

	"github.com/forgegraph/engine/domain"
	"github.com/forgegraph/engine/domain/entity"
)

// PostgresRunRepository implements RunRepository using PostgreSQL.
type PostgresRunRepository struct {
	db *sql.DB
}

// NewPostgresRunRepository creates a new PostgreSQL-based run repository
func NewPostgresRunRepository(db *sql.DB) *PostgresRunRepository {
	return &PostgresRunRepository{db: db}
}

// GetRun retrieves a run by ID
func (r *PostgresRunRepository) GetRun(ctx context.Context, runID string) (*entity.Run, error) {
	query := `
		SELECT id, graph_version_id, status, input_json, output_json, error_message,
		       started_at, ended_at
		FROM runs
		WHERE id = $1
	`

	var run entity.Run
	var inputJSON, outputJSON sql.NullString
	var errorMessage sql.NullString
	var endedAt sql.NullTime

	err := r.db.QueryRowContext(ctx, query, runID).Scan(
		&run.ID,
		&run.GraphVersionID,
		&run.Status,
		&inputJSON,
		&outputJSON,
		&errorMessage,
		&run.StartedAt,
		&endedAt,
	)

	if err == sql.ErrNoRows {
		return nil, domain.ErrRunNotFound
	}
	if err != nil {
		return nil, fmt.Errorf("failed to get run: %w", err)
	}

	// Parse JSON fields
	if inputJSON.Valid && inputJSON.String != "" {
		if err := json.Unmarshal([]byte(inputJSON.String), &run.InputJSON); err != nil {
			return nil, fmt.Errorf("failed to parse input_json: %w", err)
		}
	}
	if outputJSON.Valid && outputJSON.String != "" {
		if err := json.Unmarshal([]byte(outputJSON.String), &run.OutputJSON); err != nil {
			return nil, fmt.Errorf("failed to parse output_json: %w", err)
		}
	}
	if errorMessage.Valid {
		run.ErrorMessage = errorMessage.String
	}
	if endedAt.Valid {
		run.EndedAt = &endedAt.Time
	}

	return &run, nil
}

// UpdateRunStatus updates the status of a run
func (r *PostgresRunRepository) UpdateRunStatus(ctx context.Context, runID string, status string) error {
	query := `UPDATE runs SET status = $1, updated_at = $2 WHERE id = $3`

	result, err := r.db.ExecContext(ctx, query, status, time.Now(), runID)
	if err != nil {
		return fmt.Errorf("failed to update run status: %w", err)
	}

	rowsAffected, err := result.RowsAffected()
	if err != nil {
		return fmt.Errorf("failed to check rows affected: %w", err)
	}
	if rowsAffected == 0 {
		return domain.ErrRunNotFound
	}

	return nil
}

// UpdateRunOutput sets the final output JSON for a completed run
func (r *PostgresRunRepository) UpdateRunOutput(ctx context.Context, runID string, output map[string]any) error {
	outputBytes, err := json.Marshal(output)
	if err != nil {
		return fmt.Errorf("failed to marshal output: %w", err)
	}

	query := `UPDATE runs SET output_json = $1, updated_at = $2 WHERE id = $3`

	result, err := r.db.ExecContext(ctx, query, string(outputBytes), time.Now(), runID)
	if err != nil {
		return fmt.Errorf("failed to update run output: %w", err)
	}

	rowsAffected, err := result.RowsAffected()
	if err != nil {
		return fmt.Errorf("failed to check rows affected: %w", err)
	}
	if rowsAffected == 0 {
		return domain.ErrRunNotFound
	}

	return nil
}

// UpdateRunError sets the error message for a failed run
func (r *PostgresRunRepository) UpdateRunError(ctx context.Context, runID string, errorMsg string) error {
	query := `UPDATE runs SET error_message = $1, updated_at = $2 WHERE id = $3`

	result, err := r.db.ExecContext(ctx, query, errorMsg, time.Now(), runID)
	if err != nil {
		return fmt.Errorf("failed to update run error: %w", err)
	}

	rowsAffected, err := result.RowsAffected()
	if err != nil {
		return fmt.Errorf("failed to check rows affected: %w", err)
	}
	if rowsAffected == 0 {
		return domain.ErrRunNotFound
	}

	return nil
}

// SetRunEnded marks a run as ended with the given status and optional output/error
func (r *PostgresRunRepository) SetRunEnded(ctx context.Context, runID string, status string, output map[string]any, errorMsg string) error {
	var outputStr *string
	if output != nil {
		outputBytes, err := json.Marshal(output)
		if err != nil {
			return fmt.Errorf("failed to marshal output: %w", err)
		}
		s := string(outputBytes)
		outputStr = &s
	}

	var errorMsgPtr *string
	if errorMsg != "" {
		errorMsgPtr = &errorMsg
	}

	query := `
		UPDATE runs
		SET status = $1, output_json = $2, error_message = $3, ended_at = $4, updated_at = $5
		WHERE id = $6
	`

	now := time.Now()
	result, err := r.db.ExecContext(ctx, query, status, outputStr, errorMsgPtr, now, now, runID)
	if err != nil {
		return fmt.Errorf("failed to set run ended: %w", err)
	}

	rowsAffected, err := result.RowsAffected()
	if err != nil {
		return fmt.Errorf("failed to check rows affected: %w", err)
	}
	if rowsAffected == 0 {
		return domain.ErrRunNotFound
	}

	return nil
}

// CreateNodeRun creates a new node run record
func (r *PostgresRunRepository) CreateNodeRun(ctx context.Context, nodeRun *entity.NodeRun) error {
	inputBytes, err := json.Marshal(nodeRun.InputJSON)
	if err != nil {
		return fmt.Errorf("failed to marshal input: %w", err)
	}

	query := `
		INSERT INTO node_runs (id, run_id, node_id, node_type, status, attempt,
		                       input_json, started_at, created_at, updated_at)
		VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
	`

	now := time.Now()
	_, err = r.db.ExecContext(ctx, query,
		nodeRun.ID,
		nodeRun.RunID,
		nodeRun.NodeID,
		nodeRun.NodeType,
		nodeRun.Status,
		nodeRun.Attempt,
		string(inputBytes),
		nodeRun.StartedAt,
		now,
		now,
	)

	if err != nil {
		return fmt.Errorf("failed to create node run: %w", err)
	}

	return nil
}

// UpdateNodeRun updates an existing node run record
func (r *PostgresRunRepository) UpdateNodeRun(ctx context.Context, nodeRun *entity.NodeRun) error {
	var outputStr *string
	if nodeRun.OutputJSON != nil {
		outputBytes, err := json.Marshal(nodeRun.OutputJSON)
		if err != nil {
			return fmt.Errorf("failed to marshal output: %w", err)
		}
		s := string(outputBytes)
		outputStr = &s
	}

	var errorStr *string
	if nodeRun.ErrorJSON != nil {
		errorBytes, err := json.Marshal(nodeRun.ErrorJSON)
		if err != nil {
			return fmt.Errorf("failed to marshal error: %w", err)
		}
		s := string(errorBytes)
		errorStr = &s
	}

	query := `
		UPDATE node_runs
		SET status = $1, attempt = $2, output_json = $3, error_json = $4,
		    ended_at = $5, duration_ms = $6, updated_at = $7
		WHERE id = $8
	`

	result, err := r.db.ExecContext(ctx, query,
		nodeRun.Status,
		nodeRun.Attempt,
		outputStr,
		errorStr,
		nodeRun.EndedAt,
		nodeRun.DurationMs,
		time.Now(),
		nodeRun.ID,
	)

	if err != nil {
		return fmt.Errorf("failed to update node run: %w", err)
	}

	rowsAffected, err := result.RowsAffected()
	if err != nil {
		return fmt.Errorf("failed to check rows affected: %w", err)
	}
	if rowsAffected == 0 {
		return domain.ErrNodeNotFound
	}

	return nil
}

// GetNodeRun retrieves a node run by run ID and node ID
func (r *PostgresRunRepository) GetNodeRun(ctx context.Context, runID, nodeID string) (*entity.NodeRun, error) {
	query := `
		SELECT id, run_id, node_id, node_type, status, attempt,
		       input_json, output_json, error_json, started_at, ended_at, duration_ms
		FROM node_runs
		WHERE run_id = $1 AND node_id = $2
	`

	var nodeRun entity.NodeRun
	var inputJSON, outputJSON, errorJSON sql.NullString
	var endedAt sql.NullTime
	var durationMs sql.NullInt64

	err := r.db.QueryRowContext(ctx, query, runID, nodeID).Scan(
		&nodeRun.ID,
		&nodeRun.RunID,
		&nodeRun.NodeID,
		&nodeRun.NodeType,
		&nodeRun.Status,
		&nodeRun.Attempt,
		&inputJSON,
		&outputJSON,
		&errorJSON,
		&nodeRun.StartedAt,
		&endedAt,
		&durationMs,
	)

	if err == sql.ErrNoRows {
		return nil, domain.ErrNodeNotFound
	}
	if err != nil {
		return nil, fmt.Errorf("failed to get node run: %w", err)
	}

	// Parse JSON fields
	if inputJSON.Valid && inputJSON.String != "" {
		if err := json.Unmarshal([]byte(inputJSON.String), &nodeRun.InputJSON); err != nil {
			return nil, fmt.Errorf("failed to parse input_json: %w", err)
		}
	}
	if outputJSON.Valid && outputJSON.String != "" {
		if err := json.Unmarshal([]byte(outputJSON.String), &nodeRun.OutputJSON); err != nil {
			return nil, fmt.Errorf("failed to parse output_json: %w", err)
		}
	}
	if errorJSON.Valid && errorJSON.String != "" {
		if err := json.Unmarshal([]byte(errorJSON.String), &nodeRun.ErrorJSON); err != nil {
			return nil, fmt.Errorf("failed to parse error_json: %w", err)
		}
	}
	if endedAt.Valid {
		nodeRun.EndedAt = &endedAt.Time
	}
	if durationMs.Valid {
		nodeRun.DurationMs = durationMs.Int64
	}

	return &nodeRun, nil
}

// GetNodeRunsByRunID retrieves all node runs for a given run
func (r *PostgresRunRepository) GetNodeRunsByRunID(ctx context.Context, runID string) ([]*entity.NodeRun, error) {
	query := `
		SELECT id, run_id, node_id, node_type, status, attempt,
		       input_json, output_json, error_json, started_at, ended_at, duration_ms
		FROM node_runs
		WHERE run_id = $1
		ORDER BY started_at ASC
	`

	rows, err := r.db.QueryContext(ctx, query, runID)
	if err != nil {
		return nil, fmt.Errorf("failed to query node runs: %w", err)
	}
	defer rows.Close()

	var result []*entity.NodeRun
	for rows.Next() {
		var nodeRun entity.NodeRun
		var inputJSON, outputJSON, errorJSON sql.NullString
		var endedAt sql.NullTime
		var durationMs sql.NullInt64

		err := rows.Scan(
			&nodeRun.ID,
			&nodeRun.RunID,
			&nodeRun.NodeID,
			&nodeRun.NodeType,
			&nodeRun.Status,
			&nodeRun.Attempt,
			&inputJSON,
			&outputJSON,
			&errorJSON,
			&nodeRun.StartedAt,
			&endedAt,
			&durationMs,
		)
		if err != nil {
			return nil, fmt.Errorf("failed to scan node run: %w", err)
		}

		// Parse JSON fields
		if inputJSON.Valid && inputJSON.String != "" {
			json.Unmarshal([]byte(inputJSON.String), &nodeRun.InputJSON)
		}
		if outputJSON.Valid && outputJSON.String != "" {
			json.Unmarshal([]byte(outputJSON.String), &nodeRun.OutputJSON)
		}
		if errorJSON.Valid && errorJSON.String != "" {
			json.Unmarshal([]byte(errorJSON.String), &nodeRun.ErrorJSON)
		}
		if endedAt.Valid {
			nodeRun.EndedAt = &endedAt.Time
		}
		if durationMs.Valid {
			nodeRun.DurationMs = durationMs.Int64
		}

		result = append(result, &nodeRun)
	}

	if err := rows.Err(); err != nil {
		return nil, fmt.Errorf("error iterating node runs: %w", err)
	}

	return result, nil
}

// SavePauseState saves the execution state when a run is paused at a human gate
func (r *PostgresRunRepository) SavePauseState(ctx context.Context, runID, pausedNodeID string, stateSnapshot map[string]any, completedNodes []string, graphJSON string) error {
	// Combine state snapshot, completed nodes, and graph into a single JSON object
	pauseState := map[string]any{
		"state_snapshot":  stateSnapshot,
		"completed_nodes": completedNodes,
		"graph_json":      graphJSON,
	}

	pauseStateBytes, err := json.Marshal(pauseState)
	if err != nil {
		return fmt.Errorf("failed to marshal pause state: %w", err)
	}

	query := `
		UPDATE runs
		SET pause_state_json = $1, paused_node_id = $2, updated_at = $3
		WHERE id = $4
	`

	result, err := r.db.ExecContext(ctx, query, string(pauseStateBytes), pausedNodeID, time.Now(), runID)
	if err != nil {
		return fmt.Errorf("failed to save pause state: %w", err)
	}

	rowsAffected, err := result.RowsAffected()
	if err != nil {
		return fmt.Errorf("failed to check rows affected: %w", err)
	}
	if rowsAffected == 0 {
		return domain.ErrRunNotFound
	}

	return nil
}

// LoadPauseState retrieves the saved pause state for resuming a run
func (r *PostgresRunRepository) LoadPauseState(ctx context.Context, runID string) (pausedNodeID string, stateSnapshot map[string]any, completedNodes []string, graphJSON string, err error) {
	query := `
		SELECT paused_node_id, pause_state_json
		FROM runs
		WHERE id = $1
	`

	var pausedNodeIDNull sql.NullString
	var pauseStateJSONStr sql.NullString

	err = r.db.QueryRowContext(ctx, query, runID).Scan(&pausedNodeIDNull, &pauseStateJSONStr)
	if err == sql.ErrNoRows {
		return "", nil, nil, "", domain.ErrRunNotFound
	}
	if err != nil {
		return "", nil, nil, "", fmt.Errorf("failed to load pause state: %w", err)
	}

	if !pausedNodeIDNull.Valid || pausedNodeIDNull.String == "" {
		return "", nil, nil, "", fmt.Errorf("run is not paused")
	}
	pausedNodeID = pausedNodeIDNull.String

	if pauseStateJSONStr.Valid && pauseStateJSONStr.String != "" {
		var pauseState map[string]any
		if err := json.Unmarshal([]byte(pauseStateJSONStr.String), &pauseState); err != nil {
			return "", nil, nil, "", fmt.Errorf("failed to parse pause state: %w", err)
		}

		if snapshot, ok := pauseState["state_snapshot"].(map[string]any); ok {
			stateSnapshot = snapshot
		}

		if nodes, ok := pauseState["completed_nodes"].([]any); ok {
			for _, n := range nodes {
				if nodeStr, ok := n.(string); ok {
					completedNodes = append(completedNodes, nodeStr)
				}
			}
		}

		if gj, ok := pauseState["graph_json"].(string); ok {
			graphJSON = gj
		}
	}

	return pausedNodeID, stateSnapshot, completedNodes, graphJSON, nil
}

// ClearPauseState removes the pause state after a run is resumed
func (r *PostgresRunRepository) ClearPauseState(ctx context.Context, runID string) error {
	query := `
		UPDATE runs
		SET pause_state_json = NULL, paused_node_id = NULL, updated_at = $1
		WHERE id = $2
	`

	result, err := r.db.ExecContext(ctx, query, time.Now(), runID)
	if err != nil {
		return fmt.Errorf("failed to clear pause state: %w", err)
	}

	rowsAffected, err := result.RowsAffected()
	if err != nil {
		return fmt.Errorf("failed to check rows affected: %w", err)
	}
	if rowsAffected == 0 {
		return domain.ErrRunNotFound
	}

	return nil
}

// SaveCheckpoint persists the latest execution state for durable resume
func (r *PostgresRunRepository) SaveCheckpoint(ctx context.Context, runID, nodeID string, stepIndex int, stateSnapshot map[string]any, completedNodes []string, skippedNodes []string, graphJSON string) error {
	stateBytes, err := json.Marshal(stateSnapshot)
	if err != nil {
		return fmt.Errorf("failed to marshal state snapshot: %w", err)
	}

	completedBytes, err := json.Marshal(completedNodes)
	if err != nil {
		return fmt.Errorf("failed to marshal completed nodes: %w", err)
	}

	skippedBytes, err := json.Marshal(skippedNodes)
	if err != nil {
		return fmt.Errorf("failed to marshal skipped nodes: %w", err)
	}

	query := `
		INSERT INTO run_checkpoints
			(run_id, node_id, step_index, state_json, completed_nodes, skipped_nodes, graph_json, created_at, updated_at)
		VALUES
			($1, $2, $3, $4, $5, $6, $7, $8, $9)
		ON CONFLICT (run_id) DO UPDATE
		SET node_id = EXCLUDED.node_id,
		    step_index = EXCLUDED.step_index,
		    state_json = EXCLUDED.state_json,
		    completed_nodes = EXCLUDED.completed_nodes,
		    skipped_nodes = EXCLUDED.skipped_nodes,
		    graph_json = EXCLUDED.graph_json,
		    updated_at = EXCLUDED.updated_at
		WHERE run_checkpoints.step_index <= EXCLUDED.step_index
	`

	now := time.Now()
	_, err = r.db.ExecContext(ctx, query, runID, nodeID, stepIndex, string(stateBytes), string(completedBytes), string(skippedBytes), graphJSON, now, now)
	if err != nil {
		return fmt.Errorf("failed to save checkpoint: %w", err)
	}

	return nil
}

// LoadLatestCheckpoint retrieves the most recent checkpoint for a run
func (r *PostgresRunRepository) LoadLatestCheckpoint(ctx context.Context, runID string) (nodeID string, stepIndex int, stateSnapshot map[string]any, completedNodes []string, skippedNodes []string, graphJSON string, err error) {
	query := `
		SELECT node_id, step_index, state_json, completed_nodes, skipped_nodes, graph_json
		FROM run_checkpoints
		WHERE run_id = $1
	`

	var stateJSON, completedJSON, skippedJSON, graphJSONStr sql.NullString
	err = r.db.QueryRowContext(ctx, query, runID).Scan(&nodeID, &stepIndex, &stateJSON, &completedJSON, &skippedJSON, &graphJSONStr)
	if err == sql.ErrNoRows {
		return "", 0, nil, nil, nil, "", domain.ErrCheckpointNotFound
	}
	if err != nil {
		return "", 0, nil, nil, nil, "", fmt.Errorf("failed to load checkpoint: %w", err)
	}

	if stateJSON.Valid && stateJSON.String != "" {
		if err := json.Unmarshal([]byte(stateJSON.String), &stateSnapshot); err != nil {
			return "", 0, nil, nil, nil, "", fmt.Errorf("failed to parse state_json: %w", err)
		}
	}

	if completedJSON.Valid && completedJSON.String != "" {
		if err := json.Unmarshal([]byte(completedJSON.String), &completedNodes); err != nil {
			return "", 0, nil, nil, nil, "", fmt.Errorf("failed to parse completed_nodes: %w", err)
		}
	}

	if skippedJSON.Valid && skippedJSON.String != "" {
		if err := json.Unmarshal([]byte(skippedJSON.String), &skippedNodes); err != nil {
			return "", 0, nil, nil, nil, "", fmt.Errorf("failed to parse skipped_nodes: %w", err)
		}
	}

	if graphJSONStr.Valid {
		graphJSON = graphJSONStr.String
	}

	return nodeID, stepIndex, stateSnapshot, completedNodes, skippedNodes, graphJSON, nil
}

// ClearCheckpoints removes all checkpoints for a run
func (r *PostgresRunRepository) ClearCheckpoints(ctx context.Context, runID string) error {
	query := `DELETE FROM run_checkpoints WHERE run_id = $1`

	result, err := r.db.ExecContext(ctx, query, runID)
	if err != nil {
		return fmt.Errorf("failed to clear checkpoints: %w", err)
	}

	rowsAffected, err := result.RowsAffected()
	if err != nil {
		return fmt.Errorf("failed to check rows affected: %w", err)
	}
	if rowsAffected == 0 {
		return domain.ErrCheckpointNotFound
	}

	return nil
}

// GetCachedNodeResult retrieves a cached node output by key if not expired
func (r *PostgresRunRepository) GetCachedNodeResult(ctx context.Context, cacheKey string) (output any, found bool, err error) {
	query := `
		SELECT output_json, expires_at
		FROM node_run_cache
		WHERE cache_key = $1 AND expires_at > $2
	`

	var outputJSON sql.NullString
	var expiresAt sql.NullTime
	err = r.db.QueryRowContext(ctx, query, cacheKey, time.Now()).Scan(&outputJSON, &expiresAt)
	if err == sql.ErrNoRows {
		return nil, false, nil
	}
	if err != nil {
		return nil, false, fmt.Errorf("failed to get cached node result: %w", err)
	}

	if !outputJSON.Valid || outputJSON.String == "" {
		return nil, false, nil
	}

	if err := json.Unmarshal([]byte(outputJSON.String), &output); err != nil {
		return nil, false, fmt.Errorf("failed to parse cached output: %w", err)
	}

	return output, true, nil
}

// SaveCachedNodeResult stores a cached node output with TTL seconds
func (r *PostgresRunRepository) SaveCachedNodeResult(ctx context.Context, cacheKey string, output any, ttlSeconds int) error {
	if ttlSeconds <= 0 {
		return nil
	}

	outputBytes, err := json.Marshal(output)
	if err != nil {
		return fmt.Errorf("failed to marshal cached output: %w", err)
	}

	now := time.Now()
	expiresAt := now.Add(time.Duration(ttlSeconds) * time.Second)

	query := `
		INSERT INTO node_run_cache
			(cache_key, output_json, created_at, updated_at, expires_at)
		VALUES
			($1, $2, $3, $4, $5)
		ON CONFLICT (cache_key) DO UPDATE
		SET output_json = EXCLUDED.output_json,
		    updated_at = EXCLUDED.updated_at,
		    expires_at = EXCLUDED.expires_at
	`

	_, err = r.db.ExecContext(ctx, query, cacheKey, string(outputBytes), now, now, expiresAt)
	if err != nil {
		return fmt.Errorf("failed to save cached node result: %w", err)
	}

	return nil
}
