package entity

import (
	"fmt"
	"sync"
	"testing"
	"time"
)

func TestMessageBuffer_Push(t *testing.T) {
	buf := NewMessageBuffer(3)
	buf.Push(Message{Role: "user", Content: "a"})
	buf.Push(Message{Role: "assistant", Content: "b"})

	if buf.Count() != 2 {
		t.Fatalf("expected count 2, got %d", buf.Count())
	}
}

func TestMessageBuffer_CircularBehavior(t *testing.T) {
	buf := NewMessageBuffer(2)
	buf.Push(Message{Content: "a"})
	buf.Push(Message{Content: "b"})
	buf.Push(Message{Content: "c"})

	all := buf.GetAll()
	if len(all) != 2 {
		t.Fatalf("expected 2 messages, got %d", len(all))
	}
	if all[0].Content != "b" || all[1].Content != "c" {
		t.Fatalf("unexpected order: %#v", all)
	}
}

func TestMessageBuffer_GetAll_Chronological(t *testing.T) {
	buf := NewMessageBuffer(3)
	buf.Push(Message{Content: "m1"})
	buf.Push(Message{Content: "m2"})
	buf.Push(Message{Content: "m3"})
	buf.Push(Message{Content: "m4"})

	all := buf.GetAll()
	if len(all) != 3 {
		t.Fatalf("expected 3 messages, got %d", len(all))
	}
	if all[0].Content != "m2" || all[2].Content != "m4" {
		t.Fatalf("unexpected order: %#v", all)
	}
}

func TestMessageBuffer_GetLast(t *testing.T) {
	buf := NewMessageBuffer(5)
	for i := 0; i < 4; i++ {
		buf.Push(Message{Content: fmt.Sprintf("m%d", i)})
	}

	last := buf.GetLast(2)
	if len(last) != 2 {
		t.Fatalf("expected 2 messages, got %d", len(last))
	}
	if last[0].Content != "m2" || last[1].Content != "m3" {
		t.Fatalf("unexpected last messages: %#v", last)
	}
}

func TestMessageBuffer_GetFirst(t *testing.T) {
	buf := NewMessageBuffer(5)
	for i := 0; i < 4; i++ {
		buf.Push(Message{Content: fmt.Sprintf("m%d", i)})
	}

	first := buf.GetFirst(2)
	if len(first) != 2 {
		t.Fatalf("expected 2 messages, got %d", len(first))
	}
	if first[0].Content != "m0" || first[1].Content != "m1" {
		t.Fatalf("unexpected first messages: %#v", first)
	}
}

func TestMessageBuffer_RemoveFirst(t *testing.T) {
	buf := NewMessageBuffer(5)
	for i := 0; i < 4; i++ {
		buf.Push(Message{Content: fmt.Sprintf("m%d", i)})
	}

	buf.RemoveFirst(2)
	all := buf.GetAll()
	if len(all) != 2 {
		t.Fatalf("expected 2 messages, got %d", len(all))
	}
	if all[0].Content != "m2" || all[1].Content != "m3" {
		t.Fatalf("unexpected remaining messages: %#v", all)
	}
}

func TestMessageBuffer_SnapshotRestore(t *testing.T) {
	buf := NewMessageBuffer(3)
	buf.Push(Message{Content: "a", Metadata: map[string]any{"k": "v"}})
	buf.Push(Message{Content: "b"})

	snapshot := buf.Snapshot()
	if snapshot[0].Metadata["k"] != "v" {
		t.Fatalf("expected metadata to be copied")
	}

	buf.Clear()
	buf.Restore(snapshot)

	all := buf.GetAll()
	if len(all) != 2 || all[0].Content != "a" {
		t.Fatalf("unexpected restore: %#v", all)
	}

	snapshot[0].Metadata["k"] = "changed"
	all = buf.GetAll()
	if all[0].Metadata["k"] != "v" {
		t.Fatalf("expected snapshot to be deep copied")
	}
}

func TestMessageBuffer_Concurrency(t *testing.T) {
	buf := NewMessageBuffer(50)
	var wg sync.WaitGroup

	for i := 0; i < 10; i++ {
		wg.Add(1)
		go func(worker int) {
			defer wg.Done()
			for j := 0; j < 100; j++ {
				buf.Push(Message{Content: fmt.Sprintf("w%d-%d", worker, j)})
				_ = buf.GetLast(5)
			}
		}(i)
	}

	wg.Wait()
	if buf.Count() == 0 {
		t.Fatalf("expected buffer to have messages")
	}
}

func BenchmarkMessageBuffer_Push(b *testing.B) {
	buf := NewMessageBuffer(100)
	msg := Message{Role: "user", Content: "test message", Timestamp: time.Now()}
	for i := 0; i < b.N; i++ {
		buf.Push(msg)
	}
}

func BenchmarkMessageBuffer_GetAll(b *testing.B) {
	buf := NewMessageBuffer(100)
	for i := 0; i < 100; i++ {
		buf.Push(Message{Role: "user", Content: fmt.Sprintf("message %d", i)})
	}
	b.ResetTimer()
	for i := 0; i < b.N; i++ {
		_ = buf.GetAll()
	}
}
