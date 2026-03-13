package gateway

import (
	"context"
	"encoding/json"
	"fmt"
	"net/http"
	"strings"
	"time"

	"github.com/forgegraph/engine/adapter/tool"
)

type MarketplaceManifestPackage struct {
	PackageSlug      string `json:"package_slug"`
	PackageName      string `json:"package_name"`
	ReleaseID        string `json:"release_id"`
	ReleaseVersion   string `json:"release_version"`
	PackageKind      string `json:"package_kind"`
	DeliveryState    string `json:"delivery_state"`
	DeliveryReason   string `json:"delivery_reason"`
	CloudAllowed     bool   `json:"cloud_allowed"`
	ManifestVersion  int    `json:"manifest_version"`
	ManifestChecksum string `json:"manifest_checksum"`
}

type MarketplaceManifestPayload struct {
	TenantID        string                       `json:"tenant_id"`
	ManifestVersion int                          `json:"manifest_version"`
	Checksum        string                       `json:"checksum"`
	GeneratedAt     string                       `json:"generated_at"`
	Tools           []tool.Definition            `json:"tools"`
	Packages        []MarketplaceManifestPackage `json:"packages"`
}

type MarketplaceManifestClient struct {
	baseURL string
	secret  string
	client  *http.Client
}

func NewMarketplaceManifestClient(baseURL string, secret string) *MarketplaceManifestClient {
	return &MarketplaceManifestClient{
		baseURL: strings.TrimRight(baseURL, "/"),
		secret:  secret,
		client: &http.Client{
			Timeout: 10 * time.Second,
		},
	}
}

func (c *MarketplaceManifestClient) Fetch(ctx context.Context, tenantID string, previousChecksum string) (*MarketplaceManifestPayload, bool, error) {
	if tenantID == "" {
		return nil, false, fmt.Errorf("tenant_id is required")
	}

	url := fmt.Sprintf("%s/api/marketplace/runtime-manifests?tenant_id=%s", c.baseURL, tenantID)
	req, err := http.NewRequestWithContext(ctx, http.MethodGet, url, nil)
	if err != nil {
		return nil, false, fmt.Errorf("build request: %w", err)
	}

	timestamp := fmt.Sprintf("%d", time.Now().UnixMilli())
	signature := signPayload(c.secret, timestamp, []byte{})
	req.Header.Set("X-Forgegraph-Timestamp", timestamp)
	req.Header.Set("X-Forgegraph-Signature", signature)
	if previousChecksum != "" {
		req.Header.Set("If-None-Match", previousChecksum)
	}

	resp, err := c.client.Do(req)
	if err != nil {
		return nil, false, fmt.Errorf("request failed: %w", err)
	}
	defer resp.Body.Close()

	if resp.StatusCode == http.StatusNotModified {
		return nil, true, nil
	}
	if resp.StatusCode >= 400 {
		return nil, false, fmt.Errorf("manifest fetch failed: status %d", resp.StatusCode)
	}

	var wrapper struct {
		Data MarketplaceManifestPayload `json:"data"`
	}
	if err := json.NewDecoder(resp.Body).Decode(&wrapper); err != nil {
		return nil, false, fmt.Errorf("decode response: %w", err)
	}
	return &wrapper.Data, false, nil
}
