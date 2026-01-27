package store

import (
	"context"
	"crypto/rand"
	"database/sql"
	"encoding/json"
	"fmt"
	"time"
)

// PostgresMemoryStore persists memory entries in PostgreSQL.
type PostgresMemoryStore struct {
	db *sql.DB
}

// NewPostgresMemoryStore creates a new Postgres-backed memory store.
func NewPostgresMemoryStore(db *sql.DB) *PostgresMemoryStore {
	return &PostgresMemoryStore{db: db}
}

// Get retrieves a value by namespace and key.
func (s *PostgresMemoryStore) Get(ctx context.Context, namespace, key string) (value any, found bool, err error) {
	query := `
		SELECT value_json, expires_at
		FROM memory_entries
		WHERE namespace = $1 AND key = $2
	`

	var valueJSON []byte
	var expiresAt sql.NullTime
	err = s.db.QueryRowContext(ctx, query, namespace, key).Scan(&valueJSON, &expiresAt)
	if err == sql.ErrNoRows {
		return nil, false, nil
	}
	if err != nil {
		return nil, false, err
	}

	if expiresAt.Valid && time.Now().After(expiresAt.Time) {
		_, _ = s.Delete(ctx, namespace, key)
		return nil, false, nil
	}

	if len(valueJSON) == 0 {
		return nil, true, nil
	}

	var parsed any
	if err := json.Unmarshal(valueJSON, &parsed); err != nil {
		return nil, false, err
	}

	return parsed, true, nil
}

// Set stores a value with optional TTL (seconds). ttlSeconds <= 0 means no expiry.
func (s *PostgresMemoryStore) Set(ctx context.Context, namespace, key string, value any, ttlSeconds int) error {
	payload, err := json.Marshal(value)
	if err != nil {
		return err
	}

	now := time.Now()
	var expiresAt sql.NullTime
	if ttlSeconds > 0 {
		expiresAt = sql.NullTime{
			Time:  now.Add(time.Duration(ttlSeconds) * time.Second),
			Valid: true,
		}
	}

	id, err := newUUID()
	if err != nil {
		return err
	}

	query := `
		INSERT INTO memory_entries (id, namespace, key, value_json, expires_at, created_at, updated_at)
		VALUES ($1, $2, $3, $4, $5, $6, $6)
		ON CONFLICT (namespace, key)
		DO UPDATE SET value_json = EXCLUDED.value_json,
					  expires_at = EXCLUDED.expires_at,
					  updated_at = EXCLUDED.updated_at
	`

	_, err = s.db.ExecContext(ctx, query, id, namespace, key, payload, expiresAt, now)
	return err
}

// Delete removes a key/value entry. Returns true if an entry was deleted.
func (s *PostgresMemoryStore) Delete(ctx context.Context, namespace, key string) (bool, error) {
	query := `
		DELETE FROM memory_entries
		WHERE namespace = $1 AND key = $2
	`
	result, err := s.db.ExecContext(ctx, query, namespace, key)
	if err != nil {
		return false, err
	}
	rows, err := result.RowsAffected()
	if err != nil {
		return false, err
	}
	return rows > 0, nil
}

func newUUID() (string, error) {
	buf := make([]byte, 16)
	if _, err := rand.Read(buf); err != nil {
		return "", err
	}

	// Set version (4) and variant bits.
	buf[6] = (buf[6] & 0x0f) | 0x40
	buf[8] = (buf[8] & 0x3f) | 0x80

	return fmt.Sprintf(
		"%x-%x-%x-%x-%x",
		buf[0:4],
		buf[4:6],
		buf[6:8],
		buf[8:10],
		buf[10:16],
	), nil
}
