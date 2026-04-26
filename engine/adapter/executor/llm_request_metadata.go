package executor

import (
	"strings"

	"github.com/forgegraph/engine/application/port"
)

func BuildLLMRequestMetadata(runCtx *port.RunContext, nodeID string) map[string]string {
	metadata := map[string]string{}
	if runCtx != nil && runCtx.RunID != "" {
		metadata["run_id"] = runCtx.RunID
	}
	if runCtx != nil {
		llmAccess := runCtx.LLMAccess.Normalized()
		metadata["llm_mode"] = llmAccess.Mode
		metadata["credential_source"] = CredentialSourceForMode(llmAccess.Mode)
		if llmAccess.CredentialID != "" {
			metadata["credential_id"] = llmAccess.CredentialID
		}
	}
	if nodeID != "" {
		metadata["node_id"] = nodeID
	}
	if len(metadata) == 0 {
		return nil
	}
	return metadata
}

func ResolveLLMProviderForAccess(
	runCtx *port.RunContext,
	configuredProvider string,
	credentialID string,
) string {
	provider := strings.ToLower(strings.TrimSpace(configuredProvider))
	if provider != "" {
		return provider
	}
	if runCtx == nil {
		return provider
	}
	access := runCtx.LLMAccess.Normalized()
	if access.Provider == "" {
		return provider
	}
	if access.Mode == port.LLMModeBYOK || strings.TrimSpace(credentialID) == "" {
		return access.Provider
	}
	return provider
}

func ApplyLLMAccessToRequest(runCtx *port.RunContext, request *LLMRequest) {
	if runCtx == nil || request == nil {
		return
	}
	access := runCtx.LLMAccess.Normalized()
	if request.Metadata == nil {
		request.Metadata = map[string]string{}
	}
	request.LLMMode = access.Mode
	request.CredentialSource = CredentialSourceForMode(access.Mode)
	request.Metadata["llm_mode"] = access.Mode
	request.Metadata["credential_source"] = request.CredentialSource
	if access.CredentialID != "" {
		request.Metadata["credential_id"] = access.CredentialID
	}
	if access.Provider != "" && (access.Mode == port.LLMModeBYOK || request.Provider == "") {
		request.Provider = access.Provider
	}
	if access.Mode == port.LLMModeBYOK {
		request.APIKey = access.APIKey
		request.CredentialID = ""
	}
}

func CredentialSourceForMode(mode string) string {
	if strings.ToLower(strings.TrimSpace(mode)) == port.LLMModeBYOK {
		return port.LLMModeBYOK
	}
	return port.LLMModeManaged
}

func LLMModeForMetadata(runCtx *port.RunContext) string {
	if runCtx == nil {
		return port.LLMModeManaged
	}
	return runCtx.LLMAccess.Normalized().Mode
}

func responseLLMMode(runCtx *port.RunContext, response *LLMResponse) string {
	if response != nil && strings.TrimSpace(response.LLMMode) != "" {
		switch strings.ToLower(strings.TrimSpace(response.LLMMode)) {
		case port.LLMModeBYOK:
			return port.LLMModeBYOK
		}
	}
	return LLMModeForMetadata(runCtx)
}
