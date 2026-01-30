package entity

import (
	"sync"
	"time"
)

// Message represents a conversational message stored in memory.
type Message struct {
	Role      string         `json:"role"` // "user", "assistant", "system"
	Content   string         `json:"content"`
	Timestamp time.Time      `json:"timestamp"`
	NodeID    string         `json:"node_id,omitempty"`
	Metadata  map[string]any `json:"metadata,omitempty"`
}

// MessageBuffer is a goroutine-safe circular buffer of messages.
type MessageBuffer struct {
	mu       sync.RWMutex
	messages []Message
	capacity int
	head     int // Next write position (oldest message when full)
	count    int // Current number of messages (0 to capacity)
}

// NewMessageBuffer creates a new buffer with the provided capacity.
func NewMessageBuffer(capacity int) *MessageBuffer {
	if capacity <= 0 {
		capacity = 20
	}
	return &MessageBuffer{
		messages: make([]Message, capacity),
		capacity: capacity,
	}
}

// Push adds a message to the buffer, evicting the oldest if full.
func (b *MessageBuffer) Push(msg Message) {
	b.mu.Lock()
	defer b.mu.Unlock()

	if msg.Timestamp.IsZero() {
		msg.Timestamp = time.Now()
	}

	b.messages[b.head] = msg
	b.head = (b.head + 1) % b.capacity
	if b.count < b.capacity {
		b.count++
	}
}

// GetAll returns all messages in chronological order.
func (b *MessageBuffer) GetAll() []Message {
	b.mu.RLock()
	defer b.mu.RUnlock()
	return b.getAllUnlocked()
}

// GetLast returns the last n messages in chronological order.
func (b *MessageBuffer) GetLast(n int) []Message {
	b.mu.RLock()
	defer b.mu.RUnlock()

	if n <= 0 || b.count == 0 {
		return nil
	}
	if n > b.count {
		n = b.count
	}

	all := b.getAllUnlocked()
	return append([]Message(nil), all[len(all)-n:]...)
}

// GetFirst returns the first n messages in chronological order.
func (b *MessageBuffer) GetFirst(n int) []Message {
	b.mu.RLock()
	defer b.mu.RUnlock()

	if n <= 0 || b.count == 0 {
		return nil
	}
	if n > b.count {
		n = b.count
	}

	all := b.getAllUnlocked()
	return append([]Message(nil), all[:n]...)
}

// RemoveFirst removes the oldest n messages from the buffer.
func (b *MessageBuffer) RemoveFirst(n int) {
	b.mu.Lock()
	defer b.mu.Unlock()

	if n <= 0 || b.count == 0 {
		return
	}
	if n > b.count {
		n = b.count
	}

	remaining := b.getAllUnlocked()[n:]
	b.resetUnlocked()
	for _, msg := range remaining {
		b.messages[b.head] = msg
		b.head = (b.head + 1) % b.capacity
		b.count++
	}
}

// Clear removes all messages from the buffer.
func (b *MessageBuffer) Clear() {
	b.mu.Lock()
	defer b.mu.Unlock()
	b.resetUnlocked()
}

// Count returns the number of messages in the buffer.
func (b *MessageBuffer) Count() int {
	b.mu.RLock()
	defer b.mu.RUnlock()
	return b.count
}

// Capacity returns the maximum number of messages the buffer can hold.
func (b *MessageBuffer) Capacity() int {
	return b.capacity
}

// Snapshot returns a deep copy of the current buffer in chronological order.
func (b *MessageBuffer) Snapshot() []Message {
	b.mu.RLock()
	defer b.mu.RUnlock()

	all := b.getAllUnlocked()
	snapshot := make([]Message, len(all))
	for i, msg := range all {
		snapshot[i] = Message{
			Role:      msg.Role,
			Content:   msg.Content,
			Timestamp: msg.Timestamp,
			NodeID:    msg.NodeID,
			Metadata:  copyMap(msg.Metadata),
		}
	}
	return snapshot
}

// Restore replaces the buffer contents with the provided messages.
func (b *MessageBuffer) Restore(messages []Message) {
	b.mu.Lock()
	defer b.mu.Unlock()

	b.resetUnlocked()
	for _, msg := range messages {
		if b.count >= b.capacity {
			break
		}
		b.messages[b.head] = Message{
			Role:      msg.Role,
			Content:   msg.Content,
			Timestamp: msg.Timestamp,
			NodeID:    msg.NodeID,
			Metadata:  copyMap(msg.Metadata),
		}
		b.head = (b.head + 1) % b.capacity
		b.count++
	}
}

func (b *MessageBuffer) getAllUnlocked() []Message {
	if b.count == 0 {
		return nil
	}

	result := make([]Message, b.count)
	if b.count < b.capacity {
		copy(result, b.messages[:b.count])
		return result
	}

	firstPart := b.messages[b.head:]
	secondPart := b.messages[:b.head]
	copy(result, firstPart)
	copy(result[len(firstPart):], secondPart)
	return result
}

func (b *MessageBuffer) resetUnlocked() {
	b.head = 0
	b.count = 0
	b.messages = make([]Message, b.capacity)
}

func copyMap(input map[string]any) map[string]any {
	if input == nil {
		return nil
	}
	clone := make(map[string]any, len(input))
	for key, value := range input {
		clone[key] = value
	}
	return clone
}
