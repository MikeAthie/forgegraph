package main

import (
	"encoding/json"
	"os"
	"path/filepath"
	"sync"
	"time"
)

type ArtifactWriter struct {
	Paths ArtifactPaths
	mu    sync.Mutex
}

func NewArtifactWriter(root string, startedAt time.Time) (*ArtifactWriter, error) {
	runRoot := filepath.Join(root, startedAt.UTC().Format("20060102T150405Z"))
	paths := ArtifactPaths{
		Root:           runRoot,
		RequestsJSONL:  filepath.Join(runRoot, "requests.jsonl"),
		RunsJSONL:      filepath.Join(runRoot, "runs.jsonl"),
		WSEventsJSONL:  filepath.Join(runRoot, "ws-events.jsonl"),
		HookTimeline:   filepath.Join(runRoot, "hook-timeline.jsonl"),
		MetricsSummary: filepath.Join(runRoot, "metrics-summary.json"),
		TenantManifest: filepath.Join(runRoot, "tenant-manifest.json"),
	}
	if err := os.MkdirAll(runRoot, 0o755); err != nil {
		return nil, err
	}
	return &ArtifactWriter{Paths: paths}, nil
}

func (writer *ArtifactWriter) AppendJSONL(path string, value any) error {
	writer.mu.Lock()
	defer writer.mu.Unlock()
	data, err := json.Marshal(value)
	if err != nil {
		return err
	}
	data = append(data, '\n')
	file, err := os.OpenFile(path, os.O_CREATE|os.O_APPEND|os.O_WRONLY, 0o644)
	if err != nil {
		return err
	}
	defer file.Close()
	_, err = file.Write(data)
	return err
}

func (writer *ArtifactWriter) WriteTenantManifest(plan WorkloadPlan) error {
	publicPlan := plan
	publicPlan.Tenants = append([]TenantPlan(nil), plan.Tenants...)
	publicPlan.Agents = append([]AgentPlan(nil), plan.Agents...)
	publicPlan.Runs = append([]RunPlan(nil), plan.Runs...)
	for index := range publicPlan.Tenants {
		publicPlan.Tenants[index].Password = ""
		publicPlan.Tenants[index].AccessToken = ""
	}
	return writeJSON(writer.Paths.TenantManifest, publicPlan)
}
