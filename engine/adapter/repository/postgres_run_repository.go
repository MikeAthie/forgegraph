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
