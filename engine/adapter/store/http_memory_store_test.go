package store

import (
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"
)

func TestHTTPMemoryStoreSetGetDelete(t *testing.T) {
	entry := map[string]any{}
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		namespace := r.URL.Query().Get("namespace")
		key := r.URL.Query().Get("key")
		if namespace != "tenant-a" || key != "session-buffer" {
			http.Error(w, `{"error":{"code":"NOT_FOUND","message":"missing"}}`, http.StatusNotFound)
			return
		}

		switch r.Method {
		case http.MethodPut:
			var payload map[string]any
			if err := json.NewDecoder(r.Body).Decode(&payload); err != nil {
				t.Fatalf("decode put payload: %v", err)
			}
			entry = map[string]any{"value": payload["value"]}
			w.Header().Set("Content-Type", "application/json")
			_, _ = w.Write([]byte(`{"data":{"stored":true}}`))
		case http.MethodGet:
			if entry == nil {
				http.Error(w, `{"error":{"code":"NOT_FOUND","message":"missing"}}`, http.StatusNotFound)
				return
			}
			body, _ := json.Marshal(map[string]any{"data": entry})
			w.Header().Set("Content-Type", "application/json")
			_, _ = w.Write(body)
		case http.MethodDelete:
			if entry == nil {
				http.Error(w, `{"error":{"code":"NOT_FOUND","message":"missing"}}`, http.StatusNotFound)
				return
			}
			entry = nil
			w.Header().Set("Content-Type", "application/json")
			_, _ = w.Write([]byte(`{"data":{"cleared":true}}`))
		default:
			http.Error(w, "method not allowed", http.StatusMethodNotAllowed)
		}
	}))
	defer server.Close()

	store := NewHTTPMemoryStore(server.URL, "test-secret", server.Client())
	ctx := context.Background()

	if err := store.Set(ctx, "tenant-a", "session-buffer", map[string]any{"messages": []string{"hi"}}, 60); err != nil {
		t.Fatalf("Set() error = %v", err)
	}

	value, found, err := store.Get(ctx, "tenant-a", "session-buffer")
	if err != nil {
		t.Fatalf("Get() error = %v", err)
	}
	if !found {
		t.Fatal("Get() found = false, want true")
	}
	got, ok := value.(map[string]any)
	if !ok {
		t.Fatalf("Get() type = %T, want map[string]any", value)
	}
	if got["messages"] == nil {
		t.Fatalf("Get() missing messages payload: %#v", got)
	}

	deleted, err := store.Delete(ctx, "tenant-a", "session-buffer")
	if err != nil {
		t.Fatalf("Delete() error = %v", err)
	}
	if !deleted {
		t.Fatal("Delete() deleted = false, want true")
	}

	_, found, err = store.Get(ctx, "tenant-a", "session-buffer")
	if err != nil {
		t.Fatalf("Get() after delete error = %v", err)
	}
	if found {
		t.Fatal("Get() after delete found = true, want false")
	}
}
