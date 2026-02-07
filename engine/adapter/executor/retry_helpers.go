package executor

import (
	"context"
	"net/http"
	"strconv"
	"strings"
	"sync"
	"time"

	"github.com/forgegraph/engine/application/port"
)

const maxProviderBackoffMs = 60_000

type tenantProviderThrottleState struct {
	mu          sync.Mutex
	nextAllowed time.Time
}

var tenantProviderThrottle sync.Map // key -> *tenantProviderThrottleState

func parseRetryAfterMs(headerValue string, now time.Time) int {
	trimmed := strings.TrimSpace(headerValue)
	if trimmed == "" {
		return 0
	}

	if seconds, err := strconv.Atoi(trimmed); err == nil {
		if seconds <= 0 {
			return 0
		}
		return seconds * 1000
	}

	retryAt, err := http.ParseTime(trimmed)
	if err != nil {
		return 0
	}
	delay := int(retryAt.Sub(now).Milliseconds())
	if delay < 0 {
		return 0
	}
	return delay
}

func isQuotaExhaustedRateLimit(body string) bool {
	normalized := strings.ToLower(strings.TrimSpace(body))
	if normalized == "" {
		return false
	}
	signatures := []string{
		"insufficient_quota",
		"quota exceeded",
		"quota_exceeded",
		"quota exhausted",
		"billing",
		"payment required",
	}
	for _, signature := range signatures {
		if strings.Contains(normalized, signature) {
			return true
		}
	}
	return false
}

func computeProviderRetryDelayMs(baseBackoffMs, attempt int, retryAfterMs int) int {
	backoff := baseBackoffMs
	if backoff <= 0 {
		backoff = 100
	}
	if attempt > 1 {
		backoff = backoff * (1 << (attempt - 1))
	}
	if backoff > maxProviderBackoffMs {
		backoff = maxProviderBackoffMs
	}
	if retryAfterMs > backoff {
		backoff = retryAfterMs
	}
	if backoff > maxProviderBackoffMs {
		backoff = maxProviderBackoffMs
	}
	if backoff < 0 {
		return 0
	}
	return backoff
}

func resolveTenantProviderThrottleMs(ctx context.Context, provider string, nodeConfig map[string]any) int {
	if nodeConfig != nil {
		if override := readThrottleInt(nodeConfig["tenant_throttle_ms"]); override > 0 {
			return override
		}
		if override := readThrottleInt(nodeConfig["provider_throttle_ms"]); override > 0 {
			return override
		}
	}

	policy := port.PolicyFromContext(ctx)
	if policy == nil {
		return 0
	}

	normalizedProvider := strings.ToLower(strings.TrimSpace(provider))
	if normalizedProvider != "" && len(policy.ProviderMinIntervalByNameMs) > 0 {
		if override, ok := policy.ProviderMinIntervalByNameMs[normalizedProvider]; ok && override > 0 {
			return override
		}
	}
	if policy.ProviderMinIntervalMs > 0 {
		return policy.ProviderMinIntervalMs
	}
	return 0
}

func throttleTenantProvider(ctx context.Context, tenantID, provider string, intervalMs int) error {
	if intervalMs <= 0 {
		return nil
	}

	normalizedTenant := strings.TrimSpace(tenantID)
	if normalizedTenant == "" {
		normalizedTenant = "global"
	}
	normalizedProvider := strings.TrimSpace(strings.ToLower(provider))
	if normalizedProvider == "" {
		normalizedProvider = "default"
	}

	key := normalizedTenant + ":" + normalizedProvider
	stateAny, _ := tenantProviderThrottle.LoadOrStore(key, &tenantProviderThrottleState{})
	state := stateAny.(*tenantProviderThrottleState)

	state.mu.Lock()
	defer state.mu.Unlock()

	now := time.Now()
	if now.Before(state.nextAllowed) {
		waitDuration := state.nextAllowed.Sub(now)
		timer := time.NewTimer(waitDuration)
		defer timer.Stop()
		select {
		case <-ctx.Done():
			return ctx.Err()
		case <-timer.C:
		}
	}

	state.nextAllowed = time.Now().Add(time.Duration(intervalMs) * time.Millisecond)
	return nil
}

func readThrottleInt(value any) int {
	switch typed := value.(type) {
	case int:
		return typed
	case int64:
		return int(typed)
	case float64:
		return int(typed)
	case float32:
		return int(typed)
	case string:
		parsed, err := strconv.Atoi(strings.TrimSpace(typed))
		if err == nil {
			return parsed
		}
	}
	return 0
}
