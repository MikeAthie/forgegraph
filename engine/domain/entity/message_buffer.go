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

// EvictionCallback is called when messages are evicted from the buffer.
// reason: "capacity" for capacity eviction, "token_limit" for token limit eviction.
// count: number of messages evicted.
// tokens: number of tokens evicted (may be 0 if token counting is disabled).
type EvictionCallback func(reason string, count int, tokens int)

// MessageBuffer is a goroutine-safe circular buffer of messages.
type MessageBuffer struct {
	mu       sync.RWMutex
	messages []Message
	capacity int
	head     int // Next write position (oldest message when full)
	count    int // Current number of messages (0 to capacity)

	tokenLimit     int
	tokenCount     int
	tokenCounts    []int
	tokenCountFunc func(Message) int

	onEviction EvictionCallback
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

// ConfigureTokenLimit enables token-based eviction using the provided counter.
func (b *MessageBuffer) ConfigureTokenLimit(maxTokens int, countFunc func(Message) int) {
	b.mu.Lock()
	defer b.mu.Unlock()

	if maxTokens <= 0 || countFunc == nil {
		b.tokenLimit = 0
		b.tokenCount = 0
		b.tokenCounts = nil
		b.tokenCountFunc = nil
		return
	}

	b.tokenLimit = maxTokens
	b.tokenCountFunc = countFunc
	b.tokenCounts = make([]int, b.capacity)
	b.tokenCount = 0

	ordered := b.getAllUnlocked()
	if len(ordered) == 0 {
		return
	}

	b.resetUnlocked()
	for _, msg := range ordered {
		b.pushUnlocked(msg)
	}
}

// Push adds a message to the buffer, evicting the oldest if full.
func (b *MessageBuffer) Push(msg Message) {
	b.mu.Lock()
	defer b.mu.Unlock()

	if msg.Timestamp.IsZero() {
		msg.Timestamp = time.Now()
	}

	b.pushUnlocked(msg)
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
	var remainingTokenCounts []int
	if b.tokenCounts != nil {
		orderedCounts := b.getTokenCountsUnlocked()
		if len(orderedCounts) >= n {
			remainingTokenCounts = orderedCounts[n:]
		}
	}
	b.restoreOrderedUnlocked(remaining, remainingTokenCounts)
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

// TokenCount returns the total token count tracked in the buffer.
func (b *MessageBuffer) TokenCount() int {
	b.mu.RLock()
	defer b.mu.RUnlock()
	return b.tokenCount
}

// TokenLimit returns the configured token limit.
func (b *MessageBuffer) TokenLimit() int {
	b.mu.RLock()
	defer b.mu.RUnlock()
	return b.tokenLimit
}

// Capacity returns the maximum number of messages the buffer can hold.
func (b *MessageBuffer) Capacity() int {
	return b.capacity
}

// SetEvictionCallback registers a callback to be invoked when messages are evicted.
func (b *MessageBuffer) SetEvictionCallback(cb EvictionCallback) {
	b.mu.Lock()
	defer b.mu.Unlock()
	b.onEviction = cb
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

	b.restoreOrderedUnlocked(messages, nil)
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

func (b *MessageBuffer) getTokenCountsUnlocked() []int {
	if b.count == 0 || b.tokenCounts == nil {
		return nil
	}

	result := make([]int, b.count)
	if b.count < b.capacity {
		copy(result, b.tokenCounts[:b.count])
		return result
	}

	firstPart := b.tokenCounts[b.head:]
	secondPart := b.tokenCounts[:b.head]
	copy(result, firstPart)
	copy(result[len(firstPart):], secondPart)
	return result
}

func (b *MessageBuffer) resetUnlocked() {
	b.head = 0
	b.count = 0
	b.messages = make([]Message, b.capacity)
	if b.tokenCounts != nil {
		b.tokenCounts = make([]int, b.capacity)
	}
	b.tokenCount = 0
}

func (b *MessageBuffer) pushUnlocked(msg Message) {
	var evictedTokens int

	// Track capacity eviction
	if b.count == b.capacity {
		if b.tokenCounts != nil && len(b.tokenCounts) > b.head {
			evictedTokens = b.tokenCounts[b.head]
		}
		if b.onEviction != nil {
			b.onEviction("capacity", 1, evictedTokens)
		}
	}

	if b.tokenLimit > 0 && b.tokenCountFunc != nil {
		if b.tokenCounts == nil {
			b.tokenCounts = make([]int, b.capacity)
		}
		if b.count == b.capacity {
			b.tokenCount -= b.tokenCounts[b.head]
		}
		tokens := b.countTokens(msg)
		b.tokenCounts[b.head] = tokens
		b.tokenCount += tokens
	}

	b.messages[b.head] = msg
	b.head = (b.head + 1) % b.capacity
	if b.count < b.capacity {
		b.count++
	}

	b.trimToTokenLimitUnlocked()
}

func (b *MessageBuffer) countTokens(msg Message) int {
	if b.tokenCountFunc == nil {
		return 0
	}
	tokens := b.tokenCountFunc(msg)
	if tokens <= 0 {
		return 1
	}
	return tokens
}

func (b *MessageBuffer) restoreOrderedUnlocked(messages []Message, tokenCounts []int) {
	b.resetUnlocked()
	if len(messages) == 0 {
		return
	}

	for i, msg := range messages {
		if b.count >= b.capacity {
			break
		}
		copyMsg := Message{
			Role:      msg.Role,
			Content:   msg.Content,
			Timestamp: msg.Timestamp,
			NodeID:    msg.NodeID,
			Metadata:  copyMap(msg.Metadata),
		}
		b.messages[b.head] = copyMsg
		if b.tokenLimit > 0 && b.tokenCountFunc != nil {
			if b.tokenCounts == nil {
				b.tokenCounts = make([]int, b.capacity)
			}
			if len(tokenCounts) == len(messages) {
				b.tokenCounts[b.head] = tokenCounts[i]
				b.tokenCount += tokenCounts[i]
			} else {
				tokens := b.countTokens(copyMsg)
				b.tokenCounts[b.head] = tokens
				b.tokenCount += tokens
			}
		}
		b.head = (b.head + 1) % b.capacity
		b.count++
	}
	b.trimToTokenLimitUnlocked()
}

func (b *MessageBuffer) trimToTokenLimitUnlocked() {
	if b.tokenLimit <= 0 || b.tokenCountFunc == nil || b.tokenCount <= b.tokenLimit {
		return
	}

	ordered := b.getAllUnlocked()
	if len(ordered) == 0 {
		return
	}

	orderedCounts := b.getTokenCountsUnlocked()
	total := 0
	for _, count := range orderedCounts {
		total += count
	}

	cutIndex := 0
	evictedTokens := 0
	for total > b.tokenLimit && cutIndex < len(ordered) {
		if cutIndex < len(orderedCounts) {
			evictedTokens += orderedCounts[cutIndex]
			total -= orderedCounts[cutIndex]
		} else {
			tokens := b.countTokens(ordered[cutIndex])
			evictedTokens += tokens
			total -= tokens
		}
		cutIndex++
	}

	if cutIndex == 0 {
		return
	}

	// Report token limit eviction
	if b.onEviction != nil {
		b.onEviction("token_limit", cutIndex, evictedTokens)
	}

	remaining := ordered[cutIndex:]
	var remainingCounts []int
	if len(orderedCounts) >= cutIndex {
		remainingCounts = orderedCounts[cutIndex:]
	}
	b.restoreOrderedUnlocked(remaining, remainingCounts)
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
