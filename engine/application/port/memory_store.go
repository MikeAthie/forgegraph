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

// BatchMemoryStore extends MemoryStore with batch operations for improved performance.
// Use type assertion to check if a MemoryStore implementation supports batch operations.
type BatchMemoryStore interface {
	MemoryStore

	// BatchGet retrieves multiple values by namespace and keys.
	// Returns a map of key to value for found keys. Missing keys are omitted from the result.
	BatchGet(ctx context.Context, namespace string, keys []string) (map[string]any, error)

	// BatchSet stores multiple key-value pairs with optional TTL (seconds).
	// ttlSeconds <= 0 means no expiry.
	BatchSet(ctx context.Context, namespace string, items map[string]any, ttlSeconds int) error
}
