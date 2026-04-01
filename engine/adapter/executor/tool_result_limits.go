package executor

import (
	"encoding/json"
	"fmt"
	"strings"
	"unicode/utf8"

	"github.com/forgegraph/engine/adapter/tool"
)

const (
	defaultMaxResultSizeChars = 50_000
	maxToolResultTokens       = 100_000
	bytesPerTokenEstimate     = 4
	maxToolResultBytes        = maxToolResultTokens * bytesPerTokenEstimate
	toolSummaryMaxLength      = 50
	truncatedPreviewSuffix    = "\n...[truncated]"
)

func applyToolResultLimits(def *tool.Definition, result map[string]any) map[string]any {
	if len(result) == 0 {
		return result
	}
	payload, ok := result["result"]
	if !ok || payload == nil {
		return result
	}

	rendered := renderToolResult(payload)
	charLimit := defaultMaxResultSizeChars
	if def != nil && def.MaxResultSize > 0 && def.MaxResultSize < charLimit {
		charLimit = def.MaxResultSize
	}

	if rendered.charCount <= charLimit && rendered.byteCount <= maxToolResultBytes {
		return result
	}

	limited := cloneToolResult(result)
	preview := truncateToolResultPreview(rendered.text, charLimit, maxToolResultBytes)
	limited["result"] = preview
	limited["result_truncated"] = true
	limited["result_summary"] = summarizeToolResultPreview(preview)
	limited["result_original_chars"] = rendered.charCount
	limited["result_original_bytes"] = rendered.byteCount
	limited["result_limit_chars"] = charLimit
	limited["result_limit_bytes"] = maxToolResultBytes
	return limited
}

type renderedToolResult struct {
	text      string
	charCount int
	byteCount int
}

func renderToolResult(value any) renderedToolResult {
	switch typed := value.(type) {
	case string:
		return renderedToolResult{
			text:      typed,
			charCount: utf8.RuneCountInString(typed),
			byteCount: len([]byte(typed)),
		}
	default:
		raw, err := json.Marshal(typed)
		if err != nil {
			fallback := strings.TrimSpace(fmt.Sprintf("%v", typed))
			return renderedToolResult{
				text:      fallback,
				charCount: utf8.RuneCountInString(fallback),
				byteCount: len([]byte(fallback)),
			}
		}
		text := string(raw)
		return renderedToolResult{
			text:      text,
			charCount: utf8.RuneCountInString(text),
			byteCount: len(raw),
		}
	}
}

func truncateToolResultPreview(value string, charLimit int, byteLimit int) string {
	if value == "" {
		return value
	}
	if charLimit <= 0 || byteLimit <= 0 {
		return truncatedPreviewSuffix
	}

	suffixBytes := len([]byte(truncatedPreviewSuffix))
	suffixChars := utf8.RuneCountInString(truncatedPreviewSuffix)
	if byteLimit <= suffixBytes || charLimit <= suffixChars {
		return truncatedPreviewSuffix
	}

	var builder strings.Builder
	currentChars := 0
	currentBytes := 0
	for _, r := range value {
		runeBytes := utf8.RuneLen(r)
		if runeBytes < 0 {
			runeBytes = 0
		}
		if currentChars+1 > charLimit-suffixChars || currentBytes+runeBytes > byteLimit-suffixBytes {
			break
		}
		builder.WriteRune(r)
		currentChars++
		currentBytes += runeBytes
	}
	preview := strings.TrimRight(builder.String(), "\n")
	if preview == "" {
		return truncatedPreviewSuffix
	}
	return preview + truncatedPreviewSuffix
}

func summarizeToolResultPreview(value string) string {
	trimmed := strings.TrimSpace(value)
	if trimmed == "" {
		return ""
	}
	if utf8.RuneCountInString(trimmed) <= toolSummaryMaxLength {
		return trimmed
	}
	var builder strings.Builder
	count := 0
	for _, r := range trimmed {
		if count >= toolSummaryMaxLength-3 {
			break
		}
		builder.WriteRune(r)
		count++
	}
	return builder.String() + "..."
}

func cloneToolResult(value map[string]any) map[string]any {
	cloned := make(map[string]any, len(value)+6)
	for k, v := range value {
		cloned[k] = v
	}
	return cloned
}
