#!/usr/bin/env bash
set -euo pipefail

mapfile -t live_specs < <(find frontend/__tests__/e2e -maxdepth 1 -name '*live.spec.ts' | sort)
live_helpers=(
  "frontend/__tests__/e2e/live-helpers.ts"
)

blocked_patterns=(
  "page.route"
  "route.fulfill"
  "proxyBackendApi"
  "seedFrontendControlPlaneFixture"
  "openAuthenticatedPage"
  "openBackendAuthenticatedPage"
  "login(page"
  "from \"./helpers\""
  "from './helpers'"
)

required_live_specs=(
  "frontend/__tests__/e2e/human-gate-live.spec.ts"
  "frontend/__tests__/e2e/production-launch-live.spec.ts"
  "frontend/__tests__/e2e/operator-recovery-live.spec.ts"
  "frontend/__tests__/e2e/tenant-isolation-live.spec.ts"
  "frontend/__tests__/e2e/failure-retry-dead-letter-live.spec.ts"
)

for spec in "${required_live_specs[@]}"; do
  if [[ ! -f "$spec" ]]; then
    echo "Missing required live Playwright spec: $spec" >&2
    exit 1
  fi
done

for spec in "${live_specs[@]}" "${live_helpers[@]}"; do
  for pattern in "${blocked_patterns[@]}"; do
    if grep -Fq "$pattern" "$spec"; then
      echo "Live Playwright spec $spec uses blocked mock/proxy pattern: $pattern" >&2
      exit 1
    fi
  done
done

echo "Live Playwright specs do not use mocked API route patterns."
