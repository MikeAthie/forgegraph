package store

import (
	"errors"
	"fmt"
	"sort"
	"strings"
)

// TieredWriteError represents failures in one or more tiers during a write operation.
type TieredWriteError struct {
	Operation   string
	Namespace   string
	Key         string
	TierErrors  map[int]error
	TierSuccess []int
}

func (e *TieredWriteError) Error() string {
	var failed []string
	// Sort tier numbers for consistent output
	tiers := make([]int, 0, len(e.TierErrors))
	for tier := range e.TierErrors {
		tiers = append(tiers, tier)
	}
	sort.Ints(tiers)

	for _, tier := range tiers {
		failed = append(failed, fmt.Sprintf("tier%d: %v", tier, e.TierErrors[tier]))
	}
	return fmt.Sprintf(
		"tiered %s partially failed (succeeded: %v, failed: %s)",
		e.Operation,
		e.TierSuccess,
		strings.Join(failed, "; "),
	)
}

// IsPartialSuccess returns true if at least one tier succeeded.
func (e *TieredWriteError) IsPartialSuccess() bool {
	return len(e.TierSuccess) > 0
}

// FailedTiers returns the list of tiers that failed.
func (e *TieredWriteError) FailedTiers() []int {
	tiers := make([]int, 0, len(e.TierErrors))
	for tier := range e.TierErrors {
		tiers = append(tiers, tier)
	}
	sort.Ints(tiers)
	return tiers
}

// TierError returns the error for a specific tier, or nil if it succeeded.
func (e *TieredWriteError) TierError(tier int) error {
	return e.TierErrors[tier]
}

// IsTieredPartialSuccess checks if an error is a TieredWriteError with at least one success.
func IsTieredPartialSuccess(err error) bool {
	var tieredErr *TieredWriteError
	if errors.As(err, &tieredErr) {
		return tieredErr.IsPartialSuccess()
	}
	return false
}

// IsTieredWriteError checks if an error is a TieredWriteError.
func IsTieredWriteError(err error) bool {
	var tieredErr *TieredWriteError
	return errors.As(err, &tieredErr)
}

// GetTieredWriteError extracts a TieredWriteError from an error chain if present.
func GetTieredWriteError(err error) (*TieredWriteError, bool) {
	var tieredErr *TieredWriteError
	if errors.As(err, &tieredErr) {
		return tieredErr, true
	}
	return nil, false
}
