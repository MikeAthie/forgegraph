package executor

import (
	"container/list"
	"sync"
	"time"
)

type promptCacheEntry struct {
	key       string
	response  *LLMResponse
	expiresAt time.Time
}

type PromptCache struct {
	mu         sync.Mutex
	maxEntries int
	items      map[string]*list.Element
	order      *list.List
}

func NewPromptCache(maxEntries int) *PromptCache {
	if maxEntries <= 0 {
		maxEntries = 256
	}
	return &PromptCache{
		maxEntries: maxEntries,
		items:      make(map[string]*list.Element),
		order:      list.New(),
	}
}

func (c *PromptCache) Get(key string, now time.Time) (*LLMResponse, bool) {
	c.mu.Lock()
	defer c.mu.Unlock()

	element, ok := c.items[key]
	if !ok {
		return nil, false
	}
	entry, ok := element.Value.(*promptCacheEntry)
	if !ok {
		return nil, false
	}
	if !entry.expiresAt.IsZero() && now.After(entry.expiresAt) {
		c.order.Remove(element)
		delete(c.items, key)
		return nil, false
	}
	c.order.MoveToFront(element)
	return entry.response, true
}

func (c *PromptCache) Set(key string, response *LLMResponse, ttl time.Duration, now time.Time) {
	if response == nil {
		return
	}
	c.mu.Lock()
	defer c.mu.Unlock()

	if element, ok := c.items[key]; ok {
		entry := element.Value.(*promptCacheEntry)
		entry.response = response
		entry.expiresAt = now.Add(ttl)
		c.order.MoveToFront(element)
		return
	}

	entry := &promptCacheEntry{
		key:       key,
		response:  response,
		expiresAt: now.Add(ttl),
	}
	element := c.order.PushFront(entry)
	c.items[key] = element

	for c.order.Len() > c.maxEntries {
		oldest := c.order.Back()
		if oldest == nil {
			break
		}
		c.order.Remove(oldest)
		if oldEntry, ok := oldest.Value.(*promptCacheEntry); ok {
			delete(c.items, oldEntry.key)
		}
	}
}
