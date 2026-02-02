package summarizer

import (
	"encoding/json"
	"errors"
	"regexp"
	"strings"
)

var (
	ErrNoJSONFound      = errors.New("no JSON object found in response")
	ErrInvalidJSON      = errors.New("extracted content is not valid JSON")
	ErrUnbalancedBraces = errors.New("unbalanced braces in response")
)

var markdownCodeBlockRe = regexp.MustCompile("(?s)```(?:json)?\\s*(.+?)\\s*```")

// ExtractJSON finds and extracts the first valid JSON object from a string.
// Handles nested objects, escaped characters, and surrounding text.
func ExtractJSON(content string) (string, error) {
	trimmed := strings.TrimSpace(content)

	// Fast path: try direct unmarshal first.
	var test map[string]any
	if err := json.Unmarshal([]byte(trimmed), &test); err == nil {
		return trimmed, nil
	}

	// Find first opening brace.
	start := strings.Index(trimmed, "{")
	if start == -1 {
		return "", ErrNoJSONFound
	}

	end, err := findMatchingBrace(trimmed, start)
	if err != nil {
		return "", err
	}

	candidate := trimmed[start : end+1]
	if err := json.Unmarshal([]byte(candidate), &test); err != nil {
		return "", ErrInvalidJSON
	}

	return candidate, nil
}

// ExtractJSONArray extracts the first valid JSON array from a string.
func ExtractJSONArray(content string) (string, error) {
	trimmed := strings.TrimSpace(content)

	// Fast path: direct unmarshal.
	var test []any
	if err := json.Unmarshal([]byte(trimmed), &test); err == nil {
		return trimmed, nil
	}

	start := strings.Index(trimmed, "[")
	if start == -1 {
		return "", ErrNoJSONFound
	}

	end, err := findMatchingBracket(trimmed, start)
	if err != nil {
		return "", err
	}

	candidate := trimmed[start : end+1]
	if err := json.Unmarshal([]byte(candidate), &test); err != nil {
		return "", ErrInvalidJSON
	}

	return candidate, nil
}

// stripMarkdownCodeBlocks removes fenced code blocks and returns the inner content.
func stripMarkdownCodeBlocks(content string) string {
	if matches := markdownCodeBlockRe.FindStringSubmatch(content); len(matches) > 1 {
		return matches[1]
	}
	return content
}

// findMatchingBrace finds the index of the closing brace matching the opening brace at start.
func findMatchingBrace(s string, start int) (int, error) {
	if start < 0 || start >= len(s) || s[start] != '{' {
		return -1, errors.New("start position must be an opening brace")
	}

	depth := 0
	inString := false
	escaped := false

	for i := start; i < len(s); i++ {
		c := s[i]

		if escaped {
			escaped = false
			continue
		}

		if c == '\\' && inString {
			escaped = true
			continue
		}

		if c == '"' {
			inString = !inString
			continue
		}

		if inString {
			continue
		}

		switch c {
		case '{':
			depth++
		case '}':
			depth--
			if depth == 0 {
				return i, nil
			}
		}
	}

	return -1, ErrUnbalancedBraces
}

// findMatchingBracket finds the index of the closing bracket matching the opening bracket at start.
func findMatchingBracket(s string, start int) (int, error) {
	if start < 0 || start >= len(s) || s[start] != '[' {
		return -1, errors.New("start position must be an opening bracket")
	}

	depth := 0
	inString := false
	escaped := false

	for i := start; i < len(s); i++ {
		c := s[i]

		if escaped {
			escaped = false
			continue
		}

		if c == '\\' && inString {
			escaped = true
			continue
		}

		if c == '"' {
			inString = !inString
			continue
		}

		if inString {
			continue
		}

		switch c {
		case '[':
			depth++
		case ']':
			depth--
			if depth == 0 {
				return i, nil
			}
		}
	}

	return -1, ErrUnbalancedBraces
}
