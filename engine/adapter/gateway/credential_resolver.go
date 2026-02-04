package gateway

import (
	"context"
	"encoding/json"
	"fmt"
	"net/http"
	"strings"
	"time"
)

// CredentialResolver resolves provider credentials from the control plane.
type CredentialResolver interface {
	Resolve(ctx context.Context, credentialID string, tenantID string) (string, string, error)
}

// BackendCredentialResolver resolves credentials via control plane HTTP API.
type BackendCredentialResolver struct {
	baseURL string
	secret  string
	client  *http.Client
}

// NewBackendCredentialResolver creates a resolver for the control plane.
func NewBackendCredentialResolver(baseURL string, secret string) *BackendCredentialResolver {
	return &BackendCredentialResolver{
		baseURL: strings.TrimRight(baseURL, "/"),
		secret:  secret,
		client: &http.Client{
			Timeout: 10 * time.Second,
		},
	}
}

func (r *BackendCredentialResolver) Resolve(ctx context.Context, credentialID string, tenantID string) (string, string, error) {
	if credentialID == "" {
		return "", "", fmt.Errorf("credential_id is required")
	}
	if tenantID == "" {
		return "", "", fmt.Errorf("tenant_id is required")
	}

	url := fmt.Sprintf("%s/api/engine/credentials/%s?tenant_id=%s", r.baseURL, credentialID, tenantID)
	req, err := http.NewRequestWithContext(ctx, http.MethodGet, url, nil)
	if err != nil {
		return "", "", fmt.Errorf("build request: %w", err)
	}

	timestamp := fmt.Sprintf("%d", time.Now().UnixMilli())
	signature := signPayload(r.secret, timestamp, []byte{})
	req.Header.Set("X-Forgegraph-Timestamp", timestamp)
	req.Header.Set("X-Forgegraph-Signature", signature)

	resp, err := r.client.Do(req)
	if err != nil {
		return "", "", fmt.Errorf("request failed: %w", err)
	}
	defer resp.Body.Close()

	if resp.StatusCode >= 400 {
		return "", "", fmt.Errorf("credential resolve failed: status %d", resp.StatusCode)
	}

	var wrapper struct {
		Data struct {
			Provider     string `json:"provider"`
			APIKey       string `json:"api_key"`
			CredentialID string `json:"credential_id"`
		} `json:"data"`
	}

	if err := json.NewDecoder(resp.Body).Decode(&wrapper); err != nil {
		return "", "", fmt.Errorf("decode response: %w", err)
	}

	return wrapper.Data.Provider, wrapper.Data.APIKey, nil
}
