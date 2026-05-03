package gateway

import (
	"context"
	"encoding/json"
	"io"
	"net/http"
	"net/http/httptest"
	"os"
	"path/filepath"
	"strings"
	"testing"
	"time"

	"github.com/forgegraph/engine/application/port"
)

func TestHTTPEventEmitterSignsCallbacksAndDoesNotLeakCallbackSecret(t *testing.T) {
	const secretSentinel = "fg-secret-sentinel-callback"

	var receivedBody []byte
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.Header.Get("X-Forgegraph-Timestamp") == "" {
			t.Fatal("missing signed timestamp")
		}
		if r.Header.Get("X-Forgegraph-Signature") == "" {
			t.Fatal("missing signature")
		}
		var err error
		receivedBody, err = readAllRequestBody(r)
		if err != nil {
			t.Fatalf("read body: %v", err)
		}
		w.WriteHeader(http.StatusServiceUnavailable)
	}))
	defer server.Close()

	spoolPath := filepath.Join(t.TempDir(), "events.jsonl")
	emitter, err := NewHTTPEventEmitter(HTTPEventEmitterConfig{
		CallbackURL:        server.URL,
		SignatureSecret:    secretSentinel,
		Client:             server.Client(),
		MaxRetries:         1,
		RetryDelay:         time.Millisecond,
		SpoolPath:          spoolPath,
		SpoolFlushInterval: time.Hour,
	})
	if err != nil {
		t.Fatalf("NewHTTPEventEmitter() error = %v", err)
	}
	defer func() {
		closeCtx, cancel := context.WithTimeout(context.Background(), time.Second)
		defer cancel()
		if closeErr := emitter.Close(closeCtx); closeErr != nil {
			t.Fatalf("Close() error = %v", closeErr)
		}
	}()

	emitErr := emitter.Emit(context.Background(), port.NewEvent(port.EventTypeRunStarted, "run-1"))
	if emitErr == nil {
		t.Fatal("expected delivery failure")
	}
	if strings.Contains(emitErr.Error(), secretSentinel) {
		t.Fatal("callback secret leaked into event delivery error")
	}
	if strings.Contains(string(receivedBody), secretSentinel) {
		t.Fatal("callback secret leaked into callback body")
	}
	spooled, readErr := os.ReadFile(spoolPath)
	if readErr != nil {
		t.Fatalf("ReadFile() error = %v", readErr)
	}
	if strings.Contains(string(spooled), secretSentinel) {
		t.Fatal("callback secret leaked into spooled event")
	}
}

func TestBackendCredentialResolverSignsControlPlaneRequest(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path != "/api/engine/credentials/credential-1" {
			t.Fatalf("path = %s", r.URL.Path)
		}
		if got := r.URL.Query().Get("tenant_id"); got != "tenant-1" {
			t.Fatalf("tenant_id = %s", got)
		}
		if r.Header.Get("X-Forgegraph-Timestamp") == "" {
			t.Fatal("missing signed timestamp")
		}
		if r.Header.Get("X-Forgegraph-Signature") == "" {
			t.Fatal("missing signature")
		}
		_ = json.NewEncoder(w).Encode(map[string]any{
			"data": map[string]any{
				"provider":      "openai",
				"api_key":       "resolved-provider-token",
				"credential_id": "credential-1",
			},
		})
	}))
	defer server.Close()

	resolver := NewBackendCredentialResolver(server.URL, "resolver-secret")
	resolver.client = server.Client()

	provider, apiKey, err := resolver.Resolve(context.Background(), "credential-1", "tenant-1")
	if err != nil {
		t.Fatalf("Resolve() error = %v", err)
	}
	if provider != "openai" || apiKey != "resolved-provider-token" {
		t.Fatalf("Resolve() = (%s, %s), want openai/resolved-provider-token", provider, apiKey)
	}
}

func TestBackendCredentialResolverDoesNotLeakCallbackSecretInErrors(t *testing.T) {
	const secretSentinel = "fg-secret-sentinel-resolver"
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusInternalServerError)
	}))
	defer server.Close()

	resolver := NewBackendCredentialResolver(server.URL, secretSentinel)
	resolver.client = server.Client()

	_, _, err := resolver.Resolve(context.Background(), "credential-1", "tenant-1")
	if err == nil {
		t.Fatal("expected resolver error")
	}
	if strings.Contains(err.Error(), secretSentinel) {
		t.Fatal("callback secret leaked into credential resolver error")
	}
}

func TestBackendAcknowledgedRuntimeIntentPublisherSignsOutcomeLookups(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.Header.Get("X-Forgegraph-Timestamp") == "" {
			t.Fatal("missing signed timestamp")
		}
		if r.Header.Get("X-Forgegraph-Signature") == "" {
			t.Fatal("missing signature")
		}
		runtimeIntentOutcomeResponse(t, w, "processed")
	}))
	defer server.Close()

	publisher := newBackendAckPublisherForTest(t, server.URL, &stubInnerRuntimeIntentPublisher{}, 50*time.Millisecond)
	err := publisher.Publish(context.Background(), &port.RuntimeIntentEnvelope{
		IntentID:   "intent-signed-lookup",
		IntentType: "set_run_status",
		RunID:      "run-1",
	})
	if err != nil {
		t.Fatalf("Publish() error = %v", err)
	}
}

func readAllRequestBody(r *http.Request) ([]byte, error) {
	defer r.Body.Close()
	return io.ReadAll(r.Body)
}
