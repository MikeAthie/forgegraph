package executor

import (
	"fmt"
	"strings"

	"github.com/forgegraph/engine/application/port"
	"github.com/forgegraph/engine/domain"
)

func policyDeniedMessage(reason string) string {
	reason = trimPolicyReason(reason)
	if reason == "" {
		reason = "blocked by policy"
	}
	return fmt.Sprintf("policy denied: %s", reason)
}

func newPolicyDeniedValidationError(field string, reason string) error {
	return domain.NewValidationError(field, policyDeniedMessage(reason))
}

func validateLLMPolicy(runCtx *port.RunContext, provider string, model string) error {
	if runCtx == nil || runCtx.Policy == nil {
		return nil
	}
	if len(runCtx.Policy.AllowedProviders) > 0 {
		allowed := false
		for _, allowedProvider := range runCtx.Policy.AllowedProviders {
			if provider == allowedProvider {
				allowed = true
				break
			}
		}
		if !allowed {
			return newPolicyDeniedValidationError("provider", "provider blocked by policy")
		}
	}
	if len(runCtx.Policy.AllowedModels) > 0 {
		allowed := false
		for _, allowedModel := range runCtx.Policy.AllowedModels {
			if model == allowedModel {
				allowed = true
				break
			}
		}
		if !allowed {
			return newPolicyDeniedValidationError("model", "model blocked by policy")
		}
	}
	return nil
}

func trimPolicyReason(reason string) string {
	return strings.TrimSpace(reason)
}
