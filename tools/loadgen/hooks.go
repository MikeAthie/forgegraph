package main

import (
	"context"
	"os/exec"
	"runtime"
	"time"
)

type HookRecord struct {
	Name      string    `json:"name"`
	Command   string    `json:"command"`
	StartedAt time.Time `json:"started_at"`
	EndedAt   time.Time `json:"ended_at"`
	ExitCode  int       `json:"exit_code"`
	Output    string    `json:"output"`
	Error     string    `json:"error,omitempty"`
}

func RunConfiguredHooks(ctx context.Context, cfg Config, writer *ArtifactWriter) []HookRecord {
	return RunNamedHooks(
		ctx,
		cfg,
		writer,
		"llm-throttle-on",
		"engine-restart",
		"backend-worker-restart",
		"redis-degrade",
		"redis-recover",
		"llm-throttle-off",
	)
}

func RunNamedHooks(ctx context.Context, cfg Config, writer *ArtifactWriter, names ...string) []HookRecord {
	selected := map[string]bool{}
	for _, name := range names {
		selected[name] = true
	}
	var records []HookRecord
	for _, hook := range []struct {
		name    string
		command string
	}{
		{"llm-throttle-on", cfg.LLMThrottleOnHook},
		{"engine-restart", cfg.EngineRestartHook},
		{"backend-worker-restart", cfg.BackendWorkerRestartHook},
		{"redis-degrade", cfg.RedisDegradeHook},
		{"redis-recover", cfg.RedisRecoverHook},
		{"llm-throttle-off", cfg.LLMThrottleOffHook},
	} {
		if !selected[hook.name] {
			continue
		}
		if hook.command == "" {
			continue
		}
		record := RunHook(ctx, hook.name, hook.command)
		records = append(records, record)
		if writer != nil {
			_ = writer.AppendJSONL(writer.Paths.HookTimeline, record)
		}
	}
	return records
}

func RunHook(ctx context.Context, name, command string) HookRecord {
	startedAt := time.Now().UTC()
	record := HookRecord{
		Name:      name,
		Command:   command,
		StartedAt: startedAt,
		ExitCode:  -1,
	}
	cmd := shellCommand(ctx, command)
	output, err := cmd.CombinedOutput()
	record.EndedAt = time.Now().UTC()
	record.Output = string(output)
	if err != nil {
		record.Error = err.Error()
		if exitErr, ok := err.(*exec.ExitError); ok {
			record.ExitCode = exitErr.ExitCode()
		}
		return record
	}
	record.ExitCode = 0
	return record
}

func shellCommand(ctx context.Context, command string) *exec.Cmd {
	if runtime.GOOS == "windows" {
		return exec.CommandContext(ctx, "powershell", "-NoProfile", "-NonInteractive", "-Command", command)
	}
	return exec.CommandContext(ctx, "bash", "-lc", command)
}
