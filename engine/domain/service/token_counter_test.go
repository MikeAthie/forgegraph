package service

import (
	"testing"

	"github.com/forgegraph/engine/domain/entity"
	"github.com/pkoukk/tiktoken-go"
)

func TestTiktokenCounter_CountMatchesEncoding(t *testing.T) {
	counter, err := NewTokenCounterWithEncoding("cl100k_base")
	if err != nil {
		t.Fatalf("failed to create token counter: %v", err)
	}

	encoding, err := tiktoken.GetEncoding("cl100k_base")
	if err != nil {
		t.Fatalf("failed to load encoding: %v", err)
	}

	text := "Hello, world!"
	expected := len(encoding.Encode(text, nil, nil))
	if got := counter.Count(text); got != expected {
		t.Fatalf("expected %d tokens, got %d", expected, got)
	}
}

func TestTiktokenCounter_CountMessagesAddsPrimer(t *testing.T) {
	counter, err := NewTokenCounterForModel("gpt-4-0613")
	if err != nil {
		t.Fatalf("failed to create token counter: %v", err)
	}

	messages := []entity.Message{
		{Role: "user", Content: "Hello"},
		{Role: "assistant", Content: "Hi there"},
	}

	total := counter.CountMessages(messages)
	minExpected := counter.CountMessage(messages[0]) + counter.CountMessage(messages[1])
	if total < minExpected+3 {
		t.Fatalf("expected total to include reply primer, got %d (min %d)", total, minExpected+3)
	}
}

func TestSafeTokenCounter_Fallback(t *testing.T) {
	safe := NewSafeTokenCounter(nil, NaiveTokenCounter{})
	count := safe.Count("hello world")
	if count <= 0 {
		t.Fatalf("expected fallback count > 0, got %d", count)
	}
}
