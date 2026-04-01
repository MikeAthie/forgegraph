package executor

import (
	"testing"
	"time"
)

func TestBudgetTrackerCheck_ContinueWhileBudgetHasRoom(t *testing.T) {
	tracker := newBudgetTracker(time.Unix(1700000000, 0))

	action, nudge, completion := tracker.check(1000, 200, time.Unix(1700000001, 0))
	if action != "continue" {
		t.Fatalf("action = %s, want continue", action)
	}
	if nudge == "" {
		t.Fatal("expected continuation nudge message")
	}
	if completion != nil {
		t.Fatalf("completion = %#v, want nil", completion)
	}
	if tracker.ContinuationCount != 1 {
		t.Fatalf("continuation_count = %d, want 1", tracker.ContinuationCount)
	}
}

func TestBudgetTrackerCheck_StopWithCompletionAfterContinuation(t *testing.T) {
	tracker := newBudgetTracker(time.Unix(1700000000, 0))
	tracker.ContinuationCount = 1
	tracker.LastGlobalTurnTokens = 300
	tracker.LastDeltaTokens = 300

	action, nudge, completion := tracker.check(1000, 1000, time.Unix(1700000002, 0))
	if action != "stop" {
		t.Fatalf("action = %s, want stop", action)
	}
	if nudge != "" {
		t.Fatalf("nudge = %q, want empty", nudge)
	}
	if completion == nil {
		t.Fatal("expected completion payload")
	}
	if completion.Pct != 100 {
		t.Fatalf("pct = %d, want 100", completion.Pct)
	}
	if completion.ContinuationCount != 1 {
		t.Fatalf("continuation_count = %d, want 1", completion.ContinuationCount)
	}
}

func TestBudgetTrackerCheck_StopOnDiminishingReturns(t *testing.T) {
	tracker := newBudgetTracker(time.Unix(1700000000, 0))
	tracker.ContinuationCount = 3
	tracker.LastGlobalTurnTokens = 900
	tracker.LastDeltaTokens = 200

	action, _, completion := tracker.check(2000, 1000, time.Unix(1700000004, 0))
	if action != "stop" {
		t.Fatalf("action = %s, want stop", action)
	}
	if completion == nil {
		t.Fatal("expected completion payload")
	}
	if !completion.DiminishingReturns {
		t.Fatal("expected diminishing returns flag")
	}
}
