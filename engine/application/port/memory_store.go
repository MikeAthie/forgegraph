// Package port defines interfaces (ports) for the application layer.
package port

import "context"

// MemoryStore provides a simple key/value store for long-term memory.
// Implementations may use in-memory maps, SQL, or external services.
type MemoryStore interface {
	// Get retrieves a value by namespace and key.
	Get(ctx context.Context, namespace, key string) (value any, found bool, err error)

	// Set stores a value with optional TTL (seconds). ttlSeconds <= 0 means no expiry.
	Set(ctx context.Context, namespace, key string, value any, ttlSeconds int) error

	// Delete removes a key/value entry. Returns true if an entry was deleted.
	Delete(ctx context.Context, namespace, key string) (bool, error)
}
