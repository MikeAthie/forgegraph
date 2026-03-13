package gateway

import (
	"context"
	"fmt"
	"net/http"
	"net/http/httptest"
	"testing"
)

func TestMarketplaceManifestClientFetchSuccess(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if got := r.URL.Query().Get("tenant_id"); got != "tenant-1" {
			t.Fatalf("tenant_id = %s, want tenant-1", got)
		}
		if r.Header.Get("X-Forgegraph-Timestamp") == "" || r.Header.Get("X-Forgegraph-Signature") == "" {
			t.Fatal("expected signed headers")
		}
		w.Header().Set("Content-Type", "application/json")
		_, _ = fmt.Fprint(w, `{"data":{"tenant_id":"tenant-1","manifest_version":1,"checksum":"abc123","generated_at":"2026-03-12T00:00:00Z","tools":[{"name":"crm_lookup","version":"1.0.0","kind":"http","http":{"url":"https://example.com/tool","method":"POST"}}],"packages":[]}}`)
	}))
	defer server.Close()

	client := NewMarketplaceManifestClient(server.URL, "test-secret")
	payload, unchanged, err := client.Fetch(context.Background(), "tenant-1", "")
	if err != nil {
		t.Fatalf("Fetch() error = %v", err)
	}
	if unchanged {
		t.Fatal("expected changed manifest")
	}
	if payload == nil || len(payload.Tools) != 1 {
		t.Fatalf("payload.Tools = %#v, want one tool", payload)
	}
	if payload.Tools[0].Name != "crm_lookup" {
		t.Fatalf("tool name = %s, want crm_lookup", payload.Tools[0].Name)
	}
}

func TestMarketplaceManifestClientFetchNotModified(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if got := r.Header.Get("If-None-Match"); got != "abc123" {
			t.Fatalf("If-None-Match = %s, want abc123", got)
		}
		w.WriteHeader(http.StatusNotModified)
	}))
	defer server.Close()

	client := NewMarketplaceManifestClient(server.URL, "test-secret")
	payload, unchanged, err := client.Fetch(context.Background(), "tenant-1", "abc123")
	if err != nil {
		t.Fatalf("Fetch() error = %v", err)
	}
	if !unchanged {
		t.Fatal("expected unchanged manifest")
	}
	if payload != nil {
		t.Fatalf("payload = %#v, want nil", payload)
	}
}
