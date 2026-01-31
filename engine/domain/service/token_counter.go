package service

import (
	"log"
	"strings"

	"github.com/forgegraph/engine/domain/entity"
	"github.com/pkoukk/tiktoken-go"
)

// TokenCounter counts tokens for text and messages.
type TokenCounter interface {
	Count(text string) int
	CountMessage(message entity.Message) int
	CountMessages(messages []entity.Message) int
}

// TiktokenCounter counts tokens using OpenAI's tiktoken encodings.
type TiktokenCounter struct {
	encoding         *tiktoken.Tiktoken
	model            string
	tokensPerMessage int
	tokensPerName    int
}

// NewDefaultTokenCounter initializes a token counter using cl100k_base encoding.
func NewDefaultTokenCounter() (TokenCounter, error) {
	return NewTokenCounterWithEncoding("cl100k_base")
}

// NewTokenCounterWithEncoding initializes a token counter using a specific encoding.
func NewTokenCounterWithEncoding(encoding string) (TokenCounter, error) {
	tke, err := tiktoken.GetEncoding(encoding)
	if err != nil {
		return nil, err
	}
	return &TiktokenCounter{
		encoding:         tke,
		model:            encoding,
		tokensPerMessage: 3,
		tokensPerName:    1,
	}, nil
}

// NewTokenCounterForModel initializes a token counter using a model name.
func NewTokenCounterForModel(model string) (TokenCounter, error) {
	tke, err := tiktoken.EncodingForModel(model)
	if err != nil {
		return nil, err
	}
	tokensPerMessage, tokensPerName := chatMLOverhead(model)
	return &TiktokenCounter{
		encoding:         tke,
		model:            model,
		tokensPerMessage: tokensPerMessage,
		tokensPerName:    tokensPerName,
	}, nil
}

// Count returns the number of tokens in the provided text.
func (c *TiktokenCounter) Count(text string) int {
	if c == nil || c.encoding == nil {
		return 0
	}
	tokens := c.encoding.Encode(text, nil, nil)
	return len(tokens)
}

// CountMessage returns the number of tokens in a single message.
func (c *TiktokenCounter) CountMessage(message entity.Message) int {
	if c == nil || c.encoding == nil {
		return 0
	}

	count := c.tokensPerMessage
	if message.Role != "" {
		count += c.Count(message.Role)
	}
	if message.Content != "" {
		count += c.Count(message.Content)
	}
	if c.tokensPerName != 0 && message.NodeID != "" {
		count += c.tokensPerName
		count += c.Count(message.NodeID)
	}
	return count
}

// CountMessages returns the number of tokens in a chat message list.
func (c *TiktokenCounter) CountMessages(messages []entity.Message) int {
	if c == nil || c.encoding == nil {
		return 0
	}
	total := 0
	for _, message := range messages {
		total += c.CountMessage(message)
	}
	if len(messages) > 0 {
		total += 3 // reply primer
	}
	return total
}

// NaiveTokenCounter provides a fallback counter that approximates token counts.
type NaiveTokenCounter struct{}

// Count returns a rough token estimate based on whitespace-separated words.
func (n NaiveTokenCounter) Count(text string) int {
	if text == "" {
		return 0
	}
	count := len(strings.Fields(text))
	if count == 0 {
		return 1
	}
	return count
}

// CountMessage returns a rough token estimate for a single message.
func (n NaiveTokenCounter) CountMessage(message entity.Message) int {
	return n.Count(message.Content)
}

// CountMessages returns a rough token estimate for a list of messages.
func (n NaiveTokenCounter) CountMessages(messages []entity.Message) int {
	if len(messages) == 0 {
		return 0
	}
	total := 0
	for _, message := range messages {
		total += n.CountMessage(message)
	}
	if total == 0 {
		return len(messages)
	}
	return total
}

// SafeTokenCounter wraps a primary counter with a fallback counter.
type SafeTokenCounter struct {
	primary  TokenCounter
	fallback TokenCounter
}

// NewSafeTokenCounter creates a safe counter with a fallback.
func NewSafeTokenCounter(primary TokenCounter, fallback TokenCounter) TokenCounter {
	if fallback == nil {
		fallback = NaiveTokenCounter{}
	}
	return SafeTokenCounter{primary: primary, fallback: fallback}
}

// Count returns token count with fallback on failure.
func (s SafeTokenCounter) Count(text string) int {
	count, ok := s.safeCount(func(counter TokenCounter) int {
		return counter.Count(text)
	})
	if ok {
		return count
	}
	return s.fallback.Count(text)
}

// CountMessage returns token count for a message with fallback on failure.
func (s SafeTokenCounter) CountMessage(message entity.Message) int {
	count, ok := s.safeCount(func(counter TokenCounter) int {
		return counter.CountMessage(message)
	})
	if ok {
		return count
	}
	return s.fallback.CountMessage(message)
}

// CountMessages returns token count for messages with fallback on failure.
func (s SafeTokenCounter) CountMessages(messages []entity.Message) int {
	count, ok := s.safeCount(func(counter TokenCounter) int {
		return counter.CountMessages(messages)
	})
	if ok {
		return count
	}
	return s.fallback.CountMessages(messages)
}

func (s SafeTokenCounter) safeCount(fn func(counter TokenCounter) int) (int, bool) {
	defer func() {
		if recover() != nil {
			log.Printf("Token counter panic recovered; using fallback")
		}
	}()
	if s.primary == nil {
		return 0, false
	}
	count := fn(s.primary)
	if count <= 0 {
		return 0, false
	}
	return count, true
}

func chatMLOverhead(model string) (int, int) {
	switch model {
	case "gpt-3.5-turbo-0613",
		"gpt-3.5-turbo-16k-0613",
		"gpt-4-0314",
		"gpt-4-32k-0314",
		"gpt-4-0613",
		"gpt-4-32k-0613":
		return 3, 1
	case "gpt-3.5-turbo-0301":
		return 4, -1
	default:
		if strings.Contains(model, "gpt-3.5-turbo") {
			log.Printf("Token counter fallback to gpt-3.5-turbo-0613 semantics for %s", model)
			return 3, 1
		}
		if strings.Contains(model, "gpt-4") {
			log.Printf("Token counter fallback to gpt-4-0613 semantics for %s", model)
			return 3, 1
		}
		return 3, 1
	}
}
