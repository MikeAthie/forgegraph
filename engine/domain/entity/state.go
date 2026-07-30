package entity

import (
	"strings"
	"sync"
)

// State holds the execution state for a run.
// It is thread-safe for concurrent node execution.
type State struct {
	mu     sync.RWMutex
	values map[string]any
}

// NewState creates a new empty execution state
func NewState() *State {
	return &State{
		values: make(map[string]any),
	}
}

// NewStateWithInput creates a new state initialized with input values
func NewStateWithInput(input map[string]any) *State {
	s := NewState()
	for k, v := range input {
		s.Set("input."+k, v)
	}
	return s
}

// NewStateFromSnapshot creates a new state from a previously saved snapshot
func NewStateFromSnapshot(snapshot map[string]any) *State {
	s := NewState()
	s.Merge(snapshot)
	return s
}

// Get retrieves a value from state (thread-safe)
func (s *State) Get(key string) (any, bool) {
	s.mu.RLock()
	defer s.mu.RUnlock()
	val, ok := s.values[key]
	return cloneStateValue(val), ok
}

// Set stores a value in state (thread-safe)
func (s *State) Set(key string, value any) {
	s.mu.Lock()
	defer s.mu.Unlock()
	s.values[key] = cloneStateValue(value)
}

// Delete removes a value from state (thread-safe)
func (s *State) Delete(key string) {
	s.mu.Lock()
	defer s.mu.Unlock()
	delete(s.values, key)
}

// SetNodeOutput stores a node's output using standard naming convention
// The key format is: node.<nodeID>.output
func (s *State) SetNodeOutput(nodeID string, output any) {
	s.Set("node."+nodeID+".output", output)
}

// GetNodeOutput retrieves a node's output
func (s *State) GetNodeOutput(nodeID string) (any, bool) {
	return s.Get("node." + nodeID + ".output")
}

// SetVar stores a computed variable
// The key format is: vars.<name>
func (s *State) SetVar(name string, value any) {
	s.Set("vars."+name, value)
}

// GetVar retrieves a computed variable
func (s *State) GetVar(name string) (any, bool) {
	return s.Get("vars." + name)
}

// GetInput retrieves an input value
func (s *State) GetInput(name string) (any, bool) {
	return s.Get("input." + name)
}

// Snapshot returns a copy of all state values (for logging/debugging)
func (s *State) Snapshot() map[string]any {
	s.mu.RLock()
	defer s.mu.RUnlock()
	snapshot := make(map[string]any, len(s.values))
	for k, v := range s.values {
		snapshot[k] = cloneStateValue(v)
	}
	return snapshot
}

// SnapshotNested returns a nested representation of the state.
// Keys are split on ".", producing a structured map useful for schema validation.
func (s *State) SnapshotNested() map[string]any {
	s.mu.RLock()
	defer s.mu.RUnlock()

	root := make(map[string]any, len(s.values))
	for key, value := range s.values {
		insertNestedValue(root, key, cloneStateValue(value))
	}
	return root
}

// Merge adds all values from another map into the state
func (s *State) Merge(values map[string]any) {
	s.mu.Lock()
	defer s.mu.Unlock()
	for k, v := range values {
		s.values[k] = cloneStateValue(v)
	}
}

// Keys returns all keys in the state
func (s *State) Keys() []string {
	s.mu.RLock()
	defer s.mu.RUnlock()
	keys := make([]string, 0, len(s.values))
	for k := range s.values {
		keys = append(keys, k)
	}
	return keys
}

// Len returns the number of entries in the state
func (s *State) Len() int {
	s.mu.RLock()
	defer s.mu.RUnlock()
	return len(s.values)
}

// GetString retrieves a string value from state
func (s *State) GetString(key string) string {
	val, ok := s.Get(key)
	if !ok {
		return ""
	}
	if str, ok := val.(string); ok {
		return str
	}
	return ""
}

// GetInt retrieves an int value from state
func (s *State) GetInt(key string) int {
	val, ok := s.Get(key)
	if !ok {
		return 0
	}
	switch v := val.(type) {
	case int:
		return v
	case float64:
		return int(v)
	case int64:
		return int(v)
	default:
		return 0
	}
}

// GetBool retrieves a bool value from state
func (s *State) GetBool(key string) bool {
	val, ok := s.Get(key)
	if !ok {
		return false
	}
	if b, ok := val.(bool); ok {
		return b
	}
	return false
}

func insertNestedValue(root map[string]any, key string, value any) {
	if key == "" {
		return
	}
	parts := strings.Split(key, ".")
	current := root
	for i, part := range parts {
		if part == "" {
			continue
		}
		if i == len(parts)-1 {
			current[part] = value
			return
		}
		next, ok := current[part]
		if !ok {
			child := make(map[string]any)
			current[part] = child
			current = child
			continue
		}
		child, ok := next.(map[string]any)
		if !ok {
			child = make(map[string]any)
			current[part] = child
		}
		current = child
	}
}

func cloneStateValue(value any) any {
	switch typed := value.(type) {
	case map[string]any:
		cloned := make(map[string]any, len(typed))
		for key, item := range typed {
			cloned[key] = cloneStateValue(item)
		}
		return cloned
	case []any:
		cloned := make([]any, len(typed))
		for i, item := range typed {
			cloned[i] = cloneStateValue(item)
		}
		return cloned
	case map[string]string:
		cloned := make(map[string]string, len(typed))
		for key, item := range typed {
			cloned[key] = item
		}
		return cloned
	case []string:
		return append([]string(nil), typed...)
	default:
		return value
	}
}
