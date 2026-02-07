package executor

import (
	"context"
	"testing"
	"time"

	"github.com/forgegraph/engine/application/port"
	"github.com/forgegraph/engine/domain/entity"
)

func TestParseRetryAfterMsSeconds(t *testing.T) {
	got := parseRetryAfterMs("3", time.Now())
	if got != 3000 {
		t.Fatalf("parseRetryAfterMs = %d, want 3000", got)
	}
}

func TestResolveTenantProviderThrottleMsFromPolicy(t *testing.T) {
	ctx := context.Background()
	ctx = port.WithRunContext(ctx, &port.RunContext{
		Policy: &entity.ExecutionPolicy{
			ProviderMinIntervalMs: 120,
			ProviderMinIntervalByNameMs: map[string]int{
				"openai": 75,
			},
		},
	})

	got := resolveTenantProviderThrottleMs(ctx, "openai", nil)
	if got != 75 {
		t.Fatalf("resolveTenantProviderThrottleMs = %d, want 75", got)
	}
}

func TestThrottleTenantProviderAppliesDelay(t *testing.T) {
	ctx := context.Background()
	intervalMs := 30

	if err := throttleTenantProvider(ctx, "tenant-test", "openai", intervalMs); err != nil {
		t.Fatalf("first throttleTenantProvider call failed: %v", err)
	}

	start := time.Now()
	if err := throttleTenantProvider(ctx, "tenant-test", "openai", intervalMs); err != nil {
		t.Fatalf("second throttleTenantProvider call failed: %v", err)
	}

	elapsed := time.Since(start).Milliseconds()
	if elapsed < 20 {
		t.Fatalf("expected tenant throttle delay >=20ms, got %dms", elapsed)
	}
}
