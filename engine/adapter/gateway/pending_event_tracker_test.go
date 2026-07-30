package gateway

import (
	"context"
	"sync"
	"testing"
	"time"
)

func TestPendingEventTrackerSupportsConcurrentWaitAndLaterAdd(t *testing.T) {
	var tracker pendingEventTracker

	if err := tracker.Wait(context.Background()); err != nil {
		t.Fatalf("empty Wait() error = %v", err)
	}

	tracker.Add()
	waitStarted := make(chan struct{})
	waitDone := make(chan error, 1)
	go func() {
		close(waitStarted)
		waitDone <- tracker.Wait(context.Background())
	}()
	<-waitStarted

	tracker.Add()
	tracker.Done()
	select {
	case err := <-waitDone:
		t.Fatalf("Wait() returned before all pending events completed: %v", err)
	default:
	}
	tracker.Done()

	select {
	case err := <-waitDone:
		if err != nil {
			t.Fatalf("Wait() error = %v", err)
		}
	case <-time.After(time.Second):
		t.Fatal("Wait() did not return after counter reached zero")
	}

	// A later queue generation is independent and remains safe while callers
	// perform empty Flush-style waits.
	var wg sync.WaitGroup
	for i := 0; i < 100; i++ {
		wg.Add(1)
		go func() {
			defer wg.Done()
			tracker.Add()
			tracker.Done()
		}()
	}
	wg.Wait()
	if err := tracker.Wait(context.Background()); err != nil {
		t.Fatalf("final Wait() error = %v", err)
	}
}

func TestPendingEventTrackerWaitHonorsContext(t *testing.T) {
	var tracker pendingEventTracker
	tracker.Add()
	defer tracker.Done()

	ctx, cancel := context.WithCancel(context.Background())
	cancel()
	if err := tracker.Wait(ctx); err == nil {
		t.Fatal("Wait() error = nil, want canceled context")
	}
}
