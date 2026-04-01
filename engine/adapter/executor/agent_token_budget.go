package executor

import "time"

const (
	tokenBudgetCompletionThreshold = 0.9
	tokenBudgetDiminishingDelta    = 500
)

type budgetTracker struct {
	ContinuationCount    int
	LastDeltaTokens      int
	LastGlobalTurnTokens int
	StartedAt            time.Time
}

type tokenBudgetCompletion struct {
	ContinuationCount  int
	Pct                int
	TurnTokens         int
	Budget             int
	DiminishingReturns bool
	DurationMs         int64
}

func newBudgetTracker(now time.Time) *budgetTracker {
	return &budgetTracker{
		StartedAt: now,
	}
}

func (t *budgetTracker) check(budget int, globalTurnTokens int, now time.Time) (string, string, *tokenBudgetCompletion) {
	if t == nil || budget <= 0 {
		return "stop", "", nil
	}

	pct := int(float64(globalTurnTokens) / float64(budget) * 100.0)
	deltaSinceLastCheck := globalTurnTokens - t.LastGlobalTurnTokens
	isDiminishing := t.ContinuationCount >= 3 &&
		deltaSinceLastCheck < tokenBudgetDiminishingDelta &&
		t.LastDeltaTokens < tokenBudgetDiminishingDelta

	if !isDiminishing && float64(globalTurnTokens) < float64(budget)*tokenBudgetCompletionThreshold {
		t.ContinuationCount++
		t.LastDeltaTokens = deltaSinceLastCheck
		t.LastGlobalTurnTokens = globalTurnTokens
		return "continue", buildBudgetContinuationMessage(pct, globalTurnTokens, budget), nil
	}

	if isDiminishing || t.ContinuationCount > 0 {
		return "stop", "", &tokenBudgetCompletion{
			ContinuationCount:  t.ContinuationCount,
			Pct:                pct,
			TurnTokens:         globalTurnTokens,
			Budget:             budget,
			DiminishingReturns: isDiminishing,
			DurationMs:         now.Sub(t.StartedAt).Milliseconds(),
		}
	}

	return "stop", "", nil
}

func buildBudgetContinuationMessage(pct int, turnTokens int, budget int) string {
	return "You still have budget remaining for this agent turn. Continue working before stopping. " +
		"Current usage is " + itoa(pct) + "% of budget (" + itoa(turnTokens) + "/" + itoa(budget) + " tokens)."
}

func itoa(value int) string {
	if value == 0 {
		return "0"
	}
	negative := value < 0
	if negative {
		value = -value
	}
	buf := [20]byte{}
	index := len(buf)
	for value > 0 {
		index--
		buf[index] = byte('0' + value%10)
		value /= 10
	}
	if negative {
		index--
		buf[index] = '-'
	}
	return string(buf[index:])
}
